# Tài Liệu Bàn Giao #3: Tài Liệu API Chi Tiết (API Reference)
**Dự án:** VN-Digitize-AI  
**Phiên bản:** 0.1.0  
**Base URL:** `http://localhost:8000`  
**Swagger UI:** `http://localhost:8000/docs`  
**Dành cho:** Frontend Developer, Integration Engineer

---

## 1. Thông Tin Chung

### Cấu trúc Response chuẩn
Tất cả API trả về JSON. Lỗi trả về theo chuẩn FastAPI:
```json
{
  "detail": "Mô tả lỗi chi tiết"
}
```

### HTTP Status Codes phổ biến
| Code | Ý nghĩa |
|---|---|
| `200 OK` | Thành công |
| `400 Bad Request` | Input không hợp lệ (file không đọc được, thiếu field) |
| `501 Not Implemented` | Tính năng chưa implement (ví dụ: scanner vật lý) |
| `503 Service Unavailable` | Service ngoài không phản hồi (Ollama down, OCR engine lỗi) |

### Authentication
Hiện tại: **Không có authentication**. Cần bổ sung Bearer Token hoặc API Key trước khi deploy production.

---

## 2. Nhóm API Ingestion (Thu Thập & Làm Sạch)

---

### API 01: `POST /api/v1/scan-upload`
**Mục đích:** Upload tài liệu hoặc trigger máy scan vật lý. Tự động chia mẻ (bundle splitting) theo mã vạch.

**Content-Type:** `multipart/form-data`

**Request Parameters (Form fields):**

| Tên | Kiểu | Bắt buộc | Mặc định | Mô tả |
|---|---|---|---|---|
| `source` | string | ✅ | - | `"scanner"` hoặc `"upload"` |
| `dpi` | integer | ❌ | `300` | DPI khi scan (chỉ dùng với `source=scanner`) |
| `color_mode` | string | ❌ | `"color"` | `"color"`, `"grayscale"`, `"bw"` |
| `files` | file[] | ✅ (upload) | - | Các file ảnh/PDF cần upload |

**Response Body (`ScanUploadResponse`):**
```json
{
  "source": "upload",
  "total_pages": 5,
  "bundles": [
    {
      "bundle_id": "bundle-1",
      "barcode": null,
      "pages": ["/data/raw/abc123/page1.jpg", "/data/raw/abc123/page2.jpg"]
    },
    {
      "bundle_id": "bundle-2",
      "barcode": "CV-2024-001",
      "pages": ["/data/raw/abc123/page3.jpg"]
    }
  ],
  "saved_pages": ["/data/raw/abc123/page1.jpg", "..."]
}
```

**Ví dụ curl:**
```bash
curl -X POST http://localhost:8000/api/v1/scan-upload \
  -F "source=upload" \
  -F "files=@document_page1.jpg" \
  -F "files=@barcode_separator.jpg" \
  -F "files=@document_page2.jpg"
```

**Lỗi thường gặp:**
- `400: source must be scanner or upload` — Giá trị source không hợp lệ
- `400: files are required for upload` — Không kèm file khi source=upload
- `501: scanner not configured` — Máy scan chưa được cấu hình

---

### API 02: `POST /api/v1/preprocess`
**Mục đích:** Làm sạch ảnh từ list đường dẫn local đã có sẵn.

**Content-Type:** `application/json`

**Request Body (`PreprocessRequest`):**
```json
{
  "input_paths": ["/data/raw/abc123/page1.jpg", "/data/raw/abc123/page2.jpg"],
  "options": {
    "deskew": true,
    "auto_crop": true,
    "shadow_removal": true,
    "denoise": true,
    "remove_yellow_stains": true,
    "binarize": false,
    "preserve_red_stamp": true,
    "remove_blank_pages": true,
    "blank_ratio_threshold": 0.006
  }
}
```

> Tất cả `options` đều có giá trị mặc định. Có thể chỉ gửi `input_paths` là đủ.

**Response Body (`PreprocessResponse`):**
```json
{
  "total_inputs": 2,
  "total_outputs": 2,
  "results": [
    {
      "input_path": "/data/raw/abc123/page1.jpg",
      "output_path": "/data/preprocessed/xyz/page1_a1b2c3d4_clean.png",
      "skipped_as_blank": false
    },
    {
      "input_path": "/data/raw/abc123/page2.jpg",
      "output_path": null,
      "skipped_as_blank": true
    }
  ]
}
```

---

### API 03: `POST /api/v1/upload-preprocess`
**Mục đích:** Kết hợp upload + preprocess trong 1 request (tiện lợi hơn cho frontend).

**Content-Type:** `multipart/form-data`

**Request Parameters:**

| Tên | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `files` | file[] | - | Danh sách ảnh cần xử lý |
| `deskew` | bool | `true` | Chỉnh thẳng văn bản nghiêng |
| `auto_crop` | bool | `true` | Tự động cắt viền |
| `shadow_removal` | bool | `true` | Loại bóng |
| `denoise` | bool | `true` | Giảm nhiễu |
| `remove_yellow_stains` | bool | `true` | Tẩy ố vàng |
| `binarize` | bool | `false` | Nhị phân hoá (đen trắng) |
| `preserve_red_stamp` | bool | `true` | Giữ mộc đỏ khi binarize |
| `remove_blank_pages` | bool | `true` | Lọc trang trắng |
| `blank_ratio_threshold` | float | `0.006` | Ngưỡng xác định trang trắng |

**Response Body (`UploadPreprocessResponse`):** Tương tự PreprocessResponse + thêm `total_uploaded`, `saved_pages`.

---

## 3. Nhóm API OCR & KIE (Xử Lý Văn Bản Cốt Lõi)

---

### API 04: `POST /api/v1/ocr-fulltext`
**Mục đích:** Trích xuất toàn bộ văn bản từ ảnh (chỉ OCR, không KIE).

**Content-Type:** `application/json`

**Request Body (`OCRRequest`):**
```json
{
  "input_paths": ["/data/preprocessed/abc/page1_clean.png"],
  "lang": "vie",
  "psm": 6,
  "oem": 3
}
```

> **Lưu ý:** Các trường `lang`, `psm`, `oem` được giữ để tương tích API cũ nhưng DeepDoc VietOCR không sử dụng chúng. Engine tự xử lý nội bộ.

**Response Body (`OCRResponse`):**
```json
{
  "total_pages": 1,
  "pages": [
    {
      "input_path": "/data/preprocessed/abc/page1_clean.png",
      "full_text": "BỘ NỘI VỤ\nSố: 123/2024/QĐ-BNV\nNgày: 15/03/2024\n...",
      "lines": [
        {
          "text": "BỘ NỘI VỤ",
          "bbox": [100, 50, 200, 30],
          "confidence": 98.5
        },
        {
          "text": "Số: 123/2024/QĐ-BNV",
          "bbox": [100, 90, 350, 28],
          "confidence": 95.2
        }
      ]
    }
  ]
}
```

> `bbox` format: `[x_top_left, y_top_left, width, height]` (đơn vị: pixel)

---

### API 05: `POST /api/v1/kie`
**Mục đích:** Bóc tách KIE từ **văn bản thô** (text đã có sẵn, không cần ảnh). Hữu ích khi đã có text từ nguồn khác.

**Content-Type:** `application/json`

**Request Body (`KIERequest`):**
```json
{
  "text": "BỘ NỘI VỤ\nSố: 73/2024/QĐ-BNV\nHà Nội, ngày 15 tháng 3 năm 2024\nQUYẾT ĐỊNH\nV/v phê duyệt kế hoạch năm 2024...",
  "model": "qwen2.5:3b-instruct",
  "ollama_url": "http://127.0.0.1:11434",
  "use_llm": true,
  "template": null
}
```

**Với template động (custom fields):**
```json
{
  "text": "...",
  "use_llm": true,
  "template": {
    "template_name": "Tòa án - Bản án hình sự",
    "custom_fields": [
      {
        "field_key": "ten_bi_cao",
        "description": "Họ tên đầy đủ của bị cáo trong bản án",
        "regex_pattern": "bị cáo[:\\s]+([^,\\n]+)"
      },
      {
        "field_key": "toi_danh",
        "description": "Tội danh mà bị cáo bị kết án theo bản án",
        "regex_pattern": null
      }
    ]
  }
}
```

**Response Body (`KIEResponse`):**
```json
{
  "result": {
    "loai_van_ban": {
      "value": "Quyết định",
      "confidence": 0.93
    },
    "so_van_ban": {
      "value": "73/2024/QĐ-BNV",
      "confidence": 0.93
    },
    "ngay_ban_hanh": {
      "value": "Hà Nội, ngày 15 tháng 3 năm 2024",
      "confidence": 0.93
    },
    "co_quan_ban_hanh": {
      "value": "BỘ NỘI VỤ",
      "confidence": 0.93
    },
    "trich_yeu": {
      "value": "phê duyệt kế hoạch năm 2024",
      "confidence": 0.72
    },
    "custom_fields": {},
    "model_used": "qwen2.5:3b-instruct"
  }
}
```

> Khi `use_llm=false`, `model_used` sẽ là `null`.  
> Khi OCR không tìm thấy trường nào, `value` là `null`, `confidence` là `0.0`.

---

### API 06: `POST /api/v1/ocr-kie`
**Mục đích:** Pipeline tích hợp: nhận ảnh → chạy OCR → chạy KIE → trả kết quả cả hai theo từng trang. Đây là API **được dùng nhiều nhất**.

**Content-Type:** `application/json`

**Request Body (`OCRKIERequest`):**
```json
{
  "input_paths": [
    "/data/preprocessed/abc/page1_clean.png",
    "/data/preprocessed/abc/page2_clean.png"
  ],
  "lang": "vie",
  "psm": 6,
  "oem": 3,
  "model": "qwen2.5:3b-instruct",
  "ollama_url": "http://127.0.0.1:11434",
  "use_llm": true,
  "template": null
}
```

**Response Body (`OCRKIEResponse`):**
```json
{
  "pages": [
    {
      "input_path": "/data/preprocessed/abc/page1_clean.png",
      "full_text": "BỘ NỘI VỤ\nSố: 73/2024/QĐ-BNV...",
      "lines": [
        {"text": "BỘ NỘI VỤ", "bbox": [100, 50, 200, 30], "confidence": 98.5}
      ],
      "kie": {
        "loai_van_ban": {"value": "Quyết định", "confidence": 0.93},
        "so_van_ban": {"value": "73/2024/QĐ-BNV", "confidence": 0.93},
        "ngay_ban_hanh": {"value": "Hà Nội, ngày 15 tháng 3 năm 2024", "confidence": 0.93},
        "co_quan_ban_hanh": {"value": "BỘ NỘI VỤ", "confidence": 0.93},
        "trich_yeu": {"value": "phê duyệt kế hoạch", "confidence": 0.72},
        "custom_fields": {},
        "model_used": "qwen2.5:3b-instruct"
      }
    }
  ],
  "document": {
    "loai_van_ban": {"value": "Quyết định", "confidence": 0.93},
    "so_van_ban": {"value": "73/2024/QĐ-BNV", "confidence": 0.93},
    "ngay_ban_hanh": {"value": "Hà Nội, ngày 15 tháng 3 năm 2024", "confidence": 0.93},
    "co_quan_ban_hanh": {"value": "BỘ NỘI VỤ", "confidence": 0.93},
    "trich_yeu": {"value": "phê duyệt kế hoạch", "confidence": 0.72},
    "custom_fields": {},
    "model_used": "qwen2.5:3b-instruct"
  }
}
```

> `document` là kết quả tổng hợp sau khi merge từ TẤT CẢ các trang (chọn field có confidence cao nhất ở mỗi trang).  
> `pages` giữ kết quả riêng từng trang, hữu ích cho debug và UI highlighting.

---

### API 07: `POST /api/v1/extract-fields`
**Mục đích:** Giống `/ocr-kie` nhưng CÓ THÊM bước **Business Logic Validation**. Là API cấp nghiệp vụ cao nhất.

**Request Body:** Giống hệt `OCRKIERequest`.

**Response Body (`ExtractFieldsResponse`):**
```json
{
  "pages": [ ... ],
  "document": { ... },
  "validation": {
    "valid": true,
    "issues": [
      {
        "field": "ngay_ban_hanh",
        "code": "future_issue_date",
        "severity": "error",
        "message": "Ngay ban hanh khong duoc lon hon ngay hien tai."
      },
      {
        "field": "so_van_ban",
        "code": "invalid_document_number_format",
        "severity": "warning",
        "message": "So/Ky hieu van ban khong dung dinh dang thuong gap."
      }
    ]
  }
}
```

**Bảng Validation Codes:**

| Code | Tên trường | Severity | Điều kiện trigger |
|---|---|---|---|
| `invalid_date_format` | `ngay_ban_hanh` | `warning` | Không parse được ngày theo format hợp lệ |
| `future_issue_date` | `ngay_ban_hanh` | `error` | Ngày ban hành sau ngày hôm nay |
| `invalid_document_number_format` | `so_van_ban` | `warning` | Không match pattern `\d+(/\d{4})?(/[A-Z0-9Đ\-]+)+` |

> `valid: false` chỉ khi có ít nhất 1 issue có `severity: "error"`.

---

## 4. Nhóm API Tóm Tắt & Phân Loại

---

### API 08: `POST /api/v1/auto-summary`
**Mục đích:** Tóm tắt tự động nội dung văn bản bằng Ollama LLM. Nhận TEXT thô.

**Request Body (`AutoSummaryRequest`):**
```json
{
  "text": "Toàn bộ nội dung văn bản cần tóm tắt...",
  "model": "qwen2.5:3b-instruct",
  "ollama_url": "http://127.0.0.1:11434",
  "max_words": 160
}
```

> `max_words`: Giới hạn 40-500 từ.

**Response Body (`AutoSummaryResponse`):**
```json
{
  "summary": "Quyết định số 73/2024/QĐ-BNV phê duyệt kế hoạch...",
  "model": "qwen2.5:3b-instruct"
}
```

---

### API 09: `POST /api/v1/ocr-auto-summary`
**Mục đích:** Pipeline tích hợp: nhận ảnh → OCR → tóm tắt tự động.

**Request Body (`OCRAutoSummaryRequest`):**
```json
{
  "input_paths": ["/data/preprocessed/abc/page1.png"],
  "lang": "vie",
  "model": "qwen2.5:3b-instruct",
  "ollama_url": "http://127.0.0.1:11434",
  "max_words": 160
}
```

**Response Body (`OCRAutoSummaryResponse`):**
```json
{
  "ocr": { ... },
  "summary": "Tóm tắt ngắn gọn...",
  "model": "qwen2.5:3b-instruct"
}
```

---

### API 10: `POST /api/v1/split-document`
**Mục đích:** Phân tách file PDF lớn hỗn hợp thành nhiều tài liệu con theo nội dung.

**Request Body:** Giống `OCRKIERequest`.

**Response Body (`SplitDocumentResponse`):**
```json
{
  "total_pages": 10,
  "total_documents": 3,
  "documents": [
    {
      "document_id": "doc-1",
      "start_page": 1,
      "end_page": 4,
      "page_paths": ["/data/raw/.../page1.jpg", "..."],
      "title": "Quyết định",
      "doc_type": "Quyết định",
      "confidence": 0.93,
      "classification": { ... KIEResult ... }
    }
  ],
  "tree": {
    "title": "Root",
    "children": [
      {
        "id": "doc-1",
        "title": "Quyết định",
        "start_page": 1,
        "end_page": 4,
        "children": []
      }
    ]
  }
}
```

---

### API 11: `POST /api/v1/postprocess-check`
**Mục đích:** Kiểm tra tài liệu sau OCR: có chữ ký không? có mộc đỏ không? có bảng không?

**Request Body (`PostprocessRequest`):**
```json
{
  "input_paths": ["/data/preprocessed/abc/page1.png"],
  "lang": "vie",
  "psm": 6,
  "oem": 3,
  "yolo_model_path": null,
  "conf_threshold": 0.25
}
```

> `yolo_model_path`: Đường dẫn tới model YOLO `.pt` nếu muốn dùng model local. Để `null` để tự download từ HuggingFace.

**Response Body (`PostprocessResponse`):**
```json
{
  "available": true,
  "pages": [
    {
      "input_path": "/data/preprocessed/abc/page1.png",
      "has_stamp": true,
      "has_signature": true,
      "detections": [
        {
          "label": "stamp",
          "confidence": 0.87,
          "bbox": [250, 400, 120, 80]
        },
        {
          "label": "signature",
          "confidence": 0.79,
          "bbox": [300, 500, 150, 60]
        }
      ],
      "tables": [
        {
          "table_id": "table-1",
          "row_count": 5,
          "column_count": 3,
          "rows": [
            {"row_index": 0, "cells": ["STT", "Tên", "Số lượng"]}
          ]
        }
      ]
    }
  ],
  "summary": {
    "total_pages": 1,
    "pages_with_stamp": 1,
    "pages_with_signature": 1
  }
}
```

> `bbox` format: `[x_top_left, y_top_left, width, height]`.  
> `available: false` khi không tải được model YOLO/Stamp2Vec.

---

### API 12: `POST /api/v1/nlp-correct`
**Mục đích:** Sửa lỗi chính tả OCR bằng AI language model (tiếng Việt).

**Request Body:**
```json
{
  "text": "Uy định về quản lý tài chin nhà nươc"
}
```

**Response Body:**
```json
{
  "original": "Uy định về quản lý tài chin nhà nươc",
  "corrected": "Quy định về quản lý tài chính nhà nước"
}
```

---

## 5. Nhóm API Async (Bất Đồng Bộ)

Dành cho tác vụ nặng (nhiều trang, cần xử lý lâu). Frontend không cần chờ, nhận task_id và polling.

---

### API 13: `POST /api/v1/async/ocr-kie`
**Mục đích:** Submit task OCR-KIE bất đồng bộ qua Celery.

**Request Body:** Giống hệt `OCRKIERequest`.

**Response Body (`AsyncTaskResponse`):**
```json
{
  "task_id": "d3f4e5a6-b7c8-...",
  "status": "PENDING",
  "message": "Task submitted successfully."
}
```

---

### API 14: `POST /api/v1/async/split-document`
**Mục đích:** Submit task Split Document bất đồng bộ.

**Request Body:** Giống hệt `SplitDocumentRequest`.

**Response Body:** Giống `AsyncTaskResponse`.

---

### API 15: `GET /api/v1/task/{task_id}`
**Mục đích:** Polling để lấy trạng thái và kết quả của async task.

**Path Parameter:** `task_id` — UUID nhận từ API 13 hoặc 14.

**Response Body (`TaskStatusResponse`):**

**Khi đang xử lý:**
```json
{
  "task_id": "d3f4e5a6-b7c8-...",
  "status": "PROGRESS",
  "result": null,
  "meta": {"message": "Running KIE extraction..."}
}
```

**Khi thành công:**
```json
{
  "task_id": "d3f4e5a6-b7c8-...",
  "status": "SUCCESS",
  "result": {
    "status": "success",
    "pages": [ ... ],
    "document": { ... }
  },
  "meta": null
}
```

**Khi lỗi:**
```json
{
  "task_id": "d3f4e5a6-b7c8-...",
  "status": "FAILURE",
  "result": null,
  "meta": {"error": "Cannot read image for OCR: /path/not/found.jpg"}
}
```

**Bảng Status Values:**
| Status | Ý nghĩa |
|---|---|
| `PENDING` | Task đang trong hàng chờ |
| `STARTED` | Celery worker đã nhận task |
| `PROGRESS` | Đang xử lý (có `meta.message`) |
| `SUCCESS` | Hoàn thành, xem `result` |
| `FAILURE` | Thất bại, xem `meta.error` |
| `RETRY` | Đang thử lại |
| `REVOKED` | Đã bị hủy |

---

## 6. Nhóm API Output & Feedback

---

### API 16: `POST /api/v1/export-pdf-searchable`
**Mục đích:** Xuất file PDF 2 lớp: lớp hình ảnh làm sạch + lớp text ẩn có thể tìm kiếm / copy-paste.

**Request Body (`ExportPDFRequest`):**
```json
{
  "pages": [
    {
      "input_path": "/data/preprocessed/abc/page1_clean.png",
      "full_text": "...",
      "lines": [
        {"text": "BỘ NỘI VỤ", "bbox": [100, 50, 200, 30], "confidence": 98.5}
      ],
      "kie": { ... }
    }
  ],
  "output_filename": "quyet-dinh-73-2024.pdf"
}
```

**Response Body (`ExportPDFResponse`):**
```json
{
  "output_path": "/data/exported/quyet-dinh-73-2024.pdf",
  "download_url": "/api/v1/downloads/quyet-dinh-73-2024.pdf"
}
```

> File PDF xuất ra tương thích Adobe Acrobat và mọi PDF viewer. Lớp text sẽ được nhúng ẩn ở đúng vị trí tương ứng để khi dùng Ctrl+F hoặc copy sẽ chọn được text.

---

### API 17: `POST /api/v1/feedback`
**Mục đích:** Nhân viên QA gửi đính chính khi AI bóc tách sai để phục vụ incremental learning.

**Request Body (`FeedbackRequest`):**
```json
{
  "corrections": [
    {
      "document_id": "doc-2024-073",
      "field_name": "so_van_ban",
      "original_text": "12/2O24/QD-BNV",
      "corrected_text": "12/2024/QĐ-BNV"
    },
    {
      "document_id": "doc-2024-073",
      "field_name": "ngay_ban_hanh",
      "original_text": "ngay 15 thang 3 nam 2024",
      "corrected_text": "ngày 15 tháng 3 năm 2024"
    }
  ]
}
```

**Response Body (`FeedbackResponse`):**
```json
{
  "status": "success",
  "saved_count": 2
}
```

> Dữ liệu này được lưu vào `data/feedback.json` (TinyDB). Team AI định kỳ export để train model.

---

## 7. Bảng Tóm Tắt Toàn Bộ API

| # | Method | Endpoint | Mô tả ngắn |
|---|---|---|---|
| 1 | POST | `/api/v1/scan-upload` | Upload / scan + chia mẻ barcode |
| 2 | POST | `/api/v1/preprocess` | Làm sạch ảnh từ đường dẫn local |
| 3 | POST | `/api/v1/upload-preprocess` | Upload + làm sạch ảnh |
| 4 | POST | `/api/v1/ocr-fulltext` | OCR trích xuất full-text |
| 5 | POST | `/api/v1/kie` | KIE từ text thô |
| 6 | POST | `/api/v1/ocr-kie` | OCR + KIE pipeline (chính) |
| 7 | POST | `/api/v1/extract-fields` | OCR + KIE + Business Validation |
| 8 | POST | `/api/v1/auto-summary` | Tóm tắt văn bản bằng LLM |
| 9 | POST | `/api/v1/ocr-auto-summary` | OCR + tóm tắt tự động |
| 10 | POST | `/api/v1/split-document` | Phân tách tài liệu hỗn hợp |
| 11 | POST | `/api/v1/postprocess-check` | Kiểm tra chữ ký / mộc / bảng |
| 12 | POST | `/api/v1/nlp-correct` | Sửa lỗi chính tả OCR |
| 13 | POST | `/api/v1/async/ocr-kie` | Submit async OCR-KIE |
| 14 | POST | `/api/v1/async/split-document` | Submit async Split Document |
| 15 | GET | `/api/v1/task/{task_id}` | Polling trạng thái async task |
| 16 | POST | `/api/v1/export-pdf-searchable` | Xuất PDF 2 lớp tìm kiếm được |
| 17 | POST | `/api/v1/feedback` | Gửi phản hồi đính chính QA |
