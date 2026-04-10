# Tài Liệu Bàn Giao #5: Tài Khoản, Vận Hành & Checklist Bàn Giao
**Dự án:** VN-Digitize-AI  
**Phiên bản:** 0.1.0  
**Phân loại:**  CONFIDENTIAL — Chỉ dành cho IT Lead, DevOps, PM  
**Dành cho:** System Administrator, DevOps Engineer, Project Manager

---

>  **LƯU Ý BẢO MẬT:** File này chứa thông tin tài khoản và cấu hình nhạy cảm.  
> Không commit file này lên Git public repository.  
> Mã hóa hoặc lưu trong Password Manager trước khi chia sẻ.

---

## 1. Danh Sách Tài Khoản & Credentials

### 1.1. Server / Infrastructure

| Mục | Thông tin | Ghi chú |
|---|---|---|
| **Server IP** | `_______________` | Điền IP server production |
| **SSH User** | `_______________` | User SSH không phải root |
| **SSH Private Key** | `_______________` | Đường dẫn file `.pem` / `.ppk` |
| **SSH Port** | `22` (mặc định) | Thay đổi nếu custom port |

**Lệnh kết nối SSH:**
```bash
ssh -i /path/to/key.pem username@SERVER_IP
```

---

### 1.2. Redis Server

| Mục | Giá trị mặc định | Giá trị Production |
|---|---|---|
| **Host** | `localhost` | `_______________` |
| **Port** | `6379` | `_______________` |
| **Password** | (none) | `_______________` |
| **Database index** | `0` | `0` |

**Connection string format:**
```
redis://:PASSWORD@HOST:PORT/0
```

**Biến môi trường cần set:**
```bash
export REDIS_URL="redis://:your_password@your_host:6379/0"
```

---

### 1.3. Ollama (Local LLM Service)

Ollama chạy local trên cùng server, không cần tài khoản. Tuy nhiên cần biết:

| Mục | Giá trị |
|---|---|
| **Ollama service URL** | `http://127.0.0.1:11434` |
| **Model mặc định** | `qwen2.5:3b-instruct` |
| **Model được cài** | `_______________` (liệt kê các model đã pull) |

**Kiểm tra Ollama đang chạy:**
```bash
curl http://localhost:11434/api/tags
# Hoặc:
ollama list
```

**Pull model (khi setup server mới):**
```bash
ollama pull qwen2.5:3b-instruct
# Các model khác nếu cần:
# ollama pull llama3.2:3b
# ollama pull gemma2:2b
```

**Khởi động Ollama như service (Linux systemd):**
```bash
# Kiểm tra trạng thái
systemctl status ollama

# Khởi động
systemctl start ollama

# Cài đặt auto-start
systemctl enable ollama
```

---

### 1.4. HuggingFace (Model Download)

Các model AI tự động tải từ HuggingFace Hub lần đầu chạy. Nếu server không có internet, cần tải trước và cấu hình local path.

| Model | HuggingFace Repo | Dùng trong |
|---|---|---|
| Signature detector | `tech4humans/yolov8s-signature-detector` | `postprocessing.py` |
| Stamp detector | `stamps-labs/yolo-stamp` | `postprocessing.py` |
| NLP correction | `bmd1905/vietnamese-correction-v2` | `nlp_correction.py` |

**HuggingFace Token (nếu repo private):**
```bash
export HUGGINGFACE_HUB_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxx"
# Hoặc đăng nhập:
huggingface-cli login
```

**Cache location mặc định:**
```
~/.cache/huggingface/hub/
```

**Cài đặt offline mode:**
```bash
export HF_HUB_OFFLINE=1       # Không fetch model mới
export TRANSFORMERS_OFFLINE=1  # Transformers offline mode
```

---

### 1.5. Tài Khoản Công Cụ Monitor (Celery Flower)

Flower là dashboard monitoring Celery tasks. Nếu đã triển khai:

| Mục | Giá trị |
|---|---|
| **URL** | `http://SERVER_IP:5555` |
| **Basic Auth User** | `_______________` |
| **Basic Auth Password** | `_______________` |

**Khởi động Flower:**
```bash
celery -A app.celery_app flower --port=5555 --basic_auth=admin:secretpassword
```

---

## 2. Hướng Dẫn Deploy & Vận Hành

### 2.1. Quy Trình Deploy Lần Đầu (Fresh Server)

```bash
# 1. Cài đặt prerequisites (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
                    redis-server tesseract-ocr tesseract-ocr-vie \
                    libzbar0 zbar-tools git

# 2. Cài Ollama
curl -fsSL https://ollama.ai/install.sh | sh
systemctl enable ollama && systemctl start ollama
ollama pull qwen2.5:3b-instruct

# 3. Clone project
git clone <REPO_URL> /opt/vn-digitize
cd /opt/vn-digitize/OCR

# 4. Tạo virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 5. Cài dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 6. Cấu hình environment
echo "REDIS_URL=redis://localhost:6379/0" > .env
# Hoặc export trực tiếp:
export REDIS_URL="redis://localhost:6379/0"

# 7. Test nhanh
python -c "from app.main import app; print('OK')"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

### 2.2. Chạy Như Service (systemd - Production)

#### File service FastAPI: `/etc/systemd/system/vn-digitize-api.service`
```ini
[Unit]
Description=VN-Digitize AI API Service
After=network.target redis.service ollama.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/vn-digitize/OCR
Environment="REDIS_URL=redis://localhost:6379/0"
ExecStart=/opt/vn-digitize/OCR/.venv/bin/uvicorn app.main:app \
          --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### File service Celery: `/etc/systemd/system/vn-digitize-worker.service`
```ini
[Unit]
Description=VN-Digitize Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/vn-digitize/OCR
Environment="REDIS_URL=redis://localhost:6379/0"
ExecStart=/opt/vn-digitize/OCR/.venv/bin/celery \
          -A app.celery_app worker --loglevel=info --concurrency=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Kích hoạt services:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable vn-digitize-api vn-digitize-worker
sudo systemctl start vn-digitize-api vn-digitize-worker
```

---

### 2.3. Quy Trình Update Code (Deploy Update)

```bash
# 1. SSH vào server
ssh -i key.pem user@SERVER_IP

# 2. Vào thư mục dự án
cd /opt/vn-digitize/OCR

# 3. Pull code mới
git pull origin main

# 4. Cập nhật dependencies nếu có thay đổi requirements.txt
source .venv/bin/activate
pip install -r requirements.txt

# 5. Restart services
sudo systemctl restart vn-digitize-api
sudo systemctl restart vn-digitize-worker

# 6. Kiểm tra trạng thái
sudo systemctl status vn-digitize-api
sudo systemctl status vn-digitize-worker

# 7. Xem log để xác nhận OK
sudo journalctl -u vn-digitize-api -n 50 --no-pager
```

---

## 3. Giám Sát & Xem Log

### 3.1. System Logs

```bash
# Log FastAPI/Uvicorn (realtime)
sudo journalctl -u vn-digitize-api -f

# Log Celery Worker (realtime)
sudo journalctl -u vn-digitize-worker -f

# Log 100 dòng gần nhất
sudo journalctl -u vn-digitize-api -n 100 --no-pager

# Log từ 1 giờ qua
sudo journalctl -u vn-digitize-api --since "1 hour ago"
```

### 3.2. Các Lỗi Phổ Biến & Cách Xử Lý

**Lỗi 1: Celery worker không nhận task**
```bash
# Kiểm tra Redis có chạy không
redis-cli ping   # Phải trả về "PONG"

# Kiểm tra kết nối Redis trong Celery
celery -A app.celery_app inspect ping

# Khởi động lại Redis
sudo systemctl restart redis
sudo systemctl restart vn-digitize-worker
```

**Lỗi 2: OCR engine không load được (`Cannot find deepdoc_vietocr`)**
```bash
# Kiểm tra thư mục tồn tại
ls /opt/vn-digitize/OCR/deepdoc_vietocr/

# Nếu không có, cần restore từ backup hoặc clone lại
git submodule update --init  # nếu là git submodule
```

**Lỗi 3: Ollama không phản hồi (KIE Stage 2 fail)**
```bash
# Kiểm tra Ollama running
systemctl status ollama
curl http://localhost:11434/api/tags

# Khởi động lại
systemctl restart ollama
ollama list  # Xác nhận model còn đây
```

**Lỗi 4: HuggingFace model download fail (postprocessing)**
```bash
# Xóa cache bị hỏng
rm -rf ~/.cache/huggingface/hub/models--tech4humans*
rm -rf ~/.cache/huggingface/hub/models--stamps-labs*

# Download lại bằng Python
python -c "from huggingface_hub import hf_hub_download; hf_hub_download('tech4humans/yolov8s-signature-detector', 'yolov8s.pt')"
```

**Lỗi 5: `data/` directory permissions**
```bash
# Đặt quyền cho thư mục data
chown -R ubuntu:ubuntu /opt/vn-digitize/OCR/data
chmod -R 755 /opt/vn-digitize/OCR/data
```

### 3.3. Health Check Nhanh

```bash
# Kiểm tra API đang chạy
curl http://localhost:8000/docs

# Kiểm tra toàn bộ services
systemctl is-active vn-digitize-api     # active = OK
systemctl is-active vn-digitize-worker  # active = OK
systemctl is-active redis               # active = OK
systemctl is-active ollama              # active = OK
redis-cli ping                          # PONG = OK
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; print('Ollama OK, models:', len(json.load(sys.stdin)['models']))"
```
---

## 4. Backup & Restore

### 4.1. Dữ Liệu Cần Backup

| Dữ liệu | Vị trí | Tần suất backup | Lý do |
|---|---|---|---|
| **Feedback QA database** | `data/feedback.json` | Hàng ngày | Dữ liệu training model tương lai |
| **Exported PDFs** | `data/exported/` | Hàng tuần | File đầu ra cho khách hàng |
| **HuggingFace model cache** | `~/.cache/huggingface/` | 1 lần khi setup | Tránh download lại tốn bandwidth |
| **Ollama models** | `~/.ollama/models/` | 1 lần khi setup | Model LLM local |

### 4.2. Script Backup `feedback.json`

```bash
#!/bin/bash
# backup_feedback.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/vn-digitize"
mkdir -p $BACKUP_DIR

# Copy feedback database
cp /opt/vn-digitize/OCR/data/feedback.json $BACKUP_DIR/feedback_${DATE}.json

# Giữ 30 bản backup gần nhất
ls -t $BACKUP_DIR/feedback_*.json | tail -n +31 | xargs rm -f

echo "Backup completed: feedback_${DATE}.json"
```

Thêm vào crontab để chạy tự động:
```bash
crontab -e
# Thêm dòng này để backup mỗi ngày lúc 2am:
0 2 * * * /opt/vn-digitize/scripts/backup_feedback.sh >> /var/log/vn-digitize-backup.log 2>&1
```

### 4.3. Export Feedback Data 

```python
# export_feedback.py - chạy khi cần dataset training
from app.services.feedback import get_all_feedback
import json, datetime

data = get_all_feedback()
filename = f"feedback_export_{datetime.date.today()}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"Exported {len(data)} records to {filename}")
```

## 5. Ghi Chú Kỹ Thuật Đặc Biệt

> ** Quan trọng 1:** Scanner vật lý (`source=scanner`) là **chưa implement** (stub). Gọi API này sẽ trả về lỗi 501. Cần implement TWAIN/WIA driver theo thiết bị scan thực tế của đơn vị.

> ** Quan trọng 2:** Hệ thống **chưa có authentication**. Bất kỳ ai có IP server đều có thể gọi API. Cần bổ sung auth trước khi expose ra internet.

> ** Quan trọng 3:** File `data/feedback.json` là nguồn dataset training quý giá. Đây là dữ liệu thực tế từ operation, backup và bảo quản cẩn thận.

> ** Lưu ý 4:** Lần đầu chạy postprocessing, hệ thống sẽ tự tải YOLO model (~50MB) và Stamp2Vec (~100MB) từ HuggingFace. Cần đảm bảo server có internet và đủ dung lượng disk.

> ** Lưu ý 5:** Nếu Ollama không chạy khi gọi KIE endpoint, hệ thống vẫn hoạt động bình thường với chỉ Stage-1 (Regex). Kết quả KIE vẫn có nhưng `model_used` sẽ là `null` và `trich_yeu` có thể kém chính xác hơn.
