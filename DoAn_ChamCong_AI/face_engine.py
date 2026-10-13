"""InsightFace buffalo_l detection, embedding extraction, and head-pose estimation."""

import numpy as np
import threading
import cv2


MODEL_NAME = "buffalo_l"
EMBEDDING_DIMENSIONS = 512

# Generic 3D face reference ordered like InsightFace's five-point landmarks:
# image-left eye, image-right eye, nose, image-left mouth, image-right mouth.
_POSE_MODEL_POINTS = np.asarray([
    [-32.0, 32.0, 28.0],
    [32.0, 32.0, 28.0],
    [0.0, 0.0, 0.0],
    [-23.0, -30.0, 20.0],
    [23.0, -30.0, 20.0],
], dtype=np.float64)


def estimate_head_pose(keypoints, frame_shape):
    """Estimate yaw/pitch in degrees from InsightFace's five facial keypoints."""
    points = np.asarray(keypoints, dtype=np.float64)
    if points.shape != (5, 2) or not np.all(np.isfinite(points)):
        raise ValueError("Expected five finite 2D face keypoints.")

    height, width = frame_shape[:2]
    focal = float(width)
    camera = np.asarray([
        [focal, 0.0, width / 2.0],
        [0.0, focal, height / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    distortion = np.zeros((4, 1), dtype=np.float64)
    ok, rotation_vector, _ = cv2.solvePnP(
        _POSE_MODEL_POINTS,
        points,
        camera,
        distortion,
        flags=cv2.SOLVEPNP_SQPNP,
    )
    if not ok:
        raise ValueError("Could not estimate head pose from face keypoints.")

    rotation, _ = cv2.Rodrigues(rotation_vector)
    yaw = np.degrees(np.arctan2(-rotation[2, 0], np.hypot(rotation[0, 0], rotation[1, 0])))
    pitch = np.degrees(np.arctan2(rotation[2, 1], rotation[2, 2]))
    return {"yaw": float(yaw), "pitch": float(pitch)}


class FaceRecognitionEngine:
    """
    Wrapper InsightFace FaceAnalysis cho enrollment.

    Usage:
        engine = FaceRecognitionEngine()
        engine.initialize()
        vector_bytes, emb_np = engine.extract_embedding(frame)
    """

    def __init__(self):
        self._app = None
        self._initialized = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # initialize
    # ------------------------------------------------------------------

    def initialize(self):
        """
        Khởi tạo InsightFace FaceAnalysis với model buffalo_l, CPU only.
        Gọi một lần khi server khởi động.

        Raises:
            RuntimeError nếu InsightFace không cài hoặc model lỗi.
        """
        with self._lock:
            if self._initialized:
                return

            try:
                from insightface.app import FaceAnalysis
            except ImportError as e:
                raise RuntimeError(
                    f"insightface chua duoc cai dat. Chay: pip install insightface onnxruntime\n"
                    f"Chi tiet: {e}"
                )

            try:
                self._app = FaceAnalysis(
                    name=MODEL_NAME,
                    providers=["CPUExecutionProvider"],
                )
                self._app.prepare(ctx_id=-1, det_size=(640, 640))
                self._initialized = True
                print(f"[face_engine] FaceAnalysis ({MODEL_NAME}, CPU) san sang.")
            except Exception as e:
                self._app = None
                raise RuntimeError(f"[face_engine] Khoi tao FaceAnalysis that bai: {e}")

    # ------------------------------------------------------------------
    # extract_embedding
    # ------------------------------------------------------------------

    def detect_embeddings(self, frame):
        """Return normalized embeddings and face metadata for every detected face."""
        if not self._initialized or self._app is None:
            raise RuntimeError("Engine chua duoc khoi tao. Goi initialize() truoc.")
        if frame is None:
            raise RuntimeError("Frame dau vao la None.")

        with self._lock:
            faces = self._app.get(frame)

        results = []
        for face in faces:
            raw_emb = getattr(face, "normed_embedding", None)
            if raw_emb is None:
                raw_emb = getattr(face, "embedding", None)
            if raw_emb is None:
                raise RuntimeError("Model khong tra ve embedding (thieu recognition module?)")

            embedding = np.asarray(raw_emb, dtype=np.float32).reshape(-1)
            if embedding.size != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"Embedding khong hop le: kich thuoc {embedding.size}, can {EMBEDDING_DIMENSIONS}."
                )
            norm = float(np.linalg.norm(embedding))
            if not np.isfinite(norm) or norm <= 1e-12:
                raise RuntimeError("Embedding khong hop le: norm bang 0 hoac khong huu han.")
            embedding = np.asarray(embedding / norm, dtype=np.float32)

            bbox = getattr(face, "bbox", None)
            keypoints = getattr(face, "kps", None)
            pose = None
            if keypoints is not None:
                try:
                    pose = estimate_head_pose(keypoints, frame.shape)
                except (ValueError, cv2.error):
                    pose = None
            results.append({
                "embedding": embedding,
                "vector_bytes": embedding.astype("<f4", copy=False).tobytes(),
                "bbox": [float(value) for value in bbox] if bbox is not None else None,
                "detection_score": float(getattr(face, "det_score", 0.0)),
                "head_pose": pose,
            })
        return results

    def inspect_pose(self, frame):
        """Return face count and estimated pose without persisting an embedding."""
        faces = self.detect_embeddings(frame)
        if not faces:
            return {"face_count": 0, "current_pose": "no_face", "yaw": None, "pitch": None}
        if len(faces) != 1:
            return {"face_count": len(faces), "current_pose": "multiple_faces", "yaw": None, "pitch": None}
        pose = faces[0]["head_pose"]
        if pose is None:
            return {"face_count": 1, "current_pose": "unknown", "yaw": None, "pitch": None}
        return {"face_count": 1, "current_pose": "frontal", **pose}

    def extract_embedding(self, frame):
        """
        Phan tich frame va trich xuat normed face embedding 512 chieu.

        Tham so:
            frame : numpy ndarray, BGR, kich thuoc bat ky (tu OpenCV).

        Tra ve:
            (vector_bytes, embedding_np)
              vector_bytes  : bytes float32, do dai 2048 byte (512 * 4)
              embedding_np  : np.ndarray shape (512,), dtype float32

        Raises:
            RuntimeError("Chua khoi tao engine")
            RuntimeError("Khong phat hien khuon mat")
            RuntimeError("Chi duoc co mot khuon mat")
            RuntimeError("Embedding khong hop le: ...")
        """
        faces = self.detect_embeddings(frame)

        if len(faces) == 0:
            raise RuntimeError("Khong phat hien khuon mat")

        if len(faces) > 1:
            raise RuntimeError("Chi duoc co mot khuon mat")

        return faces[0]["vector_bytes"], faces[0]["embedding"]


# ============================================================
# Singleton — khoi tao lazy khi can
# ============================================================

face_engine = FaceRecognitionEngine()
