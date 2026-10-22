
"""
api_server.py — FastAPI Server nhận HTTP POST từ 2 mạch ESP32-CAM:
- Mạch 1: Chụp ảnh gửi /api/attendance -> Nhận diện khuôn mặt (AI 1 - InsightFace)
- Mạch 2: Chụp ảnh + dữ liệu nhịp tim/SpO2 gửi /api/health -> Phân tích trạng thái (AI 2 - MediaPipe/RF)
"""

import sys
import os
import json
import logging
from pathlib import Path
from collections import deque
from typing import Optional, Dict

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Thêm đường dẫn src vào sys.path
SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(SRC_DIR))

from face_engine import FaceEngine
from verify import identify, DEFAULT_THRESHOLD
from status_features import StatusFeatureExtractor

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ESP32-API-Server")

app = FastAPI(title="PBL4 FaceHealth IoT API Server", version="1.0.0")

# ─── Khởi tạo các Engine AI ──────────────────────────────────────────────────
logger.info("Đang khởi tạo FaceEngine (AI 1)...")
face_engine = FaceEngine()

logger.info("Đang khởi tạo StatusFeatureExtractor (AI 2)...")
feature_extractor = StatusFeatureExtractor()

# Thử load StatusPredictor nếu đã có model Random Forest
status_predictor = None
try:
    from predict_status import StatusPredictor
    status_predictor = StatusPredictor()
    logger.info("✅ Đã nạp thành công mô hình Random Forest cho AI 2.")
except Exception as e:
    logger.warning(f"⚠️ Chưa thể nạp mô hình Random Forest ({e}). Hệ thống sẽ dùng cơ chế ngưỡng fallback (Rule-based).")

# Bộ nhớ đệm 3 frame gần nhất cho từng Node ESP32-CAM để phân tích trạng thái
node_frame_buffers: Dict[str, deque] = {}


# ─── API Routes ──────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/api/status")
def health_check():
    return {
        "status": "online",
        "service": "PBL4 FaceHealth API Server",
        "ai1_loaded": face_engine is not None,
        "ai2_loaded": feature_extractor is not None,
        "rf_model_available": status_predictor is not None
    }


@app.post("/api/attendance")
async def process_attendance(
    image: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    """
    Tiếp nhận ảnh từ ESP32-CAM Node 1 và thực hiện điểm danh 1:N
    """
    try:
        # Đọc dữ liệu ảnh từ buffer multipart
        img_bytes = await image.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể giải mã định dạng ảnh JPEG.")

        node_id = "UNKNOWN_NODE"
        if metadata:
            try:
                meta_json = json.loads(metadata)
                node_id = meta_json.get("node_id", node_id)
            except Exception:
                pass

        logger.info(f"[{node_id}] Nhận yêu cầu điểm danh. Kích thước frame: {frame.shape}")

        # Nhận diện 1:N với cơ sở dữ liệu đã đăng ký
        result = identify(face_engine, frame, threshold=DEFAULT_THRESHOLD)

        matched = result.get("match", False)
        student_id = result.get("student_id")
        name = result.get("name", "Không xác định")
        similarity = float(result.get("similarity", 0.0))

        if matched:
            logger.info(f"✅ [MATCH] {student_id} - {name} (Similarity: {similarity:.3f})")
            msg = f"Điểm danh thành công: {name} ({student_id})"
        else:
            logger.info(f"❌ [NO MATCH] Similarity cao nhất: {similarity:.3f}")
            msg = "Khuôn mặt chưa được đăng ký trong hệ thống."

        return {
            "status": "success",
            "matched": matched,
            "student_id": student_id,
            "name": name,
            "confidence": round(similarity, 3),
            "message": msg
        }

    except Exception as e:
        logger.error(f"Lỗi xử lý điểm danh: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/health")
async def process_health(
    image: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    """
    Tiếp nhận ảnh + dữ liệu nhịp tim/SpO2 từ ESP32-CAM Node 2
    """
    try:
        img_bytes = await image.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể giải mã định dạng ảnh JPEG.")

        # Parse thông số cảm biến
        node_id = "CAM_HEALTH_02"
        heart_rate = 0
        spo2 = 0
        finger_detected = False

        if metadata:
            try:
                meta_json = json.loads(metadata)
                node_id = meta_json.get("node_id", node_id)
                heart_rate = int(meta_json.get("heart_rate", 0))
                spo2 = int(meta_json.get("spo2", 0))
                finger_detected = bool(meta_json.get("finger_detected", False))
            except Exception as pe:
                logger.warning(f"Lỗi parse JSON metadata: {pe}")

        logger.info(f"[{node_id}] Frame: {frame.shape}, HR: {heart_rate}, SpO2: {spo2}%, Finger: {finger_detected}")

        # Trích xuất đặc trưng khuôn mặt (EAR, MAR, Pose)
        feats = feature_extractor.extract_features(frame)
        ear = round(float(feats['ear']), 3) if feats else 0.0
        mar = round(float(feats['mar']), 3) if feats else 0.0

        # Quản lý bộ đệm 3 frames cho node này
        if node_id not in node_frame_buffers:
            node_frame_buffers[node_id] = deque(maxlen=3)
        node_frame_buffers[node_id].append(frame)

        face_status = "Normal"
        alert = False
        message = "Trạng thái bình thường"

        # Phân loại trạng thái
        if status_predictor and len(node_frame_buffers[node_id]) == 3:
            try:
                face_status = status_predictor.predict_status(list(node_frame_buffers[node_id]))
            except Exception as pred_err:
                logger.warning(f"Lỗi predictor, fallback sang rule-based: {pred_err}")
                face_status = rule_based_status(feats)
        else:
            # Fallback sang logic ngưỡng trực tiếp
            face_status = rule_based_status(feats)

        # Cảnh báo dựa trên khuôn mặt hoặc chỉ số SpO2
        if face_status in ["Drowsy", "Yawn", "Head-down"]:
            alert = True
            message = f"Cảnh báo: Phát hiện sinh viên có dấu hiệu {face_status}!"
        elif finger_detected and (spo2 > 0 and spo2 < 94):
            alert = True
            message = f"Cảnh báo: Chỉ số SpO2 thấp ({spo2}%)!"

        return {
            "status": "success",
            "face_status": face_status,
            "ear": ear,
            "mar": mar,
            "heart_rate": heart_rate,
            "spo2": spo2,
            "finger_detected": finger_detected,
            "alert": alert,
            "message": message
        }

    except Exception as e:
        logger.error(f"Lỗi xử lý health: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


def rule_based_status(feats: Optional[dict]) -> str:
    """Đánh giá trạng thái quy tắc nếu chưa nạp được Random Forest"""
    if feats is None:
        return "Unknown"
    ear = feats.get("ear", 0.3)
    mar = feats.get("mar", 0.1)
    pitch = feats.get("pitch", 0.0)

    if pitch < -20.0:
        return "Head-down"
    if mar > 0.45:
        return "Yawn"
    if ear < 0.21:
        return "Drowsy"
    return "Normal"


if __name__ == "__main__":
    logger.info("Khởi động FastAPI server trên cổng 8000 (0.0.0.0)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
