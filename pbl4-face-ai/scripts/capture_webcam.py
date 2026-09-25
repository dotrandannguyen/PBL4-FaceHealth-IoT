"""
capture_webcam.py — Script thu ảnh từ webcam để tạo dataset
Dùng cho cả đăng ký (registered/) và đánh giá (test/)
"""

import cv2
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console  = Console()
DATA_DIR = Path(__file__).parent.parent / "data"


def capture(
    student_id: str,
    student_name: str,
    mode: str = "registered",   # "registered" hoặc "test"
    n_samples: int = 10,
    camera_id: int = 0,
):
    """
    Thu ảnh từ webcam, lưu vào data/<mode>/<student_id>/.
    Nhấn SPACE để chụp, Q để thoát.
    """
    save_dir = DATA_DIR / mode / student_id
    save_dir.mkdir(parents=True, exist_ok=True)

    # Đếm ảnh hiện có
    existing = len(list(save_dir.glob("*.jpg")))

    console.print(Panel(
        f"[bold]Thu ảnh: {student_name} ({student_id})[/]\n"
        f"Lưu tại  : [cyan]{save_dir}[/]\n"
        f"Đã có    : [yellow]{existing} ảnh[/]\n"
        f"Cần thu  : [green]{n_samples} ảnh mới[/]\n\n"
        f"→ [cyan]SPACE[/] : Chụp ảnh\n"
        f"→ [yellow]A[/]     : Auto chụp mỗi 1 giây\n"
        f"→ [red]Q[/]     : Thoát",
        title="📷 Thu Ảnh Webcam",
        border_style="cyan",
    ))

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        console.print(f"[red]❌ Không mở được camera {camera_id}![/]")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    count      = 0
    auto_mode  = False
    auto_timer = 0

    while count < n_samples:
        ret, frame = cap.read()
        if not ret:
            break

        vis = frame.copy()

        # HUD
        color = (0, 200, 0) if count > 0 else (0, 200, 255)
        cv2.putText(vis, f"Da chup: {count}/{n_samples}", (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        cv2.putText(vis, f"ID: {student_id} | {student_name}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        cv2.putText(vis, "SPACE=chup  A=auto  Q=thoat", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)

        if auto_mode:
            cv2.putText(vis, "AUTO MODE", (vis.shape[1] - 160, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 100, 255), 2)

        cv2.imshow(f"Thu anh: {student_id}", vis)

        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("a"):
            auto_mode = not auto_mode
            console.print(f"[yellow]{'🔴 AUTO ON' if auto_mode else '⚪ AUTO OFF'}[/]")
            auto_timer = 0

        # Chụp ảnh
        should_capture = (key == ord(" ")) or (auto_mode and auto_timer >= 33)  # ~1s

        if should_capture:
            img_idx  = existing + count + 1
            img_path = save_dir / f"{student_id}_{img_idx:04d}.jpg"
            cv2.imwrite(str(img_path), frame)
            count += 1
            auto_timer = 0
            console.print(f"[green]📸 [{count}/{n_samples}] Lưu: {img_path.name}[/]")

        if auto_mode:
            auto_timer += 1

    cap.release()
    cv2.destroyAllWindows()

    console.print(Panel(
        f"[bold green]✅ Hoàn thành![/]\n"
        f"Đã thu: [cyan]{count}[/] ảnh\n"
        f"Tổng  : [cyan]{existing + count}[/] ảnh trong {save_dir}",
        title="📷 Kết quả",
        border_style="green",
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Thu ảnh webcam cho dataset")
    parser.add_argument("--id",      required=True,  help="Student ID (VD: SV001)")
    parser.add_argument("--name",    required=True,  help="Tên sinh viên")
    parser.add_argument("--mode",    default="registered", choices=["registered", "test"],
                        help="Lưu vào registered/ hay test/ (mặc định: registered)")
    parser.add_argument("--samples", type=int, default=10, help="Số ảnh cần thu (mặc định: 10)")
    parser.add_argument("--camera",  type=int, default=0,  help="Camera ID (mặc định: 0)")
    args = parser.parse_args()

    capture(args.id, args.name, args.mode, args.samples, args.camera)
