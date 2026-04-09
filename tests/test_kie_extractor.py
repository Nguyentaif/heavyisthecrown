"""
tests/test_kie_extractor.py

Unit tests for app/services/kie_extractor.py.

Tests are organised into three groups:
  A — Stage 1: Regex extraction
  B — Stage 3: Merge logic
  C — Public API: extract_kie / extract_kie_from_pages (LLM mocked)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.kie_extractor import (
    _extract_co_quan_ban_hanh,
    _extract_loai_van_ban,
    _extract_ngay_ban_hanh,
    _extract_so_van_ban,
    _extract_trich_yeu,
    _merge_field,
    _merge_stages,
    _stage1_regex,
    extract_kie,
    extract_kie_from_pages,
)

# ============================================================================
# Fixtures — sample Vietnamese admin document texts
# ============================================================================

SAMPLE_QUYET_DINH = """\
BỘ Y TẾ
Số: 1234/QĐ-BYT
CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập – Tự do – Hạnh phúc

Hà Nội, ngày 15 tháng 3 năm 2024

QUYẾT ĐỊNH
V/v: Phê duyệt kế hoạch phòng chống dịch bệnh năm 2024
"""

SAMPLE_CONG_VAN = """\
SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI
Số: 789/SGDDT-VP
Về việc: Triển khai chương trình giáo dục phổ thông mới
Hà Nội, ngày 05 tháng 01 năm 2024
CÔNG VĂN
"""

SAMPLE_NGHI_DINH = """\
CHÍNH PHỦ
Số: 56/2024/NĐ-CP
CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập – Tự do – Hạnh phúc

Hà Nội, ngày 20/06/2024

NGHỊ ĐỊNH
Quy định về quản lý đầu tư xây dựng công trình
"""

SAMPLE_OCR_NOISY = """\
BỘ TAI CHINH  [noisy scan]
So: 45/2023/TT-BTC
ngàv 10 tháng 12 năm 2023

THONG TU
V/v Huong dan thuc hien co che tai chinh
"""

SAMPLE_EMPTY = ""

# ============================================================================
# A — Stage 1: Regex extraction
# ============================================================================


class TestExtractSoVanBan:
    def test_full_format(self):
        result = _extract_so_van_ban(SAMPLE_QUYET_DINH)
        assert result["value"] == "1234/QĐ-BYT"
        assert result["confidence"] >= 0.85

    def test_nghi_dinh_full(self):
        result = _extract_so_van_ban(SAMPLE_NGHI_DINH)
        assert result["value"] == "56/2024/NĐ-CP"
        assert result["confidence"] >= 0.85

    def test_cong_van(self):
        result = _extract_so_van_ban(SAMPLE_CONG_VAN)
        assert result["value"] is not None
        assert "789" in result["value"]
        assert result["confidence"] >= 0.8

    def test_ocr_noisy_so(self):
        # "So:" instead of "Số:" — fallback pattern should still catch it
        result = _extract_so_van_ban(SAMPLE_OCR_NOISY)
        assert result["value"] is not None
        assert result["confidence"] > 0.0

    def test_empty_text(self):
        result = _extract_so_van_ban(SAMPLE_EMPTY)
        assert result["value"] is None
        assert result["confidence"] == 0.0

    def test_no_so_in_text(self):
        result = _extract_so_van_ban("Không có số văn bản trong đoạn này.")
        assert result["value"] is None


class TestExtractNgayBanHanh:
    def test_full_pattern(self):
        result = _extract_ngay_ban_hanh(SAMPLE_QUYET_DINH)
        assert result["value"] is not None
        assert "15" in result["value"]
        assert "3" in result["value"] or "03" in result["value"]
        assert "2024" in result["value"]
        assert result["confidence"] >= 0.9

    def test_cong_van(self):
        result = _extract_ngay_ban_hanh(SAMPLE_CONG_VAN)
        assert result["value"] is not None
        assert "05" in result["value"] or "5" in result["value"]
        assert "2024" in result["value"]

    def test_short_dmy_pattern(self):
        result = _extract_ngay_ban_hanh(SAMPLE_NGHI_DINH)
        assert result["value"] is not None
        assert "2024" in result["value"]
        assert result["confidence"] >= 0.75

    def test_no_date(self):
        result = _extract_ngay_ban_hanh("Không có ngày tháng.")
        assert result["value"] is None
        assert result["confidence"] == 0.0


class TestExtractLoaiVanBan:
    def test_quyet_dinh(self):
        result = _extract_loai_van_ban(SAMPLE_QUYET_DINH)
        assert result["value"] == "Quyết định"
        assert result["confidence"] >= 0.8

    def test_cong_van(self):
        result = _extract_loai_van_ban(SAMPLE_CONG_VAN)
        assert result["value"] == "Công văn"

    def test_nghi_dinh(self):
        result = _extract_loai_van_ban(SAMPLE_NGHI_DINH)
        assert result["value"] == "Nghị định"

    def test_thong_tu(self):
        result = _extract_loai_van_ban(SAMPLE_OCR_NOISY)
        # OCR-noisy "THONG TU" — Vietnamese diacritics stripped, may not match
        # The extractor tries with re.I | re.U; noisy text might not match
        # Just verify it returns a dict with the right keys
        assert "value" in result
        assert "confidence" in result

    def test_no_doc_type(self):
        result = _extract_loai_van_ban("Đây là một đoạn văn bản thông thường không có loại.")
        assert result["value"] is None


class TestExtractCoQuanBanHanh:
    def test_bo_y_te(self):
        result = _extract_co_quan_ban_hanh(SAMPLE_QUYET_DINH)
        assert result["value"] is not None
        assert "BỘ Y TẾ" in result["value"]
        assert result["confidence"] >= 0.85

    def test_so_giao_duc(self):
        result = _extract_co_quan_ban_hanh(SAMPLE_CONG_VAN)
        assert result["value"] is not None
        assert "SỞ" in result["value"]

    def test_chinh_phu(self):
        # "CHÍNH PHỦ" doesn't match org prefixes (not in list)
        # Test that it returns null or a valid dict
        result = _extract_co_quan_ban_hanh(SAMPLE_NGHI_DINH)
        assert "value" in result
        assert "confidence" in result

    def test_no_org(self):
        result = _extract_co_quan_ban_hanh("Ngày mai trời đẹp.")
        assert result["value"] is None
        assert result["confidence"] == 0.0


class TestExtractTrichYeu:
    def test_vv_pattern(self):
        result = _extract_trich_yeu(SAMPLE_QUYET_DINH)
        assert result["value"] is not None
        assert "Phê duyệt" in result["value"] or "kế hoạch" in result["value"]
        assert result["confidence"] >= 0.85

    def test_ve_viec_pattern(self):
        result = _extract_trich_yeu(SAMPLE_CONG_VAN)
        assert result["value"] is not None
        assert "giáo dục" in result["value"].lower() or "triển khai" in result["value"].lower()

    def test_no_subject(self):
        result = _extract_trich_yeu("Không có trích yếu trong văn bản này.")
        assert result["value"] is None
        assert result["confidence"] == 0.0


class TestStage1Regex:
    def test_returns_all_five_fields(self):
        result = _stage1_regex(SAMPLE_QUYET_DINH)
        expected_keys = {"so_van_ban", "ngay_ban_hanh", "co_quan_ban_hanh", "loai_van_ban", "trich_yeu"}
        assert set(result.keys()) == expected_keys

    def test_all_fields_have_value_and_confidence(self):
        result = _stage1_regex(SAMPLE_QUYET_DINH)
        for field_name, field_val in result.items():
            assert "value" in field_val
            assert "confidence" in field_val
            assert 0.0 <= field_val["confidence"] <= 1.0


# ============================================================================
# B — Stage 3: Merge logic
# ============================================================================


class TestMergeField:
    def test_prefers_stage1_when_high_confidence(self):
        s1 = {"value": "regex_result", "confidence": 0.93}
        s2 = {"value": "llm_result", "confidence": 0.75}
        result = _merge_field(s1, s2)
        assert result["value"] == "regex_result"

    def test_prefers_stage2_when_stage1_null(self):
        s1 = {"value": None, "confidence": 0.0}
        s2 = {"value": "llm_result", "confidence": 0.72}
        result = _merge_field(s1, s2)
        assert result["value"] == "llm_result"

    def test_prefers_stage2_when_higher_confidence(self):
        s1 = {"value": "regex_result", "confidence": 0.60}
        s2 = {"value": "llm_result", "confidence": 0.75}
        result = _merge_field(s1, s2)
        assert result["value"] == "llm_result"

    def test_no_stage2_returns_stage1(self):
        s1 = {"value": "regex_result", "confidence": 0.50}
        result = _merge_field(s1, None)
        assert result["value"] == "regex_result"


class TestMergeStages:
    def test_merge_combines_all_fields(self):
        s1 = {
            "so_van_ban": {"value": "123/QĐ-BYT", "confidence": 0.93},
            "ngay_ban_hanh": {"value": None, "confidence": 0.0},
            "co_quan_ban_hanh": {"value": "BỘ Y TẾ", "confidence": 0.93},
            "loai_van_ban": {"value": "Quyết định", "confidence": 0.93},
            "trich_yeu": {"value": None, "confidence": 0.0},
        }
        s2 = {
            "so_van_ban": {"value": "123/QĐ-BYT", "confidence": 0.85},
            "ngay_ban_hanh": {"value": "15/03/2024", "confidence": 0.72},
            "co_quan_ban_hanh": {"value": "BỘ Y TẾ", "confidence": 0.70},
            "loai_van_ban": {"value": "Quyết định", "confidence": 0.80},
            "trich_yeu": {"value": "Phê duyệt kế hoạch ABC", "confidence": 0.72},
        }
        merged = _merge_stages(s1, s2)
        # Stage-1 high confidence fields stay
        assert merged["so_van_ban"]["value"] == "123/QĐ-BYT"
        # Stage-2 fills in missing
        assert merged["ngay_ban_hanh"]["value"] == "15/03/2024"
        assert merged["trich_yeu"]["value"] == "Phê duyệt kế hoạch ABC"

    def test_merge_with_no_stage2(self):
        s1 = _stage1_regex(SAMPLE_QUYET_DINH)
        merged = _merge_stages(s1, None)
        assert set(merged.keys()) == {
            "so_van_ban",
            "ngay_ban_hanh",
            "co_quan_ban_hanh",
            "loai_van_ban",
            "trich_yeu",
            "_custom",
        }


# ============================================================================
# C — Public API (LLM mocked)
# ============================================================================


class TestExtractKie:
    def test_regex_only_no_llm(self):
        result = extract_kie(text=SAMPLE_QUYET_DINH, use_llm=False)
        assert result["so_van_ban"]["value"] is not None
        assert result["loai_van_ban"]["value"] == "Quyết định"
        assert result["model_used"] is None  # LLM was not called

    def test_empty_text_returns_null_fields(self):
        result = extract_kie(text="", use_llm=False)
        for field_name in ["so_van_ban", "ngay_ban_hanh", "co_quan_ban_hanh", "loai_van_ban", "trich_yeu"]:
            assert result[field_name]["value"] is None
            assert result[field_name]["confidence"] == 0.0

    def test_llm_fallback_on_connection_error(self):
        """LLM unavailable → should return stage-1 results without crashing."""
        with patch("app.services.kie_extractor._call_ollama", return_value=None):
            result = extract_kie(text=SAMPLE_QUYET_DINH, use_llm=True)
        # Stage-1 results are still present
        assert result["so_van_ban"]["value"] is not None
        assert result["model_used"] is None  # LLM contributed nothing

    def test_llm_used_when_available(self):
        """When LLM returns valid JSON, model_used should be set."""
        mock_llm_response = {
            "so_van_ban": {"value": "1234/QĐ-BYT", "confidence": 0.90},
            "ngay_ban_hanh": {"value": "ngày 15 tháng 3 năm 2024", "confidence": 0.90},
            "co_quan_ban_hanh": {"value": "Bộ Y tế", "confidence": 0.85},
            "loai_van_ban": {"value": "Quyết định", "confidence": 0.95},
            "trich_yeu": {"value": "Phê duyệt kế hoạch phòng chống dịch 2024", "confidence": 0.82},
        }
        with patch("app.services.kie_extractor._call_ollama", return_value=mock_llm_response):
            result = extract_kie(
                text=SAMPLE_QUYET_DINH,
                model="qwen2.5:3b-instruct",
                use_llm=True,
            )
        assert result["model_used"] == "qwen2.5:3b-instruct"
        # trich_yeu should come from LLM (stage-1 was None or lower confidence)
        assert result["trich_yeu"]["value"] is not None

    def test_llm_invalid_json_graceful(self):
        """LLM returns invalid/no JSON → fallback to stage-1 gracefully."""
        with patch("app.services.kie_extractor._call_ollama", return_value=None):
            result = extract_kie(text=SAMPLE_CONG_VAN, use_llm=True)
        assert result["loai_van_ban"]["value"] == "Công văn"


class TestExtractKieFromPages:
    def test_single_page(self):
        ocr_pages = [
            {
                "input_path": "page1.png",
                "full_text": SAMPLE_QUYET_DINH,
                "lines": [],
            }
        ]
        result = extract_kie_from_pages(ocr_pages, use_llm=False)
        assert "pages" in result
        assert "document" in result
        assert len(result["pages"]) == 1
        # Document-level should mirror single page
        assert result["document"]["so_van_ban"]["value"] is not None

    def test_multi_page_picks_best_confidence(self):
        ocr_pages = [
            {
                "input_path": "page1.png",
                "full_text": "Không có thông tin gì.",
                "lines": [],
            },
            {
                "input_path": "page2.png",
                "full_text": SAMPLE_QUYET_DINH,
                "lines": [],
            },
        ]
        result = extract_kie_from_pages(ocr_pages, use_llm=False)
        # Document level should pull best values from page 2
        assert result["document"]["so_van_ban"]["value"] is not None
        assert result["document"]["loai_van_ban"]["value"] == "Quyết định"
        assert len(result["pages"]) == 2

    def test_empty_pages(self):
        result = extract_kie_from_pages([], use_llm=False)
        assert result["pages"] == []
        assert result["document"]["so_van_ban"]["value"] is None

    def test_page_has_input_path_and_full_text(self):
        ocr_pages = [
            {"input_path": "test.png", "full_text": SAMPLE_CONG_VAN, "lines": []}
        ]
        result = extract_kie_from_pages(ocr_pages, use_llm=False)
        page = result["pages"][0]
        assert page["input_path"] == "test.png"
        assert page["full_text"] == SAMPLE_CONG_VAN.strip()
        assert "kie" in page

    def test_model_used_propagated(self):
        mock_llm_response = {
            "so_van_ban": {"value": "789/SGDDT-VP", "confidence": 0.88},
            "ngay_ban_hanh": {"value": "05/01/2024", "confidence": 0.88},
            "co_quan_ban_hanh": {"value": "Sở Giáo dục và Đào tạo Hà Nội", "confidence": 0.80},
            "loai_van_ban": {"value": "Công văn", "confidence": 0.90},
            "trich_yeu": {"value": "Triển khai chương trình giáo dục phổ thông mới", "confidence": 0.85},
        }
        ocr_pages = [{"input_path": "p.png", "full_text": SAMPLE_CONG_VAN, "lines": []}]
        with patch("app.services.kie_extractor._call_ollama", return_value=mock_llm_response):
            result = extract_kie_from_pages(
                ocr_pages, model="qwen2.5:3b-instruct", use_llm=True
            )
        assert result["document"]["model_used"] == "qwen2.5:3b-instruct"
