from __future__ import annotations

from typing import Any

from app.services.kie_extractor import extract_kie_from_pages


def _is_document_start(page_kie: dict[str, Any]) -> bool:
    loai_conf = float(page_kie.get("loai_van_ban", {}).get("confidence", 0.0))
    so_conf = float(page_kie.get("so_van_ban", {}).get("confidence", 0.0))
    ngay_conf = float(page_kie.get("ngay_ban_hanh", {}).get("confidence", 0.0))
    score = 0
    if loai_conf >= 0.85:
        score += 2
    if so_conf >= 0.85:
        score += 1
    if ngay_conf >= 0.80:
        score += 1
    return score >= 2


def split_document_by_content(
    ocr_pages: list[dict[str, Any]],
    *,
    model: str = "qwen2.5:3b-instruct",
    ollama_url: str = "http://127.0.0.1:11434",
    use_llm: bool = True,
    template: Any | None = None,
) -> dict[str, Any]:
    """
    Split a large OCR page list into logical documents by page-level KIE signals.
    """
    total_pages = len(ocr_pages)
    if total_pages == 0:
        return {
            "total_pages": 0,
            "total_documents": 0,
            "documents": [],
            "tree": {"title": "Root", "children": []},
        }

    kie_all_pages = extract_kie_from_pages(
        ocr_pages=ocr_pages,
        model=model,
        ollama_url=ollama_url,
        use_llm=use_llm,
        template=template,
    )
    page_kie_results = [item["kie"] for item in kie_all_pages["pages"]]

    boundaries = [0]
    for idx in range(1, total_pages):
        if _is_document_start(page_kie_results[idx]):
            boundaries.append(idx)
    boundaries.append(total_pages)

    documents: list[dict[str, Any]] = []
    tree_children: list[dict[str, Any]] = []

    for doc_idx in range(len(boundaries) - 1):
        start_idx = boundaries[doc_idx]
        end_idx_exclusive = boundaries[doc_idx + 1]
        segment_pages = ocr_pages[start_idx:end_idx_exclusive]
        segment_kie = extract_kie_from_pages(
            ocr_pages=segment_pages,
            model=model,
            ollama_url=ollama_url,
            use_llm=use_llm,
            template=template,
        )["document"]

        doc_id = f"doc-{doc_idx + 1}"
        doc_type = segment_kie.get("loai_van_ban", {}).get("value")
        doc_conf = float(segment_kie.get("loai_van_ban", {}).get("confidence", 0.0))
        title = doc_type or f"Tai lieu {doc_idx + 1}"
        page_paths = [page.get("input_path", "") for page in segment_pages]

        document_item = {
            "document_id": doc_id,
            "start_page": start_idx + 1,
            "end_page": end_idx_exclusive,
            "page_paths": page_paths,
            "title": title,
            "doc_type": doc_type,
            "confidence": doc_conf,
            "classification": segment_kie,
        }
        documents.append(document_item)
        tree_children.append(
            {
                "id": doc_id,
                "title": title,
                "start_page": start_idx + 1,
                "end_page": end_idx_exclusive,
                "children": [],
            }
        )

    return {
        "total_pages": total_pages,
        "total_documents": len(documents),
        "documents": documents,
        "tree": {"title": "Root", "children": tree_children},
    }
