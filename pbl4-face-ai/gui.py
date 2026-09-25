import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os

# Đường dẫn Python trong môi trường ảo
PYTHON_CMD = r".\.venv\Scripts\python.exe"
# Fix lỗi in emoji trong subprocess trên Windows
ENV = os.environ.copy()
ENV["PYTHONIOENCODING"] = "utf-8"

def run_cmd(cmd_list, title=""):
    """Hàm hỗ trợ chạy lệnh trong Terminal riêng hoặc ngầm"""
    try:
        # Popen sẽ chạy dưới nền, cửa sổ webcam (nếu có) sẽ tự động hiện lên nhờ OpenCV
        subprocess.Popen(cmd_list, env=ENV)
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể chạy lệnh {title}:\n{str(e)}")

def handle_register():
    sv_id = entry_id.get().strip()
    sv_name = entry_name.get().strip()
    if not sv_id or not sv_name:
        messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Mã Sinh Viên và Tên trước khi đăng ký!")
        return
    
    # Chạy đăng ký webcam
    cmd = [PYTHON_CMD, "main.py", "register", "webcam", "--id", sv_id, "--name", sv_name]
    run_cmd(cmd, "Đăng ký")

def handle_attendance():
    # Chạy điểm danh webcam 1:N
    cmd = [PYTHON_CMD, "main.py", "identify", "--webcam"]
    run_cmd(cmd, "Chấm công")

def handle_train_status():
    msg = (
        "Bước 1: Cửa sổ Webcam sẽ hiện ra. Bạn nhìn vào và bấm:\n"
        "  [1] Normal\n  [2] Drowsy\n  [3] Yawn\n  [4] Head-down\n"
        "  [Q] để Lưu & Thoát.\n\n"
        "Bước 2: Sau khi bạn bấm Q thoát Webcam, hệ thống sẽ tự động Train mô hình AI.\n\n"
        "Bạn đã sẵn sàng mở Webcam chưa?"
    )
    if messagebox.askyesno("Thu thập & Train AI", msg):
        # Chạy file thu thập dữ liệu
        cmd = [PYTHON_CMD, "scripts/collect_status.py"]
        
        def on_collect_done():
            # Hàm chạy tiếp train sau khi collect xong
            messagebox.showinfo("Thông báo", "Đang tiến hành Train AI, vui lòng chờ chút trong Terminal...")
            subprocess.run([PYTHON_CMD, "src/train_rf.py"], env=ENV)
            messagebox.showinfo("Thành công", "Đã Train xong AI Trạng thái khuôn mặt!")
            
        # Chạy thu thập xong mới train, ta dùng luồng hoặc process chờ
        # Để GUI không đơ, ta có thể Popen và cho 1 thread chờ, nhưng để đơn giản ta dùng lệnh shell hoặc run.
        import threading
        def worker():
            subprocess.run(cmd, env=ENV)
            # Sau khi cửa sổ webcam đóng (thu thập xong)
            on_collect_done()
            
        threading.Thread(target=worker, daemon=True).start()

def handle_test_status():
    # Test realtime webcam
    cmd = [PYTHON_CMD, "src/predict_status.py"]
    run_cmd(cmd, "Test Trạng thái")

# --- Xây dựng giao diện Tkinter ---
root = tk.Tk()
root.title("AI Điểm Danh & Trạng Thái")
root.geometry("400x380")
root.resizable(False, False)

# Style
style = ttk.Style()
style.theme_use('clam')
style.configure("TButton", font=("Segoe UI", 11), padding=6)
style.configure("TLabel", font=("Segoe UI", 10))

# Khung Đăng ký
frame_reg = ttk.LabelFrame(root, text=" 1. Đăng ký khuôn mặt ", padding=15)
frame_reg.pack(fill="x", padx=15, pady=10)

ttk.Label(frame_reg, text="Mã SV:").grid(row=0, column=0, sticky="w", pady=5)
entry_id = ttk.Entry(frame_reg, width=30)
entry_id.grid(row=0, column=1, padx=5, pady=5)
entry_id.insert(0, "SV001")

ttk.Label(frame_reg, text="Tên SV:").grid(row=1, column=0, sticky="w", pady=5)
entry_name = ttk.Entry(frame_reg, width=30)
entry_name.grid(row=1, column=1, padx=5, pady=5)
entry_name.insert(0, "Nguyen Van A")

btn_reg = ttk.Button(frame_reg, text="📸 Đăng ký Webcam", command=handle_register)
btn_reg.grid(row=2, column=0, columnspan=2, pady=10, sticky="we")

# Khung Điểm danh
frame_att = ttk.LabelFrame(root, text=" 2. Điểm danh (Nhận diện AI 1) ", padding=15)
frame_att.pack(fill="x", padx=15, pady=5)

btn_att = ttk.Button(frame_att, text="✅ Mở Webcam Chấm công", command=handle_attendance)
btn_att.pack(fill="x")

# Khung Trạng thái khuôn mặt
frame_status = ttk.LabelFrame(root, text=" 3. Phân tích Trạng thái (AI 2) ", padding=15)
frame_status.pack(fill="x", padx=15, pady=5)

btn_train = ttk.Button(frame_status, text="🔄 Thu thập dữ liệu & Train AI", command=handle_train_status)
btn_train.pack(fill="x", pady=2)

btn_test = ttk.Button(frame_status, text="🧪 Test Trạng thái (Real-time)", command=handle_test_status)
btn_test.pack(fill="x", pady=2)

root.mainloop()
