'''
gui_register.py -- Giao dien GUI Dang ky Khuon mat Nhan vien
'''

from __future__ import annotations

import sys
import os
from src.runtime_config import load_environment

load_environment()
import time
import threading
from typing import Optional, List, Dict, Any
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import cv2
from src.camera_source import open_camera
import numpy as np
import pickle
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

EMBEDDINGS_PATH = CURRENT_DIR / 'data' / 'embeddings.pkl'
REGISTERED_DIR  = CURRENT_DIR / 'data' / 'registered'

CAPTURE_STEPS = [
    {'name': 'Nhin thang', 'hint': 'Nhin thang vao camera'},
    {'name': 'Xoay trai',  'hint': 'Xoay mat sang TRAI nhe'},
    {'name': 'Xoay phai',  'hint': 'Xoay mat sang PHAI nhe'},
    {'name': 'Ngang len',  'hint': 'Ngang mat LEN nhe'},
    {'name': 'Cui xuong',  'hint': 'Cui mat XUONG nhe'},
]
READY_FRAMES = 35

DARK_BG = '#0d1117'; PANEL_BG = '#161b22'; CARD_BG = '#1c2128'
ACCENT = '#238636'; ACCENT2 = '#1f6feb'; TEXT_MAIN = '#e6edf3'
TEXT_DIM = '#8b949e'; RED_ALERT = '#da3633'; YELLOW = '#d29922'
FONT_MAIN = ('Segoe UI', 10); FONT_BOLD = ('Segoe UI', 10, 'bold')
FONT_TITLE = ('Segoe UI', 14, 'bold'); FONT_SMALL = ('Segoe UI', 9)


def load_db():
    if EMBEDDINGS_PATH.exists():
        with open(EMBEDDINGS_PATH, 'rb') as f:
            return pickle.load(f)
    return {}

class RegisterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PBL4 - Dang ky Khuon mat Nhan vien')
        self.geometry('1200x750')
        self.minsize(1000, 650)
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
        self.samples_collected = []
        self.frame_timer = None
        self._canvas_image = None
        self._build_ui()
        self._load_engine_async()
        self._open_webcam()
        self._poll_frame()
        self._refresh_from_web()

    def _build_ui(self):
        hdr = tk.Frame(self, bg=PANEL_BG, height=56)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='PBL4 Face Registration', font=FONT_TITLE,
                 bg=PANEL_BG, fg=TEXT_MAIN).pack(side='left', padx=20, pady=12)
        tk.Label(hdr, text='He thong Cham cong Thong minh', font=FONT_SMALL,
                 bg=PANEL_BG, fg=TEXT_DIM).pack(side='left', padx=5)

        main = tk.Frame(self, bg=DARK_BG)
        main.pack(fill='both', expand=True, padx=12, pady=10)

        left = tk.Frame(main, bg=DARK_BG)
        left.pack(side='left', fill='both', expand=True)

        self.cam_canvas = tk.Canvas(left, bg='#000000', cursor='crosshair',
                                    highlightthickness=2, highlightbackground=ACCENT2)
        self.cam_canvas.pack(fill='both', expand=True, pady=(0, 8))

        self.step_frame = tk.Frame(left, bg=DARK_BG)
        self.step_frame.pack(fill='x')
        self._build_step_indicators()

        right = tk.Frame(main, bg=DARK_BG, width=340)
        right.pack(side='right', fill='y', padx=(12, 0))
        right.pack_propagate(False)

        self._build_info_card(right)
        self._build_control_card(right)
        self._build_list_card(right)

        self.status_var = tk.StringVar(value='Dang tai mo hinh InsightFace...')
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
        tk.Label(card, text='Thong tin Nhan vien', font=FONT_BOLD,
                 bg=CARD_BG, fg=ACCENT2).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        tk.Label(card, text='Student ID:', font=FONT_MAIN, bg=CARD_BG, fg=TEXT_DIM).grid(row=1, column=0, sticky='w', pady=3)
        self.id_var = tk.StringVar()
        self.id_entry = tk.Entry(card, textvariable=self.id_var, font=FONT_MAIN,
                                  bg='#21262d', fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                                  relief='flat', bd=6, width=20)
        self.id_entry.grid(row=1, column=1, sticky='ew', padx=(8, 0))
        tk.Label(card, text='Ten nhan vien:', font=FONT_MAIN, bg=CARD_BG, fg=TEXT_DIM).grid(row=2, column=0, sticky='w', pady=3)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(card, textvariable=self.name_var, font=FONT_MAIN,
                                    bg='#21262d', fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                                    relief='flat', bd=6, width=20)
        self.name_entry.grid(row=2, column=1, sticky='ew', padx=(8, 0))
        tk.Label(card, text='So anh:', font=FONT_MAIN, bg=CARD_BG, fg=TEXT_DIM).grid(row=3, column=0, sticky='w', pady=3)
        self.n_samples_var = tk.IntVar(value=5)
        tk.Spinbox(card, from_=5, to=5, state='disabled', textvariable=self.n_samples_var, font=FONT_MAIN,
                   bg='#21262d', fg=TEXT_MAIN, relief='flat', bd=4, width=5).grid(row=3, column=1, sticky='w', padx=(8,0))
        card.columnconfigure(1, weight=1)

    def _build_control_card(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=14, pady=12)
        card.pack(fill='x', pady=(0, 8))
        tk.Label(card, text='Dieu khien', font=FONT_BOLD, bg=CARD_BG, fg=ACCENT2).pack(anchor='w', pady=(0, 8))
        self.hint_var = tk.StringVar(value='Nhap thong tin va nhan [Bat dau Dang ky]')
        tk.Label(card, textvariable=self.hint_var, font=FONT_MAIN, bg=CARD_BG, fg=YELLOW,
                 wraplength=290, justify='left').pack(anchor='w', pady=(0, 8))
        self.progress_var = tk.DoubleVar(value=0.0)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('green.Horizontal.TProgressbar', troughcolor=PANEL_BG, background=ACCENT, thickness=12)
        style.configure('Treeview', background=CARD_BG, foreground=TEXT_MAIN, fieldbackground=CARD_BG, rowheight=24)
        style.configure('Treeview.Heading', background=PANEL_BG, foreground=TEXT_DIM, font=FONT_SMALL)
        style.map('Treeview', background=[('selected', ACCENT2)])
        ttk.Progressbar(card, variable=self.progress_var, maximum=100,
                        style='green.Horizontal.TProgressbar').pack(fill='x', pady=(0, 8))
        self.conf_var = tk.StringVar(value='')
        tk.Label(card, textvariable=self.conf_var, font=FONT_SMALL, bg=CARD_BG, fg=TEXT_DIM).pack(anchor='w')
        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.pack(fill='x', pady=(10, 0))
        self.btn_start = tk.Button(btn_frame, text='Bat dau Dang ky', font=FONT_BOLD,
                                   bg=ACCENT, fg='white', relief='flat', bd=0,
                                   padx=14, pady=8, cursor='hand2', command=self._start_register)
        self.btn_start.pack(fill='x', pady=(0, 5))
        self.btn_capture = tk.Button(btn_frame, text='Chup ngay (SPACE)', font=FONT_BOLD,
                                     bg=ACCENT2, fg='white', relief='flat', bd=0,
                                     padx=14, pady=8, cursor='hand2',
                                     command=self._manual_capture, state='disabled')
        self.btn_capture.pack(fill='x', pady=(0, 5))
        tk.Button(btn_frame, text='Reset / Huy', font=FONT_MAIN, bg='#30363d', fg=TEXT_DIM,
                  relief='flat', bd=0, padx=14, pady=6, cursor='hand2',
                  command=self._reset_session).pack(fill='x')
        tk.Button(btn_frame, text='Thử đồng bộ batch chờ', command=self._retry_sync,
                  bg=ACCENT2, fg='white').pack(fill='x', pady=5)
        tk.Button(btn_frame, text='Lưu trữ batch chờ của ID này', command=self._archive_pending,
                  bg='#30363d', fg=TEXT_DIM).pack(fill='x', pady=5)
        self.bind('<space>', lambda e: self._manual_capture())

    def _build_list_card(self, parent):
        card = tk.Frame(parent, bg=CARD_BG, padx=14, pady=12)
        card.pack(fill='both', expand=True)
        hdr = tk.Frame(card, bg=CARD_BG)
        hdr.pack(fill='x', pady=(0, 6))
        tk.Label(hdr, text='Da dang ky', font=FONT_BOLD, bg=CARD_BG, fg=ACCENT2).pack(side='left')
        tk.Button(hdr, text='Xoa tat ca', font=FONT_SMALL, bg=RED_ALERT, fg='white',
                  relief='flat', bd=0, cursor='hand2', padx=6, command=self._delete_all).pack(side='right', padx=(0, 4))
        tk.Button(hdr, text='Lam moi', font=FONT_SMALL, bg=CARD_BG, fg=TEXT_DIM,
                  relief='flat', bd=0, cursor='hand2', command=self._refresh_from_web).pack(side='right')
        cols = ('ID', 'Ten', 'Anh')
        self.tree = ttk.Treeview(card, columns=cols, show='headings', height=8, selectmode='browse')
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column('ID', width=80); self.tree.column('Ten', width=120); self.tree.column('Anh', width=50)
        self.tree.pack(fill='both', expand=True, pady=(0, 6))
        tk.Button(card, text='Xoa nguoi da chon', font=FONT_SMALL, bg='#30363d', fg=TEXT_DIM,
                  relief='flat', bd=0, padx=10, pady=5, cursor='hand2',
                  command=self._delete_selected).pack(fill='x')
        self._refresh_list()

    def _load_engine_async(self):
        def loaded(engine):
            self.engine = engine
            self.engine_loading = False
            self.btn_start.configure(state='disabled' if self.sync_busy else 'normal')
            self.status_var.set('InsightFace sẵn sàng; gallery chỉ chứa dữ liệu DB đã xác nhận.')
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
        try:
            frame, faces = self.pump.snapshot()
            if frame is not None:
                self._show_frame(self._process_frame(frame, faces))
            else:
                self.ready_timer = 0
                self.progress_var.set(0)
                self.hint_var.set('Chưa có frame mới. Kiểm tra camera relay hoặc chọn local khi service đã dừng.')
                if self._canvas_image is not None:
                    self.cam_canvas.itemconfigure(self._canvas_image, image='')
                    self._current_photo = None
        except Exception:
            self.ready_timer = 0
            self.hint_var.set('Không xử lý được frame. Kiểm tra camera/model.')
        self.frame_timer = self.after(33, self._poll_frame)

    def _process_frame(self, frame, faces):
        vis = frame.copy()
        h, w = frame.shape[:2]
        if self.engine is None or self.engine_loading:
            cv2.putText(vis, 'Dang tai InsightFace...', (30, h//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 215, 255), 2)
            return vis
        if not self.is_capturing or self.capture_done or self.current_step >= 5:
            cv2.putText(vis, 'Nhan [Bat dau Dang ky] de bat dau', (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
            return vis
        from src.enrollment_pose import POSES, estimate_pose, check_pose_match
        has_face = False
        if len(faces) == 1:
            try:
                detected, metrics = estimate_pose(faces[0].kps)
                has_face = check_pose_match(POSES[self.current_step], detected, metrics)
            except (ValueError, TypeError):
                pass
        step_info = CAPTURE_STEPS[self.current_step % len(CAPTURE_STEPS)]
        step_hint = step_info['hint']
        for face in faces:
            x1, y1, x2, y2 = [int(v) for v in face.bbox]
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 220, 100), 2)
            if face.kps is not None:
                for kp in face.kps:
                    cv2.circle(vis, (int(kp[0]), int(kp[1])), 3, (0, 100, 255), -1)
        overlay = vis.copy()
        cv2.rectangle(overlay, (0, 0), (w, 90), (15, 15, 30), -1)
        vis = cv2.addWeighted(overlay, 0.75, vis, 0.25, 0)
        n_samples = self.n_samples_var.get()
        cv2.putText(vis, f'Buoc {self.current_step+1}/{n_samples}', (15, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
        sid = self.id_var.get().strip(); sname = self.name_var.get().strip()
        cv2.putText(vis, f'ID: {sid} | {sname}', (15, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        hint_text = f'>> {step_hint} <<'
        (tw, _), _ = cv2.getTextSize(hint_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.putText(vis, hint_text, ((w-tw)//2, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 200), 2)
        if has_face:
            self.ready_timer += 1
            ratio = min(self.ready_timer / READY_FRAMES, 1.0)
            bar_w = int((w - 40) * ratio)
            cv2.rectangle(vis, (20, h-48), (20+bar_w, h-34), (0, 220, 100), -1)
            cv2.rectangle(vis, (20, h-48), (w-20, h-34), (80, 80, 80), 1)
            self.progress_var.set(ratio * 100)
            cv2.putText(vis, f'Dang nhan dien... {int(ratio*100)}%', (20, h-56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 100), 1)
            self.hint_var.set(f'Phat hien mat - {int(ratio*100)}%\n{step_hint}')
            if ratio >= 1.0 and self.flash_timer <= 0:
                self._do_capture(frame, faces)
        else:
            self.ready_timer = 0; self.progress_var.set(0)
            self.hint_var.set(f'Khong thay mat!\n{step_hint}')
            cv2.putText(vis, 'Khong thay mat - hay dua mat vao camera',
                        (20, h-56), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1)
        cv2.putText(vis, 'SPACE=chup  |  ESC=huy', (20, h-14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1)
        if self.flash_timer > 0:
            flash_ov = vis.copy()
            cv2.rectangle(flash_ov, (0, 0), (w, h), (0, 255, 100), -1)
            alpha = self.flash_timer / 12.0
            vis = cv2.addWeighted(flash_ov, alpha*0.3, vis, 1-alpha*0.3, 0)
            done = f'OK! Buoc {self.current_step}/{n_samples}'
            (tw2, _), _ = cv2.getTextSize(done, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
            cv2.putText(vis, done, ((w-tw2)//2, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 100), 3)
            self.flash_timer -= 1
        return vis

    def _show_frame(self, frame):
        cw = self.cam_canvas.winfo_width(); ch = self.cam_canvas.winfo_height()
        if cw < 10 or ch < 10: return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(frame_rgb).resize((cw, ch), Resampling.LANCZOS)
        img_tk = ImageTk.PhotoImage(img_pil)
        if self._canvas_image is None:
            self._canvas_image = self.cam_canvas.create_image(0, 0, anchor='nw', image=img_tk)
        else:
            self.cam_canvas.itemconfigure(self._canvas_image, image=img_tk)
        self._current_photo = img_tk

    def _start_register(self):
        if self.sync_busy or self.is_capturing:
            return
        sid = self.id_var.get().strip(); sname = self.name_var.get().strip()
        from src.face_sync import employee_id
        try:
            sid = f'SV{employee_id(sid):03d}'
            self.id_var.set(sid)
        except ValueError:
            messagebox.showwarning('ID', 'Use a positive numeric ID, SV001 or NV001'); return
        if not sid:
            messagebox.showwarning('Thieu thong tin', 'Vui long nhap Student ID!'); return
        if not sname:
            messagebox.showwarning('Thieu thong tin', 'Vui long nhap ten nhan vien!'); return
        if self.engine is None:
            messagebox.showerror('Loi', 'Mo hinh InsightFace chua san sang!'); return
        try:
            self.enrollment_revision = self.store.revision(sid)
        except Exception:
            messagebox.showerror('Đồng bộ', 'Làm mới gallery từ DB trước khi bắt đầu đăng ký.')
            return
        db = load_db()
        if sid in db:
            _msg = "Student ID '" + sid + "' da duoc dang ky (" + db[sid]['name'] + ").\nBan co muon ghi de khong?"
            if not messagebox.askyesno('ID da ton tai', _msg): return
        self.current_step = 0; self.embeddings_collected.clear(); self.samples_collected.clear()
        self.ready_timer = 0; self.flash_timer = 0
        self.is_capturing = True; self.capture_done = False; self.progress_var.set(0)
        self.btn_start.configure(state='disabled'); self.btn_capture.configure(state='normal')
        self.id_entry.configure(state='disabled'); self.name_entry.configure(state='disabled')
        self.hint_var.set(f'Bat dau! Giu mat nhin thang ({self.n_samples_var.get()} buoc)\nDua mat vao camera...')
        self.status_var.set(f'Dang thu thap anh: {sid} - {sname}')
        self._build_step_indicators()

    def _do_capture(self, frame, faces):
        if self.current_step >= 5 or self.capture_done:
            return
        from src.enrollment_pose import POSES
        from src.enrollment_samples import sample_from_frame
        try:
            sample = sample_from_frame(frame, faces, POSES[self.current_step],
                self.samples_collected[0]['vector'] if self.samples_collected else None)
        except (ValueError, TypeError):
            self.ready_timer = 0
            self.hint_var.set('Mẫu chưa hợp lệ: chỉ một mặt, đúng hướng và cùng người với mẫu đầu.')
            return
        self.samples_collected.append(sample)
        self.embeddings_collected.append(sample['vector'])
        self.current_step += 1
        self.ready_timer = 0
        self.flash_timer = 12
        self.progress_var.set(0)
        self._build_step_indicators()
        self.conf_var.set(f'Đã thu {self.current_step}/5 mẫu theo cặp ảnh/vector')
        if self.current_step == 5:
            self._finalize_registration()

    def _manual_capture(self):
        if not self.is_capturing or self.capture_done or self.flash_timer > 0:
            return
        if self.current_step == 5:
            self._finalize_registration()
            return
        frame, faces = self.pump.snapshot()
        if frame is not None:
            self._do_capture(frame, faces)

    def _finalize_registration(self):
        try:
            self.store.stage(self.id_var.get(), self.name_var.get(), list(self.samples_collected), self.enrollment_revision)
        except Exception:
            self.hint_var.set('Chưa lưu được batch. Giữ cửa sổ và bấm SPACE thử lưu lại; mẫu cũ chưa đổi.')
            self.flash_timer = 0
            return
        self.capture_done = True
        self.is_capturing = False
        self.btn_capture.configure(state='disabled')
        self.hint_var.set('Đã lưu batch chờ; chưa dùng các mẫu này để nhận diện.')
        self._run_sync(self.store.retry)

    def _run_sync(self, work):
        if self.sync_busy or self.is_capturing:
            return
        self.sync_busy = True
        self.btn_start.configure(state='disabled')
        def finish(result):
            self.sync_busy = False
            self.btn_start.configure(state='normal' if self.engine else 'disabled')
            self.id_entry.configure(state='normal')
            self.name_entry.configure(state='normal')
            self._refresh_list()
            if isinstance(result, dict) and 'pending' in result:
                message = result.get('message') or ('; '.join(result['errors']) if result['errors'] else 'Đã đồng bộ DB và gallery nhận diện.')
                self.status_var.set(f"{message} Batch chờ: {result['pending']}")
            else:
                self.status_var.set('Đã làm mới gallery từ DB. Batch chưa xác nhận vẫn nằm riêng.')
        def failed(error):
            self.sync_busy = False
            self.btn_start.configure(state='normal' if self.engine else 'disabled')
            self.id_entry.configure(state='normal')
            self.name_entry.configure(state='normal')
            self.status_var.set('Chưa đồng bộ được. Gallery cũ và batch chờ được giữ; kiểm tra kết nối/cấu hình.')
        self.io.submit(work, finish, failed)

    def _retry_sync(self):
        self._run_sync(self.store.retry)

    def _refresh_from_web(self):
        self._run_sync(self.store.refresh)

    def _archive_pending(self):
        sid = self.id_var.get().strip()
        from src.face_sync import employee_id
        try:
            identity = employee_id(sid)
        except ValueError:
            messagebox.showwarning('ID', 'Nhập ID nhân viên có batch chờ.')
            return
        if self.sync_busy or self.is_capturing:
            return
        if messagebox.askyesno('Lưu trữ batch chờ', f'Ngừng thử lại batch chưa xác nhận của NV {identity}? Bản batch được giữ trong archived; DB không thay đổi.'):
            self._run_sync(lambda: self.store.archive(identity))

    def _reset_session(self):
        if self.sync_busy:
            return
        self.current_step = 0; self.embeddings_collected.clear(); self.samples_collected.clear()
        self.ready_timer = 0; self.flash_timer = 0
        self.is_capturing = False; self.capture_done = False; self.progress_var.set(0)
        self.hint_var.set('Nhap thong tin va nhan [Bat dau Dang ky]'); self.conf_var.set('')
        self.btn_start.configure(state='normal' if self.engine else 'disabled')
        self.btn_capture.configure(state='disabled')
        self.id_entry.configure(state='normal'); self.name_entry.configure(state='normal')
        self.status_var.set('Da reset. San sang dang ky moi.')
        self._build_step_indicators()

    def _refresh_list(self):
        for row in self.tree.get_children(): self.tree.delete(row)
        try:
            gallery = load_db()
        except Exception:
            if self.__dict__.get('status_var') is not None:
                self.status_var.set('Gallery cục bộ bị lỗi. Làm mới từ DB; file cũ được giữ nếu mất kết nối.')
            return
        for sid, info in gallery.items():
            self.tree.insert('', 'end', values=(sid, info['name'], info.get('n_images', '?')))

    def _delete_selected(self):
        if self.is_capturing or self.sync_busy:
            return
        selected = self.tree.selection()
        if not selected:
            return
        sid = str(self.tree.item(selected[0])['values'][0])
        try:
            revision = self.store.revision(sid)
        except Exception:
            messagebox.showerror('Đồng bộ', 'Làm mới gallery từ DB trước khi xóa.')
            return
        if messagebox.askyesno('Xác nhận', 'Xóa mẫu khuôn mặt của ' + sid + '? Giữ hồ sơ và lịch sử chấm công.'):
            def work():
                self.store.stage_delete(sid, revision)
                return self.store.retry()
            self._run_sync(work)

    def _delete_all(self):
        if self.is_capturing or self.sync_busy:
            return
        try:
            identities = {sid: self.store.revision(sid) for sid in load_db()}
        except Exception:
            messagebox.showerror('Đồng bộ', 'Làm mới gallery từ DB trước khi xóa.')
            return
        if identities and messagebox.askyesno('Xác nhận', f'Xóa mẫu của {len(identities)} nhân viên trong danh sách?'):
            def work():
                for sid, revision in identities.items():
                    self.store.stage_delete(sid, revision)
                return self.store.retry()
            self._run_sync(work)

    def on_close(self):
        self.running = False
        if self.frame_timer:
            self.after_cancel(self.frame_timer)
        self.pump.close()
        self.io.close()
        self.destroy()


if __name__ == '__main__':
    app = RegisterApp()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()
