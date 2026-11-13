"""Desktop Tkinter shell for the isolated, local-only AI1 standalone system."""

import os
import queue
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

import face_matching
from ai1_standalone_core.ai1_adapter import (
    validate_enrollment_frame,
    validate_enrollment_pose_frame,
)
from ai1_standalone_core.config import (
    EMBEDDING_DIMENSIONS,
    FRAME_CONSISTENCY_THRESHOLD,
    GUIDED_POSE_STABLE_FRAMES,
    GUIDED_POSE_STABILITY_WINDOW_SECONDS,
    GUIDED_POSE_TIMEOUT_SECONDS,
    POSES,
    RECOGNITION_THRESHOLD,
    STALE_FRAME_SECONDS,
)
from ai1_standalone_core.pose_tracking import GuidedPoseTracker, POSE_DIRECTIONS
from ai1_standalone_core.utils import safe_identity_path, validate_employee_id
from .controller import AI1GuiController, DuplicateFaceError
from .enrollment_state import EnrollmentCaptureState


BG = "#0d1117"
PANEL = "#161b22"
CARD = "#1c2128"
TEXT = "#e6edf3"
DIM = "#8b949e"
BLUE = "#1f6feb"
GREEN = "#238636"
RED = "#da3633"
YELLOW = "#d29922"
POSE_LABELS = {
    "frontal": "Nhìn thẳng",
    "left": "Xoay trái",
    "right": "Xoay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}
MESSAGE_LABELS = {
    "NO FACE": "Không thấy khuôn mặt",
    "MULTIPLE FACES": "Chỉ để một người trong khung",
    "LOW DETECTION SCORE": "AI chưa phát hiện mặt đủ chắc — nhìn rõ camera, tăng ánh sáng",
    "FACE TOO SMALL": "Mặt quá xa — tiến gần camera hơn",
    "FACE TOO LARGE": "Mặt quá gần — lùi nhẹ khỏi camera",
    "FACE POSITION": "Đưa khuôn mặt về gần vùng trung tâm, giữ khoảng cách phù hợp",
    "FACE CROPPED": "Khuôn mặt bị cắt ở mép khung hình",
    "FACE TOO CLOSE TO EDGE": "Đưa khuôn mặt xa mép khung hình hơn",
    "BAD LIGHTING": "Ánh sáng chưa phù hợp",
    "TOO BLURRY": "Ảnh bị mờ — kiểm tra nét và chuyển động của camera",
    "WRONG POSE": "Điều chỉnh theo pose yêu cầu",
    "SAME PERSON": "Khuôn mặt khác mẫu nhìn thẳng",
    "STALE_FRAME": "Đang chờ khung hình mới",
    "CAMERA DISCONNECTED": "Camera chưa có frame mới",
    "INVALID EMBEDDING": "Embedding không hợp lệ — thử lại",
}

_OVERLAY_FONT_CACHE = {}


def _unicode_overlay_font(size):
    size = max(10, int(size))
    if size in _OVERLAY_FONT_CACHE:
        return _OVERLAY_FONT_CACHE[size]
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windir / "Fonts" / "segoeui.ttf",
        windir / "Fonts" / "arial.ttf",
        windir / "Fonts" / "tahoma.ttf",
    )
    for path in candidates:
        try:
            font = ImageFont.truetype(str(path), size=size)
            _OVERLAY_FONT_CACHE[size] = font
            return font
        except (OSError, ValueError):
            continue
    font = ImageFont.load_default()
    _OVERLAY_FONT_CACHE[size] = font
    return font


def _draw_unicode_runs(frame_bgr, runs):
    """Render positioned Unicode labels in one RGB/Pillow conversion per frame."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb).convert("RGBA")
    draw = ImageDraw.Draw(image)
    for text, x, y, color, size in runs:
        font = _unicode_overlay_font(size)
        red, green, blue = [int(value) for value in color]
        draw.text((int(x), int(y)), str(text), font=font,
                  fill=(red, green, blue, 255), stroke_width=1,
                  stroke_fill=(0, 0, 0, 220))
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _atomic_write_jpeg(path, frame):
    """Write an uncommitted enrollment image into its private stage atomically."""
    path = Path(path)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok or encoded is None or encoded.size == 0:
        raise OSError("Không mã hóa được ảnh pose.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".pose-", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded.tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class AI1Gui:
    """Responsive dark GUI; all model/camera work runs outside Tk's main thread."""

    def __init__(self, root=None, controller=None):
        self.root = root or tk.Tk()
        self.controller = controller or AI1GuiController()
        self.events = queue.Queue()
        self.close_event = threading.Event()
        self.active_operation = None
        self.active_token = None
        self.active_stop_event = None
        self.worker_thread = None
        self.closing = False
        self.enrollment = None
        self.current_packet = None
        self.current_photo = None
        self.thumbnail_photos = [None] * len(POSES)
        self.captured_pose_order = []
        self.latest_analysis = {}
        self.best_result_frame = None
        self.best_frame_until = 0.0
        self.last_result_status = None
        self.result_card_until = 0.0
        self.space_is_down = False
        self.space_capture_pending = False
        self.capture_feedback = None

        self.root.title("AI1 Standalone | Nhận diện khuôn mặt")
        self.root.geometry("1480x1024")
        self.root.minsize(820, 640)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind_all("<KeyPress-space>", self._on_space_press)
        self.root.bind_all("<KeyRelease-space>", self._on_space_release)
        self.root.bind_all("<Escape>", self._on_escape)
        self._configure_style()
        self._build_ui()
        self._set_controls()
        self._start_job("startup", lambda: self.controller.startup(self.close_event))
        self.root.after(60, self._poll_events)
        self.root.after(33, self._update_preview)

    def run(self):
        self.root.mainloop()

    def _on_space_press(self, _event=None):
        """Queue one manual pose capture; ignore key repeat and other modes."""
        if self.active_operation != "enrollment" or self.enrollment is None:
            return None
        if self.enrollment.get("ready_to_save"):
            return "break"
        if self.space_is_down or self.space_capture_pending:
            return "break"
        self.space_is_down = True
        if self.enrollment.get("mode", "MANUAL") == "AUTO":
            self.state_var.set("TRẠNG THÁI: AUTO ĐANG QUÉT · SPACE CHỈ DÙNG Ở MANUAL")
            return "break"
        self.space_capture_pending = True
        self.capture_feedback = None
        self.enrollment["requests"].put({"action": "capture"})
        self.state_var.set("TRẠNG THÁI: ĐANG KIỂM TRA FRAME MỚI…")
        return "break"

    def _on_space_release(self, _event=None):
        self.space_is_down = False
        return "break" if self.active_operation == "enrollment" else None

    def _on_escape(self, _event=None):
        if self.active_operation == "enrollment" and self.enrollment is not None:
            self._cancel_enrollment()
            return "break"
        return None

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Treeview", background=CARD, foreground=TEXT,
                        fieldbackground=CARD, rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL, foreground=DIM,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL,
                        background=GREEN, thickness=11)
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT)

    def _build_ui(self):
        header = tk.Frame(self.root, bg=PANEL, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Label(header, text="AI1 STANDALONE", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=(20, 12), pady=16)
        tk.Label(header, text="ArcFace buffalo_l  ·  SCRFD  ·  dữ liệu riêng trên máy này",
                 bg=PANEL, fg=DIM, font=("Segoe UI", 10)).pack(side="left", pady=18)
        self.header_status = tk.StringVar(value="Đang tải AI1...")
        self.header_label = tk.Label(header, textvariable=self.header_status, bg=PANEL, fg=YELLOW,
                                      font=("Segoe UI", 9, "bold"))
        self.header_label.pack(side="right", padx=20)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(body, bg=BG, highlightthickness=0, borderwidth=0)
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        self.content_scrollbar = ttk.Scrollbar(body, orient="vertical",
                                               command=self.content_canvas.yview)
        self.content_scrollbar.grid(row=0, column=1, sticky="ns")
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.scroll_content = tk.Frame(self.content_canvas, bg=BG)
        self.scroll_content.columnconfigure(0, weight=1)
        self.content_window = self.content_canvas.create_window(
            (0, 0), window=self.scroll_content, anchor="nw"
        )
        self.scroll_content.bind("<Configure>", self._refresh_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.root.bind_all("<MouseWheel>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_content_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_content_mousewheel, add="+")

        camera_section = tk.Frame(self.scroll_content, bg=BG)
        camera_section.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        camera_section.columnconfigure(0, weight=1)
        tk.Label(camera_section, text="CAMERA PREVIEW", bg=BG, fg=DIM,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(0, 5))
        self.camera_stage = tk.Frame(camera_section, bg=BG)
        self.camera_stage.grid(row=1, column=0, sticky="ew")
        self.camera_stage.columnconfigure(0, weight=1)
        self.preview_host = tk.Frame(self.camera_stage, bg="#05070a",
                                     highlightthickness=1, highlightbackground="#30363d")
        self.preview_host.grid(row=0, column=0, pady=3)
        self.preview_host.grid_propagate(False)
        self.preview = tk.Label(self.preview_host, bg="#05070a", fg=DIM,
                                text="Đang khởi tạo AI1 và camera…", font=("Segoe UI", 14),
                                bd=0, compound="center")
        self.preview.pack(fill="both", expand=True)
        self.preview_hint = tk.StringVar(value="Camera preview sẽ xuất hiện tại đây.")
        self.preview_hint_label = tk.Label(
            camera_section, textvariable=self.preview_hint, bg=BG, fg=DIM,
            anchor="center", justify="center", font=("Segoe UI", 9), wraplength=1000,
        )
        self.preview_hint_label.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.camera_stage.bind("<Configure>", self._resize_preview)
        self.preview_host.bind("<Configure>", self._resize_result_overlay)

        self.controls_frame = tk.Frame(self.scroll_content, bg=BG)
        self.controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Group 1 — camera source controls.
        self.camera_card = self._card(self.controls_frame, "NGUỒN CAMERA")
        camera_form = tk.Frame(self.camera_card, bg=CARD)
        camera_form.pack(fill="x", padx=12, pady=(1, 9))
        self.camera_type_var = tk.StringVar(value="WEBCAM")
        self.camera_combo = ttk.Combobox(
            camera_form, textvariable=self.camera_type_var,
            values=("WEBCAM", "ESP32-CAM"), state="readonly", width=13,
        )
        self.camera_combo.grid(row=0, column=0, sticky="ew")
        self.stream_url_var = tk.StringVar(
            value=os.getenv("AI1_ESP32_STREAM_URL", "http://esp32cam.local:81/stream")
        )
        self.stream_entry = ttk.Entry(camera_form, textvariable=self.stream_url_var)
        self.stream_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        camera_form.columnconfigure(0, weight=0)
        camera_form.columnconfigure(1, weight=1)
        self.camera_button = self._button(
            self.camera_card, "Chọn nguồn camera", self._change_camera, BLUE
        )
        self.camera_button.pack(fill="x", padx=12, pady=(0, 11))

        # Group 2 — employee actions and standalone identity form.
        self.employee_card = self._card(self.controls_frame, "NHÂN VIÊN LOCAL")
        form = tk.Frame(self.employee_card, bg=CARD)
        form.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(form, text="Employee ID", bg=CARD, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(form, text="Employee Name", bg=CARD, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.id_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.id_entry = ttk.Entry(form, textvariable=self.id_var, width=14)
        self.name_entry = ttk.Entry(form, textvariable=self.name_var, width=22)
        self.id_entry.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(3, 0))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=2)
        self.register_button = self._button(
            self.employee_card, "BẮT ĐẦU QUÉT AUTO", self._begin_registration, GREEN
        )
        self.register_button.pack(fill="x", padx=12, pady=(0, 6))
        self.recognize_button = self._button(
            self.employee_card, "QUÉT THỬ / NHẬN DIỆN", self._recognize, BLUE
        )
        self.recognize_button.pack(fill="x", padx=12, pady=(0, 6))
        quick = tk.Frame(self.employee_card, bg=CARD)
        quick.pack(fill="x", padx=12, pady=(0, 10))
        self.refresh_button = self._button(quick, "Làm mới danh sách", self._refresh, "#30363d")
        self.refresh_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.delete_button = self._button(quick, "Xóa nhân viên", self._delete_selected, "#30363d")
        self.delete_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.gallery_status_var = tk.StringVar(value="Gallery: đang tải dữ liệu local…")
        tk.Label(self.employee_card, textvariable=self.gallery_status_var, bg=CARD, fg=DIM,
                 font=("Segoe UI", 9, "bold"), anchor="w", justify="left",
                 wraplength=430).pack(fill="x", padx=12, pady=(0, 10))

        # Group 3 — Smart Enrollment v2 controls and five-pose progress.
        self.capture_card = self._card(self.controls_frame, "SMART ENROLLMENT · QUÉT 5 GÓC")
        mode_row = tk.Frame(self.capture_card, bg=CARD)
        mode_row.pack(fill="x", padx=12, pady=(0, 5))
        tk.Label(mode_row, text="Chế độ", bg=CARD, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        self.enrollment_mode_var = tk.StringVar(value="AUTO")
        self.enrollment_mode_combo = ttk.Combobox(
            mode_row, textvariable=self.enrollment_mode_var,
            values=("AUTO", "MANUAL"), state="readonly", width=10,
        )
        self.enrollment_mode_combo.pack(side="left", padx=(8, 0))
        self.enrollment_mode_combo.bind("<<ComboboxSelected>>", self._sync_enrollment_start_button)
        tk.Label(mode_row, text="AUTO · hướng dẫn   |   MANUAL · SPACE",
                 bg=CARD, fg=DIM, font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
        self.pose_var = tk.StringVar(value="Pose yêu cầu: —")
        self.detected_pose_var = tk.StringVar(value="Pose phát hiện: —")
        self.quality_var = tk.StringVar(value="Quality: chờ enrollment")
        self.auto_status_var = tk.StringVar(value="AUTO: chờ bắt đầu")
        self.capture_hint_var = tk.StringVar(value="Chọn Đăng ký khuôn mặt để bắt đầu.")
        self.enrollment_info_labels = []
        for variable in (self.pose_var, self.detected_pose_var, self.quality_var,
                         self.auto_status_var, self.capture_hint_var):
            label = tk.Label(self.capture_card, textvariable=variable, bg=CARD, fg=TEXT,
                             font=("Segoe UI", 9), anchor="w", justify="left",
                             wraplength=500)
            label.pack(fill="x", padx=12, pady=1)
            self.enrollment_info_labels.append(label)
        progress_row = tk.Frame(self.capture_card, bg=CARD)
        progress_row.pack(fill="x", padx=12, pady=(6, 8))
        self.pose_ring = tk.Canvas(progress_row, width=78, height=78, bg=CARD,
                                   highlightthickness=0, borderwidth=0)
        self.pose_ring.pack(side="left", padx=(0, 10))
        progress_column = tk.Frame(progress_row, bg=CARD)
        progress_column.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(progress_column, maximum=5)
        self.progress.pack(fill="x", pady=(16, 4))
        self.enrollment_progress_var = tk.StringVar(value="Tiến độ: 0/5")
        tk.Label(progress_column, textvariable=self.enrollment_progress_var, bg=CARD, fg=DIM,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        thumbs = tk.Frame(self.capture_card, bg=CARD)
        thumbs.pack(fill="x", padx=8, pady=(0, 8))
        self.thumb_labels = []
        self.thumb_status_labels = []
        self.thumb_cells = []
        for pose in POSES:
            cell = tk.Frame(thumbs, bg=PANEL, padx=2, pady=3)
            cell.pack(side="left", fill="both", expand=True, padx=2)
            image_label = tk.Label(cell, text="—", width=7, height=3, bg=PANEL, fg=DIM,
                                   font=("Segoe UI", 9, "bold"))
            image_label.pack(fill="both", expand=True)
            status_label = tk.Label(cell, text="•", bg=PANEL, fg=DIM,
                                    font=("Segoe UI", 9, "bold"))
            status_label.pack(pady=(2, 0))
            tk.Label(cell, text=POSE_LABELS[pose], bg=PANEL, fg=DIM,
                     font=("Segoe UI", 7)).pack(pady=(0, 2))
            self.thumb_labels.append(image_label)
            self.thumb_status_labels.append(status_label)
            self.thumb_cells.append(cell)
        capture_actions = tk.Frame(self.capture_card, bg=CARD)
        capture_actions.pack(fill="x", padx=12, pady=(0, 10))
        self.retake_button = self._button(
            capture_actions, "Quét lại 5 góc", self._retake_pose, "#30363d"
        )
        self.retake_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.cancel_button = self._button(
            capture_actions, "Hủy", self._cancel_enrollment, "#30363d"
        )
        self.cancel_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.save_button = self._button(
            self.capture_card, "Lưu lại 5 mẫu local", self._retry_save, BLUE
        )
        self.save_button.pack(fill="x", padx=12, pady=(0, 10))

        # Group 4 — local employee gallery.
        self.list_card = self._card(self.controls_frame, "DANH SÁCH NHÂN VIÊN STANDALONE")
        table_wrap = tk.Frame(self.list_card, bg=CARD)
        table_wrap.pack(fill="both", expand=True, padx=9, pady=(0, 9))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.employee_table = ttk.Treeview(
            table_wrap, columns=("id", "name", "samples"), show="headings",
            height=7, selectmode="browse",
        )
        for column, title in (("id", "Employee ID"), ("name", "Họ tên"), ("samples", "Embedding")):
            self.employee_table.heading(column, text=title)
        self.employee_table.column("id", width=105, stretch=False)
        self.employee_table.column("name", width=220, stretch=True)
        self.employee_table.column("samples", width=82, stretch=False, anchor="center")
        table_scrollbar = ttk.Scrollbar(table_wrap, orient="vertical",
                                        command=self.employee_table.yview)
        self.employee_table.configure(yscrollcommand=table_scrollbar.set)
        self.employee_table.grid(row=0, column=0, sticky="nsew")
        table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.employee_table.bind("<<TreeviewSelect>>", self._select_employee)

        # Group 5 — persistent recognition metrics and session status.
        self.result_summary_card = self._card(self.controls_frame, "NHẬN DIỆN VÀ KẾT QUẢ")
        self.state_var = tk.StringVar(value="TRẠNG THÁI: ĐANG TẢI AI1")
        self.prediction_var = tk.StringVar(value="KẾT QUẢ: —")
        status = tk.Frame(self.result_summary_card, bg=CARD)
        status.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(status, textvariable=self.state_var, bg=CARD, fg=YELLOW,
                 font=("Segoe UI", 10, "bold"), anchor="w", justify="left",
                 wraplength=500).pack(fill="x", pady=(0, 4))
        tk.Label(status, textvariable=self.prediction_var, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 10, "bold"), anchor="w", justify="left",
                 wraplength=500).pack(fill="x")
        metrics = tk.Frame(self.result_summary_card, bg=CARD)
        metrics.pack(fill="x", padx=12, pady=(0, 8))
        self.progress_var = tk.StringVar(value="Tiến độ: 0/5")
        self.sharpness_var = tk.StringVar(value="Sharpness: —")
        self.latency_var = tk.StringVar(value="Latency: —")
        self.score_var = tk.StringVar(value="Similarity: —")
        self.threshold_var = tk.StringVar(value=f"Threshold: {RECOGNITION_THRESHOLD:.3f}")
        self.consistency_var = tk.StringVar(value=f"Temporal: {FRAME_CONSISTENCY_THRESHOLD:.2f}")
        self.result_metric_labels = []
        for index, variable in enumerate((self.progress_var, self.sharpness_var, self.latency_var,
                                          self.score_var, self.threshold_var, self.consistency_var)):
            label = tk.Label(metrics, textvariable=variable, bg=CARD, fg=DIM,
                             font=("Segoe UI", 9), anchor="w", justify="left", wraplength=240)
            label.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 8), pady=3)
            self.result_metric_labels.append(label)
        for column in range(3):
            metrics.columnconfigure(column, weight=1)
        actions = tk.Frame(self.result_summary_card, bg=CARD)
        actions.pack(fill="x", padx=12, pady=(0, 10))
        self.exit_button = self._button(actions, "Thoát", self._on_close, "#30363d")
        self.exit_button.pack(side="right")

        self.control_cards = [self.camera_card, self.employee_card, self.capture_card,
                              self.list_card, self.result_summary_card]
        self._control_columns = None
        self._relayout_control_cards(self.content_canvas.winfo_width())

        self.result_title_var = tk.StringVar(value="")
        self.result_detail_var = tk.StringVar(value="")
        self.result_card = tk.Frame(
            self.preview, bg="#17212b", highlightthickness=2, highlightbackground=YELLOW
        )
        self.result_title_label = tk.Label(
            self.result_card, textvariable=self.result_title_var, bg="#17212b", fg=YELLOW,
            font=("Segoe UI", 22, "bold"), anchor="w",
        )
        self.result_title_label.pack(fill="x", padx=16, pady=(10, 3))
        self.result_detail_label = tk.Label(
            self.result_card, textvariable=self.result_detail_var, bg="#17212b", fg=TEXT,
            font=("Segoe UI", 11, "bold"), anchor="w", justify="left", wraplength=560,
        )
        self.result_detail_label.pack(fill="x", padx=16, pady=(0, 12))
        self.result_card.place_forget()

        self._update_pose_ring(0, 0)
        self._sync_enrollment_start_button()

    def _refresh_scroll_region(self, _event=None):
        if hasattr(self, "content_canvas"):
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event):
        self.content_canvas.itemconfigure(self.content_window, width=max(1, event.width))
        self._relayout_control_cards(event.width)
        self.root.after_idle(self._resize_preview)

    def _relayout_control_cards(self, width):
        if not hasattr(self, "control_cards"):
            return
        width = max(1, int(width or 1))
        columns = self._layout_columns_for_width(width)
        if columns == self._control_columns:
            return
        for column in range(3):
            self.controls_frame.grid_columnconfigure(
                column, weight=1 if column < columns else 0, uniform="control-card"
            )
        if columns == 3:
            placements = ((0, 0, 1), (0, 1, 1), (0, 2, 1), (1, 0, 2), (1, 2, 1))
        elif columns == 2:
            placements = ((0, 0, 1), (0, 1, 1), (1, 0, 2), (2, 0, 1), (2, 1, 1))
        else:
            placements = tuple((row, 0, 1) for row in range(len(self.control_cards)))
        for card, (row, column, span) in zip(self.control_cards, placements):
            card.grid_forget()
            card.grid(row=row, column=column, columnspan=span, sticky="nsew",
                      padx=5, pady=5)
        self._control_columns = columns

    @staticmethod
    def _layout_columns_for_width(width):
        width = max(1, int(width or 1))
        return 3 if width >= 1240 else 2 if width >= 820 else 1

    def _resize_preview(self, _event=None):
        if not hasattr(self, "preview_host"):
            return
        canvas_width = max(320, self.content_canvas.winfo_width())
        available_width = max(320, min(1280, canvas_width - 42))
        viewport_height = max(360, self.content_canvas.winfo_height())
        max_height = max(300, int(viewport_height * 0.80))
        packet = getattr(self, "current_packet", None)
        frame = getattr(packet, "frame", None) if packet is not None else None
        if isinstance(frame, np.ndarray) and frame.ndim >= 2:
            source_height, source_width = frame.shape[:2]
            aspect = source_width / max(1, source_height)
        else:
            aspect = 4.0 / 3.0
        width = max(1, min(available_width, int(max_height * aspect)))
        height = max(1, int(round(width / aspect)))
        self.preview_host.configure(width=width, height=height)
        self._preview_size = (width, height)
        self._preview_aspect = aspect
        if hasattr(self, "preview_hint_label"):
            self.preview_hint_label.configure(wraplength=max(320, width))
        if hasattr(self, "result_detail_label"):
            self.result_detail_label.configure(wraplength=max(280, int(width * 0.72)))
        for label in getattr(self, "enrollment_info_labels", ()):
            label.configure(wraplength=max(300, available_width - 50))

    def _resize_result_overlay(self, event):
        if hasattr(self, "result_detail_label"):
            self.result_detail_label.configure(wraplength=max(280, int(event.width * 0.72)))

    def _on_content_mousewheel(self, event):
        widget = getattr(event, "widget", None)
        while widget is not None and widget is not getattr(self, "scroll_content", None):
            widget = getattr(widget, "master", None)
        if widget is None:
            return None
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            raw_delta = int(getattr(event, "delta", 0))
            delta = -int(raw_delta / 120) if raw_delta else 0
            if raw_delta and delta == 0:
                delta = -1 if raw_delta > 0 else 1
        if delta:
            self.content_canvas.yview_scroll(delta, "units")
            return "break"
        return None

    @staticmethod
    def _card(parent, title):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground="#30363d")
        tk.Label(card, text=title, bg=CARD, fg=BLUE, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(9, 6))
        return card

    @staticmethod
    def _button(parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white",
                         activebackground=color, activeforeground="white", relief="flat",
                         bd=0, padx=10, pady=7, cursor="hand2", font=("Segoe UI", 9, "bold"))

    def _set_controls(self):
        idle = self.active_operation is None and not self.closing
        ready = bool(self.controller.ready)
        enabled = tk.NORMAL if idle and ready else tk.DISABLED
        for widget in (self.register_button, self.refresh_button, self.delete_button,
                       self.recognize_button, self.camera_button, self.camera_combo,
                       self.stream_entry, self.id_entry, self.name_entry):
            widget.configure(state=enabled)
        in_enrollment = self.active_operation == "enrollment" and self.enrollment is not None
        can_switch_fallback = bool(in_enrollment and self.enrollment.get("fallback_reason"))
        self.enrollment_mode_combo.configure(
            state="readonly" if (idle and ready) or can_switch_fallback else tk.DISABLED
        )
        save_retry = idle and self.enrollment is not None and self.enrollment.get("ready_to_save")
        self.retake_button.configure(state=tk.NORMAL if in_enrollment or save_retry else tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL if in_enrollment or save_retry else tk.DISABLED)
        self.save_button.configure(state=tk.NORMAL if save_retry else tk.DISABLED)
        if self.closing:
            self.exit_button.configure(state=tk.DISABLED)

    def _sync_enrollment_start_button(self, _event=None):
        if not hasattr(self, "register_button") or not hasattr(self, "enrollment_mode_var"):
            return
        mode = str(self.enrollment_mode_var.get()).upper()
        if (getattr(self, "active_operation", None) == "enrollment" and self.enrollment is not None
                and self.enrollment.get("auto_paused") and mode == "MANUAL"
                and self.enrollment.get("mode") == "AUTO"):
            # AUTO remains paused until the operator explicitly selects MANUAL.
            self.enrollment["mode"] = "MANUAL"
            self.enrollment["requests"].put({"action": "select_manual"})
        label = "BẮT ĐẦU QUÉT AUTO" if mode == "AUTO" else "BẮT ĐẦU ĐĂNG KÝ MANUAL"
        self.register_button.configure(text=label)
        if hasattr(self, "retake_button"):
            if (self.active_operation == "enrollment" and self.enrollment is not None
                    and self.enrollment.get("fallback_reason") and mode == "AUTO"):
                self.retake_button.configure(text="Khởi động lại AUTO")
            else:
                self.retake_button.configure(text="Quét lại 5 góc")

    def _start_job(self, kind, callback):
        if self.closing or self.active_operation is not None:
            return False
        token = uuid.uuid4().hex
        stop_event = threading.Event()
        self.active_operation, self.active_token, self.active_stop_event = kind, token, stop_event
        self._set_controls()

        def run():
            try:
                value = callback()
                payload = {"kind": kind, "value": value, "error": None}
            except Exception as exc:
                payload = {"kind": kind, "value": None, "error": exc}
            self.events.put(("job_done", token, payload))

        self.worker_thread = threading.Thread(target=run, name=f"ai1-gui-{kind}", daemon=True)
        self.worker_thread.start()
        return True

    def _start_session(self, kind, worker):
        if self.closing or self.active_operation is not None:
            return None
        token = self.controller.begin_session()
        if token is None:
            self.state_var.set("TRẠNG THÁI: SESSION ĐANG CHẠY")
            return None
        stop_event = threading.Event()
        self.active_operation, self.active_token, self.active_stop_event = kind, token, stop_event
        self._set_controls()

        def run():
            try:
                value = worker(token, stop_event)
                payload = {"kind": kind, "value": value, "error": None}
            except Exception as exc:
                payload = {"kind": kind, "value": None, "error": exc}
            finally:
                self.controller.end_session(token)
            self.events.put(("session_done", token, payload))

        self.worker_thread = threading.Thread(target=run, name=f"ai1-gui-{kind}", daemon=True)
        self.worker_thread.start()
        return token

    def _poll_events(self):
        if self.closing:
            return
        while True:
            try:
                kind, token, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if token != self.active_token:
                continue
            if kind == "enrollment_progress":
                self._show_enrollment_progress(payload)
            elif kind == "enrollment_capture_result":
                self.space_capture_pending = False
                self._show_capture_result(payload)
            elif kind == "enrollment_captured":
                self._show_captured_pose(payload)
            elif kind == "enrollment_retake":
                self._show_retake_pose(payload)
            elif kind == "enrollment_auto_paused":
                if self.enrollment is not None:
                    self.enrollment["auto_paused"] = True
                    self.enrollment["fallback_reason"] = str(
                        payload.get("reason") or "Pose tracking could not be trusted."
                    )
                self.enrollment_mode_var.set("AUTO")
                self._sync_enrollment_start_button()
                reason = str(payload.get("reason") or "Pose chưa đủ tin cậy.")
                self.auto_status_var.set(f"AUTO TẠM DỪNG · {reason}")
                self.capture_hint_var.set(
                    f"AUTO tạm dừng: {reason} · chọn MANUAL để chụp hoặc khởi động lại AUTO."
                )
                self.state_var.set("TRẠNG THÁI: AUTO TẠM DỪNG · CHỜ LỰA CHỌN")
                self._set_controls()
            elif kind == "enrollment_reset":
                self._show_enrollment_reset(payload)
            elif kind == "enrollment_saving":
                self.state_var.set("TRẠNG THÁI: ĐANG KIỂM TRA VÀ LƯU ĐỦ 5 MẪU")
                self.enrollment_hint_set("Đang xác minh 5 embedding rồi lưu vào kho standalone local.")
            elif kind == "recognition_progress":
                count, total = payload
                self.state_var.set("TRẠNG THÁI: ĐANG QUÉT KHUÔN MẶT")
                self.progress_var.set(f"Snapshot: {count}/{total}")
                self.preview_hint.set(f"ĐANG QUÉT KHUÔN MẶT · {count}/{total}")
                title = "ĐANG XỬ LÝ…" if count >= total else "ĐANG QUÉT KHUÔN MẶT"
                detail = ("Đang kiểm tra tính nhất quán và chọn frame rõ nhất."
                          if count >= total else f"Đang lấy ảnh mới · {count}/{total}")
                self._set_result_card(title, detail, YELLOW)
            elif kind == "recognition_frame":
                self.latest_analysis = payload
                code = str(payload.get("code", ""))
                self.quality_var.set(f"Quality: {payload.get('quality_status', 'CHECK')}")
                detected = payload.get("detected_pose") or "—"
                self.detected_pose_var.set(
                    f"Pose phát hiện: {POSE_LABELS.get(detected, detected)}"
                )
                if code and code != "OK":
                    self.preview_hint.set(
                        MESSAGE_LABELS.get(code, payload.get("reason") or code)
                    )
            elif kind == "job_done":
                self.active_operation = None
                self._handle_job_done(payload)
                self._set_controls()
            elif kind == "session_done":
                self.space_capture_pending = False
                self.space_is_down = False
                self.active_operation = None
                self._handle_session_done(payload)
                self._set_controls()
        self.root.after(60, self._poll_events)

    def _handle_job_done(self, payload):
        kind, value, error = payload["kind"], payload["value"], payload["error"]
        if kind == "startup":
            if error:
                self.refresh_employee_list(self.controller.employees)
                self.header_status.set(f"Lỗi khởi tạo AI1: {error}")
                self.header_label.configure(fg=RED)
                self.state_var.set("TRẠNG THÁI: INIT FAILED")
                messagebox.showerror("AI1 không khởi tạo được", str(error), parent=self.root)
                return
            self.refresh_employee_list(value["employees"])
            self.threshold_var.set(f"Threshold: {value['threshold']:.3f}")
            if value["camera_available"]:
                self.header_status.set("buffalo_l sẵn sàng · camera đã kết nối")
                self.header_label.configure(fg=GREEN)
                self.state_var.set("TRẠNG THÁI: READY")
                self.preview.configure(text="")
                self.preview_hint.set("Webcam sẵn sàng. Có thể chọn ESP32-CAM trong nguồn camera.")
            else:
                self.header_status.set("buffalo_l sẵn sàng · camera chưa có frame")
                self.header_label.configure(fg=YELLOW)
                self.state_var.set("TRẠNG THÁI: CAMERA UNAVAILABLE")
                self.preview.configure(text="Camera chưa sẵn sàng — chọn lại nguồn camera.")
                self.preview_hint.set(value.get("camera_error") or "Kiểm tra webcam hoặc URL ESP32-CAM.")
            return
        if error:
            self.state_var.set(f"TRẠNG THÁI: LỖI · {str(error)[:90]}")
            messagebox.showerror("Thao tác thất bại", str(error), parent=self.root)
            if kind == "change_camera":
                self.header_status.set(f"Camera chưa kết nối · {str(error)[:75]}")
                self.header_label.configure(fg=RED)
            return
        if kind == "refresh":
            self.refresh_employee_list(value["employees"])
            self.state_var.set("TRẠNG THÁI: ĐÃ LÀM MỚI DANH SÁCH LOCAL")
        elif kind == "delete_employee":
            self.refresh_employee_list(value["employees"])
            self.state_var.set("TRẠNG THÁI: ĐÃ XÓA NHÂN VIÊN LOCAL")
            self.prediction_var.set("KẾT QUẢ: —")
        elif kind == "change_camera":
            self.camera_type_var.set("ESP32-CAM" if value["camera_type"] == "esp32" else "WEBCAM")
            self.header_status.set(
                "ESP32-CAM đã chọn · chờ frame mới" if value["camera_type"] == "esp32"
                else "Webcam đã kết nối"
            )
            self.header_label.configure(fg=GREEN if value["camera_available"] else YELLOW)
            self.state_var.set("TRẠNG THÁI: CAMERA ĐÃ ĐỔI")
        elif kind == "retry_save":
            self._enrollment_saved(value)

    def _handle_session_done(self, payload):
        kind, value, error = payload["kind"], payload["value"], payload["error"]
        if kind == "enrollment":
            if error:
                session = self.enrollment
                if session is not None and session.get("state") is not None and session["state"].complete:
                    session["ready_to_save"] = True
                    session["session_id"] = None
                    self.state_var.set("TRẠNG THÁI: LƯU CHƯA THÀNH CÔNG · CÓ THỂ THỬ LẠI")
                    self.enrollment_hint_set(str(error))
                else:
                    self._discard_enrollment()
                    self.state_var.set("TRẠNG THÁI: RETRY · ENROLLMENT ĐÃ HỦY")
                    self.preview_hint.set(str(error))
                return
            if value and value.get("status") == "SAVED":
                self._enrollment_saved(value["snapshot"])
            elif value and value.get("status") == "DUPLICATE_FACE":
                duplicate = value["duplicate"]
                self._discard_enrollment()
                self._show_duplicate_face(duplicate)
            elif value and value.get("status") == "READY_TO_SAVE":
                session = self.enrollment
                if session is not None:
                    session["state"] = value["state"]
                    session["ready_to_save"] = True
                    session["session_id"] = None
                self.pose_var.set("ĐÃ ĐỦ 5 MẪU · SẴN SÀNG LƯU")
                self.capture_hint_var.set(
                    "Đã chụp đủ 5 góc. Kiểm tra ảnh rồi nhấn Lưu lại 5 mẫu local."
                )
                self.state_var.set("TRẠNG THÁI: SẴN SÀNG LƯU 5 MẪU")
                self.preview_hint.set(
                    "Đã đủ 5 pose và kiểm tra nhất quán; nhấn Lưu lại 5 mẫu local."
                )
            elif value and value.get("status") == "SAVE_FAILED":
                session = self.enrollment
                if session is not None:
                    session["state"] = value["state"]
                    session["ready_to_save"] = True
                    session["session_id"] = None
                self.state_var.set("TRẠNG THÁI: LƯU THẤT BẠI · CÓ THỂ THỬ LẠI")
                self.enrollment_hint_set(value.get("error", "Không lưu được 5 mẫu."))
            else:
                self._discard_enrollment()
                self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ ĐÃ HỦY · GALLERY KHÔNG THAY ĐỔI")
            return
        if kind == "recognition":
            if error:
                result = {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                          "threshold": self.controller.threshold, "reason": str(error),
                          "latency_ms": 0.0}
            else:
                result = value
            if result is not None:
                self._show_recognition(result)
        elif kind == "save_retry":
            if error:
                if isinstance(error, DuplicateFaceError):
                    duplicate = error.duplicate
                    self._discard_enrollment()
                    self._show_duplicate_face(duplicate)
                    return
                if self.enrollment:
                    self.enrollment["ready_to_save"] = True
                self.state_var.set("TRẠNG THÁI: RETRY SAVE")
                self.enrollment_hint_set(str(error))
            else:
                self._enrollment_saved(value)

    def refresh_employee_list(self, employees=None):
        """Render the one controller/store snapshot used by list, gallery and duplicate checks."""
        employees = list(self.controller.employees if employees is None else employees)
        gallery = {str(identity): person for identity, person in self.controller.gallery.items()}
        for item in self.employee_table.get_children():
            self.employee_table.delete(item)
        for employee in employees:
            identity = str(employee["MaNV"])
            samples = len(gallery.get(identity, {}).get("embeddings", ()))
            self.employee_table.insert("", "end", iid=identity,
                                       values=(identity, employee["HoTen"], samples))
        gallery_employees = sum(
            bool(person.get("embeddings")) for person in gallery.values()
        )
        embedding_count = sum(len(person.get("embeddings", ())) for person in gallery.values())
        if hasattr(self, "gallery_status_var"):
            self.gallery_status_var.set(
                f"Gallery: {gallery_employees} nhân viên / {embedding_count} embeddings"
            )
        if self.controller.ready:
            self.header_status.set(f"buffalo_l sẵn sàng · {len(employees)} nhân viên standalone")
            self.header_label.configure(fg=GREEN)
        return {"employees": len(employees), "gallery_employees": gallery_employees,
                "embeddings": embedding_count}

    def _select_employee(self, _event=None):
        selection = self.employee_table.selection()
        if not selection:
            return
        identity = selection[0]
        employee = next((item for item in self.controller.employees if item["MaNV"] == identity), None)
        if employee:
            self.id_var.set(employee["MaNV"])
            self.name_var.set(employee["HoTen"])

    def _refresh(self):
        self.state_var.set("TRẠNG THÁI: ĐANG LÀM MỚI GALLERY LOCAL…")
        self._start_job("refresh", self.controller.refresh_data)

    def _change_camera(self):
        selected = self.camera_type_var.get().strip().upper()
        source_type = "esp32" if selected == "ESP32-CAM" else "webcam"
        url = self.stream_url_var.get().strip()
        self.state_var.set("TRẠNG THÁI: ĐANG MỞ NGUỒN CAMERA…")
        self._start_job("change_camera", lambda: self.controller.change_camera(source_type, url))

    def _begin_registration(self):
        if self.controller.source is None:
            messagebox.showwarning("Camera chưa sẵn sàng", "Chọn nguồn camera đang có frame trước.",
                                   parent=self.root)
            return
        try:
            identity = validate_employee_id(self.id_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("Employee ID không hợp lệ", str(exc), parent=self.root)
            return
        name = self.name_var.get().strip()
        existing_employee = next(
            (person for person in self.controller.employees
             if str(person["MaNV"]) == identity),
            None,
        )
        overwrite = False
        if existing_employee is not None:
            existing_name = str(existing_employee.get("HoTen") or identity)
            if not name:
                name = existing_name
                self.name_var.set(name)
            overwrite = messagebox.askyesno(
                "Đăng ký lại / cập nhật khuôn mặt",
                f"Employee ID {identity} đã tồn tại: {existing_name}.\n\n"
                "Bạn muốn chụp lại đủ 5 pose và thay thế bộ khuôn mặt local hiện tại không?\n"
                "Thao tác chỉ thay dữ liệu sau khi đủ 5 mẫu hợp lệ.",
                parent=self.root,
            )
            if not overwrite:
                return
        else:
            if not name:
                messagebox.showerror("Thiếu Employee Name", "Nhập họ tên trước khi đăng ký.", parent=self.root)
                return
            target = safe_identity_path(self.controller.store.images_root, identity)
            if target.exists():
                messagebox.showerror("Dữ liệu local không đồng bộ",
                                     "Đã có thư mục ảnh cho mã này; không ghi đè im lặng.",
                                     parent=self.root)
                return
        try:
            self.controller.store.ensure()
            stage = Path(tempfile.mkdtemp(prefix=f".pending-gui-{identity}-",
                                          dir=self.controller.store.root))
        except Exception as exc:
            messagebox.showerror("Không tạo được thư mục tạm", str(exc), parent=self.root)
            return
        mode_var = getattr(self, "enrollment_mode_var", None)
        selected_mode = mode_var.get() if mode_var is not None else "MANUAL"
        self.enrollment = {
            "identity": identity, "name": name, "overwrite": overwrite,
            "stage": stage, "frames": {}, "state": EnrollmentCaptureState(),
            "requests": queue.Queue(), "ready_to_save": False, "saved": False,
            "session_id": None, "captured_order_ui": [],
            "mode": selected_mode, "capture_pending": False, "fallback_reason": None,
            "auto_paused": False,
        }
        self.last_result_status = None
        self.result_card_until = 0.0
        if hasattr(self, "result_card"):
            self.result_card.place_forget()
        self.space_is_down = False
        self.space_capture_pending = False
        self.capture_feedback = None
        self.latest_analysis = {}
        self._reset_thumbnails()
        self.progress.configure(value=0)
        self._update_pose_ring(0, 0)
        self.progress_var.set("Tiến độ: 0/5")
        if hasattr(self, "enrollment_progress_var"):
            self.enrollment_progress_var.set("Tiến độ: 0/5")
        self.quality_var.set("Quality: đang kiểm tra")
        self.pose_var.set("Pose yêu cầu: 1/5 · Nhìn thẳng")
        self.detected_pose_var.set("Pose phát hiện: —")
        mode = self.enrollment["mode"]
        self._sync_enrollment_start_button()
        self.capture_hint_var.set(
            "Nhìn thẳng tự nhiên để hiệu chỉnh frontal; camera sẽ tự gom các frame hợp lệ."
            if mode == "AUTO" else "Nhìn theo pose yêu cầu; quality PASS thì nhấn SPACE để chụp."
        )
        if hasattr(self, "auto_status_var"):
            self.auto_status_var.set(
                f"AUTO: hiệu chỉnh frontal · {GUIDED_POSE_STABLE_FRAMES} frame hợp lệ / "
                f"≤{GUIDED_POSE_STABILITY_WINDOW_SECONDS:.0f} giây"
                if mode == "AUTO" else "MANUAL: nhấn SPACE để chụp pose hiện tại"
            )
        token = self._start_session("enrollment", self._enrollment_worker)
        if token is None:
            self._discard_enrollment()
            return
        self.enrollment["session_id"] = token
        self.state_var.set(f"TRẠNG THÁI: ĐĂNG KÝ {identity} · POSE 1/5")
        self._set_controls()

    def _capture_enrollment_sample(self, token, session, sequence, captured_at, frame, outcome,
                                   auto_tracker=None):
        """Validate identity and stage one selected sample without touching the gallery."""
        state = session["state"]
        pose = state.current_pose
        if pose is None:
            return {"status": "CANCELLED"}
        if not isinstance(outcome, dict) or outcome.get("status") != "OK":
            code = outcome.get("code", "QUALITY CHECK") if isinstance(outcome, dict) else "QUALITY CHECK"
            reason = outcome.get("reason", code) if isinstance(outcome, dict) else code
            self.events.put(("enrollment_capture_result", token, {
                "captured": False, "code": code, "reason": reason,
            }))
            return {"status": "REJECTED", "code": code}

        if pose == POSES[0]:
            duplicate = self.controller.find_duplicate_employee(
                outcome["embedding"], exclude_identity=session["identity"]
            )
            if duplicate is not None:
                return {"status": "DUPLICATE_FACE", "duplicate": duplicate}
        try:
            capture = state.capture(outcome)
        except (TypeError, ValueError, RuntimeError) as exc:
            reason = str(exc)
            code = "SAME PERSON" if "frontal reference" in reason.lower() else "INVALID EMBEDDING"
            self.events.put(("enrollment_capture_result", token, {
                "captured": False, "code": code, "reason": reason,
            }))
            return {"status": "REJECTED", "code": code}

        image_path = session["stage"] / f"{pose}.jpg"
        try:
            _atomic_write_jpeg(image_path, frame)
        except Exception as exc:
            state.clear_pose(pose)
            self.events.put(("enrollment_capture_result", token, {
                "captured": False, "code": "IMAGE SAVE FAILED",
                "reason": f"Không lưu được ảnh tạm: {exc}",
            }))
            return {"status": "REJECTED", "code": "IMAGE SAVE FAILED"}

        session["frames"][pose] = frame.copy()
        self.events.put(("enrollment_capture_result", token, {
            "captured": True, "code": "OK", "reason": "Đã chọn mẫu pose đạt chất lượng.",
            "mode": session.get("mode", "MANUAL"),
        }))
        self.events.put(("enrollment_captured", token, {
            "pose": pose, "frame": frame.copy(), "captured": capture["captured"],
            "current_pose": state.current_pose,
            "mode": session.get("mode", "MANUAL"),
        }))
        if auto_tracker is not None:
            auto_tracker.capture_result(
                True, state.current_pose, embedding=state.embeddings[pose]
            )
        if not state.complete:
            return {"status": "CAPTURED", "pose": pose, "next_pose": state.current_pose}

        consistency = state.validate_complete()
        if not consistency["valid"]:
            bad_poses = consistency.get("bad_poses") or list(POSES)
            for bad_pose in bad_poses:
                state.clear_pose(bad_pose)
                session["frames"].pop(bad_pose, None)
                staged = session["stage"] / f"{bad_pose}.jpg"
                if staged.exists():
                    staged.unlink()
            if auto_tracker is not None:
                auto_tracker.reset()
            self.events.put(("enrollment_retake", token, {
                "poses": bad_poses, "captured": len(state.embeddings),
                "current_pose": state.current_pose, "reason": consistency.get("reason"),
            }))
            return {"status": "RETAKE", "reason": consistency.get("reason")}
        return {"status": "READY_TO_SAVE", "state": state}

    def _enrollment_worker(self, token, stop_event):
        session = self.enrollment
        if session is None:
            return {"status": "CANCELLED"}
        state = session["state"]
        mode = session.get("mode", "MANUAL")
        auto_tracker = GuidedPoseTracker() if mode == "AUTO" else None
        session["auto_tracker"] = auto_tracker
        last_sequence = -1
        last_reported_duplicate_sequence = None
        last_ui_time = 0.0
        last_ui_signature = None
        last_worker_analysis = {}
        pose_started_at = time.monotonic()

        def pause_auto(reason):
            if session.get("mode") != "AUTO" or session.get("auto_paused"):
                return
            session["auto_paused"] = True
            session["fallback_reason"] = str(reason)
            if auto_tracker is not None:
                auto_tracker.force_manual_fallback(reason)
            self.events.put(("enrollment_auto_paused", token, {"reason": str(reason)}))

        try:
            while not stop_event.is_set():
                while True:
                    try:
                        request = session["requests"].get_nowait()
                    except queue.Empty:
                        break
                    if not isinstance(request, dict):
                        continue
                    action = request.get("action")
                    if action == "reset_all":
                        requested_mode = str(request.get("mode", session.get("mode", "MANUAL"))).upper()
                        if requested_mode not in {"AUTO", "MANUAL"}:
                            requested_mode = "MANUAL"
                        session["mode"] = requested_mode
                        session["fallback_reason"] = None
                        session["auto_paused"] = False
                        auto_tracker = GuidedPoseTracker() if requested_mode == "AUTO" else None
                        session["auto_tracker"] = auto_tracker
                        state = EnrollmentCaptureState()
                        session["state"] = state
                        session["frames"].clear()
                        session["capture_pending"] = False
                        for staged in session["stage"].glob("*.jpg"):
                            staged.unlink()
                        pose_started_at = time.monotonic()
                        self.events.put(("enrollment_reset", token, {"mode": session.get("mode")}))
                        continue

                    if action == "select_manual":
                        if session.get("mode") == "MANUAL":
                            session["auto_paused"] = False
                            auto_tracker = None
                            session["auto_tracker"] = None
                            self.events.put(("enrollment_mode_selected", token,
                                             {"mode": "MANUAL"}))
                        continue

                    if action in {"capture", "capture_auto"}:
                        if action == "capture_auto":
                            candidate = request["candidate"]
                            sequence = candidate["sequence"]
                            captured_at = candidate["captured_at"]
                            frame = candidate["frame"].copy()
                            age = time.monotonic() - captured_at
                            if age < -0.1 or age > STALE_FRAME_SECONDS:
                                if auto_tracker is not None:
                                    auto_tracker.capture_result(False, state.current_pose)
                                session["capture_pending"] = False
                                self.events.put(("enrollment_capture_result", token, {
                                    "captured": False, "code": "STALE_FRAME",
                                    "reason": "Mẫu ổn định đã cũ; đang chờ pose mới.",
                                }))
                                continue
                            # Pose/quality tracking used SCRFD only. ArcFace is
                            # now run once on the sharpest selected frame, then
                            # pose and identity are revalidated before staging.
                            pose = state.current_pose
                            outcome = validate_enrollment_frame(
                                self.controller.engine, frame, pose, enforce_pose=False
                            )
                            selected_check = (auto_tracker.validate_selected_candidate(
                                candidate, outcome, pose
                            ) if auto_tracker is not None else {
                                "status": "RETRY", "code": "AUTO TRACKER MISSING",
                                "reason": "Không còn AUTO tracker để xác minh mẫu đã chọn.",
                            })
                            if selected_check.get("status") != "OK":
                                if auto_tracker is not None:
                                    auto_tracker.capture_result(False, pose)
                                session["capture_pending"] = False
                                self.events.put(("enrollment_capture_result", token, {
                                    "captured": False,
                                    "code": selected_check.get("code", "QUALITY CHECK"),
                                    "reason": selected_check.get("reason", "Mẫu đã chọn không hợp lệ."),
                                }))
                                continue
                            outcome = {**outcome, "embedding": selected_check["embedding"]}
                        else:
                            packet, failure_code = self._wait_for_new_packet(last_sequence, stop_event)
                            if packet is None:
                                code = failure_code or "CAMERA DISCONNECTED"
                                self.events.put(("enrollment_capture_result", token, {
                                    "captured": False, "code": code,
                                    "reason": "Không nhận được frame camera mới để chụp.",
                                }))
                                continue
                            last_sequence = packet.sequence
                            sequence, captured_at = packet.sequence, packet.captured_at
                            frame = packet.frame.copy()
                            age = time.monotonic() - packet.captured_at
                            pose = state.current_pose
                            if age < -0.1 or age > STALE_FRAME_SECONDS:
                                outcome = {"status": "RETRY", "code": "STALE_FRAME",
                                           "reason": "Khung hình camera đã cũ.", "face": None,
                                           "faces": [], "face_count": 0, "quality": {}}
                            else:
                                outcome = validate_enrollment_frame(
                                    self.controller.engine, frame, pose, enforce_pose=False
                                )
                            analysis = self._make_enrollment_analysis(
                                packet, frame, pose, outcome, len(state.embeddings)
                            )
                            self.events.put(("enrollment_progress", token, analysis))

                        result = self._capture_enrollment_sample(
                            token, session, sequence, captured_at, frame, outcome,
                            auto_tracker=auto_tracker if action == "capture_auto" else None,
                        )
                        if action == "capture_auto":
                            session["capture_pending"] = False
                            if result["status"] not in {"CAPTURED", "READY_TO_SAVE"}:
                                if auto_tracker is not None:
                                    auto_tracker.capture_result(False, state.current_pose)
                            else:
                                pose_started_at = time.monotonic()
                        if result["status"] == "DUPLICATE_FACE":
                            return result
                        if result["status"] == "READY_TO_SAVE":
                            return result
                        continue

                    if action == "retake":
                        pose = request.get("pose")
                    else:
                        pose = None
                    if pose in state.embeddings:
                        state.clear_pose(pose)
                        session["frames"].pop(pose, None)
                        image_path = session["stage"] / f"{pose}.jpg"
                        if image_path.exists():
                            image_path.unlink()
                        if auto_tracker is not None:
                            if pose == "frontal":
                                auto_tracker.reset()
                            else:
                                auto_tracker.capture_result(False, state.current_pose)
                        pose_started_at = time.monotonic()
                        self.events.put(("enrollment_retake", token, {
                            "pose": pose, "captured": len(state.embeddings),
                            "current_pose": state.current_pose,
                        }))

                packet = self.controller.get_packet()
                if packet is None:
                    missing = (auto_tracker.note_missing_frame() if auto_tracker is not None
                               and session.get("mode") == "AUTO" else {})
                    if (session.get("mode") == "AUTO"
                            and time.monotonic() - pose_started_at >= GUIDED_POSE_TIMEOUT_SECONDS):
                        timeout_detail = (auto_tracker._timeout_reason(state.current_pose)
                                          if auto_tracker is not None else
                                          f"AUTO quá {GUIDED_POSE_TIMEOUT_SECONDS:.0f} giây.")
                        pause_auto(
                            f"{missing.get('reason', 'Không có frame mới từ camera.')} "
                            f"{timeout_detail}"
                        )
                    missing_analysis = {
                        "current_pose": state.current_pose, "detected_pose": "—",
                        "captured": len(state.embeddings),
                        "code": "STALE_FRAME",
                        "reason": missing.get("reason", "Camera chưa có frame mới."),
                        "bbox": None, "sharpness": None, "color": RED, "sequence": None,
                        "quality_status": "FAIL", "diagnostics": {},
                        "mode": session.get("mode", "MANUAL"),
                        "auto_status": ("FALLBACK_MANUAL" if session.get("mode") == "MANUAL"
                                        else "AUTO_PAUSED" if session.get("auto_paused")
                                        else missing.get("status", "STALE_FRAME")),
                        "fallback_reason": session.get("fallback_reason"),
                        "stable_count": missing.get("stable_count", 0),
                        "inference_fps": missing.get("inference_fps"),
                        "valid_frames": missing.get("valid_frames", missing.get("stable_count", 0)),
                        "time_remaining_seconds": missing.get("time_remaining_seconds"),
                    }
                    missing_signature = self._analysis_signature(
                        missing_analysis["code"], state, missing_analysis["detected_pose"],
                        missing_analysis["auto_status"], missing_analysis["stable_count"],
                        missing_analysis["mode"],
                    )
                    now = time.monotonic()
                    if missing_signature != last_ui_signature or now - last_ui_time >= 0.12:
                        self.events.put(("enrollment_progress", token, missing_analysis))
                        last_ui_signature, last_ui_time = missing_signature, now
                    stop_event.wait(0.04)
                    continue

                if packet.sequence <= last_sequence:
                    if (session.get("mode") == "AUTO" and auto_tracker is not None
                            and packet.sequence != last_reported_duplicate_sequence):
                        repeated = auto_tracker.note_repeated_frame()
                        last_reported_duplicate_sequence = packet.sequence
                        now = time.monotonic()
                        if now - last_ui_time >= 0.12:
                            repeated_analysis = dict(last_worker_analysis)
                            repeated_analysis.update({
                                "current_pose": state.current_pose,
                                "captured": len(state.embeddings),
                                "code": "STALE_FRAME", "reason": repeated["reason"],
                                "mode": "AUTO", "auto_status": repeated["status"],
                                "stable_count": repeated["stable_count"],
                                "inference_fps": repeated.get("inference_fps"),
                                "valid_frames": repeated.get("valid_frames", repeated.get("stable_count", 0)),
                                "time_remaining_seconds": repeated.get("time_remaining_seconds"),
                            })
                            self.events.put(("enrollment_progress", token, repeated_analysis))
                            last_ui_time = now
                    stop_event.wait(0.005)
                    continue
                last_sequence = packet.sequence
                last_reported_duplicate_sequence = None
                age = time.monotonic() - packet.captured_at
                pose = state.current_pose
                frame = packet.frame.copy()
                if age < -0.1 or age > STALE_FRAME_SECONDS:
                    outcome = {
                        "status": "RETRY", "code": "STALE_FRAME",
                        "reason": "Khung hình camera đã cũ.", "face": None,
                        "faces": [], "face_count": 0, "quality": {}, "diagnostics": {},
                    }
                    analysis = {
                        "current_pose": pose, "detected_pose": "—",
                        "captured": len(state.embeddings), "code": "STALE_FRAME",
                        "reason": "Khung hình camera đã cũ.", "bbox": None, "sharpness": None,
                        "color": RED, "sequence": packet.sequence, "quality_status": "FAIL",
                        "diagnostics": {}, "expected_pose": pose,
                    }
                else:
                    if session.get("mode") == "AUTO" and auto_tracker is not None:
                        outcome = validate_enrollment_pose_frame(
                            self.controller.engine, frame, pose
                        )
                    else:
                        outcome = validate_enrollment_frame(
                            self.controller.engine, frame, pose, enforce_pose=False
                        )
                    analysis = self._make_enrollment_analysis(
                        packet, frame, pose, outcome, len(state.embeddings)
                    )
                last_worker_analysis = analysis
                analysis["mode"] = session.get("mode", "MANUAL")
                if session.get("mode") == "AUTO" and auto_tracker is not None:
                    auto = auto_tracker.observe(
                        pose, outcome, frame, packet.sequence, packet.captured_at,
                        now=time.monotonic(),
                    )
                    analysis.update({
                        "auto_status": auto.get("status"),
                        "auto_reason": auto.get("reason"),
                        "inference_fps": auto.get("inference_fps"),
                        "calibrated_yaw": auto.get("yaw"),
                        "calibrated_pitch": auto.get("pitch"),
                        "pose_roll": auto.get("roll"),
                        "frontal_view": auto.get("frontal_view"),
                        "frontal_ok": auto.get("frontal_ok"),
                        "calibrating": bool(auto.get("calibrating", False)),
                        "calibration_reason": auto.get("reason"),
                        "reprojection_error_px": auto.get("reprojection_error_px"),
                        "stable_count": auto.get("stable_count", 0),
                        "valid_frames": auto.get("valid_frames", auto.get("stable_count", 0)),
                        "time_remaining_seconds": auto.get("time_remaining_seconds"),
                        "stability_window_expirations": auto.get("stability_window_expirations", 0),
                        "detected_pose": auto.get("detected_pose", analysis.get("detected_pose")),
                    })
                    if auto.get("reason") and auto.get("status") not in {
                            "CAPTURE_READY", "CAPTURE_PENDING"}:
                        analysis["reason"] = auto["reason"]
                        if auto.get("fps_reason") and auto["fps_reason"] not in analysis["reason"]:
                            analysis["reason"] += f" {auto['fps_reason']}"
                    if auto.get("status") in {
                            "POSE_NOT_READY", "WRONG_POSE", "STABILIZING", "LOW_FPS",
                            "POSE_UNRELIABLE", "IDENTITY_MISMATCH"}:
                        analysis["color"] = YELLOW
                    if auto.get("status") == "CAPTURE_READY" and not session.get("capture_pending"):
                        candidate = auto["candidate"]
                        session["capture_pending"] = True
                        session["requests"].put({"action": "capture_auto", "candidate": candidate})
                        analysis["auto_status"] = "CAPTURE_PENDING"
                        analysis["reason"] = (
                            f"Đã gom {auto['stable_count']}/{GUIDED_POSE_STABLE_FRAMES} frame hợp lệ "
                            "trong cửa sổ ổn định; đang chọn ảnh nét nhất."
                        )
                    elif auto.get("status") in {"FALLBACK_MANUAL", "AUTO_PAUSED"}:
                        pause_auto(auto.get("reason", "Pose estimate unreliable."))
                        analysis["auto_status"] = "AUTO_PAUSED"
                        analysis["reason"] = (
                            f"{auto.get('reason', 'Pose chưa tin cậy')} · AUTO tạm dừng; "
                            "chọn MANUAL hoặc khởi động lại AUTO."
                        )
                    elif (time.monotonic() - pose_started_at >= GUIDED_POSE_TIMEOUT_SECONDS
                          and auto.get("status") not in {"CAPTURE_READY", "CAPTURE_PENDING"}):
                        reason = auto_tracker._timeout_reason(state.current_pose)
                        pause_auto(reason)
                        analysis["auto_status"] = "AUTO_PAUSED"
                        analysis["reason"] = (
                            f"{reason} · chọn MANUAL để tiếp tục hoặc khởi động lại AUTO."
                        )
                elif session.get("fallback_reason"):
                    analysis["auto_status"] = "FALLBACK_MANUAL"
                    analysis["auto_reason"] = session["fallback_reason"]
                    analysis["fallback_reason"] = session["fallback_reason"]

                signature = self._analysis_signature(
                    analysis.get("code"), state, analysis.get("detected_pose"),
                    analysis.get("auto_status"), analysis.get("stable_count", 0),
                    analysis.get("mode"),
                )
                now = time.monotonic()
                if signature != last_ui_signature or now - last_ui_time >= 0.12:
                    self.events.put(("enrollment_progress", token, analysis))
                    last_ui_signature, last_ui_time = signature, now
            return {"status": "CANCELLED"}
        finally:
            if stop_event.is_set() and session["stage"].exists():
                shutil.rmtree(session["stage"], ignore_errors=True)

    def _wait_for_new_packet(self, after_sequence, stop_event, timeout=1.0):
        """Get a new, fresh camera frame for the manual capture request."""
        deadline = time.monotonic() + timeout
        failure_code = "CAMERA DISCONNECTED"
        while not stop_event.is_set() and time.monotonic() < deadline:
            packet = self.controller.get_packet()
            if packet is not None and packet.sequence > after_sequence:
                age = time.monotonic() - packet.captured_at
                if -0.1 <= age <= STALE_FRAME_SECONDS:
                    return packet, None
                failure_code = "STALE_FRAME"
            stop_event.wait(0.015)
        return None, failure_code

    @staticmethod
    def _make_enrollment_analysis(packet, frame, pose, outcome, captured):
        face = outcome.get("face") if isinstance(outcome, dict) else None
        quality = outcome.get("quality", {}) if isinstance(outcome, dict) else {}
        diagnostics = outcome.get("diagnostics", {}) if isinstance(outcome, dict) else {}
        valid = isinstance(outcome, dict) and outcome.get("status") == "OK"
        code = "OK" if valid else str(outcome.get("code", "QUALITY CHECK"))
        reason = ("Quality PASS · Nhấn SPACE để chụp" if valid else
                  str(outcome.get("reason") or code))
        faces = outcome.get("faces", []) if isinstance(outcome, dict) else []
        return {
            "current_pose": pose,
            "captured": captured,
            "code": code,
            "reason": reason,
            "detected_pose": outcome.get("detected_pose", "—") if isinstance(outcome, dict) else "—",
            "raw_detected_pose": diagnostics.get("raw_pose_classification") if diagnostics else None,
            "bbox": list(face["bbox"]) if isinstance(face, dict) and face.get("bbox") else None,
            "bboxes": [list(item["bbox"]) for item in faces
                       if isinstance(item, dict) and item.get("bbox")],
            "detection_scores": [item.get("detection_score") for item in faces
                                 if isinstance(item, dict)],
            "detection_score": face.get("detection_score") if isinstance(face, dict) else None,
            "frame_shape": list(frame.shape[:2]),
            "observed_at": time.monotonic(),
            "quality_status": "PASS" if valid else "FAIL",
            "diagnostics": diagnostics,
            "expected_pose": pose,
            "sharpness": quality.get("sharpness"),
            "brightness": quality.get("brightness"),
            "color": GREEN if valid else RED,
            "sequence": packet.sequence,
        }

    @staticmethod
    def _analysis_signature(code, state, detected_pose, auto_status=None,
                            stable_count=0, mode="MANUAL"):
        return (code, state.current_pose, len(state.embeddings), detected_pose,
                auto_status, int(stable_count or 0), mode)

    def _show_enrollment_progress(self, analysis):
        if self.enrollment is None:
            return
        pose = analysis.get("current_pose")
        pose_number = POSES.index(pose) + 1 if pose in POSES else min(int(analysis.get("captured", 0)) + 1, 5)
        requested = POSE_LABELS.get(pose, "Đã đủ 5 pose")
        self.pose_var.set(f"Pose yêu cầu: {pose_number}/5 · {requested}")
        mode = str(analysis.get("mode", self.enrollment.get("mode", "MANUAL"))).upper()
        detected = analysis.get("detected_pose") or "—"
        raw_detected = analysis.get("raw_detected_pose") or detected
        detected_for_ui = detected if mode == "AUTO" else raw_detected
        detected_text = POSE_LABELS.get(detected_for_ui, detected_for_ui)
        if mode != "AUTO" and raw_detected != detected:
            detected_text += f" → {POSE_LABELS.get(detected, detected)} (jitter)"
        self.detected_pose_var.set(f"Pose phát hiện: {detected_text}")
        code = str(analysis.get("code", ""))
        reason = str(analysis.get("reason", ""))
        auto_status = str(analysis.get("auto_status") or "")
        stable_count = int(analysis.get("stable_count") or 0)
        captured = int(analysis.get("captured", len(self.enrollment["state"].embeddings)))
        self._update_pose_ring(captured, stable_count if mode == "AUTO" else 0)
        if mode == "AUTO":
            manual_choice_pending = bool(
                self.enrollment.get("auto_paused")
                and str(self.enrollment_mode_var.get()).upper() == "MANUAL"
            )
            if not manual_choice_pending:
                self.enrollment_mode_var.set("AUTO")
            if auto_status == "STABILIZING":
                if analysis.get("calibrating"):
                    message = ("Đang hiệu chỉnh frontal · nhìn thẳng tự nhiên · "
                               f"{stable_count}/{GUIDED_POSE_STABLE_FRAMES}")
                else:
                    message = (f"{POSE_DIRECTIONS.get(pose, 'Giữ pose hiện tại')} · "
                               f"đã gom {stable_count}/{GUIDED_POSE_STABLE_FRAMES} frame hợp lệ "
                               f"trong {GUIDED_POSE_STABILITY_WINDOW_SECONDS:.0f}s")
            elif auto_status == "LOW_FPS":
                message = reason or "FPS inference thấp; AUTO đang chờ thêm frame mới."
            elif auto_status == "CAPTURE_PENDING":
                message = "Đủ frame ổn định · đang chọn frame rõ nhất để tự chụp."
            elif auto_status == "CAPTURE_READY":
                message = "Đã đạt pose · đang chụp mẫu tốt nhất."
            elif auto_status == "POSE_NOT_READY":
                message = reason or (
                    f"Hãy {POSE_DIRECTIONS.get(pose, 'điều chỉnh đầu')} · hiện tại: "
                    f"{analysis.get('detected_pose', 'between')}"
                )
            elif auto_status in {
                    "WRONG_POSE", "POSE_UNRELIABLE", "QUALITY_REJECTED", "STALE_FRAME",
                    "IDENTITY_MISMATCH"}:
                message = reason or str(analysis.get("auto_reason") or auto_status)
            elif auto_status == "FALLBACK_MANUAL":
                message = reason or "Pose chưa ổn định · dùng SPACE để chụp thủ công."
            elif auto_status == "AUTO_PAUSED":
                message = reason or "AUTO đã tạm dừng · chọn MANUAL hoặc khởi động lại AUTO."
            else:
                message = "Nhìn thẳng vào camera để hiệu chỉnh pose frontal."
            yaw, pitch = analysis.get("calibrated_yaw"), analysis.get("calibrated_pitch")
            angles = (f" · Yaw {float(yaw):+.1f}° / Pitch {float(pitch):+.1f}°"
                      if yaw is not None and pitch is not None else "")
            status_detail = ("frontal calibration · góc tương đối chưa có"
                             if analysis.get("calibrating") and yaw is None
                             else f"frame hợp lệ {stable_count}/{GUIDED_POSE_STABLE_FRAMES}{angles}")
            inference_fps = analysis.get("inference_fps")
            if inference_fps is not None:
                status_detail += f" · {float(inference_fps):.1f} FPS"
            else:
                status_detail += " · — FPS"
            remaining = analysis.get("time_remaining_seconds")
            if remaining is not None:
                status_detail += f" · còn {max(0, int(float(remaining)))}s"
            self.auto_status_var.set(f"AUTO · {auto_status or 'WAITING'} · {status_detail}")
        else:
            self.enrollment_mode_var.set("MANUAL")
            fallback_reason = (analysis.get("fallback_reason")
                               or self.enrollment.get("fallback_reason"))
            if fallback_reason:
                self.auto_status_var.set(f"MANUAL FALLBACK · {fallback_reason}")
            else:
                self.auto_status_var.set("MANUAL · nhấn SPACE khi quality PASS")
            message = ("Quality PASS · nhấn SPACE để chụp" if code == "OK" else
                       MESSAGE_LABELS.get(code, reason or "Kiểm tra chất lượng ảnh"))
        diagnostics = analysis.get("diagnostics", {})
        quality_result = diagnostics.get("quality_result")
        quality_code = diagnostics.get("quality_code")
        if quality_result:
            displayed_quality_code = quality_code or code
            self.quality_var.set(f"Quality: {quality_result} · {displayed_quality_code}")
        else:
            self.quality_var.set(f"Quality: {'PASS' if code == 'OK' else 'FAIL'} · {code}")
        self.capture_hint_var.set(message)
        if self.capture_feedback:
            suffix = "· giữ pose rồi chờ tự chụp" if mode == "AUTO" else "· chỉnh lại rồi nhấn SPACE"
            message = f"{self.capture_feedback} {suffix}"
            self.capture_hint_var.set(message)
        if self.capture_feedback:
            self.state_var.set(f"TRẠNG THÁI: {self.capture_feedback}")
        elif mode == "AUTO":
            status_map = {
                "STABILIZING": "ĐANG GOM FRAME HỢP LỆ",
                "LOW_FPS": "FPS INFERENCE THẤP",
                "CAPTURE_PENDING": "ĐANG TỰ CHỌN MẪU TỐT NHẤT",
                "POSE_NOT_READY": "ĐANG ĐIỀU CHỈNH POSE",
                "WRONG_POSE": "SAI HƯỚNG ĐẦU",
                "POSE_UNRELIABLE": "POSE CHƯA ĐÁNG TIN CẬY",
                "IDENTITY_MISMATCH": "KHUÔN MẶT KHÔNG NHẤT QUÁN",
                "QUALITY_REJECTED": "QUALITY GATE CHƯA ĐẠT",
                "STALE_FRAME": "ĐANG CHỜ FRAME MỚI",
                "FALLBACK_MANUAL": "MANUAL FALLBACK · SPACE",
                "AUTO_PAUSED": "AUTO TẠM DỪNG · CHỜ LỰA CHỌN",
            }
            self.state_var.set(f"TRẠNG THÁI: {status_map.get(auto_status, message)}")
        else:
            self.state_var.set("TRẠNG THÁI: SẴN SÀNG · NHẤN SPACE" if code == "OK"
                               else f"TRẠNG THÁI: {message}")
        self.preview_hint.set(message)
        self.latest_analysis = analysis
        if analysis.get("sharpness") is not None:
            self.sharpness_var.set(f"Sharpness: {float(analysis['sharpness']):.1f}")
        progress_text = f"Tiến độ: {captured}/5"
        if mode == "AUTO" and pose in POSES:
            progress_text += f" · frame hợp lệ {stable_count}/{GUIDED_POSE_STABLE_FRAMES}"
        self.progress_var.set(progress_text)
        self.enrollment_progress_var.set(progress_text)

    def _show_capture_result(self, payload):
        if payload.get("captured"):
            self.capture_feedback = None
            mode = str(payload.get("mode", self.enrollment.get("mode", "MANUAL"))).upper()
            self.capture_hint_var.set("Đã tự chụp pose tốt nhất." if mode == "AUTO"
                                      else "Đã chụp pose.")
            return
        code = str(payload.get("code", "QUALITY CHECK"))
        reason = str(payload.get("reason", ""))
        message = MESSAGE_LABELS.get(code, reason or code)
        mode = self.enrollment.get("mode", "MANUAL")
        self.capture_feedback = message
        self.quality_var.set(f"Quality: FAIL · {code}")
        suffix = "pose chưa được chụp · tiếp tục hướng dẫn AUTO" if mode == "AUTO" \
            else "pose chưa được chụp"
        self.capture_hint_var.set(f"{message} · {suffix}")
        self.state_var.set(f"TRẠNG THÁI: {message}")
        suffix = "· tiếp tục theo hướng dẫn AUTO" if mode == "AUTO" else "· chỉnh lại rồi nhấn SPACE"
        self.preview_hint.set(f"{message} {suffix}")

    def _show_captured_pose(self, payload):
        self.capture_feedback = None
        pose = payload["pose"]
        frame = payload["frame"]
        index = POSES.index(pose)
        thumb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        thumb = ImageOps.fit(thumb, (74, 50), method=Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(thumb)
        self.thumbnail_photos[index] = photo
        self.thumb_labels[index].configure(image=photo, text="")
        self.thumb_status_labels[index].configure(text="✓", fg=GREEN)
        if pose not in self.captured_pose_order:
            self.captured_pose_order.append(pose)
        self.progress.configure(value=payload["captured"])
        self.progress_var.set(f"Tiến độ: {payload['captured']}/5")
        self.enrollment_progress_var.set(f"Tiến độ: {payload['captured']}/5")
        mode = str(payload.get("mode", self.enrollment.get("mode", "MANUAL"))).upper()
        self._update_pose_ring(payload["captured"], 0)
        for pose_index, cell in enumerate(self.thumb_cells):
            if pose_index < int(payload["captured"]):
                cell.configure(bg="#163323")
            elif payload.get("current_pose") == POSES[pose_index]:
                cell.configure(bg="#1b2d46")
            else:
                cell.configure(bg=PANEL)
        if payload["current_pose"]:
            number = POSES.index(payload["current_pose"]) + 1
            self.pose_var.set(f"Pose yêu cầu: {number}/5 · {POSE_LABELS[payload['current_pose']]}")
            next_pose = POSE_LABELS[payload["current_pose"]]
            if mode == "AUTO":
                self.capture_hint_var.set(
                    f"Đã chụp: {payload['captured']}/5 · Pose tiếp theo: {next_pose} · "
                    f"{POSE_DIRECTIONS.get(payload['current_pose'], '')}"
                )
                self.auto_status_var.set("AUTO · chuyển sang pose tiếp theo")
            else:
                self.capture_hint_var.set(
                    f"Đã chụp: {payload['captured']}/5 · Pose tiếp theo: {next_pose} · nhấn SPACE"
                )
                self.auto_status_var.set("MANUAL · nhấn SPACE khi quality PASS")
            self.state_var.set(f"TRẠNG THÁI: ĐÃ CHỤP {payload['captured']}/5")
            self.preview_hint.set(f"✓ {POSE_LABELS[pose]} · tiếp theo: {next_pose}")
        else:
            self.pose_var.set("ĐÃ ĐỦ 5 MẪU · ĐANG XÁC MINH")
            self.capture_hint_var.set("Đủ 5 pose · đang kiểm tra embedding và cùng người.")
            self.state_var.set("TRẠNG THÁI: ĐÃ ĐỦ 5 MẪU · ĐANG XÁC MINH")
            self.preview_hint.set("Đang xác minh 5 embedding trước khi cho phép lưu local.")

    def _show_retake_pose(self, payload):
        self.capture_feedback = None
        poses = payload.get("poses", [payload.get("pose")])
        for pose in poses:
            if pose not in POSES:
                continue
            index = POSES.index(pose)
            self.thumb_labels[index].configure(image="", text="—")
            self.thumb_status_labels[index].configure(text="•", fg=DIM)
            self.thumbnail_photos[index] = None
            if pose in self.captured_pose_order:
                self.captured_pose_order.remove(pose)
        self.progress.configure(value=payload.get("captured", 0))
        self.progress_var.set(f"Tiến độ: {payload.get('captured', 0)}/5")
        self.enrollment_progress_var.set(f"Tiến độ: {payload.get('captured', 0)}/5")
        self._update_pose_ring(payload.get("captured", 0), 0)
        pose = payload.get("current_pose")
        if pose in POSES:
            self.pose_var.set(f"Pose yêu cầu: {POSES.index(pose) + 1}/5 · {POSE_LABELS[pose]}")
        self.state_var.set("TRẠNG THÁI: CẦN CHỤP LẠI POSE")
        reason = payload.get("reason") or "Mẫu chưa cùng người; chụp lại pose được đánh dấu."
        self.capture_hint_var.set(
            f"{reason} · tiếp tục theo hướng dẫn AUTO" if self.enrollment.get("mode") == "AUTO"
            else f"{reason} · nhấn SPACE để chụp lại"
        )
        self.preview_hint.set(reason)

    def _retake_pose(self):
        if self.enrollment is None:
            return
        if self.active_operation == "enrollment":
            selected_mode = str(self.enrollment_mode_var.get()).upper()
            self.enrollment["requests"].put({"action": "reset_all", "mode": selected_mode})
            self.state_var.set("TRẠNG THÁI: ĐANG QUÉT LẠI 5 GÓC…")
            return
        if self.enrollment.get("ready_to_save"):
            session = self.enrollment
            for staged in session["stage"].glob("*.jpg"):
                staged.unlink()
            session["state"] = EnrollmentCaptureState()
            session["frames"].clear()
            session["ready_to_save"] = False
            session["mode"] = self.enrollment_mode_var.get()
            session["fallback_reason"] = None
            session["requests"] = queue.Queue()
            self._reset_thumbnails()
            self.progress.configure(value=0)
            self.progress_var.set("Tiến độ: 0/5")
            self.enrollment_progress_var.set("Tiến độ: 0/5")
            self._update_pose_ring(0, 0)
            self.latest_analysis = {}
            self.pose_var.set("Pose yêu cầu: 1/5 · Nhìn thẳng")
            self.auto_status_var.set(
                f"AUTO · frontal · {GUIDED_POSE_STABLE_FRAMES} frame hợp lệ / "
                f"≤{GUIDED_POSE_STABILITY_WINDOW_SECONDS:.0f} giây"
                if session["mode"] == "AUTO"
                else "MANUAL · nhấn SPACE khi quality PASS"
            )
            self._sync_enrollment_start_button()
            token = self._start_session("enrollment", self._enrollment_worker)
            if token is not None:
                session["session_id"] = token
                self.state_var.set("TRẠNG THÁI: QUÉT LẠI 5 GÓC")
            self._set_controls()

    def _show_enrollment_reset(self, payload):
        if self.enrollment is None:
            return
        self.enrollment["ready_to_save"] = False
        self.enrollment["mode"] = payload.get("mode") or self.enrollment.get("mode", "MANUAL")
        self.enrollment["fallback_reason"] = None
        self.enrollment_mode_var.set(self.enrollment["mode"])
        self._sync_enrollment_start_button()
        self._reset_thumbnails()
        self.progress.configure(value=0)
        self.progress_var.set("Tiến độ: 0/5")
        self.enrollment_progress_var.set("Tiến độ: 0/5")
        self._update_pose_ring(0, 0)
        self.latest_analysis = {}
        self.pose_var.set("Pose yêu cầu: 1/5 · Nhìn thẳng")
        mode = self.enrollment["mode"]
        self.capture_hint_var.set(
            "Nhìn thẳng vào camera để hiệu chỉnh frontal." if mode == "AUTO"
            else "Nhìn theo pose yêu cầu; nhấn SPACE khi quality PASS."
        )
        self.auto_status_var.set(
            f"AUTO · frontal · {GUIDED_POSE_STABLE_FRAMES} frame hợp lệ / "
            f"≤{GUIDED_POSE_STABILITY_WINDOW_SECONDS:.0f} giây"
            if mode == "AUTO" else "MANUAL · nhấn SPACE khi quality PASS"
        )
        self.state_var.set("TRẠNG THÁI: ĐÃ RESET · BẮT ĐẦU TỪ FRONTAL")

    def _cancel_enrollment(self):
        if self.enrollment is None:
            return
        if self.active_operation == "enrollment" and self.active_stop_event is not None:
            self.active_stop_event.set()
            self.state_var.set("TRẠNG THÁI: ĐANG HỦY ENROLLMENT…")
            return
        if self.enrollment.get("ready_to_save"):
            shutil.rmtree(self.enrollment["stage"], ignore_errors=True)
        self._discard_enrollment()
        self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ ĐÃ HỦY · GALLERY KHÔNG THAY ĐỔI")
        self._set_controls()

    def _discard_enrollment(self):
        session = self.enrollment
        self.enrollment = None
        self.space_capture_pending = False
        self.space_is_down = False
        if session is not None and not session.get("saved"):
            shutil.rmtree(session["stage"], ignore_errors=True)
        self._reset_thumbnails()
        self.progress.configure(value=0)
        self.progress_var.set("Tiến độ: 0/5")
        self.enrollment_progress_var.set("Tiến độ: 0/5")
        self._update_pose_ring(0, 0)
        self.pose_var.set("Pose yêu cầu: —")
        self.detected_pose_var.set("Pose phát hiện: —")
        self.quality_var.set("Quality: chờ enrollment")
        self.auto_status_var.set("AUTO: chờ bắt đầu")
        self.capture_hint_var.set("Chọn Đăng ký khuôn mặt để bắt đầu.")

    def _reset_thumbnails(self):
        self.thumbnail_photos = [None] * len(POSES)
        self.captured_pose_order = []
        if not hasattr(self, "thumb_labels"):
            return
        for image_label, status_label, cell in zip(
                self.thumb_labels, self.thumb_status_labels, self.thumb_cells):
            image_label.configure(image="", text="—")
            status_label.configure(text="•", fg=DIM)
            cell.configure(bg=PANEL)

    def _update_pose_ring(self, completed, stable_count=0):
        """Draw five segmented pose arcs; the active segment shows auto stability."""
        if not hasattr(self, "pose_ring"):
            return
        canvas = self.pose_ring
        canvas.delete("all")
        center_x, center_y = 39, 39
        box = (9, 9, 69, 69)
        completed = max(0, min(int(completed), len(POSES)))
        stable_count = max(0, min(int(stable_count), GUIDED_POSE_STABLE_FRAMES))
        current_index = completed if completed < len(POSES) else None
        for index in range(len(POSES)):
            start = 90 - index * 72
            canvas.create_arc(box, start=start, extent=58, style=tk.ARC,
                              outline="#30363d", width=7)
            if index < completed:
                color, extent = GREEN, 58
            elif index == current_index and stable_count:
                color = YELLOW
                extent = max(2, 58 * stable_count / GUIDED_POSE_STABLE_FRAMES)
            elif index == current_index:
                color, extent = BLUE, 8
            else:
                continue
            canvas.create_arc(box, start=start, extent=extent, style=tk.ARC,
                              outline=color, width=7)
        canvas.create_text(center_x, center_y - 2, text=f"{completed}/5",
                           fill=TEXT, font=("Segoe UI", 12, "bold"))
        canvas.create_text(center_x, center_y + 14,
                            text=(f"{stable_count}/{GUIDED_POSE_STABLE_FRAMES}"
                                  if current_index is not None else "XONG"),
                           fill=DIM, font=("Segoe UI", 7))

    def _retry_save(self):
        session = self.enrollment
        if session is None or not session.get("ready_to_save"):
            return
        validation = session["state"].validate_complete()
        if not validation["valid"]:
            messagebox.showerror("5 pose chưa nhất quán", validation.get("reason", "Kiểm tra thất bại."),
                                 parent=self.root)
            return
        self.state_var.set("TRẠNG THÁI: ĐANG LƯU 5 MẪU LOCAL…")
        token = self._start_session("save_retry", lambda _token, _stop: self.controller.register_employee(
            session["identity"], session["name"], session["state"].embeddings,
            session["stage"], overwrite=session["overwrite"],
        ))
        if token:
            session["session_id"] = token
            session["ready_to_save"] = False
            self._set_controls()

    def _show_duplicate_face(self, duplicate):
        identity = str(duplicate.get("MaNV", "—"))
        name = str(duplicate.get("HoTen") or identity)
        similarity = float(duplicate.get("similarity", 0.0))
        threshold = float(duplicate.get("threshold", self.controller.threshold))
        detail = (
            "Khuôn mặt đã tồn tại\n"
            f"Employee ID: {identity}\n"
            f"Name: {name}\n"
            f"Similarity: {similarity:.3f}\n"
            f"Threshold: {threshold:.3f}"
        )
        self.state_var.set("TRẠNG THÁI: DUPLICATE FACE")
        self.prediction_var.set(
            f"Khuôn mặt đã tồn tại · Employee: {identity} - {name} · Similarity: {similarity:.3f}"
        )
        self.preview_hint.set(detail.replace("\n", " · "))
        self._set_result_card("KHUÔN MẶT ĐÃ TỒN TẠI", detail, RED, seconds=8.0)
        messagebox.showwarning("Khuôn mặt đã tồn tại", detail, parent=self.root)

    def _enrollment_saved(self, snapshot):
        self.refresh_employee_list(snapshot["employees"])
        self.enrollment = None
        self.progress.configure(value=5)
        self.progress_var.set("Tiến độ: 5/5 · ĐÃ LƯU LOCAL")
        self.pose_var.set("ĐÃ ĐỦ 5 MẪU")
        self.capture_hint_var.set("Đã lưu đủ 5 góc và 5 embedding local.")
        self.state_var.set("TRẠNG THÁI: ĐĂNG KÝ THÀNH CÔNG")
        self.prediction_var.set("KẾT QUẢ: ĐÃ LƯU 5 EMBEDDING")
        self.preview_hint.set("Đã lưu đủ 5 pose và 5 embedding trong ai1_standalone_data.")
        self._set_controls()

    def enrollment_hint_set(self, text):
        self.quality_var.set(f"Quality: {text}")

    def _delete_selected(self):
        selected = self.employee_table.selection()
        if not selected:
            messagebox.showinfo("Chọn nhân viên", "Chọn nhân viên trong danh sách local.",
                                parent=self.root)
            return
        identity = selected[0]
        if not messagebox.askyesno("Xóa dữ liệu standalone",
                                   f"Xóa vĩnh viễn {identity} khỏi ai1_standalone_data trên máy này?",
                                   parent=self.root):
            return
        self.state_var.set(f"TRẠNG THÁI: ĐANG XÓA {identity} KHỎI KHO LOCAL…")
        self._start_job("delete_employee",
                        lambda: self.controller.delete_employee(identity, confirmed=True))

    def _set_result_card(self, title, detail, tone=YELLOW, seconds=None):
        """Keep session state visibly over the live preview, independent of camera frames."""
        self.result_title_var.set(str(title))
        self.result_detail_var.set(str(detail))
        backgrounds = {
            GREEN: ("#13281d", "#3fb950"),
            RED: ("#32191c", "#ff6b6b"),
            YELLOW: ("#302817", "#e3b341"),
            BLUE: ("#17212b", "#79c0ff"),
        }
        background, foreground = backgrounds.get(tone, backgrounds[YELLOW])
        if hasattr(self, "result_card"):
            self.result_card.configure(bg=background, highlightbackground=foreground)
            self.result_title_label.configure(bg=background, fg=foreground)
            self.result_detail_label.configure(bg=background, fg=TEXT)
            self.result_card.place(relx=0.5, y=14, anchor="n", relwidth=0.88)
            self.result_card.lift()
        self.result_card_until = time.monotonic() + float(seconds) if seconds else 0.0

    def _expire_result_card(self):
        if not self.result_card_until or time.monotonic() < self.result_card_until:
            return
        if hasattr(self, "result_card"):
            self.result_card.place_forget()
        self.result_card_until = 0.0
        if (self.active_operation is None
                and self.last_result_status in {"MATCH", "UNKNOWN", "RETRY"}):
            self.state_var.set("TRẠNG THÁI: READY")
            self.prediction_var.set("KẾT QUẢ: —")
            self.preview_hint.set("Camera sẵn sàng cho phiên tiếp theo.")
        self.last_result_status = None

    def _recognize(self):
        if self.enrollment is not None:
            messagebox.showinfo("Đang enrollment", "Hoàn tất hoặc hủy enrollment trước.", parent=self.root)
            return
        self.best_result_frame = None
        self.best_frame_until = 0.0
        self.last_result_status = None
        self.result_card_until = 0.0
        self.latest_analysis = {}
        self.state_var.set("TRẠNG THÁI: ĐANG QUÉT KHUÔN MẶT")
        self.prediction_var.set("KẾT QUẢ: ĐANG LẤY 3 SNAPSHOT MỚI")
        self.score_var.set("Similarity: —")
        self.sharpness_var.set("Sharpness: —")
        self.latency_var.set("Latency: —")
        self.progress_var.set("Snapshot: 0/3")
        self.preview_hint.set("ĐANG QUÉT KHUÔN MẶT · 0/3")
        self._set_result_card("ĐANG QUÉT KHUÔN MẶT", "Đang lấy 3 snapshot mới · 0/3", YELLOW)

        gallery = self.controller.gallery
        if not any(person.get("embeddings") for person in gallery.values()):
            self._show_recognition({
                "status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": self.controller.threshold, "reason": "EMPTY GALLERY — Chưa có dữ liệu khuôn mặt standalone.",
                "latency_ms": 0.0, "captured_frames": 0,
            })
            return

        def run(token, stop_event):
            return self.controller.recognize(
                stop_event,
                progress_callback=lambda count, total: self.events.put(
                    ("recognition_progress", token, (count, total))
                ),
                session_id=token,
                frame_callback=lambda analysis: self.events.put(
                    ("recognition_frame", token, analysis)
                ),
            )
        if self._start_session("recognition", run) is None:
            self._show_recognition({
                "status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                "threshold": self.controller.threshold,
                "reason": "SESSION ACTIVE — Một phiên AI1 khác đang chạy.",
                "latency_ms": 0.0, "captured_frames": 0,
            })

    def _show_recognition(self, result):
        status = str(result.get("status", "RETRY")).upper()
        self.last_result_status = status
        score = float(result.get("score", 0.0))
        threshold = float(result.get("threshold", self.controller.threshold))
        latency = float(result.get("latency_ms", 0.0))
        self.threshold_var.set(f"Threshold: {threshold:.3f}")
        self.score_var.set(f"Similarity: {score:.3f}")
        self.latency_var.set(f"Latency: {latency:.1f} ms")
        self.sharpness_var.set(f"Sharpness: {float(result.get('sharpness', 0.0)):.1f}")
        self.progress_var.set(f"Snapshot: {result.get('captured_frames', 3)}/3")
        if status == "MATCH":
            identity = result["predicted_id"]
            employee = next((person for person in self.controller.employees
                             if person["MaNV"] == identity), None)
            name = employee["HoTen"] if employee else identity
            self.state_var.set("KẾT QUẢ: MATCH")
            self.prediction_var.set(
                f"Employee: {identity} - {name} · Similarity: {score:.3f} · Threshold: {threshold:.3f}"
            )
            self.preview_hint.set(
                f"KẾT QUẢ: MATCH · Employee: {identity} - {name} · "
                f"Similarity: {score:.3f} · Threshold: {threshold:.3f}"
            )
            self._set_result_card(
                "MATCH",
                f"Employee ID: {identity}\nName: {name}\n"
                f"Similarity: {score:.3f}\nThreshold: {threshold:.3f}",
                GREEN, seconds=7.0,
            )
        elif status == "UNKNOWN":
            self.state_var.set("KẾT QUẢ: UNKNOWN")
            self.prediction_var.set(
                f"Best similarity: {score:.3f} · Threshold: {threshold:.3f}"
            )
            self.preview_hint.set(
                f"KẾT QUẢ: UNKNOWN · Best similarity: {score:.3f} · Threshold: {threshold:.3f}"
            )
            self._set_result_card(
                "UNKNOWN",
                f"Không tìm thấy nhân viên phù hợp.\nBest similarity: {score:.3f}\n"
                f"Threshold: {threshold:.3f}",
                YELLOW, seconds=7.0,
            )
        else:
            reason = str(result.get("reason", "Không đủ snapshot hợp lệ."))
            self.state_var.set("KẾT QUẢ: RETRY")
            self.prediction_var.set(f"RETRY: {reason}")
            self.preview_hint.set(reason)
            self._set_result_card("RETRY", f"Reason: {reason}", RED, seconds=7.0)
        best_frame = result.get("best_frame")
        if isinstance(best_frame, np.ndarray) and best_frame.size:
            overlay = best_frame.copy()
            bbox = result.get("bbox")
            color = (60, 220, 90) if status == "MATCH" else (40, 50, 240)
            if bbox and len(bbox) == 4:
                x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
            label = result["predicted_id"] if status == "MATCH" else status
            cv2.putText(overlay, str(label), (14, 34), cv2.FONT_HERSHEY_SIMPLEX,
                        0.85, color, 2, cv2.LINE_AA)
            self.best_result_frame = overlay
            self.best_frame_until = time.monotonic() + 4.0
        else:
            self.best_result_frame = None
            self.best_frame_until = 0.0

    def _draw_preview(self, frame, packet):
        image = frame.copy()
        height, width = image.shape[:2]
        analysis = self.latest_analysis
        enrollment_visual = bool(
            self.enrollment is not None
            and (self.active_operation == "enrollment" or self.enrollment.get("ready_to_save"))
        )
        overlay_active = self.active_operation == "recognition" or enrollment_visual
        observed_at = analysis.get("observed_at")
        analysis_fresh = (isinstance(observed_at, (int, float))
                          and 0 <= time.monotonic() - observed_at <= 0.75)
        text_runs = []

        # The static oval is only a composition guide. AUTO's scanning ring is
        # drawn independently around the live SCRFD bounding box below.
        if enrollment_visual and self.enrollment.get("mode", "MANUAL") != "AUTO":
            center = (width // 2, int(height * 0.51))
            axes = (int(min(height * 0.72, width * 0.86) * 0.78 / 2),
                    int(min(height * 0.72, width * 0.86) / 2))
            cv2.ellipse(image, center, axes, 0, 0, 360, (92, 102, 116), 1, cv2.LINE_AA)

        if overlay_active and analysis_fresh:
            try:
                boxes = analysis.get("bboxes") or ([analysis["bbox"]] if analysis.get("bbox") else [])
                source_shape = analysis.get("frame_shape") or (height, width)
                source_height, source_width = int(source_shape[0]), int(source_shape[1])
                if boxes and source_width > 0 and source_height > 0:
                    scale_x, scale_y = width / source_width, height / source_height
                    quality_pass = analysis.get("quality_status") in {"PASS", "READY"}
                    color_hex = analysis.get("color", GREEN if quality_pass else RED)
                    color = {GREEN: (50, 200, 90), YELLOW: (0, 210, 255), RED: (45, 55, 245)}.get(
                        color_hex,
                        (50, 200, 90) if quality_pass else (45, 55, 245),
                    )
                    scores = analysis.get("detection_scores") or [analysis.get("detection_score")]
                    for index, box in enumerate(boxes):
                        x1, y1, x2, y2 = [float(value) for value in box]
                        x1, x2 = int(round(x1 * scale_x)), int(round(x2 * scale_x))
                        y1, y2 = int(round(y1 * scale_y)), int(round(y2 * scale_y))
                        x1, x2 = max(0, min(width - 1, x1)), max(0, min(width - 1, x2))
                        y1, y2 = max(0, min(height - 1, y1)), max(0, min(height - 1, y2))
                        if x2 <= x1 or y2 <= y1:
                            continue
                        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                        score = scores[index] if index < len(scores) else None
                        score_text = f"{float(score):.2f}" if score is not None else "—"
                        label = f"SCRFD {index + 1}: {score_text}"
                        cv2.putText(image, label, (max(4, x1), max(20, y1 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
                    if enrollment_visual and self.enrollment.get("mode") == "AUTO" and len(boxes) == 1:
                        box = boxes[0]
                        x1, y1, x2, y2 = [float(value) for value in box]
                        x1, x2 = int(x1 * scale_x), int(x2 * scale_x)
                        y1, y2 = int(y1 * scale_y), int(y2 * scale_y)
                        face_width, face_height = max(1, x2 - x1), max(1, y2 - y1)
                        ring_center = ((x1 + x2) // 2, (y1 + y2) // 2)
                        ring_axes = (max(28, int(face_width * 0.68)),
                                     max(32, int(face_height * 0.66)))
                        cv2.ellipse(image, ring_center, ring_axes, 0, 0, 360,
                                    (90, 95, 105), 2, cv2.LINE_AA)
                        auto_status = analysis.get("auto_status")
                        stable = max(0, min(int(analysis.get("stable_count", 0) or 0),
                                            GUIDED_POSE_STABLE_FRAMES))
                        if auto_status == "CAPTURE_PENDING":
                            stable = GUIDED_POSE_STABLE_FRAMES
                        sweep = int(360 * stable / GUIDED_POSE_STABLE_FRAMES)
                        expected = analysis.get("expected_pose")
                        detected = analysis.get("detected_pose")
                        quality_pass = analysis.get("quality_status") == "PASS"
                        ring_color = ((50, 210, 95) if quality_pass and detected == expected
                                      else (0, 200, 255))
                        if sweep:
                            cv2.ellipse(image, ring_center, ring_axes, 0, -90, -90 + sweep,
                                        ring_color, 3, cv2.LINE_AA)
            except (TypeError, ValueError, IndexError):
                pass

        if enrollment_visual:
            debug = analysis.get("diagnostics") or {}

            def number(value, digits=1, signed=False):
                if value is None:
                    return "—"
                try:
                    return f"{float(value):+.{digits}f}" if signed else f"{float(value):.{digits}f}"
                except (TypeError, ValueError):
                    return "—"

            bbox = debug.get("bbox")
            bbox_text = "—" if not bbox else ",".join(str(int(round(float(v)))) for v in bbox)
            width_ratio = debug.get("bbox_width_frame_ratio")
            height_ratio = debug.get("bbox_height_frame_ratio")
            offset_x = debug.get("center_offset_x_px")
            offset_y = debug.get("center_offset_y_px")
            offset_x_pct = debug.get("center_offset_x_ratio")
            offset_y_pct = debug.get("center_offset_y_ratio")
            yaw, pitch = debug.get("raw_yaw", debug.get("yaw")), debug.get("raw_pitch", debug.get("pitch"))
            detected = analysis.get("detected_pose") or debug.get("detected_pose", "—")
            raw_detected = analysis.get("raw_detected_pose") or debug.get("raw_pose_classification") or detected
            expected = analysis.get("expected_pose") or debug.get("expected_pose", "—")
            quality_result = debug.get("quality_result", analysis.get("quality_status", "—"))
            quality_code = debug.get("quality_code", analysis.get("code", "—"))
            face_count = debug.get("face_count")
            reason = str(analysis.get("reason") or analysis.get("code") or "—")
            reason = reason.replace("\n", " ")[:76]
            mode = analysis.get("mode", self.enrollment.get("mode", "MANUAL")
                                if self.enrollment is not None else "MANUAL")
            calibrated_yaw = analysis.get("calibrated_yaw")
            calibrated_pitch = analysis.get("calibrated_pitch")
            reprojection = analysis.get("reprojection_error_px", debug.get("reprojection_error_px"))
            stable_count = analysis.get("stable_count", 0)
            frontal_view = analysis.get("frontal_view") or {}
            if mode == "AUTO" and analysis.get("calibrating") and frontal_view:
                frontal_text = (
                    f"Front check: {'PASS' if analysis.get('frontal_ok') else 'FAIL'} · "
                    f"yaw {number(frontal_view.get('raw_yaw'), 1, True)}° · "
                    f"eye span {number(frontal_view.get('eye_span_face_height'), 2)}h · "
                    f"nose offset {number(frontal_view.get('nose_offset_face_width'), 2)}w"
                )
            elif mode == "AUTO" and analysis.get("calibrating"):
                frontal_text = "Front check: đang xác minh hướng mặt từ landmark SCRFD"
            else:
                frontal_text = None
            if mode == "AUTO":
                capture_instruction = (f"AUTO: gom frame {stable_count}/{GUIDED_POSE_STABLE_FRAMES}"
                                       if not analysis.get("calibrating") else
                                       f"Hiệu chỉnh frontal {stable_count}/{GUIDED_POSE_STABLE_FRAMES}")
            else:
                fallback_reason = analysis.get("fallback_reason") or (
                    self.enrollment.get("fallback_reason") if self.enrollment else None
                )
                capture_instruction = (f"MANUAL FALLBACK: {fallback_reason}"
                                       if fallback_reason else "MANUAL: nhấn SPACE khi quality PASS")
            pose_line = (f"Raw pose: {raw_detected} | Calibrated pose: {detected} | Expected: {expected}"
                         if mode == "AUTO" else
                         f"Raw pose: {raw_detected} | Expected: {expected}")
            angle_text = (
                "đang hiệu chỉnh frontal · góc tương đối chưa có"
                if mode == "AUTO" and analysis.get("calibrating")
                and calibrated_yaw is None and calibrated_pitch is None
                else f"{number(calibrated_yaw, 1, True)}° / {number(calibrated_pitch, 1, True)}°"
            )
            lines = [
                f"Det: {number(debug.get('detection_score'), 2)} | Faces: {face_count if face_count is not None else '—'} | BBox: {bbox_text}",
                f"BBox/frame: W {number(None if width_ratio is None else width_ratio * 100)}%  H {number(None if height_ratio is None else height_ratio * 100)}%",
                f"Center offset: X {number(offset_x, 1, True)}px ({number(None if offset_x_pct is None else offset_x_pct * 100, 1, True)}%)  Y {number(offset_y, 1, True)}px ({number(None if offset_y_pct is None else offset_y_pct * 100, 1, True)}%)",
                f"Brightness: {number(debug.get('brightness'))} | Laplacian: {number(debug.get('sharpness'))}",
                f"Raw yaw: {number(yaw, 1, True)}° | Raw pitch: {number(pitch, 1, True)}°",
                *([frontal_text] if frontal_text else []),
                pose_line,
                f"Yaw/pitch đã hiệu chỉnh: {angle_text} | Reproject: {number(reprojection, 1)}px",
                f"Quality: {quality_result} | Code: {quality_code}",
                f"Inference: {number(analysis.get('inference_fps'), 1)} FPS | "
                f"Frame hợp lệ: {stable_count}/{GUIDED_POSE_STABLE_FRAMES} | "
                f"Còn: {number(analysis.get('time_remaining_seconds'), 0)}s | {capture_instruction}",
                f"Reason: {reason}",
            ]
            font_size = 11
            line_height = 16
            panel_width = width - 16
            panel_height = len(lines) * line_height + 12
            panel_x, panel_y = 8, max(42, height - panel_height - 8)
            shade = image.copy()
            cv2.rectangle(shade, (panel_x, panel_y),
                          (panel_x + panel_width, panel_y + panel_height), (13, 17, 23), -1)
            image = cv2.addWeighted(shade, 0.78, image, 0.22, 0.0)
            for index, line in enumerate(lines):
                text_runs.append((line, panel_x + 8, panel_y + 5 + index * line_height,
                                  (236, 239, 244), font_size))

            if mode == "AUTO":
                short_labels = ("Nhìn thẳng", "Trái", "Phải", "Ngẩng", "Cúi")
                captured_poses = set(getattr(self, "captured_pose_order", ()))
                expected_pose = analysis.get("expected_pose")
                detected_pose = analysis.get("detected_pose")
                quality_pass = analysis.get("quality_status") == "PASS"
                gap = 4
                chip_width = max(58, (width - 16 - gap * 4) // 5)
                for index, pose_name in enumerate(POSES):
                    x = 8 + index * (chip_width + gap)
                    if pose_name in captured_poses:
                        bgr, rgb_text = (35, 115, 55), (245, 255, 245)
                    elif pose_name == expected_pose and detected_pose == expected_pose and quality_pass:
                        bgr, rgb_text = (0, 145, 175), (255, 255, 245)
                    elif pose_name == expected_pose:
                        bgr, rgb_text = (50, 78, 112), (255, 255, 245)
                    else:
                        bgr, rgb_text = (44, 49, 57), (195, 201, 210)
                    cv2.rectangle(image, (x, 45), (x + chip_width, 69), bgr, -1)
                    text_runs.append((short_labels[index], x + 5, 49, rgb_text, 11))

        if self.active_operation == "recognition":
            text_runs.append((self.progress_var.get(), 14, 12, (255, 220, 0), 16))
        elif enrollment_visual:
            if self.enrollment.get("mode") == "AUTO":
                prompt = f"QUÉT TỰ ĐỘNG  ·  {self.progress_var.get()}"
                prompt_color = (110, 235, 145)
            else:
                prompt = f"MANUAL · NHẤN SPACE  ·  {self.progress_var.get()}"
                prompt_color = (255, 220, 0)
            text_runs.append((prompt, 14, 12, prompt_color, 16))
        if text_runs:
            image = _draw_unicode_runs(image, text_runs)
        return image

    def _update_preview(self):
        if self.closing:
            return
        self._expire_result_card()
        packet = self.controller.get_packet()
        frame = packet.frame if packet is not None else None
        if frame is not None:
            self.current_packet = packet
            source_height, source_width = frame.shape[:2]
            aspect = source_width / max(1, source_height)
            if (getattr(self, "_preview_size", None) is None
                    or abs(getattr(self, "_preview_aspect", 0.0) - aspect) > 0.01):
                self._resize_preview()
            if self.best_result_frame is not None and time.monotonic() < self.best_frame_until:
                display = self.best_result_frame.copy()
            else:
                if self.best_result_frame is not None:
                    self.best_result_frame = None
                display = self._draw_preview(frame, packet)
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            width, height = getattr(self, "_preview_size", (640, 480))
            contained = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
            canvas_image = Image.new("RGB", (width, height), (5, 7, 10))
            canvas_image.paste(contained, ((width - contained.width) // 2,
                                           (height - contained.height) // 2))
            photo = ImageTk.PhotoImage(canvas_image)
            self.current_photo = photo
            self.preview.configure(image=photo, text="")
        elif self.controller.ready and self.active_operation is None:
            self.preview.configure(image="", text="Chưa có frame mới từ camera.")
            self.current_photo = None
        self.root.after(33, self._update_preview)

    def _on_close(self):
        if self.closing:
            return
        self.closing = True
        self.close_event.set()
        if self.active_stop_event is not None:
            self.active_stop_event.set()
        session = self.enrollment
        worker = self.worker_thread

        def cleanup():
            if worker is not None and worker.is_alive():
                worker.join()
            if session is not None and not session.get("saved"):
                shutil.rmtree(session["stage"], ignore_errors=True)
            try:
                self.controller.release()
            except Exception:
                pass

        threading.Thread(target=cleanup, name="ai1-gui-close-cleanup", daemon=True).start()
        self.root.destroy()
