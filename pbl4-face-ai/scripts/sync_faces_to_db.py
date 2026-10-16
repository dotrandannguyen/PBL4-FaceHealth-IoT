"""
sync_faces_to_db.py — Đồng bộ toàn bộ khuôn mặt đã đăng ký offline vào CSDL MariaDB của Web
"""
import os
import sys
import pickle
import pymysql
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REG_DIR = DATA_DIR / "registered"
EMB_PATH = DATA_DIR / "embeddings.pkl"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.face_engine import FaceEngine

def main():
    print(">> Đang nạp FaceEngine...")
    engine = FaceEngine(model_name="buffalo_sc")

    print(">> Đang kết nối MariaDB...")
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="pbl4_user",
        password="pbl4_password",
        database="DoAn_ChamCong_AI_MariaDB",
        charset="utf8mb4",
        autocommit=True
    )
    cursor = conn.cursor()

    # Xóa lịch sử chấm công test cũ để người dùng test mới hoàn toàn
    cursor.execute("DELETE FROM LichSuSucKhoe;")
    cursor.execute("DELETE FROM ChamCong;")
    print(">> Đã dọn dẹp bảng ChamCong & LichSuSucKhoe test cũ.")

    if not EMB_PATH.exists():
        print(">> Không tìm thấy embeddings.pkl")
        return

    with open(EMB_PATH, "rb") as f:
        db = pickle.load(f)

    for sid, info in db.items():
        if not sid.startswith("SV"):
            continue
        emp_id = int(sid.replace("SV", ""))
        raw_name = info.get("name", f"Nhân viên #{emp_id}")

        # Tên chuẩn hiển thị
        if sid == "SV001":
            clean_name = "Nguyễn Văn A (SV001)"
        elif sid == "SV002":
            clean_name = "Trần Văn Hùng (SV002)"
        else:
            clean_name = f"{raw_name} ({sid})"

        # 1. Cập nhật hoặc tạo NhanVien
        cursor.execute(
            """
            INSERT INTO NhanVien (MaNV, HoTen, MaVaiTro)
            VALUES (%s, %s, 2)
            ON DUPLICATE KEY UPDATE HoTen = VALUES(HoTen)
            """,
            (emp_id, clean_name)
        )

        # 2. Xóa embedding cũ của MaNV này trong MariaDB
        cursor.execute("DELETE FROM FaceEmbedding WHERE MaNV = %s", (emp_id,))

        # 3. Lấy ảnh mẫu từ data/registered/{sid}
        user_reg_dir = REG_DIR / sid
        sample_files = sorted(list(user_reg_dir.glob("*.jpg"))) if user_reg_dir.exists() else []

        frontal_img_bytes = None

        if sample_files:
            import cv2
            for img_path in sample_files:
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                emb = engine.embed(img)
                if emb is None:
                    continue
                emb = emb.astype(np.float32)
                emb = emb / np.linalg.norm(emb)
                vec_bytes = emb.tobytes()

                with open(img_path, "rb") as f_img:
                    img_bytes = f_img.read()

                if frontal_img_bytes is None:
                    frontal_img_bytes = img_bytes

                cursor.execute(
                    """
                    INSERT INTO FaceEmbedding (MaNV, VectorData, AnhKhuonMat, SoChieu, ThoiGianTao)
                    VALUES (%s, %s, %s, 512, NOW())
                    """,
                    (emp_id, vec_bytes, img_bytes)
                )
            print(f">> ✅ Đã đồng bộ {len(sample_files)} ảnh mẫu khuôn mặt cho {clean_name} (MaNV={emp_id})")
        else:
            # Nếu không có ảnh gốc, dùng mean embedding
            mean_emb = info.get("embedding")
            if mean_emb is not None:
                mean_emb = mean_emb.astype(np.float32)
                vec_bytes = mean_emb.tobytes()
                cursor.execute(
                    """
                    INSERT INTO FaceEmbedding (MaNV, VectorData, AnhKhuonMat, SoChieu, ThoiGianTao)
                    VALUES (%s, %s, NULL, 512, NOW())
                    """,
                    (emp_id, vec_bytes)
                )
                print(f">> ✅ Đã đồng bộ vector trung bình cho {clean_name} (MaNV={emp_id})")

        # 4. Cập nhật Avatar NhanVien nếu có ảnh
        if frontal_img_bytes is not None:
            import base64
            b64_avatar = "data:image/jpeg;base64," + base64.b64encode(frontal_img_bytes).decode("ascii")
            cursor.execute("UPDATE NhanVien SET AnhKhuonMat = %s WHERE MaNV = %s", (b64_avatar, emp_id))

    cursor.close()
    conn.close()
    print(">> 🎉 Hoàn tất đồng bộ toàn bộ dữ liệu khuôn mặt vào CSDL MariaDB!")

if __name__ == "__main__":
    main()
