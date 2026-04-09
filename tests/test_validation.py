from datetime import date

from app.services.validation import validate_document_logic


def _field(value: str, confidence: float = 0.9) -> dict:
    return {"value": value, "confidence": confidence}


def test_validate_document_logic_detects_future_issue_date():
    kie_document = {
        "so_van_ban": _field("56/2024/NĐ-CP"),
        "ngay_ban_hanh": _field("ngày 01 tháng 01 năm 2099"),
    }
    result = validate_document_logic(kie_document, today=date(2026, 4, 6))

    assert result["valid"] is False
    assert any(issue["code"] == "future_issue_date" for issue in result["issues"])


def test_validate_document_logic_flags_document_number_format_warning():
    kie_document = {
        "so_van_ban": _field("ABC 12"),
        "ngay_ban_hanh": _field("05/04/2026"),
    }
    result = validate_document_logic(kie_document, today=date(2026, 4, 6))

    assert any(issue["code"] == "invalid_document_number_format" for issue in result["issues"])
