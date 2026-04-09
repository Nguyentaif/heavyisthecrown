import json
import logging
import os
from pathlib import Path
import torch

# Monkey patch torch.load for PyTorch 2.6+
original_load = torch.load
def load_with_weights_only_false(*args, **kwargs):
    kwargs['weights_only'] = False
    return original_load(*args, **kwargs)
torch.load = load_with_weights_only_false

# Monkey patch VietOCR to bypass it since the vocr.vn weights URL is returning a 404 HTML
import app.services.ocr
app.services.ocr._apply_vietocr_recognition = lambda image_bgr, lines: lines

from app.services.preprocessing import run_preprocess_pipeline
from app.schemas import CustomFieldDef, KIETemplate, PreprocessOptions
from app.services.ocr import run_ocr_fulltext
from app.services.kie_extractor import extract_kie_from_pages

logging.basicConfig(level=logging.INFO)

cur_dir = Path(__file__).parent.absolute()

# Tự động trỏ TESSDATA_PREFIX về thư mục chứa model đã tải
os.environ["TESSDATA_PREFIX"] = str(cur_dir / "tessdata")

input_image = str(cur_dir / "image3.png")
output_dir = cur_dir / "data" / "test_preprocess"

options = PreprocessOptions(
    deskew=True,
    auto_crop=True,
    shadow_removal=True,
    denoise=True,
    remove_yellow_stains=True,
    binarize=False,
    preserve_red_stamp=True,
    remove_blank_pages=False,
    blank_ratio_threshold=0.006,
)

# ---------------------------------------------------------------------------
# Ví dụ Template động — có thể bật/tắt bằng cách set template=None
# ---------------------------------------------------------------------------
# Template Tòa án: bóc thêm tên bị cáo, tội danh
toa_an_template = KIETemplate(
    template_name="Tòa án — Bản án sơ thẩm",
    custom_fields=[
        CustomFieldDef(
            field_key="ten_bi_cao",
            description=(
                "Họ và tên bị cáo đứng trước tòa. "
                "Thường xuất hiện sau cụm 'Bị cáo:' hoặc 'bị cáo' ở phần xét xử."
            ),
            regex_pattern=r"[Bb]ị\s+c[áa]o[:\s]+([A-ZÀÁẠẢÃĂẮẶẲẴÂẤẦẨẪĐÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ][a-zàáạảãăắặẳẵâấầẩẫđèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ]+(?:\s+[A-ZÀÁẠẢÃĂẮẶẲẴÂẤẦẨẪĐÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ][a-zàáạảãăắặẳẵâấầẩẫđèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ]+)*)",
        ),
        CustomFieldDef(
            field_key="toi_danh",
            description=(
                "Tội danh bị kết án theo bản án. "
                "Thường sau cụm 'tội', 'về tội', hoặc trong phần Quyết định."
            ),
            # Không khai báo regex → để LLM trích xuất
        ),
    ],
)

# Để chạy KIE không có template (chế độ bình thường), đặt template=None
ACTIVE_TEMPLATE = None   # hoặc None

try:
    print("1. Running Preprocessing...")
    prep_results = run_preprocess_pipeline([input_image], output_dir, options)
    clean_image = prep_results[0]["output_path"]

    if clean_image is None:
        print("Image was skipped as blank!")
    else:
        print(f"Preprocessed image saved at: {clean_image}")
        print("2. Running OCR (using Tesseract ONLY, VietOCR bypassed)...")
        ocr_result = run_ocr_fulltext([clean_image])

        full_text = ocr_result["pages"][0]["full_text"]
        print(f"\n--- Extracted Text Preview ({len(full_text)} chars) ---")
        print(full_text[:500] + ("..." if len(full_text) > 500 else ""))

        template_label = f"'{ACTIVE_TEMPLATE.template_name}'" if ACTIVE_TEMPLATE else "không template"
        print(f"\n3. Running KIE (regex + Ollama | template: {template_label})...")
        kie_result = extract_kie_from_pages(
            ocr_result["pages"],
            use_llm=True,
            model="qwen2.5:3b-instruct",       # Đổi model ở đây nếu cần
            ollama_url="http://127.0.0.1:11434",
            template=ACTIVE_TEMPLATE,
        )

        print("\n--- DOCUMENT KIE RESULT (5 trường gốc) ---")
        doc = kie_result["document"]
        core_fields = ["loai_van_ban", "so_van_ban", "ngay_ban_hanh",
                       "co_quan_ban_hanh", "trich_yeu"]
        core_output = {f: doc[f] for f in core_fields if f in doc}
        core_output["model_used"] = doc.get("model_used")
        print(json.dumps(core_output, indent=2, ensure_ascii=False))

        if doc.get("custom_fields"):
            print("\n--- CUSTOM FIELDS (theo Template đơn vị) ---")
            print(json.dumps(doc["custom_fields"], indent=2, ensure_ascii=False))

except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

