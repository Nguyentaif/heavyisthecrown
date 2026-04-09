from __future__ import annotations

import json
import urllib.error
import urllib.request


def build_summary_prompt(text: str, max_words: int) -> str:
    return (
        "Ban la tro ly xu ly van ban hanh chinh/phap ly. "
        "Hay doc noi dung OCR va viet trich yeu ngan gon, ro y chinh, "
        "khong them thong tin khong co trong van ban. "
        f"Gioi han toi da {max_words} tu.\n\n"
        "Noi dung:\n"
        f"{text}"
    )


def summarize_with_ollama(
    text: str,
    model: str = "qwen2.5:3b-instruct",
    ollama_url: str = "http://127.0.0.1:11434",
    max_words: int = 160,
) -> dict:
    prompt = build_summary_prompt(text=text, max_words=max_words)
    base = ollama_url.rstrip("/")
    generate_url = (
        base
        if base.endswith("/api/generate")
        else f"{base}/api/generate"
    )
    chat_url = (
        base
        if base.endswith("/v1/chat/completions")
        else f"{base}/v1/chat/completions"
    )

    request_plan: list[tuple[str, dict]] = [
        (
            generate_url,
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
        ),
        (
            chat_url,
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        ),
    ]
    errors: list[str] = []

    for url, payload in request_plan:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 405}:
                errors.append(f"{url} -> HTTP {exc.code}")
                continue
            raise RuntimeError(f"Ollama request failed at {url}: HTTP {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(f"Ollama request failed at {url}: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response from Ollama at {url}.") from exc

        summary = (parsed.get("response") or "").strip()
        if not summary:
            choices = parsed.get("choices") or []
            if choices:
                summary = (
                    choices[0].get("message", {}).get("content", "") or ""
                ).strip()

        if summary:
            return {"summary": summary, "model": model}

        errors.append(f"{url} -> empty summary")

    raise RuntimeError(
        "Ollama summary failed on all endpoints. Tried: " + "; ".join(errors)
    )
