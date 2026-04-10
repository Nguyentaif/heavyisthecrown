# Tài Liệu Bàn Giao #2: Đặc Tả Nghiệp Vụ & Luồng Hoạt Động
**Dự án:** VN-Digitize-AI  
**Phiên bản:** 0.1.0  
**Dành cho:** Business Analyst, Product Manager, QA Engineer

---

## 1. Tổng Quan Nghiệp Vụ

VN-Digitize-AI giải quyết bài toán số hoá hàng loạt tài liệu hành chính tiếng Việt với **7 nhóm nghiệp vụ cốt lõi**:

---

## 2. Chi Tiết Các Nghiệp Vụ Cốt Lõi

### NV-01: Số Hoá Vật Lý & Chia Mẻ Tài Liệu (Digitization & Bundle Splitting)

**Mô tả:** Tiếp nhận tài liệu từ hai nguồn: upload file (ảnh/PDF) hoặc kết nối trực tiếp máy scan. Sau đó tự động phát hiện trang mã vạch (barcode separator) để phân chia một batch lớn thành các "mẻ" (bundle) logic riêng biệt.

**Quy tắc nghiệp vụ:**
- Khi scan một chồng tài liệu, người dùng đặt trang có in mã vạch vào giữa các công văn khác nhau
- Hệ thống scan xong, đọc từng trang và phát hiện barcode
- Mỗi khi gặp trang barcode, hệ thống **kết thúc bundle trước** và **bắt đầu bundle mới**
- Trang barcode không được tính là nội dung, chỉ là phân cách
- Nếu không có barcode nào trong toàn bộ batch, toàn bộ trang sẽ là 1 bundle duy nhất

**Hoạt động kỹ thuật:**
- Nguồn `upload`: Nhận multipart file upload (JPEG, PNG, PDF), lưu vào `data/raw/{uuid}/`
- Nguồn `scanner`: Gọi TWAIN/WIA drivers qua `scan_from_device()` *(hiện tại là stub, cần cấu hình theo máy scan thực tế)*
- Phát hiện barcode bằng thư viện `pyzbar` (hỗ trợ QR code, Code128, EAN, v.v.)

---

### NV-02: Tiền Xử Lý Ảnh (Image Preprocessing)

**Mô tả:** Làm sạch và chuẩn hóa ảnh trước khi đưa vào OCR để tăng độ chính xác nhận dạng chữ. Đây là bước cực kỳ quan trọng vì chất lượng ảnh quyết định 50-70% độ chính xác của cả pipeline.

**Các bước xử lý (theo thứ tự):**

| Bước | Tên | Mô tả | Mặc định |
|---|---|---|---|
| 1 | **Deskew + Auto-crop** | Phát hiện và chỉnh thẳng tài liệu bị nghiêng, cắt viền thừa | BẬT |
| 2 | **Shadow Removal** | Cân bằng sáng tối, loại bóng do ánh sáng không đều | BẬT |
| 3 | **Yellow Stain Removal** | Tẩy ố vàng theo thời gian trên giấy cũ (xử lý kênh LAB) | BẬT |
| 4 | **Denoise** | Giảm nhiễu hạt ảnh (fastNlMeansDenoisingColored) | BẬT |
| 5 | **Binarize** | Chuyển sang ảnh đen trắng (nhị phân hoá) | TẮT |
| 6 | **Preserve Red Stamp** | Giữ lại vùng màu đỏ (mộc đỏ) khi binarize | BẬT |
| 7 | **Remove Blank Pages** | Lọc bỏ trang trắng dựa trên tỉ lệ điểm ảnh có nội dung | BẬT |

**Quy tắc đặc biệt - Red Stamp Preservation:**
- Khi binarize thường, mộc đỏ bị biến thành màu đen mất tính phân biệt
- Hệ thống phát hiện vùng màu đỏ bằng HSV color range: Hue [0-12] và [160-180], Sat ≥ 60
- Vùng màu đỏ được mask riêng, giữ nguyên màu gốc, phần còn lại mới binarize

**Ngưỡng phát hiện trang trắng:**
- Tỉ lệ pixel có nội dung < 0.6% (0.006) → coi là trang trắng → bỏ qua

---

### NV-03: Nhận Dạng Ký Tự OCR (Optical Character Recognition)

**Mô tả:** Đọc và trích xuất toàn bộ văn bản từ ảnh tài liệu, trả về cả full-text lẫn thông tin vị trí từng dòng chữ để hỗ trợ UI highlight.

**Engine sử dụng:** DeepDoc VietOCR (kiến trúc `vgg_transformer`)
- Được tối ưu hóa cho chữ Việt có dấu
- Chạy hoàn toàn local, không cần internet
- Thread-safe (singleton pattern với lock để init 1 lần)

**Output cấp trang:**
```json
{
  "input_path": "/data/raw/abc123/page1.jpg",
  "full_text": "BỘ NỘI VỤ\nSố: 123/2024/QĐ-BNV\n...",
  "lines": [
    {
      "text": "BỘ NỘI VỤ",
      "bbox": [100, 50, 300, 30],
      "confidence": 98.5
    }
  ]
}
```

**Định dạng bbox:** `[x_top_left, y_top_left, width, height]`

---

### NV-04: Bóc Tách Thông Tin Chính (Key Information Extraction - KIE)

**Mô tả:** Phân tích văn bản OCR thô và tự động nhận diện, bóc tách các trường thông tin có cấu trúc của văn bản hành chính tiếng Việt.

**5 Trường thông tin chuẩn của văn bản hành chính VN:**

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| `loai_van_ban` | Loại hình tài liệu | "Quyết định", "Thông tư", "Công văn" |
| `so_van_ban` | Số/ký hiệu văn bản | "73/2024/NĐ-CP", "123/QĐ-UBND" |
| `ngay_ban_hanh` | Ngày ký ban hành | "Hà Nội, ngày 30 tháng 6 năm 2024" |
| `co_quan_ban_hanh` | Cơ quan phát hành | "BỘ Y TẾ", "UBND TỈNH HÀ NỘI" |
| `trich_yeu` | Nội dung trích yếu | "Về việc quy định quản lý ngân sách..." |

**Template KIE Động (Custom Fields):**
Ngoài 5 trường mặc định, hệ thống hỗ trợ Template để bóc tách thêm các trường nghiệp vụ đặc thù:
- Lĩnh vực Tòa án: `ten_bi_cao`, `toi_danh`, `muc_an`
- Lĩnh vực Thuế: `ma_so_thue`, `ten_to_chuc`
- Lĩnh vực BHXH: `so_so_bhxh`, `ten_nguoi_tham_gia`

**Phân biệt trường tĩnh và trường động:**
- Trường tĩnh (5 trường mặc định): Có Regex pattern cố định, cực kỳ nhanh
- Trường động (custom): Chỉ định nghĩa description cho LLM + regex tùy chọn, linh hoạt

**Cơ chế hoạt động 3 giai đoạn (xem Flow 1 bên dưới):**

---

### NV-05: Hậu Kiểm Tài Liệu (Post-processing)

**Mô tả:** Sau khi OCR xong, thực hiện thêm các kiểm tra nâng cao trên tài liệu.

**Các kiểm tra thực hiện:**
1. **Phát hiện chữ ký:** Dùng YOLOv8 (model từ HuggingFace `tech4humans/yolov8s-signature-detector`) để khoanh vùng vị trí chữ ký trên mỗi trang
2. **Phát hiện con dấu đỏ:** Dùng Stamp2Vec (`stamps-labs/yolo-stamp`) để tìm mộc đỏ
3. **Bóc tách bảng biểu:** Phân tích cấu trúc bảng từ OCR text thô
4. **Sửa lỗi chính tả:** NLP correction qua model `bmd1905/vietnamese-correction-v2`

**Xử lý lỗi chính tả (NLP Correction):**
- Model: HuggingFace `bmd1905/vietnamese-correction-v2` (Seq2Seq based)
- Bắt các lỗi OCR phổ biến như: thiếu dấu, nhầm ký tự tương tự, mất chữ đầu dòng
- Fallback passthrough: nếu model không tải được, trả nguyên văn bản gốc

---

### NV-06: Phân Loại & Cắt Tách Tài Liệu (Document Splitting)

**Mô tả:** Nhận một file/batch lớn chứa nhiều công văn/quyết định hỗn hợp, tự động chia tách thành các tài liệu con riêng biệt dựa trên phân tích ngữ nghĩa nội dung từng trang.

**Cơ chế phát hiện ranh giới tài liệu:**
Hệ thống tính điểm `_is_document_start()` cho mỗi trang:
- Phát hiện `loai_van_ban` với confidence ≥ 0.85 → +2 điểm
- Phát hiện `so_van_ban` với confidence ≥ 0.85 → +1 điểm  
- Phát hiện `ngay_ban_hanh` với confidence ≥ 0.80 → +1 điểm
- **Điểm ≥ 2 → Đây là trang đầu của tài liệu mới**

**Output:** Cây phân cấp tài liệu (tree structure) với thông tin mỗi tài liệu con

---

### NV-07: Học Liên Tục Từ Phản Hồi (Human-in-the-Loop / Feedback)

**Mô tả:** Cho phép nhân viên QA đính chính kết quả AI bóc tách sai. Dữ liệu đính chính được lưu lại tự động để phục vụ fine-tuning model trong tương lai.

**Quy trình:**
1. AI bóc tách `so_van_ban` = "12/2024/QD-BNV" (sai)
2. Nhân viên QA nhận ra sai, gửi request đính chính
3. Server lưu record: `{field_name, original_text, corrected_text, document_id, created_at}` vào `data/feedback.json`
4. Định kỳ team AI export dataset này ra, dùng để fine-tune hoặc cải thiện Regex patterns

---

## 3. Luồng Hoạt Động (Flows)

### Flow 1: Pipeline End-to-End (OCR → KIE) - Luồng chính

```
Người dùng upload file
        │
        ↓
[API /api/v1/ocr-kie hoặc /api/v1/extract-fields]
        │
        ↓
┌─────────────────────────────────────────────┐
│         GIAI ĐOẠN 1: OCR                   │
│  DeepDoc VietOCR đọc ảnh                   │
│  → Output: full_text + lines[{text, bbox}] │
└─────────────────────────────────────────────┘
        │
        ↓
┌─────────────────────────────────────────────────────┐
│              GIAI ĐOẠN 2: KIE Stage 1 (Regex)       │
│  Phân tích text thô bằng regex pattern cho VN      │
│                                                     │
│  _extract_so_van_ban()    → conf ≥ 0.93 nếu match │
│  _extract_ngay_ban_hanh() → conf ≥ 0.93 nếu match │
│  _extract_loai_van_ban()  → conf ≥ 0.93 nếu match │
│  _extract_co_quan_ban_hanh() → conf ≥ 0.93        │
│  _extract_trich_yeu()     → conf ≥ 0.80           │
└─────────────────────────────────────────────────────┘
        │
        ↓ (Nếu use_llm=True)
┌─────────────────────────────────────────────────────┐
│        GIAI ĐOẠN 3: KIE Stage 2 (Ollama LLM)       │
│  Gửi TOÀN BỘ văn bản + gợi ý từ Regex vào prompt  │
│  Model: qwen2.5:3b-instruct (local, không internet) │
│  Timeout: 90 giây                                   │
│  → LLM xử lý những phần khó, sửa lỗi trich_yeu    │
│  → confidence LLM: 0.55 - 0.72                     │
└─────────────────────────────────────────────────────┘
        │
        ↓
┌─────────────────────────────────────────────────────┐
│        GIAI ĐOẠN 4: Merge (Chọn kết quả tốt nhất)  │
│  Nguyên tắc:                                        │
│  • Stage 1 conf ≥ 0.85 → Giữ kết quả Regex        │
│  • Stage 1 không có giá trị → Lấy LLM             │
│  • Trường trich_yeu: ưu tiên LLM để sửa lỗi OCR   │
│  • Còn lại: chọn confidence cao hơn               │
└─────────────────────────────────────────────────────┘
        │
        ↓ (Chỉ với /extract-fields)
┌─────────────────────────────────────────────────────┐
│        GIAI ĐOẠN 5: Business Validation            │
│  validate_document_logic():                         │
│  • Kiểm tra ngay_ban_hanh có phải ngày trong quá  │
│    khứ hợp lệ không                               │
│  • Kiểm tra so_van_ban đúng định dạng VN không    │
│    Pattern: \d+(/\d{4})?(/[A-Z0-9Đ\-]+)+          │
└─────────────────────────────────────────────────────┘
        │
        ↓
Trả về JSON: { pages: [...], document: {...}, validation: {...} }
```

---

### Flow 2: Tiền Xử Lý Ảnh (Image Preprocessing)

```
Ảnh đầu vào (JPEG/PNG từ upload hoặc scanner)
        │
        ↓
[run_preprocess_pipeline()]
        │
        ├──→ Kiểm tra trang trắng (is_blank_page)
        │       Nếu pixel_ratio < 0.6% → SKIP, không xử lý
        │
        ↓
[preprocess_image() - nếu bật auto_crop hoặc deskew]
        │
        ├──→ run_document_scanner() 
        │       Phát hiện viền tài liệu → Perspective transform
        │       → Output: color_image (cắt gọn) + binary_image
        │
        ↓
[Xử lý màu sắc - theo thứ tự:]
        │
        ├── shadow_removal=True → remove_shadows()
        │       Dilate → Blur → AbsDiff → Invert → Normalize
        │
        ├── remove_yellow_stains=True → remove_yellow_stains()
        │       Chuyển LAB → CLAHE → Giảm A/B channel shift
        │
        └── denoise=True → denoise_image()
                fastNlMeansDenoisingColored (h=7, hColor=7)
        │
        ↓
[binarize=True?]
        │
        ├── Không → Giữ ảnh màu đã làm sạch
        │
        └── Có → adaptive_binarize()
                Gaussian Adaptive Threshold (blockSize=31, C=15)
                │
                ├── preserve_red_stamp=True?
                │       → get_red_stamp_mask() (HSV range đỏ)
                │       → Overlay vùng đỏ lên ảnh binary
                └── preserve_red_stamp=False
                        → Ảnh đen trắng thuần túy
        │
        ↓
Lưu ảnh đã xử lý vào data/preprocessed/{uuid}/{stem}_{uuid8}_clean.png
Trả về: { input_path, output_path, skipped_as_blank }
```

---

### Flow 3: Xử Lý Bất Đồng Bộ Qua Celery (Async Queue)

```
Frontend / Client
        │
        ↓ POST /api/v1/async/ocr-kie  (non-blocking)
[FastAPI Handler]
        │
        ├── Ghi task vào Redis Queue
        └── Trả về ngay: { task_id: "abc-123", status: "PENDING" }
        
[Celery Worker] (nền, song song)
        │
        ├── Lấy task từ Redis
        ├── Update state → PROGRESS "Running OCR..."
        ├── Chạy run_ocr_fulltext()
        ├── Update state → PROGRESS "Running KIE extraction..."
        ├── Chạy extract_kie_from_pages()
        └── Lưu kết quả vào Redis backend

Frontend polling (mỗi 5-10 giây):
GET /api/v1/task/{task_id}
        │
        ├── status = PENDING   → Chờ tiếp
        ├── status = PROGRESS  → Hiển thị "Đang xử lý..."
        ├── status = SUCCESS   → Lấy result, hiển thị kết quả
        └── status = FAILURE   → Hiển thị lỗi

Celery Config:
  - Serializer: JSON
  - Timezone: Asia/Ho_Chi_Minh
  - task_time_limit: 3600 giây (1 tiếng max)
  - Broker + Backend: Redis
```

---

### Flow 4: Phát Hiện Chữ Ký & Mộc Đỏ (Postprocessing)

```
Danh sách đường dẫn ảnh (đã OCR)
        │
        ↓
[run_postprocess_pipeline()]
        │
        ├──→ Tải model chữ ký từ HuggingFace:
        │       repo: tech4humans/yolov8s-signature-detector
        │       file: train/weights/best.pt
        │       (tự động download lần đầu, cache local)
        │
        ├──→ Tải pipeline mộc đỏ:
        │       repo: stamps-labs/yolo-stamp (Stamp2Vec)
        │       (tự động download lần đầu, cache local)
        │
        [Per-page xử lý:]
        ├── cv2.imread(image_path) → image_bgr
        │
        ├── Phát hiện chữ ký:
        │       signature_model.predict(image, conf=0.25)
        │       Normalize label: "signature", "sign" → "signature"
        │
        ├── Phát hiện mộc đỏ:
        │       stamp_pipeline(Image.fromarray(image_rgb))
        │       Normalize label → "stamp"
        │       Lấy bbox [x1, y1, width, height]
        │
        └── Bóc tách bảng biểu:
                extract_tables_from_ocr_page(ocr_page)
                Phân tích cấu trúc dòng/cột từ text
        │
        ↓
Trả về per-page: { has_stamp, has_signature, detections[{label, confidence, bbox}], tables }
Trả về summary: { total_pages, pages_with_stamp, pages_with_signature }
```

---

### Flow 5: Học Liên Tục Từ Feedback QA

```
[QA Nhân viên phát hiện lỗi]
        │
        ↓ POST /api/v1/feedback
{
  "corrections": [
    {
      "document_id": "doc-2024-001",
      "field_name": "so_van_ban",
      "original_text": "12/2O24/QD-BNV",   ← AI đọc sai (chữ O thay 0)
      "corrected_text": "12/2024/QĐ-BNV"    ← Người dùng sửa đúng
    }
  ]
}
        │
        ↓
[save_feedback() - TinyDB]
        │
        ├── Lưu record vào data/feedback.json:
        │   { document_id, field_name, original_text, 
        │     corrected_text, created_at: ISO timestamp }
        └── Trả về: { status: "success", saved_count: 1 }

[Định kỳ - Team AI:] 
get_all_feedback() → Export dataset → Fine-tune / Cải thiện Regex
```

---

## 4. Các Loại Văn Bản Hành Chính Được Hỗ Trợ Nhận Dạng

Hệ thống nhận diện **19 loại** văn bản hành chính phổ biến:

| Loại Văn Bản | Pattern nhận dạng |
|---|---|
| Quyết định | "Quyết định", "QUYẾT ĐỊNH" |
| Nghị quyết | "Nghị quyết", "NGHỊ QUYẾT" |
| Thông tư | "Thông tư", "THÔNG TƯ" |
| Nghị định | "Nghị định", "NGHỊ ĐỊNH" |
| Công văn | "Công văn", "CÔNG VĂN" |
| Chỉ thị | "Chỉ thị", "CHỈ THỊ" |
| Thông báo | "Thông báo", "THÔNG BÁO" |
| Báo cáo | "Báo cáo", "BÁO CÁO" |
| Tờ trình | "Tờ trình", "TỜ TRÌNH" |
| Biên bản | "Biên bản", "BIÊN BẢN" |
| Hợp đồng | "Hợp đồng", "HỢP ĐỒNG" |
| Pháp lệnh | "Pháp lệnh" |
| Luật | "Luật" |
| Kế hoạch | "Kế hoạch" |
| Giấy phép | "Giấy phép" |
| Giấy chứng nhận | "Giấy chứng nhận" |
| Hướng dẫn | "Hướng dẫn" |
| Quy chế | "Quy chế" |
| Quy định | "Quy định" |

---

## 5. Ngưỡng Độ Tin Cậy (Confidence Thresholds)

| Mức | Giá trị | Ý nghĩa |
|---|---|---|
| `_CONF_HIGH` | 0.93 | Regex khớp chắc chắn, pattern rõ ràng |
| `_CONF_MED` | 0.80 | Regex heuristic, khớp một phần |
| `_CONF_LLM` | 0.72 | LLM bóc tách thành công |
| `_CONF_LLM_LOW` | 0.55 | LLM không chắc chắn |
| `_MERGE_THRESHOLD` | 0.85 | Ngưỡng giữ kết quả Stage-1 thay vì xét Stage-2 |
| Postprocessing YOLO | 0.25 | Ngưỡng confidence tối thiểu để nhận nhận diện detection |

---

## 6. Các Hạn Chế & Điều Kiện Giới Hạn Hiện Tại

1. **Scanner vật lý:** Chức năng `source=scanner` hiện là **stub** (cần tích hợp TWAIN driver theo thiết bị thực tế)
2. **Model YOLO chữ ký:** Tự động tải từ internet lần đầu chạy, cần kết nối internet ban đầu
3. **NLP Correction:** Model `bmd1905/vietnamese-correction-v2` cần tải từ HuggingFace lần đầu
4. **Ollama LLM:** Phải chạy riêng (service Ollama), nếu Ollama không sẵn sàng, hệ thống **vẫn hoạt động** (KIE chỉ dùng Regex, bỏ Stage 2)
5. **Table Extraction:** Dựa trên phân tích OCR text, độ chính xác với bảng phức tạp còn hạn chế
6. **PDF nhập liệu:** Hiện tại pipeline xử lý ảnh (JPEG/PNG). Với PDF, cần convert sang ảnh trước bằng PyMuPDF ngoài pipeline
