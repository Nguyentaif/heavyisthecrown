import sys
from pathlib import Path

from app.services.ocr import _normalize_deepdoc_result

_DEEPOCR_SRC = Path(__file__).resolve().parents[1] / "deepdoc_vietocr"
if str(_DEEPOCR_SRC) not in sys.path:
    sys.path.insert(0, str(_DEEPOCR_SRC))

from deepdoc_vietocr.module.ocr import (
    _probability_to_score,
    _resolve_vietocr_weight_path,
)


def test_normalize_deepdoc_result_scales_probability_to_percent():
    raw_items = [
        (
            [[10.0, 20.0], [30.0, 20.0], [30.0, 35.0], [10.0, 35.0]],
            ("Xin chao", 0.73),
        )
    ]

    lines = _normalize_deepdoc_result(raw_items)

    assert len(lines) == 1
    assert lines[0]["text"] == "Xin chao"
    assert lines[0]["bbox"] == [10, 20, 20, 15]
    assert lines[0]["confidence"] == 73.0


def test_normalize_deepdoc_result_keeps_percent_score():
    raw_items = [
        (
            [[1.0, 1.0], [11.0, 1.0], [11.0, 9.0], [1.0, 9.0]],
            ("abc", 82.5),
        )
    ]

    lines = _normalize_deepdoc_result(raw_items)

    assert len(lines) == 1
    assert lines[0]["confidence"] == 82.5


def test_resolve_vietocr_weight_path_uses_project_location():
    weight_path = _resolve_vietocr_weight_path("vgg_seq2seq.pth")
    normalized = weight_path.replace("\\", "/")

    assert normalized.endswith("/deepdoc_vietocr/vietocr/weight/vgg_seq2seq.pth")


def test_probability_to_score_converts_prob_tensor_like_value():
    class FakeProb:
        def item(self):
            return 0.42

    score = _probability_to_score(FakeProb())

    assert score == 0.42
