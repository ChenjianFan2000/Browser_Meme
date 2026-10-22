"""Frozen-case MCP extension: one declaration to the trusted management clock.

The extra control socket is intentionally not mounted in either model or browser
execution namespaces. It only acknowledges a prediction; it exposes no truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

from browser_broker import Broker, write_new
from permissions import CODEX, overrides


class FrozenBroker(Broker):
    def model_predict(self, arguments):
        if self.config["condition"] != "A":
            raise ValueError("executable behavior prediction is absent in condition B")
        self.check_frozen()
        model = Path(self.config["frozen_model"])
        folder = self.private / ("prediction-" + uuid.uuid4().hex[:12])
        folder.mkdir()
        job = {"model_path": str(model), "observation": arguments["observation"], "intent": arguments["intent"]}
        write_new(folder / "job.json", job)
        command = [CODEX, "sandbox", "-P", "p2", "-C", str(folder)]
        command += overrides(extra_paths={str(model.parent): "read", str(self.runtime): "read"})
        command += ["/usr/bin/python3", str(self.runtime / "predict_runtime.py"), "--job", str(folder / "job.json")]
        started = time.monotonic()
        with (folder / "stdout.txt").open("x") as out, (folder / "stderr.txt").open("x") as err:
            result = subprocess.run(command, stdout=out, stderr=err, timeout=30,
                                    env={"PATH": "/usr/bin:/bin", "HOME": str(folder), "LANG": "C.UTF-8"})
        if result.returncode or not (folder / "prediction.json").is_file():
            raise ValueError("frozen predictor failed: " + (folder / "stderr.txt").read_text()[-3000:])
        prediction = json.loads((folder / "prediction.json").read_text())
        record = {"prediction": prediction, "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                  "input_sha256": hashlib.sha256((folder / "job.json").read_bytes()).hexdigest(),
                  "elapsed_seconds": time.monotonic() - started, "directory": folder.name}
        write_new(folder / "model-result.json", record)
        self.latest_model_prediction = record
        self.log({"event": "frozen_model_prediction", **record})
        return record

    def check_frozen(self):
        root = Path(self.config["frozen_root"])
        for relative, expected in self.config["frozen_files"].items():
            if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("frozen learning package hash changed")

    def declare(self, arguments):
        self.check_frozen()
        path = self.private / "prediction-ack.json"
        if path.exists():
            raise ValueError("a task prediction is already frozen")
        value = arguments["prediction"]
        if not isinstance(value, dict) or value.get("disposition") not in {"accepted", "rejected", "unknown"}:
            raise ValueError("invalid disposition")
        encoded_prediction = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        model_record = getattr(self, "latest_model_prediction", None)
        if self.config["condition"] == "A" and (model_record is None or encoded_prediction != json.dumps(
                model_record["prediction"], sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))):
            raise ValueError("condition A must first call model_predict and declare that exact frozen-model output")
        message = {"command": "declare_prediction", "prediction": value,
                   "basis": str(arguments.get("basis", "")), "case_id": self.config["case_id"],
                   "before_sha256": self.config["before_sha256"]}
        if model_record:
            message["model_provenance"] = {key: model_record[key] for key in ("model_sha256", "input_sha256")}
        encoded = json.dumps(message).encode() + b"\n"
        if len(encoded) > 65536:
            raise ValueError("prediction record too large")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(self.config["control_socket"])
            client.sendall(encoded)
            with client.makefile("rb") as incoming:
                result = json.loads(incoming.readline(65537))
        if result.get("status") != "frozen":
            raise ValueError("management did not accept the declaration: " + str(result))
        write_new(path, {"request": message, "acknowledgement": result})
        self.log({"event": "task_prediction_frozen", "acknowledgement": result})
        return result

    def execute(self, arguments):
        self.check_frozen()
        for value in arguments.get("modules", []):
            if value.startswith("frozen/"):
                raise ValueError("copy a frozen pure module unchanged into the task workspace and pass that path")
        return super().execute(arguments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    broker = FrozenBroker(json.loads(Path(args.config).read_text()))
    tool_list = [
        {"name": "execute_script", "description": "Execute a workspace-relative native Playwright script def run(h) in the isolated browser. Use h.expect before every UI action. Before declaring a task prediction, only inspect the initial state and authenticate; do not change target business state. After declare_task_prediction, execute the task with within-case supervision. Original evidence and budget are authoritative.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "modules": {"type": "array", "items": {"type": "string"}}}, "required": ["script_path"], "additionalProperties": False}},
        {"name": "declare_task_prediction", "description": "Freeze the single whole-task prediction BEFORE any target business write. The coordinator timestamps it and binds it to this case. This returns only an acknowledgement, never an answer or score. Cannot revise it. Use the registered prediction object and describe its evidence/model basis.", "inputSchema": {"type": "object", "properties": {"prediction": {"type": "object"}, "basis": {"type": "string"}}, "required": ["prediction", "basis"], "additionalProperties": False}},
        {"name": "status", "description": "Read actual case execution budget.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ]
    if broker.config["condition"] == "A":
        tool_list.append({"name": "model_predict", "description": "Run the exact immutable learned behavior_model.predict(observation,intent) in an offline namespace. Supply only allowed current browser observations and the current task intent. Declare this exact returned prediction; the model cannot be edited during frozen evaluation.", "inputSchema": {"type": "object", "properties": {"observation": {"type": "object"}, "intent": {"type": "object"}}, "required": ["observation", "intent"], "additionalProperties": False}})
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        try:
            method = request["method"]
            if method == "initialize":
                result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "phase2-frozen-case", "version": "1.0"}}
            elif method == "tools/list":
                result = {"tools": tool_list}
            elif method in {"ping", "resources/list", "resources/templates/list"}:
                result = {} if method == "ping" else {"resources" if method == "resources/list" else "resourceTemplates": []}
            elif method == "tools/call":
                name = request["params"]["name"]
                arguments = request["params"].get("arguments", {})
                try:
                    value = {"execute_script": broker.execute, "declare_task_prediction": broker.declare,
                             "model_predict": broker.model_predict,
                             "status": lambda _: broker.status()}[name](arguments)
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
                except Exception as error:
                    result = {"isError": True, "content": [{"type": "text", "text": type(error).__name__ + ": " + str(error)}]}
            else:
                raise ValueError("unsupported method")
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32603, "message": str(error)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
