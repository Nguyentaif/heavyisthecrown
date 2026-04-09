from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app.schemas import PreprocessOptions
from app.services.document_scanner import run_document_scanner


def is_blank_page(image_bgr: np.ndarray, threshold: float = 0.006) -> bool:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )
    text_ratio = float(np.count_nonzero(binary)) / binary.size
    return text_ratio < threshold


def deskew_image(image_bgr: np.ndarray) -> np.ndarray:
    angle = estimate_skew_angle(image_bgr)
    if abs(angle) < 0.7:
        return image_bgr

    h, w = image_bgr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        image_bgr,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _estimate_skew_angle_by_min_area_rect(binary_inv: np.ndarray) -> float:
    h, w = binary_inv.shape[:2]
    margin_y = max(2, int(0.02 * h))
    margin_x = max(2, int(0.02 * w))
    focused = binary_inv.copy()
    focused[:margin_y, :] = 0
    focused[h - margin_y :, :] = 0
    focused[:, :margin_x] = 0
    focused[:, w - margin_x :] = 0

    coords = np.column_stack(np.where(focused > 0))
    if coords.shape[0] < 50:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    normalized = -(90 + angle) if angle < -45 else -angle
    return float(np.clip(normalized, -45.0, 45.0))


def estimate_skew_angle(image_bgr: np.ndarray) -> float:
    """
    Estimate document skew angle in degrees (positive means CCW-tilted text).
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    binary_inv = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    lines = cv2.HoughLinesP(
        binary_inv,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=max(60, int(0.2 * image_bgr.shape[1])),
        maxLineGap=20,
    )
    if lines is not None and len(lines) > 0:
        angles: list[float] = []
        for line in lines[:, 0]:
            x1, y1, x2, y2 = line.tolist()
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            while angle <= -90.0:
                angle += 180.0
            while angle > 90.0:
                angle -= 180.0
            if abs(angle) <= 45.0:
                angles.append(angle)

        if angles:
            return float(np.median(np.array(angles, dtype=np.float32)))

    return _estimate_skew_angle_by_min_area_rect(binary_inv)


def auto_crop_document(image_bgr: np.ndarray) -> np.ndarray:
    scanned = run_document_scanner(image_bgr)
    return scanned["color"]


def remove_yellow_stains(image_bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)

    a_shift = a_channel.astype(np.float32) - 128.0
    b_shift = b_channel.astype(np.float32) - 128.0
    a_channel = np.clip(a_channel.astype(np.float32) - 0.25 * a_shift, 0, 255).astype(
        np.uint8
    )
    b_channel = np.clip(b_channel.astype(np.float32) - 0.45 * b_shift, 0, 255).astype(
        np.uint8
    )

    merged = cv2.merge([l_channel, a_channel, b_channel])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def remove_shadows(image_bgr: np.ndarray) -> np.ndarray:
    """
    Illumination normalization inspired by common OpenCV document-scanner pipelines.
    """
    channels = cv2.split(image_bgr)
    normalized_channels: list[np.ndarray] = []
    kernel = np.ones((7, 7), np.uint8)

    for channel in channels:
        dilated = cv2.dilate(channel, kernel)
        background = cv2.medianBlur(dilated, 21)
        diff = cv2.absdiff(channel, background)
        inverted = 255 - diff
        normalized = cv2.normalize(
            inverted, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX
        )
        normalized_channels.append(normalized)

    return cv2.merge(normalized_channels)


def denoise_image(image_bgr: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(image_bgr, None, 7, 7, 7, 21)


def get_red_stamp_mask(image_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lower_red_1 = np.array([0, 60, 40], dtype=np.uint8)
    upper_red_1 = np.array([12, 255, 255], dtype=np.uint8)
    lower_red_2 = np.array([160, 60, 40], dtype=np.uint8)
    upper_red_2 = np.array([180, 255, 255], dtype=np.uint8)
    mask_1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
    mask_2 = cv2.inRange(hsv, lower_red_2, upper_red_2)
    return cv2.bitwise_or(mask_1, mask_2)


def adaptive_binarize(
    image_bgr: np.ndarray, preserve_red_stamp: bool, reference_bgr: np.ndarray | None = None
) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )
    binarized_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    if not preserve_red_stamp:
        return binarized_bgr

    source_for_stamp = image_bgr if reference_bgr is None else reference_bgr
    red_mask = get_red_stamp_mask(source_for_stamp)
    red_mask_3c = cv2.cvtColor(red_mask, cv2.COLOR_GRAY2BGR)
    preserved = np.where(red_mask_3c > 0, source_for_stamp, binarized_bgr)
    return preserved.astype(np.uint8)


def preprocess_image(image_bgr: np.ndarray, options: PreprocessOptions) -> np.ndarray:
    if options.auto_crop or options.deskew:
        scanned = run_document_scanner(image_bgr)
        processed_color = scanned["color"]
        binary_bgr = cv2.cvtColor(scanned["binary"], cv2.COLOR_GRAY2BGR)
    else:
        processed_color = image_bgr.copy()
        binary_bgr = cv2.cvtColor(
            cv2.adaptiveThreshold(
                cv2.cvtColor(processed_color, cv2.COLOR_BGR2GRAY),
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                15,
            ),
            cv2.COLOR_GRAY2BGR,
        )

    if options.shadow_removal:
        processed_color = remove_shadows(processed_color)
    if options.remove_yellow_stains:
        processed_color = remove_yellow_stains(processed_color)
    if options.denoise:
        processed_color = denoise_image(processed_color)

    if not options.binarize:
        return processed_color

    if not options.preserve_red_stamp:
        return binary_bgr

    red_mask = get_red_stamp_mask(processed_color)
    red_mask = cv2.dilate(
        red_mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    red_mask_3c = cv2.cvtColor(red_mask, cv2.COLOR_GRAY2BGR)
    preserved = np.where(red_mask_3c > 0, processed_color, binary_bgr)
    return preserved.astype(np.uint8)


def run_preprocess_pipeline(
    input_paths: list[str], output_dir: Path, options: PreprocessOptions
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for input_path in input_paths:
        image = cv2.imread(input_path)
        if image is None:
            raise ValueError(f"Cannot read image at path: {input_path}")

        if options.remove_blank_pages and is_blank_page(
            image, threshold=options.blank_ratio_threshold
        ):
            results.append(
                {
                    "input_path": input_path,
                    "output_path": None,
                    "skipped_as_blank": True,
                }
            )
            continue

        processed = preprocess_image(image, options)
        unique_suffix = uuid4().hex[:8]
        output_path = output_dir / f"{Path(input_path).stem}_{unique_suffix}_clean.png"
        write_ok = cv2.imwrite(str(output_path), processed)
        if not write_ok:
            raise ValueError(f"Failed to write preprocessed image to: {output_path}")
        results.append(
            {
                "input_path": input_path,
                "output_path": str(output_path),
                "skipped_as_blank": False,
            }
        )

    return results
