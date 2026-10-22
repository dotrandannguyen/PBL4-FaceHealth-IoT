import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os
import pickle
import threading
from pathlib import Path

import sys
BASE_DIR = Path(__file__).resolve().parent
os.chdir(str(BASE_DIR))
DB_PATH = BASE_DIR / "data" / "embeddings.pkl"

# Đường dẫn Python và môi trường (Ưu tiên .venv Python 3.11 có đầy đủ model AI)
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_CMD = str(VENV_PYTHON) if VENV_PYTHON.exists() else (sys.executable or "python")
ENV = os.environ.copy()
ENV["PYTHONIOENCODING"] = "utf-8"


def run_cmd(cmd_list, title=""):
    try:
        creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        subprocess.Popen(cmd_list, env=ENV, cwd=str(BASE_DIR), creationflags=creationflags)
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
        self.geometry("820x720")
        self.resizable(False, False)
        self.ai_service_proc = None
        self.esp32_server_proc = None
        self.camera_source = tk.StringVar(value="esp32")
        
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
        self.after(500, self._check_services_status)

    def setup_left_panel(self):
        # --- Phần Nguồn Camera ---
        frame_cam = ttk.LabelFrame(self.left_frame, text=" 📹 Nguồn Camera AI ", padding=10)
        frame_cam.pack(fill="x", pady=6)

        rb_esp32 = ttk.Radiobutton(
            frame_cam, text="📡 ESP32-CAM (Node 1 - WiFi)", variable=self.camera_source, value="esp32", command=self._update_cam_labels
        )
        rb_esp32.grid(row=0, column=0, sticky="w", padx=5)

        rb_webcam = ttk.Radiobutton(
            frame_cam, text="📷 Webcam Máy tính", variable=self.camera_source, value="0", command=self._update_cam_labels
        )
        rb_webcam.grid(row=0, column=1, sticky="w", padx=5)

        self.lbl_esp_status = ttk.Label(frame_cam, text="⚪ Server ESP32 (Port 5000): Đang kiểm tra...", font=("Segoe UI", 9))
        self.lbl_esp_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 2))

        self.btn_esp_server = ttk.Button(
            frame_cam, text="🚀 Bật Server ESP32 (Port 5000)", command=self.handle_toggle_esp_server
        )
        self.btn_esp_server.grid(row=2, column=0, columnspan=2, sticky="we", pady=3)

        self.btn_preview = ttk.Button(
            frame_cam, text="👁️ Xem Trực Tiếp Stream (On-Demand)", command=self.handle_preview_cam
        )
        self.btn_preview.grid(row=3, column=0, columnspan=2, sticky="we", pady=3)

        # --- Phần Đăng ký ---
        frame_reg = ttk.LabelFrame(self.left_frame, text=" 🎓 Cập nhật Sinh viên (AI 1) ", padding=12)
        frame_reg.pack(fill="x", pady=6)

        ttk.Label(frame_reg, text="Mã SV:").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_id = ttk.Entry(frame_reg, width=25, font=("Segoe UI", 10))
        self.entry_id.grid(row=0, column=1, padx=10, pady=4)
        self.entry_id.insert(0, "SV001")

        ttk.Label(frame_reg, text="Tên SV:").grid(row=1, column=0, sticky="w", pady=4)
        self.entry_name = ttk.Entry(frame_reg, width=25, font=("Segoe UI", 10))
        self.entry_name.grid(row=1, column=1, padx=10, pady=4)
        self.entry_name.insert(0, "Nguyen Van A")

        self.btn_reg = ttk.Button(frame_reg, text="📸 Bắt đầu Đăng ký (ESP32-CAM)", style="Action.TButton", command=self.handle_register)
        self.btn_reg.grid(row=2, column=0, columnspan=2, pady=10, sticky="we")

        # --- Phần Điểm danh ---
        frame_att = ttk.LabelFrame(self.left_frame, text=" 🕒 Chấm công Điểm danh ", padding=12)
        frame_att.pack(fill="x", pady=6)

        self.btn_att = ttk.Button(frame_att, text="✅ Mở Chấm công (ESP32-CAM)", style="Action.TButton", command=self.handle_attendance)
        self.btn_att.pack(fill="x", pady=4)

        # --- Phần Trạng thái ---
        frame_status = ttk.LabelFrame(self.left_frame, text=" 🧠 Nhận diện Trạng thái (AI 2) ", padding=10)
        frame_status.pack(fill="x", pady=5)

        btn_train = ttk.Button(frame_status, text="🔄 Thu thập & Tự động Train AI", command=self.handle_train_status)
        btn_train.pack(fill="x", pady=2)

        self.btn_test = ttk.Button(frame_status, text="🧪 Test Trạng thái (ESP32-CAM)", command=self.handle_test_status)
        self.btn_test.pack(fill="x", pady=2)

        # --- Phần AI REST Service & Web Quản lý ---
        frame_web = ttk.LabelFrame(self.left_frame, text=" 🌐 AI Service & Web Quản trị ", padding=10)
        frame_web.pack(fill="x", pady=5)

        self.lbl_service_status = ttk.Label(frame_web, text="⚪ AI Service: Đang kiểm tra...", font=("Segoe UI", 9))
        self.lbl_service_status.pack(fill="x", pady=2)

        self.btn_service = ttk.Button(
            frame_web,
            text="🚀 Bật AI REST Service (Port 5001)",
            command=self.handle_toggle_ai_service,
        )
        self.btn_service.pack(fill="x", pady=2)

        btn_open_web = ttk.Button(
            frame_web,
            text="🌍 Mở Web Quản trị (localhost:8080)",
            command=self.handle_open_web,
        )
        btn_open_web.pack(fill="x", pady=2)
        self._update_cam_labels()

    def _update_cam_labels(self):
        source = self.camera_source.get()
        tag = "ESP32-CAM" if source == "esp32" else "Webcam"
        if hasattr(self, "btn_reg"):
            self.btn_reg.config(text=f"📸 Bắt đầu Đăng ký ({tag})")
        if hasattr(self, "btn_att"):
            self.btn_att.config(text=f"✅ Mở Chấm công ({tag})")
        if hasattr(self, "btn_test"):
            self.btn_test.config(text=f"🧪 Test Trạng thái ({tag})")


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
        cam = self.camera_source.get()
        sid = self.entry_id.get().strip()
        sname = self.entry_name.get().strip()
        script = str(BASE_DIR / "gui_register.py")
        cmd = [PYTHON_CMD, script, "--camera", cam]
        if sid: cmd += ["--id", sid]
        if sname: cmd += ["--name", sname]
        tag = "ESP32-CAM" if cam == "esp32" else "Webcam"
        run_cmd(cmd, f"Đăng ký Khuôn mặt ({tag})")

    def handle_attendance(self):
        cam = self.camera_source.get()
        tag = "ESP32-CAM" if cam == "esp32" else "Webcam"
        script = str(BASE_DIR / "demo_unified_iot.py")
        run_cmd([PYTHON_CMD, script, "--camera", cam], f"Chấm công ({tag})")

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
            collect_script = str(BASE_DIR / "scripts" / "collect_status.py")
            train_script = str(BASE_DIR / "src" / "train_rf.py")
            creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            
            def worker():
                subprocess.run([PYTHON_CMD, collect_script], env=ENV, cwd=str(BASE_DIR), creationflags=creationflags)
                # Chạy tiếp lệnh Train
                subprocess.run([PYTHON_CMD, train_script], env=ENV, cwd=str(BASE_DIR), creationflags=creationflags)
                messagebox.showinfo("Thành công", "Đã Train xong AI Trạng thái khuôn mặt!")
                
            threading.Thread(target=worker, daemon=True).start()

    def handle_test_status(self):
        cam = self.camera_source.get()
        tag = "ESP32-CAM" if cam == "esp32" else "Webcam"
        script = str(BASE_DIR / "src" / "predict_status.py")
        run_cmd([PYTHON_CMD, script, "--camera", cam], f"Test Trạng thái ({tag})")

    def handle_preview_cam(self):
        cam = self.camera_source.get()
        tag = "ESP32-CAM" if cam == "esp32" else "Webcam"
        script = str(BASE_DIR / "src" / "camera_preview.py")
        run_cmd([PYTHON_CMD, script, "--camera", cam], f"Xem Trực Tiếp ({tag})")

    def handle_clear_db(self):
        if messagebox.askyesno("Cảnh báo", "Bạn có chắc chắn muốn xóa TOÀN BỘ dữ liệu sinh viên đã đăng ký không?"):
            if DB_PATH.exists():
                DB_PATH.unlink()
            import shutil
            reg_dir = Path("data/registered")
            if reg_dir.exists():
                shutil.rmtree(reg_dir, ignore_errors=True)
            try:
                import pymysql
                conn = pymysql.connect(
                    host="127.0.0.1", port=3306, user="pbl4_user", password="pbl4_password",
                    database="DoAn_ChamCong_AI_MariaDB", charset="utf8mb4", autocommit=True, connect_timeout=2
                )
                cursor = conn.cursor()
                cursor.execute("DELETE FROM FaceEmbedding;")
                cursor.close(); conn.close()
            except Exception:
                pass
            self.refresh_user_list()
            messagebox.showinfo("Thành công", "Đã xóa sạch cơ sở dữ liệu khuôn mặt!")

    def handle_toggle_esp_server(self):
        import urllib.request
        server_script = BASE_DIR.parent / "ESP32-CAM" / "server" / "app.py"
        is_running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=0.6) as r:
                if r.status == 200:
                    is_running = True
        except Exception:
            is_running = False

        if is_running:
            if self.esp32_server_proc is not None and self.esp32_server_proc.poll() is None:
                self.esp32_server_proc.terminate()
                self.esp32_server_proc = None
                messagebox.showinfo("Server ESP32", "Đã dừng Server nhận ảnh ESP32.")
            else:
                messagebox.showinfo("Server ESP32", "Server ESP32 đang chạy từ một cửa sổ lệnh bên ngoài.")
        else:
            try:
                creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                self.esp32_server_proc = subprocess.Popen([PYTHON_CMD, str(server_script)], env=ENV, cwd=str(server_script.parent), creationflags=creationflags)
                messagebox.showinfo("Server ESP32", "Đã khởi động Server ESP32 trên cổng 5000!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể bật Server ESP32:\n{str(e)}")

        self._check_services_status()

    def handle_toggle_ai_service(self):
        import urllib.request
        is_running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:5001/health", timeout=0.5) as r:
                if r.status == 200:
                    is_running = True
        except Exception:
            is_running = False

        if is_running:
            if self.ai_service_proc is not None and self.ai_service_proc.poll() is None:
                self.ai_service_proc.terminate()
                self.ai_service_proc = None
                messagebox.showinfo("AI Service", "Đã dừng AI REST Service.")
            else:
                messagebox.showinfo("AI Service", "AI Service đang chạy ở process khác hoặc cổng 5001 đang được sử dụng.")
        else:
            try:
                creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                ai_script = str(BASE_DIR / "ai_web_service.py")
                self.ai_service_proc = subprocess.Popen([PYTHON_CMD, ai_script], env=ENV, cwd=str(BASE_DIR), creationflags=creationflags)
                messagebox.showinfo("AI Service", "Đã khởi động AI REST Service trên cổng 5001!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể bật AI Service:\n{str(e)}")

        self._check_services_status()

    def handle_open_web(self):
        import webbrowser
        webbrowser.open("http://localhost:8080")

    def _check_services_status(self):
        def _check():
            import urllib.request
            import json

            # 1. Kiểm tra AI Service (Port 5001)
            ai_running = False
            try:
                with urllib.request.urlopen("http://127.0.0.1:5001/health", timeout=0.6) as r:
                    if r.status == 200:
                        ai_running = True
            except Exception:
                ai_running = False

            # 2. Kiểm tra ESP32 Camera trực tiếp (mDNS: esp32cam.local:81) hoặc qua Server (Port 5000)
            esp_status = "stopped"
            esp_info = ""
            try:
                # Ưu tiên kiểm tra trực tiếp qua mDNS
                with urllib.request.urlopen("http://esp32cam.local:81/status", timeout=0.8) as r:
                    if r.status == 200:
                        data = json.loads(r.read().decode())
                        is_stream = data.get("streaming", False)
                        esp_status = "streaming" if is_stream else "standby"
                        esp_info = "esp32cam.local:81"
            except Exception:
                # Nếu mDNS chưa phản hồi, kiểm tra qua Server trung gian Port 5000
                try:
                    with urllib.request.urlopen("http://127.0.0.1:5000/api/camera_status", timeout=0.5) as r:
                        if r.status == 200:
                            data = json.loads(r.read().decode())
                            if data.get("online"):
                                esp_status = "standby"
                                esp_info = data.get("client_ip", "")
                except Exception:
                    esp_status = "stopped"

            def _update_ui():
                # Cập nhật nhãn AI Service
                if ai_running:
                    self.lbl_service_status.config(
                        text="🟢 AI Service: Đang chạy (Port 5001)",
                        foreground="#27ae60",
                    )
                    self.btn_service.config(text="🛑 Dừng AI REST Service")
                else:
                    self.lbl_service_status.config(
                        text="⚪ AI Service: Đã dừng",
                        foreground="#7f8c8d",
                    )
                    self.btn_service.config(text="🚀 Bật AI REST Service (Port 5001)")

                # Cập nhật nhãn ESP32 Camera
                if esp_status == "streaming":
                    self.lbl_esp_status.config(
                        text=f"🟢 ESP32-CAM: Đang phát Stream Live ({esp_info})",
                        foreground="#27ae60",
                    )
                    self.btn_esp_server.config(text="🛑 Dừng Server Phụ (Port 5000)")
                elif esp_status == "standby":
                    self.lbl_esp_status.config(
                        text=f"🟢 ESP32-CAM (mDNS): Online - Chế độ Nghỉ ({esp_info})",
                        foreground="#2980b9",
                    )
                    self.btn_esp_server.config(text="🚀 Bật Server Phụ (Port 5000)")
                else:
                    self.lbl_esp_status.config(
                        text="⚪ ESP32-CAM: Ngoại tuyến (Đang tìm esp32cam.local...)",
                        foreground="#7f8c8d",
                    )
                    self.btn_esp_server.config(text="🚀 Bật Server Phụ (Port 5000)")

                self.after(3000, self._check_services_status)

            self.after(0, _update_ui)

        threading.Thread(target=_check, daemon=True).start()

    def destroy(self):
        if self.ai_service_proc is not None and self.ai_service_proc.poll() is None:
            try:
                self.ai_service_proc.terminate()
            except Exception:
                pass
        if self.esp32_server_proc is not None and self.esp32_server_proc.poll() is None:
            try:
                self.esp32_server_proc.terminate()
            except Exception:
                pass
        super().destroy()

if __name__ == "__main__":
    app = FaceAIDashboard()
    app.mainloop()

