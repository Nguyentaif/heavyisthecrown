from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


client = TestClient(app)


def test_postprocess_check_endpoint_success(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        return {
            "total_pages": 1,
            "pages": [
                {
                    "input_path": input_paths[0],
                    "full_text": "A",
                    "lines": [{"text": "A", "bbox": [10, 10, 20, 10], "confidence": 95.0}],
                }
            ],
        }

    def fake_run_postprocess_pipeline(ocr_pages, yolo_model_path, conf_threshold):
        return {
            "available": True,
            "pages": [
                {
                    "input_path": ocr_pages[0]["input_path"],
                    "has_stamp": True,
                    "has_signature": False,
                    "detections": [{"label": "stamp", "confidence": 0.91, "bbox": [5, 5, 20, 20]}],
                    "tables": [{"table_id": "table-1", "row_count": 2, "column_count": 2, "rows": []}],
                }
            ],
            "summary": {"total_pages": 1, "pages_with_stamp": 1, "pages_with_signature": 0},
        }

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)
    monkeypatch.setattr(main_module, "run_postprocess_pipeline", fake_run_postprocess_pipeline)

    response = client.post(
        "/api/v1/postprocess-check",
        json={"input_paths": ["a.png"], "yolo_model_path": "model.pt"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["summary"]["pages_with_stamp"] == 1
    assert payload["pages"][0]["tables"][0]["column_count"] == 2
