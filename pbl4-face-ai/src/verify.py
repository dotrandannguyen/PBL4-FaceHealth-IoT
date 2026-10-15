"""
verify.py — Bước 3: Xác minh khuôn mặt 1:1
- Nhận student_id + ảnh mới (hoặc webcam)
- So sánh cosine similarity với embedding đã đăng ký
- Trả về MATCH / NO MATCH dựa trên ngưỡng
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
from rich.panel import Panel
from rich.table import Table

import sys
sys.path.insert(0, str(Path(__file__).parent))
from face_engine import FaceEngine, cosine_similarity, load_image

console = Console()

EMBEDDINGS_PATH = Path(__file__).parent.parent / "data" / "embeddings.pkl"

# Ngưỡng mặc định — sẽ tinh chỉnh ở Bước 4
DEFAULT_THRESHOLD = 0.45

# Cache DB trong memory để tránh đọc file pkl mỗi lần gọi
_DB_CACHE: dict | None = None


# ─── Load DB ──────────────────────────────────────────────────────────────────
def load_db(force_reload: bool = False) -> dict:
    global _DB_CACHE
    if _DB_CACHE is not None and not force_reload:
        return _DB_CACHE
    if not EMBEDDINGS_PATH.exists():
        console.print(f"[red]❌ Không tìm thấy database: {EMBEDDINGS_PATH}[/]")
        console.print("[yellow]→ Hãy đăng ký sinh viên trước bằng register.py[/]")
        return {}
    with open(EMBEDDINGS_PATH, "rb") as f:
        _DB_CACHE = pickle.load(f)
    return _DB_CACHE


# ─── Xác minh 1:1 ────────────────────────────────────────────────────────────
def verify_one(
    engine: FaceEngine,
    student_id: str,
    image: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """
    Xác minh: ảnh có phải là student_id không?

    Returns dict:
        {
          "student_id": str,
          "name": str,
          "similarity": float,
          "threshold": float,
          "match": bool,
          "probe_embedding": np.ndarray | None,
        }
    """
    db = load_db()
    result = {
        "student_id":       student_id,
        "name":             "N/A",
        "similarity":       -1.0,
        "threshold":        threshold,
        "match":            False,
        "probe_embedding":  None,
    }

    if not db:
        return result

    if student_id not in db:
        console.print(f"[red]❌ Sinh viên '{student_id}' chưa được đăng ký![/]")
        return result

    # Lấy embedding probe từ ảnh
    probe_emb = engine.embed(image)
    if probe_emb is None:
        console.print("[red]❌ Không phát hiện được khuôn mặt trong ảnh xác minh![/]")
        return result

    # Lấy embedding đã đăng ký
    registered = db[student_id]
    gallery_emb = registered["embedding"]
    result["name"] = registered["name"]

    # Tính cosine similarity
    sim = cosine_similarity(probe_emb, gallery_emb)
    result["similarity"]      = sim
    result["probe_embedding"] = probe_emb
    result["match"]           = sim >= threshold

    return result


# ─── Identify 1:N ─────────────────────────────────────────────────────────────
def identify(
    engine: FaceEngine,
    image: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """
    Nhận dạng 1:N — không cần biết trước là ai.
    Tìm người có similarity cao nhất trong toàn bộ DB.

    Returns dict với thông tin người tìm thấy hoặc "Unknown".
    """
    db = load_db()
    if not db:
        return {"match": False, "name": "Unknown", "student_id": None, "similarity": -1.0, "threshold": threshold}

    probe_emb = engine.embed(image)
    if probe_emb is None:
        return {"match": False, "name": "Unknown", "student_id": None, "similarity": -1.0, "threshold": threshold}

    best_id  = None
    best_sim = -1.0

    for sid, info in db.items():
        sim = cosine_similarity(probe_emb, info["embedding"])
        if sim > best_sim:
            best_sim = sim
            best_id  = sid

    matched = best_sim >= threshold
    return {
        "match":      matched,
        "student_id": best_id if matched else None,
        "name":       db[best_id]["name"] if matched else "Không xác định",
        "similarity": best_sim,
        "threshold":  threshold,
    }


# ─── In kết quả đẹp ──────────────────────────────────────────────────────────
def print_result(result: dict):
    match   = result["match"]
    sim     = result["similarity"]
    thresh  = result["threshold"]
    sid     = result["student_id"]
    name    = result["name"]

    if match:
        style = "bold green"
        icon  = "✅ MATCH"
    else:
        style = "bold red"
        icon  = "❌ NO MATCH"

    # Thanh similarity trực quan
    bar_len  = 30
    filled   = int(bar_len * max(0, sim))
    bar      = "█" * filled + "░" * (bar_len - filled)

    console.print(Panel(
        f"[{style}]{icon}[/]\n\n"
        f"Student ID : [cyan]{sid}[/]\n"
        f"Tên        : [cyan]{name}[/]\n"
        f"Similarity : [yellow]{sim:.4f}[/]  [{bar}]\n"
        f"Ngưỡng     : {thresh}  ({'≥ threshold → MATCH' if match else '< threshold → NO MATCH'})",
        title="🔍 Kết quả Xác minh",
        border_style="green" if match else "red",
    ))


# ─── Webcam real-time verify ──────────────────────────────────────────────────
def verify_realtime(
    engine: FaceEngine,
    student_id: str,
    threshold: float = DEFAULT_THRESHOLD,
    mode: str = "verify",   # "verify" (1:1) hoặc "identify" (1:N)
):
    """
    Xác minh real-time qua webcam.
    Nhấn SPACE để chụp và xác minh, Q để thoát.
    """
    db = load_db()
    if not db:
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        console.print("[red]❌ Không mở được webcam![/]")
        return

    console.print(Panel(
        f"[bold]Chế độ: {'1:1 Verify' if mode == 'verify' else '1:N Identify'}[/]\n"
        f"→ [cyan]SPACE[/]: chụp & xác minh\n"
        f"→ [red]Q[/]: thoát",
        title="📷 Webcam Verify",
        border_style="cyan",
    ))

    last_result = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        faces = engine.detect(frame)
        vis   = engine.draw(frame, faces)

        # Hiện kết quả lần trước (nếu có)
        if last_result:
            color = (0, 200, 0) if last_result["match"] else (0, 0, 220)
            label = f"{last_result['name']} ({last_result['similarity']:.3f})"
            cv2.putText(vis, label, (10, frame.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.putText(vis, "SPACE=xac minh  Q=thoat", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
        cv2.imshow("Verify", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            if mode == "verify":
                last_result = verify_one(engine, student_id, frame, threshold)
            else:
                last_result = identify(engine, frame, threshold)
            print_result(last_result)

    cap.release()
    cv2.destroyAllWindows()


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xác minh khuôn mặt sinh viên")
    parser.add_argument("--id",        help="Student ID cần xác minh (chỉ dùng cho mode 1:1)")
    parser.add_argument("--image",     help="Đường dẫn ảnh probe")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Ngưỡng cosine similarity (mặc định: {DEFAULT_THRESHOLD})")
    parser.add_argument("--webcam",    action="store_true",  help="Dùng webcam real-time")
    parser.add_argument("--identify",  action="store_true",  help="Chế độ 1:N (không cần --id)")
    args = parser.parse_args()

    engine = FaceEngine()

    if args.webcam:
        mode = "identify" if args.identify else "verify"
        verify_realtime(engine, args.id or "", args.threshold, mode)

    elif args.image:
        img = load_image(args.image)
        if img is None:
            exit(1)

        if args.identify:
            result = identify(engine, img, args.threshold)
        else:
            if not args.id:
                console.print("[red]❌ Cần --id khi xác minh 1:1[/]")
                exit(1)
            result = verify_one(engine, args.id, img, args.threshold)

        print_result(result)

    else:
        parser.print_help()
