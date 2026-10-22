'''
gui_register.py -- Giao dien GUI Dang ky Khuon mat Nhan vien
'''

from __future__ import annotations

import sys
import os
import logging
from src.runtime_config import load_environment

load_environment()
from typing import Optional, List
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import cv2
from src.camera_source import open_camera
import numpy as np
from PIL import Image, ImageTk
from PIL.Image import Resampling

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / 'src'
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.face_engine import FaceEngine
from src.registration_capture import assess_frame, render_guide, capture_sample

logger = logging.getLogger(__name__)

CAPTURE_STEPS = [
    {'name': 'Nhìn thẳng', 'hint': 'Nhin thang vao camera', 'display': 'Nhìn thẳng', 'instruction': 'nhìn thẳng vào camera'},
    {'name': 'Xoay trái', 'hint': 'Xoay mat sang TRAI nhe', 'display': 'Xoay trái', 'instruction': 'xoay mặt nhẹ sang trái'},
    {'name': 'Xoay phải', 'hint': 'Xoay mat sang PHAI nhe', 'display': 'Xoay phải', 'instruction': 'xoay mặt nhẹ sang phải'},
    {'name': 'Ngẩng lên', 'hint': 'Ngang mat LEN nhe', 'display': 'Ngẩng lên', 'instruction': 'ngẩng mặt nhẹ lên'},
    {'name': 'Cúi xuống', 'hint': 'Cui mat XUONG nhe', 'display': 'Cúi xuống', 'instruction': 'cúi mặt nhẹ xuống'},
]
READY_FRAMES = 8

DARK_BG = '#0d1117'; PANEL_BG = '#161b22'; CARD_BG = '#1c2128'
ACCENT = '#238636'; ACCENT2 = '#1f6feb'; TEXT_MAIN = '#e6edf3'
TEXT_DIM = '#8b949e'; RED_ALERT = '#da3633'; YELLOW = '#d29922'
FONT_MAIN = ('Segoe UI', 10); FONT_BOLD = ('Segoe UI', 10, 'bold')
FONT_TITLE = ('Segoe UI', 14, 'bold'); FONT_SMALL = ('Segoe UI', 9)


class RegisterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PBL4 - Đăng ký khuôn mặt nhân viên')
        self.geometry('1180x760')
        self.minsize(1000, 700)
        self.configure(bg=DARK_BG)
        self.engine: Optional[FaceEngine] = None
        self.engine_loading: bool = True
        self.cap: Optional[cv2.VideoCapture] = None
        self.running: bool = True
        self.current_step: int = 0
        self.embeddings_collected: List[np.ndarray] = []
        self._current_photo: Optional[ImageTk.PhotoImage] = None
        self.ready_timer = 0
        self.flash_timer = 0
        self.is_capturing = False
        self.capture_done = False
        from src.desktop_enrollment import DesktopEnrollment
        from src.ui_worker import UiWorker
        self.store = DesktopEnrollment()
        self.io = UiWorker(self)
        self.sync_busy = False
        self.employees = {}
        self.pending_by_employee = {}
        self.registration_job = None
        self.registration_conflict = False
        self.pending_action = None
        self.last_frame_time = None
        self.camera_ready = False
        self.samples_collected = []
        self.sample_busy = False
        self.session_token = 0
        self._sample_photos = []
        self._thumbnail_widgets = []
        self._sample_crops = []
        self.frame_timer = None
        self._canvas_image = None
        self._camera_notice = None
        self._build_ui()
        self._load_engine_async()
        self._open_webcam()
        self._poll_frame()
        self._load_employees()
        from src.desktop_lifecycle import install_close_listener
        install_close_listener(self, lambda: self.on_close(from_dashboard=True))

    def _build_ui(self):
        hdr = tk.Frame(self, bg=PANEL_BG, height=56)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='Đăng ký khuôn mặt', font=FONT_TITLE,
                 bg=PANEL_BG, fg=TEXT_MAIN).pack(side='left', padx=20, pady=12)
        tk.Label(hdr, text='1. Thông tin  →  2. Thu 5 mẫu  →  3. Kiểm tra và lưu', font=FONT_SMALL,
                 bg=PANEL_BG, fg=TEXT_DIM).pack(side='left', padx=5)

        main = tk.Frame(self, bg=DARK_BG)
        main.pack(fill='both', expand=True, padx=12, pady=10)

        left = tk.Frame(main, bg=DARK_BG)
        left.pack(side='left', fill='both', expand=True)

        self.cam_canvas = tk.Canvas(left, bg='#000000', cursor='crosshair',
                                    highlightthickness=2, highlightbackground=ACCENT2)
        self.cam_canvas.pack(fill='both', expand=True, pady=(0, 8))

        self.preview_hint = tk.StringVar(value='Đặt khuôn mặt vào khung oval • Đỏ: chưa hợp lệ • Xanh: sẵn sàng')
        tk.Label(left, textvariable=self.preview_hint, bg=DARK_BG, fg=TEXT_MAIN,
                 font=FONT_MAIN, anchor='w', wraplength=680).pack(fill='x', pady=(0, 8))

        self.step_frame = tk.Frame(left, bg=DARK_BG)
        self.step_frame.pack(fill='x')
        self._build_step_indicators()
        self.thumbnail_frame = tk.Frame(left, bg=DARK_BG)
        self.thumbnail_frame.pack(fill='x', pady=(8, 0))
        for index, step in enumerate(CAPTURE_STEPS):
            cell = tk.Frame(self.thumbnail_frame, bg=CARD_BG, padx=4, pady=4)
            cell.grid(row=0, column=index, sticky='nsew', padx=3)
            self.thumbnail_frame.columnconfigure(index, weight=1)
            label = tk.Label(cell, text=f'{index + 1}', bg=PANEL_BG, fg=TEXT_DIM,
                             width=12, height=4, font=FONT_BOLD)
            label.pack(fill='both', expand=True)
            tk.Label(cell, text=step['name'], font=FONT_SMALL, bg=CARD_BG,
                     fg=TEXT_DIM).pack(pady=(4, 0))
            self._thumbnail_widgets.append(label)

        right = tk.Frame(main, bg=DARK_BG, width=365)
        right.pack(side='right', fill='y', padx=(12, 0))
        right.pack_propagate(False)

        self._build_info_card(right)
        self._build_control_card(right)
        self._build_list_card(right)

        self.status_var = tk.StringVar(value='Đang chuẩn bị camera và tải danh sách nhân viên…')
        tk.Label(self, textvariable=self.status_var, font=FONT_SMALL,
                 bg=PANEL_BG, fg=YELLOW, anchor='w', padx=12, pady=6).pack(fill='x', side='bottom')

    def _build_step_indicators(self):
        for w in self.step_frame.winfo_children():
            w.destroy()
        cols = tk.Frame(self.step_frame, bg=DARK_BG)
        cols.pack()
        for i, step in enumerate(CAPTURE_STEPS):
            color = ACCENT if i < self.current_step else (ACCENT2 if i == self.current_step else CARD_BG)
            fg = TEXT_MAIN if i <= self.current_step else TEXT_DIM
            cell = tk.Frame(cols, bg=color, padx=10, pady=5)
            cell.pack(side='left', padx=3)
            tk.Label(cell, text=step['name'], font=FONT_SMALL, bg=color, fg=fg).pack()

    def _build_info_card(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=14, pady=12)
        card.pack(fill='x', pady=(0, 8))
        tk.Label(card, text='1. Chọn nhân viên', font=FONT_BOLD,
                 bg=CARD_BG, fg=ACCENT2).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        self.id_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.employee_var = tk.StringVar()
        self.employee_combo = ttk.Combobox(card, textvariable=self.employee_var,
                                          state='readonly', font=FONT_MAIN, width=30)
        self.employee_combo.grid(row=1, column=0, columnspan=2, sticky='ew', pady=4)
        self.employee_combo.bind('<<ComboboxSelected>>', self._select_employee)
        tk.Label(card, text='ID / Mã số', bg=CARD_BG, fg=TEXT_DIM, font=FONT_SMALL).grid(
            row=2, column=0, sticky='w', pady=(8, 2))
        ttk.Entry(card, textvariable=self.id_var, state='readonly', font=FONT_MAIN, width=11).grid(
            row=3, column=0, sticky='ew', padx=(0, 8))
        tk.Label(card, text='Họ và tên', bg=CARD_BG, fg=TEXT_DIM, font=FONT_SMALL).grid(
            row=2, column=1, sticky='w', pady=(8, 2))
        ttk.Entry(card, textvariable=self.name_var, state='readonly', font=FONT_MAIN, width=24).grid(
            row=3, column=1, sticky='ew')
        self.employee_note = tk.StringVar(value='Đang tải nhân viên từ hệ thống…')
        tk.Label(card, textvariable=self.employee_note, font=FONT_SMALL, bg=CARD_BG,
                 fg=TEXT_DIM, wraplength=325, justify='left').grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        tk.Button(card, text='Quản lý / thêm nhân viên trên Web', command=self._open_employee_web,
                  font=FONT_SMALL, bg=CARD_BG, fg=ACCENT2, relief='flat', cursor='hand2').grid(row=5, column=0, columnspan=2, sticky='w')
        self.n_samples_var = tk.IntVar(value=5)
        card.columnconfigure(0, weight=0)
        card.columnconfigure(1, weight=1)

    def _build_control_card(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=14, pady=12)
        card.pack(fill='x', pady=(0, 8))
        tk.Label(card, text='2. Chụp và đăng ký', font=FONT_BOLD, bg=CARD_BG, fg=ACCENT2).pack(anchor='w', pady=(0, 8))
        self.hint_var = tk.StringVar(value='Chọn nhân viên, bấm Bắt đầu chụp và làm theo hướng dẫn từng góc mặt.')
        tk.Label(card, textvariable=self.hint_var, font=FONT_MAIN, bg=CARD_BG, fg=YELLOW,
                 wraplength=325, justify='left').pack(anchor='w', pady=(0, 8))
        self.progress_var = tk.DoubleVar(value=0.0)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('green.Horizontal.TProgressbar', troughcolor=PANEL_BG, background=ACCENT, thickness=12)
        style.configure('Treeview', background=CARD_BG, foreground=TEXT_MAIN, fieldbackground=CARD_BG, rowheight=24)
        style.configure('Treeview.Heading', background=PANEL_BG, foreground=TEXT_DIM, font=FONT_SMALL)
        style.map('Treeview', background=[('selected', ACCENT2)])
        ttk.Progressbar(card, variable=self.progress_var, maximum=100,
                        style='green.Horizontal.TProgressbar').pack(fill='x', pady=(0, 8))
        self.count_var = tk.StringVar(value='Đã chụp: 0/5 mẫu')
        tk.Label(card, textvariable=self.count_var, font=FONT_BOLD, bg=CARD_BG,
                 fg=TEXT_MAIN).pack(anchor='w')
        self.conf_var = tk.StringVar(value='Mỗi mẫu gồm một ảnh gốc và một vector 512 chiều.')
        tk.Label(card, textvariable=self.conf_var, font=FONT_SMALL, bg=CARD_BG, fg=TEXT_DIM).pack(anchor='w')
        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.pack(fill='x', pady=(10, 0))
        self.btn_start = tk.Button(btn_frame, text='Bắt đầu chụp', font=FONT_BOLD,
                                   bg=ACCENT, fg='white', relief='flat', bd=0,
                                   padx=14, pady=8, cursor='hand2', command=self._start_register)
        self.btn_start.pack(fill='x', pady=(0, 5))
        secondary = tk.Frame(btn_frame, bg=CARD_BG)
        secondary.pack(fill='x', pady=(0, 5))
        self.btn_capture = tk.Button(secondary, text='Chụp (Space)', font=FONT_SMALL,
                                     bg=ACCENT2, fg='white', relief='flat', bd=0,
                                     padx=14, pady=8, cursor='hand2',
                                     command=self._manual_capture, state='disabled')
        self.btn_capture.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.btn_save = tk.Button(btn_frame, text='Lưu / Trích xuất Embedding', font=FONT_BOLD,
                                  bg=ACCENT, fg='white', relief='flat', bd=0,
                                  padx=10, pady=8, cursor='hand2', state='disabled',
                                  command=self._save_registration)
        self.btn_save.pack(fill='x', pady=(0, 5))
        self.btn_reset = tk.Button(secondary, text='Chụp lại / Reset', font=FONT_SMALL, bg='#30363d', fg=TEXT_DIM,
                  relief='flat', bd=0, padx=14, pady=6, cursor='hand2',
                  command=self._reset_session)
        self.btn_reset.pack(side='left', fill='x', expand=True)
        self.bind('<space>', lambda e: self._manual_capture())
        self.bind('<Escape>', lambda e: self._reset_session())

    def _build_list_card(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=14, pady=12)
        card.pack(fill='both', expand=True)
        hdr = tk.Frame(card, bg=CARD_BG)
        hdr.pack(fill='x', pady=(0, 6))
        tk.Label(hdr, text='Nhân viên trên hệ thống', font=FONT_BOLD, bg=CARD_BG, fg=ACCENT2).pack(side='left')
        self.btn_refresh = tk.Button(hdr, text='Tải lại', font=FONT_SMALL, bg=CARD_BG, fg=TEXT_DIM,
                  relief='flat', bd=0, cursor='hand2', command=self._load_employees)
        self.btn_refresh.pack(side='right')
        cols = ('ID', 'Ten', 'TinhTrang')
        self.tree = ttk.Treeview(card, columns=cols, show='headings', height=2, selectmode='browse')
        for col, label in zip(cols, ('Mã', 'Họ tên', 'Khuôn mặt')):
            self.tree.heading(col, text=label)
        self.tree.column('ID', width=60, stretch=False); self.tree.column('Ten', width=130); self.tree.column('TinhTrang', width=85, stretch=False)
        self.tree.pack(fill='both', expand=True, pady=(0, 6))
        self.tree.bind('<<TreeviewSelect>>', self._select_employee_row)

    def _load_engine_async(self):
        def loaded(engine):
            self.engine = engine
            self.engine_loading = False
            self._update_controls()
        def failed(error):
            self.engine_loading = False
            self.status_var.set('Không tải được InsightFace. Kiểm tra môi trường/model.')
        self.btn_start.configure(state='disabled')
        self.io.submit(lambda: FaceEngine(model_name='buffalo_sc'), loaded, failed)

    def _open_webcam(self):
        from src.camera_source import FramePump
        self.pump = FramePump(lambda: open_camera(0), lambda: self.engine)

    def _poll_frame(self):
        if not self.running:
            return
        was_ready = self.camera_ready
        try:
            frame, faces, captured_at = self.pump.snapshot_with_timestamp()
            self.camera_ready = frame is not None
            if frame is not None:
                if captured_at != self.last_frame_time:
                    self.last_frame_time = captured_at
                    self._show_frame(self._process_frame(frame, faces))
            else:
                self.ready_timer = 0
                self.progress_var.set(len(getattr(self, 'samples_collected', [])) * 20)
                if self.is_capturing:
                    self.hint_var.set('Đang kết nối lại camera… Giữ cửa sổ mở để tiếp tục chụp.')
                if self._canvas_image is not None:
                    self.cam_canvas.itemconfigure(self._canvas_image, image='')
                    self._current_photo = None
                if getattr(self, '_camera_notice', False) is None:
                    self._camera_notice = self.cam_canvas.create_text(20, 35, anchor='nw',
                        text='Đang kết nối camera…', fill=TEXT_MAIN, font=FONT_TITLE)
        except Exception:
            logger.exception('Registration preview failed')
            self.camera_ready = False
            self.ready_timer = 0
            if self.is_capturing:
                self.hint_var.set('Camera đang gặp lỗi. Chưa chụp thêm ảnh; hãy thử lại.')
        if was_ready != self.camera_ready:
            update_controls = getattr(self, '_update_controls', None)
            if callable(update_controls):
                update_controls()
        self.frame_timer = self.after(33, self._poll_frame)

    def _process_frame(self, frame, faces):
        from src.enrollment_pose import POSES
        expected_pose = POSES[self.current_step] if self.is_capturing and self.current_step < 5 else None
        readiness = assess_frame(frame, faces, expected_pose)
        if self.engine is None or self.engine_loading:
            self.preview_hint.set('Đang tải InsightFace. Camera vẫn hiển thị trong lúc chuẩn bị model.')
        elif self.is_capturing and self.current_step < 5:
            step = CAPTURE_STEPS[self.current_step]
            self.preview_hint.set(f'Mẫu {self.current_step + 1}/5 · {step["display"]} · {readiness.message}')
            if readiness.ready and not self.sample_busy and self.flash_timer <= 0:
                self.ready_timer += 1
            elif not readiness.ready:
                self.ready_timer = 0
            ratio = min(self.ready_timer / READY_FRAMES, 1.)
            self.hint_var.set(f'{step["display"]}\n{readiness.message}' +
                              (f' ({int(ratio * 100)}%)' if readiness.ready else ''))
            if ratio >= 1. and not self.sample_busy:
                self._do_capture(frame, faces)
        else:
            self.ready_timer = 0
            self.preview_hint.set('Đã đủ 5 mẫu. Kiểm tra ảnh và bấm Lưu / Trích xuất Embedding.'
                                  if self.capture_done else readiness.message)
        if self.flash_timer > 0:
            self.flash_timer -= 1
        step_text = (f'Sample {self.current_step + 1}/5: {CAPTURE_STEPS[self.current_step]["hint"]}'
                     if self.is_capturing and self.current_step < 5 else
                     f'Collected: {self.current_step}/5 | Face registration')
        return render_guide(frame, faces, readiness, step_text,
                            min(self.ready_timer / READY_FRAMES, 1.))

    def _show_frame(self, frame):
        cw, ch = self.cam_canvas.winfo_width(), self.cam_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        if self._camera_notice is not None:
            self.cam_canvas.delete(self._camera_notice)
            self._camera_notice = None
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image.thumbnail((cw, ch), Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        if self._canvas_image is None:
            self._canvas_image = self.cam_canvas.create_image(cw // 2, ch // 2, anchor='center', image=photo)
        else:
            self.cam_canvas.coords(self._canvas_image, cw // 2, ch // 2)
            self.cam_canvas.itemconfigure(self._canvas_image, image=photo)
        self._current_photo = photo

    def _refresh_thumbnails(self):
        self._sample_photos = []
        for index, label in enumerate(self._thumbnail_widgets):
            if index < len(self._sample_crops):
                image = Image.fromarray(cv2.cvtColor(self._sample_crops[index], cv2.COLOR_BGR2RGB))
                image.thumbnail((96, 78), Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self._sample_photos.append(photo)
                label.configure(image=photo, text='', width=96, height=78)
            else:
                label.configure(image='', text=str(index + 1), width=12, height=4)
        self.count_var.set(f'Đã chụp: {self.current_step}/5 mẫu')

    def _start_register(self):
        if self.sync_busy or self.is_capturing:
            return
        selected = self.employees.get(self.employee_var.get())
        if selected is None:
            messagebox.showwarning('Chọn nhân viên', 'Chọn nhân viên cần đăng ký trong danh sách.')
            return
        if self.engine is None:
            messagebox.showwarning('Đang chuẩn bị', 'Đợi bộ nhận diện khuôn mặt sẵn sàng rồi đăng ký.')
            return
        if self.registration_job or (self.capture_done and self.samples_collected):
            self._save_registration()
            return
        self.sync_busy = True
        self._update_controls()
        self.hint_var.set('Đang kiểm tra nhân viên và kết nối hệ thống…')
        identity = selected['id']
        def work():
            self.store.refresh()
            official = next((person for person in self.store.employees() if person['id'] == identity), None)
            if official is None:
                raise ValueError('Nhân viên không còn trong hệ thống. Hãy tải lại danh sách.')
            pending = next((job for _, job in self.store.pending() if job['employee_id'] == identity), None)
            return official, pending, self.store.revision(identity)
        def checked(result):
            self.sync_busy = False
            official, pending, revision = result
            self.id_var.set(f'SV{official["id"]:03d}')
            self.name_var.set(official['name'])
            # Keep the displayed canonical record synchronized with preflight.
            self.employees[self.employee_var.get()] = official
            if pending:
                if pending['action'] != 'replace':
                    self.hint_var.set('Nhân viên đang có yêu cầu xóa khuôn mặt chưa hoàn tất. Hãy kiểm tra trên Web trước khi đăng ký.')
                    self.pending_action = pending['action']
                    self._update_controls()
                    return
                self.registration_job = pending['id']
                self._save_registration()
                return
            if not self.camera_ready:
                self.hint_var.set('Chưa nhận được hình từ camera. Đợi camera kết nối rồi bấm Đăng ký khuôn mặt.')
                self._update_controls()
                return
            if official['n_images'] and not messagebox.askyesno('Đăng ký lại khuôn mặt',
                    f'{official["name"]} đã có khuôn mặt đăng ký.\nChụp 5 ảnh mới để thay bộ ảnh hiện tại?', parent=self):
                self._update_controls()
                return
            self.enrollment_revision = revision
            self._begin_capture()
        def failed(error):
            self.sync_busy = False
            self.hint_var.set('Chưa bắt đầu đăng ký. Không kết nối được hệ thống hoặc nhân viên đã thay đổi. Hãy tải lại danh sách.')
            self._update_controls()
        self.io.submit(work, checked, failed)

    def _begin_capture(self):
        self.session_token += 1
        self._sample_crops.clear()
        self.current_step = 0; self.embeddings_collected.clear(); self.samples_collected.clear()
        self.ready_timer = 0; self.flash_timer = 0
        self.is_capturing = True; self.capture_done = False; self.progress_var.set(0)
        self._update_controls()
        self.hint_var.set('Góc 1/5: Nhìn thẳng. Giữ mặt trong khung hình; camera sẽ tự chụp.')
        self.status_var.set(f'Đang đăng ký cho {self.id_var.get()} — {self.name_var.get()}')
        self._build_step_indicators()
        self._refresh_thumbnails()

    def _do_capture(self, frame, faces):
        if self.current_step >= 5 or self.capture_done or not self.is_capturing or self.sample_busy:
            return
        from src.enrollment_pose import POSES
        pose = POSES[self.current_step]
        readiness = assess_frame(frame, faces, pose)
        if not readiness.ready:
            self.ready_timer = 0
            self.hint_var.set(readiness.message)
            return
        token = self.session_token
        reference = self.samples_collected[0]['vector'] if self.samples_collected else None
        self.sample_busy = True
        self._update_controls()
        def captured(result):
            if token != self.session_token:
                return
            self.sample_busy = False
            sample, crop = result
            self.samples_collected.append(sample)
            self.embeddings_collected.append(sample['vector'])
            self._sample_crops.append(crop)
            self.current_step += 1
            self.ready_timer = 0
            self.flash_timer = 8
            self.progress_var.set(self.current_step * 20)
            self._build_step_indicators()
            self._refresh_thumbnails()
            self.conf_var.set(f'Đã xác thực {self.current_step}/5 cặp ảnh / embedding cùng người.')
            if self.current_step == 5:
                self._finalize_registration()
            self._update_controls()
        def failed(error):
            if token != self.session_token:
                return
            self.sample_busy = False
            self.ready_timer = 0
            self.hint_var.set('Mẫu chưa hợp lệ: chỉ một mặt, đúng hướng, rõ nét và cùng người với mẫu đầu.')
            self._update_controls()
        self.io.submit(lambda: capture_sample(frame, faces, pose, reference), captured, failed)

    def _manual_capture(self):
        if not self.is_capturing or self.capture_done or self.flash_timer > 0 or self.sample_busy:
            return
        if self.current_step == 5:
            self._finalize_registration()
            return
        frame, faces = self.pump.snapshot()
        if frame is not None:
            self._do_capture(frame, faces)

    def _finalize_registration(self):
        self.capture_done = True
        self.is_capturing = False
        self.progress_var.set(100)
        self.hint_var.set('Đã đủ 5 mẫu. Kiểm tra các ảnh bên dưới và bấm Lưu / Trích xuất Embedding.')
        self.status_var.set('Chưa lưu đăng ký. Bạn có thể kiểm tra mẫu hoặc Chụp lại từ đầu.')
        self._update_controls()

    def _save_registration(self):
        if self.sync_busy or self.is_capturing or getattr(self, 'sample_busy', False):
            return
        selected = self.employees.get(self.employee_var.get())
        valid_identity = (selected is not None and self.id_var.get().strip() == f'SV{selected["id"]:03d}'
                          and self.name_var.get().strip() == selected['name'].strip()
                          and bool(self.name_var.get().strip()))
        if not valid_identity or self.pending_action == 'delete':
            messagebox.showwarning('Thông tin chưa hợp lệ', 'Chọn đúng nhân viên có đầy đủ ID và họ tên trước khi lưu.', parent=self)
            return
        if not self.registration_job and (not self.capture_done or len(self.samples_collected) != 5):
            messagebox.showwarning('Chưa đủ mẫu', 'Thu thập đủ 5 góc mặt trước khi lưu đăng ký.', parent=self)
            return
        self.sync_busy = True
        self._update_controls()
        self.hint_var.set('Đã chụp đủ 5 góc. Đang lưu đăng ký vào hệ thống…')
        self.status_var.set('Đang lưu khuôn mặt; vui lòng giữ cửa sổ mở.')
        sid, name = self.id_var.get(), self.name_var.get()
        samples = list(self.samples_collected)
        revision = getattr(self, 'enrollment_revision', None)
        def work():
            if not self.registration_job:
                self.registration_job = self.store.stage(sid, name, samples, revision)
            from src.face_sync import employee_id
            job = next((job for _, job in self.store.pending() if job['id'] == self.registration_job), None)
            if job is None or job['action'] != 'replace' or job['employee_id'] != employee_id(sid):
                raise ValueError('Không phải phiên đăng ký khuôn mặt của nhân viên đang chọn.')
            result = self.store.retry(job_id=self.registration_job)
            return result['jobs'].get(self.registration_job, 'pending')
        def finished(state):
            self.sync_busy = False
            self._update_controls()
            if state == 'completed':
                self.registration_job = None
                self.samples_collected.clear()
                self.embeddings_collected.clear()
                self.progress_var.set(100)
                self.hint_var.set(f'Đăng ký thành công!\n{name} đã có thể chấm công bằng khuôn mặt.')
                self.status_var.set(f'Đã lưu 5 ảnh khuôn mặt của {sid} vào hệ thống và cập nhật nhận diện.')
                self.conf_var.set('Đã lưu vào hệ thống ✓')
                self._update_controls()
                messagebox.showinfo('Đăng ký thành công', f'Đã đăng ký khuôn mặt cho {name} ({sid}).\nBạn có thể mở Chấm công để sử dụng.', parent=self)
                self._load_employees(keep_message=True)
            else:
                self.conf_var.set('Chưa hoàn tất đăng ký')
                if state == 'saved':
                    message = 'Khuôn mặt đã lưu trên hệ thống, nhưng chưa cập nhật được bộ nhận diện. Bấm Hoàn tất đăng ký để thử lại.'
                elif state == 'conflict':
                    self.registration_conflict = True
                    message = 'Khuôn mặt trên hệ thống đã thay đổi trong lúc chụp. Bấm Chụp lại từ đầu để đăng ký lại; bộ ảnh vừa chụp vẫn được giữ.'
                else:
                    message = 'Chưa lưu được đăng ký vào hệ thống. Ảnh đã chụp được giữ lại. Kiểm tra kết nối rồi bấm Hoàn tất đăng ký.'
                self.hint_var.set(message)
                self.status_var.set(message)
                self._update_controls()
        def failed(error):
            self.sync_busy = False
            self.hint_var.set('Chưa hoàn tất đăng ký. Ảnh đã chụp được giữ lại; bấm Lưu lại đăng ký để thử lại.')
            self.status_var.set('Chưa xác nhận lưu thành công. Dữ liệu đăng ký cũ được giữ nguyên.')
            self._update_controls()
        self.io.submit(work, finished, failed)

    def _update_controls(self):
        busy = self.sync_busy or self.is_capturing or self.sample_busy
        person = self.employees.get(self.employee_var.get())
        selected = (person is not None and self.id_var.get().strip() == f'SV{person["id"]:03d}'
                    and self.name_var.get().strip() == person['name'].strip()
                    and bool(self.name_var.get().strip()))
        blocked = self.pending_action == 'delete' or self.registration_conflict
        unsaved_complete = self.capture_done and len(self.samples_collected) == 5
        self.btn_start.configure(state='normal' if self.engine and selected and self.camera_ready and
                                 not busy and not blocked and not self.registration_job and not unsaved_complete else 'disabled',
                                 text='Bắt đầu chụp')
        pending = self.pending_by_employee.get(person['id']) if person else None
        durable_complete = bool(self.registration_job and pending and len(pending.get('samples', [])) == 5)
        self.btn_save.configure(state='normal' if selected and not busy and not blocked and
                                (unsaved_complete or durable_complete) else 'disabled',
                                text='Hoàn tất đăng ký' if self.registration_job else 'Lưu / Trích xuất Embedding')
        self.btn_capture.configure(state='normal' if self.is_capturing and not self.capture_done and
                                   not self.sample_busy else 'disabled')
        unsaved = bool(self.samples_collected) and not self.registration_job and self.capture_done
        self.employee_combo.configure(state='disabled' if busy or unsaved else 'readonly')
        self.btn_refresh.configure(state='disabled' if busy or unsaved else 'normal')
        self.btn_reset.configure(state='disabled' if self.sync_busy or (self.registration_job and not self.registration_conflict) else 'normal')

    @staticmethod
    def _open_employee_web():
        import webbrowser
        webbrowser.open('http://localhost:8080/?action=index')

    def _load_employees(self, keep_message=False):
        if self.sync_busy or self.is_capturing:
            return
        self.sync_busy = True
        self._update_controls()
        previous = self.id_var.get()
        def work():
            self.store.refresh()
            return self.store.employees(), [job for _, job in self.store.pending()]
        def loaded(result):
            self.sync_busy = False
            people, pending = result
            self.employees = {f'SV{person["id"]:03d} — {person["name"]}': person for person in people}
            self.pending_by_employee = {job['employee_id']: job for job in pending}
            self.employee_combo.configure(values=list(self.employees))
            choice = next((label for label, person in self.employees.items() if f'SV{person["id"]:03d}' == previous), '')
            self.employee_var.set(choice)
            self._select_employee(keep_message=keep_message)
            self._refresh_list()
            if not people:
                self.employee_note.set('Chưa có nhân viên. Mở Web để thêm nhân viên trước khi đăng ký.')
            if not keep_message:
                self.status_var.set('Chọn nhân viên, chụp đủ 5 góc mặt, kiểm tra ảnh rồi bấm Lưu / Trích xuất Embedding.')
            self._update_controls()
        def failed(error):
            self.sync_busy = False
            self.employees = {}
            self.employee_combo.configure(values=[])
            self.employee_note.set('Không tải được nhân viên. Kiểm tra Web / cơ sở dữ liệu rồi bấm Tải lại.')
            self.status_var.set('Chưa kết nối được hệ thống; chưa bắt đầu đăng ký.')
            self._update_controls()
        self.io.submit(work, loaded, failed)

    def _select_employee(self, event=None, keep_message=False):
        if self.is_capturing or self.sync_busy or self.sample_busy:
            return
        person = self.employees.get(self.employee_var.get())
        self.registration_conflict = False
        if person is None:
            self.id_var.set('')
            self.name_var.set('')
            self.employee_note.set('Chọn đúng người trong danh sách. Tên được lấy từ hồ sơ nhân viên.')
            self.registration_job = None
            self.pending_action = None
        else:
            self.id_var.set(f'SV{person["id"]:03d}')
            self.name_var.set(person['name'])
            pending = self.pending_by_employee.get(person['id'])
            self.pending_action = pending['action'] if pending else None
            self.registration_job = pending['id'] if pending and pending['action'] == 'replace' else None
            note = ('Đang có yêu cầu xóa khuôn mặt chưa hoàn tất. Hãy kiểm tra trên Web trước khi đăng ký.' if self.pending_action == 'delete' else
                    'Có đăng ký chưa hoàn tất. Bấm Hoàn tất đăng ký để tiếp tục.' if pending else
                    f'Đã có {person["n_images"]} ảnh. Đăng ký lại sẽ thay bộ ảnh khuôn mặt.' if person['n_images'] else
                    'Chưa đăng ký khuôn mặt. Sẵn sàng chụp 5 góc.')
            self.employee_note.set(note)
        if not keep_message:
            self.current_step = 0
            self.capture_done = False
            self.samples_collected.clear()
            self.embeddings_collected.clear()
            self._sample_crops.clear()
            self.session_token += 1
            self.progress_var.set(0)
            self.conf_var.set('')
            self.hint_var.set('Bấm Hoàn tất đăng ký để tiếp tục lưu.' if self.registration_job else
                              'Bấm Bắt đầu chụp. Camera tự chụp khi khuôn mặt đúng vị trí, đủ rõ và đúng góc.')
            self._build_step_indicators()
            self._refresh_thumbnails()
        if self.registration_job:
            self._restore_pending_preview(self.pending_by_employee.get(person['id']))
        self._update_controls()

    def _restore_pending_preview(self, pending):
        """Show the five durable samples before an operator retries a write."""
        if not pending or len(pending.get('samples', [])) != 5:
            return
        from src.registration_capture import restore_pending_samples
        token = self.session_token
        def loaded(result):
            if token != self.session_token:
                return
            self.samples_collected, self._sample_crops = result
            self.embeddings_collected = [sample['vector'] for sample in self.samples_collected]
            self.current_step = 5
            self.capture_done = True
            self.progress_var.set(100)
            self._refresh_thumbnails()
            self._build_step_indicators()
            self._update_controls()
        def failed(error):
            if token == self.session_token:
                self.hint_var.set('Batch đăng ký chờ không đọc được. Dữ liệu vẫn được giữ để kiểm tra.')
        self.io.submit(lambda: restore_pending_samples(pending['samples']), loaded, failed)

    def _select_employee_row(self, event=None):
        if self.sync_busy or self.is_capturing or (self.samples_collected and not self.registration_job):
            return
        selection = self.tree.selection()
        if not selection:
            return
        sid = str(self.tree.item(selection[0])['values'][0])
        choice = next((label for label, person in self.employees.items() if f'SV{person["id"]:03d}' == sid), None)
        if choice:
            self.employee_var.set(choice)
            self._select_employee()

    def _reset_session(self):
        if self.sync_busy:
            return
        if self.registration_job:
            if not self.registration_conflict:
                return
            if not messagebox.askyesno('Chụp lại đăng ký',
                    'Giữ bộ ảnh vừa chụp trong bản lưu và bắt đầu đăng ký lại theo dữ liệu mới nhất trên hệ thống?', parent=self):
                return
            self.sync_busy = True
            self._update_controls()
            identity, job_id = self.id_var.get(), self.registration_job
            def archive():
                from src.face_sync import employee_id
                jobs = [job for _, job in self.store.pending() if job['employee_id'] == employee_id(identity)]
                if len(jobs) != 1 or jobs[0]['id'] != job_id or jobs[0]['action'] != 'replace' or jobs[0]['db_saved']:
                    raise ValueError('Trạng thái đăng ký đã thay đổi; giữ nguyên ảnh để kiểm tra.')
                return self.store.archive(identity)
            def archived(result):
                self.sync_busy = False
                self.registration_job = None
                self.registration_conflict = False
                self.samples_collected.clear()
                self.embeddings_collected.clear()
                self._reset_session()
                self._load_employees()
            def failed(error):
                self.sync_busy = False
                self.hint_var.set('Chưa bắt đầu chụp lại. Dữ liệu đang được giữ nguyên; hãy tải lại hoặc kiểm tra trên Web.')
                self._update_controls()
            self.io.submit(archive, archived, failed)
            return
        if self.samples_collected and not messagebox.askyesno('Chụp lại từ đầu',
                'Bỏ các ảnh vừa chụp chưa lưu để chụp lại 5 góc?', parent=self):
            return
        self.session_token += 1
        self.sample_busy = False
        self.current_step = 0
        self.embeddings_collected.clear()
        self.samples_collected.clear()
        self._sample_crops.clear()
        self.ready_timer = 0
        self.flash_timer = 0
        self.is_capturing = False
        self.capture_done = False
        self.progress_var.set(0)
        self.conf_var.set('')
        self.hint_var.set('Bấm Bắt đầu chụp để thu lại đủ 5 góc mặt.')
        self._update_controls()
        self._build_step_indicators()
        self._refresh_thumbnails()

    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for person in self.employees.values():
            self.tree.insert('', 'end', values=(f'SV{person["id"]:03d}', person['name'],
                             'Đã đăng ký' if person['n_images'] == 5 else 'Cần bổ sung' if person['n_images'] else 'Chưa có'))

    def on_close(self, from_dashboard=False):
        if not self.running:
            return
        if self.sync_busy:
            if from_dashboard:
                self.status_var.set('Đang hoàn tất thao tác lưu trước khi chuyển module…')
                self.after(150, lambda: self.on_close(from_dashboard=True))
                return
            messagebox.showinfo('Đang xử lý', 'Đang kết nối hoặc lưu đăng ký. Vui lòng đợi hoàn tất trước khi đóng.', parent=self)
            return
        if not from_dashboard and self.samples_collected and not self.registration_job and not messagebox.askyesno(
                'Chưa hoàn tất đăng ký', 'Ảnh vừa chụp chưa được lưu. Đóng cửa sổ và bỏ các ảnh này?', parent=self):
            return
        self.running = False
        if self.frame_timer:
            self.after_cancel(self.frame_timer)
        self.pump.close()
        self.io.close()
        self.status_var.set('Đang giải phóng camera…')
        self._finish_close()

    def _finish_close(self):
        # Never join a camera read on Tk's event loop. FramePump releases the
        # device in its finally block, then this process can safely exit.
        if self.pump.thread.is_alive():
            self.after(40, self._finish_close)
            return
        self.destroy()


if __name__ == '__main__':
    app = RegisterApp()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()
