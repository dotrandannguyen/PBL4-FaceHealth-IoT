# CHECKPOINT — PBL4 — trạng thái sau Task 6

> **Trạng thái hiện hành 20/10/2026:** Task 1–5 hoàn tất logic/hồi quy; Task 6 đã hoàn tất phần mã, cấu hình, runtime local, hướng dẫn và workflow CI. **Web PHP 8.2/MariaDB 10.11, AI InsightFace và webcam laptop/USB đã chạy thật; PHP nhận JPEG qua AI thành công.** Có backup trước khi áp dụng migration cộng thêm vào DB dự án; số dòng cũ giữ nguyên. Chưa có model RF v2 từ dữ liệu người thật, chưa phiên chấm công người thật đầy đủ, chưa compile/flash ESP32 hoặc chạy workflow trên GitHub. AI/upload đang chạy. Người dùng đã yêu cầu commit gói thay đổi sau khi sửa lỗi trang chấm công; xem mục hậu kiểm cuối file. Chưa push. Các phần ngày 19/10 và nhật ký Task 1–5 bên dưới là lịch sử; đọc nhật ký Task 6 ở cuối trước khi tiếp tục.

## 1. Ảnh chụp trạng thái 19/10/2026 — lịch sử

- Workspace: `D:/DTDN_DOC/HK5/PBL4`.
- Ngày theo Asia/Saigon: **19/10/2026**. Thời điểm lưu: **2026-10-19T15:13:03+07:00**.
- Nhánh hiện tại: `master`; HEAD: `5a09099e1f2738837959ef92eb6a5f1b8ea8793a`.
- Công việc đang sửa **chưa commit, chưa stage, chưa push**. Trước đợt sửa, master đã đồng bộ origin/master.
- **ĐÃ TẠM DỪNG** theo yêu cầu rõ ràng của người dùng. Chỉ tiếp tục sửa khi người dùng yêu cầu tiếp tục. Không tự reset/revert/clean, xóa hay ghi đè thay đổi.
- Có **49 file thay đổi trước checkpoint**: 30 tracked modified, 4 tracked deleted, 15 file mới untracked. Số 23 người dùng nhắc không còn phản ánh tổng số file Git; có 23 file Python thay đổi được kiểm tra cú pháp lúc tạm dừng. CHECKPOINT.md là file mới thứ 16, nâng tổng lên 50.
- Không có thao tác ghi đang chạy dở được phát hiện. Lệnh cuối trước khi ngắt đã kết thúc thành công và lưu collector/train_rf. Không thấy process python/php/mysqld/mysql_install_db trong lần kiểm tra tạm dừng. Không chạy thêm kiểm thử dài hoặc thao tác DB trong giai đoạn checkpoint.
- Phiên này không tạo goal qua công cụ create_goal; không có goal cần chuyển trạng thái.

## 2. Yêu cầu gốc phải tiếp tục giữ

Người dùng yêu cầu xóa các báo cáo Markdown cũ, tạo báo cáo mới có ngày trong một folder dưới gốc PBL4, sau đó sửa lần lượt vấn đề audit, ưu tiên AI và luồng chấm công trước rồi các phần khác. Không có yêu cầu tự commit/push cho đợt sửa hiện tại.

Đã xóa bốn tài liệu báo cáo cũ theo yêu cầu trước đó; **không khôi phục chúng tự động**. Giữ README vì là hướng dẫn sử dụng. Báo cáo mới: `bao-cao/BAO_CAO_KIEM_TOAN_VA_KHAC_PHUC_2026-10-19.md`.

Tab IDE BAO_CAO.md người dùng đưa nằm ở dự án khác ngoài workspace này. Không đọc/sửa tab đó; checkpoint thuộc PBL4.

## 3. Những phần đã viết xong trong working tree

### Báo cáo

- Tạo báo cáo mới có ngày, 10 mục, danh sách audit T01–T18, Mermaid, lộ trình và giới hạn kiểm chứng.
- Xóa ARCHITECTURE.md, BAO_CAO_KY_THUAT.md, docs/ai1_diem_danh.md, docs/ai2_trang_thai.md.
- Báo cáo mới vẫn ghi “Đang khắc phục”; chưa cập nhật nhật ký sửa cuối cùng. README chưa cập nhật.

### AI và phiên chấm công

- `unified_engine.py` đã refactor sang RLock + một ThreadPoolExecutor; `done_session` chỉ ghi sự kiện; `update` chuyển state và duy nhất khởi chạy finalization. Có FINALIZING, UUID v4, đồng hồ monotonic, timestamp +07:00, stale-session guard, kiểm tra chỉ số hữu hạn, shutdown.
- AI/HTTP chạy worker để preview không chờ. Hủy/timeout không tiếp nhận kết quả inference muộn. Phiên mới chỉ được nhận ở IDLE.
- Giữ `Unknown/is_valid=False`; không đổi lỗi AI thành Normal. Thiếu dữ liệu không đi tới kết luận GREEN (trừ cảnh báo chỉ số độc lập được ưu tiên theo luật hiện hành).
- `predict_status.py` yêu cầu đủ ba quan sát thật, kiểm tra góc đầu và NaN; bỏ bù frame thiếu. Reset buffer khi mất mặt/quay đầu. Thêm close extractor.
- `sequence_features.py` là hợp đồng bảy đặc trưng dùng chung; collector lấy mẫu cách nhau tối thiểu 300 ms.
- Snapshot dùng event UUID, kiểm tra imwrite, log kết quả sau khi có web_result. Lưu pending outbox atomic trước gửi; xác thực Bearer; retry cùng event ID và thời điểm gốc.
- **Sửa mới nhất chưa regression đầy đủ**: yêu cầu danh tính nhất quán trên cả ba ảnh; `identify` nhận probe_embedding để tránh embed lại ảnh tốt nhất; kiểm tra confidence/similarity; outbox sắp thứ tự theo occurred_at và chặn sự kiện sau của cùng nhân viên khi sự kiện trước còn pending.

### Backend chấm công

- `AttendancePayload.php`: UUID v4, ID, timestamp có timezone, enum trạng thái, range/chỉ số, ảnh JPEG/PNG/kích thước và request hash.
- `AttendanceService::processEvent()`: khóa hàng nhân viên FOR UPDATE, bảng AttendanceEvent chống gửi lặp, phát hiện event ID đổi payload, transaction chung event/chấm công/sức khỏe/trạng thái/cảnh báo, giữ thời gian sự kiện gốc, từ chối tự tạo nhân viên, từ chối thiết bị chưa đăng ký, rollback và thông báo lỗi không lộ SQL.
- `AttendanceController::recordApi()` dùng service mới; bỏ ghi sức khỏe/cảnh báo rời và không dùng ảnh camera chụp ở thời điểm khác làm bằng chứng thay thế.
- Bổ sung các cột TheTrang/TheTrangVao/TheTrangRa và bảng AttendanceEvent trong schema mới. Migration nâng cấp: `DoAn_ChamCong_AI/migration/02_attendance_integrity.sql`, có thể chạy lại trên MariaDB.
- **Migration chỉ được thử trên instance tạm**; CHƯA áp dụng DB/volume thật của người dùng.

### Enrollment, gallery và cấu hình

- AI REST có Bearer auth (health không cần token), giới hạn body/ảnh, health phản ánh engine thật, capture kiểm tra lại một mặt và pose, vector hợp lệ; giấu exception chi tiết với HTTP client.
- `FaceSample.php` kiểm tra vector hữu hạn/norm và đồng nhất danh tính giữa các mẫu. PHP frame/inspect giải phóng session lock trước I/O đọc.
- Gallery ghi atomic, không tạo alias số trùng ở refresh; verify tự invalid cache khi stat file đổi hoặc file bị xóa.
- `.env.example` được thêm; `.env` local được tạo và **đã gitignore**, giữ credential DB cũ và tạo internal token cục bộ. Không in/chép nội dung .env vào báo cáo hoặc commit. Python runtime_config tự nạp .env nhưng không ghi đè biến môi trường đã đặt; Compose dùng biến .env. DB port bind loopback. .htaccess chặn các thư mục/file nội bộ và chuyển tiếp Authorization. Dockerfile khai báo mbstring.
- requirements bổ sung Flask, PyMySQL, pyserial; chưa có lock dependency đã resolver/kiểm chứng.

### Những phần viết gần cuối, chưa chạy lại đầy đủ

- `camera_source.py`: auto dùng relay từ AI service nếu đang chạy, tránh mở webcam thứ hai; mode auto/relay/local. Đã nối vào demo, desktop register và một số CLI.
- `face_sync.py`: đồng bộ/xóa embedding trong transaction, lấy credential từ môi trường. Script sync mặc định dry-run, chỉ --apply mới ghi, không xóa lịch sử chấm công/sức khỏe.
- GUI register: pose/một mặt/cùng danh tính, kiểm tra lưu ảnh; thông báo trạng thái sync; xóa DB trước local và giữ local nếu DB lỗi. GUI launcher thêm cwd; train chỉ báo thành công nếu subprocess thành công.
- Collector/train_rf vừa cập nhật metadata subject/session/interval, FEATURE_NAMES rõ, group split khi có đủ subject độc lập, warning với legacy/anonymous, lưu model và metadata atomic. **Chưa chạy collector hoặc train, không thay dataset/model hiện có.**

## 4. Kết quả kiểm thử đã thực sự thu được

### Python — mốc trung gian

Lệnh:

```powershell
python -B -m unittest discover -s pbl4-face-ai/tests -v
```

Kết quả: **11/11 tests PASS** ở mốc sau refactor engine ban đầu, trước các thay đổi cuối về consistency ba ảnh/outbox ordering/camera/GUI/train.

Bao phủ: DONE đồng thời chỉ finalize một lần; preview không chờ inference; stale session/NaN bị bỏ qua; abort không ghi; timeout không reset ngay; invalid AI không GREEN; failed imwrite không tạo đường dẫn giả; log chứa web_result; pending retry giữ payload; event ID không cho đổi payload; predictor không bù landmark thiếu và từ chối sai pose/NaN.

Không được diễn giải kết quả này là toàn bộ working tree hiện tại đã regression PASS. Nhiều trường hợp dùng dependency giả lập; chưa chạy model/camera thật.

### PHP/MariaDB — integration thật trên instance tạm

Lệnh đã chạy thành công:

```powershell
python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe
```

Kết quả in ra:

```text
PASS: fresh schema, repeatable migration, check-in/out, replay, conflict, Unknown, rollback, six concurrent requests, validation, embeddings
```

Runner khởi tạo instance mới trong thư mục hệ thống tạm, bind 127.0.0.1 với port ngẫu nhiên, không service Windows. Kiểm thử fresh schema, upgrade schema cũ và chạy migration lại, check-in/out, replay không biến vào thành ra, conflict payload, Unknown không thành Normal, không tự tạo nhân viên, inject lỗi trigger để xác nhận rollback toàn bộ, retry sau rollback và sáu process PHP cùng event chỉ tạo một check-in.

Runner đã terminate database tạm và đóng TemporaryDirectory. **Không thay DB dự án.** Phiên bản thực: MariaDB 10.4.32 và PHP CLI 8.0.30 từ XAMPP; môi trường Docker mục tiêu là MariaDB 10.11/PHP 8.2, chưa build/chạy được vì daemon không hoạt động.

### Syntax/static

- PHP lint toàn bộ PHP từng PASS ở mốc trung gian; một số sửa sau mốc đó chưa lint lại.
- Lần chuẩn bị pause chỉ chạy kiểm tra đọc nhanh: **23 file Python đang thay đổi parse AST thành công, không lỗi cú pháp**. Không import model/thư viện.
- `git diff --check` lúc pause không báo lỗi whitespace; chỉ cảnh báo .gitignore LF sẽ đổi CRLF khi Git chạm file.
- 5 JS từng node --check PASS ở audit ban đầu; JS enrollment đã sửa sau đó, chưa check lại bản mới.
- Không có HTTP end-to-end tests; mới test service/DB và logic tách biệt.

## 5. File còn sửa dở / cần review trước khi coi hoàn thành

Không phát hiện file bị cắt giữa chừng hoặc lỗi AST. “Dở” ở đây là logic, kiểm thử và tích hợp còn thiếu:

1. `src/attendance_transport.py`: thay ordering vừa thêm chưa test. `_pending()` bỏ qua entry thiếu occurred_at; cần bổ sung test ordering, server nhận nhưng client mất ACK, lỗi tạm, event lỗi vĩnh viễn, nhiều nhân viên. `send()` có thể xử lý nhiều pending trước event mới, cần chặn số lần/độ trễ hợp lý. Cơ chế xác thực chỉ chấp nhận HTTP 200+success/completed; chưa đối soát HTTP server thật.
2. `unified_engine.py` + `src/verify.py`: mới thêm embed cả ba frame và consistency; cần tests cho đổi người/nhiều mặt/confidence lỗi, performance và timeout. Tránh gọi model đồng thời từ GUI process; không khẳng định tốc độ. Xem lại behavior lỗi ghi JSONL sau khi Web đã ACK để HUD không báo sai tình trạng DB.
3. `ai_web_service.py`: auth/readiness/capture/gallery mới cần Flask test client/HTTP tests; chưa có môi trường import AI. `_engine_lock` dùng cho init/inference; cần review deadlock/ownership và shutdown. Chưa có test nhiều request refresh/gallery writers.
4. `src/camera_source.py` và các entry points: relay dùng HTTP đồng bộ ở read với timeout 1.5s; chưa benchmark hay thử camera thật. Auto có thể chọn local khi service khởi động trễ; cần xác nhận một camera owner. Review import path khi chạy trực tiếp các src/scripts từ cwd khác.
5. `gui_register.py`, `gui.py`, `src/face_sync.py`: chưa chạy GUI/DB sync thật. GUI register import ai_web_service chỉ để dùng pose, nên phụ thuộc Flask và side effect module; nên tách pose helper khi tiếp tục. Review callback Tkinter khi cửa sổ đóng, tên ID và alias, xóa folder có kiểm tra resolved path, cập nhật gallery nếu Web và desktop cùng thay đổi. Có thể còn thông báo “thành công” cần điều chỉnh cho đúng local/Web.
6. `scripts/collect_status.py`, `src/train_rf.py`: là thao tác ghi cuối trước khi ngắt, đã lưu hoàn chỉnh và AST pass, nhưng chưa unit/runtime. GUI chưa truyền --subject nên mặc định anonymous; independent evaluation không được tuyên bố nếu dùng legacy/anonymous. Split theo subject có thể thiếu class trong train và hiện chủ động báo lỗi; cần test dataset nhỏ. File model và metadata được thay riêng, chưa có manifest nguyên tử chung. Không train ghi đè model để “thử” nếu chưa chủ động chuẩn bị bản sao.
7. PHP API/auth/payload/FaceSample/config mới: cần lint bản cuối, HTTP tests 401/503/body/image và migration trên MariaDB 10.11 mục tiêu. `.htaccess` chưa thêm quy tắc chặn thư mục tests mới. Chưa áp migration lên DB thật. Không tự làm ở phiên tiếp theo nếu người dùng vẫn chỉ yêu cầu pause.
8. Báo cáo mới cần cập nhật trạng thái từng T01–T18 và kết quả thực; docs/README.md chưa cập nhật sau xóa báo cáo. Chưa bổ sung CI hoặc hướng dẫn migration/token đầy đủ.

## 6. Vấn đề audit còn tồn đọng / chưa hoàn tất

- Firmware MAX30102 với START/ABORT/DONE chưa tồn tại trong repo; chưa biết pin/hardware để triển khai đúng, không được đoán.
- `PhanCung/esp32_server/app.py` chưa sửa: upload chưa auth/validate/limit/retention (T17).
- Credential Wi-Fi trong firmware chưa tách khỏi source. Credential từng commit trong lịch sử Git không tự biến mất khi chuyển sang .env; chưa rotate và không rewrite history (T12 còn một phần).
- Môi trường `.venv` cũ vẫn trỏ interpreter Python 3.11 không còn tồn tại. Python mặc định 3.12.11 thiếu numpy/cv2/flask/insightface/mediapipe/sklearn. Không cài thư viện hoặc sửa virtualenv trong phiên này.
- Dependency chưa khóa bằng bộ phiên bản đã resolver/runtime, chưa có CI (T15/T18 còn phần việc).
- Multi-writer gallery vẫn cần review: atomic replace và stat invalidation giải quyết file cắt dở/cache cũ nhưng không tự giải quyết lost update khi nhiều process cùng read-modify-write.
- Hiệu suất chưa benchmark; chưa sửa phân trang danh sách nhân viên, chưa retention evidence, chưa hợp nhất toàn bộ tính trạng thái ca.
- Serial consumer chưa có event ID từ firmware thật; local session token giúp timer nhưng không chứng minh phân biệt được gói phần cứng gửi muộn từ phiên trước.
- Chưa kiểm chứng camera, model AI, GUI, ESP32 và luồng đầy đủ Web; chưa có độ chính xác độc lập được xác nhận.

## 7. Công cụ và môi trường để tiếp tục

- Shell PowerShell, root workspace như trên. Không spawn sub-agent nếu chưa được yêu cầu.
- Python gọi được: `C:/msys64/mingw64/bin/python.exe` 3.12.11; dùng `-B` tránh ghi pyc.
- PHP: `C:/xampp/php/php.exe` 8.0.30, có pdo_mysql, pdo_sqlite, mbstring, fileinfo.
- MariaDB test binaries: `C:/xampp/mysql/bin/mysql_install_db.exe`, `mysqld.exe` 10.4.32. Dùng runner isolated; tuyệt đối không chạy test trên port 3306/DB đang dùng.
- Node v22.14.0. Docker CLI có, daemon không hoạt động ở lần kiểm tra trước.
- Chú ý Windows PowerShell: script Python nhiều dòng nên dùng `$OutputEncoding = [System.Text.UTF8Encoding]::new($false)` rồi here-string pipe vào `python -B -`; truyền chuỗi nhiều dấu nháy qua `python -c` từng bị lỗi quoting. Không mất dữ liệu từ các lần lệnh lỗi đầu vì chưa ghi; các thao tác sau đã hoàn tất.
- Không đọc/in nội dung `.env`. File local tồn tại và `git check-ignore .env` xác nhận đã ignore. Khi chuyển máy cần tự cấu hình từ .env.example; file này không đi theo Git.

## 8. Trình tự tiếp tục được đề xuất khi người dùng cho phép

1. Đọc checkpoint và git diff, giữ nguyên thay đổi hiện có.
2. Review engine/transport/verify và bổ sung tests cho thay đổi cuối; chạy lại suite Python nhẹ trước.
3. Lint PHP/JS bản cuối; test auth HTTP trên môi trường tách biệt. Không tự áp migration production.
4. Review và kiểm thử enrollment/gallery/camera relay/desktop sync. Không công bố runtime AI khi chưa có interpreter/dependency/model.
5. Hoàn thiện collector/train subject workflow, upload/firmware config, docs/CI và báo cáo.
6. Chốt kết quả kiểm thử, phần còn chặn bởi môi trường/phần cứng; chỉ commit/push khi người dùng yêu cầu.

## 9. Danh mục chính xác tại thời điểm checkpoint

Danh sách dưới đây lấy trực tiếp từ Git, không tự stage hay sửa file. SHA-256 dùng để xác nhận bảo toàn file hiện tại, không bao gồm secret local .env.

| Git | File | SHA-256 lúc pause |
|---|---|---|
| M | `.gitignore` | f7c21fa3c2ee9130123398fd3a422ea58e3a3bec152d57e823fbf9448eacc974 |
| M | `DoAn_ChamCong_AI/.htaccess` | 4fb2b55d5ba3e6ad4f2738473f9e4b147d00f834d96e4ce641abff9d8a4b8203 |
| M | `DoAn_ChamCong_AI/Controller/AiController.php` | 4c35ede34231b20b96de204a98256cce0d35579511e1e990a127875c517c21e7 |
| M | `DoAn_ChamCong_AI/Controller/AttendanceController.php` | 766a56e52c6c0a291976dc3bf3ca3c3f37a7f8efc20a24b38a7b944da0e475b3 |
| M | `DoAn_ChamCong_AI/Controller/FaceEnrollmentController.php` | 708a2330af93a45800f0fbdce5f60be9e455aeb4e2c0b1a619adb913a8e44c2b |
| M | `DoAn_ChamCong_AI/Dockerfile` | 2c7ac953a6e2fcaf785ccc728c28d6eeee74515e9c184df44e44bece7094f38c |
| M | `DoAn_ChamCong_AI/Model/AttendanceModel.php` | dc6c3ddc954a5f6465588214797c80baf35c4aae8cce2dbe15711549b6b7bd46 |
| M | `DoAn_ChamCong_AI/Model/FaceEmbeddingModel.php` | 16fbc5944960435dc46d9143fa4a5d5eb9ea6dabb77dc293add71ea65440d55a |
| M | `DoAn_ChamCong_AI/Service/AiClient.php` | e2eccae921e921e9629e282b6616c07ed68f40b0d6d92aeb80559223f545e8c2 |
| M | `DoAn_ChamCong_AI/Service/AttendanceService.php` | 599d80c0c411f304e30cf464d512d45b4c1b1dc20c04b1656da8961d058ea9e5 |
| M | `DoAn_ChamCong_AI/Service/CameraFrameClient.php` | cfd02128e3f5e94f7a2e01fc04877205eec1781a0a590990275fd15dd9d6efbf |
| M | `DoAn_ChamCong_AI/migration/mariadb_schema.sql` | c9fbc84fa287c4c89cd2ddcd0f5af2917fa76353ac9d9fa6d889a09d22e8790b |
| M | `DoAn_ChamCong_AI/public/js/face_enrollment.js` | a8731c2c9448fab419c9a3cf2d555cd9569d73373f5311ee0f9d672f594cb688 |
| M | `docker-compose.yml` | 4f7d2b4247e7593cd369dc25e0e6a0830dd182054c9e1a64a27806327c042ae5 |
| D | `pbl4-face-ai/ARCHITECTURE.md` | Đã xóa theo yêu cầu trước; nội dung gốc còn trong Git HEAD |
| D | `pbl4-face-ai/BAO_CAO_KY_THUAT.md` | Đã xóa theo yêu cầu trước; nội dung gốc còn trong Git HEAD |
| M | `pbl4-face-ai/ai_web_service.py` | c03c3ca6c4524d8dabacfd5fde09b721b74e1292b5369a05749569891171a9ee |
| M | `pbl4-face-ai/demo_unified_iot.py` | 7e6d684e482afae4c914bdf3c0d860d318939b1c5dd6c4a589ce4fdc4e89445f |
| M | `pbl4-face-ai/demo_webcam.py` | ef16d02e23ff7debda1e100ff620c312303d6b526006d8d13227f53c4b7e5ce1 |
| D | `pbl4-face-ai/docs/ai1_diem_danh.md` | Đã xóa theo yêu cầu trước; nội dung gốc còn trong Git HEAD |
| D | `pbl4-face-ai/docs/ai2_trang_thai.md` | Đã xóa theo yêu cầu trước; nội dung gốc còn trong Git HEAD |
| M | `pbl4-face-ai/gui.py` | b54aba4726f98b0462cf9b42542dc2d88a9755c1ebec230d19c561dc4d59b1a1 |
| M | `pbl4-face-ai/gui_register.py` | 0ebfb80260b6b6bac238b6b4d6d1509831ed9b650a9e9eb6cb255c8bcf990de6 |
| M | `pbl4-face-ai/requirements.txt` | 415c42645d2885b9e94bc0289c49545324229ba13da271410f434b3bc93fd4d6 |
| M | `pbl4-face-ai/scripts/capture_webcam.py` | 8639dcdc29bd2e2a601e9a23f9746abe60fe9eb71d2b82e6b8fcfd70eacae970 |
| M | `pbl4-face-ai/scripts/collect_status.py` | 24fbd6c0dc5879d6a006a18bf9111df1f8303357a8ba6903224985b80ceca936 |
| M | `pbl4-face-ai/scripts/sync_faces_to_db.py` | 81cfe04dfc5be462bb0733faab648431da2c0844244dc0f0a19a38855601c70d |
| M | `pbl4-face-ai/src/face_engine.py` | 8e45f0ac5e364bedbad6ba9625cfe6bc051f215f9d7d44a15f2076721150fa96 |
| M | `pbl4-face-ai/src/predict_status.py` | 704bb68c08c1e92e535e8f1ba21b62851b0e902147bc1f107b50efff1e0f63c8 |
| M | `pbl4-face-ai/src/register.py` | 0789973a76660d1fc11f8657cb5ac9374df3b992a8b982abed9e3d1a95e8106b |
| M | `pbl4-face-ai/src/status_features.py` | 81bea6ecd8eb014a1f7b526140be3f522dae0149ae5590179ca591f6129f59cf |
| M | `pbl4-face-ai/src/train_rf.py` | 1f9269dc23753639bf6b2580ca3fb925662df7bba7725c816d3c92f84b224295 |
| M | `pbl4-face-ai/src/verify.py` | 17ce724c67698af2c76264cfc0d738bff379e4147c31bc9b68784a039aa890b7 |
| M | `pbl4-face-ai/unified_engine.py` | 89671489513b11d631c7f067f2cb9c9b938840ecbc71154b796b27433268bb3e |
| ?? | `.env.example` | 2d34821062973aebb2294aded4fa9904957d480d0692ba6bb507e3c1b94427e4 |
| ?? | `DoAn_ChamCong_AI/Security/InternalApi.php` | a7108cd3b2bd409ae938ffd4ad1b7268829725ec9774305343945e73082e6472 |
| ?? | `DoAn_ChamCong_AI/Service/AttendancePayload.php` | 933dc280bd8ce487a6364c0e402a1a5643598724d78f16d78c38526b7a8500f9 |
| ?? | `DoAn_ChamCong_AI/Service/FaceSample.php` | 55aa58a8c5ad46416f3dba109f7c8320808887364907e06f51da8c6dedca8d46 |
| ?? | `DoAn_ChamCong_AI/migration/02_attendance_integrity.sql` | 274381ec1c63a883a493378d5ac46c90d964fa375df001534d2f77b8f0ce1008 |
| ?? | `DoAn_ChamCong_AI/tests/integration_attendance.php` | fcf5db8bd1fbe9422205dd4417b3d7f0ae475c6e65cb1631f54f902b72706e5a |
| ?? | `bao-cao/BAO_CAO_KIEM_TOAN_VA_KHAC_PHUC_2026-10-19.md` | 715650b4674c84c02ec7b256d0f0b6d4e77cba1026c42f6ef023a67d58483921 |
| ?? | `pbl4-face-ai/src/atomic_storage.py` | 6767d581ec5de453c0952310f447cc5baf1786273d61cba3eab44d2e28860425 |
| ?? | `pbl4-face-ai/src/attendance_transport.py` | b3a1930cef2947c1d56b4b0a01633cc32e423f58f3b2fe94335ecaa8f6cd8c7f |
| ?? | `pbl4-face-ai/src/camera_source.py` | d7bca3e33593bd599e911a54ee868c3d3ca8c0d5f95ed89b04b9ca1ff5d964f6 |
| ?? | `pbl4-face-ai/src/face_sync.py` | 790c1ce1066ab959fe7e668cf09879e7422f81b7339034370d2d7c3ba361467d |
| ?? | `pbl4-face-ai/src/runtime_config.py` | d8f21c2667797f580e545ceb3d0b088f8d0db25e2d4bda428f9a1aacb7d1a853 |
| ?? | `pbl4-face-ai/src/sequence_features.py` | 6edb87fa6a0842ac07895776ff1f7adc0eaf61fecf6f5a683251bf4e26ad30b8 |
| ?? | `pbl4-face-ai/tests/test_attendance.py` | 9569ba1380a3d780877666362f270cb5d427951faa8674e939bdd9c7f249d491 |
| ?? | `tools/test_isolated_database.py` | 1b0587a37cddf9a6819f46667b4b6ba113eff362152bb3adca65bdd34e42f1a2 |

## 10. Kết luận bàn giao

Toàn bộ công việc hiện có được giữ trong working tree. Không reset/revert/clean, không thêm commit/push, không áp migration lên DB người dùng. Checkpoint này là file duy nhất được tạo trong bước tạm dừng. Phiên làm việc đã dừng và sẵn sàng tiếp tục từ đây khi người dùng yêu cầu.

## 11. Tiếp tục theo từng task — 20/10/2026

| Task | Phạm vi | Trạng thái |
|---|---|---|
| 1 | AI, state machine, outbox, hồi quy | Hoàn tất logic và unit tests; runtime model/camera chưa kiểm chứng |
| 2 | API/PHP: auth HTTP, validation, migration, transaction | Hoàn tất; 44 PHP lint, DB tạm và 43 kiểm tra HTTP PASS |
| 3 | Enrollment Web, pose, đồng nhất người, gallery/cache | Hoàn tất logic; 36 unit tests, 8 Flask tests, DB tạm và 37 HTTP enrollment checks PASS; chưa model/camera thật |
| 4 | Desktop, camera relay, đồng bộ DB/local | Hoàn tất logic; 42 unit, 8 Flask, 14 desktop/runtime, 43 HTTP chấm công + 42 HTTP enrollment/camera PASS; chưa GUI/camera/model thật |
| 5 | Collector/train: metadata, split, lưu model | Hoàn tất logic; 58 unit + 11 collector/train/inference tests PASS; RF thật trên dữ liệu tổng hợp, chưa camera/dataset thực |
| 6 | Upload ESP32, cấu hình, hướng dẫn, báo cáo tổng hợp | Chờ |

### Task 1 — kết quả cụ thể

- Đọc checkpoint, kiểm tra trạng thái và chạy lại 11 tests cũ: PASS.
- Giữ điều kiện ba ảnh cùng người; thêm hồi quy cho đổi người/mất mặt, confidence/similarity không hợp lệ. Không đổi model/dataset, không đoán độ chính xác hoặc FPS.
- Outbox kiểm tra UUID v4, ID nhân viên và thời gian có múi giờ trước khi lưu; chỉ xóa pending khi ACK đúng event_id và hành động/trạng thái hợp lệ. Ghi receipt atomic chứa hash request và kết quả Web (không lưu ảnh trong receipt) để replay không gửi thêm hoặc đổi payload.
- Gửi theo thời gian thực có xét timezone, giới hạn tối đa 5 lần gửi trong send; sự kiện trước lỗi chặn sự kiện sau của cùng nhân viên nhưng không chặn nhân viên khác. Entry hỏng được giữ nguyên và chặn gửi thay vì âm thầm bỏ qua; cần người vận hành kiểm tra, không tự xóa.
- Tách executor retry khỏi executor inference để mạng chậm không chiếm hàng đợi AI.
- JSONL ghi lỗi không hủy ACK từ Web; record trả local_log_saved=false. Có receipt riêng để đối soát. Khóa ghi journal giữa retry và finalization.
- Shutdown đợi finalization đã được submit; không cancel gây mất lần chốt đang chờ. Giá trị Serial boolean/string/NaN/range sai bị bỏ qua.
- Các file mã nguồn của task này: `unified_engine.py`, `src/attendance_transport.py`, `src/predict_status.py`, `tests/test_attendance.py`, mới `tests/test_session_regressions.py`. Các phần task khác giữ nguyên từ checkpoint.
- Lệnh nghiệm thu: `python -B -m unittest discover -s pbl4-face-ai/tests -v`. Kết quả cuối: **28 tests PASS**, dùng mô hình/camera/HTTP giả lập và thư mục tạm. Không chạy MariaDB, HTTP backend, GUI, inference thật trong task này.
- Việc tiếp theo: Task 2; kiểm tra PHP/HTTP và DB tạm theo runner đã có. Không tự áp migration DB thật hoặc commit/push.

### Task 2 — API/PHP, hoàn tất ngày 20/10/2026

Phạm vi riêng task này: router, xác thực API PHP, payload, giao dịch và ca chấm công; chưa bắt đầu task 3 enrollment/gallery.

**Thay đổi và lỗi đã xử lý:**

- Check-out/completed giữ MaCa đã lưu lúc check-in, kể cả khi ca đó bị tắt hoặc ca mặc định/phân ca thay đổi. Trước đó service chọn lại ca hiện tại, có thể trả sai ca hoặc chặn checkout khi không còn ca đang bật.
- Từ chối sự kiện mới đến trước/cùng thời điểm check-in; giữ replay cùng event_id trả kết quả cũ.
- Phân biệt lỗi nghiệp vụ/conflict HTTP 409 với lỗi lưu trữ/DB unavailable HTTP 503. Toàn bộ event/chấm công/sức khỏe/trạng thái/cảnh báo vẫn rollback cùng nhau; không trả SQL/credential trong response.
- API yêu cầu Content-Type application/json (415 nếu sai), giữ giới hạn body 8 MiB (413), chặn query action dạng array (400 thay vì lỗi offset gây 500).
- NhipTim là cột INT: chấp nhận giá trị nguyên 80/80.0 sau chuẩn hóa, từ chối 80.5 để không âm thầm làm tròn. Payload tương đương về timezone/kiểu số cho cùng request hash và replay đúng.
- Phản hồi xác thực có Cache-Control private, no-store; auth thiếu/sai 401, token chưa cấu hình 503; gallery cũng được test.
- .htaccess bổ sung chặn thư mục tests; đây là cấu hình Apache, chưa tuyên bố được kiểm chứng bằng PHP built-in server.
- Gỡ CameraFrameClient không còn dùng trong AttendanceController và require HealthModel thừa trong service. API không chụp ảnh camera khác thay cho bằng chứng của event.

**Kiểm thử thực tế:**

1. PHP lint: **44 file, 0 lỗi** (PHP 8.0.30 CLI XAMPP; bản mục tiêu Docker 8.2 chưa build).
2. `python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe`:
   - Fresh schema, upgrade và migration chạy lại: PASS.
   - Check-in/out, replay, event conflict, Unknown, nhân viên/thiết bị chưa đăng ký, out-of-order: PASS.
   - Trigger lỗi xác nhận rollback và retry; 6 process PHP cùng event; giữ ca cũ khi tất cả ca bị tắt: PASS.
   - **43 kiểm tra HTTP PASS** qua PHP router thật: 401/400/405/409/413/415/503; gallery auth; ảnh PNG sinh trong test và thời gian sự kiện giữ nguyên; duplicate không ghi thêm; timezone/số nguyên tương đương replay đúng; Unknown không thành Normal; inject lỗi DB rollback và retry; DB không kết nối được trả 503 an toàn.
3. Server PHP dùng session.save_path và log trong thư mục tạm; MariaDB 10.4.32 chạy instance tạm, port ngẫu nhiên, không Windows service, không port 3306. Các process do runner khởi chạy được dừng và temp directory được thu dọn. **Không chạm DB/volume hiện có.**
4. Một lỗi đầu ở test harness (HTTPConnection không hỗ trợ context manager) đã sửa; các lần nghiệm thu sau PASS. Một shell kiểm tra process trả exit 1 do không tìm thấy process còn chạy, không phải lỗi test (hai dòng PASS đã xác nhận test thành công).

**Giới hạn còn lại:** PHP 8.2/MariaDB 10.11 trong Docker và quy tắc .htaccess trên Apache chưa chạy; chưa áp migration DB thật; chưa test model/camera/ESP32; chưa commit/push. Tiếp theo là **Task 3: enrollment, pose, cùng người và gallery/cache**.


### Task 3 — enrollment Web và gallery/cache, hoàn tất ngày 20/10/2026

**Phạm vi:** đăng ký Web đủ năm hướng, xác thực mẫu cùng người, giao dịch ảnh/vector/avatar, làm mới gallery và cache giữa các process. Chỉ sửa đường ghi gallery dùng chung ở CLI/desktop; chưa nghiệm thu toàn bộ desktop/camera/sync (Task 4).

**Thay đổi đã hoàn thành:**

- Tách kiểm tra năm tư thế vào `src/enrollment_pose.py`, Web và desktop dùng chung. Capture kiểm tra lại đúng một mặt và đúng hướng trên ảnh capture; không coi trái/phải tương đương. Từ chối landmarks suy biến/NaN, ảnh giả/sai định dạng/quá lớn và vector không hữu hạn/zero norm/sai 512 chiều. Vector wire dùng float32 little endian.
- PHP kiểm tra pose trả về, SHA-256 ảnh và cặp ảnh/vector; đối chiếu danh tính với mẫu đầu. Chỉ ghi sau đủ năm hướng. `FaceEmbeddingModel` khóa hàng nhân viên; thay mẫu và avatar trong cùng transaction; xóa mẫu đồng thời xóa avatar. Lỗi cập nhật avatar rollback cả mẫu, giữ dữ liệu cũ. Avatar ghi MIME đúng PNG/JPEG.
- Lưu kết quả batch trong session sau hoàn tất để mất phản hồi rồi gửi complete lại không tạo batch mới. Batch đã lưu không nhận thêm capture/inspect; session/receipt vẫn có TTL 10 phút, không phải nhật ký bền vững khi PHP crash hoặc mất session.
- `AiClient` kiểm tra HTTP status/JSON/bool success, không theo redirect, giới hạn response 8 MiB. Không tin success=true trong HTTP 500/503. Capture bị từ chối hợp lệ HTTP 409 được chuyển tới UI.
- Thêm route POST `face_gallery_refresh` có admin/CSRF. UI báo rõ DB đã lưu/xóa nhưng AI chưa cập nhật, có nút đồng bộ/thử lại (kể cả sau tải lại trang); retry không ghi lại mẫu. Cảnh báo xóa chưa đồng bộ có thể vẫn nhận diện bằng dữ liệu cũ. Chặn bắt đầu lặp khi batch đang thu.
- Gallery khóa toàn bộ fetch + validate + atomic replace bằng khóa thread và khóa file liên tiến trình; refresh cũ không ghi sau refresh mới. Mutation CLI/desktop đọc-sửa-ghi dưới cùng khóa, tránh mất cập nhật của nhân viên khác. File `.pkl.lock` được giữ để khóa ổn định, đã ignore Git.
- Gallery từ Web kiểm tra IDs, chiều, base64, hash, norm và tên nhất quán trước khi thay file; dùng một key chuẩn `SVxxx`. Payload lỗi giữ nguyên file cũ; gallery rỗng hợp lệ xóa hết dữ liệu nhận diện. `verify.load_db()` dùng `GalleryCache` tự phát hiện file atomic replacement/xóa. File hỏng gây lỗi thay vì âm thầm nhận diện từ cache cũ.
- Flask không import/khởi tạo InsightFace chỉ để import ứng dụng; health không tải model. Response nội bộ no-store, body quá lớn trả 413.

**Kiểm thử và bằng chứng:**

1. `python -B -m unittest discover -s pbl4-face-ai/tests -v` — **36 tests PASS** (28 hồi quy Task 1 + 8 pose/storage/cache). Test có tám process cùng cập nhật, refresh bị chậm, cache của process đọc đang chạy nhận file thay/xóa; không dùng NumPy/model trong bộ này.
2. `C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B tools/test_ai_enrollment.py --extra-site pbl4-face-ai/.venv/Lib/site-packages -v` — **8 tests PASS**, Flask test client thật, NumPy/Pillow thật; detector và adapter OpenCV giả lập. Có auth/no-store, readiness, 413, dữ liệu ảnh lỗi, không mặt/nhiều mặt/sai pose/landmarks, vector lỗi, ảnh/hash và gallery refresh lỗi/xóa/cache. Không có inference InsightFace hoặc camera thật.
3. `python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe` — **PASS** toàn bộ Task 2 + **DB enrollment và 37 HTTP enrollment checks** mới. Login admin, cookie session, CSRF và router PHP thật; AI/camera HTTP giả lập. Test sai pose/khác người/hash sai/HTTP lỗi không tăng tiến độ; rollback lưu/xóa, bốn PHP process đồng thời thay mẫu, complete replay, hủy giữ mẫu cũ, refresh thất bại rồi retry, ảnh bảo vệ và xóa avatar. Giữ **43 HTTP chấm công checks PASS**.
4. **45 file PHP lint PASS**, **31 file Python thay đổi/mới AST PASS**, `node --check DoAn_ChamCong_AI/public/js/face_enrollment.js` PASS. `git diff --check` không lỗi whitespace (Git có cảnh báo LF/CRLF ở .gitignore).
5. Test đầu phát hiện PermissionError ở Windows do đọc byte khóa trước khi giữ khóa; đã sửa và chạy lại đạt. Đây là lỗi được test phát hiện/sửa trong Task 3, không phải lỗi còn tồn đọng.

**Môi trường và giới hạn:**

- DB test là MariaDB 10.4.32 tạm, port ngẫu nhiên, PHP 8.0.30 CLI/built-in, process/temp được runner dọn; không DB/volume/service dự án. Chưa Docker PHP 8.2/MariaDB 10.11 hoặc Apache .htaccess.
- Không cài thêm thư viện/đổi virtualenv. Python mặc định thiếu thư viện AI; venv dự án vẫn trỏ Python 3.11 không có. Test Flask dùng Python runtime 3.12 có NumPy/Pillow và append thư viện pure Python Flask/requests từ venv hiện có; không chứng minh venv dự án chạy được.
- Khi service/mạng lỗi sau lưu/xóa DB, gallery cục bộ cũ vẫn tồn tại cho tới đồng bộ thành công. UI đã cảnh báo và cho retry; **chưa có cơ chế thu hồi offline tức thời hoặc reconciliation tự động**. Kiểm tra nguồn DB/local và retry desktop ở Task 4. Ngưỡng danh tính/pose chưa hiệu chỉnh với dữ liệu thật; chưa đánh giá liveness/độ chính xác/FPS.
- Các đường đăng ký folder/webcam/GUI còn cần kiểm tra trọn luồng cùng người, ảnh theo batch, thất bại sync và callback Tkinter trong Task 4; chưa coi hoàn tất chỉ vì gallery dùng khóa chung.
- Không commit/push, không reset/revert/clean; giữ các file thay đổi từ trước. Bảng hash ở phần 9 là lịch sử, không phản ánh nội dung sau Task 1–3.

**File thêm trong Task 3:** `pbl4-face-ai/src/enrollment_pose.py`, `src/gallery_store.py`, `src/gallery_payload.py`, `tests/test_enrollment_store.py`; `tools/test_ai_enrollment.py`, `tools/test_http_enrollment.py`; `DoAn_ChamCong_AI/tests/integration_enrollment.php`.

**File sửa trong Task 3:** `.gitignore`; `pbl4-face-ai/ai_web_service.py`, `src/atomic_storage.py`, `src/verify.py`, `src/register.py`, `gui_register.py`; `DoAn_ChamCong_AI/Controller/FaceEnrollmentController.php`, `Model/FaceEmbeddingModel.php`, `Service/AiClient.php`, `index.php`, `public/js/face_enrollment.js`, `public/css/app.css`; `tools/test_isolated_database.py`; checkpoint và báo cáo.

**Tiếp theo:** Task 4, chỉ bắt đầu khi người dùng yêu cầu tiếp tục. Đọc phần cập nhật này trước; không làm lại Task 1–3 trừ khi phát hiện hồi quy mới. Giữ yêu cầu làm tuần tự từng task, bảo toàn thay đổi và không tự áp migration DB thật.

Ghi chú xác minh cuối Task 3: truy vấn toàn hệ thống bằng Get-CimInstance Win32_Process bị Access denied; dòng đếm 0 sau lệnh đó không phải bằng chứng process sạch. Runner đã terminate/wait các process do nó tạo và thoát TemporaryDirectory thành công; chưa xác minh độc lập toàn hệ thống. Không yêu cầu thêm quyền chỉ để làm kiểm tra phụ này.


### Task 4 — desktop, camera relay và đồng bộ DB/local, hoàn tất ngày 20/10/2026

**Phạm vi:** `gui_register.py`, dashboard `gui.py`, CLI đăng ký/import, camera adapter, đồng bộ mẫu vào DB và gallery đã xác nhận. Không bắt đầu sửa collector/train/firmware.

**Các lỗi đã xử lý và hành vi hiện tại:**

- Không ghép vector với ảnh theo danh sách tên file trong `data/registered` nữa. Một lần detect cung cấp cả pose và vector; ảnh JPEG được mã hóa từ chính frame đó. GUI/CLI yêu cầu đủ năm hướng, chỉ một mặt, vector hữu hạn/nonzero và cùng người. Hủy/thiếu mẫu không ghi gallery hoặc ghi đè ảnh của lần đăng ký trước. Folder phải có đúng năm ảnh với năm pose riêng; không dùng vector trung bình làm mẫu gốc thay thế.
- Thêm `src/enrollment_samples.py` để validate/chuẩn hóa các mẫu dùng chung; ảnh PNG/JPEG được xác thực bằng Pillow trước DB. Byte vector little endian. Không gọi inference lần hai để lấy vector sau kiểm tra pose.
- Thêm `DesktopEnrollment`: batch được lưu atomic vào `data/enrollment-outbox/pending/<uuid>.json` với ảnh/vector/hash theo cặp, phiên bản DB kỳ vọng, thời điểm và cờ `db_saved`. Batch chưa xác nhận không được đưa vào gallery nhận diện. Mất kết nối giữ file để thử lại sau khi mở ứng dụng lại.
- Gallery là bản đọc từ DB đã xác nhận. UI có làm mới DB và thử đồng bộ batch chờ; CLI có `refresh`/`retry`. Sau DB commit, nếu refresh gallery lỗi, retry chỉ đọc lại DB và không ghi batch cũ lên một đăng ký Web mới. Receipt không chứa ảnh/vector; chỉ bỏ pending khi đồng bộ xong.
- Phiên bản gallery được tạo từ ID mẫu và SHA-256 vector. GUI/CLI chốt phiên bản **trước lúc bắt đầu thu mẫu**; xóa chốt trước lúc xác nhận. DB transaction khóa nhân viên rồi so phiên bản, từ chối batch/xóa cũ khi Web đã đổi. Exact replay sau mất ACK giữ nguyên các MaEmbedding nếu các mẫu đã giống nhau.
- `face_sync` không tự tạo nhân viên, đổi tên hoặc đổi vai trò; chỉ cập nhật mẫu/avatar của hồ sơ đã có. Xóa cần một nhân viên cụ thể, bỏ API xóa DB không có ID. Xóa nhiều từ UI chỉ tạo job cho danh sách đã xác nhận, từng nhân viên độc lập; có thể hoàn thành một phần, phần lỗi vẫn pending. Không tác động hồ sơ/tài khoản/chấm công/sức khỏe/cảnh báo.
- Batch xung đột giữ nguyên và chặn batch mới cùng nhân viên cho tới khi xử lý. GUI đăng ký có nút **Lưu trữ batch chờ của ID này**, xác nhận trước khi chuyển sang `archived`; bản batch được giữ nguyên, DB không đổi. Batch đã `db_saved` phải thử refresh, không được lưu trữ qua nút này. Batch hỏng không tự xóa/bỏ qua; giữ file để kiểm tra.
- `UiWorker` dùng executor và hàng đợi: worker không gọi Tkinter/after/widget. Load model, DB, sync, kiểm tra service và callback train trả kết quả để main thread cập nhật. `FramePump` riêng đọc camera/detect; Tkinter chỉ đọc snapshot mới, không chờ HTTP/inference. Khi mất frame: reset bộ đếm và bỏ ảnh preview cũ. Canvas tái sử dụng một item ảnh, không tạo vô hạn. Đóng cửa sổ hủy timer/callback chờ; việc ghi DB đã chạy được kết thúc với batch bền vững, không gọi widget đã hủy.
- Camera mặc định dùng relay; `auto` cũ cũng không tự mở camera vật lý khi service tạm mất. Chỉ `PBL4_CAMERA_MODE=local` mở thiết bị trực tiếp; camera_id khác 0 yêu cầu local rõ ràng. Đọc relay kiểm tra HTTP 200, JPEG, dung lượng/kích thước, timeout, không theo redirect; bearer nội bộ không gửi qua environment proxy. Session/camera được worker sở hữu và release khi dừng.
- PHP `CameraFrameClient` kiểm tra status và JPEG/dimensions, giới hạn đọc 5 MiB, không theo redirect; HTTP 500 có JPEG không được coi là frame tốt.
- Regression phát hiện Windows có thể giữ handle gallery tạm thời làm `os.replace` lỗi. `atomic_write` retry PermissionError tối đa 2 giây trên Windows; không truncate file cũ. Lỗi vĩnh viễn vẫn báo lỗi và giữ file cũ. Có test cho cả retry thành công và thất bại có giới hạn.

**Nghiệm thu cuối:**

1. `python -B -m unittest discover -s pbl4-face-ai/tests -q` — **42 tests PASS**. Gồm hồi quy Task 1–3, bốn tests thread/close/camera pump mới và hai tests atomic replace trên Windows. Suite gallery/storage chạy lặp thêm **5 lần đều PASS** sau khi sửa lỗi chia sẻ file.
2. `C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B tools/test_ai_enrollment.py --extra-site pbl4-face-ai/.venv/Lib/site-packages -q` — **8 Flask tests PASS**.
3. `python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe --desktop-python C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe --desktop-site pbl4-face-ai/.venv/Lib/site-packages` — **PASS**:
   - Toàn bộ migration/attendance/enrollment DB regression cũ, **43 HTTP chấm công + 42 HTTP enrollment/camera**. Năm camera checks thêm gồm JPEG đúng bytes và từ chối status lỗi, redirect, ảnh giả, ảnh quá lớn.
   - **14 desktop/runtime tests PASS, không skip**: ảnh/vector theo cặp, năm pose, khác người, pending offline/restart, không phát hành mẫu chưa xác nhận, DB commit + refresh lỗi chỉ retry đọc, giữ batch hỏng/xung đột, archive giữ nguyên bytes, chốt phiên bản trước capture, GUI capture methods chạy headless, CLI hủy/release, relay HTTP và local/auto.
   - Một test DB thật gồm PyMySQL transaction, exact replay giữ ID mẫu, xung đột với đăng ký mới, rollback replace/delete khi avatar lỗi, không tự tạo NV, không đổi tên/vai trò, delete replay, reconciliation và bảo toàn số dòng lịch sử/tài khoản. Nhân viên khác vẫn đồng bộ được khi có job xung đột.
4. **45 PHP lint PASS**, **36 Python thay đổi/mới AST PASS**, `git diff --check` không lỗi whitespace (còn cảnh báo LF/CRLF .gitignore).
5. Lần đầu test relay thất bại do test harness nạp lại requests/CookieJar trong patch sys.modules; đã sửa import trước khi patch. Một lần test đa process bắt lỗi Windows replace nêu trên; đã sửa và stress lại đạt. Runner hiện capture output của Python native để không mất log khi gọi từ Python MSYS.

**Môi trường/bảo toàn:**

- MariaDB 10.4.32 instance tạm, random port khác 3306, PHP 8.0.30; PyMySQL/NumPy/Pillow/requests thật bằng Python runtime 3.12, reuse thư viện pure Python từ venv. Runner terminate/wait process của mình và xóa temp khi thoát. Không query/ghi DB dự án, không migration thật, không cài dependency hoặc sửa virtualenv. Không kiểm tra process toàn hệ thống bằng CIM (lần trước bị từ chối quyền).
- Inference và camera được giả lập; Tkinter chỉ import và test methods/helper headless, **chưa mở/kiểm chứng GUI thực tế**, chưa webcam/ESP32/InsightFace thật. Chưa số đo FPS/độ chính xác/hiệu chỉnh pose. Không tuyên bố camera driver hết treo; đọc local bị treo chỉ được cách ly trong worker daemon, không thể cưỡng bức hủy driver an toàn.
- DB offline vẫn có thể dùng gallery đã xác nhận trước đó; không có thu hồi nhận diện offline tức thời. Refresh thủ công/startup/sau sync đã có, chưa có lịch reconciliation nền định kỳ. Các process nhận diện phải dùng cùng file gallery; triển khai AI service trên máy khác cần đồng bộ file hoặc gọi refresh ở máy đó, chưa nghiệm thu liên máy.
- Venv trỏ Python 3.11 không tồn tại vẫn chưa sửa. Chưa Docker PHP 8.2/MariaDB 10.11/Apache runtime. Lifecycle collector/train và kiểm thử train thuộc Task 5; chưa tự chạy collector/train thật trong Task 4.
- Giữ toàn bộ dữ liệu `data/registered` cũ; không xóa/rename batch thật khi test. Outbox/pending/receipts/archived mới được ignore Git; nên giữ cùng dữ liệu dự án khi sao lưu. Chưa thêm commit/push, không reset/revert/clean.

**Cách tiếp tục thao tác (trong `pbl4-face-ai`, bằng Python đã cấu hình đủ dependency):**

- Tạo hồ sơ nhân viên trên Web trước. `python src/register.py refresh` đọc gallery DB; `python src/register.py webcam --id SV001 --name "Tên"` thu đủ năm hướng; `folder --id ... --name ... --images ...` dùng năm ảnh đủ pose. Tên nhập không đổi hồ sơ Web.
- `python src/register.py retry` thử batch chờ; thành công trả exit 0, còn pending trả 2. GUI đăng ký/dashboard có nút retry. Nếu xung đột: làm mới danh sách, kiểm tra batch rồi xác nhận lưu trữ qua GUI trước khi đăng ký lại. Không sửa `expected_revision` để ép ghi đè.
- CLI import `scripts/sync_faces_to_db.py` mặc định chỉ xem kế hoạch; `--apply` đọc DB trước, kiểm tra mọi folder năm pose trước khi stage, không còn fallback một mean embedding. Import lỗi vẫn giữ dữ liệu/batch đã có.
- Muốn dùng camera vật lý trực tiếp: dừng service đang sở hữu thiết bị rồi cấu hình `PBL4_CAMERA_MODE=local`; còn lại dùng relay. `.env.example` đã có mẫu mode và URL; `.env` thật không đổi.

**Files mới Task 4:** `pbl4-face-ai/src/enrollment_samples.py`, `src/desktop_enrollment.py`, `src/ui_worker.py`, `tests/test_desktop_threads.py`, `tools/test_desktop_runtime.py`.

**Files sửa Task 4:** `.gitignore`, `.env.example`; `pbl4-face-ai/src/face_sync.py`, `src/gallery_payload.py`, `src/camera_source.py`, `src/atomic_storage.py`, `src/register.py`, `gui_register.py`, `gui.py`, `scripts/sync_faces_to_db.py`, `tests/test_enrollment_store.py`; `DoAn_ChamCong_AI/Service/CameraFrameClient.php`; `tools/test_isolated_database.py`, `tools/test_http_enrollment.py`; checkpoint và báo cáo.

**Tiếp theo:** Task 5 — collector/train, metadata, split theo người/phiên, lưu model và validation. Chỉ bắt đầu khi người dùng yêu cầu tiếp tục. Đọc nhật ký Task 4 này trước; giữ yêu cầu từng task tuần tự và bảo toàn mọi thay đổi chưa commit.


### Task 5 — collector/train, metadata, split và model artifact, hoàn tất ngày 20/10/2026

**Phạm vi:** thu dữ liệu trạng thái AI 2, schema/timing/feature dùng chung, tách train/test theo người/phiên, lưu model cùng metadata, xác thực inference và lifecycle tiến trình collector/train trong dashboard. Không bắt đầu Task 6 upload/firmware/cấu hình/CI.

**Lỗi đã sửa và hành vi cuối:**

- Collector bắt buộc `--subject` là mã giả danh ổn định; không dùng `anonymous`, `legacy`, `unknown` hoặc ID/path tùy ý. Mỗi lần chạy có session UUID v4, mỗi chuỗi có sequence UUID v4, thời gian UTC có timezone và `label_source=operator_manual`. Nhãn là lựa chọn người vận hành, không tự suy từ EAR.
- Dataset mặc định mới `data/status_dataset_v2.csv`; không sửa/append vào dataset legacy bằng metadata giả. Schema đúng thứ tự gồm bảy features, nhãn, subject/session/sequence, thời gian, khoảng mục tiêu và hai khoảng đo thực tế, feature_schema, label_source. Đọc dữ liệu từ chối NaN/inf, boolean, feature bất nhất, nhãn sai, UUID/thời gian sai, một session thuộc nhiều subject hoặc sequence trùng.
- State collector chỉ tạo row khi đủ ba quan sát hợp lệ cách nhau 300–600 ms. Mất mặt/sai góc/NaN/gap dài/quay ngược đồng hồ hủy chuỗi; nhấn đổi nhãn hoặc Q bỏ chuỗi đang dở. Không nối ảnh cũ sau mất mặt và không pad frame. Frame quá sớm không được đếm thêm. `UnifiedAttendanceEngine` dùng cùng interval và hủy phiên `SNAPSHOT_GAP_EXCEEDED` nếu quá 600 ms giữa ảnh chấm công; streaming predictor cũng dùng timing này.
- `status_sequence_v2` chuẩn hóa pitch quanh hướng chính diện 180 độ và unwrap pitch/roll: +179/-179 không còn thành chuyển động 358 độ; mean_pitch trong vector là độ lệch quanh chính diện. Có kiểm tra overflow dù đầu vào từng số hữu hạn. Collector/train/inference dùng cùng thứ tự/tính toán feature.
- MediaPipe yêu cầu đúng một mặt (cho phép detector thấy tối đa hai để từ chối nhiều mặt). Geometry mắt/miệng suy biến, landmarks thiếu/không hữu hạn và solvePnP thất bại không biến thành đặc trưng bình thường/nhãn chắc chắn.
- Mỗi row hoàn chỉnh được ghi journal atomic trước khi merge CSV. Khóa file liên tiến trình giữ toàn bộ đọc-validate-merge-atomic replace; không mất dòng khi nhiều collector cùng ghi. Replay sequence giống nhau không nhân đôi; nội dung khác bị từ chối. Merge lỗi giữ journal tại `<tên_csv>.pending`; lần chạy sau/recover sẽ ghi tiếp. Journal hỏng/xung đột được giữ, không tự bỏ qua/xóa.
- Train đọc CSV đúng một snapshot bytes và hash chính snapshot đó. Không có fallback chia ngẫu nhiên theo dòng. Mặc định split theo subject; phải có ít nhất hai subject, 18 chuỗi và đủ ba nhãn ở cả train/test (train mỗi nhãn ít nhất hai, test mỗi nhãn ít nhất một). Tìm split nhóm có seed, không chia một session/người sang cả hai bên. Thiếu dữ liệu/metadata trả exit 1 và giữ model cũ.
- `--split session` phải chọn rõ; metadata ghi `held_out_sessions_not_new_people`, không nhận là đánh giá người mới. Subject/session và provenance chỉ dựa mã giả danh do người vận hành nhập, không phải bằng chứng định danh sinh trắc của người tham gia.
- Artifact một file gồm model + metadata: feature schema/order, ba nhãn, timing, dataset SHA-256, seed/tham số, train/test subjects/sessions/class counts, accuracy/balanced accuracy/macro F1/confusion/report và phiên bản Python/NumPy/scikit-learn/joblib. Trainer giữ khóa theo output và atomic replace sau fit/evaluate/serialize; không còn hai lần ghi model/sidecar dễ lệch. Sidecar cũ không còn được dùng, không tự xóa file cũ.
- Loader kiểm tra schema, số features/classes, timing và đúng phiên bản scikit-learn trước khi dùng artifact. Predictor load/validate model trước khi khởi tạo MediaPipe để không rò tài nguyên khi model lỗi; xác thực toàn bộ vector xác suất thay vì chỉ kiểm tra giá trị lớn nhất. Buffer/smoothing reset khi quan sát hoặc timing không hợp lệ.
- **Thay đổi tương thích có chủ ý:** model RF legacy không có bundle metadata hoặc dùng feature cũ bị từ chối; không nạp bằng feature v2 để đoán tiếp. File model/dataset hiện có vẫn được giữ nguyên. Cần thu dataset v2 đủ nhóm và train model tương thích trong môi trường dự án trước khi chạy AI 2 thật. Task này chỉ train vào thư mục tạm, không thay model triển khai.
- Dashboard hỏi mã người trước khi thu, bỏ hướng dẫn EAR quyết định nhãn, chỉ gọi train khi collector có mẫu mới và exit 0; cancel/lỗi/không mẫu không train trên dataset cũ. Thông báo phân biệt dataset đã lưu nhưng train chưa đủ điều kiện với train thành công. Thu/train dùng worker riêng khỏi tác vụ DB/health, callback trở về main thread. `ProcessRunner` sở hữu các child do dashboard tạo, dừng/reap chúng khi đóng và chặn child mới sau close; không tác động process bên ngoài.
- Collector và CLI test inference dùng cleanup bảo đảm đóng extractor/camera/window kể cả lỗi. Test realtime dùng camera relay adapter chung thay vì tự mở camera thứ hai. CSV/journal/model thật không bị truy cập ghi trong kiểm thử.

**Nghiệm thu:**

1. `python -B -m unittest discover -s pbl4-face-ai/tests -q` — **58 tests PASS**. Bao gồm 42 hồi quy trước + 15 tests metadata/collector/timing/split/journal/concurrent CSV/process cleanup + một hồi quy chấm công quá gap. Có sáu child cùng ghi CSV, retry journal, replay/conflict, legacy không bị sửa, không rò subject/session, angle wrap/overflow và dừng child đang chạy.
2. `C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B tools/test_status_training_runtime.py --deps C:/Users/admin/AppData/Local/Temp/pbl4-training-deps-task5-20261020 -v` — **11 tests PASS**:
   - RandomForestClassifier thật, joblib fit/dump/load thật; 72 chuỗi tổng hợp của sáu subject, holdout 48 train/24 test. Kiểm tra hash snapshot, disjoint nhóm và JSON metadata; cùng seed lặp được split/metrics.
   - Split session cùng người phải chọn rõ; dữ liệu legacy/thiếu nhóm bị từ chối và giữ artifact cũ. Inject lỗi lưu giữ nguyên artifact cũ. Model legacy/sai schema/order/interval/classes/version bị từ chối.
   - Predictor đọc bundle thật, dùng feature/timing chung, trả Buffering/Unknown cho trường hợp không hợp lệ; kiểm tra xác suất sai kích thước/tổng/NaN/âm.
   - Collector entry loop chạy với camera/extractor/UI giả, ghi đúng chuỗi hoàn chỉnh, hủy chuỗi dở không ghi, lỗi vẫn release; multi-face/geometry lỗi bị từ chối. Dashboard orchestration được test headless: cancel/lỗi không gọi train, mọi trạng thái đều kết thúc busy.
3. **42 file Python thay đổi/mới AST PASS**; `git diff --check` không lỗi whitespace, chỉ cảnh báo LF/CRLF .gitignore. Không sửa PHP/DB nên không chạy lại DB suite dài; bằng chứng PHP/HTTP ở Task 2–4 vẫn là mốc trước, không gọi là đã chạy lại trong Task 5.

**Môi trường kiểm thử và quyền:**

- Python mặc định MSYS 3.12 chạy bộ stdlib; Python runtime 3.12 chạy RF thật với NumPy **2.3.5**, scikit-learn **1.7.2**, SciPy **1.16.2**, joblib **1.5.2**, threadpoolctl **3.6.0**. Dataset/model test nằm trong TemporaryDirectory và được thu dọn; không dùng model/dataset dự án.
- Runtime thiếu sklearn/SciPy nên tải đúng các wheel vào thư mục TEMP, không cài vào runtime/venv dự án. Sandbox chặn mạng; đã dùng tool xin phép chạy pip ngoài sandbox. Lần đầu tải được nhưng Windows chặn ghi vào temp do sandbox tạo; lần hai dùng `C:/Users/admin/AppData/Local/Temp/pbl4-training-deps-task5-20261020` thành công. Windows ACL chặn sandbox đọc các file của installer, nên lệnh test RF đã được cho phép chạy ngoài sandbox; prefix lệnh test cụ thể đã lưu. Không phải test failure của code dự án.
- Thư viện test tạm được giữ tại đường dẫn trên để tái chạy kiểm thử (và có cache pip); thư mục `C:/Users/admin/AppData/Local/Temp/pbl4-training-deps-4c5rjrto` là đích thử lần đầu thất bại. Các thư mục này ngoài repo, không phải virtualenv dự án. Phiên tiếp theo không cần tải lại nếu còn dùng được; không tự dùng chúng làm môi trường production.
- Venv trỏ Python 3.11 thiếu vẫn chưa sửa. Chưa MediaPipe/InsightFace/camera/UI trực quan thật; detector/extractor camera trong tests là adapter giả. RF train thật chỉ dùng dữ liệu tổng hợp để kiểm tra phần mềm; không có kết luận độ chính xác, hiệu suất hoặc giá trị chẩn đoán trên người thật. Nhãn thủ công/chất lượng dữ liệu/độ tin cậy ID cần kiểm chứng trong thu thập thật.
- Chưa train/promote model mới vào `data/rf_status_model.pkl`; chưa sửa dataset legacy, DB, migration, firmware hoặc môi trường triển khai; chưa commit/push/reset/revert/clean.

**Cách chạy mới (sau khi có môi trường đủ thư viện, trong `pbl4-face-ai`):**

- `python scripts/collect_status.py --subject P01` ghi vào dataset v2. Dùng cùng mã cho cùng người ở mọi lần thu; mã khác cho người khác. Mỗi lần nhấn 1/2/3 ghi một chuỗi ba ảnh; Q kết thúc; không có mẫu mới trả exit 2.
- `python scripts/collect_status.py --subject P01 --recover` chỉ khôi phục journal, không mở camera. `--output <file.csv>` chọn dataset riêng; không append legacy schema.
- `python src/train_rf.py --data data/status_dataset_v2.csv --output data/rf_status_model.pkl` yêu cầu split subject mặc định. Dùng `--output <candidate.pkl>` để giữ thêm model thử riêng. `--split session` chỉ đánh giá phiên khác, không thay thế đánh giá người mới.
- Artifact v2 dùng cho inference và giữ metadata bên trong; loader yêu cầu phiên bản scikit-learn khớp. Không sửa metadata/schema hoặc xóa kiểm tra để ép dùng model legacy. Nếu thiếu dữ liệu đủ nhóm thì giữ model cũ nguyên trạng, thu thêm dữ liệu v2 trước.

**Files mới Task 5:** `pbl4-face-ai/src/status_dataset.py`, `src/status_training.py`, `src/status_model.py`, `src/process_runner.py`, `tests/test_status_dataset.py`; `tools/test_status_training_runtime.py`.

**Files sửa Task 5:** `.gitignore`; `pbl4-face-ai/scripts/collect_status.py`, `src/train_rf.py`, `src/sequence_features.py`, `src/status_features.py`, `src/predict_status.py`, `gui.py`, `unified_engine.py`, `tests/test_attendance.py`; checkpoint và báo cáo.

**Tiếp theo:** Task 6 — ESP32 upload, cấu hình/môi trường, hướng dẫn và CI/báo cáo tổng hợp. Chỉ bắt đầu khi người dùng yêu cầu tiếp tục; đọc trạng thái mới ở đầu và nhật ký này, không dùng bảng hash ngày 19/10 làm trạng thái hiện hành. Giữ yêu cầu từng task tuần tự, bảo toàn toàn bộ thay đổi chưa commit.


### Task 6 — runtime, webcam, ESP32 upload, cấu hình, hướng dẫn/CI — 20/10/2026

**Ủy quyền:** người dùng yêu cầu làm luôn các bước tiếp theo; xác nhận nguồn ảnh là webcam laptop hoặc USB. Làm trong Task 6 tuần tự sau Task 5, không mở task độc lập. Không commit/push/reset/revert/clean. Phần triển khai local và kiểm thử phần mềm đã làm xong; nghiệm thu RF v2/người thật/phần cứng/CI remote còn chờ.

**Đã hoàn tất:**

1. **Môi trường AI:** giữ nguyên `.venv` cũ bị hỏng; tạo `.venv-pbl4` bằng Python 3.12.14 x64, cài toàn bộ dependency. Thêm `requirements-runtime.txt` và `requirements-lock-win-py312.txt`; `requirements.txt` include profile runtime. NumPy 1.26.4, InsightFace 2.0, ONNX Runtime 1.22.1, OpenCV 4.11.0.86, MediaPipe 0.10.21, scikit-learn 1.7.2. `pip check` PASS, import và `mediapipe.solutions` PASS. Hai package OpenCV cùng build là yêu cầu upstream; cấu hình đã chạy thực tế. MPL cache nằm trong `.pbl4-run`, stdout/stderr Windows UTF-8; đã sửa lỗi emoji cp1252 làm service chết lúc khởi động.
2. **Inference thật:** InsightFace `buffalo_sc` lấy từ cache sẵn tại `%USERPROFILE%/.insightface/models/buffalo_sc`, CPU; `data/test_photo.jpg` phát hiện một mặt/embedding 512D. MediaPipe thật trả observation hợp lệ trên ảnh này. Không ghi lại ảnh/vector vào báo cáo; không ghi đè RF/dataset cũ. RF train regression chạy thật trên dữ liệu tổng hợp trong temp, không phải model triển khai.
3. **Web/DB thật:** sửa YAML sai `MYSQL_PASSWORD` trong Compose. `tools/check_services.py` chỉ in trạng thái/boolean, không lộ env. Phát hiện token Web cũ không khớp `.env` và thiếu bảng `AttendanceEvent`. Tạo backup **`.pbl4-run/backups/pbl4-before-attendance-migration-20261020-143748.sql` — 3.799.593 bytes**, kế hoạch/hash tại `.pbl4-run/live-update-plan.json`. `tools/manage_live_stack.py apply` kiểm tra backup/hash/migration/container ID/số dòng rồi áp dụng đúng migration cộng thêm `02_attendance_integrity.sql`; **13 bảng cũ/47 dòng giữ nguyên**, không reset dữ liệu/volume. Chỉ recreate container Web bằng image hiện có (`--no-build --no-deps`), giữ MariaDB. Xác nhận `AttendanceEvent` có **7 cột**, `ChamCong` đủ ba cột trạng thái, credential và internal token khớp `.env`. PHP runtime thật **8.2.34**, MariaDB container **10.11**. Đợt sửa này chỉ tạo schema thêm, không tạo sự kiện chấm công hoặc tài khoản trong DB dự án.
4. **Gallery/camera thật:** Web gallery có auth trả 200/14 mẫu. Sao lưu gallery local cũ theo hash nếu có rồi refresh thành công 3 hồ sơ. Webcam index 0/DirectShow đọc được frame bằng `tools/probe_camera.py` khi chạy ngoài sandbox; trong sandbox không đọc được. Dừng chính xác hai process do phiên tạo (kiểm tra PID/starttime/path), khởi động lại ngoài sandbox, Windows hidden window. AI `/internal/camera/frame` trả **200/JPEG/640×480**, ảnh chỉ trong RAM. PHP `CameraFrameClient` chạy trong Docker nhận JPEG thật thành công. Không lưu ảnh webcam hoặc thay dữ liệu đăng ký. `get_camera()` hỗ trợ `PBL4_CAMERA_ID` và `PBL4_CAMERA_BACKEND=dshow|msmf|auto`.
5. **Khởi động/dừng:** `tools/start_services.ps1` bật AI và receiver bằng venv mới, giữ log UTF-8 và ownership trong `.pbl4-run/services.json`, reuse dịch vụ khỏe, từ chối khởi tạo thêm khi PID đã ghi còn chạy nhưng không đáp ứng. `tools/stop_services.ps1` chỉ kill PID khớp executable/starttime. Đã sửa lỗi mảng JSON PowerShell 5 và lỗi cmdlet Stop-Process (dùng Process.Kill + WaitForExit sau kiểm tra ownership). `KHOI_DONG_PBL4.cmd` bật dịch vụ rồi mở Web; Docker/Web/DB cần chạy sẵn. Script khởi động không migration hoặc train. PowerShell syntax PASS; thực tế stop/start/reuse PASS.
6. **Upload receiver:** Flask factory, token riêng `PBL4_UPLOAD_TOKEN`, bind loopback mặc định, Bearer auth, JPEG decode thật, 5 MiB/16 triệu pixel, quota 1.000 ảnh/256 MiB được khóa giữa process, filename UUID, atomic write, SHA-256/timestamp, no-store, lỗi generic. Đầy trả 507 và giữ dữ liệu, không tự xóa. `.env` chỉ append upload token còn thiếu; giữ credential/internal token hiện có. Nhánh upload chưa nối vào attendance, không tự biến ảnh thành sự kiện.
7. **Firmware:** tách Wi-Fi/URL/token sang `wifi_config.h` ignore Git (giữ giá trị local); có `wifi_config.example.h`. Config camera zero-init, kiểm tra init/Wi-Fi/frame/JPEG/size, timeout connect/read, không redirect, Bearer upload token riêng, RAII trả frame, reconnect có chu kỳ, không log token/body. Chưa có Arduino CLI/ESP32 core để compile; chưa flash hoặc thử thiết bị thật.
8. **Bootstrap admin:** bỏ tài khoản/mật khẩu mặc định và cơ chế seed ghi đè mật khẩu khỏi `01_seed_init.sql`. Thêm CLI-only `DoAn_ChamCong_AI/tools/create_admin.php`, password 12–72 bytes/hash/transaction, tài khoản trùng trả lỗi và giữ mật khẩu cũ. Apache deny thư mục tools. **Chỉ sửa source cho setup mới; không đổi tài khoản đang có.** Kiểm thử bootstrap trên DB tạm xác nhận validation/create/refuse overwrite/hash/role. Apache thật trả 403 với `/tools/create_admin.php`, `/migration/01_seed_init.sql`, `/Model/Database.php`.
9. **Hướng dẫn/CI:** viết lại `pbl4-face-ai/docs/README.md` theo đúng entry point, venv, Docker, webcam, năm pose, pending, RF v2, upload, backup và giới hạn. Thêm `.github/workflows/regression.yml`: Python 3.12/PHP 8.2/MariaDB 10.11 service riêng cổng 33307; `tools/test_ci_database.py` chỉ chạy khi `CI=true`, `PBL4_TEST_DATABASE=isolated`, loopback và đúng cổng. Workflow chưa chạy trên GitHub; chưa chứng nhận CI xanh. Compose đã được Docker parse/config --quiet PASS. Máy không có PyYAML; không tính lần thử import yaml bị thiếu là đã parse workflow. Không cài thêm dependency chỉ để parse YAML.

**Kết quả đã chạy lại bằng venv mới:**

- `python -B -m unittest discover -s pbl4-face-ai/tests -q`: **58 PASS**.
- `python -B tools/test_ai_enrollment.py -q`: **8 PASS**, Flask thật/detector giả.
- `python -B tools/test_upload_receiver.py -v`: **8 PASS**, JPEG tạo trong temp; auth/media/empty/invalid/truncated/size/dimensions/hash/filename/quota/storage error và tám request đồng thời tranh quota.
- `python -B tools/test_status_training_runtime.py -q`: **11 PASS**, sklearn/joblib thật trên dữ liệu tổng hợp. `--deps` giờ tùy chọn; mặc định dùng venv hiện tại.
- `python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe --desktop-python D:/DTDN_DOC/HK5/PBL4/pbl4-face-ai/.venv-pbl4/Scripts/python.exe`: **PASS**, không skip; **43 HTTP attendance + 42 HTTP enrollment/camera**, DB transaction/concurrency/migration regressions, **14 desktop/runtime tests**, bootstrap admin. MariaDB 10.4.32/PHP 8.0.30 trong runner tạm; không coi đây là toàn bộ suite trên target 10.11/8.2. Target Docker 10.11/8.2 mới kiểm tra schema/auth/gallery/health/camera và Apache 403 thật.
- Tổng **99 tests unittest + 85 checks HTTP PASS**, cộng các integration DB/bootstrap. **46 PHP lint PASS; 49 file Python sửa/mới AST PASS; 1 JS sửa node --check PASS; 2 PowerShell syntax PASS; pip check PASS**. `git diff --check` không lỗi whitespace, còn cảnh báo LF/CRLF `.gitignore`.
- Một lần kiểm tra syntax dừng sớm vì môi trường thiếu module yaml; đã chạy lại AST/PHP/JS độc lập thành công. Không tính lượt dừng sớm là PASS. Lỗi sandbox đọc camera và lỗi script lifecycle đã tìm nguyên nhân, sửa và kiểm tra lại như trên.

**Đang chạy / bảo toàn:**

- Web <http://localhost:8080>, AI <http://127.0.0.1:5001/health>, receiver <http://127.0.0.1:5000/> đều HTTP 200. AI `model_ready=true` ở startup. Camera do AI giữ; desktop/collector phải dùng relay.
- AI/upload PID và starttime ở `.pbl4-run/services.json` là nguồn ownership hiện hành; không hard-code PID để kill ở phiên sau. Dịch vụ chạy ngoài sandbox để đọc camera, nên thao tác lifecycle có thể cần escalation trong tool. Không dừng camera ngoài phiên bằng probe khi AI đang giữ.
- `.env`, `wifi_config.h`, `.venv-pbl4`, `.pbl4-run` (SQL backup/log/state), gallery/models/dataset/ảnh/outbox nằm trong ignore. Giữ backup này khi sao lưu workspace; không log secret hoặc dữ liệu sinh trắc. Không xóa bốn báo cáo đã xóa, không xóa README hoặc thay file model/dataset legacy.
- Không có thao tác ghi đang dở. Mã/kiểm thử local đã lưu; chưa stage/commit/merge/push. Lệnh Git chỉ kiểm tra trạng thái/diff/ignore.

**Còn cần làm — theo thứ tự, không tuyên bố hệ thống đã nghiệm thu toàn bộ:**

1. Với ít nhất hai người thật, thu `status_dataset_v2.csv` bằng collector (P01/P02 ổn định, đủ Normal/Fatigue/Exhausted theo nhãn vận hành; tối thiểu 18 chuỗi và đủ lớp ở cả nhóm train/test). Hiện chưa có dữ liệu v2 đủ điều kiện. Không tự bịa người/nhãn/metadata; không dùng dữ liệu tổng hợp làm artifact triển khai. Train v2 rồi kiểm tra chất lượng/holdout trước chạy attendance thật. GUI dashboard đã có thao tác thu/train; hướng dẫn CLI trong README.
2. Nghiệm thu thao tác Web/GUI có người trước camera: đăng ký đủ năm pose; nhận diện đúng/sai/Unknown, một phiên vào/ra/replay với model v2 và bằng chứng. Chưa đăng nhập/chụp đăng ký người thật hoặc tạo event thật tự động. Hiện gallery 3 hồ sơ/14 mẫu có thể có hồ sơ thiếu năm hướng cũ.
3. Arduino build/flash đúng board AI Thinker và thử ESP32 upload; producer MAX30102/Serial toàn luồng chưa có nghiệm thu. Quota receiver cần người vận hành sao lưu/giải phóng khi đầy; chưa có retention tự động.
4. Push/PR chỉ khi người dùng yêu cầu cho đợt sửa này, rồi quan sát workflow CI mới. Chưa kiểm tra remote runner/Linux hoặc compile firmware; không hứa pipeline đã xanh.
5. Giới hạn còn: chưa benchmark FPS/độ chính xác/pose và hiệu chỉnh ngưỡng trên người; offline gallery có thể cũ đến khi refresh, chưa thu hồi tức thời hoặc reconciliation nền/liên máy. Đây là giới hạn vận hành, không tự tạo số đo/kết luận y tế.

**Các file chính mới/sửa Task 6:** profile/lock requirements, runtime_config, camera config trong ai_web_service; Compose, `.env.example`, `.gitignore`; receiver/firmware/config example; seed/CLI admin và Apache deny; `tools/check_services.py`, `manage_live_stack.py`, `probe_camera.py`, `start_services.ps1`, `stop_services.ps1`, `test_upload_receiver.py`, `test_admin_bootstrap.py`, `test_ci_database.py`; runner isolated/training; workflow; launcher CMD; README/checkpoint/báo cáo. Các thay đổi Task 1–5 được giữ.

**Chốt trạng thái:** Git có 91 file: 36 tracked modified, 4 tracked deleted và 51 untracked, không có thao tác ghi dở. Kiểm tra cuối xác nhận Web/AI/upload HTTP 200, InsightFace model_ready=true, số dòng của mọi bảng cũ không đổi, AttendanceEvent chưa có event thử, container MariaDB và SHA-256 backup giữ nguyên. Một assertion tìm tiêu đề checkpoint dùng literal Unicode qua PowerShell bị lệch encoding; đổi sang kiểm tra prefix ASCII rồi chạy lại PASS, nội dung checkpoint UTF-8 được giữ nguyên.


### Hậu kiểm trang chấm công và chốt commit — 20/10/2026

Người dùng báo ảnh `/?action=attendance` lỗi tải dữ liệu và yêu cầu commit sau khi sửa. Đã tái hiện bằng SELECT trên PHP 8.2/MariaDB 10.11 thật: `SQLSTATE[42S22] 1054 Unknown column 'CLV.TrangThai' in 'ON'`. Đây là lỗi JOIN trong AttendanceModel::findDaily, không phải mất kết nối DB. Bộ kiểm thử trước tập trung API/enrollment nên chưa gọi trang danh sách admin, để lọt nhánh query này.

**Đã sửa:** JOIN bảng ca sau khi chọn bản ghi chấm công; chỉ dùng alias đã khai báo, lấy ca đã ghi trong ChamCong ưu tiên hơn phân ca hiện tại, giữ được ca lịch sử bị vô hiệu. Nhân viên chưa chấm công vẫn xuất hiện; ca phân công chưa có bản ghi chỉ hiện khi đang hoạt động. Thông báo lỗi trang đổi thành yêu cầu thử lại, không khẳng định DB mất kết nối khi mọi loại exception đều đi qua cùng catch.

**Kiểm chứng:** thêm `tests/integration_attendance_read.php` (transaction/rollback trên DB tạm): active/inactive/unassigned, bản ghi mới nhất khi trùng timestamp, ca gốc sau đổi phân công, ranh giới ngày, lọc ID/tên và phân trang daily/history. Thêm bốn request trang admin có login thật vào HTTP runner: mặc định, một ngày, khoảng ngày, lọc/phân trang. Runner DB đã chạy lại PASS: schema/migration/concurrency/rollback/read-model, **43 HTTP attendance + 46 enrollment/admin-page = 89 checks**, **14 desktop/runtime tests không skip**, bootstrap admin. Sửa fixture để đọc password DB test từ môi trường, phù hợp CI có password riêng.

Trong Docker thật, gọi trực tiếp controller/template với session giả chỉ trong bộ nhớ CLI cho ba biến thể daily/history/filter: **render HTTP status 200, không notice lỗi, PHP 8.2.34**. Không tạo session HTTP/tài khoản hoặc sửa DB dự án. Không tuyên bố đã thao tác trình duyệt Chrome của người dùng; người dùng tải lại trang hiện tại để thấy sửa đổi qua bind mount, không cần rebuild container.

**Kiểm tra trước commit:** 49 Python AST, 16 PHP sửa/mới lint, 1 JS syntax PASS; diff whitespace không lỗi (còn cảnh báo LF/CRLF .gitignore). Quét giá trị password/token .env đủ dài trong phần source thêm mới PASS, các secret/local data vẫn ignore. Một lần quét bị lỗi decode cp1252 của Git subprocess; đã đặt encoding UTF-8 và chạy lại PASS. 92 file thuộc gói thay đổi (36 modified, 4 deleted, 52 untracked) trước stage; không có file sửa dở. Toàn bộ thay đổi Task 1–6 và hậu kiểm này thuộc commit theo yêu cầu mới; hash thực tế xem `git log -1`. Không reset/revert/clean hoặc push. Các mục “chưa commit” phía trên là lịch sử trước yêu cầu mới.
