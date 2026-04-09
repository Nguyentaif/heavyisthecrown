from app.services.table_extraction import extract_tables_from_ocr_page


def _line(text: str, x: int, y: int, w: int = 70, h: int = 20) -> dict:
    return {"text": text, "bbox": [x, y, w, h], "confidence": 95.0}


def test_extract_tables_from_ocr_page_returns_grid_for_tabular_lines():
    page = {
        "input_path": "p1.png",
        "full_text": "",
        "lines": [
            _line("So hieu", 40, 50),
            _line("Ngay", 220, 50),
            _line("01/2026", 40, 90),
            _line("05/04/2026", 220, 90),
        ],
    }
    tables = extract_tables_from_ocr_page(page)

    assert len(tables) == 1
    assert tables[0]["row_count"] == 2
    assert tables[0]["column_count"] == 2
    assert tables[0]["rows"][0]["cells"][0] == "So hieu"
    assert tables[0]["rows"][1]["cells"][1] == "05/04/2026"


def test_extract_tables_from_ocr_page_returns_empty_when_not_table_like():
    page = {
        "input_path": "p1.png",
        "full_text": "",
        "lines": [_line("Van ban hanh chinh", 20, 40), _line("Doan van ban tiep theo", 20, 75)],
    }
    tables = extract_tables_from_ocr_page(page)
    assert tables == []
