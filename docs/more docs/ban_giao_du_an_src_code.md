# Tài liệu bàn giao dự án (Source code) - VN-Digitize-AI

## 1) Mục tiêu tài liệu bàn giao

Tài liệu này phục vụ bàn giao cho team phát triển/vận hành tiếp theo, bao gồm:
- Tài liệu nghiệp vụ theo từng nhóm chức năng.
- Tài liệu API chi tiết cho từng endpoint đang có trong source code.
- Tài liệu flow xử lý end-to-end (kèm các điểm rollback/QA).
- Tài liệu công nghệ sử dụng và tài khoản liên quan (nếu có).


## 2) Nghiệp vụ

### Capture & Ingestion (Scan/Upload)

**Phạm vi nghiệp vụ**
- Thu nhận tài liệu từ máy scan vật lý hoặc upload file.
- Tách bộ tài liệu tự động bằng Barcode.
- Chuẩn hóa dữ liệu đầu vào để đưa vào pipeline xử lý ảnh/OCR.

**Màn hình/API chính**
- `POST /api/v1/scan-upload`
- `POST /api/v1/upload-preprocess`

**Đầu ra bàn giao**
- Danh sách trang đã lưu (`saved_pages`).
- Danh sách bundle theo barcode (`bundles`).
- Metadata phiên xử lý đầu vào (source, số trang, cấu hình scan).


### Image Processing & OCR

**Phạm vi nghiệp vụ**
- Tiền xử lý ảnh: deskew, crop, denoise, shadow removal, stain removal, xóa trang trắng.
- OCR tiếng Việt, giữ `full_text` + `lines` (bbox/confidence).
- Hỗ trợ nhận diện chữ viết tay (tùy chọn `handwriting_support`).

**Màn hình/API chính**
- `POST /api/v1/preprocess`
- `POST /api/v1/ocr-fulltext`
- `POST /api/v1/ocr-auto-summary`

**Đầu ra bàn giao**
- Bộ ảnh sau tiền xử lý.
- Raw OCR theo trang.
- Trạng thái các trang bị bỏ qua do blank page.


### KIE/AI Understanding

**Phạm vi nghiệp vụ**
- Bóc tách trường thông tin chuẩn (5 field hành chính).
- Hỗ trợ template custom field theo đơn vị.
- Tóm tắt văn bản tự động bằng AI local (Ollama).

**Màn hình/API chính**
- `POST /api/v1/kie`
- `POST /api/v1/ocr-kie`
- `POST /api/v1/extract-fields`
- `POST /api/v1/auto-summary`
- `POST /api/v1/nlp-correct`

**Đầu ra bàn giao**
- JSON KIE theo trang + mức document.
- Validation issues cho nghiệp vụ.
- Summary phục vụ tra cứu nhanh.


### QA, Archive, Feedback, Incremental Learning

**Phạm vi nghiệp vụ**
- QA1/QA2 duyệt dữ liệu trích xuất.
- Xuất PDF searchable/PDF-A.
- Lưu archive hồ sơ.
- Nhận feedback người dùng để học gia tăng.

**Màn hình/API chính**
- `POST /api/v1/qa1/review-create`
- `GET /api/v1/qa1/review/{session_id}`
- `POST /api/v1/qa2/decision`
- `POST /api/v1/export-pdf-searchable`
- `GET /api/v1/downloads/{filename}`
- `POST /api/v1/archive/store`
- `POST /api/v1/feedback`
- `POST /api/v1/incremental-learning/retrain`
- `GET /api/v1/incremental-learning/status`

**Đầu ra bàn giao**
- QA session records.
- File PDF export.
- Dữ liệu feedback và trạng thái lexicon học gia tăng.


## 3) Flow nghiệp vụ chi tiết (ưu tiên bàn giao)

### Flow lõi 3 bước

**Bước 1 - Scan & Tải lên:**
Kết nối máy scan vật lý (chỉnh DPI, màu,..) hoặc upload file. Tự động tách bộ theo Barcode.

**Mục tiêu**
- Đảm bảo ảnh đầu vào đủ chất lượng để OCR.
- Tách đúng hồ sơ theo barcode để không trộn chứng từ.

**Input**
- `source=scanner|upload`
- Cấu hình scan: `dpi`, `color_mode`
- File upload: ảnh/PDF theo lô

**Output**
- `saved_pages`: đường dẫn các trang đã lưu
- `bundles`: nhóm trang theo barcode

---

**Bước 2 - Tiền xử lý ảnh:**
Tự động chỉnh thẳng, cắt viền, tẩy ố vàng, xóa trang trắng.

**Mục tiêu**
- Tăng độ chính xác OCR.
- Loại bỏ trang rỗng, giảm chi phí xử lý.

**Tác vụ chính**
- `deskew`, `auto_crop`, `shadow_removal`, `denoise`
- `remove_yellow_stains`, `remove_blank_pages`
- Có thể bật `preserve_red_stamp` để giữ dấu đỏ rõ hơn cho bước hậu xử lý

**Output**
- Danh sách trang đã xử lý + trạng thái `skipped_as_blank`.

---

**Bước 3 - OCR & AI (Nhận dạng):**
Chuyển đổi toàn bộ hình ảnh thành văn bản thô (Raw OCR). Tích hợp Trợ lý AI tự động đọc hiểu và sinh trích yếu nội dung văn bản (Auto-summary).

**Mục tiêu**
- Trích xuất toàn văn bản và thông tin có cấu trúc.
- Tạo trích yếu để người dùng nắm nội dung nhanh.

**Tác vụ chính**
- OCR toàn trang (`full_text`) + từng dòng (`lines` có bbox/confidence).
- KIE 5 trường chuẩn + custom fields (nếu có template).
- AI summary qua mô hình local.

**Output**
- Raw OCR + KIE + summary.
- Cờ lỗi nếu văn bản trống/không OCR được.


### Flow end-to-end đề xuất vận hành

1. `scan-upload` -> nhận/tách bộ.
2. `preprocess` hoặc `upload-preprocess`.
3. `ocr-kie` hoặc `extract-fields`.
4. `postprocess-check` (dấu/chữ ký/bảng) khi cần compliance.
5. `qa1/review-create` -> thao tác QA.
6. `qa2/decision` duyệt hoặc rollback.
7. `export-pdf-searchable` -> `archive/store`.
8. `feedback` + `incremental-learning/retrain` theo chu kỳ.


## 4) Tài liệu API chi tiết

## 4.1 Capture & Preprocess

### `POST /api/v1/scan-upload`
- **Nghiệp vụ:** Nhận scan/upload và split bundle theo barcode.
- **Request:** multipart form (`source`, `dpi`, `color_mode`, `files[]`).
- **Response:** `ScanUploadResponse` (`source`, `total_pages`, `bundles`, `saved_pages`).
- **Lỗi thường gặp:** `400` source sai/thiếu file, `501` scanner chưa hỗ trợ, `503` barcode service lỗi.

### `POST /api/v1/preprocess`
- **Nghiệp vụ:** Tiền xử lý ảnh từ danh sách path có sẵn.
- **Request:** `PreprocessRequest` (`input_paths`, `options`).
- **Response:** `PreprocessResponse`.
- **Lỗi thường gặp:** `400` input path/options không hợp lệ.

### `POST /api/v1/upload-preprocess`
- **Nghiệp vụ:** Upload và preprocess trong một lần gọi.
- **Request:** multipart `files[]` + các cờ preprocess.
- **Response:** `UploadPreprocessResponse`.


## 4.2 OCR & AI

### `POST /api/v1/ocr-fulltext`
- **Nghiệp vụ:** OCR toàn văn từ ảnh.
- **Request:** `OCRRequest`.
- **Response:** `OCRResponse` (gồm `pages[].full_text`, `pages[].lines[].bbox/confidence`).
- **Lỗi:** `400` input lỗi, `503` OCR engine unavailable.

### `POST /api/v1/auto-summary`
- **Nghiệp vụ:** Tóm tắt từ text đầu vào.
- **Request:** `AutoSummaryRequest` (`text`, `model`, `ollama_url`, `max_words`).
- **Response:** `AutoSummaryResponse`.
- **Lỗi:** `503` khi LLM local không sẵn sàng.

### `POST /api/v1/ocr-auto-summary`
- **Nghiệp vụ:** OCR + summary trong một request.
- **Request:** `OCRAutoSummaryRequest`.
- **Response:** `OCRAutoSummaryResponse` (`ocr`, `summary`, `model`).
- **Lỗi:** `400` OCR rỗng text, `503` OCR/LLM lỗi.

### `POST /api/v1/nlp-correct`
- **Nghiệp vụ:** Sửa lỗi chính tả OCR text.
- **Request:** `{ "text": "..." }`
- **Response:** `{ "original": "...", "corrected": "..." }`


## 4.3 KIE & Business Extraction

### `POST /api/v1/kie`
- **Nghiệp vụ:** Bóc field từ raw text (regex + LLM tùy chọn).
- **Request:** `KIERequest`.
- **Response:** `KIEResponse` (5 trường chuẩn + `custom_fields`).

### `POST /api/v1/ocr-kie`
- **Nghiệp vụ:** Pipeline ảnh -> OCR -> KIE.
- **Request:** `OCRKIERequest`.
- **Response:** `OCRKIEResponse` (`pages` + `document`).

### `POST /api/v1/extract-fields`
- **Nghiệp vụ:** OCR -> KIE -> validate logic nghiệp vụ.
- **Request:** `ExtractFieldsRequest`.
- **Response:** `ExtractFieldsResponse` có thêm `validation`.

### `POST /api/v1/split-document`
- **Nghiệp vụ:** Tách 1 bộ lớn thành nhiều document logic.
- **Request:** `SplitDocumentRequest`.
- **Response:** `SplitDocumentResponse` (`documents`, `tree`).

### `POST /api/v1/postprocess-check`
- **Nghiệp vụ:** Kiểm tra hậu xử lý (stamp/signature/table).
- **Request:** `PostprocessRequest`.
- **Response:** `PostprocessResponse`.


## 4.4 Async Processing

### `POST /api/v1/async/ocr-kie`
- Trả về `task_id` để xử lý OCR-KIE nền.

### `POST /api/v1/async/split-document`
- Trả về `task_id` để xử lý split nền.

### `GET /api/v1/task/{task_id}`
- Polling trạng thái task (`PENDING/PROGRESS/SUCCESS/FAILURE`).


## 4.5 QA, Export, Archive, Learning

### `POST /api/v1/qa1/review-create`
- Tạo phiên QA1 từ input ảnh.

### `GET /api/v1/qa1/review/{session_id}`
- Lấy lại trạng thái chi tiết phiên QA.

### `POST /api/v1/qa2/decision`
- Duyệt QA2 (`approve`) hoặc từ chối (`reject`) và rollback.

### `POST /api/v1/export-pdf-searchable`
- Xuất PDF có layer text tra cứu.

### `GET /api/v1/downloads/{filename}`
- Tải file PDF đã export.

### `POST /api/v1/archive/store`
- Lưu hồ sơ vào kho archive nội bộ.

### `POST /api/v1/feedback`
- Nhận corrections từ người dùng để cải thiện mô hình.

### `POST /api/v1/incremental-learning/retrain`
- Chạy học gia tăng từ feedback records.

### `GET /api/v1/incremental-learning/status`
- Kiểm tra trạng thái lexicon và số bản ghi feedback.


## 5) Công nghệ trong project và tài khoản (nếu có)

## 5.1 Stack chính

- **Backend API:** FastAPI, Uvicorn
- **Validation/Schema:** Pydantic
- **Image processing:** OpenCV, Pillow, NumPy
- **OCR:** deepdoc_vietocr, VietOCR
- **NLP/LLM:** Transformers, Ollama local (`qwen2.5:3b-instruct` mặc định)
- **Detection:** Ultralytics YOLO (stamp/signature)
- **Async queue:** Celery + Redis
- **PDF:** PyMuPDF, pdfplumber
- **Testing:** Pytest, HTTPX


## 5.2 Tài khoản / quyền truy cập

### Bắt buộc để chạy local
- **Không yêu cầu tài khoản cloud bắt buộc** cho luồng core nếu chạy local đầy đủ.
- Cần cài service nội bộ: Redis, Ollama, Python environment.

### Tài khoản có thể phát sinh theo môi trường
- **Hugging Face (tùy chọn):** dùng khi tải model private hoặc vượt giới hạn anonymous.
- **Máy chủ scan nội bộ (tùy tổ chức):** user/pass thiết bị scan hoặc quyền chia sẻ thư mục scan.
- **Kho lưu trữ doanh nghiệp (nếu tích hợp):** S3/MinIO/NAS account theo hạ tầng.

### Bảng bàn giao tài khoản (template)

| Hạng mục | Môi trường | Username/Service Account | Chủ sở hữu | Nơi lưu secret | Ghi chú |
|---|---|---|---|---|---|
| Redis | Dev/UAT/Prod | TBD | TBD | Vault/Secret Manager | Nếu bật auth |
| Ollama host | Dev/UAT/Prod | N/A (local service) | TBD | N/A | Kiểm tra port/network |
| Hugging Face Token | Dev/UAT/Prod | TBD | TBD | Vault/Secret Manager | Chỉ khi dùng model private |
| Scanner gateway | On-prem | TBD | TBD | Vault/Password manager | Nếu scan qua thiết bị mạng |
| Archive storage | UAT/Prod | TBD | TBD | Vault/Secret Manager | Nếu archive ra kho ngoài |


## 6) Quy ước vận hành khi bàn giao

- Luôn test lại các endpoint chính sau khi cập nhật model/preprocessing.
- Tách cấu hình Dev/UAT/Prod bằng biến môi trường.
- Không lưu key/token/private key trực tiếp trong repo.
- Với tiến trình async, bắt buộc có dashboard hoặc log theo `task_id`.
- Với QA2 reject, phải ghi lý do và rollback stage để audit.


## 7) Checklist hoàn tất bàn giao

- [ ] Đã bàn giao source code + dependency lock.
- [ ] Đã bàn giao tài liệu API + flow theo phiên bản hiện tại.
- [ ] Đã bàn giao danh sách service nền cần chạy (Redis/Ollama/worker).
- [ ] Đã bàn giao tài khoản, owner, nơi lưu secret.
- [ ] Đã chạy smoke test các API trọng yếu sau bàn giao.

