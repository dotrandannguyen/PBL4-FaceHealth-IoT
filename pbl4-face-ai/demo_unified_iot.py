"""
demo_unified_iot.py — Giao diện Demo & Kiểm thử Hệ thống Chấm công Thông minh
Kết hợp Face Recognition + Phân tích Thể trạng + Giả lập Sinh trắc học IoT (MAX30102).

Tính năng:
  - HUD trực quan trên OpenCV với Bounding Box, Top Banner tiến trình và Card Kết quả Late Fusion.
  - Bộ phím bấm Giả lập Phần cứng IoT (Mock Triggers):
      [SPACE] hoặc [1] : Giả lập phiên Bình thường (Bio_Normal: HR 70-90, SpO2 97-99)
      [2]             : Giả lập phiên Mệt mỏi / Căng thẳng (Bio_Warning: HR 104-112, SpO2 96)
      [3]             : Giả lập phiên Nguy hiểm Y tế (Bio_Danger: HR 125, SpO2 91)
      [a]             : Giả lập Rút tay ra sớm (ABORT_SESSION)
      [t]             : Kiểm thử Hard Timeout 7.0s (Không gửi DONE)
      [q]             : Thoát chương trình
  - Tùy chọn đọc cổng Serial thật từ ESP32: python demo_unified_iot.py --serial-port COM3
"""

import sys
import os
import time
import json
import random
import argparse
import threading
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    reconfig = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig):
        try:
            reconfig(encoding="utf-8", errors="replace")
        except Exception:
            pass

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "3")

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Thêm đường dẫn
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from unified_engine import UnifiedAttendanceEngine, SessionState

# Bảng màu HUD BGR (OpenCV)
COLORS = {
    "GREEN": (46, 204, 113),
    "YELLOW": (0, 215, 255),
    "ORANGE": (0, 140, 255),
    "RED": (50, 50, 240),
    "DARK_BG": (22, 27, 34),
    "PANEL_BG": (30, 36, 46),
    "WHITE": (255, 255, 255),
    "GRAY": (180, 180, 180),
    "CYAN": (255, 220, 0),
}

# Bảng màu RGB (PIL)
RGB_COLORS = {
    "GREEN": (46, 204, 113),
    "EMERALD": (16, 185, 129),
    "SKY": (14, 165, 233),
    "YELLOW": (245, 158, 11),
    "ORANGE": (249, 115, 22),
    "RED": (239, 68, 68),
    "WHITE": (255, 255, 255),
    "GRAY": (148, 163, 184),
    "LIGHT_GRAY": (226, 232, 240),
    "CYAN": (6, 182, 212),
    "MUTED": (100, 116, 139),
    "DARK_CARD": (22, 28, 38),
}

def load_hud_fonts():
    """Khởi tạo bộ font tiếng Việt Segoe UI / Arial sắc nét với đầy đủ dấu UTF-8."""
    for fn in ["segoeui.ttf", "arial.ttf", "calibri.ttf"]:
        try:
            bn = "segoeuib.ttf" if "segoe" in fn else ("arialbd.ttf" if "arial" in fn else "calibrib.ttf")
            return {
                "header_large": ImageFont.truetype(bn, 20),
                "name_large": ImageFont.truetype(bn, 22),
                "stat_val": ImageFont.truetype(bn, 16),
                "body_bold": ImageFont.truetype(bn, 14),
                "body": ImageFont.truetype(fn, 14),
                "body_small": ImageFont.truetype(fn, 12),
                "countdown": ImageFont.truetype(bn, 13),
                "banner_title": ImageFont.truetype(bn, 18),
                "banner_sub": ImageFont.truetype(fn, 13),
                "panel_title": ImageFont.truetype(bn, 13),
                "panel_body": ImageFont.truetype(fn, 13),
                "panel_sub": ImageFont.truetype(fn, 11),
                "bbox_name": ImageFont.truetype(bn, 14),
                "bbox_sub": ImageFont.truetype(fn, 12),
            }
        except Exception:
            continue
    def_font = ImageFont.load_default()
    keys = [
        "header_large", "name_large", "stat_val", "body_bold",
        "body", "body_small", "countdown", "banner_title", "banner_sub",
        "panel_title", "panel_body", "panel_sub", "bbox_name", "bbox_sub"
    ]
    return {k: def_font for k in keys}

HUD_FONTS = load_hud_fonts()


class MockHardwareController:
    """Quản lý các sự kiện hẹn giờ giả lập phần cứng IoT."""

    def __init__(self, engine: UnifiedAttendanceEngine):
        self.engine = engine
        self._timer: Optional[threading.Timer] = None

    def cancel_pending(self):
        if self._timer is not None and self._timer.is_alive():
            self._timer.cancel()
        self._timer = None

    def trigger_normal(self):
        self.cancel_pending()
        self.engine.start_session(ir=68500)
        hr = random.randint(72, 88)
        spo2 = random.randint(97, 99)
        self._timer = threading.Timer(3.5, lambda: self.engine.done_session(hr=hr, spo2=spo2, ir_avg=69000))
        self._timer.daemon = True
        self._timer.start()

    def trigger_warning(self):
        self.cancel_pending()
        self.engine.start_session(ir=67000)
        hr = random.randint(104, 112)
        spo2 = 95
        self._timer = threading.Timer(3.5, lambda: self.engine.done_session(hr=hr, spo2=spo2, ir_avg=67500))
        self._timer.daemon = True
        self._timer.start()

    def trigger_danger(self):
        self.cancel_pending()
        self.engine.start_session(ir=66000)
        hr = 125
        spo2 = 91
        self._timer = threading.Timer(3.5, lambda: self.engine.done_session(hr=hr, spo2=spo2, ir_avg=66500))
        self._timer.daemon = True
        self._timer.start()

    def trigger_timeout_test(self):
        self.cancel_pending()
        self.engine.start_session(ir=65000)
        print("[MockIoT] Đã kích hoạt START_SESSION — Không gửi DONE để test Hard Timeout (7s)...")

    def trigger_abort(self):
        self.cancel_pending()
        self.engine.abort_session(reason="FINGER_REMOVED (Mock)")


def start_serial_listener(engine: UnifiedAttendanceEngine, port: str, baud: int = 115200):
    """Lắng nghe gói tin JSON từ ESP32 qua Serial trên Background Thread."""
    try:
        import serial
    except ImportError:
        print("[Serial] ❌ Chưa cài thư viện pyserial. Vui lòng cài: pip install pyserial")
        return

    def listener():
        try:
            print(f"[Serial] 🔌 Đang kết nối cổng {port} @ {baud} bps...")
            ser = serial.Serial(port, baud, timeout=1.0)
            time.sleep(1.5)
            print(f"[Serial] ✅ Đã kết nối {port}. Đang đọc dữ liệu JSON...")

            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("{"):
                    continue

                try:
                    data = json.loads(line)
                    event = data.get("event")
                    if event == "START_SESSION":
                        engine.start_session(ir=data.get("ir", 65000))
                    elif event == "ABORT_SESSION":
                        engine.abort_session(reason=data.get("reason", "FINGER_REMOVED"))
                    elif event == "DONE_SESSION":
                        engine.done_session(
                            hr=int(data.get("hr", 0)),
                            spo2=int(data.get("spo2", 0)),
                            ir_avg=int(data.get("ir_avg", 0)),
                        )
                except Exception as e:
                    print(f"[Serial] Lỗi parse JSON: {e}")

        except Exception as e:
            print(f"[Serial] ❌ Lỗi cổng Serial: {e}")

    t = threading.Thread(target=listener, daemon=True)
    t.start()


# -------------------------------------------------------------
# CÁC HÀM VẼ GIAO DIỆN HUD OPENCV
# -------------------------------------------------------------
def draw_hud(frame: np.ndarray, info: dict, fps: float) -> np.ndarray:
    """Vẽ toàn bộ HUD thông tin, bounding box và overlay kết quả bằng tiếng Việt sắc nét."""
    vis = frame.copy()
    h, w = vis.shape[:2]
    state: SessionState = info["state"]
    elapsed_state = info["elapsed_in_state"]
    elapsed_session = info["elapsed_in_session"]

    # 1. TOP BANNER TRẠNG THÁI & PROGRESS BAR
    banner_h = 70
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), COLORS["DARK_BG"], -1)
    vis = cv2.addWeighted(overlay, 0.85, vis, 0.15, 0)

    # Tiêu đề trạng thái & Màu chủ đạo
    if state == SessionState.IDLE:
        state_text = "SẴN SÀNG CHẤM CÔNG"
        state_rgb = RGB_COLORS["SKY"]
        state_bgr = (233, 165, 14)
        sub_text = "Đặt ngón tay lên cảm biến hoặc bấm [1] để quét  |  [Q] Thoát"
        prog_ratio = 0.0

    elif state == SessionState.WARMUP:
        state_text = f"ĐANG KHỞI ĐỘNG CẢM BIẾN ({elapsed_state:.1f}s / 1.2s)"
        state_rgb = RGB_COLORS["YELLOW"]
        state_bgr = (11, 158, 245)
        sub_text = "Vui lòng nhìn thẳng vào camera và giữ ngón tay trên cảm biến..."
        prog_ratio = min(1.0, elapsed_state / 1.2)

    elif state == SessionState.SCANNING:
        state_text = f"ĐANG QUÉT NHẬN DIỆN... ({elapsed_session:.1f}s)"
        state_rgb = RGB_COLORS["EMERALD"]
        state_bgr = (129, 185, 16)
        sub_text = "Đang đối chiếu khuôn mặt và phân tích chỉ số thể trạng realtime..."
        prog_ratio = min(1.0, elapsed_session / 3.5)

    elif state == SessionState.COMPLETED:
        remain_s = max(0.0, 5.0 - elapsed_state)
        state_text = f"HOÀN TẤT ĐIỂM DANH (Tự đóng sau {remain_s:.1f}s)"
        state_rgb = RGB_COLORS["EMERALD"]
        state_bgr = (129, 185, 16)
        sub_text = "Đã lưu kết quả thành công và đồng bộ lên Web."
        prog_ratio = 1.0

    else:  # ABORTED
        reason = info.get("abort_reason", "Rút tay sớm")
        remain_s = max(0.0, 2.5 - elapsed_state)
        state_text = f"CHẤM CÔNG BỊ HỦY ({reason})"
        state_rgb = RGB_COLORS["RED"]
        state_bgr = (68, 68, 239)
        sub_text = f"Tự động quay về màn hình chờ sau {remain_s:.1f}s..."
        prog_ratio = 1.0

    # Thanh tiến trình (Progress Bar)
    bar_y = banner_h - 4
    cv2.rectangle(vis, (0, bar_y), (w, banner_h), (40, 48, 60), -1)
    if prog_ratio > 0.0:
        cv2.rectangle(vis, (0, bar_y), (int(w * prog_ratio), banner_h), state_bgr, -1)

    # 2. VẼ BOUNDING BOX KHUÔN MẶT
    bbox = info.get("face_bbox")
    ai2_res = info.get("ai2_result")
    bbox_info = None

    if bbox is not None:
        bx1, by1, bx2, by2 = bbox
        cur_ai2_status = ai2_res.get("status", "Unknown") if ai2_res else "Unknown"

        st_map = {
            "Normal": ("Tỉnh táo", (129, 185, 16), RGB_COLORS["EMERALD"]),
            "Fatigue": ("Mệt mỏi", (11, 158, 245), RGB_COLORS["YELLOW"]),
            "Exhausted": ("Buồn ngủ", (68, 68, 239), RGB_COLORS["RED"]),
            "Turned_Head": ("Lệch góc", (11, 158, 245), RGB_COLORS["YELLOW"]),
            "Unknown": ("Đang quét", (233, 165, 14), RGB_COLORS["SKY"]),
        }
        st_vn, box_bgr, box_rgb = st_map.get(cur_ai2_status, ("Đang quét", (233, 165, 14), RGB_COLORS["SKY"]))

        cv2.rectangle(vis, (bx1, by1), (bx2, by2), box_bgr, 2)

        name_str = info.get("identified_name") or "Đang nhận diện..."
        sid = info.get("identified_id")
        sim_val = info.get("identity_sim", 0.0)
        if sid and sim_val > 0.1:
            label_id = f"{name_str} ({sid})"
        else:
            label_id = name_str

        label_st = f"Thể trạng: {st_vn}"

        bg_w = max(220, bx2 - bx1)
        bg_h = 44
        ty1 = max(banner_h + 8, by1 - bg_h - 4)

        cv2.rectangle(vis, (bx1, ty1), (bx1 + bg_w, ty1 + bg_h), (18, 24, 34), -1)
        cv2.rectangle(vis, (bx1, ty1), (bx1 + bg_w, ty1 + bg_h), box_bgr, 1)

        bbox_info = {
            "label_id": label_id,
            "label_st": label_st,
            "box_rgb": box_rgb,
            "pos": (bx1 + 8, ty1 + 4, ty1 + 23),
        }

    # 3. BẢNG THÔNG SỐ REALTIME GÓC DƯỚI BÊN TRÁI (TINH GỌN, SANG TRỌNG)
    stats_w, stats_h = 320, 115
    sx1, sy1 = 15, h - stats_h - 15
    panel_overlay = vis.copy()
    cv2.rectangle(panel_overlay, (sx1, sy1), (sx1 + stats_w, sy1 + stats_h), COLORS["DARK_BG"], -1)
    vis = cv2.addWeighted(panel_overlay, 0.85, vis, 0.15, 0)
    cv2.rectangle(vis, (sx1, sy1), (sx1 + stats_w, sy1 + stats_h), (48, 58, 75), 1)

    m = info.get("latest_metrics", {})
    ear_v = m.get("ear", 0.0)
    mar_v = m.get("mar", 0.0)
    pitch_v = m.get("pitch", 0.0)
    yaw_v = m.get("yaw", 0.0)
    sharp_v = m.get("sharpness", 0.0)

    # 4. OVERLAY CARD KẾT QUẢ KHI COMPLETED (BỐ CỤC 2 CỘT HIỆN ĐẠI)
    modal_info = None
    if state == SessionState.COMPLETED and info.get("completed_record") is not None:
        rec = info["completed_record"]
        fusion = rec.get("fusion_result", {})
        att_action = rec.get("attendance_action", "")
        web_res = rec.get("web_result", {})
        is_completed_already = (
            web_res.get("action") == "completed"
            or att_action == "DA_CHECK_OUT"
            or "DA CHECK-OUT" in att_action
        )

        if is_completed_already:
            modal_bgr = (68, 68, 239)
            modal_rgb = RGB_COLORS["RED"]
            modal_title = "BẠN ĐÃ CHECK-OUT HÔM NAY"
            modal_desc = "Hôm nay bạn đã hoàn thành ca làm việc."
            modal_note = "Hệ thống không ghi nhận thêm lượt chấm công mới."
        elif "CHECK-OUT" in att_action:
            modal_bgr = (233, 165, 14)
            modal_rgb = RGB_COLORS["SKY"]
            modal_title = "CHECK-OUT THÀNH CÔNG"
            modal_desc = "Đã xác nhận hoàn thành ca làm việc."
            modal_note = "Chúc bạn ra về an toàn và vui vẻ!"
        elif "CHECK-IN" in att_action:
            modal_bgr = (129, 185, 16)
            modal_rgb = RGB_COLORS["EMERALD"]
            modal_title = "CHECK-IN THÀNH CÔNG"
            modal_desc = "Bắt đầu tính giờ làm việc hôm nay."
            modal_note = "Chúc bạn một ngày làm việc hiệu quả!"
        else:
            modal_bgr = (129, 185, 16)
            modal_rgb = RGB_COLORS["EMERALD"]
            modal_title = "ĐIỂM DANH THÀNH CÔNG"
            modal_desc = "Đã ghi nhận dữ liệu điểm danh."
            modal_note = ""

        mw, mh = 780, 350
        mx1, my1 = (w - mw) // 2, (h - mh) // 2

        # Nền card chính
        card_bg = vis.copy()
        cv2.rectangle(card_bg, (mx1, my1), (mx1 + mw, my1 + mh), (15, 19, 26), -1)
        vis = cv2.addWeighted(card_bg, 0.93, vis, 0.07, 0)
        cv2.rectangle(vis, (mx1, my1), (mx1 + mw, my1 + mh), modal_bgr, 2)

        # Header Bar
        cv2.rectangle(vis, (mx1, my1), (mx1 + mw, my1 + 52), (22, 28, 38), -1)
        cv2.rectangle(vis, (mx1, my1), (mx1 + mw, my1 + 4), modal_bgr, -1)
        cv2.line(vis, (mx1, my1 + 52), (mx1 + mw, my1 + 52), (40, 48, 60), 1)

        # Cột Trái: Thẻ Nhân viên
        lx1, ly1 = mx1 + 22, my1 + 66
        lw, lh = 350, 232
        cv2.rectangle(vis, (lx1, ly1), (lx1 + lw, ly1 + lh), (22, 28, 38), -1)
        cv2.rectangle(vis, (lx1, ly1), (lx1 + lw, ly1 + lh), (38, 48, 64), 1)

        # Cột Phải: Thẻ Chỉ số hoặc Cảnh báo
        rx1, ry1 = mx1 + 392, my1 + 66
        rw, rh = 366, 232
        if is_completed_already:
            cv2.rectangle(vis, (rx1, ry1), (rx1 + rw, ry1 + rh), (32, 20, 24), -1)
            cv2.rectangle(vis, (rx1, ry1), (rx1 + rw, ry1 + rh), (100, 35, 45), 1)
        else:
            # 3 thẻ mini bên phải
            cv2.rectangle(vis, (rx1, ry1), (rx1 + rw, ry1 + 70), (22, 28, 38), -1)
            cv2.rectangle(vis, (rx1, ry1), (rx1 + rw, ry1 + 70), (38, 48, 64), 1)

            cv2.rectangle(vis, (rx1, ry1 + 78), (rx1 + rw, ry1 + 148), (22, 28, 38), -1)
            cv2.rectangle(vis, (rx1, ry1 + 78), (rx1 + rw, ry1 + 148), (38, 48, 64), 1)

            cv2.rectangle(vis, (rx1, ry1 + 156), (rx1 + rw, ry1 + 232), (22, 28, 38), -1)
            cv2.rectangle(vis, (rx1, ry1 + 156), (rx1 + rw, ry1 + 232), (38, 48, 64), 1)

        # Footer line
        cv2.line(vis, (mx1 + 20, my1 + mh - 36), (mx1 + mw - 20, my1 + mh - 36), (35, 42, 54), 1)

        modal_info = {
            "pos": (mx1, my1, mw, mh),
            "left_pos": (lx1, ly1, lw, lh),
            "right_pos": (rx1, ry1, rw, rh),
            "bgr": modal_bgr,
            "rgb": modal_rgb,
            "title": modal_title,
            "desc": modal_desc,
            "note": modal_note,
            "is_completed_already": is_completed_already,
            "rec": rec,
            "fusion": fusion,
        }

    # 5. CHUYỂN SANG PIL ĐỂ VẼ TOÀN BỘ CHỮ TIẾNG VIỆT CÓ DẤU SẮC NÉT
    pil_img = Image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    # 5.1 Vẽ chữ Top Banner
    draw.text((20, 14), state_text, font=HUD_FONTS["banner_title"], fill=state_rgb)
    draw.text((20, 42), sub_text, font=HUD_FONTS["banner_sub"], fill=RGB_COLORS["LIGHT_GRAY"])

    # 5.2 Vẽ chữ Bounding Box
    if bbox_info is not None:
        bx_txt, by_id, by_st = bbox_info["pos"]
        draw.text((bx_txt, by_id), bbox_info["label_id"], font=HUD_FONTS["bbox_name"], fill=RGB_COLORS["WHITE"])
        draw.text((bx_txt, by_st), bbox_info["label_st"], font=HUD_FONTS["bbox_sub"], fill=bbox_info["box_rgb"])

    # 5.3 Vẽ chữ Bảng Thống số Realtime (Cực kỳ tinh gọn)
    draw.text((sx1 + 14, sy1 + 10), "THÔNG SỐ REALTIME", font=HUD_FONTS["panel_title"], fill=RGB_COLORS["SKY"])
    draw.text((sx1 + stats_w - 75, sy1 + 10), f"FPS: {fps:.0f}", font=HUD_FONTS["panel_title"], fill=RGB_COLORS["GRAY"])
    draw.text((sx1 + 14, sy1 + 34), f"Mắt (EAR): {ear_v:.3f}   •   Miệng (MAR): {mar_v:.3f}", font=HUD_FONTS["panel_body"], fill=RGB_COLORS["LIGHT_GRAY"])
    draw.text((sx1 + 14, sy1 + 58), f"Độ nét: {sharp_v:.1f}      •   Góc đầu: {pitch_v:.0f}°/{yaw_v:.0f}°", font=HUD_FONTS["panel_body"], fill=RGB_COLORS["LIGHT_GRAY"])
    draw.text((sx1 + 14, sy1 + 86), "[1] Chấm công   •   [Q] Thoát", font=HUD_FONTS["panel_sub"], fill=RGB_COLORS["MUTED"])

    # 5.4 Vẽ chữ Thẻ Kết quả Trung tâm (Completed Modal)
    if modal_info is not None:
        mx1, my1, mw, mh = modal_info["pos"]
        lx1, ly1, lw, lh = modal_info["left_pos"]
        rx1, ry1, rw, rh = modal_info["right_pos"]
        m_rgb = modal_info["rgb"]
        m_rec = modal_info["rec"]
        m_fusion = modal_info["fusion"]
        remain_s = max(0.0, 5.0 - elapsed_state)
        time_now = time.strftime("%H:%M:%S")

        # Header Text
        draw.text((mx1 + 22, my1 + 15), modal_info["title"], font=HUD_FONTS["header_large"], fill=m_rgb)
        draw.text((mx1 + mw - 140, my1 + 18), time_now, font=HUD_FONTS["body"], fill=RGB_COLORS["GRAY"])

        s_name = m_rec.get("student_name", "Chưa rõ")
        s_id = m_rec.get("student_id", "Unknown")

        # Cột Trái (Thông tin Nhân viên)
        draw.text((lx1 + 18, ly1 + 14), "NHÂN VIÊN", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
        draw.text((lx1 + 18, ly1 + 34), s_name, font=HUD_FONTS["name_large"], fill=RGB_COLORS["WHITE"])
        draw.text((lx1 + 18, ly1 + 68), f"Mã số: {s_id}", font=HUD_FONTS["body_bold"], fill=RGB_COLORS["SKY"])
        draw.line([(lx1 + 18, ly1 + 96), (lx1 + lw - 18, ly1 + 96)], fill=(50, 60, 75))

        draw.text((lx1 + 18, ly1 + 108), modal_info["desc"], font=HUD_FONTS["body"], fill=RGB_COLORS["LIGHT_GRAY"])
        draw.text((lx1 + 18, ly1 + 132), modal_info["note"], font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])

        f_status = m_fusion.get("final_status", "Đạt chuẩn")
        draw.text((lx1 + 18, ly1 + 175), "ĐÁNH GIÁ SỨC KHỎE", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
        draw.text((lx1 + 18, ly1 + 195), f_status, font=HUD_FONTS["stat_val"], fill=m_rgb)

        # Cột Phải
        if modal_info["is_completed_already"]:
            draw.text((rx1 + 20, ry1 + 18), "QUY ĐỊNH ĐIỂM DANH", font=HUD_FONTS["body_bold"], fill=RGB_COLORS["YELLOW"])
            draw.text((rx1 + 20, ry1 + 52), "• Mỗi ngày chỉ có 1 lần Check-out duy nhất.", font=HUD_FONTS["body"], fill=RGB_COLORS["LIGHT_GRAY"])
            draw.text((rx1 + 20, ry1 + 82), "• Dữ liệu giờ ra đã được lưu an toàn vào hệ thống.", font=HUD_FONTS["body"], fill=RGB_COLORS["LIGHT_GRAY"])
            draw.text((rx1 + 20, ry1 + 112), "• Quét lại không làm thay đổi giờ ra của bạn.", font=HUD_FONTS["body"], fill=RGB_COLORS["LIGHT_GRAY"])
            draw.text((rx1 + 20, ry1 + 155), "Hỗ trợ: Nếu cần điểm danh lại, vui lòng liên hệ", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
            draw.text((rx1 + 20, ry1 + 176), "Quản trị viên trên trang Web để xóa phiên.", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])

        else:
            face_st = m_rec.get("ai2_face_status", "Normal")
            face_st_vn = {
                "Normal": "Tỉnh táo & Sẵn sàng",
                "Fatigue": "Mệt mỏi / Cần nghỉ ngơi",
                "Exhausted": "Kiệt sức / Buồn ngủ",
                "Turned_Head": "Lệch góc nhìn"
            }.get(face_st, face_st)

            iot = m_rec.get("iot_metrics", {})
            hr_val = iot.get("hr", 75)
            spo2_val = iot.get("spo2", 98)
            recom = m_fusion.get("recommendation", "Trạng thái ổn định.")

            # Khối 1: Thể trạng
            draw.text((rx1 + 18, ry1 + 12), "THỂ TRẠNG KHUÔN MẶT", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
            draw.text((rx1 + 18, ry1 + 34), face_st_vn, font=HUD_FONTS["stat_val"], fill=m_rgb)

            # Khối 2: Sinh trắc học
            draw.text((rx1 + 18, ry1 + 90), "SINH TRẮC HỌC (MAX30102)", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
            draw.text((rx1 + 18, ry1 + 112), f"Nhịp tim: {hr_val} BPM   •   SpO2: {spo2_val}%", font=HUD_FONTS["stat_val"], fill=RGB_COLORS["WHITE"])

            # Khối 3: Lời khuyên
            draw.text((rx1 + 18, ry1 + 168), "LỜI KHUYÊN SỨC KHỎE", font=HUD_FONTS["body_small"], fill=RGB_COLORS["GRAY"])
            draw.text((rx1 + 18, ry1 + 190), recom, font=HUD_FONTS["body_small"], fill=RGB_COLORS["LIGHT_GRAY"])

        # Footer Bar
        draw.text((mx1 + 22, my1 + mh - 26), "Hệ thống Điểm danh Thông minh PBL4", font=HUD_FONTS["body_small"], fill=RGB_COLORS["MUTED"])
        draw.text((mx1 + mw - 220, my1 + mh - 26), f"Màn hình tự đóng sau {remain_s:.1f}s", font=HUD_FONTS["countdown"], fill=RGB_COLORS["CYAN"])

    # Chuyển ngược lại OpenCV BGR
    vis = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return vis


# -------------------------------------------------------------
# MAIN ENTRY POINT
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Demo Unified Attendance Engine (Face AI + IoT MAX30102)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (mặc định: 0)")
    parser.add_argument("--serial-port", type=str, default=None, help="Cổng Serial ESP32 (ví dụ: COM3 hoặc /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate Serial (mặc định: 115200)")
    parser.add_argument("--threshold", type=float, default=0.45, help="Ngưỡng nhận diện khuôn mặt (mặc định: 0.45)")
    args = parser.parse_args()

    print("\n=======================================================")
    print("🚀 KHỞI ĐỘNG HỆ THỐNG ĐIỂM DANH THÔNG MINH PBL4 (UNIFIED AI + IOT)")
    print("=======================================================")

    # Khởi tạo Unified Attendance Engine
    engine = UnifiedAttendanceEngine(face_threshold=args.threshold)
    mock_iot = MockHardwareController(engine)

    # Nếu có cổng Serial thật
    if args.serial_port:
        start_serial_listener(engine, args.serial_port, args.baud)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[Demo] ❌ Không mở được camera index {args.camera}!")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("\n[Demo] 🎮 HƯỚNG DẪN ĐIỀU KHIỂN:")
    print("  [SPACE] hoặc [1] : Bắt đầu phiên chấm công BÌNH THƯỜNG (Bio_Normal)")
    print("  [2]             : Bắt đầu phiên CĂNG THẲNG / TẬP THỂ DỤC (Bio_Warning)")
    print("  [3]             : Bắt đầu phiên CẢNH BÁO Y TẾ (Bio_Danger: HR cao, SpO2 tụt)")
    print("  [a]             : Rút tay ra sớm giữa chừng (Hủy phiên ABORT_SESSION)")
    print("  [t]             : Kiểm thử Hard Timeout 7.0s (Không gửi gói DONE)")
    print("  [q]             : Thoát chương trình an toàn\n")

    prev_time = time.time()
    fps = 30.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[Demo] Lỗi đọc frame từ camera!")
                break

            curr_time = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(curr_time - prev_time, 1e-5))
            prev_time = curr_time

            # Update engine
            info = engine.update(frame)

            # Vẽ HUD
            vis = draw_hud(frame, info, fps)

            cv2.imshow("PBL4 - He Thong Diem Danh Thong Minh (Unified AI + IoT)", vis)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("[Demo] Người dùng bấm Q để thoát.")
                break
            elif key in [ord(" "), ord("1")]:
                print("[Demo] Phím [1] / [SPACE] -> Giả lập Bio_Normal")
                mock_iot.trigger_normal()
            elif key == ord("2"):
                print("[Demo] Phím [2] -> Giả lập Bio_Warning")
                mock_iot.trigger_warning()
            elif key == ord("3"):
                print("[Demo] Phím [3] -> Giả lập Bio_Danger")
                mock_iot.trigger_danger()
            elif key == ord("a"):
                print("[Demo] Phím [A] -> Giả lập Abort (rút tay)")
                mock_iot.trigger_abort()
            elif key == ord("t"):
                print("[Demo] Phím [T] -> Giả lập Timeout")
                mock_iot.trigger_timeout_test()

    finally:
        mock_iot.cancel_pending()
        engine.close()
        cap.release()
        cv2.destroyAllWindows()
        print("[Demo] Đã giải phóng Camera và tắt luồng nền thành công.")


if __name__ == "__main__":
    main()
