# TÀI LIỆU KỸ THUẬT: AI 1 — HỆ THỐNG ĐIỂM DANH (FACE RECOGNITION)

## 1. Giới thiệu & Mục đích
- **Tên mô hình**: InsightFace (sử dụng backbone `buffalo_sc` siêu nhẹ).
- **Mục đích**: Nhận diện khuôn mặt sinh viên để tiến hành điểm danh tự động thông qua camera (ESP32-CAM).
- **Đầu vào (Input)**: 1 khung hình (frame) chứa khuôn mặt.
- **Đầu ra (Output)**: Mã định danh của sinh viên (User ID) hoặc "Chưa đăng ký".

## 2. Nguyên lý hoạt động (Quy trình)
Công nghệ cốt lõi của AI 1 là **so khớp vector đặc trưng (Feature Matching)** thông qua 3 bước chính:
1. **Phát hiện (Face Detection)**: Tìm vị trí và cắt khuôn mặt ra khỏi khung hình.
2. **Trích xuất đặc trưng (Embedding)**: Chuyển đổi bức ảnh khuôn mặt thành một mảng số học gồm 512 chiều (512-d vector). Mỗi người sẽ có một vector toán học đặc trưng gần như không đổi ở các góc độ khác nhau.
3. **So khớp (Cosine Similarity)**: Tính toán góc (độ lệch) giữa vector của người đang đứng trước camera với các vector đã lưu trong Database (`embeddings.pkl`). Nếu độ tương đồng (Similarity) lớn hơn ngưỡng (Threshold, ví dụ > 0.45), hệ thống sẽ kết luận là **MATCH** (Nhận diện thành công).

## 3. Những gì đã hoàn thành (Achieved)
- ✅ Xây dựng thành công `FaceEngine` tích hợp InsightFace.
- ✅ Chuyển đổi thành công sang mô hình `buffalo_sc` để chạy mượt mà trên CPU với tốc độ FPS cao, không cần bắt buộc cài đặt cấu hình GPU/CUDA phức tạp.
- ✅ Hoàn thiện kịch bản **Đăng ký (Register)**: Hướng dẫn người dùng xoay mặt 5 góc (thẳng, trái, phải, lên, xuống) thông qua UI trực quan trên Terminal.
- ✅ Hoàn thiện kịch bản **Xác minh (Verify 1:N)**: Nhận diện theo thời gian thực (Real-time), in ra Tên và tỷ lệ phần trăm khớp (Confidence Score).
- ✅ Quản lý hoàn toàn qua CLI (`main.py`) thống nhất.

## 4. Những điểm cần cải tiến (Future Improvements)
- 🚧 **Đánh giá và chốt Ngưỡng (Threshold)**: Cần thu thập tập dữ liệu lớn hơn để chạy kịch bản Đánh giá (Evaluate), từ đó tìm ra điểm EER (Equal Error Rate) nhằm chốt ngưỡng nhận diện chống nhận diện nhầm.
- 🚧 **Chống gian lận (Anti-spoofing)**: Hiện tại hệ thống có thể bị qua mặt nếu đưa ảnh điện thoại hoặc ảnh in giấy ra trước camera. Có thể cân nhắc thêm model Liveness Detection để phân biệt mặt thật/giả.
- 🚧 **Tối ưu CSDL**: Khi số lượng sinh viên lên đến hàng ngàn, việc đọc file `.pkl` để so khớp từng người sẽ chậm lại. Cần đưa embedding vào các CSDL vector chuyên dụng như Milvus hoặc FAISS.

