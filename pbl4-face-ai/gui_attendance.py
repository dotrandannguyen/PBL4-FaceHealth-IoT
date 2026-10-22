"""Camera-only attendance UI: one session per physical Space press.

Tk only displays snapshots. AttendanceWorker owns the camera, inference,
persistence and the existing five-second result state.
"""
from __future__ import annotations

import math
import tkinter as tk

from PIL import Image, ImageTk

BACKGROUND = "#080d13"
PANEL = "#111c29"
TEXT = "#f3f7fc"
MUTED = "#b5c5d8"
GREEN = "#55e49b"
AMBER = "#ffd176"
RED = "#ff8181"


def session_state(snapshot):
    state = (snapshot.get("info") or {}).get("state", "IDLE")
    return getattr(state, "value", state)


def result_presentation(record):
    """Keep confirmed actions distinct from pending or unsuccessful attempts."""
    action = record.get("attendance_action")
    if action == "CHECK-IN":
        return "CHECK-IN THÀNH CÔNG", "Đã ghi nhận vào ca.", GREEN
    if action == "CHECK-OUT":
        return "CHECK-OUT THÀNH CÔNG", "Đã ghi nhận ra ca.", GREEN
    if action == "DA_CHECK_OUT":
        return "HÔM NAY ĐÃ CHECK-OUT", "Bạn đã hoàn thành chấm công hôm nay.", AMBER
    if action == "PENDING":
        return "ĐANG CHỜ XÁC NHẬN", "Chưa có xác nhận chấm công từ máy chủ.", AMBER
    if (record.get("web_result") or {}).get("status") in {"no_identity", "no_id"}:
        return "CHƯA GHI NHẬN", "Chưa nhận diện được nhân viên. Vui lòng thử lại.", RED
    return "CHƯA GHI NHẬN", "Chưa có xác nhận chấm công. Vui lòng thử lại.", RED


def _identity_text(record):
    identity = str(record.get("student_id") or "")
    name = str(record.get("student_name") or "")
    if identity in {"", "Unknown"}:
        return ""
    return f"{identity} · {name}" if name and name != "Unknown" else identity


class AttendanceApp(tk.Tk):
    def __init__(self, worker=None):
        super().__init__()
        self.title("PBL4 · Chấm công")
        self.geometry("1180x760")
        self.minsize(800, 560)
        self.configure(bg=BACKGROUND)
        self._closing = False
        self._timer = None
        self._close_timer = None
        self._space_release_timer = None
        self._space_down = False
        self._defer_space_release = self.tk.call("tk", "windowingsystem") == "x11"
        self._request_pending = False
        self._photo = None
        self._render_token = None
        self._snapshot = {}
        self.canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._invalidate_frame())
        self.bind("<KeyPress-space>", self._on_space_press)
        self.bind("<KeyRelease-space>", self._on_space_release)
        self.bind("<Escape>", lambda _event: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        from src.desktop_lifecycle import install_close_listener
        install_close_listener(self, self._on_close)
        if worker is None:
            from src.live_attendance import AttendanceWorker
            worker = AttendanceWorker()
        self.worker = worker
        self._timer = self.after(30, self._poll)

    def _invalidate_frame(self):
        self._render_token = None

    def _can_start(self):
        return (not self._closing and not self._request_pending
                and not getattr(self.worker, "loading", False)
                and not getattr(self.worker, "error", "")
                and self._snapshot.get("frame") is not None
                and session_state(self._snapshot) == "IDLE")

    def _on_space_press(self, _event=None):
        # X11 repeat can synthesize release/press pairs in one event batch.
        # Windows repeat sends KeyPress without a physical KeyRelease.
        if self._space_release_timer is not None:
            self.after_cancel(self._space_release_timer)
            self._space_release_timer = None
        if self._space_down:
            return "break"
        self._space_down = True
        if self._can_start() and self.worker.start_session():
            self._request_pending = True
            self._render_token = None
        return "break"

    def _on_space_release(self, _event=None):
        if self._space_release_timer is not None:
            self.after_cancel(self._space_release_timer)
        if self._defer_space_release:
            self._space_release_timer = self.after_idle(self._release_space)
        else:
            self._release_space()
        return "break"

    def _release_space(self):
        self._space_release_timer = None
        self._space_down = False

    def _poll(self):
        if self._closing:
            return
        try:
            snapshot = self.worker.snapshot() or {}
            self._snapshot = snapshot
            if session_state(snapshot) != "IDLE" or getattr(self.worker, "error", ""):
                self._request_pending = False
            self._render(snapshot)
        finally:
            if not self._closing:
                self._timer = self.after(30, self._poll)

    @staticmethod
    def _countdown(info):
        try:
            elapsed = float(info.get("elapsed_in_state", 0))
        except (TypeError, ValueError):
            elapsed = 0
        if not math.isfinite(elapsed):
            elapsed = 0
        return max(0, math.ceil(5 - elapsed))

    def _presentation(self, snapshot):
        info = snapshot.get("info") or {}
        state = session_state(snapshot)
        if self._closing:
            return "Đang đóng camera…", "", "", MUTED, "center"
        error = str(getattr(self.worker, "error", "") or snapshot.get("error") or "")
        if error:
            return "Không mở được chấm công", error, "Đóng cửa sổ và kiểm tra kết nối camera.", RED, "center"
        if getattr(self.worker, "loading", False):
            return "Đang chuẩn bị camera…", "", "", MUTED, "center"
        if state == "COMPLETED":
            record = info.get("completed_record") or {}
            title, detail, color = result_presentation(record)
            lines = "\n".join(value for value in (_identity_text(record), detail) if value)
            return title, lines, f"Trở về camera sau {self._countdown(info)} giây", color, "result"
        if state == "ABORTED":
            return ("CHƯA GHI NHẬN", "Chưa đủ dữ liệu khuôn mặt hợp lệ. Vui lòng thử lại.",
                    f"Trở về camera sau {self._countdown(info)} giây", RED, "result")
        if state in {"CAPTURING", "PROCESSING", "FINALIZING"} or self._request_pending:
            titles = {"CAPTURING": "Đang quét khuôn mặt…", "PROCESSING": "Đang xử lý…", "FINALIZING": "Đang xác nhận…"}
            return titles.get(state, "Đang bắt đầu…"), "Giữ yên khuôn mặt và nhìn vào camera.", "", TEXT, "bottom"
        if snapshot.get("frame") is None:
            return "Đang kết nối camera…", "Kiểm tra webcam hoặc AI Service.", "", MUTED, "center"
        return "Nhấn Space để chấm công", "", "", TEXT, "bottom"

    def _render(self, snapshot):
        state = session_state(snapshot)
        frame = snapshot.get("result_frame") if state == "COMPLETED" else None
        if frame is None:
            frame = snapshot.get("frame")
        width, height = max(2, self.canvas.winfo_width()), max(2, self.canvas.winfo_height())
        presentation = self._presentation(snapshot)
        token = (snapshot.get("seq", id(frame)), id(frame) if state == "COMPLETED" else None,
                 frame is None, width, height, presentation)
        if token == self._render_token:
            return
        self._render_token = token
        self.canvas.delete("all")
        if frame is not None and getattr(frame, "size", 0):
            image = Image.fromarray(frame[:, :, ::-1])
            scale = min(width / image.width, height / image.height)
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                 Image.Resampling.BILINEAR)
            self._photo = ImageTk.PhotoImage(image, master=self)
            self.canvas.create_image(width / 2, height / 2, image=self._photo, anchor="center", tags="camera")
        else:
            self._photo = None
        self._draw_message(width, height, *presentation)

    def _draw_message(self, width, height, title, detail, note, color, position):
        text_width = max(180, min(width - 56, 860))
        top = height - 112 if position == "bottom" else max(35, height * .16) if position == "result" else height * .36
        title_size = 23 if position == "result" else 19
        title_item = self.canvas.create_text(width / 2, top, text=title, fill=color,
            font=("Segoe UI", title_size, "bold"), width=text_width, anchor="n", justify="center", tags="message")
        bounds = self.canvas.bbox(title_item)
        bottom = bounds[3] if bounds else top + 32
        if detail:
            item = self.canvas.create_text(width / 2, bottom + 12, text=detail, fill=TEXT,
                font=("Segoe UI", 13), width=text_width, anchor="n", justify="center", tags="message")
            bounds = self.canvas.bbox(item)
            if bounds:
                bottom = bounds[3]
        if note:
            item = self.canvas.create_text(width / 2, bottom + 14, text=note, fill=MUTED,
                font=("Segoe UI", 11), width=text_width, anchor="n", justify="center", tags="message")
            bounds = self.canvas.bbox(item)
            if bounds:
                bottom = bounds[3]
        box_width = min(width - 24, text_width + 34)
        background = self.canvas.create_rectangle((width - box_width) / 2, top - 18,
            (width + box_width) / 2, bottom + 18, fill=PANEL, outline="", tags="message_background")
        self.canvas.tag_lower(background, title_item)

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        for name in ("_timer", "_space_release_timer"):
            timer = getattr(self, name)
            if timer is not None:
                self.after_cancel(timer)
                setattr(self, name, None)
        self._render_token = None
        self._render(self._snapshot)
        self.worker.close()
        self._close_timer = self.after(30, self._wait_for_close)

    def _wait_for_close(self):
        if self._close_timer is not None:
            self.after_cancel(self._close_timer)
            self._close_timer = None
        thread = getattr(self.worker, "thread", None)
        if thread is not None and thread.is_alive():
            self._close_timer = self.after(50, self._wait_for_close)
        else:
            self.destroy()


def main():
    AttendanceApp().mainloop()


if __name__ == "__main__":
    main()
