"""
services.py — Tầng nghiệp vụ (Business Logic Layer)
=====================================================
Nhận dữ liệu thô từ database, áp dụng quy tắc nghiệp vụ,
trả về dict/list sẵn sàng cho JSON response.

Quy tắc chấm công (KHÔNG có thời gian ân hạn):
    GioVao <= GioBatDau  -> Đúng giờ
    GioVao >  GioBatDau  -> Đi trễ

    GioRa  >= GioKetThuc -> Đúng giờ
    GioRa  <  GioKetThuc -> Về sớm
    GioRa  is None       -> Đang làm việc
"""

from datetime import date, datetime, time
import os
import database
from face_matching import aggregate_gallery, identify_embedding, verify_embedding
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None


# ============================================================
# Helper: Encode frame camera sang JPEG bytes
# ============================================================

def encode_frame_to_jpg(frame):
    """
    Encode numpy frame thành bytes JPEG để lưu vào DB.

    Không lưu raw frame;
    dùng JPEG quality 85 để giảm kích thước.

    Trả về bytes hoặc None.
    """
    if frame is None or _cv2 is None:
        return None

    success, buffer = _cv2.imencode(
        ".jpg",
        frame,
        [_cv2.IMWRITE_JPEG_QUALITY, 85],
    )

    if not success:
        return None

    return buffer.tobytes()


# ============================================================
# Hàm tính trạng thái chấm công
# ============================================================

def _to_time(val):
    """
    Chuyển nhiều kiểu dữ liệu về datetime.time.
    Hỗ trợ: datetime.time, datetime.timedelta (SQL Server TIME),
            datetime.datetime, str "HH:MM:SS".
    """
    if val is None:
        return None

    # timedelta — SQL Server trả TIME dưới dạng timedelta
    try:
        from datetime import timedelta
        if isinstance(val, timedelta):
            total_sec = int(val.total_seconds())
            h = total_sec // 3600
            m = (total_sec % 3600) // 60
            s = total_sec % 60
            return time(h, m, s)
    except Exception:
        pass

    if isinstance(val, time):
        return val

    if isinstance(val, datetime):
        return val.time()

    if isinstance(val, str):
        try:
            parts = val.split(":")
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        except Exception:
            return None

    return None


def calc_attendance_status(gio_bat_dau, gio_ket_thuc, gio_vao, gio_ra):
    """
    Tính trạng thái chấm công theo quy tắc nghiệp vụ.

    Tham số:
        gio_bat_dau  : giờ bắt đầu ca (time hoặc timedelta)
        gio_ket_thuc : giờ kết thúc ca
        gio_vao      : giờ nhân viên vào (datetime hoặc None)
        gio_ra       : giờ nhân viên ra (datetime hoặc None)

    Trả về dict:
        TrangThaiVao      : "Đúng giờ" | "Đi trễ" | "Chưa chấm công"
        TrangThaiRa       : "Đang làm việc" | "Đúng giờ" | "Về sớm"
        TrangThaiTongHop  : chuỗi gộp ngắn gọn
    """
    # Chuyển ca về time
    bat_dau  = _to_time(gio_bat_dau)
    ket_thuc = _to_time(gio_ket_thuc)

    # Chưa chấm công
    if gio_vao is None:
        return {
            "TrangThaiVao":     "Chưa chấm công",
            "TrangThaiRa":      "--",
            "TrangThaiTongHop": "Chưa chấm công",
        }

    t_vao = gio_vao.time() if isinstance(gio_vao, datetime) else gio_vao

    # Trạng thái vào
    if bat_dau is not None and t_vao > bat_dau:
        trang_thai_vao = "Đi trễ"
    else:
        trang_thai_vao = "Đúng giờ"

    # Trạng thái ra
    if gio_ra is None:
        trang_thai_ra = "Đang làm việc"
    else:
        t_ra = gio_ra.time() if isinstance(gio_ra, datetime) else gio_ra
        if ket_thuc is not None and t_ra < ket_thuc:
            trang_thai_ra = "Về sớm"
        else:
            trang_thai_ra = "Đúng giờ"

    # Tổng hợp
    if trang_thai_ra == "Đang làm việc":
        tong_hop = f"{trang_thai_vao} · Đang làm việc"
    elif trang_thai_vao == "Đúng giờ" and trang_thai_ra == "Đúng giờ":
        tong_hop = "Hoàn thành"
    else:
        tong_hop = f"{trang_thai_vao} · {trang_thai_ra}"

    return {
        "TrangThaiVao":     trang_thai_vao,
        "TrangThaiRa":      trang_thai_ra,
        "TrangThaiTongHop": tong_hop,
    }


# ============================================================
# NhanVien
# ============================================================

def fetch_dashboard_data():
    users = database.get_all_users()
    return [{"MaNV": row[0], "HoTen": row[1]} for row in users]


# ============================================================
# CaLamViec
# ============================================================

def fetch_all_shifts():
    """Trả về danh sách ca làm việc."""
    try:
        rows = database.get_all_shifts()
        result = []
        for row in rows:
            gbd = _to_time(row[2])
            gkt = _to_time(row[3])
            result.append({
                "MaCa":       row[0],
                "TenCa":      row[1],
                "GioBatDau":  gbd.strftime("%H:%M") if gbd else "--",
                "GioKetThuc": gkt.strftime("%H:%M") if gkt else "--",
            })
        return result
    except Exception as e:
        print(f"[services] Loi lay ca lam viec: {e}")
        return []


# ============================================================
# PhanCaNhanVien
# ============================================================

def assign_shift(data):
    """
    Phân ca cho nhân viên.
    data: {"MaNV": int, "MaCa": int, "NgayLamViec": "YYYY-MM-DD" (tùy chọn)}
    """
    ma_nv = data.get("MaNV")
    ma_ca = data.get("MaCa")
    ngay  = data.get("NgayLamViec")

    if ma_nv is None or ma_ca is None:
        return False, "Thiếu MaNV hoặc MaCa"

    if ngay is None:
        ngay = date.today().isoformat()

    try:
        database.assign_shift(ma_nv, ma_ca, ngay)
        return True, "Phân ca thành công"
    except Exception as e:
        print(f"[services] Loi phan ca: {e}")
        return False, f"Lỗi phân ca: {e}"


# ============================================================
# ChamCong — Check-in / Check-out
# ============================================================

def process_attendance(ma_nv, ma_tb=1, image_bytes=None):
    """
    Xử lý chấm công theo quy tắc:

    1. Lấy ca hôm nay của nhân viên.
       Nếu không có ca → trả lỗi rõ.

    2. Lấy bản ghi ChamCong hôm nay.
       - Không có bản ghi → CHECK-IN
       - Có bản ghi, GioRa=NULL → CHECK-OUT
       - Có bản ghi, GioRa!=NULL → COMPLETED

    3. CHECK-IN thành công → set_active_employee (caller xử lý)
       CHECK-OUT thành công → clear_active_employee nếu đúng người

    image_bytes: bytes JPEG hoặc None.
                 Nếu None, chấm công vẫn hoạt động bình thường;
                 AnhVao / AnhRa sẽ lưu NULL.

    Trả về dict:
        action   : "checkin" | "checkout" | "completed" | "error"
        status   : "success" | "error"
        message  : chuỗi mô tả
        MaCa     : ca làm việc (nếu có)
    """
    today = date.today().isoformat()

    # --- Lấy ca ---
    try:
        shift_row = database.get_employee_shift(ma_nv, today)
    except Exception as e:
        return {
            "action":  "error",
            "status":  "error",
            "message": f"Lỗi truy vấn ca: {e}",
        }

    if shift_row is None:
        return {
            "action":  "error",
            "status":  "error",
            "message": "Nhân viên chưa được phân ca hôm nay",
        }

    ma_ca        = shift_row[0]
    ten_ca       = shift_row[1]
    gio_bat_dau  = shift_row[2]
    gio_ket_thuc = shift_row[3]

    # --- Lấy bản ghi hôm nay ---
    try:
        today_rec = database.get_today_record(ma_nv)
    except Exception as e:
        return {
            "action":  "error",
            "status":  "error",
            "message": f"Lỗi truy vấn chấm công: {e}",
        }

    # --- CHECK-IN ---
    if today_rec is None:
        try:
            database.insert_checkin(ma_nv, ma_ca, ma_tb, image_bytes)
            return {
                "action":  "checkin",
                "status":  "success",
                "message": f"Chấm công vào thành công — Ca: {ten_ca}",
                "MaCa":    ma_ca,
                "TenCa":   ten_ca,
            }
        except Exception as e:
            return {
                "action":  "error",
                "status":  "error",
                "message": f"Lỗi check-in: {e}",
            }

    ma_cc  = today_rec[0]
    gio_vao = today_rec[1]
    gio_ra  = today_rec[2]

    # --- CHECK-OUT ---
    if gio_vao is not None and gio_ra is None:
        try:
            database.update_checkout(ma_cc, image_bytes)
            return {
                "action":  "checkout",
                "status":  "success",
                "message": f"Chấm công ra thành công — Ca: {ten_ca}",
                "MaCa":    ma_ca,
                "TenCa":   ten_ca,
            }
        except Exception as e:
            return {
                "action":  "error",
                "status":  "error",
                "message": f"Lỗi check-out: {e}",
            }

    # --- COMPLETED ---
    return {
        "action":  "completed",
        "status":  "success",
        "message": "Đã hoàn tất chấm công hôm nay",
        "MaCa":    ma_ca,
        "TenCa":   ten_ca,
    }



# ============================================================
# ChamCong — Dashboard Summary
# ============================================================

def fetch_attendance_dashboard(target_date=None):
    """
    Trả về summary KPI + records đầy đủ cho Dashboard.

    Tham số:
        target_date : None (hôm nay), string 'YYYY-MM-DD', hoặc date object.

    Summary (tính từ 1 snapshot — KHÔNG thể mâu thuẫn):
        TongNhanVien  : tổng NV hệ thống
        DaChamCong    : số NV đã có GioVao ngày được chọn
        DangLamViec   : GioVao != NULL, GioRa == NULL
        DiTre         : GioVao > GioBatDau
        VeSom         : GioRa < GioKetThuc (đã ra về)
        ChuaChamCong  : TongNhanVien - DaChamCong  (≥ 0)
        DaRaVe        : GioRa != NULL
        CanhBaoHomNay : số cảnh báo AI ngày được chọn
        SelectedDate  : ngày được chọn (YYYY-MM-DD)

    Records: danh sách toàn bộ NV kèm trạng thái
    """
    # Parse / default target_date
    if target_date is None:
        target_d = date.today()
    elif isinstance(target_date, date) and not isinstance(target_date, datetime):
        target_d = target_date
    elif isinstance(target_date, datetime):
        target_d = target_date.date()
    else:
        # string
        try:
            target_d = datetime.strptime(str(target_date).strip(), '%Y-%m-%d').date()
        except ValueError:
            target_d = date.today()

    selected_str = target_d.strftime('%Y-%m-%d')

    try:
        rows         = database.get_attendance_by_date(target_d)
        canh_bao_cnt = database.get_alert_count_by_date(target_d)
    except Exception as e:
        print(f"[services] Loi lay dashboard: {e}")
        return {
            "Summary": {
                "TongNhanVien":  0,
                "DaChamCong":    0,
                "DangLamViec":   0,
                "DiTre":         0,
                "VeSom":         0,
                "ChuaChamCong":  0,
                "DaRaVe":        0,
                "CanhBaoHomNay": 0,
            },
            "Records": [],
            "SelectedDate": selected_str,
        }

    tong      = len(rows)
    da_cham   = 0
    dang_lam  = 0
    di_tre    = 0
    ve_som    = 0
    da_ra_ve  = 0

    records = []

    for row in rows:
        ma_nv        = row[0]
        ho_ten       = row[1]
        ma_ca        = row[2]
        ten_ca       = row[3]
        gio_bat_dau  = row[4]
        gio_ket_thuc = row[5]
        gio_vao      = row[6]   # datetime hoặc None
        gio_ra       = row[7]   # datetime hoặc None
        ma_cc        = row[8] if len(row) > 8 else None  # MaCC hoặc None

        gbd_t = _to_time(gio_bat_dau)
        gkt_t = _to_time(gio_ket_thuc)

        status = calc_attendance_status(
            gio_bat_dau, gio_ket_thuc, gio_vao, gio_ra
        )

        # Đếm KPI
        if gio_vao is not None:
            da_cham += 1

            if gio_ra is None:
                dang_lam += 1
            else:
                da_ra_ve += 1
                # Về sớm: GioRa < GioKetThuc
                if gkt_t and gio_ra.time() < gkt_t:
                    ve_som += 1

            # Đi trễ: GioVao > GioBatDau
            if gbd_t and gio_vao.time() > gbd_t:
                di_tre += 1

        # Format để trả JSON
        records.append({
            "MaCC":  ma_cc,
            "MaNV":  ma_nv,
            "HoTen": ho_ten,

            "MaCa":       ma_ca,
            "TenCa":      ten_ca or "--",
            "GioBatDau":  gbd_t.strftime("%H:%M") if gbd_t else "--",
            "GioKetThuc": gkt_t.strftime("%H:%M") if gkt_t else "--",

            "GioVao": (
                gio_vao.strftime("%H:%M:%S")
                if gio_vao else None
            ),
            "GioRa": (
                gio_ra.strftime("%H:%M:%S")
                if gio_ra else None
            ),

            "TrangThaiVao":     status["TrangThaiVao"],
            "TrangThaiRa":      status["TrangThaiRa"],
            "TrangThaiTongHop": status["TrangThaiTongHop"],
        })

    chua_cham = max(0, tong - da_cham)

    return {
        "Summary": {
            "TongNhanVien":  tong,
            "DaChamCong":    da_cham,
            "DangLamViec":   dang_lam,
            "DiTre":         di_tre,
            "VeSom":         ve_som,
            "ChuaChamCong":  chua_cham,
            "DaRaVe":        da_ra_ve,
            "CanhBaoHomNay": canh_bao_cnt,
        },
        "Records": records,
        "SelectedDate": selected_str,
    }


def fetch_today_attendance_summary():
    """
    Toàn bộ chấm công hôm nay + tổng nhân viên.
    Dùng cho endpoint /api/get_chamcong_today (backward compat).
    """
    try:
        records   = database.get_today_cham_cong()
        total_nv  = database.get_total_employees()

        rows = []
        for row in records:
            rows.append({
                "HoTen": row[0],
                "GioVao": (
                    row[1].strftime("%Y-%m-%d %H:%M:%S")
                    if row[1] else None
                ),
                "GioRa": (
                    row[2].strftime("%Y-%m-%d %H:%M:%S")
                    if row[2] else None
                ),
                "MaNV": row[3],
            })

        return {"TongNV": total_nv, "Records": rows}

    except Exception as e:
        print(f"[services] Loi lay cham cong hom nay: {e}")
        return {"TongNV": 0, "Records": []}


def fetch_attendance_weekly():
    """Thống kê chấm công 7 ngày gần nhất."""
    try:
        records = database.get_weekly_cham_cong()
        return [
            {
                "Ngay":       str(row[0]) if row[0] else "--",
                "SoNguoiVao": int(row[1]) if row[1] else 0,
                "SoNguoiRa":  int(row[2]) if row[2] else 0,
            }
            for row in records
        ]
    except Exception as e:
        print(f"[services] Loi lay thong ke tuan: {e}")
        return []


def fetch_attendance_history():
    """Lịch sử chấm công gần nhất (backward compat)."""
    try:
        records = database.get_recent_cham_cong()
        return [
            {
                "HoTen":  row[0],
                "GioVao": (
                    row[1].strftime("%Y-%m-%d %H:%M:%S")
                    if row[1] else "--"
                ),
                "GioRa": (
                    row[2].strftime("%Y-%m-%d %H:%M:%S")
                    if row[2] else "--"
                ),
            }
            for row in records
        ]
    except Exception as e:
        print(f"[services] Loi lay lich su cham cong: {e}")
        return []


# ============================================================
# Health
# ============================================================

def save_sensor_data(data):
    ma_nv    = data.get("MaNV")
    nhip_tim = data.get("NhipTim")
    spo2     = data.get("SpO2")

    if ma_nv is None or nhip_tim is None or spo2 is None:
        return False

    try:
        database.insert_health_data(ma_nv, nhip_tim, spo2)
        return True
    except Exception as e:
        print(f"[services] Loi luu suc khoe: {e}")
        return False


def fetch_health_data():
    try:
        records = database.get_recent_health_data()
        return [
            {
                "HoTen":   row[0],
                "NhipTim": row[1],
                "SpO2":    row[2],
                "ThoiGian": (
                    row[3].strftime("%Y-%m-%d %H:%M:%S")
                    if row[3] else "--"
                ),
            }
            for row in records
        ]
    except Exception as e:
        print(f"[services] Loi lay suc khoe: {e}")
        return []


def fetch_health_chart_data():
    try:
        records = database.get_health_chart_data(limit=20)
        return [
            {
                "HoTen":   row[0],
                "NhipTim": row[1],
                "ThoiGian": (
                    row[2].strftime("%H:%M:%S")
                    if row[2] else "--"
                ),
            }
            for row in records
        ]
    except Exception as e:
        print(f"[services] Loi lay chart suc khoe: {e}")
        return []


# ============================================================
# ============================================================
# AI State Log
# ============================================================

def save_state_log(ma_nv, trang_thai, gia_tri=None):
    """
    Lưu trạng thái AI.
    gia_tri nhận để tương thích với ai_engine.
    """
    if ma_nv is None:
        return False
    try:
        database.insert_trang_thai(ma_nv, trang_thai, gia_tri)
        return True
    except Exception as e:
        print(f"[services] Loi luu trang thai: {e}")
        return False


# ============================================================
# AI Alert
# ============================================================

def save_alert(ma_nv, loai_canh_bao, mo_ta, gia_tri=None):
    """
    Khi AI phát hiện buồn ngủ / gục đầu:
    1. Tạo LichSuTrangThai → lấy MaTT.
    2. Tạo CanhBao liên kết MaTT.
    """
    if ma_nv is None:
        return False

    loai_lower = str(loai_canh_bao).strip().lower()

    if "buon" in loai_lower or "ngu" in loai_lower or "ngủ" in loai_lower:
        trang_thai = "buon_ngu"
    elif "guc" in loai_lower or "gục" in loai_lower:
        trang_thai = "guc_dau"
    else:
        trang_thai = "binh_thuong"

    try:
        ma_tt = database.insert_trang_thai(ma_nv, trang_thai, gia_tri)
        database.insert_canh_bao(
            ma_nv=ma_nv,
            loai_canh_bao=loai_canh_bao,
            mo_ta=mo_ta,
            gia_tri=gia_tri,
            ma_tt=ma_tt,
            ma_tb=1,
            ma_loai_cb=1,
        )
        return True
    except Exception as e:
        print(f"[services] Loi luu canh bao: {e}")
        return False


# ============================================================
# Alert History
# ============================================================

def fetch_alert_history(limit=10):
    """
    Trả danh sách cảnh báo cho Dashboard.
    Fields: HoTen, LoaiCanhBao, MoTa, GiaTri, ThoiGian, DaXuLy
    """
    try:
        records = database.get_recent_canh_bao(limit=limit)
        result = []
        for row in records:
            result.append({
                "HoTen":      row[0],
                "LoaiCanhBao": row[1] if row[1] else "Cảnh báo AI",
                "MoTa":       row[2] if row[2] else "",
                "GiaTri":     None,
                "ThoiGian": (
                    row[3].strftime("%Y-%m-%d %H:%M:%S")
                    if row[3] else "--"
                ),
                "DaXuLy": False,
            })
        return result
    except Exception as e:
        print(f"[services] Loi lay canh bao: {e}")
        return []


# ============================================================
# Quản lý Nhân viên
# ============================================================

def _row_to_employee_dict(row, has_face_embedding=None):
    """
    Chuyển row DB (MaNV, HoTen, AnhKhuonMat, MaVaiTro, TenVaiTro)
    thành dict trả client.

    AnhKhuonMat KHÔNG trả về client.
    DaDangKyKhuonMat phản ánh FaceEmbedding, không phải ảnh hồ sơ legacy.
    """
    da_dang_ky = bool(has_face_embedding)
    return {
        "MaNV":              row[0],
        "HoTen":             row[1],
        "MaVaiTro":          row[3],
        "TenVaiTro":         row[4] if row[4] else "",
        "DaDangKyKhuonMat":  da_dang_ky,
    }


def fetch_employees():
    """
    Danh sách tất cả nhân viên kèm trạng thái khuôn mặt.

    Output:
    [
        {
            "MaNV": 1,
            "HoTen": "Nguyễn Văn A",
            "MaVaiTro": 1,
            "TenVaiTro": "Quản trị viên",
            "DaDangKyKhuonMat": true
        }
    ]
    """
    try:
        rows = database.get_all_employees()
        face_ids = set(database.get_face_enrolled_employee_ids())
        return [_row_to_employee_dict(r, r[0] in face_ids) for r in rows]
    except Exception as e:
        print(f"[services] Loi lay danh sach nhan vien: {e}")
        return []


def fetch_employee(ma_nv):
    """
    Thông tin 1 nhân viên.

    Trả về dict hoặc None nếu không tìm thấy.
    """
    try:
        row = database.get_employee_by_id(ma_nv)
        if row is None:
            return None
        return _row_to_employee_dict(row, database.count_face_embeddings(ma_nv) > 0)
    except Exception as e:
        print(f"[services] Loi lay nhan vien {ma_nv}: {e}")
        return None


def fetch_all_roles():
    """
    Danh sách vai trò.

    Output:
    [{"MaVaiTro": 1, "TenVaiTro": "Quản trị viên"}, ...]
    """
    try:
        rows = database.get_all_roles()
        return [{"MaVaiTro": r[0], "TenVaiTro": r[1]} for r in rows]
    except Exception as e:
        print(f"[services] Loi lay vai tro: {e}")
        return []


def create_employee(data):
    """
    Thêm nhân viên mới.

    Input: {"HoTen": "...", "MaVaiTro": int}

    Validation:
    - HoTen bắt buộc, không rỗng sau khi trim
    - MaVaiTro bắt buộc, phải tồn tại trong VaiTro

    AnhKhuonMat luôn = NULL — không nhận từ client.

    Trả về:
    - Thành công: {"status": "success", "message": "...", "MaNV": int}
    - Lỗi:        {"status": "error",   "message": "..."}
    """
    # --- Validation HoTen ---
    ho_ten = data.get("HoTen")
    if ho_ten is None:
        return {"status": "error", "message": "Thiếu HoTen"}

    ho_ten = str(ho_ten).strip()
    if not ho_ten:
        return {"status": "error", "message": "HoTen không được rỗng"}

    # --- Validation MaVaiTro ---
    ma_vai_tro = data.get("MaVaiTro")
    if ma_vai_tro is None:
        return {"status": "error", "message": "Thiếu MaVaiTro"}

    try:
        ma_vai_tro = int(ma_vai_tro)
    except (TypeError, ValueError):
        return {"status": "error", "message": "MaVaiTro phải là số nguyên"}

    try:
        if not database.role_exists(ma_vai_tro):
            return {"status": "error", "message": f"MaVaiTro={ma_vai_tro} không tồn tại"}
    except Exception as e:
        return {"status": "error", "message": f"Lỗi kiểm tra vai trò: {e}"}

    # --- Insert ---
    try:
        ma_nv = database.insert_employee(ho_ten, ma_vai_tro)
        if ma_nv is None:
            return {"status": "error", "message": "Không lấy được MaNV sau khi tạo"}
        return {
            "status":  "success",
            "message": "Thêm nhân viên thành công",
            "MaNV":    ma_nv,
        }
    except Exception as e:
        print(f"[services] Loi tao nhan vien: {e}")
        return {"status": "error", "message": f"Lỗi tạo nhân viên: {e}"}


def edit_employee(ma_nv, data):
    """
    Cập nhật thông tin nhân viên.

    Chỉ cho sửa: HoTen, MaVaiTro.
    Bỏ qua hoàn toàn: MaNV, AnhKhuonMat trong data.

    Trả về:
    - Thành công: {"status": "success", "message": "..."}
    - Không tìm thấy: {"status": "not_found"}
    - Lỗi: {"status": "error", "message": "..."}
    """
    # --- Kiểm tra nhân viên tồn tại ---
    try:
        existing = database.get_employee_by_id(ma_nv)
    except Exception as e:
        return {"status": "error", "message": f"Lỗi truy vấn: {e}"}

    if existing is None:
        return {"status": "not_found"}

    # --- Lấy giá trị mới (fallback về giá trị cũ nếu không truyền) ---
    ho_ten = data.get("HoTen", existing[1])
    if ho_ten is None:
        ho_ten = existing[1]
    ho_ten = str(ho_ten).strip()
    if not ho_ten:
        return {"status": "error", "message": "HoTen không được rỗng"}

    ma_vai_tro = data.get("MaVaiTro", existing[3])
    try:
        ma_vai_tro = int(ma_vai_tro)
    except (TypeError, ValueError):
        return {"status": "error", "message": "MaVaiTro phải là số nguyên"}

    try:
        if not database.role_exists(ma_vai_tro):
            return {"status": "error", "message": f"MaVaiTro={ma_vai_tro} không tồn tại"}
    except Exception as e:
        return {"status": "error", "message": f"Lỗi kiểm tra vai trò: {e}"}

    # --- Update ---
    try:
        affected = database.update_employee(ma_nv, ho_ten, ma_vai_tro)
        if affected == 0:
            return {"status": "error", "message": "Không có thay đổi nào được lưu"}
        return {"status": "success", "message": "Cập nhật nhân viên thành công"}
    except Exception as e:
        print(f"[services] Loi sua nhan vien {ma_nv}: {e}")
        return {"status": "error", "message": f"Lỗi cập nhật: {e}"}


# ============================================================
# Xác thực — Login / Tài khoản
# ============================================================

def authenticate(username, password):
    """
    Xác thực đăng nhập.

    Input: username (str), password (str)

    Trả về:
    - Thành công:
        {
            "status": "success",
            "user": {
                "MaTK":      int,
                "MaNV":      int,
                "HoTen":     str,
                "MaVaiTro":  int,
                "TenVaiTro": str
            }
        }
    - Thất bại:
        {"status": "error", "message": "..."}
    """
    if not username or not password:
        return {"status": "error", "message": "Thiếu tên đăng nhập hoặc mật khẩu"}

    username = str(username).strip()
    if not username:
        return {"status": "error", "message": "Tên đăng nhập không được rỗng"}

    try:
        row = database.get_account_by_username(username)
    except Exception as e:
        print(f"[services] Loi truy van tai khoan: {e}")
        return {"status": "error", "message": "Lỗi hệ thống"}

    if row is None:
        return {"status": "error", "message": "Sai tên đăng nhập hoặc mật khẩu"}

    # row: (MaTK, MaNV, TenDangNhap, MatKhau, HoTen, MaVaiTro, TenVaiTro)
    mat_khau_hash = row[3]

    # Hỗ trợ migrate plaintext password
    if not mat_khau_hash.startswith("scrypt:") and not mat_khau_hash.startswith("pbkdf2:"):
        # Mật khẩu cũ (plaintext)
        if mat_khau_hash == password:
            # Đúng mật khẩu -> migrate sang hash
            new_hash = generate_password_hash(password)
            try:
                database.update_account_password(row[0], new_hash)
            except Exception as e:
                print(f"[services] Loi migrate password cho MaTK {row[0]}: {e}")
        else:
            return {"status": "error", "message": "Sai tên đăng nhập hoặc mật khẩu"}
    elif not check_password_hash(mat_khau_hash, password):
        return {"status": "error", "message": "Sai tên đăng nhập hoặc mật khẩu"}

    return {
        "status": "success",
        "user": {
            "MaTK":      row[0],
            "MaNV":      row[1],
            "HoTen":     row[4],
            "MaVaiTro":  row[5],
            "TenVaiTro": row[6] if row[6] else "",
        },
    }


def create_account(data):
    """
    Tạo tài khoản.

    Input: {"MaNV": int, "TenDangNhap": str, "MatKhau": str}

    Trả về:
    - Thành công: {"status": "success", "message": "...", "MaTK": int}
    - Lỗi:        {"status": "error",   "message": "..."}
    """
    ma_nv         = data.get("MaNV")
    ten_dang_nhap = data.get("TenDangNhap")
    mat_khau      = data.get("MatKhau")

    if ma_nv is None:
        return {"status": "error", "message": "Thiếu MaNV"}
    if not ten_dang_nhap or not str(ten_dang_nhap).strip():
        return {"status": "error", "message": "Thiếu TenDangNhap"}
    if not mat_khau:
        return {"status": "error", "message": "Thiếu MatKhau"}

    ten_dang_nhap = str(ten_dang_nhap).strip()

    try:
        if database.account_exists(ten_dang_nhap):
            return {"status": "error", "message": f"TenDangNhap '{ten_dang_nhap}' đã tồn tại"}
    except Exception as e:
        return {"status": "error", "message": f"Lỗi kiểm tra: {e}"}

    mat_khau_hash = generate_password_hash(mat_khau)

    try:
        ma_tk = database.insert_account(ma_nv, ten_dang_nhap, mat_khau_hash)
        if ma_tk is None:
            return {"status": "error", "message": "Không lấy được MaTK"}
        return {
            "status":  "success",
            "message": "Tạo tài khoản thành công",
            "MaTK":    ma_tk,
        }
    except Exception as e:
        print(f"[services] Loi tao tai khoan: {e}")
        return {"status": "error", "message": f"Lỗi tạo tài khoản: {e}"}


def fetch_my_attendance(ma_nv):
    """
    Lấy chấm công hôm nay + ca làm việc của chính nhân viên.

    Trả về dict cho trang /me.
    """
    today = date.today().isoformat()

    result = {
        "CaHomNay":   None,
        "ChamCong":   None,
        "TrangThai":  "Chưa chấm công",
        "LichSu":     [],
    }

    try:
        # Ca hôm nay
        shift_row = database.get_employee_shift(ma_nv, today)
        if shift_row:
            gbd = _to_time(shift_row[2])
            gkt = _to_time(shift_row[3])
            result["CaHomNay"] = {
                "MaCa":       shift_row[0],
                "TenCa":      shift_row[1],
                "GioBatDau":  gbd.strftime("%H:%M") if gbd else "--",
                "GioKetThuc": gkt.strftime("%H:%M") if gkt else "--",
            }

        # Chấm công hôm nay
        today_rec = database.get_today_record(ma_nv)
        if today_rec:
            gio_vao = today_rec[1]
            gio_ra  = today_rec[2]
            result["ChamCong"] = {
                "MaCC":  today_rec[0],
                "GioVao": gio_vao.strftime("%H:%M:%S") if gio_vao else None,
                "GioRa":  gio_ra.strftime("%H:%M:%S") if gio_ra else None,
            }

            # Tính trạng thái
            if shift_row:
                status = calc_attendance_status(
                    shift_row[2], shift_row[3], gio_vao, gio_ra
                )
                result["TrangThai"] = status["TrangThaiTongHop"]
            else:
                if gio_ra:
                    result["TrangThai"] = "Đã chấm công ra"
                else:
                    result["TrangThai"] = "Đang làm việc"

    except Exception as e:
        print(f"[services] Loi lay cham cong ca nhan {ma_nv}: {e}")

    # Lịch sử 30 bản ghi gần nhất
    try:
        recent = database.get_employee_attendance_history(ma_nv, limit=30)
        for row in recent:
            result["LichSu"].append({
                "GioVao": row[0].strftime("%Y-%m-%d %H:%M:%S") if row[0] else None,
                "GioRa": row[1].strftime("%Y-%m-%d %H:%M:%S") if row[1] else None,
            })
    except Exception as e:
        print(f"[services] Loi lay lich su cham cong ca nhan {ma_nv}: {e}")

    return result

def fetch_employee_profile(ma_nv):
    emp = database.get_employee_by_id(ma_nv)
    if not emp:
        return {}
    return {
        "MaNV": emp[0],
        "HoTen": emp[1],
        "MaVaiTro": emp[3],
        "TenVaiTro": emp[4]
    }

def fetch_my_today_status(ma_nv):
    # Trả về status chấm công hôm nay
    today = date.today().isoformat()
    try:
        shift_row = database.get_employee_shift(ma_nv, today)
        today_rec = database.get_today_record(ma_nv)
        
        ca = None
        if shift_row:
            gbd = _to_time(shift_row[2])
            gkt = _to_time(shift_row[3])
            ca = {
                "TenCa": shift_row[1],
                "GioBatDau": gbd.strftime("%H:%M") if gbd else "--",
                "GioKetThuc": gkt.strftime("%H:%M") if gkt else "--",
            }
        
        cc = None
        status = "Chưa chấm công"
        if today_rec:
            gio_vao = today_rec[1]
            gio_ra = today_rec[2]
            cc = {
                "GioVao": gio_vao.strftime("%H:%M:%S") if gio_vao else None,
                "GioRa": gio_ra.strftime("%H:%M:%S") if gio_ra else None,
            }
            if shift_row:
                st = calc_attendance_status(shift_row[2], shift_row[3], gio_vao, gio_ra)
                status = st["TrangThaiTongHop"]
            else:
                status = "Đã chấm công ra" if gio_ra else "Đang làm việc"
                
        return {"CaHomNay": ca, "ChamCong": cc, "TrangThai": status}
    except Exception as e:
        print(f"[services] Loi lay trang thai hom nay {ma_nv}: {e}")
        return {}

def fetch_my_health(ma_nv):
    try:
        rows = database.get_employee_health_history(ma_nv, limit=30)
        return [{
            "NhipTim": r[0],
            "SpO2": r[1],
            "ThoiGian": r[2].strftime("%Y-%m-%d %H:%M:%S") if r[2] else "--"
        } for r in rows]
    except Exception as e:
        print(f"[services] Loi lay suc khoe ca nhan {ma_nv}: {e}")
        return []

def fetch_my_alerts(ma_nv):
    try:
        rows = database.get_employee_alert_history(ma_nv, limit=20)
        return [{
            "LoaiCanhBao": r[0] if r[0] else "Cảnh báo AI",
            "MoTa": r[1] if r[1] else "",
            "ThoiGian": r[2].strftime("%Y-%m-%d %H:%M:%S") if r[2] else "--"
        } for r in rows]
    except Exception as e:
        print(f"[services] Loi lay canh bao ca nhan {ma_nv}: {e}")
        return []


# ============================================================
# Face Enrollment — PHASE 1
# ============================================================

def register_face(ma_nv, frames, target_count=5):
    """
    Đăng ký khuôn mặt nhân viên từ danh sách frame OpenCV.

    Tham so:
        ma_nv        : MaNV (int)
        frames       : list[ndarray] — BGR frames từ camera
        target_count : số embedding cần lưu (mặc định 5)

    Quy tac:
        - Mỗi frame phải có đúng 1 khuôn mặt
        - Lưu mỗi embedding thành 1 row riêng biệt (không average)
        - KHÔNG xóa dữ liệu cũ nếu đã tồn tại

    Tra ve dict:
        success  : bool
        message  : str
        embeddings_saved : int (nếu success)
        dimensions       : int (nếu success)
        errors           : list[str] (các frame bị lỗi)
    """
    import face_engine as _fe

    # Khởi tạo engine nếu chưa làm
    try:
        _fe.face_engine.initialize()
    except RuntimeError as e:
        return {
            "success": False,
            "message": str(e),
        }

    embeddings = []
    errors = []

    for i, frame in enumerate(frames):
        try:
            vector_bytes, emb_np = _fe.face_engine.extract_embedding(frame)
            embeddings.append(vector_bytes)
        except RuntimeError as e:
            errors.append(f"Frame {i+1}: {e}")
        except Exception as e:
            errors.append(f"Frame {i+1}: loi khong xac dinh: {e}")

    if len(embeddings) != target_count:
        return {
            "success": False,
            "message": f"Can du {target_count} frame hop le; chi thu duoc {len(embeddings)}.",
            "errors": errors,
        }

    return save_face_embeddings(ma_nv, embeddings)


def save_face_embeddings(ma_nv, embeddings):
    """Append a complete enrollment batch without replacing prior vectors."""
    if not embeddings:
        return {"success": False, "message": "Khong co embedding de luu.", "errors": []}
    if database.count_face_embeddings(ma_nv) > 0:
        return {
            "success": False,
            "conflict": True,
            "message": "Nhan vien da co face embedding; tu choi ghi them de tranh ghi de du lieu.",
            "errors": [],
        }

    try:
        saved_ids = database.insert_face_embeddings(ma_nv, embeddings, so_chieu=512)
    except Exception as exc:
        return {"success": False, "message": f"Khong luu duoc enrollment batch: {exc}", "errors": []}

    return {
        "success": True,
        "message": "Dang ky khuon mat thanh cong",
        "embeddings_saved": len(saved_ids),
        "embedding_ids": saved_ids,
        "dimensions": 512,
        "errors": [],
    }


def _recognition_threshold(override=None):
    value = override if override is not None else os.getenv("FACE_RECOGNITION_THRESHOLD", "0.45")
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a number between -1 and 1.") from exc
    if not -1.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be a number between -1 and 1.")
    return threshold


def _load_face_gallery():
    rows = database.get_all_face_embeddings()
    gallery, invalid_rows = aggregate_gallery(rows)
    if invalid_rows:
        print(f"[face_recognition] Ignored {len(invalid_rows)} invalid embedding row(s).")
    return gallery, invalid_rows


def identify_face_embedding(probe_embedding, threshold=None):
    threshold = _recognition_threshold(threshold)
    gallery, invalid_rows = _load_face_gallery()
    result = identify_embedding(probe_embedding, gallery, threshold)
    result["invalidEmbeddings"] = len(invalid_rows)
    return result


def verify_face_embedding(probe_embedding, ma_nv, threshold=None):
    threshold = _recognition_threshold(threshold)
    gallery, invalid_rows = _load_face_gallery()
    result = verify_embedding(probe_embedding, ma_nv, gallery, threshold)
    result["invalidEmbeddings"] = len(invalid_rows)
    return result


def _face_bbox_area(face):
    bbox = face.get("bbox")
    if bbox is None or len(bbox) != 4:
        return 0.0
    width = max(0.0, float(bbox[2]) - float(bbox[0]))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    return width * height


def _extract_largest_face(frame):
    import face_engine as _fe

    _fe.face_engine.initialize()
    faces = _fe.face_engine.detect_embeddings(frame)
    if not faces:
        return None, {"status": "NO_FACE", "match": False, "MaNV": None,
                      "HoTen": "UNKNOWN", "similarity": None}
    largest_face = max(faces, key=_face_bbox_area)
    return largest_face["embedding"], None


def identify_face_frame(frame, threshold=None):
    resolved_threshold = _recognition_threshold(threshold)
    probe, error_result = _extract_largest_face(frame)
    if error_result:
        error_result["threshold"] = resolved_threshold
        return error_result
    return identify_face_embedding(probe, resolved_threshold)


def verify_face_frame(frame, ma_nv, threshold=None):
    resolved_threshold = _recognition_threshold(threshold)
    probe, error_result = _extract_largest_face(frame)
    if error_result:
        error_result["threshold"] = resolved_threshold
        return error_result
    return verify_face_embedding(probe, ma_nv, resolved_threshold)

def fetch_attendance_history_filtered(tu_ngay=None, den_ngay=None, keyword=None, page=1, limit=20):
    """
    Format data từ database.get_attendance_history_filtered.
    """
    try:
        rows, total = database.get_attendance_history_filtered(tu_ngay, den_ngay, keyword, page, limit)
        records = []
        for row in rows:
            ma_cc        = row[0]
            ma_nv        = row[1]
            ho_ten       = row[2]
            ma_ca        = row[3]
            ten_ca       = row[4]
            gio_bat_dau  = row[5]
            gio_ket_thuc = row[6]
            gio_vao      = row[7]   # datetime
            gio_ra       = row[8]   # datetime
            
            gbd_t = _to_time(gio_bat_dau)
            gkt_t = _to_time(gio_ket_thuc)
            
            status = calc_attendance_status(
                gio_bat_dau, gio_ket_thuc, gio_vao, gio_ra
            )
            
            records.append({
                "MaCC":  ma_cc,
                "MaNV":  ma_nv,
                "HoTen": ho_ten,
                "MaCa":       ma_ca,
                "TenCa":      ten_ca or "--",
                "GioBatDau":  gbd_t.strftime("%H:%M") if gbd_t else "--",
                "GioKetThuc": gkt_t.strftime("%H:%M") if gkt_t else "--",
                "GioVao": (
                    gio_vao.strftime("%H:%M:%S")
                    if gio_vao else None
                ),
                "GioRa": (
                    gio_ra.strftime("%H:%M:%S")
                    if gio_ra else None
                ),
                "TrangThaiVao":     status["TrangThaiVao"],
                "TrangThaiRa":      status["TrangThaiRa"],
                "TrangThaiTongHop": status["TrangThaiTongHop"],
                # Return the full date of GioVao so we can group or display
                "Ngay": gio_vao.strftime("%Y-%m-%d") if gio_vao else None
            })
        return {
            "records": records,
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        print(f"[services] Loi fetch_attendance_history_filtered: {e}")
        return {
            "records": [],
            "total": 0,
            "page": page,
            "limit": limit
        }
