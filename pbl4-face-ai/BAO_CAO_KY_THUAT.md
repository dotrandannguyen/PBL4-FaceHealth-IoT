# BÁO CÁO KỸ THUẬT TOÀN DIỆN ĐỒ ÁN PBL4
## HỆ THỐNG ĐIỂM DANH SINH VIÊN THÔNG MINH KẾT HỢP ĐÁNH GIÁ THỂ TRẠNG VÀ CẢM BIẾN SINH TRẮC HỌC IOT

---

## MỤC LỤC
1. [TỔNG QUAN HỆ THỐNG & ĐẶT VẤN ĐỀ](#1-tổng-quan-hệ-thống--đặt-vấn-đề)
2. [CHI TIẾT VỀ AI 1 — NHẬN DIỆN DANH TÍNH (FACE RECOGNITION)](#2-chi-tiết-về-ai-1--nhận-diện-danh-tính-face-recognition)
3. [CHI TIẾT VỀ AI 2 — ĐÁNH GIÁ THỂ TRẠNG MỆT MỎI (STATUS & FATIGUE DETECTION)](#3-chi-tiết-về-ai-2--đánh-giá-thể-trạng-mệt-mỏi-status--fatigue-detection)
4. [KIẾN TRÚC ĐA LUỒNG & STATE MACHINE (UNIFIED ENGINE)](#4-kiến-trúc-đa-luồng--state-machine-unified-engine)
5. [MA TRẬN HỢP NHẤT QUYẾT ĐỊNH (LATE FUSION MATRIX)](#5-ma-trận-hợp-nhất-quyết-định-late-fusion-matrix)
6. [GIAO THỨC TRUYỀN THÔNG VỚI THIẾT BỊ IOT (ESP32 + MAX30102)](#6-giao-thức-truyền-thông-với-thiết-bị-iot-esp32--max30102)
7. [TỔNG HỢP CÁC KẾT QUẢ ĐÃ TRIỂN KHAI & CÁC LỖI KỸ THUẬT ĐÃ GIẢI QUYẾT](#7-tổng-hợp-các-kết-quả-đã-triển-khai--các-lỗi-kỹ-thuật-đã-giải-quyết)
8. [HƯỚNG DẪN VẬN HÀNH & DEMO HỆ THỐNG](#8-hướng-dẫn-vận-hành--demo-hệ-thống)

---

## 1. TỔNG QUAN HỆ THỐNG & ĐẶT VẤN ĐỀ

Hầu hết các hệ thống điểm danh truyền thống chỉ dừng lại ở bài toán xác định **"Sinh viên đó là ai?"**. Trong môi trường học tập và lao động hiện đại, sức khỏe thể chất và mức độ tỉnh táo có ảnh hưởng quyết định đến chất lượng tiếp thu và an toàn.

Đồ án xây dựng một giải pháp **Chấm công Thông minh Hai Nhánh (Dual-modality Smart Attendance)** kết hợp:
1. **Thị giác Máy tính (Computer Vision AI)**: Vừa nhận diện khuôn mặt sinh viên (AI 1), vừa phân tích biểu cảm động học vi mô trên mắt, miệng và tư thế đầu để lượng hóa mức độ mệt mỏi (AI 2).
2. **Cảm biến Sinh trắc học Quang học (IoT PPG Sensor MAX30102)**: Đo lưu lượng máu qua mao mạch đầu ngón tay để lấy nhịp tim (Heart Rate - BPM) và độ bão hòa oxy trong máu ($\text{SpO}_2$).
3. **Bộ điều phối Hợp nhất (Late Fusion Engine)**: Ghép nối 2 nguồn dữ liệu độc lập để đưa ra kết luận toàn diện về cả **Danh tính** lẫn **Thể trạng sức khỏe**.

---

## 2. CHI TIẾT VỀ AI 1 — NHẬN DIỆN DANH TÍNH (FACE RECOGNITION)

*Mã nguồn thực thi: `src/face_engine.py`, `src/register.py`, `src/verify.py`*

### 2.1. Kiến trúc mô hình
AI 1 sử dụng framework **InsightFace** với backbone **`buffalo_sc`** (ONNX Runtime, dung lượng ~16MB). Đây là mô hình được lựa chọn nhằm tối ưu hóa tốc độ thực thi trên CPU tiêu chuẩn (đáp ứng thời gian suy luận ~80–120ms mà không đòi hỏi GPU rời).

### 2.2. Nguyên lý hoạt động (Quy trình 3 bước)
```
[Frame ảnh BGR] 
       │
       ▼ (Bước 1: SCRFD Detector)
[Phát hiện khuôn mặt + 5 Điểm mốc chuẩn (KPS)]
       │
       ▼ (Bước 2: Căn chỉnh hình học Similarity Transform & ArcFace Backbone)
[Vector Embedding 512 chiều (Đã chuẩn hóa L2 Norm)]
       │
       ▼ (Bước 3: So khớp Cosine Similarity với Database)
[Mã SV + Tên + Điểm khớp Sim]
```

1. **Phát hiện khuôn mặt (Face Detection - SCRFD)**:
   - Tìm kiếm vị trí khuôn mặt trong khung hình, trích xuất tọa độ Bounding Box $[x_1, y_1, x_2, y_2]$ và 5 điểm mốc quan trọng (2 mắt, đỉnh mũi, 2 mép môi).
   - Ngưỡng lọc độ tự tin: $\text{det\_score} \ge 0.5$.
2. **Trích xuất đặc trưng (ArcFace Embedding)**:
   - Khuôn mặt được cắt và căn chỉnh hình học (Face Alignment) về kích thước chuẩn $112 \times 112$.
   - Mạng nơ-ron tích chập (ArcFace) chiếu khuôn mặt vào không gian siêu cầu 512 chiều (512-dimensional hypersphere).
   - Vector được chuẩn hóa L2:
     $$\vec{v}_{norm} = \frac{\vec{v}}{||\vec{v}||_2} \quad \implies \quad ||\vec{v}_{norm}||_2 = 1$$
3. **So khớp độ tương đồng (Cosine Similarity)**:
   - Độ tương đồng giữa vector kiểm tra $\vec{u}$ và vector đã đăng ký $\vec{v}$ được tính toán bằng tích vô hướng:
     $$\text{Cosine Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{||\vec{u}||_2 \times ||\vec{v}||_2} = \vec{u} \cdot \vec{v}$$
   - Ngưỡng quyết định mặc định: **$\text{Threshold} = 0.45$**.
     - Nếu $\text{Sim} \ge 0.45 \rightarrow$ **MATCH** (Nhận diện thành công).
     - Nếu $\text{Sim} < 0.45 \rightarrow$ **NO MATCH** (Sinh viên lạ / Chưa đăng ký).

### 2.3. Quy trình Đăng ký Sinh viên (Enrollment)
- Người dùng được hướng dẫn xoay mặt theo 5 hướng: *Nhìn thẳng, Quay trái, Quay phải, Ngước lên, Cúi xuống*.
- Mỗi góc chụp lưu một vector đặc trưng. Vector đại diện cuối cùng của sinh viên được tính bằng trung bình cộng các vector thành phần:
  $$\vec{v}_{final} = \text{Normalize}\left(\frac{1}{N} \sum_{i=1}^N \vec{v}_i\right)$$
- Dữ liệu được lưu trữ trong CSDL nhị phân `data/embeddings.pkl` theo cấu trúc:
  ```python
  {
      "SV001": {"name": "Nguyen Van A", "embedding": np.ndarray (512,)},
      "SV002": {"name": "Dang Tien Thinh", "embedding": np.ndarray (512,)},
      ...
  }
  ```

---

## 3. CHI TIẾT VỀ AI 2 — ĐÁNH GIÁ THỂ TRẠNG MỆT MỎI (STATUS & FATIGUE DETECTION)

*Mã nguồn thực thi: `src/status_features.py`, `src/train_rf.py`, `src/predict_status.py`*

### 3.1. Kiến trúc mô hình
AI 2 kết hợp giữa **Thị giác Máy tính Hình học (Geometric Computer Vision)** và **Mô hình Học máy Cổ điển (Machine Learning)**:
- **Trích xuất đặc trưng**: **MediaPipe Face Mesh** (nhận diện 468 điểm mốc không gian 3D trên khuôn mặt).
- **Phân loại**: **Random Forest Classifier** (50 cây quyết định, lưu tại `data/rf_status_model.pkl`, tốc độ suy luận $< 5\text{ms}$).

### 3.2. Ba Nhãn Phân loại Thể trạng
Hệ thống lượng hóa thần thái và biểu cảm khuôn mặt thành 3 cấp độ rõ rệt:

| Nhãn (Label) | Tên tiếng Việt | Tiêu chuẩn hình học (MediaPipe) | Ý nghĩa thực tế |
| :---: | :---: | :--- | :--- |
| **`Normal`** | **Bình thường / Tỉnh táo** | - $\text{EAR} \ge 0.25$ (Độ mở mắt lớn, rõ ràng)<br>- $\Delta\text{Pitch}, \Delta\text{Roll}$ thấp (Đầu giữ thẳng) | Tươi tỉnh, tràn đầy năng lượng, mắt mở to và tập trung nhìn camera. |
| **`Fatigue`** | **Mệt mỏi / Lờ đờ** | - $0.18 \le \text{EAR} < 0.25$ (Độ mở mắt giảm thấp)<br>- Tốc độ chớp mắt chậm, mi mắt trĩu nặng | Có biểu hiện thiếu ngủ, làm việc quá tải; mắt lờ đờ, lim dim. |
| **`Exhausted`** | **Kiệt sức / Sụp mí** | - $\text{EAR} < 0.18$ (Mắt sụp sâu hoặc nhắm nghiền)<br>- $\Delta\text{Pitch}$ lớn (Có hiện tượng gật gù) | Đang trong tình trạng suy nhược hoặc ngủ gật tại chỗ, nguy hiểm. |

### 3.3. Các công thức toán học trích xuất đặc trưng
1. **Độ mở mắt (Eye Aspect Ratio - EAR)**:
   Được tính dựa trên khoảng cách giữa các điểm mốc mi trên và mi dưới so với độ rộng khóe mắt (tính trung bình cả 2 mắt):
   $$\text{EAR} = \frac{||p_2 - p_6|| + ||p_3 - p_5||}{2 \times ||p_1 - p_4||}$$
   *Trong đó: $p_1, p_4$ là khóe mắt trong/ngoài; $p_2, p_3, p_5, p_6$ là các cặp điểm đối xứng trên mi trên và mi dưới.*

2. **Độ mở miệng (Mouth Aspect Ratio - MAR)**:
   Nhận diện hành vi ngáp ngủ:
   $$\text{MAR} = \frac{||p_{top} - p_{bottom}||}{||p_{left} - p_{right}||}$$

3. **Ước lượng Tư thế Đầu (Head Pose Estimation qua solvePnP)**:
   - Sử dụng 6 điểm mốc 3D chuẩn trên mô hình khuôn mặt thực tế: Đỉnh mũi, cằm, khóe mắt trái/phải, mép môi trái/phải.
   - Giải bài toán hình học phối cảnh (Perspective-n-Point) bằng hàm `cv2.solvePnP` để tìm Rotation Vector.
   - Chuyển đổi qua ma trận quay Rodrigues và phân tích góc Euler:
     - $\text{Pitch}$: Góc cúi / ngửa đầu (phát hiện gục đầu ngủ gật).
     - $\text{Yaw}$: Góc quay mặt sang trái / phải (phát hiện ngoảnh mặt đi nơi khác).
     - $\text{Roll}$: Góc nghiêng đầu sang vai.

4. **Vector đặc trưng chuỗi 3 frames liên tiếp**:
   $$\vec{x} = [\min(\text{EAR}), \text{mean}(\text{EAR}), \max(\text{MAR}), \text{mean}(\text{MAR}), \Delta\text{Pitch}, \Delta\text{Roll}, \text{mean}(\text{Pitch})]$$
   - Vector 7 chiều này đóng gói trọn vẹn cả độ mở mắt nhỏ nhất (bắt chớp mắt chậm), độ ngáp lớn nhất và sự bất ổn định của trục đầu qua thời gian.

### 3.4. Các cơ chế tối ưu chống sai lệch (Noise Filtering)
- **Single-pass Frame Extraction**: Mỗi frame camera chỉ chạy qua MediaPipe đúng 1 lần duy nhất trên bộ đệm RAM để tiết kiệm tối đa CPU.
- **Head Pose Filter (Lọc góc nhìn)**: Khi người dùng quay mặt góc lớn ($|\text{Yaw}| > 25^\circ$), hình chiếu 2D của mắt sẽ bị hẹp lại theo góc nhìn khiến EAR sụt giảm giả tạo. Hệ thống sẽ gán trạng thái `Turned_Head` và tạm dừng ghi nhận nhãn mệt mỏi cho đến khi người dùng nhìn thẳng.
- **Temporal Smoothing (Làm mịn theo thời gian)**: Duy trì một deque 5 frame gần nhất để tính xác suất trung bình các nhãn. Điều này loại bỏ hoàn toàn hiện tượng "nhảy nhãn tức thời" khi người dùng chỉ chớp mắt sinh lý bình thường trong 100ms.

---

## 4. KIẾN TRÚC ĐA LUỒNG & STATE MACHINE (UNIFIED ENGINE)

*Mã nguồn thực thi: `unified_engine.py`*

### 4.1. Giải quyết bài toán nghẽn CPU (Concurrency Architecture)
- **Vấn đề**: Nếu chạy song song cả InsightFace (tốn ~100ms/frame) và MediaPipe (tốn ~30ms/frame) trên cùng một luồng tuần tự (Main Thread), tốc độ khung hình sẽ tụt xuống dưới 8–10 FPS, gây giật lag và làm đứt gãy chuỗi thời gian của AI 2.
- **Giải pháp**:
  - **Main Thread**: Chạy MediaPipe Face Mesh + Random Forest liên tục ở tốc độ cao (25–30 FPS).
  - **Worker Thread**: Sử dụng `ThreadPoolExecutor(max_workers=1)` chạy ngầm riêng biệt cho InsightFace. Main thread chỉ gửi bản copy của frame sang cho Worker khi Worker đang rảnh rỗi.

### 4.2. Vòng đời Máy trạng thái (State Machine Lifecycle)
Hệ thống vận hành theo 5 trạng thái tuần tự chặt chẽ:

```
[IDLE] ──(START_SESSION)──► [WARMUP (1.2s)] ──(Hết 1.2s)──► [SCANNING (2.3s)]
  ▲                               │                              │
  │                               ▼                              ▼
  │                        (Rút tay sớm)                  (Rút tay / Timeout)
  │                               │                              │
  │                               ▼                              ▼
  │                         [ABORTED (2.5s)] ◄───────────────────┘
  │                               │
  └───(Hết thời gian giữ màn)─────┴──────────◄ [COMPLETED (3.0s)] ◄──(DONE_SESSION)
```

1. **`IDLE` (Nghỉ)**:
   - CPU nghỉ (~0% AI). Camera chỉ hiển thị luồng video thô kèm hướng dẫn *"Đặt ngón tay lên cảm biến để bắt đầu chấm công"*. Không chạy MediaPipe hay InsightFace để tiết kiệm điện năng và nhiệt độ thiết bị.
2. **`WARMUP` (1.2 giây)**:
   - Kích hoạt khi nhận tín hiệu `START_SESSION`.
   - Giai đoạn loại bỏ nhiễu quang học ban đầu của cảm biến PPG và để sinh viên ổn định vị trí đứng. Bắt đầu bật MediaPipe để vẽ khung dẫn hướng nhưng chưa ghi nhận nhãn mệt mỏi.
3. **`SCANNING` (2.0s – 2.5 giây)**:
   - AI 2 tích lũy nhãn liên tục trên Main Thread vào `session_status_history`.
   - Main Thread đồng thời chọn lọc Frame tốt nhất dựa trên điểm chất lượng thích ứng (Adaptive Quality Score):
     $$\text{Quality Score} = (\text{Sharpness} + 1) \times \max\left(0.1, 1 - \frac{|\text{Yaw}|}{45^\circ}\right)$$
     *Trong đó: Sharpness được đo bằng phương sai toán tử Laplacian $\text{Var}(\Delta(\text{ROI}_{gray}))$ để chống nhòe chuyển động.*
   - Worker Thread chạy nhận diện khuôn mặt 1:N trong nền.
4. **`COMPLETED` (3.0 giây)**:
   - Kích hoạt khi nhận tín hiệu `DONE_SESSION` từ ESP32.
   - Chốt kết quả AI 2 bằng **Majority Voting** kèm quy tắc đặc biệt:
     > **Quy tắc An toàn 30% cho `Exhausted`**: Nếu số frame `Exhausted` chiếm $\ge 30\%$ tổng số frame hợp lệ trong phiên thì **ưu tiên chốt luôn là `Exhausted`** (ngăn chặn trường hợp sinh viên ngủ gật trong 1 giây rồi giật mình mở mắt ở cuối phiên bị Majority Voting lấn át thành `Normal`).
   - Kích hoạt bộ Ma trận Late Fusion, lưu snapshot vào `logs/snapshots/` và ghi 1 dòng log JSONL vào `logs/attendance_logs.jsonl`. Giữ thẻ kết quả trên màn hình trong 3 giây rồi quay về `IDLE`.
5. **`ABORTED` (2.5 giây)**:
   - Kích hoạt khi nhận `ABORT_SESSION` (người dùng rút tay sớm) hoặc khi phiên vượt quá **Hard Timeout = 7.0 giây** mà không nhận được tín hiệu kết thúc. Báo lỗi màu đỏ trên HUD rồi tự phục hồi về `IDLE`.

---

## 5. MA TRẬN HỢP NHẤT QUYẾT ĐỊNH (LATE FUSION MATRIX)

Late Fusion là tầng ra quyết định tối cao, kết hợp chéo giữa **Nhãn Thần thái Khuôn mặt (AI 2)** và **Chỉ số Sinh trắc học Tuần hoàn (MAX30102)**.

### 5.1. Phân loại Mức sinh trắc học (`bio_level`)
- **`Bio_Missing`**: Không đo được nhịp tim hoặc SpO2 ($\text{HR} \le 0$ hoặc $\text{SpO}_2 \le 0$).
- **`Bio_Danger`**: $\text{HR} > 115$ hoặc $\text{HR} < 50$ **HOẶC** $\text{SpO}_2 < 94\%$.
- **`Bio_Warning`**: ($100 < \text{HR} \le 115$ hoặc $50 \le \text{HR} < 60$) **HOẶC** ($94\% \le \text{SpO}_2 < 96\%$).
- **`Bio_Normal`**: $60 \le \text{HR} \le 100$ **VÀ** $\text{SpO}_2 \ge 96\%$.

### 5.2. Bảng Ma trận Quyết định (Xét duyệt theo thứ tự ưu tiên từ 1 đến 7)

| Thứ tự | Thể trạng mặt (AI 2) | Sinh trắc (`bio_level`) | Kết luận Hợp nhất (`final_status`) | Mức cảnh báo | Khuyến nghị & Diễn giải |
| :---: | :---: | :---: | :--- | :---: | :--- |
| **Ưu tiên 1** | Bất kỳ | **`Bio_Danger`** | **CẢNH BÁO Y TẾ (Medical Alert)** | 🔴 **RED** | Chỉ số tim mạch/SpO2 bất thường. Cần nghỉ ngơi kiểm tra y tế ngay! |
| **Ưu tiên 2** | **`Exhausted`** | Bất kỳ (`Normal`/`Warning`) | **KIỆT SỨC / NGỦ GẬT (Exhausted)** | 🔴 **RED** | Mắt nhắm nghiền hoặc gật gù nặng. Không đảm bảo an toàn học tập/làm việc. |
| **Ưu tiên 3** | **`Fatigue`** | **`Bio_Warning`** | **MỆT MỎI THỂ CHẤT (Physical Fatigue)** | 🟠 **ORANGE** | Có cả biểu hiện lờ đờ trên mặt lẫn nhịp tim/SpO2 suy giảm nhẹ. |
| **Ưu tiên 4** | **`Fatigue`** | **`Bio_Normal`** hoặc `Missing` | **BUỒN NGỦ / THIẾU NGỦ (Drowsy)** | 🟡 **YELLOW** | Chỉ số sinh tồn ổn định nhưng mắt/cơ mặt mỏi. Khuyến nghị rửa mặt tỉnh táo. |
| **Ưu tiên 5** | **`Normal`** | **`Bio_Warning`** | **TỈNH TÁO - TIM ĐẬP NHANH (Active/Stressed)** | 🟡 **YELLOW** | Khuôn mặt tỉnh táo nhưng nhịp tim hơi cao (có thể vừa leo cầu thang hoặc căng thẳng). |
| **Ưu tiên 6** | **`Normal`** | **`Bio_Normal`** hoặc `Missing` | **ĐẠT CHUẨN (Fit to Study/Work)** | 🟢 **GREEN** | Trạng thái tinh thần và thể chất hoàn toàn ổn định. |
| **Ưu tiên 7** | **`Unknown`** | Bất kỳ | **CHƯA RÕ MẶT** | 🟡 **YELLOW** | Camera không bắt đủ góc mặt chuẩn, chỉ ghi nhận chỉ số sinh trắc học. |

---

## 6. GIAO THỨC TRUYỀN THÔNG VỚI THIẾT BỊ IOT (ESP32 + MAX30102)

Dữ liệu truyền thông giữa bo mạch ESP32 và PC được chuẩn hóa qua **Serial USB (Baud rate: 115200 bps)** theo định dạng **JSON Lines (mỗi dòng là một object JSON)**:

1. **Khởi động phiên (`START_SESSION`)**:
   - Khi cảm biến phát hiện có ngón tay đặt lên (`irValue > 50000` liên tục trong 0.5s):
   ```json
   {"event": "START_SESSION", "ir": 68500, "timestamp": 1710000000}
   ```
2. **Hủy phiên giữa chừng (`ABORT_SESSION`)**:
   - Khi sinh viên rút tay ra sớm trước khi đo xong (`irValue < 50000`):
   ```json
   {"event": "ABORT_SESSION", "reason": "FINGER_REMOVED"}
   ```
3. **Hoàn tất đo sinh trắc (`DONE_SESSION`)**:
   - Sau 1.2s warm-up bỏ qua nhiễu tiếp xúc và 2.0s lấy mẫu ổn định, ESP32 tính **Trung vị (Median)** để triệt tiêu các mẫu đột biến do tay rung nhẹ, rồi gửi gói chốt:
   ```json
   {"event": "DONE_SESSION", "hr": 82, "spo2": 98, "ir_avg": 71200}
   ```

### Cấu trúc Output JSON chuẩn ghi log (`attendance_logs.jsonl`)
Mỗi phiên hoàn tất sẽ tự động tạo một bản ghi chuẩn hóa để sẵn sàng đồng bộ lên cơ sở dữ liệu SQL Server / REST API của hệ thống web [DoAn_ChamCong_AI](file:///d:/DTDN_DOC/HK5/PBL4/DoAn_ChamCong_AI):
```json
{
  "timestamp": "2026-10-15 18:44:50",
  "student_id": "SV001",
  "student_name": "Nguyen Van A",
  "face_confidence": 0.9003,
  "ai2_face_status": "Normal",
  "face_metrics": {
    "ear": 0.285,
    "mar": 0.038,
    "pitch": -2.1,
    "yaw": 1.4,
    "sharpness": 28.6
  },
  "iot_metrics": {
    "hr": 80,
    "spo2": 98,
    "bio_level": "Bio_Normal",
    "ir_avg": 69000
  },
  "fusion_result": {
    "final_status": "ĐẠT CHUẨN (Fit to Study/Work)",
    "alert_level": "GREEN",
    "recommendation": "Trạng thái tinh thần và thể chất hoàn toàn ổn định."
  },
  "snapshot_path": "logs/snapshots/SV001_20261015_184450.jpg"
}
```

---

## 7. TỔNG HỢP CÁC KẾT QUẢ ĐÃ TRIỂN KHAI & CÁC LỖI KỸ THUẬT ĐÃ GIẢI QUYẾT

### 7.1. Các tệp đã xây dựng và tích hợp
1. [unified_engine.py](file:///d:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/unified_engine.py): Module lõi tích hợp State Machine, đa luồng, lọc chất lượng ảnh và ma trận Late Fusion.
2. [demo_unified_iot.py](file:///d:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/demo_unified_iot.py): Giao diện HUD trực quan trên OpenCV với bộ phím giả lập phần cứng (Mock Triggers) và cổng Serial kết nối ESP32.
3. [ARCHITECTURE.md](file:///d:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/ARCHITECTURE.md): Tài liệu sơ đồ State Diagram & Sequence Diagram dạng Mermaid cùng ghi chú học thuật về cảm biến PPG.
4. [gui.py](file:///d:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/gui.py): Nâng cấp Dashboard Tkinter kết nối trực tiếp với module chấm công hợp nhất mới.

### 7.2. Các bài toán kỹ thuật thực tế đã phân tích & sửa triệt để
1. **Lỗi VS Code hiển thị gạch đỏ toàn bộ file (Pylance Import Error)**:
   - *Nguyên nhân*: Workspace mở ở thư mục gốc `PBL4`, Pylance không đọc được cấu hình `.vscode/settings.json` nằm trong thư mục con `pbl4-face-ai`.
   - *Khắc phục*: Tạo file [.vscode/settings.json](file:///d:/DTDN_DOC/HK5/PBL4/.vscode/settings.json) và [pyrightconfig.json](file:///d:/DTDN_DOC/HK5/PBL4/pyrightconfig.json) ở cấp thư mục gốc trỏ thẳng tới `.venv` và bổ sung `extraPaths`, đưa lỗi Pylance về **0 errors**.
2. **Lỗi AI 1 quét 10 lần liên tục không ra mặt (Báo "Unknown")**:
   - *Nguyên nhân*: Điều kiện lọc frame cũ đặt ngưỡng cứng `sharpness >= 45.0`. Trong khi webcam laptop trong phòng bình thường chỉ đo được độ nét Laplacian $\sim 20 - 30$ (thực tế ảnh đo được $25.1$). Điều này khiến **InsightFace không bao giờ được kích hoạt**, luồng Worker bị treo ở *"Scanning Identity..."*.
   - *Khắc phục*: Bỏ ngưỡng chặn cứng độ nét 45, kích hoạt Worker Thread chạy nền ngay khi mặt hướng thẳng ($\vert{}Yaw\vert{} \le 30^\circ, W_{face} \ge 50\text{px}$), đồng thời bổ sung cơ chế Fallback kiểm tra lại frame nét nhất ở cuối phiên. Ngay sau khi sửa, hệ thống nhận diện tức thì sinh viên với điểm khớp $\text{Sim} = 0.900$.

---

## 8. HƯỚNG DẪN VẬN HÀNH & DEMO HỆ THỐNG

### Cách 1: Chạy trực tiếp Giao diện Điểm danh Thông minh (OpenCV HUD)
```powershell
cd d:\DTDN_DOC\HK5\PBL4\pbl4-face-ai
.\.venv\Scripts\python demo_unified_iot.py
```
*(Nếu có ESP32 cắm cổng COM: `.\.venv\Scripts\python demo_unified_iot.py --serial-port COM3`)*

* **Phím `SPACE` hoặc `1`**: Kích hoạt phiên chấm công thực tế (AI 1 nhận diện bạn là ai, AI 2 đo cử động mắt/miệng thật của bạn, giả lập nhịp tim bình thường 75–85 BPM).
* **Phím `2`**: Giả lập nhịp tim cảnh báo (HR 104–110 BPM, SpO2 95%) — Thử nheo mắt lờ đờ để thấy Thẻ Cam `MỆT MỎI THỂ CHẤT`.
* **Phím `3`**: Giả lập nhịp tim nguy cơ (HR 125 BPM, SpO2 91%) $\rightarrow$ Kích hoạt Thẻ Đỏ `CẢNH BÁO Y TẾ`.
* **Phím `a`**: Giả lập hành vi rút tay sớm $\rightarrow$ Kích hoạt `ABORT_SESSION`.
* **Phím `t`**: Kiểm thử ngắt an toàn Hard Timeout (7 giây).
* **Phím `q`**: Thoát chương trình.

### Cách 2: Mở Bảng điều khiển Quản lý & Đăng ký Sinh viên mới (Tkinter GUI)
```powershell
cd d:\DTDN_DOC\HK5\PBL4\pbl4-face-ai
.\.venv\Scripts\python gui.py
```
- Nhập Mã SV và Tên $\rightarrow$ Bấm nút **"📸 Bắt đầu Đăng ký Webcam"** để đăng ký khuôn mặt mới vào database.
- Bấm nút **"✅ Mở Webcam Chấm công"** để tự động chuyển sang luồng chấm công hợp nhất AI 1 + AI 2 + IoT.
