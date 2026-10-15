# TÀI LIỆU KỸ THUẬT: AI 2 — HỆ THỐNG PHÂN TÍCH TRẠNG THÁI & MỨC ĐỘ MỆT MỎI

## 1. Giới thiệu & Mục đích
- **Tên mô hình**: MediaPipe Face Mesh kết hợp với thuật toán Học máy Random Forest Classifier.
- **Mục đích**: Hoạt động độc lập để phân tích hình ảnh khuôn mặt qua camera và phân loại thành **3 cấp độ mệt mỏi** ngay tại thời điểm nhân viên quét chấm công (thời gian xử lý: 1–2 giây).
- **Đầu vào (Input)**: Một chuỗi khung hình liên tiếp (3 frames) trong khoảng thời gian quét 1–2 giây, lưu tạm thời trực tiếp trên RAM.
- **Đầu ra (Output)**: 3 nhãn phân loại thể trạng:
  1. `Normal` (Bình thường / Tỉnh táo)
  2. `Fatigue` (Mệt mỏi / Lờ đờ / Thiếu ngủ)
  3. `Exhausted` (Kiệt sức / Siêu mệt mỏi)
*(Ghi chú: Dữ liệu nhịp tim từ cảm biến MAX30102 sẽ được tích hợp kết hợp ở giai đoạn sau của hệ thống).*

---

## 2. Chi tiết Định nghĩa & Thiết kế 3 Nhãn Trạng Thái

| Nhãn (Code) | Tên hiển thị (Tiếng Việt) | Đặc điểm hình học (MediaPipe) | Trạng thái thực tế khi chấm công | Mức độ cảnh báo & Xử lý |
| :--- | :--- | :--- | :--- | :--- |
| **`Normal`** | **Bình thường / Tỉnh táo** | - **$EAR \ge 0.25$** (Độ mở mắt cao, ổn định)<br>- Trục đầu hướng thẳng ($\Delta Pitch, \Delta Roll$ thấp, không gật gù) | Nhân viên bước đến máy chấm công với thần thái tươi tỉnh, tràn đầy năng lượng, mắt mở to và nhìn thẳng vào camera. | ✅ **Trạng thái tốt**: Ghi nhận chấm công thành công, thể chất đạt chuẩn. |
| **`Fatigue`** | **Mệt mỏi / Lờ đờ / Thiếu ngủ** | - **$0.18 \le EAR < 0.25$** (Độ mở mắt giảm xuống mức thấp)<br>- Tốc độ chớp mắt chậm, mi mắt trĩu nặng | Có dấu hiệu thiếu ngủ, làm việc quá tải hoặc ca đêm. Vẫn nhìn vào camera nhưng mắt sụp xuống, lim dim, phản ứng chậm chạp. | ⚠️ **Cảnh báo Vàng**: Ghi nhận chấm công kèm cảnh báo để HR/Quản lý theo dõi sức khỏe nhân viên. |
| **`Exhausted`** | **Kiệt sức / Siêu mệt mỏi** | - **$EAR < 0.18$** (Độ mở mắt cực kỳ thấp)<br>- Mi mắt sụp sâu che gần hết tròng mắt, các điểm mốc co rúm lại | Đang trong tình trạng suy nhược, kiệt quỵ hoặc thức trắng đêm. Mắt gần như sụp hẳn, mặt đờ đẫn, không giữ được tập trung tối thiểu. | 🚨 **Cảnh báo Đỏ**: Lưu vết sức khỏe nguy cơ cao, cần can thiệp nghỉ ngơi hoặc hỗ trợ y tế. |

---

## 3. Kiến trúc & Quy trình Xử lý (1–2 giây trên RAM)

```
[Camera / ESP32-CAM]
        │
        ▼ (Thu nhận chuỗi 3 frames trong 1-2 giây)
 ┌────────────────────────────────────────────────────────┐
 │ BỘ ĐỆM RAM (In-Memory Buffer)                          │
 └────────────────────────────────────────────────────────┘
        │
        ▼ (Giai đoạn 1: MediaPipe Face Mesh - 468 landmarks)
 ┌────────────────────────────────────────────────────────┐
 │ TRÍCH XUẤT ĐẶC TRƯNG HÌNH HỌC                          │
 │  - Eye Aspect Ratio: min(EAR), mean(EAR)               │
 │  - Mouth Aspect Ratio: max(MAR), mean(MAR)             │
 │  - Head Pose (solvePnP): delta_Pitch, delta_Roll,...   │
 └────────────────────────────────────────────────────────┘
        │
        ▼ (Giai đoạn 2: Random Forest Inference < 5ms)
 ┌────────────────────────────────────────────────────────┐
 │ PHÂN LOẠI RANDOM FOREST CLASSIFIER                     │
 │  - Output: Normal | Fatigue | Exhausted                │
 └────────────────────────────────────────────────────────┘
        │
        ▼
 [Database / Backend Server: Ghi nhận trạng thái điểm danh]
```

### Các công thức đặc trưng hình học cốt lõi:
1. **Eye Aspect Ratio (EAR)**:
   $$EAR = \frac{||p_2 - p_6|| + ||p_3 - p_5||}{2 \times ||p_1 - p_4||}$$
   *Đo độ mở của mắt dựa trên khoảng cách giữa các điểm mốc mi trên và mi dưới so với chiều ngang mắt.*

2. **Mouth Aspect Ratio (MAR)**:
   $$MAR = \frac{||p_{top} - p_{bottom}||}{||p_{left} - p_{right}||}$$
   *Đo độ mở của khuôn miệng.*

3. **Head Pose Estimation (solvePnP)**:
   *Tính góc quay 3 chiều (Pitch - Cúi/Ngửa, Roll - Nghiêng, Yaw - Xoay) để xác định độ ổn định của trục đầu.*

4. **Vector đặc trưng chuỗi 3 frames**:
   $$\text{Feature Vector} = [\min(EAR), \text{mean}(EAR), \max(MAR), \text{mean}(MAR), \Delta\text{Pitch}, \Delta\text{Roll}, \text{mean}(\text{Pitch})]$$

---

## 4. Danh mục File triển khai

- **`src/status_features.py`**: Trích xuất tọa độ landmark MediaPipe, tính EAR, MAR, Head Pose (solvePnP).
- **`scripts/collect_status.py`**: Giao diện thu thập mẫu dữ liệu chuẩn 3 nhãn (`Normal`, `Fatigue`, `Exhausted`) với gợi ý thời gian thực.
- **`src/train_rf.py`**: Huấn luyện Random Forest với dữ liệu 3 nhãn từ file CSV, xuất mô hình `data/rf_status_model.pkl` và xếp hạng Feature Importances.
- **`src/predict_status.py`**: Module dự đoán trạng thái nâng cao:
  - Hỗ trợ **Streaming Buffer**: Trích xuất MediaPipe 1 lần duy nhất mỗi frame (giảm tải 3x CPU).
  - **Làm mịn nhãn (Temporal Smoothing)**: Khử hiện tượng nhảy nhãn tức thời khi chớp mắt sinh lý.
  - **Lọc góc quay mặt (Head Pose Filter)**: Phát hiện người dùng quay đầu ngoảnh mặt ($|Yaw| > 25^\circ$) để tránh nhận diện sai độ mở mắt.
- **`gui.py`**: Giao diện tích hợp đầy đủ các chức năng thu thập, huấn luyện và kiểm thử.

