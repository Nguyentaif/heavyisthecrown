from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cv2
from huggingface_hub import hf_hub_download

from app.services.table_extraction import extract_tables_from_ocr_page

_DEFAULT_SIGNATURE_REPO_ID = "tech4humans/yolov8s-signature-detector"
_DEFAULT_SIGNATURE_MODEL_CANDIDATES = [
    "train/weights/best.pt",
    "yolov8s.pt",
]
_DEFAULT_STAMP2VEC_PIPELINE_ID = "stamps-labs/yolo-stamp"


def _normalize_label(raw_label: str) -> str | None:
    label = (raw_label or "").strip().lower()
    if not label:
        return None
    if "stamp" in label or "seal" in label or "con_dau" in label:
        return "stamp"
    if "signature" in label or "sign" in label or "chu_ky" in label:
        return "signature"
    return None


def _load_yolo_model(model_path: str):
    from ultralytics import YOLO  # type: ignore

    return YOLO(model_path)


def _resolve_local_stamp2vec_root() -> Path | None:
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / "stamp2vec",
        project_root / "external" / "stamp2vec",
        project_root / "external" / "stamp2vec_repo",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _ensure_stamp2vec_import_path() -> None:
    local_root = _resolve_local_stamp2vec_root()
    if local_root is None:
        return
    root_str = str(local_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _load_stamp2vec_pipeline():
    _ensure_stamp2vec_import_path()
    from pipelines.detection.yolo_stamp import YoloStampPipeline  # type: ignore

    return YoloStampPipeline.from_pretrained(_DEFAULT_STAMP2VEC_PIPELINE_ID)


def _resolve_default_signature_model_path() -> str:
    last_error: Exception | None = None
    for filename in _DEFAULT_SIGNATURE_MODEL_CANDIDATES:
        try:
            return str(
                hf_hub_download(
                    repo_id=_DEFAULT_SIGNATURE_REPO_ID,
                    filename=filename,
                )
            )
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            last_error = exc
            continue
    if last_error is None:
        raise RuntimeError("No candidate model file configured.")
    raise RuntimeError(
        f"Cannot download signature model from {_DEFAULT_SIGNATURE_REPO_ID}: {last_error}"
    ) from last_error


def _predict_detections(model: Any, image_bgr, conf_threshold: float) -> list[dict[str, Any]]:
    results = model.predict(image_bgr, conf=conf_threshold, verbose=False)
    detections: list[dict[str, Any]] = []
    for result in results:
        names = getattr(result, "names", {})
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            cls_idx = int(box.cls[0].item())
            label_name = str(names.get(cls_idx, cls_idx))
            normalized_label = _normalize_label(label_name)
            if normalized_label is None:
                continue
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            detections.append(
                {
                    "label": normalized_label,
                    "confidence": conf,
                    "bbox": [int(round(x1)), int(round(y1)), int(round(max(0, x2 - x1))), int(round(max(0, y2 - y1)))],
                }
            )
    return detections


def _predict_stamp2vec_stamp_detections(
    pipeline: Any,
    image_bgr,
    conf_threshold: float,
) -> list[dict[str, Any]]:
    from PIL import Image

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    prediction = pipeline(Image.fromarray(image_rgb))
    if isinstance(prediction, dict):
        candidates = (
            prediction.get("boxes")
            or prediction.get("bboxes")
            or prediction.get("detections")
            or prediction.get("predictions")
            or []
        )
    elif isinstance(prediction, (list, tuple)):
        candidates = list(prediction)
    else:
        candidates = []

    detections: list[dict[str, Any]] = []
    for item in candidates:
        x1 = y1 = x2 = y2 = None
        confidence = 1.0
        if isinstance(item, dict):
            bbox = item.get("bbox") or item.get("box")
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[:4]
            else:
                x1 = item.get("x1")
                y1 = item.get("y1")
                x2 = item.get("x2")
                y2 = item.get("y2")
            confidence = float(item.get("score", item.get("confidence", 1.0)))
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            x1, y1, x2, y2 = item[:4]
            if len(item) >= 5:
                confidence = float(item[4])

        if None in (x1, y1, x2, y2):
            continue
        if confidence < conf_threshold:
            continue
        width = max(0.0, float(x2) - float(x1))
        height = max(0.0, float(y2) - float(y1))
        detections.append(
            {
                "label": "stamp",
                "confidence": confidence,
                "bbox": [
                    int(round(float(x1))),
                    int(round(float(y1))),
                    int(round(width)),
                    int(round(height)),
                ],
            }
        )
    return detections


def detect_stamp_signature_for_pages(
    input_paths: list[str],
    *,
    model_path: str | None = None,
    conf_threshold: float = 0.25,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    signature_model = None
    signature_error: str | None = None
    try:
        if model_path:
            signature_model = _load_yolo_model(model_path)
    except Exception as exc:
        signature_error = f"Cannot load signature YOLO model: {exc}"

    stamp_pipeline = None
    stamp_error: str | None = None
    try:
        stamp_pipeline = _load_stamp2vec_pipeline()
    except Exception as exc:
        stamp_error = f"Cannot load stamp2vec pipeline: {exc}"

    if signature_model is None and stamp_pipeline is None:
        for input_path in input_paths:
            pages.append(
                {
                    "input_path": input_path,
                    "has_stamp": False,
                    "has_signature": False,
                    "detections": [],
                }
            )
        reason_parts = [part for part in [signature_error, stamp_error] if part]
        return {
            "available": False,
            "reason": "; ".join(reason_parts) or "No detector backend is available.",
            "pages": pages,
        }

    for input_path in input_paths:
        image = cv2.imread(str(Path(input_path)))
        if image is None:
            detections = []
        else:
            detections: list[dict[str, Any]] = []
            if signature_model is not None:
                signature_predictions = _predict_detections(
                    signature_model,
                    image,
                    conf_threshold=conf_threshold,
                )
                detections.extend(
                    item for item in signature_predictions if item.get("label") == "signature"
                )
            if stamp_pipeline is not None:
                detections.extend(
                    _predict_stamp2vec_stamp_detections(
                        stamp_pipeline,
                        image,
                        conf_threshold=conf_threshold,
                    )
                )
        has_stamp = any(item["label"] == "stamp" for item in detections)
        has_signature = any(item["label"] == "signature" for item in detections)
        pages.append(
            {
                "input_path": input_path,
                "has_stamp": has_stamp,
                "has_signature": has_signature,
                "detections": detections,
            }
        )

    reason = None
    if signature_error or stamp_error:
        reason = "; ".join([part for part in [signature_error, stamp_error] if part]) or None
    return {"available": True, "reason": reason, "pages": pages}


def run_postprocess_pipeline(
    ocr_pages: list[dict[str, Any]],
    *,
    yolo_model_path: str | None = None,
    conf_threshold: float = 0.25,
) -> dict[str, Any]:
    effective_model_path = yolo_model_path
    if not effective_model_path:
        try:
            effective_model_path = _resolve_default_signature_model_path()
        except Exception:
            effective_model_path = None

    detection_result = detect_stamp_signature_for_pages(
        [page.get("input_path", "") for page in ocr_pages],
        model_path=effective_model_path,
        conf_threshold=conf_threshold,
    )
    page_detection_map = {item["input_path"]: item for item in detection_result["pages"]}

    pages: list[dict[str, Any]] = []
    for page in ocr_pages:
        input_path = page.get("input_path", "")
        detection = page_detection_map.get(
            input_path,
            {"has_stamp": False, "has_signature": False, "detections": []},
        )
        tables = extract_tables_from_ocr_page(page)
        pages.append(
            {
                "input_path": input_path,
                "has_stamp": bool(detection.get("has_stamp", False)),
                "has_signature": bool(detection.get("has_signature", False)),
                "detections": detection.get("detections", []),
                "tables": tables,
            }
        )

    summary = {
        "total_pages": len(pages),
        "pages_with_stamp": sum(1 for page in pages if page["has_stamp"]),
        "pages_with_signature": sum(1 for page in pages if page["has_signature"]),
    }
    return {
        "available": bool(detection_result.get("available", False)),
        "pages": pages,
        "summary": summary,
    }
