# Chạy PBL4 trên Windows — cập nhật 20/10/2026

Từ thư mục gốc `PBL4`. Web dùng PHP 8.2/MariaDB 10.11 trong Docker; AI dùng Python 3.12 x64 trên Windows. Webcam laptop/USB index 0, backend DirectShow đã đọc được JPEG 640×480; PHP trong container cũng đã nhận ảnh qua AI.

## Dùng ngay trên máy hiện tại

1. Giữ Docker Desktop và các container `pbl4_web`, `pbl4_mariadb` chạy.
2. Nhấp đúp `KHOI_DONG_PBL4.cmd` tại gốc dự án. File này bật AI/upload nếu chưa chạy rồi mở <http://localhost:8080>. Nó không chạy migration, reset DB hoặc train model.
3. Đăng nhập bằng tài khoản hiện có, mở quản lý nhân viên và đăng ký khuôn mặt. Hồ sơ nhân viên phải tồn tại trước; chụp đủ năm hướng theo giao diện.

Dịch vụ đã được khởi động trong phiên ngày 20/10. Không cần bật thêm bản AI thứ hai. `tools/start_services.ps1` nhận diện dịch vụ đang chạy; log và PID nằm trong `.pbl4-run/`. Dừng các Python process do script sở hữu bằng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/stop_services.ps1
```

Script dừng kiểm tra PID, thời điểm khởi động và đường dẫn Python; không dừng container Web/DB.

**Trạng thái thực tế:** nhận diện InsightFace và MediaPipe đã chạy trên ảnh có sẵn; webcam và relay PHP đã kiểm tra thật. Chấm công HTTP và enrollment đã qua kiểm thử trên DB tạm. Chưa nghiệm thu một phiên chấm công người thật đầy đủ với model RF v2 và cảm biến thật. Không đánh đồng các kiểm tra này với độ chính xác nhận diện hoặc trạng thái sức khỏe.

## Cài môi trường trên máy mới

Cài Python 3.12 x64 và Docker Desktop. Không sao chép virtualenv từ máy khác. Venv cũ `.venv` trên máy hiện tại trỏ interpreter thiếu; venv mới `.venv-pbl4` đã chạy được.

```powershell
py -3.12 -m venv pbl4-face-ai/.venv-pbl4
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -m pip install -r pbl4-face-ai/requirements-lock-win-py312.txt
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -m pip check
```

`requirements-runtime.txt` ghi các dependency trực tiếp; `requirements-lock-win-py312.txt` là toàn bộ phiên bản đã cài và kiểm tra trên Windows/Python 3.12 ngày 20/10. Có cả `opencv-python` và `opencv-contrib-python` cùng build 4.11.0.86 do yêu cầu upstream của InsightFace/MediaPipe. NumPy 1.26.4, MediaPipe 0.10.21, InsightFace 2.0, ONNX Runtime 1.22.1 và scikit-learn 1.7.2 đã import/chạy thật trong cấu hình này. Lock này không phải môi trường GPU hoặc Linux đã nghiệm thu.

InsightFace dùng `buffalo_sc`, CPU, embedding 512 chiều. Model đã cache tại `%USERPROFILE%/.insightface/models/buffalo_sc`; máy mới cần tải model trong lần đầu. Phiên bản package không thay thế điều kiện cấp phép của model. Nguồn package: [InsightFace](https://pypi.org/project/insightface/2.0/), [MediaPipe](https://pypi.org/project/mediapipe/0.10.21/).

## Cấu hình và database

Chỉ với máy mới: sao chép `.env.example` thành `.env`, đặt mật khẩu DB và hai token ngẫu nhiên riêng biệt. Với DB hiện có, giữ đúng credential đang sử dụng. `.env`, ảnh, model, outbox và bản sao lưu được ignore Git; không đưa chúng vào báo cáo hoặc commit.

- `PBL4_INTERNAL_TOKEN`: dùng chung giữa PHP và AI; Compose cần nạp lại Web nếu token thay đổi.
- `PBL4_UPLOAD_TOKEN`: token riêng cho ESP32 upload, không dùng token nội bộ Web–AI.
- `AI_BIND_HOST=0.0.0.0`: cần cho Web trong Docker gọi host; các route nội bộ yêu cầu Bearer.
- `PBL4_CAMERA_MODE=relay`: desktop đọc camera do AI service sở hữu.
- `PBL4_CAMERA_ID=0`, `PBL4_CAMERA_BACKEND=dshow`: webcam đã kiểm chứng trên máy này; `msmf`/`auto` là lựa chọn khi đổi thiết bị.
- `PBL4_DEVICE_ID=1`: phải là thiết bị tồn tại trên Web.

Khởi tạo **DB mới**:

```powershell
docker compose config --quiet
docker compose up -d --build
```

Schema mới đã có bảng chống lặp `AttendanceEvent` và các cột trạng thái. Seed chỉ tạo danh mục/thiết bị/ca, **không tạo tài khoản với mật khẩu mặc định**. Với DB mới, đặt `PBL4_BOOTSTRAP_ADMIN`, `PBL4_BOOTSTRAP_PASSWORD` (12–72 bytes), tùy chọn `PBL4_BOOTSTRAP_NAME` trong môi trường PowerShell, rồi:

```powershell
docker compose exec -e PBL4_BOOTSTRAP_ADMIN -e PBL4_BOOTSTRAP_PASSWORD -e PBL4_BOOTSTRAP_NAME web php tools/create_admin.php
Remove-Item Env:PBL4_BOOTSTRAP_PASSWORD
```

CLI hash mật khẩu, tạo hồ sơ/tài khoản trong một transaction và từ chối sửa tài khoản đã tồn tại. Script chỉ chạy CLI, bị chặn truy cập HTTP. Không cần chạy với DB hiện tại; tài khoản hiện có được giữ nguyên. Mật khẩu của tài khoản cũ không tự đổi khi sửa seed.

DB hiện tại đã được sao lưu rồi áp dụng migration cộng thêm `02_attendance_integrity.sql` ngày 20/10; giữ nguyên số dòng của 13 bảng cũ và container/volume MariaDB. Bản sao lưu: `.pbl4-run/backups/pbl4-before-attendance-migration-20261020-143748.sql`. Không chạy lại `mariadb_schema.sql` lên DB đang có dữ liệu. Công cụ `tools/manage_live_stack.py prepare`/`apply` dành cho người bảo trì: phải đọc kế hoạch/backup trước khi apply; không có trong script khởi động.

Kiểm tra chỉ đọc cấu hình/schema/dịch vụ (không in credential):

```powershell
python -B tools/check_services.py
```

## Webcam và đăng ký

AI REST chiếm camera vật lý. Web/desktop/collector đọc qua relay, không mở camera lần hai. Nếu camera lỗi, đóng ứng dụng khác đang dùng webcam, kiểm tra Windows cho phép desktop app truy cập camera và chạy `tools/probe_camera.py` bằng Python venv. Dừng AI trước khi probe trực tiếp để tránh tranh thiết bị. Với index/backend mới, sửa `.env`, dừng và bật lại dịch vụ. Chỉ chọn `PBL4_CAMERA_MODE=local` khi chủ động dừng dịch vụ giữ camera.

Trong `pbl4-face-ai`, dùng Python của venv:

```powershell
& ./.venv-pbl4/Scripts/python.exe gui.py
& ./.venv-pbl4/Scripts/python.exe src/register.py refresh
& ./.venv-pbl4/Scripts/python.exe src/register.py webcam --id 2 --name "Ten nhan vien"
& ./.venv-pbl4/Scripts/python.exe src/register.py retry
```

Thay `2` bằng mã hồ sơ thực trên Web. Đăng ký yêu cầu năm pose cùng một người. Khi DB/refresh lỗi, batch giữ trong `data/enrollment-outbox`; retry tiếp tục batch cũ, không tạo hồ sơ hoặc ghi đè phiên bản mới hơn. Batch xung đột phải xem và xác nhận lưu trữ qua GUI. Gallery chỉ phát hành dữ liệu DB đã xác nhận. Gallery hiện đã refresh từ Web: 3 hồ sơ, 14 mẫu; mẫu cũ thiếu hướng vẫn cần đăng ký lại khi sử dụng.

## Thu dữ liệu RF v2 — bước cần người tham gia

Model `data/rf_status_model.pkl` hiện là legacy; loader v2 từ chối để tránh dùng sai feature. Giữ nguyên model/dataset cũ, không tự thêm metadata hoặc train bằng dữ liệu giả rồi triển khai.

Tại `pbl4-face-ai`:

```powershell
& ./.venv-pbl4/Scripts/python.exe scripts/collect_status.py --subject P01
# Người thứ hai dùng P02; cùng người phải giữ cùng mã ở mọi lần thu.
& ./.venv-pbl4/Scripts/python.exe scripts/collect_status.py --subject P02
& ./.venv-pbl4/Scripts/python.exe src/train_rf.py --data data/status_dataset_v2.csv --output data/rf_status_model.pkl
```

Trong cửa sổ collector: chọn nhãn bằng 1/2/3, giữ mặt chính diện đủ một chuỗi ba quan sát cách nhau 300–600 ms; nhấn lại để thu chuỗi tiếp theo; Q thoát. Nhãn do người vận hành ghi nhận. Cần ít nhất hai người, 18 chuỗi và đủ ba nhãn ở cả nhóm train/test; nên thu nhiều hơn mức tối thiểu cho mỗi người/nhãn. Chỉ thu khi người tham gia và người gán nhãn sẵn sàng, không tự suy nhãn từ chỉ số mắt. Nếu chưa đủ nhóm, trainer từ chối và giữ artifact cũ.

Sau khi có artifact tương thích, có thể chạy `demo_unified_iot.py`; phím 1/2/3 ở demo tạo chỉ số IoT giả lập và có thể gửi sự kiện chấm công thật vào Web. Không dùng demo để kết luận cảm biến đã được kiểm chứng. Serial thật cần firmware producer đúng giao thức; repo chưa có nghiệm thu MAX30102 toàn luồng.

## ESP32-CAM upload

Webcam laptop/USB là nguồn dùng hiện tại. ESP32 upload là nhánh nhận ảnh độc lập, chưa nối JPEG upload vào phiên chấm công.

- Sao chép `PhanCung/GuiAnhLenServer_2/wifi_config.example.h` thành `wifi_config.h` (được ignore), đặt Wi-Fi, URL `http://<IPv4-may-PC>:5000/upload` và upload token riêng.
- Chọn đúng board/camera trong `board_config.h`. Firmware có timeout HTTP, retry kết nối Wi-Fi, kiểm tra frame và hoàn trả buffer cả khi lỗi.
- Receiver mặc định bind loopback. Để ESP32 cùng LAN truy cập, chủ động đặt `PBL4_UPLOAD_BIND_HOST=0.0.0.0`, khởi động lại receiver và cho phép cổng 5000 trên mạng riêng Windows Firewall.
- Receiver chỉ nhận Bearer + `image/jpeg`, tối đa 5 MiB và 16 triệu pixel. Quota 1.000 ảnh/256 MiB; đầy trả 507, không tự xóa ảnh. Người vận hành sao lưu/chuyển ảnh đã nhận trước khi giải phóng dung lượng.
- Firmware chưa compile/flash hoặc kiểm thử ESP32 thật trong phiên này. Arduino CLI/ESP32 core chưa được cấu hình; không ghi nhận build PASS.

## Kiểm thử

Tại gốc PBL4, dùng Python venv:

```powershell
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -B -m unittest discover -s pbl4-face-ai/tests -q
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -B tools/test_ai_enrollment.py -q
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -B tools/test_upload_receiver.py -q
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -B tools/test_status_training_runtime.py -q
& ./pbl4-face-ai/.venv-pbl4/Scripts/python.exe -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe --desktop-python D:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/.venv-pbl4/Scripts/python.exe
```

Lệnh cuối dành cho Windows/XAMPP trên máy này: tạo MariaDB tạm ở random port, chạy fixture/HTTP/desktop, rồi dừng và xóa instance tạm; không dùng DB dự án. Sửa đường dẫn theo máy. Kiểm thử RF dùng dữ liệu tổng hợp trong thư mục tạm, không thay model đang triển khai.

`.github/workflows/regression.yml` cấu hình CI Python 3.12/PHP 8.2/MariaDB 10.11, với DB service riêng cổng 33307. CI kiểm tra hồi quy logic/HTTP/DB, không dùng webcam, cảm biến hay tải model. Workflow mới chưa được thực thi trên GitHub; kết quả local nằm trong [CHECKPOINT](../../CHECKPOINT.md) và [báo cáo](../../bao-cao/BAO_CAO_KIEM_TOAN_VA_KHAC_PHUC_2026-10-19.md).
