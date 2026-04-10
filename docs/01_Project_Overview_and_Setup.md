# Tài Liệu Bàn Giao #1: Tổng Quan Dự Án & Hướng Dẫn Cài Đặt
**Dự án:** VN-Digitize-AI  
**Phiên bản:** 0.1.0  
**Ngày bàn giao:** 10/04/2026  
**Người bàn giao:** Team phát triển

---

## 1. Giới Thiệu Dự Án

**VN-Digitize-AI** là hệ thống AI số hoá tài liệu hành chính và pháp lý tiếng Việt, được thiết kế ở chuẩn **Production-grade**. Hệ thống cung cấp toàn bộ pipeline xử lý từ input (ảnh chụp/scan) đến output (dữ liệu có cấu trúc JSON + file PDF tìm kiếm được).

### Mục tiêu nghiệp vụ chính:
- Tự động số hoá văn bản hành chính (công văn, quyết định, thông tư...) từ giấy sang dữ liệu số
- Bóc tách thông tin cốt lõi (số văn bản, ngày ban hành, cơ quan, nội dung...) không cần nhập liệu thủ công
- Hỗ trợ xử lý hàng loạt với khả năng chịu tải qua kiến trúc queue bất đồng bộ
- Giữ bảo mật tuyệt đối: không gọi API bên ngoài, mọi AI đều chạy local

---

## 2. Cấu Trúc Source Code

```
OCR/                                   ← Thư mục gốc dự án
├── app/                               ← Ứng dụng FastAPI chính
│   ├── main.py                        ← Entry-point: đăng ký toàn bộ 16 API endpoints
│   ├── schemas.py                     ← Toàn bộ Pydantic models (Request/Response)
│   ├── celery_app.py                  ← Cấu hình Celery + Redis broker
│   ├── tasks.py                       ← Định nghĩa Celery async tasks
│   └── services/                      ← Lớp nghiệp vụ lõi (Business Logic)
│       ├── preprocessing.py           ← Engine tiền xử lý ảnh (OpenCV)
│       ├── ocr.py                     ← Engine OCR (DeepDoc VietOCR)
│       ├── kie_extractor.py           ← Engine KIE 3 giai đoạn (Regex + LLM + Merge)
│       ├── postprocessing.py          ← Engine hậu kỳ (YOLO chữ ký, Stamp2Vec mộc đỏ)
│       ├── document_splitter.py       ← Engine phân tách tài liệu theo nội dung
│       ├── document_scanner.py        ← Làm thẳng và cắt tài liệu (OpenCV Scan)
│       ├── barcode_splitter.py        ← Phân tách bundle theo mã vạch (pyzbar)
│       ├── summarizer.py              ← Tóm tắt tự động qua Ollama LLM
│       ├── nlp_correction.py          ← Sửa lỗi chính tả OCR (Hugging Face model)
│       ├── pdf_exporter.py            ← Xuất PDF 2 lớp tìm kiếm được (PyMuPDF)
│       ├── feedback.py                ← Lưu phản hồi QA (TinyDB)
│       ├── table_extraction.py        ← Bóc tách bảng biểu từ OCR text
│       ├── validation.py              ← Kiểm tra logic nghiệp vụ (ngày, số hiệu)
│       └── scanner.py                 ← Kết nối máy scan vật lý
├── deepdoc_vietocr/                   ← Module OCR nội bộ (DeepDoc + VietOCR)
│   └── module/ocr.py                  ← Class OCR chính (vgg_transformer)
├── OpenCV-Document-Scanner/           ← Thư viện phụ trợ scan tài liệu bằng OpenCV
├── tessdata/                          ← Dữ liệu ngôn ngữ Tesseract (tiếng Việt)
├── data/                              ← Thư mục dữ liệu runtime (tự tạo khi chạy)
│   ├── raw/                           ← Upload thô
│   ├── preprocessed/                  ← Ảnh sau khi làm sạch
│   ├── exported/                      ← File PDF xuất ra
│   └── feedback.json                  ← Database phản hồi QA (TinyDB)
├── docs/                              ← Tài liệu dự án
├── tests/                             ← Unit tests
├── demo.py                            ← Demo script chạy toàn bộ pipeline
├── test_kie.py                        ← Test riêng cho KIE engine
├── requirements.txt                   ← Danh sách Python dependencies
└── pytest.ini                         ← Cấu hình pytest
```

---

## 3. Stack Công Nghệ

| Hạng mục | Công nghệ | Phiên bản tối thiểu | Ghi chú |
|---|---|---|---|
| Backend Web | FastAPI | >=0.115.0 | RESTful API framework |
| ASGI Server | Uvicorn | >=0.30.0 | Chạy FastAPI |
| Task Queue | Celery | >=5.4.0 | Xử lý bất đồng bộ |
| Message Broker | Redis | >=5.0.0 | Backend broker cho Celery |
| OCR Engine | DeepDoc VietOCR | nội bộ | vgg_transformer, đọc tiếng Việt |
| Computer Vision | OpenCV | 4.10.0.84 | Tiền xử lý ảnh |
| Object Detection | Ultralytics (YOLO) | >=8.2.0 | Phát hiện chữ ký (YOLOv8) |
| Stamp Detection | stamps-labs/yolo-stamp | HuggingFace | Phát hiện mộc đỏ |
| Local LLM | Ollama | latest | Chạy Qwen2.5:3b-instruct local |
| NLP Correction | bmd1905/vietnamese-correction-v2 | HuggingFace | Sửa lỗi chính tả |
| PDF Processing | PyMuPDF (fitz) | >=1.23.0 | Xuất PDF 2 lớp |
| Data Validation | Pydantic | bundled with FastAPI | Schema Input/Output |
| Barcode | pyzbar | >=0.1.9 | Nhận diện mã vạch |
| Feedback DB | TinyDB | >=4.8.0 | Lưu dữ liệu phản hồi QA |
| DL Framework | PyTorch + HuggingFace Transformers | latest | NLP model inference |
| Test Framework | pytest + httpx | >=8.0.0 | Unit & integration tests |

---

## 4. Yêu Cầu Hệ Thống

### Phần cứng tối thiểu:
- **RAM:** 8 GB (khuyến nghị 16 GB khi chạy model AI đồng thời)
- **Ổ đĩa:** 20 GB trống (model AI + data runtime)
- **GPU:** Tùy chọn (hệ thống tương thích CPU-only nhưng chậm hơn)

### Phần mềm bắt buộc:
- **Python:** 3.10 hoặc 3.11
- **Redis Server:** 6.x hoặc 7.x (cài riêng, không có trong requirements.txt)
- **Ollama:** Phiên bản mới nhất (download tại https://ollama.ai)
- **Tesseract OCR:** 5.x (cài riêng, kèm gói ngôn ngữ tiếng Việt `vie`)
- **zbar library:** Cần thiết để pyzbar đọc barcode (cài qua hệ thống OS)

---

## 5. Hướng Dẫn Cài Đặt Chi Tiết

### Bước 1: Cài đặt phần mềm ngoại biên

#### Cài Tesseract OCR (Windows):
```powershell
# Tải installer tại: https://github.com/UB-Mannheim/tesseract/wiki
# Sau khi cài, thêm vào PATH, ví dụ:
# C:\Program Files\Tesseract-OCR

# Xác nhận cài đặt:
tesseract --version
```

#### Cài Redis (Windows):
```powershell
# Option 1: Dùng WSL2 (khuyến nghị)
wsl --install
# Trong WSL:
sudo apt update && sudo apt install redis-server
redis-server --daemonize yes

# Option 2: Dùng Redis for Windows (Memurai hoặc Redis Stack)
# Tải tại: https://redis.io/download
```

#### Cài Ollama và tải model:
```powershell
# Tải Ollama tại: https://ollama.ai/download
# Sau khi cài, tải model KIE mặc định:
ollama pull qwen2.5:3b-instruct

# Test Ollama đang chạy:
ollama list
# Ollama service sẽ tự chạy tại http://127.0.0.1:11434
```

#### Cài zbar (cho pyzbar - barcode):
```powershell
# Windows: Tải Windows installer tại http://zbar.sourceforge.net/
# Hoặc qua conda: conda install -c conda-forge zbar
```

### Bước 2: Clone và cài đặt Python dependencies

```powershell
# Đi đến thư mục dự án
cd C:\đường\dẫn\đến\OCR

# Tạo virtual environment
python -m venv .venv

# Kích hoạt venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/Mac

# Cài đặt các thư viện Python
pip install -r requirements.txt
```

> **Lưu ý:** Quá trình cài `torch` và `ultralytics` có thể mất 10-20 phút do kích thước lớn. Đảm bảo kết nối internet ổn định.

### Bước 3: Xác nhận cài đặt

```powershell
python -c "import cv2; import fastapi; import celery; print('OK')"
python -c "from app.main import app; print('FastAPI app loaded OK')"
```

---

## 6. Cách Chạy Dự Án

### Chạy FastAPI Server (Development)

```powershell
# Đảm bảo venv đã kích hoạt
.venv\Scripts\activate

# Chạy server (từ thư mục gốc OCR/)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# API sẽ sẵn sàng tại:
# http://localhost:8000
# Swagger UI tại: http://localhost:8000/docs
# ReDoc tại:      http://localhost:8000/redoc
```

### Chạy Celery Worker (xử lý tác vụ bất đồng bộ)

```powershell
# Terminal riêng, đảm bảo Redis đang chạy trước
.venv\Scripts\activate

# Windows: Phải thêm -P gevent hoặc -P solo
celery -A app.celery_app worker --loglevel=info -P solo

# Linux:
# celery -A app.celery_app worker --loglevel=info --concurrency=4
```

### Chạy Demo Pipeline đầy đủ

```powershell
# Đảm bảo Ollama đang chạy và đã tải model
python demo.py
```

### Chạy Tests

```powershell
# Toàn bộ test suite
pytest

# Test riêng KIE engine (cần Ollama đang chạy)
python test_kie.py

# Xem coverage
pytest --cov=app tests/
```

---

## 7. Các Biến Môi Trường Quan Trọng

| Biến | Giá trị mặc định | Mô tả |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | URL kết nối Redis broker |

Các tham số cấu hình khác (Ollama URL, model name) được truyền trực tiếp qua API request body, không cần set env riêng trừ `REDIS_URL`.

**Thiết lập biến môi trường:**
```powershell
# Windows
$env:REDIS_URL = "redis://your-redis-server:6379/0"

# Linux
export REDIS_URL="redis://your-redis-server:6379/0"
```

---

## 8. Cấu Trúc Thư Mục `data/` (Runtime)

Thư mục `data/` được tạo tự động khi server khởi động lần đầu:

```
data/
├── raw/             ← Upload tạm thời (mỗi session một UUID folder)
├── preprocessed/    ← Ảnh sau xử lý (tự dọn sau khi dùng xong)
├── exported/        ← File PDF xuất ra cho người dùng
└── feedback.json    ← Database JSON (TinyDB) lưu phản hồi QA
```

> ⚠️ **Lưu ý bảo mật:** Thư mục `data/` chứa thông tin tài liệu. Cần cấu hình quyền truy cập phù hợp và backup định kỳ, đặc biệt `feedback.json` vì đây là dữ liệu phục vụ huấn luyện model về sau.
