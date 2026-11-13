"""Console menu and live camera UI for the standalone AI1 system."""

import threading
import time
from pathlib import Path
import shutil

import cv2
import numpy as np

from .ai1_adapter import initialize_ai1
from .camera_source import WebcamSource
from .config import (DATA_ROOT, RECOGNITION_COOLDOWN_SECONDS, RECOGNITION_THRESHOLD,
                     UNKNOWN_RETRY_INTERVAL_SECONDS)
from .data_store import StandaloneStore
from .enrollment import capture_five_pose_enrollment
from .recognition import recognize_sequence_from_source
from .utils import ascii_display, safe_identity_path, validate_employee_id


class StandaloneApplication:
    def __init__(self, store=None):
        self.store = store or StandaloneStore()
        self.store.ensure()
        print("Initializing production ArcFace buffalo_l (CPU)...")
        self.engine = initialize_ai1()
        self.employees, self.gallery = self.store.load()
        self.threshold = RECOGNITION_THRESHOLD
        print(f"AI1 ready. Registered employees: {len(self.employees)}. Threshold: {self.threshold:.3f}")

    def _reload_data(self):
        self.employees, self.gallery = self.store.load()

    def register_employee(self):
        try:
            identity = validate_employee_id(input("Employee ID: ").strip())
            name = input("Employee Name: ").strip()
            if not name:
                print("Employee Name cannot be empty.")
                return
            existing = identity in {employee["MaNV"] for employee in self.employees}
            overwrite = False
            if existing:
                print(f"{identity} already exists. Existing data is preserved unless enrollment is confirmed.")
                overwrite = input(f"Type {identity} to replace this employee: ").strip() == identity
                if not overwrite:
                    print("Registration cancelled; existing employee was not changed.")
                    return
            else:
                target_dir = safe_identity_path(self.store.images_root, identity)
                if target_dir.exists():
                    print("An image folder already exists for this ID without metadata; resolve it manually first.")
                    return

            source = WebcamSource()
            print(f"Webcam ready: index {source.camera_index}, backend {source.backend_name}.")
            staged = None
            try:
                capture = capture_five_pose_enrollment(self.engine, source, identity, self.store.root)
                if capture is None:
                    print("Registration cancelled; no profile was saved.")
                    return
                staged = capture["stage"]
                self.employees, self.gallery = self.store.add_employee(
                    identity, name, capture["embeddings"], staged, overwrite=overwrite
                )
                print(f"Registered {identity} | {name} | 5 samples.")
            finally:
                source.release()
                if staged is not None and Path(staged).exists():
                    shutil.rmtree(staged, ignore_errors=True)
        except Exception as exc:
            print(f"Registration failed: {exc}")

    def list_employees(self):
        if not self.employees:
            print("No registered employees.")
            return
        for employee in self.employees:
            samples = len(self.gallery.get(employee["MaNV"], {}).get("embeddings", ()))
            print(f"{employee['MaNV']} | {employee['HoTen']} | {samples} samples")

    def delete_employee(self):
        try:
            identity = validate_employee_id(input("Employee ID to delete: ").strip())
            if identity not in {employee["MaNV"] for employee in self.employees}:
                print(f"Employee {identity} is not registered.")
                return
            confirmation = input(f"Type {identity} to permanently delete standalone test data: ").strip()
            if confirmation != identity:
                print("Delete cancelled.")
                return
            self.employees, self.gallery = self.store.delete_employee(identity, confirmed=True)
            print(f"Deleted {identity} from ai1_standalone_data only.")
        except Exception as exc:
            print(f"Delete failed: {exc}")

    def start_recognition(self):
        try:
            source = WebcamSource()
        except Exception as exc:
            print(f"RETRY / NO FACE — camera error: {exc}")
            return
        print(f"Recognition camera: index {source.camera_index}, backend {source.backend_name}.")
        print("Q/ESC returns to menu.")
        stop_event = threading.Event()
        result_lock = threading.Lock()
        result_state = {"result": None}

        def worker():
            while not stop_event.is_set():
                try:
                    result = recognize_sequence_from_source(
                        self.engine, source, self.gallery, stop_event, self.threshold
                    )
                except Exception as exc:
                    result = {"status": "RETRY", "predicted_id": "UNKNOWN", "score": 0.0,
                              "threshold": self.threshold, "reason": f"AI ERROR: {exc}", "latency_ms": 0.0}
                if result is None or stop_event.is_set():
                    break
                with result_lock:
                    result_state["result"] = result
                if result["status"] == "MATCH":
                    employee = next((item for item in self.employees
                                     if item["MaNV"] == result["predicted_id"]), None)
                    name = employee["HoTen"] if employee else result["predicted_id"]
                    print(f"MATCH {result['predicted_id']} | {name} | score={result['score']:.3f} "
                          f"| latency={result['latency_ms']:.0f} ms")
                    wait_seconds = RECOGNITION_COOLDOWN_SECONDS
                else:
                    print(f"{result['status']} {result.get('reason', '')} "
                          f"| score={result.get('score', 0.0):.3f} "
                          f"| latency={result.get('latency_ms', 0.0):.0f} ms")
                    wait_seconds = UNKNOWN_RETRY_INTERVAL_SECONDS
                if stop_event.wait(wait_seconds):
                    break

        worker_thread = threading.Thread(target=worker, name="ai1-standalone-recognition", daemon=True)
        worker_thread.start()
        frame_counter = 0
        fps_started = time.perf_counter()
        fps = 0.0
        try:
            while True:
                frame = source.get_frame()
                if frame is None:
                    blank = cv2.putText(
                        np.zeros((480, 640, 3), dtype=np.uint8), "RETRY / NO FACE", (12, 36),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 255), 2, cv2.LINE_AA,
                    )
                    cv2.imshow("AI1 standalone recognition", blank)
                    key = cv2.waitKey(30) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):
                        break
                    continue
                frame_counter += 1
                elapsed = time.perf_counter() - fps_started
                if elapsed >= 1.0:
                    fps = frame_counter / elapsed
                    frame_counter = 0
                    fps_started = time.perf_counter()
                with result_lock:
                    result = dict(result_state["result"]) if result_state["result"] else None
                preview = frame.copy()
                lines = ["AI1 FACE RECOGNITION", f"Threshold: {self.threshold:.3f}", f"Preview FPS: {fps:.1f}"]
                if result is None:
                    lines.append("WAITING FOR 3-FRAME SCAN...")
                elif result["status"] == "MATCH":
                    employee = next((item for item in self.employees
                                     if item["MaNV"] == result["predicted_id"]), None)
                    name = employee["HoTen"] if employee else result["predicted_id"]
                    lines.extend(["MATCH", result["predicted_id"], ascii_display(name),
                                  f"Score: {result['score']:.3f}",
                                  f"Latency: {result['latency_ms']:.0f} ms"])
                elif result["status"] == "UNKNOWN":
                    lines.extend(["UNKNOWN", f"Score: {result['score']:.3f}",
                                  f"Latency: {result['latency_ms']:.0f} ms"])
                else:
                    lines.extend(["RETRY", str(result.get("reason", "NO FACE"))[:64],
                                  f"Latency: {result.get('latency_ms', 0.0):.0f} ms"])
                lines.append("Q / ESC: back to menu")
                for index, line in enumerate(lines):
                    cv2.putText(preview, line, (12, 28 + index * 28), cv2.FONT_HERSHEY_SIMPLEX,
                                0.62, (40, 240, 240), 2, cv2.LINE_AA)
                cv2.imshow("AI1 standalone recognition", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
        finally:
            stop_event.set()
            worker_thread.join()
            source.release()
            cv2.destroyAllWindows()

    @staticmethod
    def _show_menu():
        print("\n==================================")
        print("AI1 FACE RECOGNITION SYSTEM")
        print("==================================")
        print("1. Register new employee")
        print("2. Start face recognition")
        print("3. List registered employees")
        print("4. Delete test employee")
        print("0. Exit")
        print("==================================")

    def run(self):
        while True:
            self._show_menu()
            choice = input("Choose: ").strip()
            if choice == "0":
                return
            if choice == "1":
                self.register_employee()
            elif choice == "2":
                self.start_recognition()
            elif choice == "3":
                self.list_employees()
            elif choice == "4":
                self.delete_employee()
            else:
                print("Invalid choice.")
