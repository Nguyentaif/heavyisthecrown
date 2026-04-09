# Báo Cáo Cập Nhật Hệ Thống VN-Digitize-AI
**Chủ đề trọng tâm:** Hoàn thiện KIE và cập nhật OCR engine sang DeepDoc VietOCR

## Cập nhật mới nhất (06/04/2026)
- Đã thay thế pipeline OCR cũ (Tesseract + VietOCR cục bộ) bằng framework `deepdoc_vietocr` trong `app/services/ocr.py`.
- Giữ nguyên response schema cho API OCR (`full_text`, `lines[].bbox`, `lines[].confidence`) để tương thích với luồng KIE/QA hiện tại.
- Bổ sung dependency phục vụ deepdoc OCR: `onnxruntime`, `huggingface-hub`, `pdfplumber`, `ruamel.yaml`, `cachetools`, `pycryptodomex`.

Hôm nay, toàn bộ kiến trúc KIE của dự án đã được xây dựng, mở rộng và sửa lỗi thành công. Đây là một bước tiến lớn giúp hệ thống không chỉ số hoá văn bản thô mà còn hiểu và bóc tách dữ liệu có cấu trúc dành cho hệ thống lưu trữ/nghiệp vụ.

---

##  1. Xây dựng Kiến Trúc "Hybrid KIE Extraction" (Kết Hợp Regex & LLM)
Hệ thống KIE đã được thiết kế bằng luồng đa lớp (Multi-stage) để tối ưu độ chính xác và tốc độ:
- **Ngữ cảnh:** Cần xử lý các văn bản hành chính phức tạp của Việt Nam.
- **Stage 1 (Regex/Rule-based):** Xây dựng các mẫu pattern ngữ pháp tiếng Việt để quét tự động (Ví dụ: 19 loại văn bản, 15 prefix cơ quan, 4 định dạng số công văn). Luồng Regex mang lại độ tin cậy cực cao (`confidence > 0.9`).
- **Stage 2 (LLM Fallback):** Tích hợp Ollama (model `qwen2.5:3b-instruct`) để xử lý các phần văn bản mà Regex không thể đảm bảo (dưới dạng mồi "Hints" thông minh lấy từ Stage 1).
- **Stage 3 (Merge Module):** Logic sáp nhập (Merge) tự động so sánh điểm `confidence` giữa Regex và LLM để đưa ra quyết định chọn trường thông tin đáng tin cậy nhất.

**5 Trường Trích Xuất Tiêu Chuẩn (Core Fields)**:
Mỗi trường trả về `value` (giá trị đoạn chữ) và `confidence` (độ tin cậy 0.0 - 1.0):
1. `loai_van_ban` (VD: Nghị định, Thông tư...)
2. `so_van_ban` (VD: 282/2025/NĐ-CP)
3. `ngay_ban_hanh` (VD: Hà Nội, ngày 30 tháng 10 năm 2025)
4. `co_quan_ban_hanh` (VD: CHÍNH PHỦ)
5. `trich_yeu` (Tiêu đề, tóm tắt)

---

##  2. Nâng cấp Architecture: KIE Template Động (Dynamic Fields)
Thay vì chỉ giới hạn ở 5 trường cứng, hệ thống đã được tái cấu trúc (Refactoring Pydantic Schemas & logic trích xuất) để cho phép bóc tách bất kỳ trường nào theo **Template Đơn vị/Nghiệp vụ**.
- **Tính năng Template:** Gửi kèm danh sách các `CustomFieldDef` (bao gồm mô tả trường, pattern regex tương ứng).
- **Cơ chế động (Dynamic Injection):** Tự động tiêm (inject) các luật xuất/nhập, regex tự định nghĩa vào trong cả 2 luồng: Rule-based Stage 1 và Prompt của LLM Stage 2.
- **Tính ứng dụng cao:** Có thể mở rộng lấy "Tên bị cáo", "Tội danh" đối với án tòa, hoặc "Mã BHXH" đối với hóa đơn bảo hiểm mà không cần sửa code cốt lõi.

---

##  3. Triển khai KIE APIs cho Frontend / Client
Hai Endpoint xịn sò đã được mở ra trong hệ thống FastAPI:
- **`POST /api/v1/kie` (Text-to-KIE):** Dành cho hệ thống đã có file word/text và chỉ cần bóc tách siêu nhanh (Lightweight).
- **`POST /api/v1/ocr-kie` (Image-to-KIE):** Luồng "All-in-one" cực khỏe. Nhận đầu vào là ảnh văn bản thô, tự động phân luồng → Tiền xử lý → OCR qua `deepdoc_vietocr` → Bo khung Bounding Box chữ → Gọi vào Extract KIE từng trang → Tổng hợp thành KIE Metadata cuối cùng cho cả Document.
- **`POST /api/v1/extract-fields`:** Endpoint nghiệp vụ chuẩn cho ảnh/PDF scan -> OCR -> trích xuất trường dữ liệu + logic validation hậu xử lý (ngày ban hành, định dạng số/ký hiệu).
- **`POST /api/v1/split-document`:** Endpoint tách một bộ tài liệu lớn thành nhiều tài liệu thành phần theo tín hiệu nội dung (classification/KIE theo từng trang), đồng thời trả về cây mục lục JSON cho frontend.
- **`POST /api/v1/postprocess-check`:** Kiểm tra hậu xử lý sau OCR, gồm:
  - nhận diện **stamp** bằng pipeline từ source `stamp2vec` (repo `stamps-labs/stamp2vec`, pretrained `stamps-labs/yolo-stamp`),
  - nhận diện **signature** bằng YOLO (mặc định model Hugging Face `tech4humans/yolov8s-signature-detector`, vẫn có thể override bằng `yolo_model_path`),
  - bóc tách bảng thành JSON hàng/cột từ OCR lines.
  - Hệ thống ưu tiên import `stamp2vec` từ repo local (ví dụ thư mục `stamp2vec/` ở root project) nếu đã clone sẵn.

---

##  4. Fix Bug & Tối ưu hoá Tự Động Sửa Lỗi Chính Tả (Trích yếu)
- **Vấn đề phát sinh:** OCR của một số trường dài như `trich_yeu` đôi lúc để lại lỗi chính tả (VD: "uy định" thay vì "Quy định", "chồng" thay vì "chống", "vưem ninh" thay vì "vực an ninh"). LLM đôi khi bị bối rối bởi prompt cung cấp hints và nguyên văn thô OCR dẫn tới tự "chép lại" lỗi chính tả.
- **Giải pháp dứt điểm:**
  1. Tách hàm `_clean_ocr_text` hoạt động như vòng gác chữ cuối cùng (Fail-safe filtering) nằm thẳng trong bộ phận Merge của `trich_yeu`. Dù xuất phát từ Regex hay LLM, kết quả cuối cùng luôn đi qua bộ lọc từ khóa mạn tính.
  2. Viết lại ngữ cảnh (Prompt Instructions) thân thiện hơn với LLM nhỏ (3B) để nó hiểu rằng nhiệm vụ không phải là chép lại mà là "Soi kỹ Hint và sửa lỗi".

---

### Tóm gọn Test/Thử nghiệm
Các thay đổi đã được xác nhận kiểm chứng (Verified) qua Unit tests (`test_kie_extractor.py`) và tích hợp thử nghiệm (`test_kie.py`) sử dụng Ollama và văn bản ảnh mock.


