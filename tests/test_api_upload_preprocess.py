import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _png_bytes_with_text() -> bytes:
    image = np.full((300, 300, 3), 255, dtype=np.uint8)
    cv2.putText(image, "TEST", (60, 160), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_upload_preprocess_returns_output_path():
    response = client.post(
        "/api/v1/upload-preprocess",
        files={"files": ("sample.png", _png_bytes_with_text(), "image/png")},
        data={
            "remove_blank_pages": "true",
            "deskew": "true",
            "auto_crop": "true",
            "denoise": "true",
            "remove_yellow_stains": "true",
            "blank_ratio_threshold": "0.006",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_uploaded"] == 1
    assert payload["total_outputs"] == 1
    assert len(payload["results"]) == 1
    assert payload["results"][0]["output_path"] is not None
    assert payload["results"][0]["skipped_as_blank"] is False


def test_upload_preprocess_requires_files():
    response = client.post(
        "/api/v1/upload-preprocess",
        data={"remove_blank_pages": "true"},
    )
    assert response.status_code == 400
