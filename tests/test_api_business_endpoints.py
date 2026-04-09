from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


client = TestClient(app)


def _kie_field(value, confidence=0.9):
    return {"value": value, "confidence": confidence}


def _kie_document(doc_type="Quyet dinh"):
    return {
        "so_van_ban": _kie_field("12/2025/QD-UBND"),
        "ngay_ban_hanh": _kie_field("05/04/2026"),
        "co_quan_ban_hanh": _kie_field("UBND"),
        "loai_van_ban": _kie_field(doc_type, 0.92),
        "trich_yeu": _kie_field("Noi dung"),
        "custom_fields": {},
        "model_used": None,
    }


def test_extract_fields_endpoint_success(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        return {
            "total_pages": 1,
            "pages": [{"input_path": input_paths[0], "full_text": "abc", "lines": []}],
        }

    def fake_extract_kie_from_pages(ocr_pages, model, ollama_url, use_llm, template):
        return {"pages": [{"kie": _kie_document()}], "document": _kie_document()}

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)
    monkeypatch.setattr(main_module, "extract_kie_from_pages", fake_extract_kie_from_pages)
    monkeypatch.setattr(
        main_module,
        "validate_document_logic",
        lambda doc: {"valid": True, "issues": []},
    )

    response = client.post("/api/v1/extract-fields", json={"input_paths": ["a.png"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["loai_van_ban"]["value"] == "Quyet dinh"
    assert payload["validation"]["valid"] is True


def test_split_document_endpoint_success(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        return {
            "total_pages": 2,
            "pages": [
                {"input_path": "a.png", "full_text": "A", "lines": []},
                {"input_path": "b.png", "full_text": "B", "lines": []},
            ],
        }

    def fake_split_document_by_content(ocr_pages, model, ollama_url, use_llm, template):
        return {
            "total_pages": 2,
            "total_documents": 1,
            "documents": [
                {
                    "document_id": "doc-1",
                    "start_page": 1,
                    "end_page": 2,
                    "page_paths": ["a.png", "b.png"],
                    "title": "Quyet dinh",
                    "doc_type": "Quyet dinh",
                    "confidence": 0.92,
                    "classification": _kie_document(),
                }
            ],
            "tree": {
                "title": "Root",
                "children": [
                    {
                        "id": "doc-1",
                        "title": "Quyet dinh",
                        "start_page": 1,
                        "end_page": 2,
                        "children": [],
                    }
                ],
            },
        }

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)
    monkeypatch.setattr(main_module, "split_document_by_content", fake_split_document_by_content)

    response = client.post("/api/v1/split-document", json={"input_paths": ["a.png", "b.png"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_documents"] == 1
    assert payload["documents"][0]["title"] == "Quyet dinh"
