"""
database.py — Tầng truy cập dữ liệu (Data Access Layer)
=========================================================
Kết nối SQL Server, thực thi truy vấn, trả raw rows.
KHÔNG chứa business logic — chỉ CRUD thuần.

Schema bổ sung (đã tạo ngoài code):
    CaLamViec(MaCa, TenCa, GioBatDau, GioKetThuc)
    PhanCaNhanVien(MaPhanCa, MaNV, MaCa, NgayLamViec)
    ChamCong.MaCa — FK tới CaLamViec
"""

import pyodbc
from datetime import date as _date


# ============================================================
# Kết nối
# ============================================================

def get_connection():
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=localhost;"
        "Database=DoAn_ChamCong_AI;"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str, timeout=5)


def _safe_limit(limit, default=10, max_value=100):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, max_value))


# ============================================================
# NhanVien
# ============================================================

def get_all_users():
    """Trả về (MaNV, HoTen) tất cả nhân viên."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_total_employees():
    """Tổng số nhân viên trong hệ thống."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM NhanVien")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ============================================================
# CaLamViec
# ============================================================

def get_all_shifts():
    """
    Tất cả ca làm việc.
    Trả về: (MaCa, TenCa, GioBatDau, GioKetThuc)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaCa, TenCa, GioBatDau, GioKetThuc
            FROM CaLamViec
            ORDER BY GioBatDau
        """)
        return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
# PhanCaNhanVien
# ============================================================

def get_employee_shift(ma_nv, ngay_lam_viec):
    """
    Lấy ca làm việc của nhân viên trong ngày chỉ định.

    Trả về row hoặc None nếu chưa phân ca.
    Row: (MaCa, TenCa, GioBatDau, GioKetThuc)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CLV.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc

            FROM PhanCaNhanVien PCN

            JOIN CaLamViec CLV
                ON PCN.MaCa = CLV.MaCa

            WHERE
                PCN.MaNV = ?
                AND PCN.NgayLamViec = ?
        """, (ma_nv, ngay_lam_viec))
        return cursor.fetchone()
    finally:
        conn.close()


def assign_shift(ma_nv, ma_ca, ngay_lam_viec):
    """
    Phân ca cho nhân viên trong ngày.
    Mỗi nhân viên chỉ có tối đa 1 ca / ngày.
    Nếu đã có thì UPDATE, chưa có thì INSERT.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Kiểm tra đã có chưa
        cursor.execute("""
            SELECT MaPhanCa
            FROM PhanCaNhanVien
            WHERE MaNV = ? AND NgayLamViec = ?
        """, (ma_nv, ngay_lam_viec))
        row = cursor.fetchone()

        if row:
            cursor.execute("""
                UPDATE PhanCaNhanVien
                SET MaCa = ?
                WHERE MaNV = ? AND NgayLamViec = ?
            """, (ma_ca, ma_nv, ngay_lam_viec))
        else:
            cursor.execute("""
                INSERT INTO PhanCaNhanVien
                    (MaNV, MaCa, NgayLamViec)
                VALUES (?, ?, ?)
            """, (ma_nv, ma_ca, ngay_lam_viec))

        conn.commit()
    finally:
        conn.close()


# ============================================================
# ChamCong — Check-in / Check-out
# ============================================================

def get_today_record(ma_nv):
    """
    Lấy bản ghi chấm công hôm nay của nhân viên.

    Trả về row hoặc None.
    Row: (MaCC, GioVao, GioRa, MaCa)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaCC, GioVao, GioRa, MaCa
            FROM ChamCong
            WHERE
                MaNV = ?
                AND CAST(GioVao AS DATE) = CAST(GETDATE() AS DATE)
        """, (ma_nv,))
        return cursor.fetchone()
    finally:
        conn.close()


def insert_checkin(ma_nv, ma_ca, ma_tb=1, anh_vao=None):
    """
    Tạo bản ghi CHECK-IN.
    GioVao = GETDATE(), GioRa = NULL.
    anh_vao: bytes JPEG hoặc None.
    Trả về MaCC vừa tạo.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ChamCong
                (MaNV, GioVao, GioRa, MaTB, MaCa, AnhVao)
            OUTPUT INSERTED.MaCC
            VALUES (?, GETDATE(), NULL, ?, ?, ?)
        """, (ma_nv, ma_tb, ma_ca, anh_vao))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


def update_checkout(ma_cc, anh_ra=None):
    """
    Cập nhật GioRa = GETDATE() và AnhRa cho bản ghi MaCC.
    anh_ra: bytes JPEG hoặc None.
    Trả về số row bị ảnh hưởng.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ChamCong
            SET
                GioRa = GETDATE(),
                AnhRa = ?
            WHERE MaCC = ?
        """, (anh_ra, ma_cc))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_attendance_image(ma_cc, image_type):
    """
    Lấy ảnh bằng chứng chấm công.

    image_type: "in"  → AnhVao
                "out" → AnhRa

    Không cho truyền tên column tùy ý từ client;
    dùng if cố định để tránh SQL injection.

    Trả về bytes hoặc None.
    """
    if image_type == "in":
        column = "AnhVao"
    elif image_type == "out":
        column = "AnhRa"
    else:
        return None  # invalid type

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # column đã được whitelist bởi if ở trên — an toàn
        cursor.execute(f"""
            SELECT {column}
            FROM ChamCong
            WHERE MaCC = ?
        """, (ma_cc,))
        row = cursor.fetchone()
        if row is None:
            return None
        return bytes(row[0]) if row[0] is not None else None
    finally:
        conn.close()


# ============================================================
# ChamCong — Read
# ============================================================

def get_recent_cham_cong(limit=20):
    """
    Lịch sử chấm công gần nhất (dùng cho /api/get_chamcong).
    Trả về: (HoTen, GioVao, GioRa)
    """
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                CC.GioVao,
                CC.GioRa

            FROM ChamCong CC

            JOIN NhanVien NV
                ON CC.MaNV = NV.MaNV

            ORDER BY CC.GioVao DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_employee_attendance_history(ma_nv, limit=30):
    limit = _safe_limit(limit, default=30)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                GioVao, GioRa
            FROM ChamCong
            WHERE MaNV = ?
            ORDER BY GioVao DESC
        """, (ma_nv,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_attendance_by_date(target_date):
    """
    Toàn bộ nhân viên kèm tình trạng chấm công theo ngày được chọn.

    Dùng OUTER APPLY + SELECT TOP 1 để đảm bảo mỗi nhân viên
    CHỈ xuất hiện đúng 1 dòng, kể cả khi ChamCong có nhiều
    bản ghi trong ngày (tránh duplicate nhân viên gây sai KPI).

    Ưu tiên bản ghi có GioVao sớm nhất trong ngày.

    Tham số:
        target_date : date object hoặc string 'YYYY-MM-DD'

    Trả về:
        MaNV, HoTen,
        MaCa, TenCa, GioBatDau, GioKetThuc,
        GioVao, GioRa, MaCC
    """
    if isinstance(target_date, str):
        from datetime import datetime
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.MaNV,
                NV.HoTen,

                CLV.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,

                CC_DAY.GioVao,
                CC_DAY.GioRa,
                CC_DAY.MaCC

            FROM NhanVien NV

            -- Ca làm việc ngày được chọn (parameterized)
            LEFT JOIN PhanCaNhanVien PCN
                ON  NV.MaNV = PCN.MaNV
                AND PCN.NgayLamViec = ?

            LEFT JOIN CaLamViec CLV
                ON PCN.MaCa = CLV.MaCa

            -- Lấy đúng 1 bản ghi ChamCong ngày được chọn (GioVao sớm nhất)
            OUTER APPLY (
                SELECT TOP 1
                    CC.MaCC,
                    CC.GioVao,
                    CC.GioRa
                FROM ChamCong CC
                WHERE
                    CC.MaNV = NV.MaNV
                    AND CAST(CC.GioVao AS DATE) = ?
                ORDER BY CC.GioVao ASC
            ) AS CC_DAY

            ORDER BY NV.MaNV
        """, (target_date, target_date))
        return cursor.fetchall()
    finally:
        conn.close()


def get_today_attendance():
    """Wrapper backward-compatible: chấm công hôm nay."""
    return get_attendance_by_date(_date.today())


def get_today_cham_cong():
    """
    Bản ghi ChamCong hôm nay (đã chấm công).
    Trả về: (HoTen, GioVao, GioRa, MaNV)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.HoTen,
                CC.GioVao,
                CC.GioRa,
                NV.MaNV

            FROM ChamCong CC

            JOIN NhanVien NV
                ON CC.MaNV = NV.MaNV

            WHERE
                CAST(CC.GioVao AS DATE)
                    = CAST(GETDATE() AS DATE)

            ORDER BY CC.GioVao ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_weekly_cham_cong():
    """
    Thống kê chấm công 7 ngày gần nhất.
    Trả về: (NgayChamCong, SoNguoiVao, SoNguoiRa)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                CAST(CC.GioVao AS DATE)  AS NgayChamCong,
                COUNT(CC.MaCC)             AS SoNguoiVao,
                SUM(
                    CASE
                        WHEN CC.GioRa IS NOT NULL THEN 1
                        ELSE 0
                    END
                )                        AS SoNguoiRa

            FROM ChamCong CC

            WHERE
                CC.GioVao >= CAST(
                    DATEADD(DAY, -6, GETDATE())
                AS DATE)

            GROUP BY
                CAST(CC.GioVao AS DATE)

            ORDER BY
                NgayChamCong ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
# LichSuSucKhoe
# ============================================================

def insert_health_data(ma_nv, nhip_tim, spo2):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO LichSuSucKhoe (MaNV, NhipTim, SpO2, ThoiGian)
            VALUES (?, ?, ?, GETDATE())
        """, (ma_nv, nhip_tim, spo2))
        conn.commit()
    finally:
        conn.close()


def get_recent_health_data(limit=10):
    """
    Trả về: (HoTen, NhipTim, SpO2, ThoiGian)
    """
    limit = _safe_limit(limit, default=10)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                SK.NhipTim,
                SK.SpO2,
                SK.ThoiGian

            FROM LichSuSucKhoe SK

            JOIN NhanVien NV
                ON SK.MaNV = NV.MaNV

            ORDER BY SK.ThoiGian DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_employee_health_history(ma_nv, limit=30):
    limit = _safe_limit(limit, default=30)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NhipTim, SpO2, ThoiGian
            FROM LichSuSucKhoe
            WHERE MaNV = ?
            ORDER BY ThoiGian DESC
        """, (ma_nv,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_health_chart_data(limit=20):
    """
    Trả về: (HoTen, NhipTim, ThoiGian) — thứ tự ASC để vẽ chart
    """
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                NV.HoTen,
                SK.NhipTim,
                SK.ThoiGian

            FROM LichSuSucKhoe SK

            JOIN NhanVien NV
                ON SK.MaNV = NV.MaNV

            ORDER BY SK.ThoiGian DESC
        """)
        rows = cursor.fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


# ============================================================
# ============================================================
# LichSuTrangThai (AI)
#
# Schema thật:
#   MaTT, MaNV, MaBieuHien, ThoiGian
# ============================================================

_STATE_TO_BIEU_HIEN = {
    "binh_thuong": 1,
    "buon_ngu":    2,
    "guc_dau":     3,
    "meo_mieng":   4,
}

_STATE_ALIASES = {
    "bình thường":  "binh_thuong",
    "binh thuong":  "binh_thuong",
    "buồn ngủ":     "buon_ngu",
    "buon ngu":     "buon_ngu",
    "gục đầu":      "guc_dau",
    "guc dau":      "guc_dau",
    "méo miệng":    "meo_mieng",
    "meo mieng":    "meo_mieng",
}


def get_ma_bieu_hien(trang_thai):
    if trang_thai is None:
        return 1
    key = str(trang_thai).strip().lower()
    key = _STATE_ALIASES.get(key, key)
    return _STATE_TO_BIEU_HIEN.get(key, 1)


def insert_trang_thai(ma_nv, trang_thai, gia_tri=None):
    """
    Lưu trạng thái AI.
    gia_tri nhận để tương thích với ai_engine nhưng
    DB không có cột GiaTri — bỏ qua.
    Trả về MaTT vừa INSERT.
    """
    ma_bieu_hien = get_ma_bieu_hien(trang_thai)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO LichSuTrangThai (MaNV, MaBieuHien, ThoiGian)
            OUTPUT INSERTED.MaTT
            VALUES (?, ?, GETDATE())
        """, (ma_nv, ma_bieu_hien))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


# ============================================================
# CanhBao (AI)
#
# Schema thật:
#   MaCB, MaNV, MaLoaiCB, NoiDung, ThoiGian, MaTT, MaTB
# ============================================================

def insert_canh_bao(
    ma_nv,
    loai_canh_bao,
    mo_ta,
    gia_tri=None,
    ma_tt=None,
    ma_tb=1,
    ma_loai_cb=1
):
    """
    Lưu cảnh báo AI.
    EAR / Tilt được gộp vào NoiDung vì DB không có cột GiaTri riêng.
    """
    noi_dung = str(loai_canh_bao)
    if mo_ta:
        noi_dung += f": {mo_ta}"
    if gia_tri is not None:
        noi_dung += f" | GiaTri={gia_tri}"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO CanhBao
                (MaNV, MaLoaiCB, NoiDung, ThoiGian, MaTT, MaTB)
            VALUES (?, ?, ?, GETDATE(), ?, ?)
        """, (ma_nv, ma_loai_cb, noi_dung, ma_tt, ma_tb))
        conn.commit()
    finally:
        conn.close()


def get_recent_canh_bao(limit=10):
    """
    Trả về: (HoTen, LoaiCanhBao, NoiDung, ThoiGian)
    """
    limit = _safe_limit(limit, default=10)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}

                NV.HoTen,

                COALESCE(
                    BH.TenBieuHien,
                    LCB.TenLoaiCB
                ) AS LoaiCanhBao,

                CB.NoiDung,

                CB.ThoiGian

            FROM CanhBao CB

            JOIN NhanVien NV
                ON CB.MaNV = NV.MaNV

            LEFT JOIN LoaiCanhBao LCB
                ON CB.MaLoaiCB = LCB.MaLoaiCB

            LEFT JOIN LichSuTrangThai TT
                ON CB.MaTT = TT.MaTT

            LEFT JOIN DanhMucBieuHien BH
                ON TT.MaBieuHien = BH.MaBieuHien

            ORDER BY CB.ThoiGian DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_employee_alert_history(ma_nv, limit=20):
    limit = _safe_limit(limit, default=20)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP {limit}
                COALESCE(BH.TenBieuHien, LCB.TenLoaiCB) AS LoaiCanhBao,
                CB.NoiDung,
                CB.ThoiGian
            FROM CanhBao CB
            LEFT JOIN LoaiCanhBao LCB ON CB.MaLoaiCB = LCB.MaLoaiCB
            LEFT JOIN LichSuTrangThai TT ON CB.MaTT = TT.MaTT
            LEFT JOIN DanhMucBieuHien BH ON TT.MaBieuHien = BH.MaBieuHien
            WHERE CB.MaNV = ?
            ORDER BY CB.ThoiGian DESC
        """, (ma_nv,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_alert_count_by_date(target_date):
    """Số cảnh báo AI theo ngày được chọn (parameterized)."""
    if isinstance(target_date, str):
        from datetime import datetime
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM CanhBao
            WHERE CAST(ThoiGian AS DATE) = ?
        """, (target_date,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_today_alert_count():
    """Wrapper backward-compatible: số cảnh báo hôm nay."""
    return get_alert_count_by_date(_date.today())


# ============================================================
# VaiTro
# ============================================================

def get_all_roles():
    """
    Tất cả vai trò.
    Trả về: (MaVaiTro, TenVaiTro)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MaVaiTro, TenVaiTro
            FROM VaiTro
            ORDER BY MaVaiTro
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def role_exists(ma_vai_tro):
    """Kiểm tra MaVaiTro có tồn tại trong VaiTro không."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM VaiTro WHERE MaVaiTro = ?
        """, (ma_vai_tro,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


# ============================================================
# NhanVien — Quản lý nhân viên
# ============================================================

def get_all_employees():
    """
    Tất cả nhân viên kèm tên vai trò.

    Trả về mỗi row:
        (MaNV, HoTen, AnhKhuonMat, MaVaiTro, TenVaiTro)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.MaNV,
                NV.HoTen,
                NV.AnhKhuonMat,
                NV.MaVaiTro,
                VT.TenVaiTro

            FROM NhanVien NV

            LEFT JOIN VaiTro VT
                ON NV.MaVaiTro = VT.MaVaiTro

            ORDER BY NV.MaNV
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_employee_by_id(ma_nv):
    """
    Lấy thông tin 1 nhân viên theo MaNV.

    Trả về row hoặc None.
    Row: (MaNV, HoTen, AnhKhuonMat, MaVaiTro, TenVaiTro)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                NV.MaNV,
                NV.HoTen,
                NV.AnhKhuonMat,
                NV.MaVaiTro,
                VT.TenVaiTro

            FROM NhanVien NV

            LEFT JOIN VaiTro VT
                ON NV.MaVaiTro = VT.MaVaiTro

            WHERE NV.MaNV = ?
        """, (ma_nv,))
        return cursor.fetchone()
    finally:
        conn.close()


def insert_employee(ho_ten, ma_vai_tro):
    """
    Thêm nhân viên mới.
    AnhKhuonMat luôn = NULL khi tạo mới.

    Trả về MaNV vừa tạo (int) hoặc None nếu thất bại.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO NhanVien
                (HoTen, AnhKhuonMat, MaVaiTro)
            OUTPUT INSERTED.MaNV
            VALUES (?, NULL, ?)
        """, (ho_ten, ma_vai_tro))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


def update_employee(ma_nv, ho_ten, ma_vai_tro):
    """
    Cập nhật thông tin nhân viên.
    CHỈ UPDATE: HoTen, MaVaiTro.
    TUYỆT ĐỐI KHÔNG update AnhKhuonMat.

    Trả về số row bị ảnh hưởng.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE NhanVien
            SET
                HoTen    = ?,
                MaVaiTro = ?
            WHERE MaNV = ?
        """, (ho_ten, ma_vai_tro, ma_nv))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ============================================================
# TaiKhoan — Xác thực
# ============================================================

def get_account_by_username(ten_dang_nhap):
    """
    Lấy tài khoản theo TenDangNhap.

    Trả về row hoặc None.
    Row: (MaTK, MaNV, TenDangNhap, MatKhau, HoTen, MaVaiTro, TenVaiTro)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                TK.MaTK,
                TK.MaNV,
                TK.TenDangNhap,
                TK.MatKhau,
                NV.HoTen,
                NV.MaVaiTro,
                VT.TenVaiTro

            FROM TaiKhoan TK

            JOIN NhanVien NV
                ON TK.MaNV = NV.MaNV

            LEFT JOIN VaiTro VT
                ON NV.MaVaiTro = VT.MaVaiTro

            WHERE TK.TenDangNhap = ?
        """, (ten_dang_nhap,))
        return cursor.fetchone()
    finally:
        conn.close()


def account_exists(ten_dang_nhap):
    """Kiểm tra TenDangNhap đã tồn tại trong TaiKhoan chưa."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM TaiKhoan WHERE TenDangNhap = ?
        """, (ten_dang_nhap,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def insert_account(ma_nv, ten_dang_nhap, mat_khau_hash):
    """
    Tạo tài khoản mới.
    mat_khau_hash phải là mật khẩu ĐÃ HASH (werkzeug).

    Trả về MaTK vừa tạo (int) hoặc None.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO TaiKhoan
                (MaNV, TenDangNhap, MatKhau)
            OUTPUT INSERTED.MaTK
            VALUES (?, ?, ?)
        """, (ma_nv, ten_dang_nhap, mat_khau_hash))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


def update_account_password(ma_tk, mat_khau_hash):
    """
    Cập nhật mật khẩu cho tài khoản.
    Dùng để migrate mật khẩu từ plaintext sang hash.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE TaiKhoan
            SET MatKhau = ?
            WHERE MaTK = ?
        """, (mat_khau_hash, ma_tk))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ============================================================
# FaceEmbedding — Enrollment
# ============================================================

def insert_face_embedding(ma_nv, vector_bytes, so_chieu=512):
    """
    Lưu một face embedding vào FaceEmbedding.

    Tham số:
        ma_nv        : MaNV (int)
        vector_bytes : bytes float32, độ dài = so_chieu * 4
        so_chieu     : số chiều embedding (mặc định 512)

    Trả về MaEmbedding vừa INSERT (int) hoặc None.

    Dùng parameterized query — KHÔNG nối binary vào SQL string.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO FaceEmbedding
                (MaNV, VectorData, SoChieu)
            OUTPUT INSERTED.MaEmbedding
            VALUES (?, ?, ?)
        """, (ma_nv, vector_bytes, so_chieu))
        row = cursor.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    finally:
        conn.close()


def insert_face_embeddings(ma_nv, embeddings, so_chieu=512):
    """Atomically append a group of embeddings; never deletes existing rows."""
    vectors = [bytes(vector) for vector in embeddings]
    if not vectors:
        raise ValueError("At least one embedding is required.")
    expected_bytes = int(so_chieu) * 4
    if any(len(vector) != expected_bytes for vector in vectors):
        raise ValueError(f"Each embedding must contain exactly {expected_bytes} bytes.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        inserted_ids = []
        for vector in vectors:
            cursor.execute("""
                INSERT INTO FaceEmbedding (MaNV, VectorData, SoChieu)
                OUTPUT INSERTED.MaEmbedding
                VALUES (?, ?, ?)
            """, (ma_nv, vector, so_chieu))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("FaceEmbedding insert returned no identifier.")
            inserted_ids.append(int(row[0]))
        conn.commit()
        return inserted_ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_face_embeddings(ma_nv):
    """
    Lấy tất cả embedding của một nhân viên.

    Trả về list of rows:
        (MaEmbedding, MaNV, VectorData, SoChieu, ThoiGianTao)

    Trả list rỗng nếu không có embedding.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                MaEmbedding,
                MaNV,
                VectorData,
                SoChieu,
                ThoiGianTao
            FROM FaceEmbedding
            WHERE MaNV = ?
            ORDER BY MaEmbedding
        """, (ma_nv,))
        return cursor.fetchall()
    finally:
        conn.close()


def delete_face_embeddings(ma_nv):
    """
    Xóa TẤT CẢ embedding của nhân viên.
    CHỈ gọi khi admin muốn đăng ký lại khuôn mặt.
    KHÔNG tự động gọi trong quá trình capture.

    Trả về số row đã xóa.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM FaceEmbedding
            WHERE MaNV = ?
        """, (ma_nv,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def count_face_embeddings(ma_nv):
    """
    Đếm số embedding hiện có của nhân viên.
    Dùng để kiểm tra trước khi đăng ký.

    Trả về int.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM FaceEmbedding
            WHERE MaNV = ?
        """, (ma_nv,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_all_face_embeddings():
    """
    Lấy toàn bộ face embedding trong hệ thống, kèm HoTen.

    Dùng cho PHASE 2 — Recognition / Matching.

    Trả về list of rows:
        (MaEmbedding, MaNV, VectorData, SoChieu, HoTen)

    VectorData là bytes (float32 little-endian), KHÔNG encode Base64.
    Trả list rỗng nếu chưa có embedding nào.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                fe.MaEmbedding,
                fe.MaNV,
                fe.VectorData,
                fe.SoChieu,
                nv.HoTen
            FROM FaceEmbedding fe
            JOIN NhanVien nv ON nv.MaNV = fe.MaNV
            ORDER BY fe.MaNV, fe.MaEmbedding
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_face_enrolled_employee_ids():
    """Return employee IDs with at least one saved face embedding."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT MaNV
            FROM FaceEmbedding
            ORDER BY MaNV
        """)
        return [int(row[0]) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_attendance_history_filtered(tu_ngay=None, den_ngay=None, keyword=None, page=1, limit=20):
    """
    Lấy danh sách lịch sử chấm công với bộ lọc bằng SQL và phân trang.
    Dùng cho trang Lịch sử chấm công của admin.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        base_query = """
            FROM ChamCong CC
            JOIN NhanVien NV ON CC.MaNV = NV.MaNV
            LEFT JOIN CaLamViec CLV ON CC.MaCa = CLV.MaCa
            WHERE 1=1
        """
        params = []
        if tu_ngay:
            base_query += " AND CAST(CC.GioVao AS DATE) >= ?"
            params.append(tu_ngay)
        if den_ngay:
            base_query += " AND CAST(CC.GioVao AS DATE) <= ?"
            params.append(den_ngay)
        if keyword:
            keyword = keyword.strip()
            base_query += " AND (NV.HoTen LIKE ? OR CC.MaNV LIKE ?)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
            
        # Count total
        cursor.execute(f"SELECT COUNT(CC.MaCC) {base_query}", tuple(params))
        total_row = cursor.fetchone()
        total = total_row[0] if total_row else 0
        
        # Data query
        query = f"""
            SELECT 
                CC.MaCC, CC.MaNV, NV.HoTen, CC.MaCa, CLV.TenCa, 
                CLV.GioBatDau, CLV.GioKetThuc, CC.GioVao, CC.GioRa
            {base_query}
            ORDER BY CC.GioVao DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        offset = (page - 1) * limit
        params.extend([offset, limit])
        
        cursor.execute(query, tuple(params))
        return cursor.fetchall(), total
    finally:
        conn.close()
