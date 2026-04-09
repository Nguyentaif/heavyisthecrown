from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode
except Exception:  # pragma: no cover - optional runtime dependency
    decode = None


DetectorFn = Callable[[np.ndarray], str | None]


def detect_barcode_value(image_bgr: np.ndarray) -> str | None:
    if decode is None:
        raise RuntimeError(
            "pyzbar is unavailable. Install pyzbar and zbar runtime to enable barcode split."
        )
    decoded = decode(image_bgr)
    if not decoded:
        return None
    value = decoded[0].data.decode("utf-8", errors="ignore").strip()
    return value or None


def split_pages_by_barcode(
    page_paths: list[Path],
    detector: DetectorFn = detect_barcode_value,
) -> list[dict]:
    bundles: list[dict] = []
    current_pages: list[str] = []
    current_marker: str | None = None

    for page_path in page_paths:
        image = cv2.imread(str(page_path))
        if image is None:
            raise ValueError(f"Cannot read page image for barcode split: {page_path}")
        marker = detector(image)
        if marker is not None:
            if current_pages:
                bundles.append(
                    {
                        "bundle_id": f"bundle-{len(bundles) + 1}",
                        "barcode": current_marker,
                        "pages": current_pages,
                    }
                )
            current_pages = [str(page_path)]
            current_marker = marker
        else:
            current_pages.append(str(page_path))

    if current_pages:
        bundles.append(
            {
                "bundle_id": f"bundle-{len(bundles) + 1}",
                "barcode": current_marker,
                "pages": current_pages,
            }
        )

    return bundles
