"""
face_engine.py — Core module cho AI Điểm danh
Khởi tạo InsightFace (buffalo_l), detect face và tạo embedding ArcFace.
"""

import sys
import os

# Fix Windows console encoding cho emoji/Unicode
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np
from pathlib import Path
from insightface.app import FaceAnalysis
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ─── Cấu hình ────────────────────────────────────────────────────────────────
DEFAULT_MODEL   = "buffalo_sc"  # Dùng buffalo_sc (siêu nhẹ 16MB) để chạy mượt trên CPU
DEFAULT_CTX_ID  = -1            # -1 = CPU
DEFAULT_DET_SIZE = (640, 640)   # Kích thước detect


class FaceEngine:
    """
    Wrapper cho InsightFace FaceAnalysis.
    Cung cấp:
      - detect(image)  → list[Face]
      - embed(image)   → np.ndarray (512,) hoặc None
      - draw(image, faces) → image có vẽ bbox + tên
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        ctx_id: int = DEFAULT_CTX_ID,
        det_size: tuple = DEFAULT_DET_SIZE,
    ):
        console.print(f"[bold cyan]🚀 Đang khởi tạo InsightFace ({model_name})...[/]")
        self.app = FaceAnalysis(
            name=model_name,
            allowed_modules=["detection", "recognition"],
        )
        self.app.prepare(ctx_id=ctx_id, det_size=det_size)
        console.print("[bold green]✅ InsightFace sẵn sàng![/]")

    # ── Detect ────────────────────────────────────────────────────────────────
    def detect(self, image: np.ndarray, min_score: float = 0.5) -> list:
        """
        Phát hiện tất cả khuôn mặt trong ảnh.
        Args:
            image:     BGR numpy array (OpenCV format)
            min_score: Ngưỡng confidence tối thiểu (mặc định 0.5)
        Returns:
            list[Face] — mỗi Face có .bbox, .kps, .embedding, .det_score
        """
        faces = self.app.get(image)
        return [f for f in faces if f.det_score >= min_score]

    # ── Embed ─────────────────────────────────────────────────────────────────
    def embed(self, image: np.ndarray) -> np.ndarray | None:
        """
        Lấy embedding ArcFace 512-dim của khuôn mặt LỚN NHẤT trong ảnh.
        Args:
            image: BGR numpy array
        Returns:
            np.ndarray shape (512,) đã normalize, hoặc None nếu không tìm thấy mặt
        """
        faces = self.detect(image)
        if len(faces) != 1:
            return None

        # Chọn mặt có diện tích bbox lớn nhất
        main_face = max(faces, key=lambda f: _bbox_area(f.bbox))
        emb = main_face.embedding

        # L2-normalize
        norm = float(np.linalg.norm(emb))
        if emb.shape != (512,) or not np.isfinite(emb).all() or not np.isfinite(norm) or norm <= 0:
            return None
        emb = emb / norm
        return emb

    # ── Draw ──────────────────────────────────────────────────────────────────
    def draw(
        self,
        image: np.ndarray,
        faces: list,
        labels: list[str] | None = None,
    ) -> np.ndarray:
        """
        Vẽ bounding box và label lên ảnh.
        Args:
            image:  BGR numpy array
            faces:  list[Face] từ detect()
            labels: list tên tương ứng với từng face (optional)
        Returns:
            BGR numpy array có bbox + label
        """
        vis = image.copy()
        for i, face in enumerate(faces):
            x1, y1, x2, y2 = [int(v) for v in face.bbox]
            score = face.det_score

            # Màu khung
            color = (0, 220, 100)

            # Vẽ bbox
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            # Label
            if labels and i < len(labels):
                label_text = labels[i]
            else:
                label_text = f"Face {i+1} ({score:.2f})"

            # Background text
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                vis, label_text, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2,
            )

            # Vẽ landmarks (5 điểm)
            if face.kps is not None:
                for kp in face.kps:
                    cv2.circle(vis, (int(kp[0]), int(kp[1])), 3, (0, 100, 255), -1)

        return vis


# ── Cosine Similarity ─────────────────────────────────────────────────────────
def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Tính cosine similarity giữa 2 embedding đã normalize.
    Kết quả trong khoảng [-1, 1], càng gần 1 càng giống nhau.
    """
    return float(np.dot(emb1, emb2))


# ── Helper ────────────────────────────────────────────────────────────────────
def _bbox_area(bbox) -> float:
    x1, y1, x2, y2 = bbox
    return max(0, x2 - x1) * max(0, y2 - y1)


def load_image(path: str | Path) -> np.ndarray | None:
    """Đọc ảnh từ file, trả về BGR numpy array."""
    img = cv2.imread(str(path))
    if img is None:
        console.print(f"[red]❌ Không đọc được ảnh: {path}[/]")
    return img


# ─── CLI test nhanh ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test FaceEngine — detect + embed")
    parser.add_argument("--image", "-i", required=True, help="Đường dẫn ảnh đầu vào")
    parser.add_argument("--show", action="store_true", help="Hiện ảnh kết quả")
    args = parser.parse_args()

    img = load_image(args.image)
    if img is None:
        exit(1)

    engine = FaceEngine()
    faces  = engine.detect(img)

    # In kết quả
    table = Table(title="🔍 Kết quả Phát hiện Khuôn mặt", show_lines=True)
    table.add_column("Face #",      style="cyan")
    table.add_column("Det Score",   style="yellow")
    table.add_column("BBox",        style="white")
    table.add_column("Embedding",   style="green")

    for i, f in enumerate(faces):
        emb_info = f"shape={f.embedding.shape}, norm={np.linalg.norm(f.embedding):.4f}" \
                   if f.embedding is not None else "N/A"
        table.add_row(
            str(i + 1),
            f"{f.det_score:.4f}",
            f"[{int(f.bbox[0])}, {int(f.bbox[1])}, {int(f.bbox[2])}, {int(f.bbox[3])}]",
            emb_info,
        )

    console.print(table)
    console.print(Panel(f"[bold]Tổng số mặt phát hiện: {len(faces)}[/]", style="green"))

    # Hiện ảnh
    if args.show:
        vis = engine.draw(img, faces)
        cv2.imshow("FaceEngine Demo", vis)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
