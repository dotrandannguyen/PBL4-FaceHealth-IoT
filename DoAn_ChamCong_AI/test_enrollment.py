"""
test_enrollment.py — Test face enrollment Phase 1 (no Flask)
=============================================================
Test truc tiep:
1. FaceAnalysis init
2. Camera capture
3. extract_embedding (real InsightFace)
4. insert_face_embedding vao DB
5. Verify DATALENGTH, shape, L2 norm
"""

import sys
import time
import numpy as np

print("=" * 60)
print("FACE ENROLLMENT PHASE 1 — TEST SCRIPT")
print("=" * 60)

# ── 1. Import ────────────────────────────────────────────────
print("\n[1] Import modules...")
try:
    import database
    print("    [OK] database")
except Exception as e:
    print(f"    [FAIL] database: {e}"); sys.exit(1)

try:
    import services
    print("    [OK] services")
except Exception as e:
    print(f"    [FAIL] services: {e}"); sys.exit(1)

try:
    import face_engine as fe
    print("    [OK] face_engine")
except Exception as e:
    print(f"    [FAIL] face_engine: {e}"); sys.exit(1)

try:
    import cv2
    print(f"    [OK] cv2 version: {cv2.__version__}")
except Exception as e:
    print(f"    [FAIL] cv2: {e}"); sys.exit(1)

# ── 2. InsightFace init ──────────────────────────────────────
print("\n[2] Khoi tao FaceAnalysis (buffalo_l, CPU)...")
try:
    fe.face_engine.initialize()
    print("    [OK] initialized =", fe.face_engine._initialized)
except RuntimeError as e:
    print(f"    [FAIL] {e}"); sys.exit(1)

# ── 3. Version info ──────────────────────────────────────────
print("\n[3] Version info:")
try:
    import insightface
    print(f"    insightface : {insightface.__version__}")
except Exception:
    print("    insightface : (version not available)")
try:
    import onnxruntime
    print(f"    onnxruntime : {onnxruntime.__version__}")
except Exception:
    pass
print(f"    numpy       : {np.__version__}")
import platform
print(f"    python      : {platform.python_version()}")

# ── 4. Camera ────────────────────────────────────────────────
print("\n[4] Mo camera (index 0)...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("    [WARN] Camera khong kha dung — se dung anh gia de test DB flow")
    cap = None
else:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("    [OK] Camera opened")

# ── 5. Xoa embedding cu MaNV=1 ───────────────────────────────
MA_NV = 1
print(f"\n[5] Xoa embedding cu MaNV={MA_NV} (neu co)...")
deleted = database.delete_face_embeddings(MA_NV)
print(f"    Xoa {deleted} embedding(s)")

# ── 6. Thu 5 frame hop le ────────────────────────────────────
print(f"\n[6] Thu 5 frame va extract embedding...")
TARGET  = 5
INTERVAL = 0.3
frames = []
errors = []

if cap is not None:
    attempts = 0
    while len(frames) < TARGET and attempts < 25:
        attempts += 1
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.1)
            continue
        frames.append(frame)
        print(f"    Frame {len(frames)} captured ({frame.shape})")
        if len(frames) < TARGET:
            time.sleep(INTERVAL)
    cap.release()
else:
    # Camera khong co — tao frame ngau nhien de test DB/vector flow
    print("    [WARN] Dung frame ngau nhien (khong co camera thuc)")
    for i in range(TARGET):
        frames.append(None)  # se bi loi "Khong phat hien khuon mat"

print(f"    Thu duoc {len(frames)} frame(s)")

# ── 7. Extract embedding + luu DB ────────────────────────────
print(f"\n[7] Extract embedding va luu vao FaceEmbedding...")
saved_ids = []

for i, frame in enumerate(frames):
    try:
        vector_bytes, emb_np = fe.face_engine.extract_embedding(frame)
        ma_emb = database.insert_face_embedding(MA_NV, vector_bytes, 512)
        norm_val = float(np.linalg.norm(emb_np))
        saved_ids.append(ma_emb)
        print(f"    Frame {i+1}: MaEmbedding={ma_emb}, "
              f"shape={emb_np.shape}, norm={norm_val:.6f}")
    except RuntimeError as e:
        errors.append(f"Frame {i+1}: {e}")
        print(f"    Frame {i+1}: [SKIP] {e}")

print(f"\n    Saved {len(saved_ids)} embeddings, {len(errors)} errors")

# ── 8. Verify DB ─────────────────────────────────────────────
print(f"\n[8] Kiem tra DB: SELECT FaceEmbedding WHERE MaNV={MA_NV}")
rows = database.get_face_embeddings(MA_NV)
print(f"    {'MaEmb':>8} {'MaNV':>6} {'SoChieu':>8} {'VectorBytes':>12} {'ThoiGianTao':>25}")
print("    " + "-" * 65)
for row in rows:
    ma_emb     = row[0]
    mnv        = row[1]
    vdata      = row[2]
    so_chieu   = row[3]
    tgt        = row[4]
    vlen = len(bytes(vdata)) if vdata else 0
    print(f"    {ma_emb:>8} {mnv:>6} {so_chieu:>8} {vlen:>12} {str(tgt):>25}")

# ── 9. Verify vector shape & norm ───────────────────────────
if rows:
    print(f"\n[9] Verify vector shape & L2 norm (embedding thu nhat)...")
    first_row = rows[0]
    raw_bytes = bytes(first_row[2])
    emb_verify = np.frombuffer(raw_bytes, dtype=np.float32)
    norm_verify = float(np.linalg.norm(emb_verify))
    print(f"    shape      : {emb_verify.shape}")
    print(f"    dtype      : {emb_verify.dtype}")
    print(f"    L2 norm    : {norm_verify:.6f}")
    print(f"    VectorBytes: {len(raw_bytes)}")

    if emb_verify.shape == (512,):
        print("    [PASS] shape == (512,)")
    else:
        print(f"    [FAIL] shape != (512,): got {emb_verify.shape}")

    if 0.99 <= norm_verify <= 1.01:
        print(f"    [PASS] norm ~ 1.0 (normed_embedding confirmed)")
    else:
        print(f"    [WARN] norm = {norm_verify:.6f} (khong phai normed_embedding?)")

    expected_bytes = 512 * 4  # float32 = 4 bytes
    if len(raw_bytes) == expected_bytes:
        print(f"    [PASS] VectorBytes = {len(raw_bytes)} = 512 * 4")
    else:
        print(f"    [FAIL] VectorBytes = {len(raw_bytes)}, expected {expected_bytes}")

# ── 10. Summary ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  MaNV             : {MA_NV}")
print(f"  Embeddings saved : {len(saved_ids)}")
print(f"  Frame errors     : {len(errors)}")
if errors:
    for e in errors:
        print(f"    - {e}")
if rows:
    vdata0 = bytes(rows[0][2])
    emb0   = np.frombuffer(vdata0, dtype=np.float32)
    print(f"  Shape            : {emb0.shape}")
    print(f"  L2 norm          : {np.linalg.norm(emb0):.6f}")
    print(f"  VectorBytes      : {len(vdata0)}")

if len(saved_ids) >= 5:
    print("\n  [PASS] Enrollment Phase 1 COMPLETE")
elif len(saved_ids) > 0:
    print(f"\n  [PARTIAL] {len(saved_ids)}/5 embeddings saved")
    print("  Dua khuon mat vao truoc camera va thu lai")
else:
    print("\n  [FAIL] Khong luu duoc embedding nao")
    print("  Kiem tra: camera co khuon mat khong? InsightFace model co OK khong?")

print("=" * 60)
