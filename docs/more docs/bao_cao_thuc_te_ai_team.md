# Báo cáo thực tế AI Team (đã làm / chưa làm)

## 1) Phạm vi và cách đánh giá

- **Nguồn đối chiếu yêu cầu:** REQUIREMENTS AI TEAM
- **Nguồn đối chiếu triển khai:** source code hiện tại trong `app/` + test suite trong `tests/`


## 2) Kết luận nhanh

- Hệ thống đã có **pipeline AI tương đối đầy đủ**: preprocess, OCR, KIE, split document, postprocess, QA, export PDF, feedback loop, incremental learning, async Celery.
- Có một số hạng mục **chưa đạt hoặc chưa đủ bằng chứng theo yêu cầu gốc**:
  - Chưa có adapter scan vật lý thật (đang `NotImplementedError`).
  - OCR engine hiện dùng `deepdoc_vietocr`, **không phải** PaddleOCR/TrOCR/Donut theo ưu tiên tài liệu yêu cầu.
  - Chưa có bằng chứng benchmark để khẳng định CER > 97%.
  - Test suite chưa chạy qua hoàn toàn do thiếu dependency runtime (`pdfplumber`) trong môi trường hiện tại.


## 3) Đối chiếu chi tiết theo REQUIREMENTS

## I. Core Engines

### 1. Engine Tiền xử lý ảnh

- **Deskewing** -> **ĐÃ LÀM**
  - Có `estimate_skew_angle()` + `deskew_image()` trong `app/services/preprocessing.py`.
  - Có clamp góc về khoảng `[-45, 45]`.
- **Denoising** -> **ĐÃ LÀM**
  - Có `denoise_image()` dùng `cv2.fastNlMeansDenoisingColored`.
- **Auto-cropping** -> **ĐÃ LÀM**
  - Có `auto_crop_document()` + tích hợp `run_document_scanner(...)`.
- **Binarization (Adaptive Threshold)** -> **ĐÃ LÀM**
  - Có `adaptiveThreshold` và cờ `binarize`.
- **Stamp Preservation** -> **ĐÃ LÀM**
  - Có `get_red_stamp_mask()` + logic preserve dấu đỏ khi nhị phân hóa.

**Nhận xét thực tế:** Hạng mục preprocess đáp ứng tốt yêu cầu chức năng, có cả remove blank page.


### 2. Engine OCR & KIE

- **OCR công nghệ ưu tiên PaddleOCR/TrOCR/Donut** -> **CHƯA ĐÚNG THEO YÊU CẦU GỐC**
  - Hiện tại dùng `deepdoc_vietocr` (`app/services/ocr.py`), không thấy triển khai PaddleOCR/TrOCR/Donut.
- **Độ chính xác CER > 97%** -> **CHƯA CÓ BẰNG CHỨNG**
  - Chưa thấy module benchmark CER/WER hoặc báo cáo số liệu đánh giá chính thức.
- **Dynamic KIE (5 trường chuẩn)** -> **ĐÃ LÀM**
  - Có regex + LLM merge cho `so_van_ban`, `ngay_ban_hanh`, `co_quan_ban_hanh`, `loai_van_ban`, `trich_yeu`.
- **Template động thêm trường theo đơn vị** -> **ĐÃ LÀM**
  - Có `KIETemplate`, `CustomFieldDef`, custom regex + custom LLM field extraction.
- **Table Extraction** -> **ĐÃ LÀM (MỨC HEURISTIC)**
  - Có `extract_tables_from_ocr_page(...)`; đang heuristic theo clustering bbox.
- **Hỗ trợ chữ viết tay** -> **ĐÃ LÀM (MỨC CƠ BẢN)**
  - Có cờ `handwriting_support` và bước refine `refine_ocr_for_handwriting`.

**Nhận xét thực tế:** KIE làm khá đầy đủ, nhưng OCR tech stack và KPI CER chưa bám đúng.


### 3. Engine Classification & Splitting

- **Classification theo tiêu đề/layout** -> **ĐÃ LÀM (MỨC KIE-SIGNAL)**
  - `split_document_by_content()` phân định ranh giới bằng confidence các field KIE.
- **Auto-splitting PDF lớn** -> **ĐÃ LÀM**
  - Có endpoint và service split theo trang bắt đầu/kết thúc.
- **Mục lục thông minh dạng tree JSON** -> **ĐÃ LÀM**
  - Trả về `tree` với `children` trong `SplitDocumentResponse`.

**Nhận xét thực tế:** Đã có khả năng chẻ tài liệu; classification hiện thiên về tín hiệu text/KIE, chưa thấy model layout classifier chuyên biệt.


### 4. Engine Post-processing

- **Stamp/Signature Detection (YOLO)** -> **ĐÃ LÀM**
  - Có pipeline detect stamp/signature trong `app/services/postprocessing.py`.
- **NLP Correction (PhoBERT hoặc tương đương)** -> **ĐÃ LÀM**
  - Có endpoint `/api/v1/nlp-correct`, logic correction trong service NLP.
- **Logic Validation** -> **ĐÃ LÀM**
  - Có check ngày ban hành tương lai, định dạng số văn bản (`app/services/validation.py`).


## II. Kiến trúc hệ thống & API

- **Python + FastAPI** -> **ĐÃ LÀM**
- **Celery + Redis async** -> **ĐÃ LÀM**
  - Có `/api/v1/async/ocr-kie`, `/api/v1/async/split-document`, `/api/v1/task/{task_id}`.
- **Nhóm endpoint quan trọng theo yêu cầu** -> **ĐÃ CÓ**
  - `preprocess`, `ocr-fulltext`, `extract-fields`, `split-document`, `export-pdf-searchable`.

**Lưu ý kỹ thuật:** `celery_app.py` có fallback dummy khi thiếu Celery, thuận tiện dev nhưng cần đảm bảo môi trường production bật worker thật.


## III. Output standards

- **JSON kèm tọa độ bbox** -> **ĐÃ LÀM**
  - OCR lines có `bbox`; KIE có `field_bbox` mapping cho highlight UI.
- **PDF/A-1b hoặc PDF/A-2b + searchable layer + nén** -> **ĐÃ LÀM (THEO API/THAM SỐ)**
  - Có `pdfa_level`, `strict_pdfa`, `mrc_compression` trong `ExportPDFRequest`.
  - Cần test tích hợp thực tế để xác nhận chất lượng PDF/A với bộ hồ sơ thật.


## IV. Human-in-the-loop

- **Feedback API** -> **ĐÃ LÀM**
  - `/api/v1/feedback` lưu correction.
- **Incremental Learning định kỳ** -> **ĐÃ LÀM (MỨC LEXICON-BASED)**
  - Có `retrain_incremental_from_feedback()` sinh `incremental_lexicon.json`.

**Nhận xét thực tế:** Đã có vòng học gia tăng, nhưng hiện là cơ chế từ điển/lexicon, chưa phải huấn luyện lại mô hình OCR/KIE đầy đủ.


## 4) Các việc chưa làm hoặc còn thiếu bằng chứng

1. **Scan vật lý chưa tích hợp backend thật**
- `scan_from_device(...)` hiện ném `NotImplementedError`.
- Cần tích hợp WIA/TWAIN/SANE theo môi trường triển khai.

2. **Chưa bám OCR stack ưu tiên trong yêu cầu**
- Yêu cầu ưu tiên PaddleOCR/TrOCR/Donut, nhưng code đang dùng DeepDoc VietOCR.
- Cần thống nhất lại tài liệu yêu cầu hoặc roadmap migration.

3. **Chưa có benchmark định lượng CER > 97%**
- Thiếu script/report benchmark chuẩn (CER/WER theo bộ dữ liệu kiểm định).

4. **Table extraction còn heuristic**
- Chưa thấy mô hình table structure chuyên sâu; có rủi ro với layout phức tạp.

5. **Chưa xác nhận e2e bằng full test trong môi trường hiện tại**
- Chạy `pytest -q` bị dừng ở bước collect do thiếu `pdfplumber`.
- Đây là vấn đề môi trường, không kết luận trực tiếp lỗi business logic.


## 5) Bằng chứng kiểm thử hiện tại

- Lệnh đã chạy: `pytest -q`
- Kết quả: **FAILED (collection error)** vì thiếu dependency:
  - `ModuleNotFoundError: No module named 'pdfplumber'`
- Ý nghĩa:
  - Chưa thể xác nhận trạng thái pass/fail toàn bộ test suite tại máy hiện tại.
  - Cần cài đủ dependency theo `requirements.txt` rồi chạy lại để chốt chất lượng.


## 6) Đề xuất hành động tiếp theo (ưu tiên)

1. Hoàn thiện adapter scan vật lý (WIA/TWAIN/SANE) và test thực tế thiết bị.
2. Chốt chiến lược OCR: giữ DeepDoc hay chuyển sang PaddleOCR/TrOCR/Donut theo yêu cầu chuẩn.
3. Bổ sung benchmark CER/WER chính thức và ngưỡng pass/fail.
4. Cài đầy đủ dependency, chạy lại toàn bộ `pytest` và lưu report CI.
5. Nếu dùng production compliance cao: nâng cấp table extraction từ heuristic sang model chuyên biệt.

