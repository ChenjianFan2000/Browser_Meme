import json
from pathlib import Path
import sys
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from harness.replica.contracts import within, verify_registration, write_new, digest, freeze_package, snapshot_package
from harness.replica.monitor import supervise
from harness.replica.server import make_server


def test_artifacts_reject_parent_and_symlink_escape(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("outside")
    (root / "escape").symlink_to(secret)
    for name in ("../outside.txt", "escape", str(secret)):
        with pytest.raises(ValueError):
            within(root, name)


def test_changed_frozen_input_cannot_pass_registration(tmp_path):
    artifact = tmp_path / "model.js"
    artifact.write_text("initial")
    record = tmp_path / "freeze.json"
    write_new(record, {"workspace": str(tmp_path), "files": {"model.js": digest(artifact)}})
    assert verify_registration(record)["passed"]
    artifact.write_text("changed")
    assert verify_registration(record) == {"passed": False, "changed": ["model.js"]}


def test_all_candidates_and_external_init_script_are_frozen(tmp_path):
    for name in ("state", "patch"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.html").write_text("<main>ready</main>")
    (tmp_path / "rules.md").write_text("Rules")
    (tmp_path / "representation.md").write_text("Model")
    (tmp_path / "flow.py").write_text("def run(h): pass")
    (tmp_path / "init.js").write_text("window.ready = true")
    (tmp_path / "components.json").write_text(json.dumps([dict(id="start", purpose="begin", locator="role", ready_when="unique", read_when="unknown")]))
    package = dict(schema_version=1, revision="v001", rulebook="rules.md", components="components.json",
        representation="representation.md", scripts=[dict(id="flow", path="flow.py", purpose="navigate")],
        replica=dict(kind="static_browser_app", directory="state", init_script="init.js"),
        candidates=[dict(id="state", directory="state"), dict(id="patch", directory="patch")])
    (tmp_path / "READY.json").write_text(json.dumps(package))
    record = tmp_path / "freeze.json"
    freeze_package(tmp_path, record)
    assert verify_registration(record)["passed"]
    (tmp_path / "private-not-declared.txt").write_text("not part of model package")
    frozen = snapshot_package(tmp_path, tmp_path.parent / (tmp_path.name + "-frozen"))
    assert verify_registration(frozen["registration"])["passed"]
    assert not (Path(frozen["package"]) / "private-not-declared.txt").exists()
    (tmp_path / "init.js").write_text("window.ready = false")
    (tmp_path / "patch" / "added.js").write_text("unregistered()")
    assert verify_registration(record) == {"passed": False, "changed": ["init.js", "patch/added.js"]}
    assert verify_registration(frozen["registration"])["passed"]


def test_watchdog_stops_alive_but_idle_process(tmp_path):
    result = supervise([sys.executable, "-c", "import time; time.sleep(30)"],
        tmp_path / "watch", timeout=5, idle_timeout=.2, interval=.04,
        min_memory_bytes=0, min_disk_bytes=0)
    assert result["reason"] == "no_evidence_progress"
    assert result["exit_code"] != 0
    heartbeats = [json.loads(row) for row in (tmp_path / "watch/heartbeat.jsonl").read_text().splitlines()]
    assert heartbeats[-1]["process"]["alive"]
    assert heartbeats[-1]["idle_seconds"] >= .2


def test_log_spam_cannot_reset_evidence_deadline(tmp_path):
    command = [sys.executable, "-u", "-c",
        "import time\nwhile True:\n print('alive', flush=True)\n time.sleep(.02)"]
    # Allow the trusted supervisor and interpreter to start before testing the
    # noisy-but-idle workload; assert real output so startup-only termination
    # cannot masquerade as this fault-injection case.
    result = supervise(command, tmp_path / "watch", timeout=8, idle_timeout=3,
        interval=.04, min_memory_bytes=0, min_disk_bytes=0)
    assert result["reason"] == "no_evidence_progress"
    assert (tmp_path / "watch/stdout.log").stat().st_size > 0


def test_replica_routes_work_but_missing_api_is_not_faked(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Replica</title><main>Ready</main>")
    with make_server(tmp_path, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(origin + "/second-page?q=value") as response:
                assert b"Ready" in response.read()
                assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
            for path in ("/api/missing", "/missing.js", "/private/data"):
                with pytest.raises(HTTPError):
                    urlopen(origin + path)
        finally:
            server.shutdown()
            thread.join(timeout=5)
