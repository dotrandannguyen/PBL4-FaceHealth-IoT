import sys
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
from pathlib import Path
from rich.console import Console

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

console = Console()

DATA_DIR = Path(__file__).parent.parent / "data"
CSV_FILE = DATA_DIR / "status_dataset.csv"
MODEL_FILE = DATA_DIR / "rf_status_model.pkl"

def main():
    if not CSV_FILE.exists():
        console.print(f"[red]❌ Không tìm thấy file dữ liệu {CSV_FILE}[/]")
        return
        
    console.print(f"[cyan]Đang đọc dữ liệu từ {CSV_FILE.name}...[/]")
    df = pd.read_csv(CSV_FILE)
    
    total_samples = len(df)
    if total_samples < 20:
        console.print("[yellow]⚠️ CẢNH BÁO: Dữ liệu quá ít (ít hơn 20 dòng). Để AI dự đoán chính xác, bạn nên chạy lại collect_status.py và thu thập thêm khoảng 40-50 dòng dữ liệu nữa![/yellow]")

    # Tính năng (Features): min_ear, mean_ear, max_mar, mean_mar, delta_pitch, delta_roll, mean_pitch
    X = df.drop(columns=['label'])
    y = df['label']

    # Chia tập train/test (80/20)
    test_size = 0.2 if total_samples > 10 else 0.1
    try:
        # Cố gắng chia cân bằng nhãn
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42, stratify=y if total_samples > 15 else None)
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)

    console.print(f"Tổng số mẫu: [green]{total_samples}[/], Train: [green]{len(X_train)}[/], Test: [green]{len(X_test)}[/]")

    # Khởi tạo mô hình Random Forest (siêu nhẹ, suy luận dưới 5ms)
    console.print("\n[cyan]Đang huấn luyện Random Forest...[/]")
    rf_model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    rf_model.fit(X_train, y_train)

    # Đánh giá trên tập Test
    y_pred = rf_model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    console.print(f"\n[bold]Kết quả Đánh giá:[/bold]")
    console.print(f"Độ chính xác (Accuracy): [bold green]{acc * 100:.2f}%[/]")
    
    if len(y_test) > 2:
        console.print("\n[bold]Báo cáo chi tiết từng nhãn:[/bold]")
        print(classification_report(y_test, y_pred, zero_division=0))

    # Lưu model nhị phân PKL
    joblib.dump(rf_model, MODEL_FILE)
    console.print(f"\n[bold green]✅ Đã lưu mô hình thành công: {MODEL_FILE}[/bold green]")

if __name__ == "__main__":
    main()
