import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import subprocess
import os
from src.runtime_config import load_environment

load_environment()
import pickle
import threading
from pathlib import Path

import sys
# Đường dẫn Python và môi trường
PYTHON_CMD = sys.executable if sys.executable else r".\.venv\Scripts\python.exe"
ENV = os.environ.copy()
ENV["PYTHONIOENCODING"] = "utf-8"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "embeddings.pkl"

def run_cmd(cmd_list, title=""):
    try:
        subprocess.Popen(cmd_list, env=ENV, cwd=BASE_DIR)
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể chạy lệnh {title}:\n{str(e)}")

def get_registered_users():
    if not DB_PATH.exists():
        return []
    try:
        with open(DB_PATH, "rb") as f:
            db = pickle.load(f)
        return [{"id": k, "name": v["name"]} for k, v in db.items()]
    except:
        return []

class FaceAIDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🤖 Bảng Điều Khiển Hệ Thống Face AI - PBL4")
        self.geometry("780x640")
        self.resizable(False, False)
        self.ai_service_proc = None
        from src.ui_worker import UiWorker
        from src.desktop_enrollment import DesktopEnrollment
        self.io = UiWorker(self)
        from src.process_runner import ProcessRunner
        self.training_io = UiWorker(self)
        self.training_runner = ProcessRunner()
        self.train_busy = False
        self.store = DesktopEnrollment()
        self._checking_service = False
        self._service_timer = None
        
        # Cài đặt Theme cho đẹp hơn
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground="#2c3e50")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"), foreground="#2980b9")
        
        # Chia layout chính thành 2 cột (Trái: Control, Phải: Database)
        self.left_frame = tk.Frame(self, padx=10, pady=10)
        self.left_frame.pack(side="left", fill="both", expand=True)
        
        self.right_frame = tk.Frame(self, padx=10, pady=10)
        self.right_frame.pack(side="right", fill="both", expand=True)

        self.setup_left_panel()
        self.setup_right_panel()
        self.refresh_user_list()
        self._service_timer = self.after(500, self._check_ai_service_status)

    def setup_left_panel(self):
        # --- Phần Đăng ký ---
        frame_reg = ttk.LabelFrame(self.left_frame, text=" 🎓 Cập nhật Sinh viên (AI 1) ", padding=15)
        frame_reg.pack(fill="x", pady=10)

        ttk.Label(frame_reg, text="Mã SV:").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_id = ttk.Entry(frame_reg, width=25, font=("Segoe UI", 10))
        self.entry_id.grid(row=0, column=1, padx=10, pady=5)
        self.entry_id.insert(0, "SV001")

        ttk.Label(frame_reg, text="Tên SV:").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_name = ttk.Entry(frame_reg, width=25, font=("Segoe UI", 10))
        self.entry_name.grid(row=1, column=1, padx=10, pady=5)
        self.entry_name.insert(0, "Nguyen Van A")

        btn_reg = ttk.Button(frame_reg, text="📸 Bắt đầu Đăng ký Webcam", style="Action.TButton", command=self.handle_register)
        btn_reg.grid(row=2, column=0, columnspan=2, pady=15, sticky="we")

        # --- Phần Điểm danh ---
        frame_att = ttk.LabelFrame(self.left_frame, text=" 🕒 Chấm công Điểm danh ", padding=15)
        frame_att.pack(fill="x", pady=10)

        btn_att = ttk.Button(frame_att, text="✅ Mở Webcam Chấm công", style="Action.TButton", command=self.handle_attendance)
        btn_att.pack(fill="x", pady=5)

        # --- Phần Trạng thái ---
        frame_status = ttk.LabelFrame(self.left_frame, text=" 🧠 Nhận diện Trạng thái (AI 2) ", padding=12)
        frame_status.pack(fill="x", pady=6)

        btn_train = ttk.Button(frame_status, text="🔄 Thu thập & Tự động Train AI", command=self.handle_train_status)
        btn_train.pack(fill="x", pady=3)

        btn_test = ttk.Button(frame_status, text="🧪 Test Trạng thái (Real-time)", command=self.handle_test_status)
        btn_test.pack(fill="x", pady=3)

        # --- Phần AI REST Service & Web Quản lý ---
        frame_web = ttk.LabelFrame(self.left_frame, text=" 🌐 AI Service & Web Quản trị ", padding=12)
        frame_web.pack(fill="x", pady=6)

        self.lbl_service_status = ttk.Label(frame_web, text="⚪ AI Service: Đang kiểm tra...", font=("Segoe UI", 9))
        self.lbl_service_status.pack(fill="x", pady=2)

        self.btn_service = ttk.Button(
            frame_web,
            text="🚀 Bật AI REST Service (Port 5001)",
            command=self.handle_toggle_ai_service,
        )
        self.btn_service.pack(fill="x", pady=3)

        btn_open_web = ttk.Button(
            frame_web,
            text="🌍 Mở Web Quản trị (localhost:8080)",
            command=self.handle_open_web,
        )
        btn_open_web.pack(fill="x", pady=3)

    def setup_right_panel(self):
        # --- Danh sách User ---
        frame_db = ttk.LabelFrame(self.right_frame, text=" 📋 Danh sách Sinh viên trong Database ", padding=15)
        frame_db.pack(fill="both", expand=True, pady=10)

        # Thanh cuộn và Treeview
        scroll = ttk.Scrollbar(frame_db)
        scroll.pack(side="right", fill="y")

        columns = ("id", "name")
        self.tree = ttk.Treeview(frame_db, columns=columns, show="headings", yscrollcommand=scroll.set, height=18)
        self.tree.heading("id", text="Mã SV")
        self.tree.heading("name", text="Họ & Tên")
        self.tree.column("id", width=90, anchor="center")
        self.tree.column("name", width=180)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.tree.yview)

        # Nút tiện ích
        frame_utils = tk.Frame(self.right_frame)
        frame_utils.pack(fill="x", pady=5)
        
        btn_refresh = ttk.Button(frame_utils, text="🔄 Làm mới danh sách", command=self.refresh_user_list)
        btn_refresh.pack(side="left", padx=5, expand=True, fill="x")

        btn_clear = ttk.Button(frame_utils, text="🗑 Xóa toàn bộ DB", command=self.handle_clear_db)
        btn_clear.pack(side="right", padx=5, expand=True, fill="x")
        ttk.Button(self.right_frame, text='Thử đồng bộ batch chờ', command=self.handle_retry_sync).pack(fill='x', padx=5)

    def refresh_user_list(self):
        def done(result):
            self._render_user_list()
        self.io.submit(self.store.refresh, done,
                       lambda error: messagebox.showerror('Đồng bộ', 'Chưa tải được gallery từ DB; dữ liệu cũ được giữ nguyên.'))

    def _render_user_list(self):
        # Xóa dữ liệu cũ trên bảng
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        users = get_registered_users()
        for u in users:
            self.tree.insert("", "end", values=(u["id"], u["name"]))

    def handle_register(self):
        run_cmd([PYTHON_CMD, "gui_register.py"], "Đăng ký Khuôn mặt")

    def handle_attendance(self):
        run_cmd([PYTHON_CMD, "demo_unified_iot.py"], "Chấm công Thông minh")

    def handle_train_status(self):
        if self.train_busy:
            return
        subject = simpledialog.askstring('Người tham gia', 'Nhập mã người ổn định (mã giả danh, không dùng anonymous):', parent=self)
        if subject is None:
            return
        from src.status_dataset import subject_id
        try:
            subject = subject_id(subject.strip())
        except ValueError as error:
            messagebox.showerror('Mã người', str(error))
            return
        if not messagebox.askyesno('Thu thập và train',
            'Phím 1/2/3 chọn nhãn thủ công Normal/Fatigue/Exhausted; mỗi lần ghi ba ảnh cách nhau 300 ms. '
            'Q dừng thu thập. Chỉ train khi có mẫu mới và dữ liệu đủ người độc lập, đủ ba nhãn. '
            'EAR không tự quyết định nhãn. Bắt đầu?'):
            return
        self.train_busy = True
        def work():
            collected = self.training_runner.run([PYTHON_CMD, 'scripts/collect_status.py', '--subject', subject], env=ENV, cwd=BASE_DIR)
            if collected.returncode != 0:
                return 'Thu thập đã dừng hoặc chưa có mẫu mới; model hiện có được giữ nguyên.'
            trained = self.training_runner.run([PYTHON_CMD, 'src/train_rf.py'], env=ENV, cwd=BASE_DIR)
            if trained.returncode != 0:
                return 'Mẫu thu thập đã lưu; chưa train được. Cần dataset v2 đủ người/nhãn và môi trường phù hợp. Model cũ được giữ nguyên.'
            return 'Đã train và lưu model cùng metadata; kết quả đánh giá thuộc split của dataset này.'
        def done(message):
            self.train_busy = False
            messagebox.showinfo('Thu thập/train', message)
        def failed(error):
            self.train_busy = False
            messagebox.showerror('Thu thập/train', 'Không chạy được tiến trình. Kiểm tra Python/dependency; dữ liệu đã lưu được giữ nguyên.')
        self.training_io.submit(work, done, failed)

    def handle_test_status(self):
        run_cmd([PYTHON_CMD, "src/predict_status.py"], "Test Trạng thái")

    def handle_clear_db(self):
        try:
            identities = {user['id']: self.store.revision(user['id']) for user in get_registered_users()}
        except Exception:
            messagebox.showerror('Đồng bộ', 'Làm mới gallery từ DB trước khi xóa.')
            return
        if not identities or not messagebox.askyesno('Xác nhận', f'Xóa mẫu của {len(identities)} nhân viên trong danh sách? Giữ hồ sơ và lịch sử.'):
            return
        def work():
            for sid, revision in identities.items():
                self.store.stage_delete(sid, revision)
            return self.store.retry()
        def done(result):
            self._render_user_list()
            messagebox.showinfo('Đồng bộ', f"Đã hoàn tất {result['completed']}; còn {result['pending']} batch chờ. " + '; '.join(result['errors']))
        self.io.submit(work, done, lambda error: messagebox.showerror('Đồng bộ', 'Chưa xóa xong; batch chờ và gallery được giữ để kiểm tra/thử lại.'))

    def handle_retry_sync(self):
        def done(result):
            self._render_user_list()
            messagebox.showinfo('Đồng bộ', f"Đã hoàn tất {result['completed']}; còn {result['pending']} batch chờ. " + '; '.join(result['errors']))
        self.io.submit(self.store.retry, done, lambda error: messagebox.showerror('Đồng bộ', 'Không đọc được batch chờ; giữ nguyên để kiểm tra.'))

    def handle_toggle_ai_service(self):
        if self.ai_service_proc is not None and self.ai_service_proc.poll() is None:
            self.ai_service_proc.terminate()
            return
        def checked(health):
            if health is not None:
                messagebox.showinfo('AI Service', 'Service đang chạy ở process khác; chỉ process do cửa sổ này tạo mới được dừng.')
                return
            try:
                self.ai_service_proc = subprocess.Popen([PYTHON_CMD, 'ai_web_service.py'], env=ENV, cwd=BASE_DIR)
                messagebox.showinfo('AI Service', 'Đã bắt đầu tải service. Theo dõi trạng thái model trước khi đăng ký.')
            except Exception:
                messagebox.showerror('AI Service', 'Không khởi động được service; kiểm tra Python/môi trường.')
        self.io.submit(self._read_service_health, checked, lambda error: checked(None))

    @staticmethod
    def _read_service_health():
        import requests
        try:
            url = os.environ.get('PBL4_AI_URL', os.environ.get('AI_SERVICE_URL', 'http://127.0.0.1:5001')).rstrip('/')
            response = requests.get(url + '/health', timeout=.6, allow_redirects=False)
            health = response.json()
            return health if response.status_code == 200 and isinstance(health, dict) and health.get('service') == 'PBL4 Face AI Service' else None
        except Exception:
            return None

    def handle_open_web(self):
        import webbrowser
        webbrowser.open("http://localhost:8080")

    def _check_ai_service_status(self):
        if self._checking_service:
            return
        self._checking_service = True
        def update(health):
            self._checking_service = False
            ready = health is not None and health.get('model_ready') is True
            text = 'AI Service: sẵn sàng' if ready else ('AI Service: model chưa sẵn sàng' if health else 'AI Service: chưa kết nối')
            self.lbl_service_status.config(text=text, foreground='#27ae60' if ready else '#7f8c8d')
            self.btn_service.config(text='Dừng service của cửa sổ này' if self.ai_service_proc is not None and self.ai_service_proc.poll() is None else 'Bật AI REST Service')
            self._service_timer = self.after(3000, self._check_ai_service_status)
        self.io.submit(self._read_service_health, update, lambda error: update(None))

    def destroy(self):
        if self._service_timer:
            self.after_cancel(self._service_timer)
        self.io.close()
        self.training_runner.close()
        self.training_io.close()
        if self.ai_service_proc is not None and self.ai_service_proc.poll() is None:
            self.ai_service_proc.terminate()
            try:
                self.ai_service_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.ai_service_proc.kill()
                self.ai_service_proc.wait(timeout=2)
        super().destroy()

if __name__ == "__main__":
    app = FaceAIDashboard()
    app.mainloop()
