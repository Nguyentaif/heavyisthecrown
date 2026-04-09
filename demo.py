from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from app.schemas import PreprocessOptions
from app.services.document_scanner import run_document_scanner_interactive
from app.services.ocr import run_ocr_fulltext
from app.services.preprocessing import get_red_stamp_mask, run_preprocess_pipeline
from app.services.summarizer import summarize_with_ollama


def main() -> None:
    # Ensure Vietnamese text can be printed on Windows terminals.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    input_image_path = "image.png"
    output_dir = Path("data") / "manual_preprocess"
    transform_mode = "manual"  # "manual" or "auto"
    manual_use_auto_init = True
    run_ocr = True
    run_auto_summary = True
    ocr_lang = "vie"
    ocr_psm = 6
    ocr_oem = 3
    ollama_model = "qwen2.5:3b-instruct"
    ollama_url = "http://127.0.0.1:11434"
    summary_max_words = 160
    options = PreprocessOptions(
        deskew=True,
        auto_crop=True,
        shadow_removal=True,
        denoise=True,
        remove_yellow_stains=True,
        binarize=False,
        preserve_red_stamp=True,
        remove_blank_pages=True,
        blank_ratio_threshold=0.006,
    )

    if transform_mode == "manual":
        import cv2

        image = cv2.imread(input_image_path)
        if image is None:
            raise ValueError(
                f"Cannot read image: {input_image_path}. "
                "Place an input image at repo root or update input_image_path."
            )
        scanned = run_document_scanner_interactive(
            image,
            use_auto_init=manual_use_auto_init,
        )
        binary_bgr = cv2.cvtColor(scanned["binary"], cv2.COLOR_GRAY2BGR)
        if options.preserve_red_stamp:
            red_mask = get_red_stamp_mask(scanned["color"])
            red_mask = cv2.dilate(
                red_mask,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                iterations=1,
            )
            red_mask_3c = cv2.cvtColor(red_mask, cv2.COLOR_GRAY2BGR)
            output_image = np.where(red_mask_3c > 0, scanned["color"], binary_bgr).astype(
                np.uint8
            )
        else:
            output_image = binary_bgr
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{Path(input_image_path).stem}_manual_clean.png"
        cv2.imwrite(str(output_path), output_image)
        results = [
            {
                "input_path": input_image_path,
                "output_path": str(output_path),
                "skipped_as_blank": False,
                "mode": "manual_corner_adjustment",
                "manual_use_auto_init": manual_use_auto_init,
            }
        ]
    else:
        results = run_preprocess_pipeline(
            input_paths=[input_image_path],
            output_dir=output_dir,
            options=options,
        )

    output_path = results[0]["output_path"]
    if output_path is None:
        raise ValueError("Preprocess skipped the page as blank; OCR step cannot continue.")

    report: dict = {"preprocess": results}

    if run_ocr:
        ocr_result = run_ocr_fulltext(
            input_paths=[output_path],
            lang=ocr_lang,
            psm=ocr_psm,
            oem=ocr_oem,
        )
        report["ocr"] = ocr_result

        ocr_json_path = output_dir / f"{Path(output_path).stem}_ocr.json"
        ocr_text_path = output_dir / f"{Path(output_path).stem}_raw.txt"
        ocr_json_path.write_text(
            json.dumps(ocr_result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        full_text = ocr_result["pages"][0]["full_text"]
        ocr_text_path.write_text(full_text, encoding="utf-8")

        if run_auto_summary:
            if not full_text.strip():
                report["summary_error"] = "OCR produced empty text; summary is skipped."
            else:
                try:
                    summary_result = summarize_with_ollama(
                        text=full_text,
                        model=ollama_model,
                        ollama_url=ollama_url,
                        max_words=summary_max_words,
                    )
                    report["summary"] = summary_result
                    summary_path = output_dir / f"{Path(output_path).stem}_summary.txt"
                    summary_path.write_text(summary_result["summary"], encoding="utf-8")
                except RuntimeError as exc:
                    report["summary_error"] = str(exc)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
