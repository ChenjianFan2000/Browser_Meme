"""Single task prediction, recorded on the same clock as trusted HTTP dispatch."""
import hashlib
from pathlib import Path
import threading
import time

from .records import validate_prediction, write_new_json, sha256


class PredictionRecorder:
    def __init__(self, case_id: str, before: Path, destination: Path):
        self.case_id = case_id
        self.before_sha256 = sha256(before)
        self.destination = destination
        self.lock = threading.Lock()

    def __call__(self, message):
        with self.lock:
            if message.get("command") != "declare_prediction":
                return {"status": "denied", "reason": "unknown_command"}
            if message.get("case_id") != self.case_id or message.get("before_sha256") != self.before_sha256:
                return {"status": "denied", "reason": "case_or_before_binding_mismatch"}
            if self.destination.exists():
                return {"status": "denied", "reason": "prediction_already_frozen"}
            validate_prediction(message["prediction"])
            record = {"source": "trusted_browser_broker", "case_id": self.case_id,
                      "before_sha256": self.before_sha256, "declaration_count": 1,
                      "declared_at_ns": time.time_ns(), "prediction": message["prediction"],
                      "basis": message.get("basis", ""), "model_provenance": message.get("model_provenance")}
            write_new_json(self.destination, record)
            return {"status": "frozen", "case_id": self.case_id, "declared_at_ns": record["declared_at_ns"],
                    "record_sha256": sha256(self.destination)}
