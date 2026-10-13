import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os
import pickle
import threading
from pathlib import Path

# Đường dẫn Python và môi trường
PYTHON_CMD = r".\.venv\Scripts\python.exe"
ENV = os.environ.copy()
ENV["PYTHONIOENCODING"] = "utf-8"

DB_PATH = Path("data/embeddings.pkl")

def run_cmd(cmd_list, title=""):
    try:
        subprocess.Popen(cmd_list, env=ENV)
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
        self.geometry("750x550")
        self.resizable(False, False)
        
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
        frame_status = ttk.LabelFrame(self.left_frame, text=" 🧠 Nhận diện Trạng thái (AI 2) ", padding=15)
        frame_status.pack(fill="x", pady=10)

        btn_train = ttk.Button(frame_status, text="🔄 Thu thập & Tự động Train AI", command=self.handle_train_status)
        btn_train.pack(fill="x", pady=5)

        btn_test = ttk.Button(frame_status, text="🧪 Test Trạng thái (Real-time)", command=self.handle_test_status)
        btn_test.pack(fill="x", pady=5)

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

    def refresh_user_list(self):
        # Xóa dữ liệu cũ trên bảng
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        users = get_registered_users()
        for u in users:
            self.tree.insert("", "end", values=(u["id"], u["name"]))

    def handle_register(self):
        sv_id = self.entry_id.get().strip()
        sv_name = self.entry_name.get().strip()
        if not sv_id or not sv_name:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Mã Sinh Viên và Tên trước khi đăng ký!")
            return
        run_cmd([PYTHON_CMD, "main.py", "register", "webcam", "--id", sv_id, "--name", sv_name], "Đăng ký")
        messagebox.showinfo("Lưu ý", "Sau khi đăng ký xong qua Webcam, hãy bấm 'Làm mới danh sách' để xem kết quả nhé.")

    def handle_attendance(self):
        run_cmd([PYTHON_CMD, "main.py", "identify", "--webcam"], "Chấm công")

    def handle_train_status(self):
        msg = (
            "Hướng dẫn thu thập dữ liệu 3 cấp độ mệt mỏi (AI 2):\n"
            "- Cửa sổ Webcam sẽ hiện ra kèm chỉ số EAR trực tiếp.\n"
            "- Bấm các phím số tương ứng để ghi lại chuỗi 3 frames:\n"
            "  [1] Normal    : Bình thường / Tỉnh táo (EAR >= 0.25)\n"
            "  [2] Fatigue   : Mệt mỏi / Lờ đờ (0.18 <= EAR < 0.25)\n"
            "  [3] Exhausted : Kiệt sức / Sụp mí (EAR < 0.18)\n"
            "- Bấm [Q] để Lưu dữ liệu vào CSV và Thoát Webcam.\n\n"
            "Hệ thống sẽ TỰ ĐỘNG TRAIN Random Forest ngay sau khi bạn bấm Q thoát.\n"
            "Bạn có muốn bắt đầu ngay bây giờ?"
        )
        if messagebox.askyesno("Thu thập & Train AI", msg):
            cmd = [PYTHON_CMD, "scripts/collect_status.py"]
            
            def worker():
                subprocess.run(cmd, env=ENV)
                # Chạy tiếp lệnh Train
                subprocess.run([PYTHON_CMD, "src/train_rf.py"], env=ENV)
                messagebox.showinfo("Thành công", "Đã Train xong AI Trạng thái khuôn mặt!")
                
            threading.Thread(target=worker, daemon=True).start()

    def handle_test_status(self):
        run_cmd([PYTHON_CMD, "src/predict_status.py"], "Test Trạng thái")
        
    def handle_clear_db(self):
        if messagebox.askyesno("Cảnh báo", "Bạn có chắc chắn muốn xóa TOÀN BỘ dữ liệu sinh viên đã đăng ký không?"):
            if DB_PATH.exists():
                DB_PATH.unlink()
            
            # Xóa các folder ảnh trong data/registered nếu muốn (ở đây ta chỉ xóa file pkl cho nhanh)
            import shutil
            reg_dir = Path("data/registered")
            if reg_dir.exists():
                shutil.rmtree(reg_dir, ignore_errors=True)
                
            self.refresh_user_list()
            messagebox.showinfo("Thành công", "Đã xóa sạch cơ sở dữ liệu khuôn mặt!")

if __name__ == "__main__":
    app = FaceAIDashboard()
    app.mainloop()
