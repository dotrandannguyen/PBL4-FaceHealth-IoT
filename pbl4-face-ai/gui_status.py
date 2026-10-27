"""Real-time status testing. Tk renders; a separate worker owns inference."""
import sys
import tkinter as tk
from tkinter import ttk

from src.runtime_config import load_environment
from src.status_preview import (
    ABNORMAL_STATES, StatusPreviewWorker, confidence_text, draw_status_frame, state_label,
)

BACKGROUND = '#0d1117'
PANEL = '#161b22'
TEXT = '#e6edf3'
MUTED = '#8b949e'
BLUE = '#58a6ff'
GREEN = '#3fb950'
RED = '#f85149'


class StatusTestApp(tk.Tk):
    def __init__(self, worker_factory=StatusPreviewWorker):
        super().__init__()
        self.worker_factory = worker_factory
        self.worker = None
        self.closing_worker = None
        self.running = True
        self.timer = None
        self.photo = None
        self.camera_item = None
        self.title('PBL4 · Test trạng thái khuôn mặt')
        self.geometry('1180x760')
        self.minsize(980, 660)
        self.configure(bg=BACKGROUND)
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Escape>', lambda event: self.destroy())
        # The dashboard uses this listener to release a module before switching.
        try:
            from src.desktop_lifecycle import install_close_listener
        except ImportError:
            pass
        else:
            install_close_listener(self, self.destroy)
        self.start()
        self._poll()

    def _label(self, parent, text='', *, color=TEXT, size=10, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), **kwargs)

    def _build_ui(self):
        header = tk.Frame(self, bg=PANEL, padx=20, pady=16)
        header.pack(fill='x')
        self._label(header, 'Test trạng thái khuôn mặt', size=17, bold=True).pack(anchor='w')
        self._label(header, 'Nhìn vào camera để xem trạng thái, điểm mốc và các chỉ số trực tiếp.', color=MUTED).pack(anchor='w', pady=(5, 0))
        body = tk.Frame(self, bg=BACKGROUND)
        body.pack(fill='both', expand=True, padx=16, pady=16)
        video_panel = tk.Frame(body, bg=BACKGROUND)
        video_panel.pack(side='left', fill='both', expand=True)
        self.canvas = tk.Canvas(video_panel, bg='#030609', highlightthickness=1, highlightbackground='#30363d')
        self.canvas.pack(fill='both', expand=True)
        self.notice_item = self.canvas.create_text(360, 220, text='Đang chuẩn bị…', fill=TEXT,
                                                   font=('Segoe UI', 12), justify='center', width=580)
        self._label(video_panel, 'Chỉ một khuôn mặt trong khung hình · ESC để đóng', color=MUTED, anchor='w').pack(fill='x', pady=(10, 0))
        side = tk.Frame(body, bg=PANEL, padx=18, pady=14, width=330)
        side.pack(side='right', fill='y', padx=(16, 0))
        side.pack_propagate(False)
        # Reserve controls first so they stay reachable at the minimum height.
        controls = tk.Frame(side, bg=PANEL)
        controls.pack(side='bottom', fill='x', pady=(10, 0))
        self.start_button = ttk.Button(controls, text='Bắt đầu / Thử lại', command=self.start)
        self.start_button.pack(fill='x', pady=3)
        self.pause_button = ttk.Button(controls, text='Dừng và giải phóng camera', command=self.pause)
        self.pause_button.pack(fill='x', pady=3)
        self._label(side, 'KẾT QUẢ PHÂN TÍCH', color=BLUE, size=10, bold=True).pack(anchor='w')
        self.status_label = self._label(side, 'Đang khởi tạo', size=15, bold=True, wraplength=280, justify='left')
        self.status_label.pack(anchor='w', pady=(8, 3))
        self.confidence_label = self._label(side, 'Độ tự tin: —', color=MUTED)
        self.confidence_label.pack(anchor='w')
        self.source_label = self._label(side, 'Nguồn kết quả: —', color=MUTED, wraplength=280, justify='left')
        self.source_label.pack(anchor='w', pady=(5, 12))
        ttk.Separator(side).pack(fill='x', pady=(0, 8))
        self._label(side, 'CHỈ SỐ THỜI GIAN THỰC', color=BLUE, bold=True).pack(anchor='w', pady=(0, 10))
        self.metric_labels = {}
        metric_names = [('ear', 'EAR · độ mở mắt'), ('mar', 'MAR · độ mở miệng'),
                        ('pitch', 'Pitch · cúi / ngẩng'), ('yaw', 'Yaw · quay đầu'), ('roll', 'Roll · nghiêng đầu')]
        for key, label in metric_names:
            row = tk.Frame(side, bg=PANEL)
            row.pack(fill='x', pady=4)
            self._label(row, label, color=MUTED).pack(side='left')
            value = self._label(row, '—', bold=True)
            value.pack(side='right')
            self.metric_labels[key] = value
        self.progress_label = self._label(side, 'Mẫu hợp lệ: 0/3', color=MUTED)
        self.progress_label.pack(anchor='w', pady=(12, 4))
        self.progress = ttk.Progressbar(side, maximum=3, mode='determinate')
        self.progress.pack(fill='x')
        self.timing_label = self._label(side, 'Thời gian phân tích: —', color=MUTED)
        self.timing_label.pack(anchor='w', pady=(6, 10))
        self._label(side, 'Chuỗi 3 mẫu · cách 300 ms\nPitch chính diện: gần ±180°\nQuay đầu: quy tắc riêng, không có % RF.',
                    color=MUTED, size=9, wraplength=280, justify='left').pack(anchor='w')
        self.footer = self._label(self, 'Đang tải model…', color=MUTED, anchor='w', padx=18, pady=9)
        self.footer.pack(fill='x')

    def start(self):
        if not self.running:
            return
        if self.worker is not None and self.worker.thread.is_alive():
            return
        if self.closing_worker is not None and self.closing_worker.thread.is_alive():
            self.footer.config(text='Đang giải phóng camera; vui lòng thử lại sau giây lát.')
            return
        if self.worker is not None:
            self.worker.close()
        self.closing_worker = None
        self.worker = self.worker_factory()
        self.start_button.config(state='disabled')
        self.pause_button.config(state='normal')

    def pause(self):
        if self.worker is not None:
            self.worker.close()
            self.closing_worker = self.worker
            self.worker = None
        self.start_button.config(state='normal')
        self.pause_button.config(state='disabled')
        self._render_metrics({})
        self._notice('Đã dừng camera.\nBấm Bắt đầu để tiếp tục.')
        self.footer.config(text='Đã yêu cầu giải phóng camera.')

    def _notice(self, message):
        self.canvas.itemconfig(self.notice_item, text=message, state='normal')
        self.canvas.coords(self.notice_item, max(1, self.canvas.winfo_width()) / 2, max(1, self.canvas.winfo_height()) / 2)
        if self.camera_item is not None:
            self.canvas.itemconfig(self.camera_item, state='hidden')

    def _render_metrics(self, result, inference_ms=None):
        status = result.get('status', 'Unknown')
        self.status_label.config(text=state_label(status), fg=RED if status in ABNORMAL_STATES else (GREEN if result.get('is_valid') else TEXT))
        self.confidence_label.config(text='Độ tự tin: ' + confidence_text(result))
        source = 'Quy tắc góc đầu · không có xác suất RF' if result.get('rule_based') else ('Random Forest · chuỗi 3 mẫu' if result.get('is_valid') else 'Chờ chuỗi hợp lệ')
        self.source_label.config(text='Nguồn: ' + source)
        metrics = result.get('metrics', {})
        for key, widget in self.metric_labels.items():
            value = metrics.get(key, result.get(key))
            text = f'{value:.3f}' if isinstance(value, (int, float)) and key in ('ear', 'mar') else (f'{value:.1f}°' if isinstance(value, (int, float)) else '—')
            widget.config(text=text)
        count = min(3, max(0, result.get('valid_count', 0)))
        self.progress['value'] = count
        self.progress_label.config(text=f'Mẫu hợp lệ: {count}/3')
        self.timing_label.config(text=f'Thời gian phân tích: {inference_ms:.0f} ms' if inference_ms is not None else 'Thời gian phân tích: —')

    def _render_frame(self, frame, result):
        import cv2
        from PIL import Image, ImageTk
        display = draw_status_frame(frame, result, show_text=False)
        image = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image=image, master=self)
        if self.camera_item is None:
            self.camera_item = self.canvas.create_image(width / 2, height / 2, image=self.photo)
        else:
            self.canvas.itemconfig(self.camera_item, image=self.photo, state='normal')
            self.canvas.coords(self.camera_item, width / 2, height / 2)
        self.canvas.itemconfig(self.notice_item, state='hidden')

    def _poll(self):
        if not self.running:
            return
        if self.worker is not None:
            snapshot = self.worker.snapshot()
            result = snapshot.get('result', {})
            self._render_metrics(result, snapshot.get('inference_ms'))
            if snapshot.get('frame') is not None:
                self._render_frame(snapshot['frame'], result)
                self.footer.config(text='Camera đang chạy · quay đầu hoặc thay đổi nét mặt để theo dõi chỉ số trực tiếp.')
            else:
                self._notice(snapshot.get('message', 'Đang chờ camera…'))
                self.footer.config(text=snapshot.get('message', 'Đang chờ camera…'))
            if snapshot.get('state') == 'error':
                self.start_button.config(state='normal')
                self.pause_button.config(state='disabled')
        self.timer = self.after(40, self._poll)

    def destroy(self):
        if not self.running:
            return
        self.running = False
        if self.timer is not None:
            self.after_cancel(self.timer)
        if self.worker is not None:
            self.worker.close()
        if self.closing_worker is not None:
            self.closing_worker.close()
        super().destroy()


def main():
    load_environment()
    try:
        app = StatusTestApp()
        app.mainloop()
        return 0
    except Exception as error:
        print('Status test stopped:', str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
