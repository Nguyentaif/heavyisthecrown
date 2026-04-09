from __future__ import annotations

import re
from datetime import date
from typing import Any


_DMY_PATTERN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
_VN_DATE_PATTERN = re.compile(
    r"ng[àa]y\s+(\d{1,2})\s+th[aá]ng\s+(\d{1,2})\s+n[aă]m\s+(\d{4})",
    re.I | re.U,
)
_DOC_NUMBER_PATTERN = re.compile(r"^\d+(?:/\d{4})?(?:/[A-Z0-9Đ\-]+)+$", re.U)


def _parse_issue_date(raw_value: str) -> date | None:
    raw = (raw_value or "").strip()
    if not raw:
        return None

    m_vn = _VN_DATE_PATTERN.search(raw)
    if m_vn:
        day, month, year = (int(m_vn.group(1)), int(m_vn.group(2)), int(m_vn.group(3)))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    m_dmy = _DMY_PATTERN.search(raw)
    if m_dmy:
        day, month, year = (int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3)))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def _field_value(kie_document: dict[str, Any], field_name: str) -> str | None:
    field_data = kie_document.get(field_name, {})
    if not isinstance(field_data, dict):
        return None
    value = field_data.get("value")
    if value is None:
        return None
    return str(value).strip() or None


def validate_document_logic(
    kie_document: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """
    Validate core logical constraints on merged KIE results.

    Returns:
        dict with keys:
          - valid: bool
          - issues: list[dict[field, code, message, severity]]
    """
    today = today or date.today()
    issues: list[dict[str, str]] = []

    issue_date_raw = _field_value(kie_document, "ngay_ban_hanh")
    if issue_date_raw:
        parsed = _parse_issue_date(issue_date_raw)
        if parsed is None:
            issues.append(
                {
                    "field": "ngay_ban_hanh",
                    "code": "invalid_date_format",
                    "severity": "warning",
                    "message": (
                        "Khong the phan tich ngay ban hanh theo dinh dang hop le "
                        "(dd/mm/yyyy hoac 'ngay d thang m nam y')."
                    ),
                }
            )
        elif parsed > today:
            issues.append(
                {
                    "field": "ngay_ban_hanh",
                    "code": "future_issue_date",
                    "severity": "error",
                    "message": "Ngay ban hanh khong duoc lon hon ngay hien tai.",
                }
            )

    so_van_ban = _field_value(kie_document, "so_van_ban")
    if so_van_ban and not _DOC_NUMBER_PATTERN.match(so_van_ban.upper()):
        issues.append(
            {
                "field": "so_van_ban",
                "code": "invalid_document_number_format",
                "severity": "warning",
                "message": "So/Ky hieu van ban khong dung dinh dang thuong gap.",
            }
        )

    has_error = any(issue["severity"] == "error" for issue in issues)
    return {"valid": not has_error, "issues": issues}
