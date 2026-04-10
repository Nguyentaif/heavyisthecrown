# Tài Liệu Bàn Giao #4: Kiến Trúc AI & Công Nghệ Lõi
**Dự án:** VN-Digitize-AI  
**Phiên bản:** 0.1.0  
**Dành cho:** AI Engineer, Data Scientist, Tech Lead

---

## 1. Tổng Quan Kiến Trúc Hệ Thống

### Mô hình kiến trúc: Modular Monolith + Async Queue

VN-Digitize-AI được thiết kế theo kiểu **Modular Monolith** — một codebase duy nhất nhưng tách biệt rõ ràng các tầng (layer):

```
┌──────────────────────────────────────────────────────────────┐
│                    CLIENT / FRONTEND                        │
└───────────────────────┬──────────────────────────────────────┘
                        │ HTTP/REST
┌───────────────────────▼──────────────────────────────────────┐
│                    FastAPI Layer                             │
│         app/main.py — 17 endpoints                          │
│         app/schemas.py — Pydantic validation                │
└───────────┬────────────────────────────────┬─────────────────┘
            │ Direct call                    │ Serialize to Redis
            ▼                               ▼
┌───────────────────────┐    ┌──────────────────────────────┐
│   Services Layer      │    │        Celery Workers        │
│   app/services/       │    │   app/tasks.py               │
│   (15 modules)        │    │   (process_ocr_kie           │
│                       │    │    process_split_document)   │
└───────────┬───────────┘    └──────────────────────────────┘
            │
    ┌───────┼───────────────────────────────────┐
    ▼       ▼           ▼              ▼         ▼
┌───────┐ ┌──────┐ ┌────────┐ ┌──────────┐ ┌────────┐
│OpenCV │ │Deep  │ │Ollama  │ │Ultralytics│ │HuggFace│
│NumPy  │ │Doc   │ │Local   │ │YOLO v8   │ │Models  │
│(image)│ │VietOCR│ │LLM    │ │(signatures│ │(NLP)   │
└───────┘ └──────┘ └────────┘ └──────────┘ └────────┘
```

### Redis giữ vai trò gì?
Redis được dùng làm **broker** (hàng chờ task) và **backend** (lưu kết quả task) cho Celery. Không dùng làm cache hay primary database.

---

## 2. Engine OCR: DeepDoc VietOCR

### Kiến trúc
**DeepDoc VietOCR** là module OCR tích hợp nội bộ, kết hợp hai thành phần:
- **DeepDoc:** Framework phân tích layout tài liệu (nhận diện vùng văn bản, bảng, hình ảnh)
- **VietOCR:** Đọc và nhận dạng chữ Việt có dấu

**Mô hình backbone:** `vgg_transformer`
- VGG backbone cho feature extraction từ ảnh chữ
- Transformer cho sequence modeling (đọc chuỗi ký tự)
- Được train trên dataset tiếng Việt đặc thù

### Cách khởi tạo trong code
```python
# app/services/ocr.py
# Thread-safe singleton pattern
_DEEPOCR_ENGINE = None
_DEEPOCR_LOCK = threading.Lock()

def _get_deepdoc_engine():
    # Double-checked locking để đảm bảo chỉ init 1 lần
    with _DEEPOCR_LOCK:
        if _DEEPOCR_ENGINE is None:
            from deepdoc_vietocr.module.ocr import OCR as DeepDocOCR
            _DEEPOCR_ENGINE = DeepDocOCR()
    return _DEEPOCR_ENGINE
```

### Output format của DeepDoc
```python
# Raw DeepDoc output: list of [(points, (text, score))]
# points: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]] — tứ giác
# text: chuỗi ký tự nhận dạng được
# score: 0.0 - 1.0 (hay 0-100%)

# Sau khi normalize:
{
    "text": "BỘ NỘI VỤ",
    "bbox": [x_left, y_top, width, height],  # chuyển từ quadrilateral sang AABB
    "confidence": 98.5  # normalized về 0-100
}
```

### Đường dẫn module
```
deepdoc_vietocr/
├── module/
│   └── ocr.py         ← Class OCR chính
├── utils/             ← Utility functions
└── ...
```
> Nếu thiếu `deepdoc_vietocr/`, OCR engine sẽ raise RuntimeError. Cần đảm bảo thư mục này tồn tại.

---

## 3. Engine KIE: Hybrid 3-Stage Pipeline

Đây là module phức tạp nhất (`kie_extractor.py` - 837 dòng code). Hoạt động theo 3 giai đoạn tuần tự.

### Stage 1: Regex Pattern Matching

**Triết lý:** Regex cho văn bản hành chính VN có tính **xác định cao** (deterministic). Khi pattern khớp, độ tin cậy rất cao (≥0.93). Nhanh, không cần GPU, không cần internet.

#### Trích xuất Số Văn Bản (`so_van_ban`):
```python
# 4 tầng pattern, độ ưu tiên giảm dần:
_SO_PATTERNS = [
    # Tốt nhất: 123/2024/QĐ-BYT  
    r'[Ss][oố][:\.\s]+(\d+/\d{4}/[\w][\w\-]*/[\w][\w\-]*)',
    # Phổ biến: 123/QĐ-UBND
    r'[Ss][oố][:\.\s]+(\d+/[\w][\w\-]*/[\w][\w\-]*)',
    # Đơn giản: 45/UBND-VP
    r'[Ss][oố][:\.\s]+(\d+/[\w][\w/\-]+)',
    # Dự phòng: Số 1234
    r'[Ss][oố][:\.\s]+(\d[\d\-/\w]+)',
]
```

**Quan trọng:** Chỉ tìm trong 25 dòng đầu và bỏ qua các dòng "Căn cứ..." / "Theo..." để không nhầm số văn bản viện dẫn với số văn bản chính.

#### Trích xuất Ngày Ban Hành (`ngay_ban_hanh`):
```python
# Tốt nhất: "Hà Nội, ngày 30 tháng 6 năm 2024"
_DATE_FULL_LINE = r'([^\n,]+,\s*ng[àa]y\s+\d{1,2}\s+th[aá]ng\s+\d{1,2}\s+n[aă]m\s+\d{4})'

# Thứ 2: "ngày 30 tháng 6 năm 2024"
_DATE_FULL = r'ng[àa]y\s+(\d{1,2})\s+th[aá]ng\s+(\d{1,2})\s+n[aă]m\s+(\d{4})'

# Dự phòng: DD/MM/YYYY (confidence thấp vì có thể là ngày bất kỳ)
_DATE_DMY = r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b'
```

#### Trích xuất Cơ Quan Ban Hành (`co_quan_ban_hanh`):
```python
# Pattern nhận dạng 30+ prefix tổ chức nhà nước VN:
_ORG_LINE = r'^(CHÍNH\s+PHỦ|QUỐC\s+HỘI|BỘ|UỶ\s+BAN|UBND|SỞ|
               CỤC|BAN|HỘI\s+ĐỒNG|TRƯỜNG|VIỆN|TRUNG\s+TÂM|
               CÔNG\s+TY|...)\b'
# Chỉ match với text ALL-CAPS (chuẩn văn bản hành chính VN)
# Tìm trong 20 dòng đầu
```

#### Trích xuất Loại Văn Bản (`loai_van_ban`):
```python
# 19 loại văn bản với pattern tiếng Việt đầy đủ dấu:
_DOC_TYPES = [
    ("Quyết định", r'\bquy[eế]t\s+[dđ][iị]nh\b'),
    ("Thông tư",   r'\bth[oô]ng\s+t[uư]\b'),
    ...
]
# Chỉ tìm trong 15 dòng đầu, bỏ qua dòng "Căn cứ..."
```

#### Trích xuất Trích Yếu (`trich_yeu`):
Hai chiến lược:
1. **Strategy 1 (ưu tiên):** Tìm pattern `V/v ...` hoặc `Về việc ...`
2. **Strategy 2 (fallback):** Tìm dòng nằm ngay dưới tên loại văn bản ALL-CAPS

### Stage 2: LLM Context Extraction (Ollama)

**Khi nào dùng:** Khi `use_llm=True` (mặc định). Nếu Ollama không khởi động, bỏ qua nhẹ nhàng.

**Prompt engineering:**
```
Bạn là chuyên gia trích xuất thông tin có cấu trúc từ văn bản pháp lý tiếng Việt (KIE).

QUY TẮC NGHIÊM NGẶT TỪNG TRƯỜNG:
1. loai_van_ban: CHỈ lấy từ phần TIÊU ĐỀ / ĐẦU văn bản (thường viết HOA, căn giữa).
2. so_van_ban: Trích số ĐẦY ĐỦ. KHÔNG trả về số bộ phận / số rút gọn.
3. co_quan_ban_hanh: Lấy từ góc TRÊN BÊN TRÁI. Thường viết HOA.
4. ngay_ban_hanh: Trả về TOÀN BỘ cụm từ bao gồm địa danh nếu có.
5. trich_yeu: [kèm gợi ý từ Stage-1 để LLM sửa lỗi OCR]
   - GỢI Ý LỜI GIẢI (đã xử lý sơ bộ): "{stage1_hint}"
   - Hãy lấy đoạn trên làm gốc, đối chiếu văn bản để sửa lỗi OCR

KHÔNG hallucinate. Nếu không tìm thấy → trả về null.

ĐẦU RA — chỉ JSON thuần, không markdown:
{
  "loai_van_ban": "...",
  "so_van_ban": "...",
  ...
}
```

**Giao tiếp với Ollama:**
- Thử `/api/generate` trước, fallback sang `/v1/chat/completions`
- Timeout: 90 giây
- JSON response parsing với fallback regex `\{.*\}`

**LLM Confidence:**
- `0.72` (CONF_LLM) — trích xuất thành công
- `0.55` (CONF_LLM_LOW) — LLM trả về nhưng không chắc

### Stage 3: Merge Logic

```python
def _merge_field(stage1_field, stage2_field, field_name):
    # 1. Stage-1 confidence >= 0.85 → Giữ nguyên Regex (đáng tin hơn)
    if s1_conf >= 0.85:
        return stage1_field
    
    # 2. Stage-1 không có giá trị → Lấy LLM
    if s1_val is None:
        return stage2_field
    
    # 3. Trường trich_yeu: ưu tiên LLM để sửa lỗi OCR
    if field_name == "trich_yeu" and len(s2_val) > 10:
        return stage2_field
    
    # 4. Còn lại: chọn confidence cao hơn
    return stage1_field if s1_conf >= s2_conf else stage2_field
```

---

## 4. Engine Tiền Xử Lý Ảnh: OpenCV Pipeline

### Deskew Algorithm
```python
def estimate_skew_angle(image_bgr):
    # Phương pháp 1: HoughLinesP
    # Phát hiện các đường ngang trong ảnh, tính góc trung vị
    lines = cv2.HoughLinesP(binary_inv, rho=1, theta=pi/180, 
                             threshold=80, minLineLength=60)
    angles = [arctan2(y2-y1, x2-x1) for each line]
    return median(angles)  # Ổn định hơn mean
    
    # Fallback: minAreaRect khi không có đường ngang rõ
    coords = np.where(binary_inv > 0)
    angle = cv2.minAreaRect(coords)[-1]
```

### Red Stamp Preservation
```python
def get_red_stamp_mask(image_bgr):
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    # Đỏ trong HSV có 2 vùng (do circular hue):
    lower_red_1 = np.array([0, 60, 40])    # Hue 0-12
    upper_red_1 = np.array([12, 255, 255])
    lower_red_2 = np.array([160, 60, 40])  # Hue 160-180
    upper_red_2 = np.array([180, 255, 255])
    mask = OR(inRange(hsv, lower1, upper1), inRange(hsv, lower2, upper2))
    return mask
```

---

## 5. Engine Phát Hiện Chữ Ký & Mộc Đỏ

### Phát Hiện Chữ Ký: YOLOv8

**Model:** `tech4humans/yolov8s-signature-detector` (HuggingFace)
- Kiến trúc: YOLOv8s (small variant)
- Được fine-tune trên dataset chữ ký đặc thù
- Tự động tải về `~/.cache/huggingface/hub/` lần đầu

```python
from ultralytics import YOLO
model = YOLO("path/to/best.pt")
results = model.predict(image_bgr, conf=0.25, verbose=False)

# Normalize label:
# "signature", "sign", "chu_ky" → "signature"
# "stamp", "seal", "con_dau" → "stamp"
```

### Phát Hiện Mộc Đỏ: Stamp2Vec / YOLO-Stamp

**Model:** `stamps-labs/yolo-stamp` (HuggingFace)
- Pipeline-based interface (khác với YOLO trực tiếp)
- Hỗ trợ nhiều format output: dict với keys `boxes/bboxes/detections/predictions`

```python
from pipelines.detection.yolo_stamp import YoloStampPipeline
pipeline = YoloStampPipeline.from_pretrained("stamps-labs/yolo-stamp")

# Input: PIL Image (RGB)
image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
prediction = pipeline(Image.fromarray(image_rgb))

# Output normalize: [{"label": "stamp", "confidence": 0.85, "bbox": [x1, y1, w, h]}]
```

---

## 6. Engine NLP Correction

**Model:** `bmd1905/vietnamese-correction-v2` (HuggingFace)
- Kiến trúc: Seq2Seq (Encoder-Decoder)
- Được fine-tune trên dataset lỗi chính tả tiếng Việt
- Input max length: 512 tokens

```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

tokenizer = AutoTokenizer.from_pretrained("bmd1905/vietnamese-correction-v2")
model = AutoModelForSeq2SeqLM.from_pretrained("bmd1905/vietnamese-correction-v2")

inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
outputs = model.generate(**inputs, max_length=512)
corrected = tokenizer.decode(outputs[0], skip_special_tokens=True)
```

**Lưu ý về hiệu năng:**
- Chạy trên CPU sẽ chậm (2-10 giây/đoạn)
- Nếu GPU có CUDA, sẽ nhanh đáng kể
- Singleton pattern: model chỉ load 1 lần khi request đầu tiên

---

## 7. Engine Tóm Tắt: Ollama LLM

**Model mặc định:** `qwen2.5:3b-instruct`
- Mô hình 3 tỷ tham số, tối ưu cho máy không có GPU cao cấp
- Hỗ trợ tiếng Việt và tiếng Anh đủ tốt
- Chạy hoàn toàn local (Ollama daemon)

**Prompt template:**
```
Ban la tro ly xu ly van ban hanh chinh/phap ly. 
Hay doc noi dung OCR va viet trich yeu ngan gon, ro y chinh, 
khong them thong tin khong co trong van ban. 
Gioi han toi da {max_words} tu.

Noi dung:
{text}
```

**Hỗ trợ 2 Ollama API endpoints:**
1. `/api/generate` — API cũ của Ollama (response về field `response`)
2. `/v1/chat/completions` — Compatible OpenAI format (response về `choices[0].message.content`)

---

## 8. Engine Xuất PDF: PyMuPDF (fitz)

**Kỹ thuật PDF 2 lớp:**
```python
import fitz  # PyMuPDF

doc = fitz.open()
page = doc.new_page(width=img_width, height=img_height)

# Lớp 1: Ảnh làm sạch (hiển thị)
page.insert_image(fitz.Rect(0, 0, width, height), filename=img_path)

# Lớp 2: Text ẩn (searchable)
for line in ocr_lines:
    page.insert_text(
        (x0, y1),           # Vị trí baseline
        text,
        fontsize=line_height * 0.8,
        fontname="helv",
        render_mode=3       # render_mode=3 = INVISIBLE (không hiển thị nhưng có trong PDF)
    )

doc.save(output_path, deflate=True)
```

> **Hạn chế hiện tại:** Font Helvetica (`helv`) không hỗ trợ đầy đủ Unicode tiếng Việt. Một số ký tự dấu có thể không tìm kiếm được chính xác 100%. Cải thiện: nhúng font có Unicode đầy đủ (VD: font NotoSans).

---

## 9. Cấu Hình Celery

```python
# app/celery_app.py
celery_app = Celery(
    "vn_digitize_tasks",
    broker=REDIS_URL,    # Nhận task từ đây
    backend=REDIS_URL,   # Lưu kết quả vào đây
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",       # Serialize task data bằng JSON
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",  # Timezone Việt Nam
    enable_utc=True,
    task_track_started=True,      # Theo dõi trạng thái STARTED
    task_time_limit=3600,         # Timeout tối đa: 1 tiếng
)
```

---

## 10. Phân Tích Độ Chính Xác & Hạn Chế Kỹ Thuật

### Độ Chính Xác Mong Đợi

| Engine | Loại tài liệu | Độ chính xác ước tính |
|---|---|---|
| OCR (DeepDoc VietOCR) | Ảnh scan chất lượng tốt (300+ DPI) | 95-99% |
| OCR (DeepDoc VietOCR) | Ảnh chụp điện thoại, ánh sáng tốt | 85-95% |
| OCR (DeepDoc VietOCR) | Ảnh mờ, nghiêng nhiều | 60-85% |
| KIE Regex - so_van_ban | Văn bản chuẩn format | ~95% |
| KIE Regex - ngay_ban_hanh | Văn bản chuẩn format | ~95% |
| KIE Regex - loai_van_ban | Tiêu đề rõ ràng | ~98% |
| KIE LLM - trich_yeu | Văn bản rõ ràng | ~80-85% |
| Signature Detection (YOLO) | Chữ ký thực | ~80-90% |
| Stamp Detection (Stamp2Vec) | Mộc đỏ rõ | ~85-92% |

### Hạn Chế Kỹ Thuật Cần Lưu Ý

1. **Handwritten text:** OCR không được train cho chữ viết tay — chỉ hiệu quả với chữ in
2. **Ảnh chất lượng thấp:** DPI < 150, blur mạnh sẽ giảm OCR accuracy xuống dưới 70%
3. **Font đặc biệt:** Một số font hành chính cũ (dot matrix, typewriter) OCR có thể nhầm
4. **Bảng biểu phức tạp:** Table extraction dựa trên text structure, không handle well bảng có merged cells
5. **Custom regex validation:** Regex kiểm tra `so_van_ban` có thể báo warning với format hiếm gặp (format địa phương không chuẩn Bộ Nội Vụ)
6. **Ollama cold start:** Lần đầu gọi Ollama sau khi model được load vào VRAM có thể mất 5-15 giây

### Điểm Yếu Cần Cải Thiện (Technical Debt)

| Vấn đề | Mức độ | Giải pháp đề xuất |
|---|---|---|
| PDF searchable font thiếu dấu Việt | Medium | Nhúng NotoSans Unicode font |
| Scanner integration là stub | High | Implement TWAIN driver theo thiết bị thực |
| Không cache model output | Low | Thêm Redis cache cho KIE result của cùng document hash |
| Không có rate limiting | Medium | Thêm slowapi rate limiter |
| Không có authentication | High | Thêm JWT Bearer token |
| `data/` không tự dọn dẹp | Medium | Thêm cleanup job định kỳ (Celery Beat) |
