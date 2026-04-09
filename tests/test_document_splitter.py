from app.services.document_splitter import split_document_by_content


def _field(value: str | None, confidence: float) -> dict:
    return {"value": value, "confidence": confidence}


def _doc_kie(doc_type: str | None, conf: float) -> dict:
    return {
        "so_van_ban": _field("12/2025/QĐ-UBND", 0.9 if doc_type else 0.0),
        "ngay_ban_hanh": _field("05/04/2026", 0.9 if doc_type else 0.0),
        "co_quan_ban_hanh": _field("UBND TP HA NOI", 0.9 if doc_type else 0.0),
        "loai_van_ban": _field(doc_type, conf),
        "trich_yeu": _field("Van ban test", 0.8 if doc_type else 0.0),
        "custom_fields": {},
        "model_used": None,
    }


def test_split_document_by_content_creates_two_documents(monkeypatch):
    ocr_pages = [
        {"input_path": "p1.png", "full_text": "A", "lines": []},
        {"input_path": "p2.png", "full_text": "B", "lines": []},
        {"input_path": "p3.png", "full_text": "C", "lines": []},
        {"input_path": "p4.png", "full_text": "D", "lines": []},
    ]

    page_kie = [
        _doc_kie("Quyet dinh", 0.95),
        _doc_kie(None, 0.0),
        _doc_kie("Cong van", 0.94),
        _doc_kie(None, 0.0),
    ]

    def fake_extract_kie_from_pages(ocr_pages, model, ollama_url, use_llm, template):
        first_page = ocr_pages[0]["input_path"] if ocr_pages else ""
        if len(ocr_pages) == 4:
            return {
                "pages": [{"kie": k} for k in page_kie],
                "document": _doc_kie("Quyet dinh", 0.95),
            }
        if first_page == "p1.png":
            return {"pages": [], "document": _doc_kie("Quyet dinh", 0.95)}
        return {"pages": [], "document": _doc_kie("Cong van", 0.94)}

    monkeypatch.setattr(
        "app.services.document_splitter.extract_kie_from_pages",
        fake_extract_kie_from_pages,
    )

    result = split_document_by_content(ocr_pages=ocr_pages, use_llm=False)

    assert result["total_documents"] == 2
    assert result["documents"][0]["start_page"] == 1
    assert result["documents"][0]["end_page"] == 2
    assert result["documents"][1]["start_page"] == 3
    assert result["documents"][1]["end_page"] == 4
