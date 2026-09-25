"""
register.py — Bước 2: Đăng ký khuôn mặt sinh viên
- Nhận student_id + folder ảnh (hoặc webcam)
- Tạo embedding trung bình → lưu vào embeddings.pkl
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import pickle
import argparse
import numpy as np
from pathlib import Path
from rich.console import Console
from rich.progress import track
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

# Thêm src vào path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from face_engine import FaceEngine, load_image

console = Console()

EMBEDDINGS_PATH = Path(__file__).parent.parent / "data" / "embeddings.pkl"
REGISTERED_DIR  = Path(__file__).parent.parent / "data" / "registered"


# ─── Load / Save database ─────────────────────────────────────────────────────
def load_db() -> dict:
    """Load database embedding từ file pkl."""
    if EMBEDDINGS_PATH.exists():
        with open(EMBEDDINGS_PATH, "rb") as f:
            return pickle.load(f)
    return {}


def save_db(db: dict):
    """Lưu database embedding ra file pkl."""
    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EMBEDDINGS_PATH, "wb") as f:
        pickle.dump(db, f)
    console.print(f"[green]💾 Đã lưu database: {EMBEDDINGS_PATH}[/]")


# ─── Đăng ký từ folder ảnh ────────────────────────────────────────────────────
def register_from_folder(
    engine: FaceEngine,
    student_id: str,
    student_name: str,
    folder: Path,
) -> bool:
    """
    Đọc tất cả ảnh trong folder, tạo embedding trung bình, lưu vào DB.
    Returns: True nếu thành công
    """
    img_paths = sorted([
        p for p in folder.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    ])

    if not img_paths:
        console.print(f"[red]❌ Không tìm thấy ảnh trong {folder}[/]")
        return False

    console.print(f"[cyan]📂 Tìm thấy {len(img_paths)} ảnh trong {folder}[/]")

    embeddings = []
    failed = 0

    for path in track(img_paths, description=f"[cyan]Đang xử lý {student_id}..."):
        img = load_image(path)
        if img is None:
            failed += 1
            continue

        emb = engine.embed(img)
        if emb is None:
            console.print(f"[yellow]⚠️  Không detect được mặt: {path.name}[/]")
            failed += 1
            continue

        embeddings.append(emb)

    if not embeddings:
        console.print(f"[red]❌ Không tạo được embedding nào cho {student_id}[/]")
        return False

    # Tính embedding trung bình và normalize lại
    mean_emb = np.mean(embeddings, axis=0)
    mean_emb = mean_emb / np.linalg.norm(mean_emb)

    # Lưu vào DB
    db = load_db()
    db[student_id] = {
        "name":      student_name,
        "embedding": mean_emb,
        "n_images":  len(embeddings),
    }
    save_db(db)

    console.print(Panel(
        f"[bold green]✅ Đăng ký thành công![/]\n"
        f"ID    : [cyan]{student_id}[/]\n"
        f"Tên   : [cyan]{student_name}[/]\n"
        f"Ảnh OK: [cyan]{len(embeddings)}/{len(img_paths)}[/] "
        f"([yellow]{failed} lỗi[/])\n"
        f"Embedding: shape={mean_emb.shape}, norm={np.linalg.norm(mean_emb):.4f}",
        title="📝 Kết quả Đăng ký",
        border_style="green",
    ))
    return True


# ─── Đăng ký từ webcam (có hướng dẫn) ─────────────────────────────────────────

# Các bước chụp — mỗi bước 1 góc mặt
CAPTURE_STEPS = [
    {"name": "Nhin thang",     "icon": "O",  "hint": "Nhin thang vao camera"},
    {"name": "Xoay trai",      "icon": "<",  "hint": "Xoay mat sang TRAI nhe"},
    {"name": "Xoay phai",      "icon": ">",  "hint": "Xoay mat sang PHAI nhe"},
    {"name": "Ngang len",      "icon": "^",  "hint": "Ngang mat LEN nhe"},
    {"name": "Cui xuong",      "icon": "v",  "hint": "Cui mat XUONG nhe"},
]


def register_from_webcam(
    engine: FaceEngine,
    student_id: str,
    student_name: str,
    n_samples: int = 5,
) -> bool:
    """
    Thu ảnh từ webcam CÓ HƯỚNG DẪN từng bước xoay mặt.
    Tự động chụp khi detect được mặt + nhấn SPACE, hoặc auto sau countdown.
    """
    import time

    save_dir = REGISTERED_DIR / student_id
    save_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        console.print("[red]Khong mo duoc webcam![/]")
        return False

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    console.print(Panel(
        f"[bold]Dang ky: {student_name} ({student_id})[/]\n"
        f"Se chup {n_samples} anh theo huong dan tren man hinh.\n"
        f"Nhan [cyan]SPACE[/] de chup | [red]Q[/] de thoat",
        title="Dang ky Webcam",
        border_style="cyan",
    ))

    # Nếu n_samples khác 5, lặp lại các bước
    steps = []
    for i in range(n_samples):
        steps.append(CAPTURE_STEPS[i % len(CAPTURE_STEPS)])

    embeddings = []
    current_step = 0
    flash_timer = 0       # countdown hiệu ứng flash khi chụp xong
    ready_timer = 0       # đếm frame có mặt liên tục (cho auto-capture)
    READY_FRAMES = 40     # ~1.3 giây detect mặt liên tục → auto chụp

    while current_step < n_samples:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        vis = frame.copy()
        step_info = steps[current_step]

        # Detect faces
        faces = engine.detect(frame)
        has_face = len(faces) > 0

        # Vẽ faces
        if has_face:
            for face in faces:
                x1, y1, x2, y2 = [int(v) for v in face.bbox]
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 220, 100), 2)
                if face.kps is not None:
                    for kp in face.kps:
                        cv2.circle(vis, (int(kp[0]), int(kp[1])), 3, (0, 100, 255), -1)

        # ── HUD Background (trên) ────────────────────────────────────────────
        overlay = vis.copy()
        cv2.rectangle(overlay, (0, 0), (w, 100), (20, 20, 40), -1)
        vis = cv2.addWeighted(overlay, 0.7, vis, 0.3, 0)
        # Khôi phục phần dưới
        vis[100:] = frame[100:] if not has_face else vis[100:]
        # Re-draw faces on non-overlay area
        if has_face:
            for face in faces:
                x1, y1, x2, y2 = [int(v) for v in face.bbox]
                if y1 >= 100:
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 220, 100), 2)
                if face.kps is not None:
                    for kp in face.kps:
                        if int(kp[1]) >= 100:
                            cv2.circle(vis, (int(kp[0]), int(kp[1])), 3, (0, 100, 255), -1)

        # ── Thông tin bước hiện tại ──────────────────────────────────────────
        progress_text = f"Buoc {current_step + 1}/{n_samples}"
        cv2.putText(vis, progress_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)

        cv2.putText(vis, f"ID: {student_id} | {student_name}", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Hướng dẫn chính — to và rõ
        hint_text = f">> {step_info['hint']} <<"
        (tw, th), _ = cv2.getTextSize(hint_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        hint_x = (w - tw) // 2
        cv2.putText(vis, hint_text, (hint_x, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 200), 2)

        # ── Trạng thái detect ────────────────────────────────────────────────
        if has_face:
            ready_timer += 1
            # Thanh tiến trình auto-capture
            progress_ratio = min(ready_timer / READY_FRAMES, 1.0)
            bar_w = int((w - 40) * progress_ratio)
            cv2.rectangle(vis, (20, h - 50), (20 + bar_w, h - 35), (0, 220, 100), -1)
            cv2.rectangle(vis, (20, h - 50), (w - 20, h - 35), (100, 100, 100), 1)

            if progress_ratio < 1.0:
                status_text = f"Dang nhan dien... SPACE=chup ngay ({int(progress_ratio*100)}%)"
                cv2.putText(vis, status_text, (20, h - 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 100), 1)
            else:
                status_text = "San sang! Dang chup..."
                cv2.putText(vis, status_text, (20, h - 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        else:
            ready_timer = 0
            cv2.putText(vis, "Khong thay mat — hay dua mat vao camera",
                        (20, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1)

        # ── Footer ───────────────────────────────────────────────────────────
        cv2.putText(vis, "SPACE=chup  |  Q=thoat", (20, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

        # ── Flash xanh khi vừa chụp xong ─────────────────────────────────────
        if flash_timer > 0:
            flash_overlay = vis.copy()
            cv2.rectangle(flash_overlay, (0, 0), (w, h), (0, 255, 100), -1)
            alpha = flash_timer / 15.0  # fade out
            vis = cv2.addWeighted(flash_overlay, alpha * 0.3, vis, 1 - alpha * 0.3, 0)

            done_text = f"OK! Da chup buoc {current_step}/{n_samples}"
            (tw2, _), _ = cv2.getTextSize(done_text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)
            cv2.putText(vis, done_text, ((w - tw2) // 2, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 100), 3)
            flash_timer -= 1

        cv2.imshow(f"Dang ky: {student_id}", vis)

        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            console.print("[yellow]Da huy dang ky.[/]")
            break

        # ── Chụp: SPACE hoặc auto khi ready đủ lâu ──────────────────────────
        should_capture = (key == ord(" ") and has_face) or (ready_timer >= READY_FRAMES)

        if should_capture and flash_timer <= 0:
            emb = engine.embed(frame)
            if emb is not None:
                current_step += 1
                embeddings.append(emb)

                # Lưu ảnh gốc
                img_path = save_dir / f"{student_id}_{current_step:03d}.jpg"
                cv2.imwrite(str(img_path), frame)

                console.print(
                    f"[green]Buoc {current_step}/{n_samples} OK: "
                    f"{step_info['name']} — {img_path.name}[/]"
                )

                flash_timer = 15  # hiệu ứng flash 15 frames (~0.5s)
                ready_timer = 0

    cap.release()
    cv2.destroyAllWindows()

    if not embeddings:
        console.print("[red]Khong chup duoc anh nao![/]")
        return False

    # Tính mean embedding
    mean_emb = np.mean(embeddings, axis=0)
    mean_emb = mean_emb / np.linalg.norm(mean_emb)

    db = load_db()
    db[student_id] = {
        "name":      student_name,
        "embedding": mean_emb,
        "n_images":  len(embeddings),
    }
    save_db(db)

    console.print(Panel(
        f"[bold green]DANG KY THANH CONG![/]\n"
        f"ID  : [cyan]{student_id}[/]\n"
        f"Ten : [cyan]{student_name}[/]\n"
        f"Anh : [cyan]{len(embeddings)}/{n_samples}[/] (luu tai {save_dir})",
        title="Ket qua Dang ky",
        border_style="green",
    ))
    return True


# ─── List database ────────────────────────────────────────────────────────────
def list_db():
    """Hiện danh sách sinh viên đã đăng ký."""
    from rich.table import Table
    db = load_db()

    if not db:
        console.print("[yellow]⚠️  Database trống, chưa có ai đăng ký.[/]")
        return

    table = Table(title="📋 Danh sách Sinh viên Đã Đăng ký", show_lines=True)
    table.add_column("STT",       style="dim")
    table.add_column("Student ID", style="cyan")
    table.add_column("Tên",        style="bold white")
    table.add_column("Số ảnh",    style="yellow")
    table.add_column("Embedding", style="green")

    for i, (sid, info) in enumerate(db.items(), 1):
        emb = info["embedding"]
        table.add_row(
            str(i),
            sid,
            info["name"],
            str(info.get("n_images", "?")),
            f"shape={emb.shape}, norm={np.linalg.norm(emb):.4f}",
        )

    console.print(table)


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đăng ký khuôn mặt sinh viên")
    subparsers = parser.add_subparsers(dest="command")

    # register from folder
    p_folder = subparsers.add_parser("folder", help="Đăng ký từ folder ảnh")
    p_folder.add_argument("--id",     required=True,  help="Student ID (VD: SV001)")
    p_folder.add_argument("--name",   required=True,  help="Tên sinh viên")
    p_folder.add_argument("--images", required=True,  help="Đường dẫn folder ảnh")

    # register from webcam
    p_webcam = subparsers.add_parser("webcam", help="Đăng ký qua webcam")
    p_webcam.add_argument("--id",      required=True, help="Student ID")
    p_webcam.add_argument("--name",    required=True, help="Tên sinh viên")
    p_webcam.add_argument("--samples", type=int, default=5, help="Số ảnh cần chụp (mặc định: 5)")

    # list
    subparsers.add_parser("list", help="Xem danh sách đã đăng ký")

    args = parser.parse_args()

    if args.command == "list" or args.command is None:
        list_db()
        exit(0)

    engine = FaceEngine()

    if args.command == "folder":
        register_from_folder(engine, args.id, args.name, Path(args.images))

    elif args.command == "webcam":
        register_from_webcam(engine, args.id, args.name, args.samples)
