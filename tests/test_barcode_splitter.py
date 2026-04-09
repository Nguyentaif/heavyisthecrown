from pathlib import Path

import cv2
import numpy as np

from app.services.barcode_splitter import split_pages_by_barcode


def _fake_detector_factory(marked_indices: set[int]):
    state = {"idx": -1}

    def detector(_image):
        state["idx"] += 1
        idx = state["idx"]
        return f"BC-{idx}" if idx in marked_indices else None

    return detector


def test_split_pages_by_barcode_starts_new_bundle_on_barcode(tmp_path: Path):
    paths = []
    for idx in range(5):
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        path = tmp_path / f"page-{idx}.png"
        cv2.imwrite(str(path), image)
        paths.append(path)

    detector = _fake_detector_factory(marked_indices={0, 3})
    bundles = split_pages_by_barcode(paths, detector=detector)

    assert len(bundles) == 2
    assert bundles[0]["barcode"] == "BC-0"
    assert len(bundles[0]["pages"]) == 3
    assert bundles[1]["barcode"] == "BC-3"
    assert len(bundles[1]["pages"]) == 2


def test_split_pages_by_barcode_raises_on_unreadable_image(tmp_path: Path):
    missing_path = tmp_path / "missing.png"
    detector = _fake_detector_factory(marked_indices=set())
    try:
        split_pages_by_barcode([missing_path], detector=detector)
        assert False, "Expected ValueError for unreadable input image"
    except ValueError as exc:
        assert "Cannot read page image for barcode split" in str(exc)
