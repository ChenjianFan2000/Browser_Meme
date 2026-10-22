"""Windows management helpers. No target-site rules or selectors live here."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LINUX_ROOT = "/opt/browser-meme/phase2-runs"
DISTRO = "BrowserMeme-Ubuntu"


def wsl_python(script, *, payload=None, timeout=60):
    if payload is not None:
        prefix = "import sys,io,base64\nsys.stdin=io.TextIOWrapper(io.BytesIO(base64.b64decode(" + repr(base64.b64encode(payload).decode()) + ")))\n"
        script = prefix + script
    return subprocess.run(["wsl", "-d", DISTRO, "--", "python3", "-"],
                          input=script.encode(), capture_output=True, timeout=timeout,
                          creationflags=0x08000000 if sys.platform == "win32" else 0)


def put_files(files, *, private=False):
    payload = json.dumps({str(path): base64.b64encode(data).decode() for path, data in files.items()}).encode()
    script = """import sys,json,pathlib,base64,os
files=json.load(sys.stdin)
for name,value in files.items():
 p=pathlib.Path(name); p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f: f.write(base64.b64decode(value))
 os.chmod(p,0o600)
print(json.dumps({'created':len(files)}))
"""
    result = wsl_python(script, payload=payload)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return json.loads(result.stdout)


def provision_runtime():
    names = ["permissions.py", "browser_broker.py", "browser_runtime.py", "script_policy.py",
             "observation.py", "launch_solar.py", "relay.py", "evaluation_broker.py", "predict_runtime.py", "process_guard.py"]
    files = {name: (ROOT / "harness" / "phase2" / name).read_bytes() for name in names}
    for name in ("unix_bridge.py", "unix_gateway.py"):
        files[name] = (ROOT / "harness" / "phase2_isolation" / name).read_bytes()
    digest = hashlib.sha256(b"".join(name.encode() + files[name] for name in sorted(files))).hexdigest()
    runtime = LINUX_ROOT + "/runtime-" + digest[:12]
    exists = wsl_python("from pathlib import Path; print(Path(" + repr(runtime) + ").exists())")
    if exists.stdout.strip() != b"True":
        put_files({runtime + "/" + name: data for name, data in files.items()})
    return runtime, digest


def fresh_session(run_id, runtime, *, condition, seed, prompt, fixture_path, socket,
                  action_limit=300, time_limit=7200):
    base = LINUX_ROOT + "/" + run_id
    work = base + "/workspace"
    private = base + "/private"
    home = base + "/codex-home"
    broker = {"workspace": work, "private": private + "/browser", "runtime": runtime,
              "origin": "http://127.0.0.1:12042", "socket": socket,
              "fixture_path": base + "/public-fixture.json", "action_limit": action_limit,
              "script_call_limit": 40, "time_limit_seconds": time_limit}
    plan = {"private": private + "/solar", "workspace": work, "runtime": runtime,
            "broker_config": base + "/broker-config.json", "codex_home": home,
            "prompt_path": work + "/PROMPT.md", "time_limit_seconds": time_limit,
            "condition": condition, "seed": seed, "model_sampling_seed": None,
            "reasoning_effort": "high"}
    fixture = Path(fixture_path).read_bytes()
    contract = (ROOT / "harness/phase2/LEARNER_CONTRACT.md").read_bytes()
    guide = (ROOT / "harness/phase2/RUNTIME_GUIDE.md").read_bytes()
    files = {base + "/broker-config.json": json.dumps(broker).encode(),
             base + "/launch-plan.json": json.dumps(plan).encode(),
             base + "/public-fixture.json": fixture,
             work + "/public-fixture.json": fixture,
             work + "/LEARNER_CONTRACT.md": contract, work + "/RUNTIME_GUIDE.md": guide,
             work + "/PROMPT.md": prompt.encode(),
             home + "/auth.json": (Path.home() / ".codex/auth.json").read_bytes()}
    put_files(files, private=True)
    wsl_python("import os; os.chmod(" + repr(home) + ",0o700)")
    return base, plan


def export_tree(linux_path, destination):
    """Copy experiment data only; caller must never select a credential home."""
    if "codex-home" in linux_path or "auth" in linux_path:
        raise ValueError("credential export forbidden")
    script = "import sys,tarfile,pathlib\np=pathlib.Path(" + repr(linux_path) + ")\n" + """
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for child in p.rglob('*'):
  if child.is_file() and 'auth.json' not in child.parts and 'codex-home' not in child.parts:
   t.add(child,arcname=str(child.relative_to(p)),recursive=False)
"""
    import tarfile, io
    result = wsl_python(script, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        for member in archive:
            if not member.isfile():
                continue
            target = (destination / member.name).resolve()
            target.relative_to(destination.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as out:
                out.write(archive.extractfile(member).read())


if __name__ == "__main__":
    print(json.dumps(dict(zip(("runtime", "sha256"), provision_runtime()))))
