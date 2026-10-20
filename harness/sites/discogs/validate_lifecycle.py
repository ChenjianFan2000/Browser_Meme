"""Offline process-cleanup component checks with sleeping child processes, no website."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.sites.discogs import deploy


def main():
    marker = deploy.RUNTIME / f"lifecycle-stop-{uuid4().hex}"
    old_stop = os.environ.get("HARNESS_STOP_FILE")
    os.environ["HARNESS_STOP_FILE"] = str(marker)
    original_start, original_healthy = deploy.start, deploy.healthy
    owned = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def sleeper():
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=flags)

    unrelated = sleeper()
    try:
        def fake_start(children):
            child = sleeper()
            owned.append(child)
            children.append(child)
            return children

        deploy.start = fake_start
        deploy.healthy = lambda url: True  # No HTTP requests in this component check.
        timer = threading.Timer(0.25, lambda: marker.write_text("stop", encoding="ascii"))
        started = time.monotonic()
        timer.start()
        deploy.serve()
        timer.join()
        elapsed = time.monotonic() - started
        assert all(p.poll() is not None for p in owned)
        assert unrelated.poll() is None
        assert elapsed < 10

        deploy.start = original_start
        try:
            deploy.start([])  # Pre-existing stop marker: must stop before any health/network probe.
        except KeyboardInterrupt:
            startup_stop_checked = True
        else:
            raise AssertionError("Startup ignored stop marker")
        marker.unlink()

        def signal_during_start(children):
            fake_start(children)
            signal.raise_signal(signal.SIGTERM)

        previous = signal.getsignal(signal.SIGTERM)
        deploy.start = signal_during_start
        deploy.serve()
        assert signal.getsignal(signal.SIGTERM) == previous
        assert all(p.poll() is not None for p in owned)
        assert unrelated.poll() is None
        result = {
            "scope": "Offline deployment lifecycle component checks with sleeping Python processes; no website or browser launched",
            "stop_file_during_runtime": True, "startup_stop_before_probes": startup_stop_checked,
            "sigterm_during_start_cleanup": True, "owned_children_reaped": True,
            "unrelated_process_preserved": True, "signal_handlers_restored": True,
            "normal_stop_elapsed_seconds": elapsed,
            "external_windows_ctrl_break_delivery_tested": False,
        }
        (deploy.RUNTIME / "lifecycle-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        deploy.start, deploy.healthy = original_start, original_healthy
        deploy.stop_owned(owned + [unrelated])
        marker.unlink(missing_ok=True)
        if old_stop is None:
            os.environ.pop("HARNESS_STOP_FILE", None)
        else:
            os.environ["HARNESS_STOP_FILE"] = old_stop


if __name__ == "__main__":
    main()
