"""Durable attendance outbox. Retries preserve the original event and timestamp."""

import json
import hashlib
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .atomic_storage import atomic_write


class AttendanceTransport:
    MAX_SEND_ATTEMPTS = 5

    def __init__(self, directory, url, token=None, sender=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.url = url
        self.token = token if token is not None else os.environ.get("PBL4_INTERNAL_TOKEN", "")
        self.sender = sender
        self._lock = threading.Lock()

    @staticmethod
    def _validate(payload):
        if not isinstance(payload, dict):
            raise ValueError("Attendance event must be an object")
        event = UUID(payload["event_id"])
        if event.version != 4 or str(event) != payload["event_id"]:
            raise ValueError("Attendance event requires a canonical UUID v4")
        employee = payload.get("MaNV")
        if isinstance(employee, bool) or not isinstance(employee, int) or not 0 < employee <= 2147483647:
            raise ValueError("Attendance event requires a positive employee ID")
        occurred = datetime.fromisoformat(payload["occurred_at"])
        if occurred.tzinfo is None:
            raise ValueError("Attendance timestamp requires a timezone")
        return str(event), occurred.timestamp()

    @staticmethod
    def _fingerprint(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                                         ensure_ascii=False).encode("utf-8")).hexdigest()

    def _receipt(self, payload):
        path = self.directory / "receipts" / (payload["event_id"] + ".json")
        if not path.exists():
            return None
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt["request_hash"] != self._fingerprint(payload):
            raise ValueError("An event ID cannot be reused for a different payload")
        return receipt["web_result"]

    @staticmethod
    def _waiting(message="Đã lưu cục bộ, chờ đồng bộ Web"):
        return {"action": "pending", "status": "pending", "message": message}

    def send(self, payload):
        event_id, _ = self._validate(payload)
        # Validate JSON before creating a queue entry; NaN must never be persisted.
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        path = self.directory / (event_id + ".json")
        with self._lock:
            receipt = self._receipt(payload)
            if receipt is not None:
                path.unlink(missing_ok=True)
                return receipt
            if path.exists():
                original = json.loads(path.read_text(encoding="utf-8"))
                if original != payload:
                    raise ValueError("An event ID cannot be reused for a different payload")
            else:
                atomic_write(path, encoded)
            # Drain older events for this employee before a newer auto in/out event.
            try:
                pending = self._pending()
            except ValueError:
                return self._waiting("Hàng chờ có dữ liệu lỗi; cần kiểm tra trước khi gửi tiếp")
            attempts = 0
            for prior, original in pending:
                if original.get("MaNV") != payload.get("MaNV"):
                    continue
                if attempts >= self.MAX_SEND_ATTEMPTS:
                    break
                result = self._deliver(prior, original)
                attempts += 1
                if prior == path:
                    return result
                if result.get("status") == "pending":
                    return self._waiting("Chờ đồng bộ sự kiện trước đó")
            return self._waiting()

    def _pending(self):
        pending = []
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                event_id, timestamp = self._validate(payload)
                if event_id != path.stem:
                    raise ValueError("Event filename does not match its ID")
                pending.append((timestamp, path, payload))
            except (ValueError, KeyError, OSError, TypeError, OverflowError) as exc:
                # Preserve evidence and fail closed: skipping an unreadable earlier
                # event could turn a later check-out into a check-in.
                logging.getLogger(__name__).error("Invalid pending attendance event: %s", path.name)
                raise ValueError("Unreadable attendance queue entry") from exc
        return [(path, payload) for _, path, payload in sorted(pending, key=lambda item: (item[0], item[1].name))]

    def _deliver(self, path, payload):
        if not self.token:
            return self._waiting("Chưa cấu hình token đồng bộ Web")
        try:
            receipt = self._receipt(payload)
            if receipt is not None:
                path.unlink(missing_ok=True)
                return receipt
            if self.sender is None:
                import requests
                sender = requests.post
            else:
                sender = self.sender
            response = sender(self.url, json=payload,
                              headers={"Authorization": "Bearer " + self.token}, timeout=2.5,
                              allow_redirects=False)
            result = response.json()
            if (response.status_code == 200 and isinstance(result, dict)
                    and result.get("event_id") == payload["event_id"]
                    and result.get("status") in ("success", "completed")
                    and result.get("action") in ("checkin", "checkout", "completed")):
                receipt_path = self.directory / "receipts" / (payload["event_id"] + ".json")
                atomic_write(receipt_path, json.dumps({"request_hash": self._fingerprint(payload),
                             "web_result": result}, ensure_ascii=False, allow_nan=False).encode("utf-8"))
                path.unlink(missing_ok=True)
                return result
            return self._waiting("Web chưa xác nhận đúng sự kiện (HTTP %s)" % response.status_code)
        except Exception:
            return self._waiting()

    def retry_pending(self, limit=5):
        results = []
        if limit <= 0:
            return results
        with self._lock:
            try:
                pending = self._pending()
            except ValueError:
                return results
            blocked = set()
            for path, payload in pending:
                employee = payload.get("MaNV")
                if employee in blocked:
                    continue
                result = self._deliver(path, payload)
                results.append((payload["event_id"], result))
                if result.get("status") == "pending":
                    blocked.add(employee)
                if len(results) >= limit:
                    break
        return results
