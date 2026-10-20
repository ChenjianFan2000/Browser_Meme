"""Deploy original Discogs source in a dedicated local runtime; never edit upstream."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / "veri_env/external/VeriEnv-main/websites/discogs"
RUNTIME = Path(os.environ.get("BM_DISCOGS_RUNTIME", str(ROOT / ".runtime/phase1-discogs-20261020"))).resolve()
SOURCE = RUNTIME / "source"
PYTHON = RUNTIME / "venv/Scripts/python.exe"
DATA = RUNTIME / "data"
DB = DATA / "discogs.db"
BASELINE = DATA / "baseline.db"
OFFLINE_PYTHON = RUNTIME / "venv-offline/Scripts/python.exe"


def env() -> dict:
    result = os.environ.copy()
    result.update(DATABASE_URL="sqlite+pysqlite:///" + DB.as_posix(),
                  PYTHONPATH=str(SOURCE / "backend"),
                  API_INTERNAL_URL="http://127.0.0.1:12138",
                  NEXT_PUBLIC_API_URL="http://127.0.0.1:12138",
                  NEXT_PUBLIC_WEB_URL="http://127.0.0.1:12042",
                  CORS_ORIGINS="http://127.0.0.1:12042,http://localhost:12042",
                  NEXT_TELEMETRY_DISABLED="1")
    return result


def run(args: list[str], cwd: Path = ROOT) -> None:
    print(json.dumps({"command": args, "cwd": str(cwd)}), flush=True)
    subprocess.run(args, cwd=cwd, env=env(), check=True)


def source_copy() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(exist_ok=True)
    if not SOURCE.exists():
        shutil.copytree(UPSTREAM, SOURCE)
    hashes = {}
    for file in sorted(UPSTREAM.rglob("*")):
        if file.is_file():
            relative = file.relative_to(UPSTREAM)
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            if hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Source copy mismatch: {relative}")
            hashes[relative.as_posix()] = digest
    (RUNTIME / "source_manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


def initialize_baseline(python: Path) -> None:
    if BASELINE.exists():
        return
    run([str(python), "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], SOURCE / "backend")
    run([str(python), "-m", "app.db.seed"], SOURCE)
    with sqlite3.connect(DB) as con:
        demo = con.execute("SELECT id FROM users WHERE username='demo'").fetchone()[0]
        con.execute("DELETE FROM collection_items WHERE user_id=? AND release_id=221", (demo,))
        con.execute("DELETE FROM wantlist_items WHERE user_id=? AND release_id=221", (demo,))
        con.execute("DELETE FROM cart_items WHERE user_id=?", (demo,))
        con.commit()
        with sqlite3.connect(BASELINE) as frozen:
            con.backup(frozen)
    (RUNTIME / "baseline.sha256").write_text(hashlib.sha256(BASELINE.read_bytes()).hexdigest(), encoding="ascii")


def prepare_backend_offline() -> None:
    source_copy()
    if not OFFLINE_PYTHON.exists():
        run([sys.executable, "-m", "venv", "--system-site-packages", str(RUNTIME / "venv-offline")])
    candidates = json.loads((RUNTIME / "offline-python-wheels.json").read_text(encoding="utf-8"))
    selected = [("python-jose", "3.3.0"), ("ecdsa", "0.19.1"), ("rsa", "4.9")]
    wheelhouse = RUNTIME / "offline-wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    paths, manifest = [], []
    for name, version in selected:
        item = next(c for c in candidates if c["name"] == name and c["version"] == version)
        source = Path(item["source"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Cached wheel hash mismatch: {name}")
        with zipfile.ZipFile(source) as z:
            if not any(n.endswith(".dist-info/METADATA") for n in z.namelist()):
                raise RuntimeError("Invalid cached wheel")
        tags = "py2.py3-none-any" if "py2-none-any" in item["tags"] else "py3-none-any"
        destination = wheelhouse / f"{name.replace('-', '_')}-{version}-{tags}.whl"
        shutil.copyfile(source, destination)
        paths.append(str(destination))
        manifest.append({**item, "local_wheel": str(destination)})
    faker = ROOT / ".runtime/downloads/wheels/core/faker-40.43.0-py3-none-any.whl"
    destination = wheelhouse / faker.name
    shutil.copyfile(faker, destination)
    paths.append(str(destination))
    manifest.append({"source": str(faker), "local_wheel": str(destination),
                     "name": "Faker", "version": "40.43.0", "sha256": hashlib.sha256(faker.read_bytes()).hexdigest()})
    (RUNTIME / "offline-install-provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    run([str(OFFLINE_PYTHON), "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir", "--disable-pip-version-check", *paths])
    code = "import importlib.metadata,json; print(json.dumps(sorted([{'name':d.metadata['Name'],'version':d.version,'location':str(d.locate_file(''))} for d in importlib.metadata.distributions()],key=lambda d:d['name'].lower()),indent=2))"
    inventory = subprocess.check_output([str(OFFLINE_PYTHON), "-c", code], text=True)
    (RUNTIME / "offline-python-inventory.json").write_text(inventory, encoding="utf-8")
    initialize_baseline(OFFLINE_PYTHON)
    run([str(OFFLINE_PYTHON), str(Path(__file__).parent / "validate_backend_offline.py")])


def prepare() -> None:
    source_copy()
    if not PYTHON.exists():
        run([sys.executable, "-m", "venv", str(RUNTIME / "venv")])
    run([str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(SOURCE / "backend/requirements.txt")])
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    run([npm, "ci", "--no-audit", "--no-fund", "--cache", str(RUNTIME / "npm-cache")], SOURCE / "frontend")
    run([npm, "run", "build"], SOURCE / "frontend")
    initialize_baseline(PYTHON)
    versions = subprocess.check_output([str(PYTHON), "-m", "pip", "freeze"], text=True)
    (RUNTIME / "python.freeze.txt").write_text(versions, encoding="utf-8")
    print("Prepared original source copy and frozen baseline.", flush=True)


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def stop_owned(children: list[subprocess.Popen]) -> None:
    """Stop only this launcher's direct children and always reap their handles."""
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 8
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
    reap_deadline = time.monotonic() + 2
    for child in children:
        child.wait(timeout=max(0, reap_deadline - time.monotonic()))


def check_stop() -> None:
    marker = os.environ.get("HARNESS_STOP_FILE")
    if marker and Path(marker).is_file():
        raise KeyboardInterrupt("Harness requested a normal service stop")


def wait_interruptibly(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_stop()
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def start(children: list[subprocess.Popen] | None = None) -> list[subprocess.Popen]:
    if not BASELINE.exists():
        raise RuntimeError("Run prepare first")
    logs = RUNTIME / "logs"
    logs.mkdir(exist_ok=True)
    definitions = [
        ("backend", [str(PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", str(SOURCE / "backend"), "--host", "127.0.0.1", "--port", "12138"], SOURCE, "http://127.0.0.1:12138/healthz"),
        ("frontend", [shutil.which("node"), str(SOURCE / "frontend/node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", "12042"], SOURCE / "frontend", "http://127.0.0.1:12042")
    ]
    pids = {}
    children = [] if children is None else children
    try:
        for name, args, cwd, health in definitions:
            check_stop()
            if healthy(health):
                print(f"{name} already responds; existing process retained", flush=True)
                continue
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with open(logs / f"{name}.log", "ab") as output:
                child = subprocess.Popen(args, cwd=cwd, env=env(), stdin=subprocess.DEVNULL,
                                         stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
            children.append(child)
            pids[name] = child.pid
            print(f"Started {name}: pid {child.pid}", flush=True)
        (RUNTIME / "pids.json").write_text(json.dumps(pids), encoding="utf-8")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            check_stop()
            failed = [child for child in children if child.poll() is not None]
            if failed:
                raise RuntimeError(f"Service exited during startup: {[child.pid for child in failed]}")
            if all(healthy(item[3]) for item in definitions):
                print("Ready: http://127.0.0.1:12042", flush=True)
                return children
            wait_interruptibly(1)
        raise RuntimeError("Readiness timeout; inspect dedicated runtime logs")
    except BaseException:
        stop_owned(children)
        raise


def serve() -> None:
    """Keep this launcher attached so managed command sessions retain its children."""
    children = []
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {sig: signal.getsignal(sig) for sig in signals}

    def request_stop(signum, frame):
        raise KeyboardInterrupt

    for sig in signals:
        signal.signal(sig, request_stop)
    try:
        start(children)
        while True:
            check_stop()
            stopped = [{"pid": child.pid, "exit_code": child.poll()}
                       for child in children if child.poll() is not None]
            if stopped:
                raise RuntimeError(f"Owned service exited: {stopped}")
            status = {"backend": healthy("http://127.0.0.1:12138/healthz"),
                      "frontend": healthy("http://127.0.0.1:12042")}
            print(json.dumps({"service_heartbeat": status, "time_unix": time.time()}), flush=True)
            wait_interruptibly(15)
    except KeyboardInterrupt:
        print("Stopping owned Discogs service processes.", flush=True)
    finally:
        # Ignore repeated stop signals while child handles are being reaped.
        for sig in signals:
            signal.signal(sig, signal.SIG_IGN)
        try:
            stop_owned(children)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "prepare-backend-offline", "start", "serve", "status"])
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
    elif action == "prepare-backend-offline":
        prepare_backend_offline()
    elif action == "start":
        start()
    elif action == "serve":
        serve()
    else:
        print(json.dumps({"backend": healthy("http://127.0.0.1:12138/healthz"), "frontend": healthy("http://127.0.0.1:12042")}))
