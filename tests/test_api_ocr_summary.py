from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


client = TestClient(app)


def test_ocr_fulltext_success(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        assert input_paths == ["data/preprocessed/a.png"]
        assert lang == "vie"
        assert psm == 6
        assert oem == 3
        return {
            "total_pages": 1,
            "pages": [
                {
                    "input_path": "data/preprocessed/a.png",
                    "full_text": "So 123",
                    "lines": [
                        {"text": "So 123", "bbox": [10, 10, 80, 20], "confidence": 95.0}
                    ],
                }
            ],
        }

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)

    response = client.post(
        "/api/v1/ocr-fulltext",
        json={"input_paths": ["data/preprocessed/a.png"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_pages"] == 1
    assert payload["pages"][0]["full_text"] == "So 123"


def test_auto_summary_success(monkeypatch):
    def fake_summarize_with_ollama(text, model, ollama_url, max_words):
        assert "Van ban mau" in text
        assert model == "qwen2.5:3b-instruct"
        return {"summary": "Trich yeu ngan gon.", "model": model}

    monkeypatch.setattr(main_module, "summarize_with_ollama", fake_summarize_with_ollama)

    response = client.post(
        "/api/v1/auto-summary",
        json={"text": "Van ban mau de tom tat."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "Trich yeu ngan gon."


def test_ocr_auto_summary_success(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        return {
            "total_pages": 2,
            "pages": [
                {"input_path": input_paths[0], "full_text": "Noi dung trang 1", "lines": []},
                {"input_path": input_paths[1], "full_text": "Noi dung trang 2", "lines": []},
            ],
        }

    def fake_summarize_with_ollama(text, model, ollama_url, max_words):
        assert "Noi dung trang 1" in text
        assert "Noi dung trang 2" in text
        return {"summary": "Tom tat 2 trang.", "model": model}

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)
    monkeypatch.setattr(main_module, "summarize_with_ollama", fake_summarize_with_ollama)

    response = client.post(
        "/api/v1/ocr-auto-summary",
        json={"input_paths": ["a.png", "b.png"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ocr"]["total_pages"] == 2
    assert payload["summary"] == "Tom tat 2 trang."


def test_ocr_auto_summary_returns_400_when_ocr_empty(monkeypatch):
    def fake_run_ocr_fulltext(input_paths, lang, psm, oem):
        return {
            "total_pages": 1,
            "pages": [{"input_path": input_paths[0], "full_text": "", "lines": []}],
        }

    monkeypatch.setattr(main_module, "run_ocr_fulltext", fake_run_ocr_fulltext)

    response = client.post(
        "/api/v1/ocr-auto-summary",
        json={"input_paths": ["a.png"]},
    )
    assert response.status_code == 400
