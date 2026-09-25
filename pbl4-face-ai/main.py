"""
main.py — Entry point CLI cho hệ thống AI Điểm danh PBL4
Tổng hợp tất cả lệnh: register, verify, identify, evaluate, capture
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

BANNER = """
██████╗ ██████╗ ██╗     ██╗  ██╗    ███████╗ █████╗  ██████╗███████╗
██╔══██╗██╔══██╗██║     ██║  ██║    ██╔════╝██╔══██╗██╔════╝██╔════╝
██████╔╝██████╔╝██║     ███████║    █████╗  ███████║██║     █████╗  
██╔═══╝ ██╔══██╗██║     ╚════██║    ██╔══╝  ██╔══██║██║     ██╔══╝  
██║     ██████╔╝███████╗     ██║    ██║     ██║  ██║╚██████╗███████╗
╚═╝     ╚═════╝ ╚══════╝     ╚═╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
   AI Điểm Danh Sinh Viên — InsightFace + ArcFace  (PBL4 - 2026)
"""

COMMANDS_HELP = {
    "register folder": "Đăng ký sinh viên từ folder ảnh",
    "register webcam": "Đăng ký sinh viên qua webcam",
    "register list":   "Xem danh sách đã đăng ký",
    "verify":          "Xác minh 1:1 (ảnh hoặc webcam)",
    "identify":        "Nhận dạng 1:N trong toàn bộ DB",
    "capture":         "Thu ảnh từ webcam vào dataset",
    "evaluate":        "Đánh giá ngưỡng FAR/FRR/EER",
}


def print_help():
    console.print(f"[bold cyan]{BANNER}[/]")
    table = Table(title="📋 Danh sách Lệnh", show_lines=True, border_style="cyan")
    table.add_column("Lệnh",     style="bold yellow", min_width=25)
    table.add_column("Mô tả",    style="white")
    for cmd, desc in COMMANDS_HELP.items():
        table.add_row(f"python main.py {cmd}", desc)
    console.print(table)
    console.print("\n[dim]Ví dụ:[/]")
    console.print("  python main.py register folder --id SV001 --name 'Nguyen Van A' --images data/registered/SV001/")
    console.print("  python main.py register webcam --id SV001 --name 'Nguyen Van A'")
    console.print("  python main.py verify --id SV001 --image photo.jpg")
    console.print("  python main.py identify --webcam")
    console.print("  python main.py capture --id SV001 --name 'Nguyen Van A'")
    console.print("  python main.py evaluate")


if __name__ == "__main__":
    # Thêm src vào path
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    sys.path.insert(0, str(Path(__file__).parent / "scripts"))

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print_help()
        sys.exit(0)

    command = sys.argv[1]
    rest    = sys.argv[2:]

    # ── register ──────────────────────────────────────────────────────────────
    if command == "register":
        sys.argv = ["register"] + rest
        # Gọi lại argparse của register.py
        import runpy
        runpy.run_path(str(Path(__file__).parent / "src" / "register.py"), run_name="__main__")

    # ── verify ────────────────────────────────────────────────────────────────
    elif command == "verify":
        sys.argv = ["verify"] + rest
        import runpy
        runpy.run_path(str(Path(__file__).parent / "src" / "verify.py"), run_name="__main__")

    # ── identify ──────────────────────────────────────────────────────────────
    elif command == "identify":
        sys.argv = ["verify", "--identify"] + rest
        import runpy
        runpy.run_path(str(Path(__file__).parent / "src" / "verify.py"), run_name="__main__")

    # ── capture ───────────────────────────────────────────────────────────────
    elif command == "capture":
        sys.argv = ["capture"] + rest
        import runpy
        runpy.run_path(str(Path(__file__).parent / "scripts" / "capture_webcam.py"), run_name="__main__")

    # ── evaluate ──────────────────────────────────────────────────────────────
    elif command == "evaluate":
        sys.argv = ["evaluate"] + rest
        import runpy
        runpy.run_path(str(Path(__file__).parent / "src" / "evaluate.py"), run_name="__main__")

    else:
        console.print(f"[red]❌ Lệnh không hợp lệ: '{command}'[/]")
        print_help()
        sys.exit(1)
