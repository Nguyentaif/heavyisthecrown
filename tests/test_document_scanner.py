import cv2
import numpy as np

from app.services.document_scanner import run_document_scanner_interactive


def test_run_document_scanner_interactive_fallback_when_highgui_unavailable(monkeypatch):
    image = np.full((80, 120, 3), 255, dtype=np.uint8)

    def raise_gui_error(*_args, **_kwargs):
        raise cv2.error("highgui unavailable")

    monkeypatch.setattr(cv2, "namedWindow", raise_gui_error)

    result = run_document_scanner_interactive(image, use_auto_init=False)

    assert set(result.keys()) == {"color", "binary"}
    assert result["color"].ndim == 3
    assert result["binary"].ndim == 2
