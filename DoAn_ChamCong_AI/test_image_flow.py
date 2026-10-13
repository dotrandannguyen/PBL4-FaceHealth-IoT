"""
test_image_flow.py — Test trực tiếp flow lưu ảnh bằng chứng
============================================================
KHÔNG dùng Flask, KHÔNG import ai_engine.
Test: database.insert_checkin / update_checkout với AnhVao / AnhRa.
"""

import sys
from datetime import date

# ── Bước 0: import database & services ──────────────────────────────────────
try:
    import database
    print("[OK] import database")
except Exception as e:
    print(f"[FAIL] import database: {e}")
    sys.exit(1)

try:
    import services
    print("[OK] import services (encode_frame_to_jpg available)")
except Exception as e:
    print(f"[FAIL] import services: {e}")
    sys.exit(1)

# ── Bước 1: Kiểm tra kết nối DB ─────────────────────────────────────────────
print("\n=== BƯỚC 1: Kết nối DB ===")
try:
    conn = database.get_connection()
    conn.close()
    print("[OK] Kết nối SQL Server thành công")
except Exception as e:
    print(f"[FAIL] Kết nối DB: {e}")
    sys.exit(1)

# ── Bước 2: Kiểm tra / phân ca MaNV=1 hôm nay ──────────────────────────────
MA_NV = 1
MA_CA = 1
MA_TB = 1
today = date.today().isoformat()

print(f"\n=== BƯỚC 2: Kiểm tra ca MaNV={MA_NV} ngày {today} ===")
try:
    shift_row = database.get_employee_shift(MA_NV, today)
    if shift_row:
        print(f"[OK] Đã có ca: MaCa={shift_row[0]}, TenCa={shift_row[1]}, "
              f"GioBatDau={shift_row[2]}, GioKetThuc={shift_row[3]}")
    else:
        print(f"[INFO] Chưa có ca — đang phân ca MaCa={MA_CA}...")
        database.assign_shift(MA_NV, MA_CA, today)
        shift_row = database.get_employee_shift(MA_NV, today)
        if shift_row:
            print(f"[OK] Phân ca thành công: MaCa={shift_row[0]}")
        else:
            print("[FAIL] Phân ca thất bại")
            sys.exit(1)
except Exception as e:
    print(f"[FAIL] Lỗi kiểm tra ca: {e}")
    sys.exit(1)

# ── Bước 3: Tạo fake image_bytes (JPEG bytes nhỏ) ───────────────────────────
print("\n=== BƯỚC 3: Tạo ảnh test ===")
try:
    import cv2
    import numpy as np

    # Tạo frame giả 100x100 màu xanh lá
    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    fake_frame[:, :] = (0, 180, 0)  # BGR green

    image_bytes = services.encode_frame_to_jpg(fake_frame)
    if image_bytes and len(image_bytes) > 0:
        print(f"[OK] encode_frame_to_jpg: {len(image_bytes)} bytes JPEG")
    else:
        print("[FAIL] encode_frame_to_jpg trả None")
        sys.exit(1)
except ImportError:
    print("[WARN] cv2 không có — dùng minimal JPEG bytes giả")
    # Tạo JPEG bytes tối thiểu hợp lệ (1x1 pixel JPEG)
    import base64
    MIN_JPEG_B64 = (
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
        "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
        "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
        "MjL/wAARCAABAAEDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUE/8QAIBAAAg"
        "IBBQEAAAAAAAAAAAAAAQIDBAUREiFBUf/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEA"
        "AAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCw2i5W2522lt9TTRS1VTKsUMbOFDOwAA"
        "JJ+AP3QBSlKAP/2Q=="
    )
    image_bytes = base64.b64decode(MIN_JPEG_B64)
    print(f"[OK] Dùng minimal JPEG: {len(image_bytes)} bytes")

# ── Bước 4: Xóa record ChamCong hôm nay của MaNV=1 (để test checkin fresh) ─
print("\n=== BƯỚC 4: Xóa record hôm nay (nếu có) để test checkin ===")
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM ChamCong
        WHERE MaNV = ?
          AND CAST(GioVao AS DATE) = CAST(GETDATE() AS DATE)
    """, (MA_NV,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"[OK] Đã xóa {deleted} record hôm nay của MaNV={MA_NV}")
except Exception as e:
    print(f"[WARN] Không xóa được record cũ: {e}")

# ── Bước 5: TEST CHECK-IN với ảnh ───────────────────────────────────────────
print("\n=== BƯỚC 5: TEST CHECK-IN (với AnhVao) ===")
ma_ca = shift_row[0]
try:
    ma_cc = database.insert_checkin(MA_NV, ma_ca, MA_TB, image_bytes)
    if ma_cc:
        print(f"[OK] insert_checkin thành công → MaCC={ma_cc}")
    else:
        print("[FAIL] insert_checkin trả None MaCC")
        sys.exit(1)
except Exception as e:
    print(f"[FAIL] insert_checkin lỗi: {e}")
    sys.exit(1)

# ── Bước 6: Kiểm tra AnhVao trong DB ────────────────────────────────────────
print("\n=== BƯỚC 6: Kiểm tra DATALENGTH(AnhVao) trong DB ===")
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MaCC, MaNV, GioVao, GioRa,
               DATALENGTH(AnhVao) AS KichThuocAnhVao,
               DATALENGTH(AnhRa)  AS KichThuocAnhRa
        FROM ChamCong
        WHERE MaCC = ?
    """, (ma_cc,))
    row = cursor.fetchone()
    conn.close()
    if row:
        k_vao = row[4]
        k_ra  = row[5]
        print(f"  MaCC             = {row[0]}")
        print(f"  MaNV             = {row[1]}")
        print(f"  GioVao           = {row[2]}")
        print(f"  GioRa            = {row[3]}")
        print(f"  KichThuocAnhVao  = {k_vao}")
        print(f"  KichThuocAnhRa   = {k_ra}")
        if k_vao and k_vao > 0:
            print(f"[PASS] AnhVao = {k_vao} bytes ✓")
        else:
            print("[FAIL] AnhVao IS NULL hoặc = 0")
    else:
        print(f"[FAIL] Không tìm thấy MaCC={ma_cc}")
except Exception as e:
    print(f"[FAIL] Lỗi truy vấn: {e}")

# ── Bước 7: TEST CHECK-OUT với ảnh ──────────────────────────────────────────
print("\n=== BƯỚC 7: TEST CHECK-OUT (với AnhRa) ===")
try:
    # Tạo ảnh checkout khác màu (đỏ) để phân biệt
    try:
        import cv2, numpy as np
        fake_frame2 = np.zeros((100, 100, 3), dtype=np.uint8)
        fake_frame2[:, :] = (0, 0, 200)  # BGR red
        image_bytes2 = services.encode_frame_to_jpg(fake_frame2)
    except Exception:
        image_bytes2 = image_bytes  # dùng lại nếu cv2 không có

    rows_affected = database.update_checkout(ma_cc, image_bytes2)
    print(f"[OK] update_checkout → {rows_affected} row(s) updated")
except Exception as e:
    print(f"[FAIL] update_checkout lỗi: {e}")

# ── Bước 8: Kiểm tra cả AnhVao và AnhRa ─────────────────────────────────────
print("\n=== BƯỚC 8: Kiểm tra DATALENGTH sau CHECK-OUT ===")
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MaCC, MaNV, GioVao, GioRa,
               DATALENGTH(AnhVao) AS KichThuocAnhVao,
               DATALENGTH(AnhRa)  AS KichThuocAnhRa
        FROM ChamCong
        WHERE MaCC = ?
    """, (ma_cc,))
    row = cursor.fetchone()
    conn.close()
    if row:
        k_vao = row[4]
        k_ra  = row[5]
        print(f"  MaCC             = {row[0]}")
        print(f"  GioVao           = {row[2]}")
        print(f"  GioRa            = {row[3]}")
        print(f"  KichThuocAnhVao  = {k_vao}")
        print(f"  KichThuocAnhRa   = {k_ra}")
        vao_ok = k_vao and k_vao > 0
        ra_ok  = k_ra  and k_ra  > 0
        print(f"[{'PASS' if vao_ok else 'FAIL'}] AnhVao = {k_vao} bytes")
        print(f"[{'PASS' if ra_ok  else 'FAIL'}] AnhRa  = {k_ra} bytes")
    else:
        print(f"[FAIL] Không tìm thấy MaCC={ma_cc}")
except Exception as e:
    print(f"[FAIL] Lỗi truy vấn: {e}")

# ── Bước 9: TEST get_attendance_image ────────────────────────────────────────
print("\n=== BƯỚC 9: Test database.get_attendance_image() ===")
try:
    img_in = database.get_attendance_image(ma_cc, "in")
    if img_in and len(img_in) > 0:
        print(f"[PASS] get_attendance_image(in)  → {len(img_in)} bytes")
    else:
        print("[FAIL] get_attendance_image(in) trả None hoặc rỗng")

    img_out = database.get_attendance_image(ma_cc, "out")
    if img_out and len(img_out) > 0:
        print(f"[PASS] get_attendance_image(out) → {len(img_out)} bytes")
    else:
        print("[FAIL] get_attendance_image(out) trả None hoặc rỗng")

    # Test invalid type → phải trả None
    img_inv = database.get_attendance_image(ma_cc, "invalid")
    if img_inv is None:
        print("[PASS] get_attendance_image(invalid) → None (security OK)")
    else:
        print("[FAIL] get_attendance_image(invalid) không trả None!")
except Exception as e:
    print(f"[FAIL] get_attendance_image lỗi: {e}")

# ── Bước 10: TOP 5 bản ghi mới nhất ─────────────────────────────────────────
print("\n=== BƯỚC 10: TOP 5 ChamCong mới nhất ===")
try:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 5
            MaCC, MaNV, GioVao, GioRa,
            DATALENGTH(AnhVao) AS KichThuocAnhVao,
            DATALENGTH(AnhRa)  AS KichThuocAnhRa
        FROM ChamCong
        ORDER BY MaCC DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    print(f"{'MaCC':>6} {'MaNV':>6} {'GioVao':>20} {'GioRa':>20} {'AnhVao(B)':>10} {'AnhRa(B)':>10}")
    print("-" * 78)
    for r in rows:
        print(f"{str(r[0]):>6} {str(r[1]):>6} {str(r[2]):>20} {str(r[3]):>20} "
              f"{str(r[4] or 'NULL'):>10} {str(r[5] or 'NULL'):>10}")
except Exception as e:
    print(f"[FAIL] Lỗi truy vấn TOP 5: {e}")

print("\n=== DONE ===")
