# TÀI LIỆU KỸ THUẬT: AI 2 — HỆ THỐNG PHÂN TÍCH TRẠNG THÁI

## 1. Giới thiệu & Mục đích
- **Tên mô hình**: MediaPipe Face Mesh kết hợp với thuật toán Học máy Random Forest.
- **Mục đích**: Phân tích biểu cảm và hành vi của khuôn mặt để suy ra trạng thái sức khỏe/độ tập trung của sinh viên (chống điểm danh hộ hoặc phát hiện ngủ gật).
- **Đầu vào (Input)**: Một chuỗi gồm 3 khung hình liên tiếp (3 frames) được lưu trực tiếp trên RAM.
- **Đầu ra (Output)**: Nhãn trạng thái gồm: `Normal` (Bình thường), `Drowsy` (Buồn ngủ/Lờ đờ), `Yawn` (Ngáp), `Head-down` (Gục đầu).

## 2. Nguyên lý hoạt động (Quy trình)
AI 2 hoạt động theo cơ chế **In-Memory Pipeline** (luồng xử lý trên RAM) chia làm 2 giai đoạn cốt lõi:

**Giai đoạn A: Trích xuất đặc trưng (MediaPipe)**
1. Nhận chuỗi 3 ảnh, dùng MediaPipe Face Mesh quét ra tọa độ 3D của 468 điểm trên khuôn mặt.
2. Từ các điểm này, dùng toán học tính toán các chỉ số vật lý:
   - **EAR (Eye Aspect Ratio)**: Tỷ lệ độ mở của mắt.
   - **MAR (Mouth Aspect Ratio)**: Tỷ lệ độ mở của miệng.
   - **Head Pose (Pitch, Roll, Yaw)**: Góc cúi ngửa, nghiêng và xoay của đầu (dùng OpenCV `solvePnP`).
3. Tổng hợp 3 khung hình thành 1 vector duy nhất phản ánh sự thay đổi theo thời gian:
   `Vector = [min(EAR), mean(EAR), max(MAR), mean(MAR), delta_Pitch, delta_Roll, mean_Pitch]`

**Giai đoạn B: Phân loại trạng thái (Random Forest)**
- Đưa Vector tổng hợp vào mô hình Máy học (Random Forest).
- Dựa trên những gì đã được "Dạy" (Huấn luyện) từ trước, Random Forest sẽ bầu chọn xem vector này thuộc về hành vi nào (Normal, Drowsy, Yawn hay Head-down).
- Kết quả được ghi xuống Database, 3 ảnh trên RAM bị xóa ngay lập tức để giải phóng bộ nhớ.

## 3. Những gì đã hoàn thành (Achieved)
- ✅ Code xong module toán học tính toán EAR, MAR, Head Pose `status_features.py`.
- ✅ Xây dựng công cụ `collect_status.py` giúp con người tự diễn xuất trước Camera để tạo ra Sách giáo khoa (Dataset) cho máy học.
- ✅ Code xong module huấn luyện Máy học `train_rf.py`. Mô hình Random Forest đã có thể tự động đọc file CSV, học và xuất ra bộ não `rf_status_model.pkl`.

## 4. Những điểm cần cải tiến (Future Improvements)
- 🚧 **Chất lượng Dữ liệu (Dataset)**: Hiện tại mới chỉ có tool thu thập, cần bỏ thời gian để thu thập thật nhiều dữ liệu (khoảng hàng trăm dòng cho mỗi trạng thái) ở nhiều điều kiện ánh sáng, góc nghiêng mặt khác nhau để mô hình đoán không bị "ngu".
- 🚧 **Tích hợp Chạy ngầm (Background Worker)**: Cần triển khai bước 4 (Tích hợp AI 1 và AI 2). AI 2 bắt buộc phải được code dưới dạng luồng chạy ngầm (Threading/Async) để khi xử lý 3 khung hình không làm giật lag hay treo Camera của AI 1.
- 🚧 **Kết nối Backend / Database**: Kết quả của AI 2 cần được đóng gói và kết nối với Database MySQL/PostgreSQL thông qua FastAPI/Flask theo đúng kiến trúc ESP32 đề ra ban đầu.

