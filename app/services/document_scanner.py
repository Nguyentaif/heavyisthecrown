from __future__ import annotations

import math

import cv2
import numpy as np


def _order_points(points: np.ndarray) -> np.ndarray:
    x_sorted = points[np.argsort(points[:, 0]), :]
    left = x_sorted[:2, :]
    right = x_sorted[2:, :]

    left = left[np.argsort(left[:, 1]), :]
    tl, bl = left

    distances = np.linalg.norm(right - tl, axis=1)
    br, tr = right[np.argsort(distances)[::-1], :]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _four_point_transform(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    rect = _order_points(points.astype(np.float32))
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))

    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _angle_between_vectors_degrees(vector_u: np.ndarray, vector_v: np.ndarray) -> float:
    denom = float(np.linalg.norm(vector_u) * np.linalg.norm(vector_v))
    if denom == 0:
        return 180.0
    value = float(np.dot(vector_u, vector_v) / denom)
    value = max(-1.0, min(1.0, value))
    return float(np.degrees(math.acos(value)))


def _quad_angle_range(quad: np.ndarray) -> float:
    tl, tr, br, bl = quad
    vectors = [
        (tl - tr, br - tr),
        (bl - tl, tr - tl),
        (tr - br, bl - br),
        (br - bl, tl - bl),
    ]
    angles = [_angle_between_vectors_degrees(u, v) for u, v in vectors]
    return float(np.ptp(np.array(angles, dtype=np.float32)))


def _is_valid_quad(
    contour: np.ndarray,
    image_w: int,
    image_h: int,
    min_quad_area_ratio: float,
    max_quad_angle_range: float,
) -> bool:
    if len(contour) != 4:
        return False
    area = cv2.contourArea(contour.astype(np.float32))
    if area <= image_w * image_h * min_quad_area_ratio:
        return False
    quad = contour.reshape(4, 2).astype(np.float32)
    return _quad_angle_range(quad) < max_quad_angle_range


def detect_document_corners(
    image_bgr: np.ndarray,
    min_quad_area_ratio: float = 0.25,
    max_quad_angle_range: float = 40.0,
    rescaled_height: float = 500.0,
) -> np.ndarray:
    ratio = image_bgr.shape[0] / rescaled_height
    resized = cv2.resize(
        image_bgr,
        (int(image_bgr.shape[1] / ratio), int(rescaled_height)),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    edged = cv2.Canny(closed, 0, 84)

    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if _is_valid_quad(
            approx,
            image_w=resized.shape[1],
            image_h=resized.shape[0],
            min_quad_area_ratio=min_quad_area_ratio,
            max_quad_angle_range=max_quad_angle_range,
        ):
            return approx.reshape(4, 2).astype(np.float32) * ratio

    h, w = image_bgr.shape[:2]
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)


def run_document_scanner(image_bgr: np.ndarray) -> dict[str, np.ndarray]:
    corners = detect_document_corners(image_bgr)
    warped_color = _four_point_transform(image_bgr, corners)
    gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    sharpen = cv2.GaussianBlur(gray, (0, 0), 3)
    sharpen = cv2.addWeighted(gray, 1.5, sharpen, -0.5, 0)
    warped_binary = cv2.adaptiveThreshold(
        sharpen,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        15,
    )
    return {"color": warped_color, "binary": warped_binary}


def _full_image_corners(image_bgr: np.ndarray) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)


def _interactive_adjust_corners(
    image_bgr: np.ndarray, corners: np.ndarray, window_name: str = "Manual Corner Adjust"
) -> np.ndarray:
    points = corners.astype(np.float32).copy()
    original_points = points.copy()
    drag_state = {"idx": None}
    render_state = {"scale": 1.0, "offset_x": 0, "offset_y": 0, "view_w": 0, "view_h": 0}
    radius_px = 16

    def draw() -> np.ndarray:
        try:
            _, _, window_w, window_h = cv2.getWindowImageRect(window_name)
            view_w = max(window_w, 1)
            view_h = max(window_h, 1)
        except Exception:
            view_w, view_h = 1200, 800

        image_h, image_w = image_bgr.shape[:2]
        scale = min(view_w / image_w, view_h / image_h)
        scale = max(scale, 1e-6)
        disp_w = max(1, int(image_w * scale))
        disp_h = max(1, int(image_h * scale))
        offset_x = (view_w - disp_w) // 2
        offset_y = (view_h - disp_h) // 2

        render_state["scale"] = scale
        render_state["offset_x"] = offset_x
        render_state["offset_y"] = offset_y
        render_state["view_w"] = view_w
        render_state["view_h"] = view_h

        resized = cv2.resize(image_bgr, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        canvas = np.full((view_h, view_w, 3), 235, dtype=np.uint8)
        canvas[offset_y : offset_y + disp_h, offset_x : offset_x + disp_w] = resized

        points_display = points * scale + np.array([offset_x, offset_y], dtype=np.float32)
        polygon = points_display.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(canvas, [polygon], True, (0, 255, 255), 2)
        for idx, point in enumerate(points_display):
            x, y = int(point[0]), int(point[1])
            cv2.circle(canvas, (x, y), radius_px, (50, 120, 255), 2)
            cv2.putText(
                canvas,
                str(idx + 1),
                (x + 10, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (30, 30, 220),
                2,
                cv2.LINE_AA,
            )
        cv2.putText(
            canvas,
            "Drag corners | Enter: apply | R: reset | Esc: cancel",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (20, 180, 20),
            2,
            cv2.LINE_AA,
        )
        return canvas

    def display_to_image(x: int, y: int) -> tuple[float, float] | None:
        scale = float(render_state["scale"])
        offset_x = int(render_state["offset_x"])
        offset_y = int(render_state["offset_y"])
        view_w = int(render_state["view_w"])
        view_h = int(render_state["view_h"])
        if not (0 <= x < view_w and 0 <= y < view_h):
            return None
        img_x = (x - offset_x) / scale
        img_y = (y - offset_y) / scale
        if not (0 <= img_x < image_bgr.shape[1] and 0 <= img_y < image_bgr.shape[0]):
            return None
        return float(img_x), float(img_y)

    def on_mouse(event: int, x: int, y: int, _flags: int, _params: object) -> None:
        mapped = display_to_image(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            if mapped is None:
                return
            click_point = np.array(mapped, dtype=np.float32)
            idx = int(np.argmin(np.linalg.norm(points - click_point, axis=1)))
            max_pick_dist = radius_px * 2 / max(float(render_state["scale"]), 1e-6)
            if np.linalg.norm(points[idx] - click_point) <= max_pick_dist:
                drag_state["idx"] = idx
        elif event == cv2.EVENT_MOUSEMOVE and drag_state["idx"] is not None:
            if mapped is None:
                return
            points[drag_state["idx"], 0] = float(np.clip(mapped[0], 0, image_bgr.shape[1] - 1))
            points[drag_state["idx"], 1] = float(np.clip(mapped[1], 0, image_bgr.shape[0] - 1))
        elif event == cv2.EVENT_LBUTTONUP:
            drag_state["idx"] = None

    window_created = False
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        initial_w = min(1200, image_bgr.shape[1])
        initial_h = min(900, image_bgr.shape[0])
        cv2.resizeWindow(window_name, initial_w, initial_h)
        cv2.setMouseCallback(window_name, on_mouse)
        window_created = True
    except cv2.error:
        # HighGUI is unavailable (e.g. headless environment). Keep auto corners.
        return points

    try:
        while True:
            cv2.imshow(window_name, draw())
            key = cv2.waitKey(16) & 0xFF
            if key in (13, 10, 32):  # Enter / Return / Space
                break
            if key in (ord("r"), ord("R")):
                points[:] = original_points
            if key == 27:  # Esc
                points[:] = original_points
                break
    finally:
        if window_created:
            cv2.destroyWindow(window_name)

    return points


def run_document_scanner_interactive(
    image_bgr: np.ndarray, use_auto_init: bool = True
) -> dict[str, np.ndarray]:
    corners = detect_document_corners(image_bgr) if use_auto_init else _full_image_corners(image_bgr)
    corners = _interactive_adjust_corners(image_bgr, corners)
    warped_color = _four_point_transform(image_bgr, corners)
    gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    sharpen = cv2.GaussianBlur(gray, (0, 0), 3)
    sharpen = cv2.addWeighted(gray, 1.5, sharpen, -0.5, 0)
    warped_binary = cv2.adaptiveThreshold(
        sharpen,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        15,
    )
    return {"color": warped_color, "binary": warped_binary}
