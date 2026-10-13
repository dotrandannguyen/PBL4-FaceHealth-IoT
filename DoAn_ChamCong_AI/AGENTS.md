# AGENTS.md — DoAn_ChamCong_AI

## 1. Project overview

Project chính: `DoAn_ChamCong_AI`

Repository:
`https://github.com/vietthang021106-glitch/DoAn_ChamCong_AI`

Mục tiêu là xây dựng hệ thống chấm công nhân viên gồm:

- Đăng nhập và phân quyền Admin / Nhân viên.
- Quản lý nhân viên và ca làm việc.
- Chấm công vào / ra.
- Nhận diện khuôn mặt bằng AI.
- Lưu ảnh bằng chứng lúc check-in / check-out.
- Theo dõi sức khỏe: nhịp tim, SpO2.
- Camera AI và cảnh báo trạng thái.
- Hỗ trợ dữ liệu từ ESP32 / ESP32-CAM.

AI nhận diện danh tính là chức năng chính.

AI phân tích trạng thái khuôn mặt hiện vẫn đang được xem xét lại, chưa coi là thiết kế cuối cùng.

> GitHub `main` gần nhất đã kiểm tra: commit `279722b` — `feat: redesign dashboard with collapsible sidebar navigation`.
> Local workspace có thể mới hơn GitHub. Luôn chạy `git status` và đọc code local trước khi sửa.

---

## 2. Tech stack

### Backend
- Python 3.12.x
- Flask
- PyODBC
- SQL Server
- REST API

### AI / Computer Vision
- OpenCV
- InsightFace
- ArcFace pretrained qua InsightFace
- Model face hiện tại: `buffalo_l`
- ONNX Runtime CPU
- MediaPipe FaceMesh

### Frontend
- HTML
- CSS
- JavaScript thuần
- Chart.js
- Flask Jinja templates

### Hardware / IoT
- Webcam hoặc ESP32-CAM
- ESP32
- MAX30102: nhịp tim + SpO2

---

## 3. Source structure quan trọng

```text
DoAn_ChamCong_AI/
│
├── app.py
├── services.py
├── database.py
├── ai_engine.py
├── face_engine.py
├── init_db.sql
│
├── templates/
│   ├── index.html
│   ├── employees.html
│   ├── me.html
│   └── login.html
│
├── static/
│   ├── css/app.css
│   └── js/ui.js
│
├── test_api.py
├── test_enrollment.py
├── test_flow.py
├── test_image_flow.py
├── seed_accounts.py
└── update_db.py
```

Vai trò:

- `app.py`: Flask routes, auth, camera singleton, HTTP API.
- `services.py`: business logic.
- `database.py`: toàn bộ truy vấn SQL Server.
- `face_engine.py`: InsightFace + ArcFace, hiện chủ yếu phục vụ enrollment.
- `ai_engine.py`: MediaPipe, EAR, head tilt, cảnh báo trạng thái.
- `index.html`: Dashboard Admin dạng SPA sections.
- `employees.html`: giao diện quản lý nhân viên cũ/riêng.
- `me.html`: trang dành cho nhân viên.
- `test_api.py`: hiện chủ yếu test auth/RBAC, không còn coi là ESP32 simulator chính.

Không dùng `flask_out.txt` như source of truth.

---

## 4. Database

Database:

```text
DoAn_ChamCong_AI
```

### Bảng chính

#### VaiTro
```text
MaVaiTro PK
TenVaiTro
```

#### NhanVien
```text
MaNV PK
HoTen
AnhKhuonMat
MaVaiTro FK -> VaiTro
```

#### TaiKhoan
```text
MaTK PK
MaNV FK -> NhanVien
TenDangNhap UNIQUE
MatKhau
```

#### ThietBi
```text
MaTB PK
LoaiTB
TrangThai
```

#### CaLamViec
```text
MaCa PK
TenCa
GioBatDau
GioKetThuc
```

Ca mặc định hiện tại:

```text
Ca hành chính: 08:00 - 17:00
```

#### PhanCaNhanVien
```text
MaPhanCa PK
MaNV FK -> NhanVien
MaCa FK -> CaLamViec
NgayLamViec
UNIQUE(MaNV, NgayLamViec)
```

#### ChamCong
```text
MaCC PK
MaNV FK -> NhanVien
GioVao
GioRa
MaTB FK -> ThietBi
MaCa FK -> CaLamViec
AnhVao VARBINARY(MAX)
AnhRa VARBINARY(MAX)
```

`AnhVao` và `AnhRa` lưu ảnh JPEG thực tế tại thời điểm chấm công.

#### FaceEmbedding
```text
MaEmbedding PK
MaNV FK -> NhanVien
VectorData VARBINARY(MAX)
SoChieu DEFAULT 512
ThoiGianTao
```

Mỗi nhân viên có thể có nhiều embedding.

#### LichSuSucKhoe
```text
MaSK PK
MaNV FK
NhipTim
SpO2
ThoiGian
```

#### DanhMucBieuHien
Hiện có các giá trị lịch sử:

```text
binh_thuong
buon_ngu
guc_dau
meo_mieng
```

Không tự coi mapping này là thiết kế AI2 cuối cùng.

#### LichSuTrangThai
```text
MaTT PK
MaNV FK
MaBieuHien FK
ThoiGian
```

#### LoaiCanhBao
Các nhóm hiện có:
- trạng thái AI
- sức khỏe

#### CanhBao
```text
MaCB PK
MaNV FK
MaLoaiCB FK
NoiDung
ThoiGian
MaTT FK nullable
MaTB FK nullable
```

### Schema drift cần chú ý

`database.py` đang sử dụng:

```text
FaceEmbedding
ChamCong.AnhVao
ChamCong.AnhRa
```

nhưng `init_db.sql` trên GitHub hiện chưa định nghĩa đầy đủ các phần này.

Không tự sửa schema ngay khi chưa phân tích ảnh hưởng, nhưng đây là điểm cần đồng bộ để project có thể setup lại từ đầu.

---

## 5. Routes / API hiện có

### Page/Auth

```text
GET  /login
POST /api/login
POST /api/logout
GET  /logout

GET /
GET /employees
GET /me
```

`/` yêu cầu Admin.

`/me` dành cho user đã đăng nhập.

### Camera

```text
GET /video_feed
```

MJPEG stream từ camera singleton.

### ESP32 / sensor

```text
POST /api/sensor
```

Body:

```json
{
  "MaNV": 1,
  "NhipTim": 80,
  "SpO2": 98
}
```

### Chấm công

```text
POST /api/chamcong
```

Body:

```json
{
  "MaNV": 1,
  "MaTB": 1
}
```

### Ảnh bằng chứng

```text
GET /api/attendance/<MaCC>/image/in
GET /api/attendance/<MaCC>/image/out
```

### Dashboard / thống kê

```text
GET /api/get_chamcong
GET /api/get_chamcong_today
GET /api/get_chamcong_weekly

GET /api/dashboard/attendance
GET /api/dashboard/attendance?date=YYYY-MM-DD

GET /api/attendance/today
```

### Health

```text
GET /api/get_health
GET /api/chart/health

```

### Shift

```text
GET  /api/shifts
POST /api/assign_shift
```

### AI / Alerts

```text
GET /api/get_alerts
GET /api/ai_status
```

### Roles / Employees

```text
GET  /api/roles

GET  /api/employees
GET  /api/employees/<MaNV>
POST /api/employees
PUT  /api/employees/<MaNV>
```

Hiện chưa có DELETE employee API hoàn chỉnh.

### Face enrollment

```text
POST /api/employees/<MaNV>/face/register
```

Thu 5 frame từ camera singleton và lưu 5 embedding.

### Employee self-service

```text
GET /api/me/profile
GET /api/me/today
GET /api/me/attendance
GET /api/me/health
GET /api/me/alerts
```

---

## 6. Luồng chấm công

Business flow hiện tại:

```text
MaNV
 ↓
Tìm ca làm việc hôm nay
 ↓
Không có ca
→ "Nhân viên chưa được phân ca hôm nay"

Có ca
 ↓
Tìm ChamCong hôm nay
 ↓
Không có record
→ CHECK-IN
→ GioVao = current time
→ lưu AnhVao nếu capture được

Đã có GioVao, GioRa = NULL
→ CHECK-OUT
→ GioRa = current time
→ lưu AnhRa nếu capture được

Đã có GioVao + GioRa
→ COMPLETED
→ không tạo lần chấm thứ 3
```

Quy tắc trạng thái:

```text
GioVao <= GioBatDau → Đúng giờ
GioVao >  GioBatDau → Đi trễ

GioRa <  GioKetThuc → Về sớm
GioRa >= GioKetThuc → Đúng giờ
GioRa = NULL         → Đang làm việc
```

Không có grace period.

Không tính overtime status.

Ca qua đêm hiện chưa phải scope chính.

Ảnh bằng chứng phải là frame lúc chấm công thành công, không ghi đè ảnh enrollment.

---

## 7. Camera + Face Recognition + AI trạng thái

### Camera

Camera được quản lý duy nhất trong `app.py`.

```python
cv2.VideoCapture(0)
640x480
CAP_PROP_FPS = 30
```

Đây là FPS yêu cầu camera, không đảm bảo inference AI chạy đủ 30 FPS.

Không được tạo thêm `VideoCapture(0)` ở module khác.

Luồng mong muốn:

```text
Camera / ESP32-CAM
        ↓
    Frame source
      ↙       ↘
Face AI       State/Sensor AI
      ↓
    Flask + DB
```

### Face enrollment — đã có

`face_engine.py`:

```text
InsightFace
buffalo_l
CPUExecutionProvider
det_size = 640x640
```

Flow:

```text
Frame
→ InsightFace detect face
→ ArcFace pretrained
→ normed embedding 512D float32
→ VectorData bytes
→ FaceEmbedding
```

Endpoint enrollment thu 5 frame.

Hiện `face_engine.py` yêu cầu mỗi frame enrollment có đúng 1 khuôn mặt.

Đã từng test thật với `MaNV=1`:

```text
5/5 frame hợp lệ
embedding 512 chiều
2048 bytes/vector
L2 norm ≈ 1.0
```

### Face recognition — chưa hoàn thiện

`database.py` đã có:

```python
get_all_face_embeddings()
```

nhưng code hiện tại chưa có pipeline recognition hoàn chỉnh/endpoint chính thức trong `app.py`.

Thiết kế dự kiến khi làm Phase 2:

```text
Frame mới
→ ArcFace 512D
→ cosine similarity
→ so với embeddings đã lưu
→ lấy best score
→ best >= threshold → MaNV
→ best < threshold  → UNKNOWN
```

Không hardcode threshold khi chưa test dữ liệu thực tế.

### AI trạng thái hiện tại trong main project

`ai_engine.py` hiện dùng rule-based MediaPipe:

```text
EAR_THRESHOLD = 0.25
EAR_CONSEC_FRAMES = 20
HEAD_TILT_THRESHOLD = 30°
ALERT_COOLDOWN = 30s
STATE_LOG_INTERVAL = 5s
```

Hiện có:

```text
binh_thuong
buon_ngu
guc_dau
khong_co_khuon_mat
```

Check-in thành công:

```text
set_active_employee(MaNV)
```

Check-out:

```text
clear_active_employee()
```

AI vẫn có thể phân tích frame khi chưa có active employee nhưng không được ghi cảnh báo sai người.

### Trạng thái AI2 hiện tại: CHƯA CHỐT

Có repo AI thử nghiệm riêng:

```text
https://github.com/dotrandannguyen/PBL4-FaceHealth-IoT.git
```

AI2 thử nghiệm ở repo đó dùng:

```text
MediaPipe
→ EAR / MAR / Head Pose
→ 3 frame liên tiếp
→ Random Forest
→ Normal / Drowsy / Yawn / Head-down
```

Thiết kế 3 frame này đã được đánh giá là quá ngắn để kết luận trạng thái.

Không tự merge AI2 experimental vào project chính.

Nếu tiếp tục AI trạng thái khuôn mặt thì hướng mới phải ưu tiên:

```text
phát hiện event
→ theo dõi thời lượng + số lần lặp
→ temporal window dài hơn
→ mới kết luận
```

Ngoài ra đang cân nhắc hướng AI2 khác:

```text
Heart Rate + SpO2
→ theo dõi chuỗi thời gian
→ phát hiện bất thường
```

Chưa có quyết định cuối cùng. Không tự triển khai hướng mới nếu user chưa yêu cầu.

---

## 8. ESP32 / API giả lập

Các endpoint hướng tới ESP32:

```text
POST /api/sensor
POST /api/chamcong
```

ESP32-CAM dự kiến gửi hình/frame qua Wi-Fi, còn inference nặng thực hiện trên PC/server.

MAX30102 dùng cho:

```text
NhipTim
SpO2
```

Không coi MAX30102 là cảm biến đo huyết áp trực tiếp.

Nếu sau này dùng AI ước lượng huyết áp thì phải gọi là "ước lượng", không phải đo y tế chính xác.

`test_api.py` hiện tại kiểm tra login/RBAC API, không nên mặc định xem nó là simulator ESP32.

---

## 9. UI đã chốt

### Admin

Thiết kế mới nhất:

```text
[ Sidebar trái ] [ Nội dung chính full phần còn lại ]
```

Phong cách giống ChatGPT desktop:

- sidebar bên trái
- sidebar có thể thu gọn / mở rộng
- bấm menu thì thay toàn bộ content bên phải
- không popup để điều hướng chức năng
- không right drawer
- không mở page mới nếu chức năng có thể nằm trong dashboard
- section active rõ ràng

Menu:

```text
Tổng quan
Nhân viên
Chấm công
Thống kê
Camera AI
Cảnh báo
Sức khỏe
```

Style:

- sáng
- sạch
- minimal
- enterprise
- nhiều khoảng trắng
- không gradient
- không neon
- icon SVG đơn giản
- responsive

### Admin — Nhân viên

Yêu cầu mới nhất:

Bấm `Nhân viên` một lần phải hiện ngay toàn bộ chức năng trong vùng content bên phải.

Không được:

```text
Nhân viên
→ màn hình trung gian
→ "Mở trang Nhân viên"
→ /employees
```

Repo GitHub hiện vẫn còn màn hình trung gian này, cần sửa.

Nhân viên cần:

```text
- danh sách nhân viên
- tìm theo HoTen / MaNV
- thêm
- sửa
- trạng thái đăng ký khuôn mặt
- đăng ký khuôn mặt
```

Ngoài ra cần tra cứu chấm công của từng nhân viên:

```text
chọn nhân viên
+ chọn ngày
→ GioVao
→ GioRa
→ Ca làm việc
→ trạng thái vào
→ trạng thái ra
→ ảnh bằng chứng nếu có
```

Mặc định ngày hôm nay và có nút `Hôm nay`.

### Admin — Chấm công

Đã chốt:

```text
[Tìm tên / MaNV] [Chọn ngày] [Hôm nay]
```

Khi đổi ngày:

- bảng đổi dữ liệu
- KPI đổi theo ngày
- ca lấy đúng `PhanCaNhanVien.NgayLamViec`
- không tự nhảy lại hôm nay khi auto-refresh
- search không thay đổi KPI tổng

### Admin personal page

Admin không cần dùng `Trang cá nhân` như nhân viên.

Nếu UI Admin vẫn hiện link `/me` trong user menu thì coi là điểm cần xem lại.

### Employee

Trang `/me` dành cho nhân viên.

Hiện có:

- profile
- trạng thái chấm công hôm nay
- lịch sử chấm công
- sức khỏe
- cảnh báo

Không expose chức năng quản trị Admin.

---

## 10. Những phần đã hoàn thành

- Flask app + SQL Server connection.
- Login/logout.
- Session auth.
- Admin/Employee RBAC.
- Quản lý role.
- Employee GET/POST/PUT APIs.
- Ca làm việc.
- Phân ca nhân viên theo ngày.
- Flow check-in/check-out/completed.
- Logic đúng giờ / đi trễ / về sớm.
- Camera singleton.
- `/video_feed`.
- Lưu ảnh `AnhVao` / `AnhRa`.
- API xem ảnh bằng chứng.
- Dashboard attendance theo ngày.
- Search nhân viên + date filter trong khu vực chấm công.
- Health API.
- Alerts API.
- Employee self-service APIs.
- Sidebar Admin mới dạng collapsible left sidebar.
- FaceEmbedding DB access methods.
- InsightFace enrollment.
- Thu 5 embedding cho một nhân viên.
- Real webcam enrollment đã test thành công.
- MediaPipe EAR/head-tilt engine hiện có.
- Background state/alert DB write để tránh block camera.

---

## 11. Lỗi / phần dang dở

### UI

1. Section `Nhân viên` trong `index.html` vẫn chỉ có nút:
   `Mở trang Nhân viên`.

   Phải đưa full employee management vào section ngay.

2. Chưa có tra cứu chấm công theo ngày ngay trong section Nhân viên.

3. Face registration modal trong `employees.html` hiện chủ yếu là placeholder; chưa thấy UI gọi đầy đủ endpoint registration.

4. Text UI nói CRUD nhưng DELETE employee API chưa có.

5. Admin user menu vẫn có thể còn link `Trang cá nhân`, trong khi requirement mới là Admin không cần flow này.

### Face AI

1. Enrollment đã có nhưng recognition Phase 2 chưa hoàn thiện.

2. `get_all_face_embeddings()` đã có nhưng chưa có matching flow chính thức.

3. Chưa calibration threshold bằng dữ liệu genuine/impostor thật.

4. Chưa có liveness / anti-spoofing.

5. Không được nói hệ thống "train ArcFace".
   ArcFace đang là pretrained model dùng để extract embedding.

### AI trạng thái

1. `ai_engine.py` hiện chỉ rule EAR + head tilt, còn đơn giản.

2. Có `_DummyDetector` fallback khi MediaPipe init lỗi.
   Nó giúp Flask sống nhưng có thể che mất lỗi AI thực tế.
   Không coi fallback là AI hoạt động bình thường.

3. AI2 Random Forest 3-frame từ repo thử nghiệm chưa phù hợp để tích hợp.

4. Nhãn `Drowsy` không được kết luận quá chắc chỉ từ vài frame.

5. Thiết kế AI2 cuối cùng đang chờ quyết định.

### Database

`init_db.sql` chưa đồng bộ hoàn toàn với DB/code đang sử dụng:

```text
FaceEmbedding
ChamCong.AnhVao
ChamCong.AnhRa
```

Cần xử lý schema drift cẩn thận, không tự DROP/reset DB.

---

## 12. Task ưu tiên tiếp theo

Ưu tiên theo thứ tự hiện tại:

### P0 — Đọc trạng thái local trước

```bash
git status
git diff
git branch
```

Không giả định GitHub là mới nhất nếu local có thay đổi.

### P1 — Hoàn thiện Admin UI Nhân viên

- bỏ màn hình trung gian
- click Nhân viên → full content ngay
- reuse code hiện có, tránh duplicate
- giữ search theo tên/MaNV
- thêm tra cứu attendance theo ngày cho nhân viên
- không redirect `/employees` khi không cần

### P2 — Wire face enrollment vào UI

- gọi endpoint hiện tại
- hiển thị progress/result/error rõ ràng
- dùng camera singleton
- không tạo camera khác

### P3 — Đồng bộ schema bootstrap

Phân tích trước khi sửa `init_db.sql`.

Mục tiêu cuối là database mới tạo từ script phải có đủ:

```text
FaceEmbedding
AnhVao
AnhRa
```

Không làm mất dữ liệu DB hiện tại.

### P4 — Hoàn thiện face recognition

Sau khi user yêu cầu tiếp tục Phase 2:

```text
frame
→ embedding
→ get_all_face_embeddings()
→ cosine similarity
→ best employee
→ threshold
→ MaNV / UNKNOWN
```

Sau đó mới nối recognition vào attendance.

### P5 — AI2

Không tự triển khai AI2 mới ngay.

Trước tiên phải chốt một trong hai hướng:

```text
A. MediaPipe + temporal fatigue/state monitoring
B. AI trên chuỗi NhipTim + SpO2 để phát hiện bất thường
```

Không dùng lại thiết kế `3 frame → Drowsy` như giải pháp cuối.

### P6 — ESP32

Sau khi software flow ổn định mới tích hợp hardware sâu hơn.

---

## 13. Coding rules cho Codex

1. Đọc code hiện tại trước khi sửa.
2. Luôn chạy `git status` và xem diff trước thay đổi.
3. Local workspace mới hơn GitHub thì ưu tiên local.
4. Không tự thay database schema nếu chưa cần.
5. Không DROP/reset database.
6. Không chạy seed làm ghi đè dữ liệu nếu chưa được yêu cầu.
7. Không tự thay public API hoặc response format đang dùng.
8. Giữ backward compatibility khi có thể.
9. Không tạo thêm `cv2.VideoCapture(0)` nếu camera singleton đã tồn tại.
10. Camera phải có một owner/source duy nhất.
11. Lỗi camera/AI không được làm toàn Flask server chết nếu có thể cô lập lỗi.
12. Không fake AI hoặc fake test result.
13. Không coi fallback AI là test PASS.
14. Không hardcode MaNV cho AI.
15. Dùng parameterized SQL query.
16. Không ghép binary/date/user input trực tiếp vào SQL.
17. Không tự commit.
18. Không tự push.
19. Chỉ commit/push khi user yêu cầu rõ.
20. Không tự tạo branch nếu chưa được yêu cầu.
21. Trước refactor lớn phải báo:
    - file bị ảnh hưởng
    - API bị ảnh hưởng
    - DB bị ảnh hưởng
    - camera/AI bị ảnh hưởng
22. Ưu tiên sửa tối thiểu đúng nguyên nhân thay vì rewrite toàn project.
23. Không redesign UI ngoài scope.
24. Không quay lại right-drawer/modal navigation; UI mới nhất là left sidebar + full main content.
25. Không duplicate DOM IDs khi reuse UI.
26. Không copy-paste nguyên `employees.html` vào `index.html` nếu có thể tách partial/component.
27. Sau khi sửa Python phải ít nhất chạy:

```bash
python -m py_compile app.py
python -m py_compile services.py
python -m py_compile database.py
```

Nếu sửa AI thì compile/test thêm file AI tương ứng.

28. Sau thay đổi backend phải test endpoint liên quan.
29. Sau thay đổi UI phải mở Flask và kiểm tra trực tiếp browser.
30. Kiểm tra Console browser nếu sửa JS/UI.
31. Test happy path và error path.
32. Không nói "đã chạy thành công" nếu chưa thực sự chạy.
33. Nếu gặp lỗi thật, giữ nguyên traceback và tìm root cause trước.
34. Sau task báo ngắn:
    - file đã sửa
    - nguyên nhân
    - cách sửa
    - test đã chạy
    - PASS/FAIL
    - phần còn tồn tại
35. Không commit/push sau khi hoàn thành trừ khi user yêu cầu.

---

## Nguyên tắc kiến trúc cần giữ

```text
app.py
   ↓
services.py
   ↓
database.py
```

Không nhét SQL trực tiếp vào frontend.

Camera:

```text
Camera singleton
      ↓
 shared frame
  ↙        ↘
AI       video stream
```

Face AI:

```text
InsightFace pretrained
→ ArcFace embedding 512D
→ similarity
→ identity
```

Không mô tả là tự train ArcFace.

Attendance:

```text
identity
→ attendance business rule
→ evidence image
→ DB
```

State/health AI không được tự quyết định danh tính hoặc trực tiếp thay đổi attendance rule nếu chưa có requirement rõ ràng.
