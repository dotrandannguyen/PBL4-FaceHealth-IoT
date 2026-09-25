"""
evaluate.py — Bước 4: Đánh giá ngưỡng FAR / FRR / EER
- Tính similarity cho tất cả cặp ảnh (genuine + impostor)
- Vẽ biểu đồ FAR / FRR theo ngưỡng
- Tìm EER (Equal Error Rate) → đề xuất ngưỡng tối ưu
"""

import cv2
import pickle
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from itertools import combinations, product
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import track
from scipy.optimize import brentq
from scipy.interpolate import interp1d

import sys
sys.path.insert(0, str(Path(__file__).parent))
from face_engine import FaceEngine, cosine_similarity, load_image

console     = Console()
DATA_DIR    = Path(__file__).parent.parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.pkl"
TEST_DIR    = DATA_DIR / "test"
OUTPUT_DIR  = DATA_DIR / "eval_results"


# ─── Load DB ──────────────────────────────────────────────────────────────────
def load_db() -> dict:
    if not EMBEDDINGS_PATH.exists():
        console.print(f"[red]❌ Không tìm thấy {EMBEDDINGS_PATH}[/]")
        return {}
    with open(EMBEDDINGS_PATH, "rb") as f:
        return pickle.load(f)


# ─── Tạo các cặp Genuine & Impostor từ ảnh test ──────────────────────────────
def build_pairs_from_test(engine: FaceEngine, db: dict) -> tuple[list, list]:
    """
    Đọc thư mục test/ (cấu trúc test/<student_id>/img.jpg)
    Tạo:
      - genuine_scores: similarity của cùng 1 người
      - impostor_scores: similarity của 2 người khác nhau
    """
    if not TEST_DIR.exists():
        console.print(f"[red]❌ Không tìm thấy thư mục test: {TEST_DIR}[/]")
        console.print("[yellow]→ Tạo cấu trúc: data/test/<student_id>/<img.jpg>[/]")
        return [], []

    # Đọc embedding từng ảnh test
    test_data: dict[str, list[np.ndarray]] = {}

    for sid_dir in sorted(TEST_DIR.iterdir()):
        if not sid_dir.is_dir():
            continue
        sid   = sid_dir.name
        embs  = []

        img_paths = [
            p for p in sid_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
        ]
        for img_path in track(img_paths, description=f"[cyan]Test {sid}..."):
            img = load_image(img_path)
            if img is None:
                continue
            emb = engine.embed(img)
            if emb is not None:
                embs.append(emb)

        if embs:
            test_data[sid] = embs
            console.print(f"  [green]{sid}[/]: {len(embs)} ảnh OK")

    if len(test_data) < 2:
        console.print("[red]❌ Cần ít nhất 2 sinh viên trong thư mục test![/]")
        return [], []

    # Genuine pairs (cùng người, khác ảnh)
    genuine_scores = []
    for sid, embs in test_data.items():
        gallery_emb = db.get(sid, {}).get("embedding")
        for emb in embs:
            if gallery_emb is not None:
                genuine_scores.append(cosine_similarity(emb, gallery_emb))

    # Impostor pairs (khác người)
    impostor_scores = []
    sids = list(test_data.keys())
    for i, sid_a in enumerate(sids):
        for sid_b in sids[i+1:]:
            for emb_a in test_data[sid_a]:
                gallery_b = db.get(sid_b, {}).get("embedding")
                if gallery_b is not None:
                    impostor_scores.append(cosine_similarity(emb_a, gallery_b))

    console.print(f"\n[bold]Genuine pairs  : {len(genuine_scores)}[/]")
    console.print(f"[bold]Impostor pairs : {len(impostor_scores)}[/]")
    return genuine_scores, impostor_scores


# ─── Tính FAR / FRR ──────────────────────────────────────────────────────────
def compute_far_frr(
    genuine_scores: list[float],
    impostor_scores: list[float],
    thresholds: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    FAR (False Accept Rate): impostor bị nhận nhầm là genuine.
    FRR (False Reject Rate): genuine bị từ chối.
    """
    gen = np.array(genuine_scores)
    imp = np.array(impostor_scores)

    far = np.array([np.mean(imp >= t) for t in thresholds])
    frr = np.array([np.mean(gen <  t) for t in thresholds])
    return far, frr


# ─── Tìm EER ─────────────────────────────────────────────────────────────────
def find_eer(
    far: np.ndarray,
    frr: np.ndarray,
    thresholds: np.ndarray,
) -> tuple[float, float]:
    """Tìm điểm EER (FAR == FRR) qua nội suy."""
    try:
        eer_threshold = brentq(interp1d(thresholds, far - frr), thresholds[0], thresholds[-1])
        eer_value     = interp1d(thresholds, (far + frr) / 2)(eer_threshold)
    except Exception:
        # Fallback: tìm điểm gần nhất
        diff = np.abs(far - frr)
        idx  = np.argmin(diff)
        eer_threshold = thresholds[idx]
        eer_value     = (far[idx] + frr[idx]) / 2

    return float(eer_threshold), float(eer_value)


# ─── Vẽ biểu đồ ─────────────────────────────────────────────────────────────
def plot_results(
    genuine_scores: list,
    impostor_scores: list,
    far: np.ndarray,
    frr: np.ndarray,
    thresholds: np.ndarray,
    eer_threshold: float,
    eer_value: float,
):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(16, 10), facecolor="#1a1a2e")
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    text_color  = "#e0e0e0"
    grid_color  = "#333355"

    # ── 1. Histogram phân phối similarity ─────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#0f0f1a")
    ax1.hist(genuine_scores,  bins=40, alpha=0.75, color="#00c896", label="Genuine",  edgecolor="white", linewidth=0.3)
    ax1.hist(impostor_scores, bins=40, alpha=0.75, color="#ff6b6b", label="Impostor", edgecolor="white", linewidth=0.3)
    ax1.axvline(eer_threshold, color="#ffd700", linewidth=2, linestyle="--", label=f"EER Threshold: {eer_threshold:.3f}")
    ax1.set_title("Phân phối Cosine Similarity", color=text_color, fontsize=12, fontweight="bold")
    ax1.set_xlabel("Cosine Similarity", color=text_color)
    ax1.set_ylabel("Số lượng", color=text_color)
    ax1.tick_params(colors=text_color)
    ax1.legend(facecolor="#1a1a2e", labelcolor=text_color, fontsize=9)
    ax1.grid(True, color=grid_color, alpha=0.5)

    # ── 2. FAR & FRR theo ngưỡng ──────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#0f0f1a")
    ax2.plot(thresholds, far * 100, color="#ff6b6b", linewidth=2, label="FAR (%)")
    ax2.plot(thresholds, frr * 100, color="#00c896", linewidth=2, label="FRR (%)")
    ax2.axvline(eer_threshold, color="#ffd700", linewidth=2, linestyle="--",
                label=f"EER={eer_value*100:.2f}% @ {eer_threshold:.3f}")
    ax2.scatter([eer_threshold], [eer_value * 100], color="#ffd700", s=80, zorder=5)
    ax2.set_title("FAR & FRR theo Ngưỡng", color=text_color, fontsize=12, fontweight="bold")
    ax2.set_xlabel("Ngưỡng (Threshold)", color=text_color)
    ax2.set_ylabel("Tỷ lệ (%)", color=text_color)
    ax2.tick_params(colors=text_color)
    ax2.legend(facecolor="#1a1a2e", labelcolor=text_color, fontsize=9)
    ax2.grid(True, color=grid_color, alpha=0.5)

    # ── 3. ROC Curve ─────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#0f0f1a")
    ax3.plot(far * 100, (1 - frr) * 100, color="#7b68ee", linewidth=2, label="ROC Curve")
    ax3.scatter([eer_value * 100], [(1 - eer_value) * 100], color="#ffd700", s=80, zorder=5, label=f"EER Point")
    ax3.plot([0, 100], [0, 100], color=grid_color, linestyle="--", linewidth=1)
    ax3.set_title("ROC Curve", color=text_color, fontsize=12, fontweight="bold")
    ax3.set_xlabel("FAR (%)", color=text_color)
    ax3.set_ylabel("TAR = 1 - FRR (%)", color=text_color)
    ax3.tick_params(colors=text_color)
    ax3.legend(facecolor="#1a1a2e", labelcolor=text_color, fontsize=9)
    ax3.grid(True, color=grid_color, alpha=0.5)

    # ── 4. Bảng kết quả tóm tắt ─────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#0f0f1a")
    ax4.axis("off")

    summary_data = [
        ["Chỉ số",                  "Giá trị"],
        ["EER Threshold",           f"{eer_threshold:.4f}"],
        ["EER Value",               f"{eer_value*100:.2f}%"],
        ["FAR @ EER",               f"{eer_value*100:.2f}%"],
        ["FRR @ EER",               f"{eer_value*100:.2f}%"],
        ["Genuine pairs",           str(len(genuine_scores))],
        ["Impostor pairs",          str(len(impostor_scores))],
        ["Genuine mean sim",        f"{np.mean(genuine_scores):.4f}"],
        ["Impostor mean sim",       f"{np.mean(impostor_scores):.4f}"],
        ["Khuyến nghị dùng",        f"{eer_threshold:.3f}"],
    ]

    tbl = ax4.table(
        cellText=summary_data[1:],
        colLabels=summary_data[0],
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#1e1e3a" if r % 2 == 0 else "#0f0f2a")
        cell.set_edgecolor("#333355")
        cell.set_text_props(color=text_color)

    ax4.set_title("📊 Tóm tắt Kết quả", color=text_color, fontsize=12, fontweight="bold")

    # Title chính
    fig.suptitle(
        "🎯 Đánh giá Ngưỡng Nhận diện Khuôn mặt — PBL4",
        color=text_color, fontsize=14, fontweight="bold", y=0.98,
    )

    out_path = OUTPUT_DIR / "threshold_evaluation.png"
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.show()
    console.print(f"[green]📊 Đã lưu biểu đồ: {out_path}[/]")


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đánh giá ngưỡng FAR/FRR")
    parser.add_argument("--thresholds", nargs=2, type=float, default=[0.1, 0.9],
                        metavar=("MIN", "MAX"), help="Khoảng ngưỡng cần quét (mặc định: 0.1 0.9)")
    parser.add_argument("--steps", type=int, default=200, help="Số bước quét (mặc định: 200)")
    parser.add_argument("--no-plot", action="store_true", help="Không vẽ biểu đồ")
    args = parser.parse_args()

    db = load_db()
    if not db:
        exit(1)

    engine = FaceEngine()

    console.print("\n[bold cyan]📂 Đang tải ảnh test và tính similarity...[/]")
    genuine_scores, impostor_scores = build_pairs_from_test(engine, db)

    if not genuine_scores or not impostor_scores:
        console.print("[red]❌ Không đủ dữ liệu để đánh giá![/]")
        exit(1)

    # Tính FAR / FRR
    thresholds = np.linspace(args.thresholds[0], args.thresholds[1], args.steps)
    far, frr   = compute_far_frr(genuine_scores, impostor_scores, thresholds)

    # Tìm EER
    eer_threshold, eer_value = find_eer(far, frr, thresholds)

    # In kết quả
    table = Table(title="📊 Kết quả Đánh giá Ngưỡng", show_lines=True)
    table.add_column("Chỉ số",    style="cyan")
    table.add_column("Giá trị",   style="bold yellow")
    table.add_row("EER Threshold",    f"{eer_threshold:.4f}")
    table.add_row("EER Value",        f"{eer_value * 100:.2f}%")
    table.add_row("Genuine pairs",    str(len(genuine_scores)))
    table.add_row("Impostor pairs",   str(len(impostor_scores)))
    table.add_row("Genuine mean",     f"{np.mean(genuine_scores):.4f}")
    table.add_row("Impostor mean",    f"{np.mean(impostor_scores):.4f}")
    console.print(table)

    console.print(Panel(
        f"[bold green]🎯 Ngưỡng khuyến nghị: [yellow]{eer_threshold:.3f}[/][/]\n"
        f"Sử dụng trong verify.py: [cyan]--threshold {eer_threshold:.3f}[/]",
        title="💡 Kết luận",
        border_style="green",
    ))

    if not args.no_plot:
        plot_results(genuine_scores, impostor_scores, far, frr,
                     thresholds, eer_threshold, eer_value)
