from pathlib import Path

import cv2
import numpy as np

from app.schemas import PreprocessOptions
from app.services.preprocessing import (
    deskew_image,
    estimate_skew_angle,
    is_blank_page,
    preprocess_image,
    run_preprocess_pipeline,
)


def test_is_blank_page_detects_white_page():
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    assert is_blank_page(image, threshold=0.01)


def test_preprocess_pipeline_skips_blank_page(tmp_path: Path):
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    input_path = tmp_path / "blank.png"
    cv2.imwrite(str(input_path), image)

    options = PreprocessOptions(remove_blank_pages=True)
    results = run_preprocess_pipeline([str(input_path)], tmp_path / "out", options)

    assert len(results) == 1
    assert results[0]["skipped_as_blank"] is True
    assert results[0]["output_path"] is None


def test_preprocess_pipeline_outputs_clean_file(tmp_path: Path):
    image = np.full((300, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (50, 100), (250, 150), (0, 0, 0), thickness=-1)
    input_path = tmp_path / "content.png"
    cv2.imwrite(str(input_path), image)

    options = PreprocessOptions(remove_blank_pages=True)
    results = run_preprocess_pipeline([str(input_path)], tmp_path / "out", options)

    assert len(results) == 1
    assert results[0]["skipped_as_blank"] is False
    assert results[0]["output_path"] is not None
    assert Path(results[0]["output_path"]).exists()


def _create_synthetic_text_image() -> np.ndarray:
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    for y in [90, 150, 210, 270, 330]:
        cv2.line(image, (70, y), (530, y), (0, 0, 0), 3)
    return image


def _rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def test_estimate_skew_angle_detects_rotated_text():
    base = _create_synthetic_text_image()
    rotated = _rotate_image(base, 12.0)
    estimated = estimate_skew_angle(rotated)
    assert abs(abs(estimated) - 12.0) < 2.0


def test_deskew_image_reduces_skew():
    base = _create_synthetic_text_image()
    rotated = _rotate_image(base, 12.0)
    corrected = deskew_image(rotated)

    before = abs(estimate_skew_angle(rotated))
    after = abs(estimate_skew_angle(corrected))

    assert before > 5.0
    assert after < 1.5


def test_binarize_preserves_red_stamp_pixels():
    image = np.full((220, 220, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (30, 30), (110, 110), (0, 0, 255), thickness=-1)
    cv2.putText(image, "A1", (130, 130), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    options = PreprocessOptions(
        deskew=False,
        auto_crop=False,
        shadow_removal=False,
        denoise=False,
        remove_yellow_stains=False,
        binarize=True,
        preserve_red_stamp=True,
        remove_blank_pages=False,
    )
    processed = preprocess_image(image, options)
    red_mask = (processed[:, :, 2] > 180) & (processed[:, :, 1] < 120)
    assert int(np.count_nonzero(red_mask)) > 300


def test_shadow_removal_flattens_background():
    h, w = 260, 260
    x = np.linspace(40, 210, w, dtype=np.float32)
    gradient = np.tile(x, (h, 1))
    image = np.stack([gradient, gradient, gradient], axis=2).astype(np.uint8)
    cv2.putText(image, "TXT", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    options = PreprocessOptions(
        deskew=False,
        auto_crop=False,
        shadow_removal=True,
        denoise=False,
        remove_yellow_stains=False,
        binarize=False,
        remove_blank_pages=False,
    )
    processed = preprocess_image(image, options)

    original_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
    assert float(np.std(processed_gray)) < float(np.std(original_gray))
