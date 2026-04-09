from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

import cv2

_DEEPOCR_ENGINE = None
_DEEPOCR_LOCK = threading.Lock()


def _resolve_deepdoc_root() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / "deepdoc_vietocr",
        project_root / "external" / "deepdoc_vietocr",
        project_root / "external" / "deepdoc_vietocr_repo",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "Cannot find deepdoc_vietocr source folder. Expected one of: "
        "deepdoc_vietocr/, external/deepdoc_vietocr/, external/deepdoc_vietocr_repo/."
    )


def _get_deepdoc_engine():
    global _DEEPOCR_ENGINE
    if _DEEPOCR_ENGINE is not None:
        return _DEEPOCR_ENGINE

    with _DEEPOCR_LOCK:
        if _DEEPOCR_ENGINE is not None:
            return _DEEPOCR_ENGINE

        deepdoc_root = _resolve_deepdoc_root()
        # deepdoc module uses absolute imports like "from utils.file_utils ...".
        # Adding this path allows those imports to resolve from deepdoc_vietocr/utils.
        deepdoc_root_str = str(deepdoc_root)
        if deepdoc_root_str not in sys.path:
            sys.path.insert(0, deepdoc_root_str)

        try:
            from deepdoc_vietocr.module.ocr import OCR as DeepDocOCR
        except ModuleNotFoundError as exc:
            missing = exc.name or "unknown"
            raise RuntimeError(
                "Failed to import deepdoc_vietocr OCR due to missing dependency "
                f"`{missing}`. Install project requirements with: pip install -r requirements.txt"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                "Failed to import deepdoc_vietocr OCR. Install required deps first "
                "(for example: pdfplumber, onnxruntime, huggingface-hub, ruamel.yaml, "
                "cachetools, pycryptodomex, strenum)."
            ) from exc

        try:
            _DEEPOCR_ENGINE = DeepDocOCR()
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize deepdoc_vietocr OCR: {exc}") from exc
        return _DEEPOCR_ENGINE


def _quad_to_bbox(points: list[list[float]]) -> list[int]:
    if not points:
        return [0, 0, 0, 0]
    xs = [int(round(point[0])) for point in points]
    ys = [int(round(point[1])) for point in points]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return [left, top, max(0, right - left), max(0, bottom - top)]


def _normalize_deepdoc_result(raw_items: Any) -> list[dict]:
    lines: list[dict] = []
    if not raw_items:
        return lines

    for item in raw_items:
        if not item or len(item) != 2:
            continue
        points, recognition = item
        if not recognition or len(recognition) != 2:
            continue

        text, score = recognition
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            continue

        confidence = float(score)
        if confidence <= 1.0:
            confidence *= 100.0

        lines.append(
            {
                "text": cleaned_text,
                "bbox": _quad_to_bbox(points),
                "confidence": confidence,
            }
        )
    return lines


def run_ocr_fulltext(
    input_paths: list[str], lang: str = "vie", psm: int = 6, oem: int = 3
) -> dict:
    # Keep API compatibility with previous request schema; deepdoc OCR does not use these.
    _ = (lang, psm, oem)

    ocr_engine = _get_deepdoc_engine()
    pages: list[dict] = []

    for input_path in input_paths:
        image_path = Path(input_path)
        if not image_path.exists():
            raise ValueError(f"Input image does not exist: {input_path}")

        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            raise ValueError(f"Cannot read image for OCR: {input_path}")

        try:
            deepdoc_items = ocr_engine(image_bgr)
        except Exception as exc:
            raise RuntimeError(f"deepdoc_vietocr failed for {input_path}: {exc}") from exc

        lines = _normalize_deepdoc_result(deepdoc_items)
        full_text = "\n".join(line["text"] for line in lines).strip()
        pages.append(
            {
                "input_path": input_path,
                "full_text": full_text,
                "lines": lines,
            }
        )

    return {"total_pages": len(pages), "pages": pages}
