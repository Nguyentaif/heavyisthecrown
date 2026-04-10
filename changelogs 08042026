# BÁO CÁO CẬP NHẬT HỆ THỐNG - Ngày 08/04/2026

## I. Tổng quan Thay đổi
Báo cáo này liệt kê chi tiết các nâng cấp kỹ thuật dành cho hệ thống VN-Digitize-AI. Đợt cập nhật tập trung vào việc hoàn thành ba hạng mục kiến trúc cốt lõi nhằm đưa hệ thống từ trạng thái xử lý đồng bộ cơ bản lên chuẩn hệ thống chịu tải cao (Production-ready). Các hạng mục bao gồm: Xây dựng luồng xử lý bất đồng bộ, xuất bản định dạng chuẩn lưu trữ và thiết lập cơ sở cho học máy tăng cường.

## II. Cập nhật Môi trường và Phụ thuộc (Dependencies)
Tập tin thay đổi: `requirements.txt`
Các gói thư viện mới được bổ sung phục vụ cho các module độc lập:
- Khung xử lý nền: Thêm `celery>=5.4.0` để định tuyến và cấp phát hàng đợi tác vụ; thêm `redis>=5.0.0` đóng vai trò Message Broker lưu trữ hàng đợi.
- Xử lý tài liệu lõi: Thêm `PyMuPDF>=1.23.0` để can thiệp bộ nhớ đệm và xây dựng cấu trúc lớp (layer) của file PDF.
- Mô hình ngôn ngữ tự nhiên: Thêm `transformers>=4.40.0` và `sentencepiece>=0.2.0` để kết nối và giải mã dữ liệu của mạng nơ-ron (PhoBERT/BART).
- Cơ sở dữ liệu nhúng: Thêm `tinydb>=4.8.0` cho thao tác lưu trữ nguyên thủy (JSON-based) tốc độ cao mà không yêu cầu cài đặt SQL Server.

## III. Chi tiết Triển khai Theo Từng Hạng Mục

### 1. Kiến trúc Xử lý Bất đồng bộ (Phase 1)
**Mục đích:** Xử lý hiện tượng thắt cổ chai (Timeout 504) trên các tài liệu PDF dung lượng lớn (trên 50 trang) do thời gian trích xuất thông tin (KIE) quá dài.

**Các tập tin cập nhật:** `app/celery_app.py`, `app/tasks.py`, `app/main.py`, `app/schemas.py`
**Chi tiết kỹ thuật:**
- Khởi tạo hạt nhân `app/celery_app.py`: Thiết lập cấu hình Celery Worker kết nối với Broker tại địa chỉ cục bộ `redis://localhost:6379/0`.
- Đóng gói Tác vụ (`app/tasks.py`): Bao bọc logic giải nén và KIE thành hai worker task chuyên trách `process_ocr_kie` và `process_split_document`. Các task này có khả năng tự báo cáo trạng thái thực thi thông qua phương thức `update_state`.
- Khai báo Schema (`app/schemas.py`): Xây dựng mô hình kiểm soát dữ liệu đầu vào và đầu ra gồm `AsyncTaskResponse` (trả về mã định danh tác vụ) và `TaskStatusResponse` (trả về tiến trình chi tiết).
- Tích hợp Định tuyến (`app/main.py`): Xây dựng ba endpoint vô hướng mới:
  - `POST /api/v1/async/ocr-kie`: Tiếp nhận hồ sơ số hóa, đẩy xuống worker và trả về `task_id` ngay lập tức.
  - `POST /api/v1/async/split-document`: Tương tự cho tính năng tách tài liệu.
  - `GET /api/v1/task/{task_id}`: Điểm giao tiếp theo phong cách Polling, cho phép Frontend tự động truy vấn trạng thái cấu trúc (Pending, Progress, Success, Failure) theo chu kỳ.

### 2. Định dạng Xuất bản Lưu trữ Tiêu chuẩn (Phase 2)
**Mục đích:** Tuân thủ quy định lưu trữ quốc gia về định dạng PDF/A có khả năng tìm kiếm và sao chép văn bản, đảm bảo tính pháp lý của bản quét.

**Các tập tin cập nhật:** `app/services/pdf_exporter.py`, `app/schemas.py`, `app/main.py`
**Chi tiết kỹ thuật:**
- Xây dựng Module Kết Xuất (`app/services/pdf_exporter.py`): Phát triển thuật toán `create_searchable_pdf`. Thuật toán thực hiện bóc tách hai lớp:
  - Lớp hiển thị (Layer 1): Hình ảnh tài liệu đã qua tiền xử lý, căn chỉnh lại đúng kích thước để giữ mộc đỏ và chữ ký góc.
  - Lớp dữ liệu (Layer 2): Chuyển đổi ma trận tọa độ hộp giới hạn (Bounding box) từ PaddleOCR thành dữ liệu văn bản vô hình (render_mode = 3).
- Cập nhật Giao tiếp Đầu cuối:
  - Khởi tạo quy chuẩn `ExportPDFRequest` và `ExportPDFResponse` trong `schemas.py`.
  - Mở cổng API `POST /api/v1/export-pdf-searchable` để nhận tham số đường dẫn và thực thi thuật toán, trả về liên kết lưu trữ.

### 3. Hiệu đính Xử lý Ngôn ngữ Tự nhiên & Vòng Lặp Học (Phase 3)
**Mục đích:** Xử lý triệt để các sai sót chính tả cục bộ (nhòe mực, mờ chữ) mà các engine như PaddleOCR không thể giải quyết bằng thuật toán quang học. Đồng thời xây dựng cơ sở thu thập dữ liệu huấn luyện độc quyền.

**Các tập tin cập nhật:** `app/services/nlp_correction.py`, `app/services/feedback.py`, `app/schemas.py`, `app/main.py`
**Chi tiết kỹ thuật:**
- Chức năng Hiệu đính Từ Vựng (`app/services/nlp_correction.py`):
  - Áp dụng cấu trúc `AutoModelForSeq2SeqLM` của thư viện Transformers để nạp mô hình dịch máy `bmd1905/vietnamese-correction-v2`. Mô hình sẽ nội suy và chẩn đoán cấu trúc hình thái từ sai để sắp xếp lại đúng ngữ pháp tiếng Việt.
  - Cơ chế Phòng vệ (Graceful Fallback): Toàn bộ thao tác nạp và dự đoán được bọc trong bộ giám sát ngoại lệ. Nếu mô hình bị thiếu thẻ token hoặc quá tải RAM, hệ thống sẽ trả về chuỗi văn bản nguyên gốc, tuyệt đối không làm đứt gãy luồng mã.
- Cơ chế Nhân bản Quản trị (Human-in-the-Loop) (`app/services/feedback.py`):
  - Khai báo TinyDB cấp phát tập tin `data/feedback.json`.
  - Xây dựng điểm cuối ghi đè (Save Feedback) để nhận dạng từ sai gốc (Original Text) và từ chốt chặn bởi quản trị viên (Corrected Text).
- Hoàn thiện Endpoint:
  - Thêm lược đồ dữ liệu và lộ trình `POST /api/v1/feedback` cho phép Front-end truyền trực tiếp tập hợp các lỗi chính tả được ghi nhận tại giao diện kiểm duyệt (QA Flow).
  - Thêm `POST /api/v1/nlp-correct` dưới dạng môi trường kiểm thử trực tiếp (Sandbox) phương trình lỗi câu của hệ thống cốt lõi.

## IV. Kết luận
Bộ khung hệ thống hiện tại đã thỏa mãn trọn vẹn toàn bộ yêu cầu mô tả chuyên sâu. Sau bản cập nhật này, mã nguồn có khả năng vận hành tự chủ cao độ, đồng thời đáp ứng các chu kỳ tự học dữ liệu thông qua vòng lặp phản hồi thủ công. Hệ thống khuyến nghị khởi động cùng bộ tham số đa luồng nhằm tiết kiệm tối đa tài nguyên máy chủ vật lý.
