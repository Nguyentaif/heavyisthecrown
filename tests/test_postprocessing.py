from pathlib import Path

import cv2
import numpy as np

from app.services.postprocessing import detect_stamp_signature_for_pages
from app.services.postprocessing import run_postprocess_pipeline
from app.services.postprocessing import _ensure_stamp2vec_import_path


def test_detect_stamp_signature_for_pages_returns_unavailable_without_model(tmp_path: Path):
    image = np.full((80, 120, 3), 255, dtype=np.uint8)
    image_path = tmp_path / "p1.png"
    cv2.imwrite(str(image_path), image)

    # Ensure deterministic behavior independent of local optional installation.
    def _raise_import_error():
        raise ModuleNotFoundError("stamp2vec not installed")

    import app.services.postprocessing as postprocessing_module

    original_loader = postprocessing_module._load_stamp2vec_pipeline
    try:
        postprocessing_module._load_stamp2vec_pipeline = _raise_import_error
        result = detect_stamp_signature_for_pages([str(image_path)], model_path=None)
    finally:
        postprocessing_module._load_stamp2vec_pipeline = original_loader

    assert result["available"] is False
    assert len(result["pages"]) == 1
    assert result["pages"][0]["has_stamp"] is False
    assert result["pages"][0]["has_signature"] is False


def test_detect_stamp_signature_for_pages_parses_predictions(monkeypatch, tmp_path: Path):
    image = np.full((80, 120, 3), 255, dtype=np.uint8)
    image_path = tmp_path / "p2.png"
    cv2.imwrite(str(image_path), image)

    monkeypatch.setattr("app.services.postprocessing._load_yolo_model", lambda _: object())
    monkeypatch.setattr("app.services.postprocessing._load_stamp2vec_pipeline", lambda: object())
    monkeypatch.setattr(
        "app.services.postprocessing._predict_detections",
        lambda model, image_bgr, conf_threshold: [
            {"label": "signature", "confidence": 0.83, "bbox": [25, 35, 50, 16]},
        ],
    )
    monkeypatch.setattr(
        "app.services.postprocessing._predict_stamp2vec_stamp_detections",
        lambda pipeline, image_bgr, conf_threshold: [
            {"label": "stamp", "confidence": 0.91, "bbox": [5, 5, 20, 20]}
        ],
    )

    result = detect_stamp_signature_for_pages([str(image_path)], model_path="fake.pt")
    page = result["pages"][0]
    assert result["available"] is True
    assert page["has_stamp"] is True
    assert page["has_signature"] is True
    assert len(page["detections"]) == 2


def test_run_postprocess_pipeline_uses_default_hf_signature_model(monkeypatch):
    ocr_pages = [{"input_path": "p1.png", "full_text": "A", "lines": []}]

    monkeypatch.setattr(
        "app.services.postprocessing._resolve_default_signature_model_path",
        lambda: "hf-default.pt",
    )

    def fake_detect(input_paths, model_path, conf_threshold):
        assert model_path == "hf-default.pt"
        return {
            "available": True,
            "reason": None,
            "pages": [
                {
                    "input_path": input_paths[0],
                    "has_stamp": False,
                    "has_signature": True,
                    "detections": [],
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.postprocessing.detect_stamp_signature_for_pages",
        fake_detect,
    )

    result = run_postprocess_pipeline(ocr_pages=ocr_pages, yolo_model_path=None)
    assert result["available"] is True
    assert result["summary"]["pages_with_signature"] == 1


def test_detect_stamp_signature_for_pages_uses_stamp2vec_for_stamp(monkeypatch, tmp_path: Path):
    image = np.full((100, 140, 3), 255, dtype=np.uint8)
    image_path = tmp_path / "stamp.png"
    cv2.imwrite(str(image_path), image)

    monkeypatch.setattr(
        "app.services.postprocessing._load_stamp2vec_pipeline",
        lambda: object(),
    )
    monkeypatch.setattr(
        "app.services.postprocessing._predict_stamp2vec_stamp_detections",
        lambda pipeline, image_bgr, conf_threshold: [
            {"label": "stamp", "confidence": 0.88, "bbox": [10, 10, 30, 30]}
        ],
    )

    result = detect_stamp_signature_for_pages([str(image_path)], model_path=None)
    page = result["pages"][0]
    assert result["available"] is True
    assert page["has_stamp"] is True
    assert page["has_signature"] is False


def test_ensure_stamp2vec_import_path_adds_local_repo(monkeypatch, tmp_path: Path):
    local_repo = tmp_path / "stamp2vec"
    local_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "app.services.postprocessing._resolve_local_stamp2vec_root",
        lambda: local_repo,
    )

    import app.services.postprocessing as postprocessing_module

    path_str = str(local_repo)
    original = list(postprocessing_module.sys.path)
    try:
        postprocessing_module.sys.path = [p for p in original if p != path_str]
        _ensure_stamp2vec_import_path()
        assert postprocessing_module.sys.path[0] == path_str
    finally:
        postprocessing_module.sys.path = original
