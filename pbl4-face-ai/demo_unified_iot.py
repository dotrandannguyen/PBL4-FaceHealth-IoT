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

# Thêm đường dẫn
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from unified_engine import UnifiedAttendanceEngine, SessionState

# Bảng màu HUD BGR
COLORS = {
    "GREEN": (46, 204, 113),
    "YELLOW": (0, 215, 255),
    "ORANGE": (0, 140, 255),
    "RED": (50, 50, 240),
    "DARK_BG": (25, 25, 25),
    "PANEL_BG": (35, 35, 35),
    "WHITE": (255, 255, 255),
    "GRAY": (180, 180, 180),
    "CYAN": (255, 220, 0),
}


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
    """Vẽ toàn bộ HUD thông tin, bounding box và overlay kết quả."""
    vis = frame.copy()
    h, w = vis.shape[:2]
    state: SessionState = info["state"]
    elapsed_state = info["elapsed_in_state"]
    elapsed_session = info["elapsed_in_session"]

    # 1. TOP BANNER TRẠNG THÁI & PROGRESS BAR
    banner_h = 75
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), COLORS["DARK_BG"], -1)
    vis = cv2.addWeighted(overlay, 0.75, vis, 0.25, 0)

    # Tiêu đề trạng thái & Màu chủ đạo
    if state == SessionState.IDLE:
        state_text = "TRẠNG THÁI: IDLE (CHỜ ĐẶT TAY LÊN CẢM BIẾN)"
        state_color = COLORS["CYAN"]
        sub_text = "Phím bấm test: [1] Bio_Normal | [2] Bio_Warning | [3] Bio_Danger | [a] Abort | [t] Timeout"
        prog_ratio = 0.0

    elif state == SessionState.WARMUP:
        state_text = f"TRẠNG THÁI: WARMUP ({elapsed_state:.1f}s / 1.2s)"
        state_color = COLORS["YELLOW"]
        sub_text = "Đang ổn định tín hiệu ngón tay & hướng dẫn tư thế mặt thẳng..."
        prog_ratio = min(1.0, elapsed_state / 1.2)

    elif state == SessionState.SCANNING:
        state_text = f"TRẠNG THÁI: SCANNING ({elapsed_session:.1f}s / ~3.5s)"
        state_color = COLORS["GREEN"]
        sub_text = "Đang thu thập AI 1 (Face ID) & AI 2 (Độ mệt mỏi) song song..."
        prog_ratio = min(1.0, elapsed_session / 3.5)

    elif state == SessionState.COMPLETED:
        state_text = f"TRẠNG THÁI: COMPLETED (HOÀN TẤT CHẤM CÔNG - {3.0 - elapsed_state:.1f}s)"
        state_color = COLORS["GREEN"]
        sub_text = "Đã hợp nhất kết quả Late Fusion, lưu snapshot và ghi log."
        prog_ratio = 1.0

    else:  # ABORTED
        reason = info.get("abort_reason", "UNKNOWN")
        state_text = f"TRẠNG THÁI: ABORTED (ĐÃ HỦY: {reason})"
        state_color = COLORS["RED"]
        sub_text = f"Tự động quay về IDLE sau {2.5 - elapsed_state:.1f}s..."
        prog_ratio = 1.0

    cv2.putText(vis, state_text, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, state_color, 2)
    cv2.putText(vis, sub_text, (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["WHITE"], 1)

    # Thanh tiến trình (Progress Bar)
    bar_y = banner_h - 6
    cv2.rectangle(vis, (0, bar_y), (w, banner_h), (50, 50, 50), -1)
    if prog_ratio > 0.0:
        cv2.rectangle(vis, (0, bar_y), (int(w * prog_ratio), banner_h), state_color, -1)

    # 2. VẼ BOUNDING BOX KHUÔN MẶT
    bbox = info.get("face_bbox")
    ai2_res = info.get("ai2_result")

    if bbox is not None:
        bx1, by1, bx2, by2 = bbox
        cur_ai2_status = ai2_res.get("status", "Unknown") if ai2_res else "Unknown"

        if cur_ai2_status == "Normal":
            box_color = COLORS["GREEN"]
        elif cur_ai2_status in ["Fatigue", "Turned_Head"]:
            box_color = COLORS["YELLOW"]
        elif cur_ai2_status == "Exhausted":
            box_color = COLORS["RED"]
        else:
            box_color = COLORS["CYAN"]

        cv2.rectangle(vis, (bx1, by1), (bx2, by2), box_color, 2)

        # Dòng 1: Danh tính sinh viên
        name_str = info.get("identified_name", "Scanning Identity...")
        sim_val = info.get("identity_sim", 0.0)
        sim_str = f" (Sim: {sim_val:.2f})" if sim_val > 0.1 else ""
        label_id = f"{name_str}{sim_str}"

        # Dòng 2: Trạng thái AI 2 tức thời
        label_ai2 = f"AI2: {cur_ai2_status.upper()}"
        if ai2_res and ai2_res.get("is_valid"):
            conf = ai2_res.get("confidence", 0.0)
            label_ai2 += f" ({conf*100:.0f}%)"

        # Background text phía trên bbox
        (tw1, th1), _ = cv2.getTextSize(label_id, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        (tw2, th2), _ = cv2.getTextSize(label_ai2, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        bg_w = max(tw1, tw2) + 12
        bg_h = th1 + th2 + 18
        ty1 = max(banner_h + 5, by1 - bg_h)

        cv2.rectangle(vis, (bx1, ty1), (bx1 + bg_w, ty1 + bg_h), (20, 20, 20), -1)
        cv2.rectangle(vis, (bx1, ty1), (bx1 + bg_w, ty1 + bg_h), box_color, 1)

        cv2.putText(vis, label_id, (bx1 + 6, ty1 + th1 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["WHITE"], 2)
        cv2.putText(vis, label_ai2, (bx1 + 6, ty1 + th1 + th2 + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

    # 3. BẢNG THÔNG SỐ REALTIME GÓC DƯỚI BÊN TRÁI
    stats_w, stats_h = 320, 140
    sx1, sy1 = 15, h - stats_h - 15
    panel_overlay = vis.copy()
    cv2.rectangle(panel_overlay, (sx1, sy1), (sx1 + stats_w, sy1 + stats_h), COLORS["DARK_BG"], -1)
    vis = cv2.addWeighted(panel_overlay, 0.7, vis, 0.3, 0)
    cv2.rectangle(vis, (sx1, sy1), (sx1 + stats_w, sy1 + stats_h), (70, 70, 70), 1)

    m = info.get("latest_metrics", {})
    ear_v = m.get("ear", 0.0)
    mar_v = m.get("mar", 0.0)
    pitch_v = m.get("pitch", 0.0)
    yaw_v = m.get("yaw", 0.0)
    sharp_v = m.get("sharpness", 0.0)

    cv2.putText(vis, f"METRICS REALTIME | FPS: {fps:.1f}", (sx1 + 12, sy1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["CYAN"], 2)
    cv2.putText(vis, f"EAR : {ear_v:.3f} (N>=0.25, F>=0.18, E<0.18)", (sx1 + 12, sy1 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["WHITE"], 1)
    cv2.putText(vis, f"MAR : {mar_v:.3f} | Sharpness: {sharp_v:.1f}", (sx1 + 12, sy1 + 74), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["WHITE"], 1)
    cv2.putText(vis, f"Pose: Pitch={pitch_v:.1f} | Yaw={yaw_v:.1f}", (sx1 + 12, sy1 + 98), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["WHITE"], 1)
    cv2.putText(vis, "Q=Thoat | 1/2/3=Mock IoT | a=Abort | t=Timeout", (sx1 + 12, sy1 + 124), cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLORS["GRAY"], 1)

    # 4. OVERLAY CARD KẾT QUẢ KHI COMPLETED
    if state == SessionState.COMPLETED and info.get("completed_record") is not None:
        rec = info["completed_record"]
        fusion = rec.get("fusion_result", {})
        alert_lvl = fusion.get("alert_level", "GREEN")
        card_color = COLORS.get(alert_lvl, COLORS["GREEN"])

        cw, ch = 560, 240
        cx1, cy1 = (w - cw) // 2, (h - ch) // 2
        card_bg = vis.copy()
        cv2.rectangle(card_bg, (cx1, cy1), (cx1 + cw, cy1 + ch), (15, 15, 15), -1)
        vis = cv2.addWeighted(card_bg, 0.88, vis, 0.12, 0)
        cv2.rectangle(vis, (cx1, cy1), (cx1 + cw, cy1 + ch), card_color, 3)

        # Tiêu đề Card
        title_str = f"KET QUA DIEM DANH & SUC KHOE [{alert_lvl}]"
        cv2.putText(vis, title_str, (cx1 + 20, cy1 + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, card_color, 2)

        # Nội dung
        s_name = rec.get("student_name", "Unknown")
        s_id = rec.get("student_id", "Unknown")
        face_st = rec.get("ai2_face_status", "Unknown")
        iot = rec.get("iot_metrics", {})
        hr_val = iot.get("hr", 0)
        spo2_val = iot.get("spo2", 0)

        cv2.putText(vis, f"Sinh vien: {s_name} (Ma: {s_id})", (cx1 + 20, cy1 + 72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLORS["WHITE"], 2)
        cv2.putText(vis, f"The trang mat (AI 2): {face_st}", (cx1 + 20, cy1 + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, card_color, 2)
        cv2.putText(vis, f"Nhip tim (BPM): {hr_val} | SpO2: {spo2_val}% ({iot.get('bio_level')})", (cx1 + 20, cy1 + 138), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS["WHITE"], 2)

        # Kết luận Late Fusion
        f_status = fusion.get("final_status", "")
        recom = fusion.get("recommendation", "")
        cv2.putText(vis, f"Ket luan: {f_status}", (cx1 + 20, cy1 + 175), cv2.FONT_HERSHEY_SIMPLEX, 0.6, card_color, 2)
        cv2.putText(vis, f"Loi khuyen: {recom}", (cx1 + 20, cy1 + 210), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["GRAY"], 1)

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
