"""Backend/API and adapter checks only; no browser or UI results are claimed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.sites.discogs import evaluator as adapter
from fastapi.testclient import TestClient
from app.main import app


def main() -> None:
    case = adapter.CASES["collection_add"]
    adapter.reset(case)
    before = adapter.observe()
    digest = hashlib.sha256(adapter.DB.read_bytes()).hexdigest()
    repeated = adapter.observe()
    assert repeated == before
    assert hashlib.sha256(adapter.DB.read_bytes()).hexdigest() == digest
    # UI evidence is explicitly absent, not fabricated from the API.
    no_ui = {"url": "", "text": "", "errors": ["Browser/UI was not executed"]}
    snapshot = {"backend": before, "ui": no_ui}
    unmet = adapter.evaluate(case, snapshot, snapshot)
    assert not next(c for c in unmet if c["id"] == "exact_target_added")["passed"]
    assert not all(c["passed"] for c in unmet)
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200 and health.json() == {"ok": True}
        invalid = client.post("/auth/login", json={"username_or_email": "demo", "password": "incorrect-phase1-password"})
        assert invalid.status_code == 400 and invalid.json()["detail"] == "Invalid credentials"
        assert adapter.observe() == before
        login = client.post("/auth/login", json={"username_or_email": "demo", "password": "password123"})
        assert login.status_code == 200
        # Tokens stay only in process memory and are never recorded.
        token = login.json()["access_token"]
        mutation = client.post("/me/collection/221", headers={"Authorization": "Bearer " + token})
        assert mutation.status_code == 200
        changed = adapter.observe()
        assert 221 in changed["collection_ids"]
        assert changed["table_hashes"]["collection_items"] != before["table_hashes"]["collection_items"]
    actual_checks = adapter.evaluate(case, snapshot, {"backend": changed, "ui": no_ui})
    assert next(c for c in actual_checks if c["id"] == "exact_target_added")["passed"]
    assert not next(c for c in actual_checks if c["id"] == "list_page_visible")["passed"]
    assert not all(c["passed"] for c in actual_checks)
    adapter.reset(case)
    restored = adapter.observe()
    assert restored == before
    resets = []
    for fixed in adapter.CASES.values():
        evidence = adapter.reset(fixed)
        assert adapter.observe() == before
        resets.append({"case_id": fixed["id"], "table_hashes_match": evidence["table_hashes"] == before["table_hashes"]})
    result = {
        "scope": "Original backend and independent adapter component validation only; no browser UI execution",
        "health": {"status": health.status_code, "body": health.json()},
        "invalid_login": {"status": invalid.status_code, "detail": invalid.json()["detail"], "unchanged": True},
        "read_only_observation": {"equal_repeated_snapshot": True, "database_file_hash_unchanged": True},
        "unmet_collection_goal": unmet,
        "api_collection_add": {"status": mutation.status_code, "target_persisted": True,
                               "evaluator_checks_with_ui_absent": actual_checks, "not_a_ui_success": True},
        "reset_after_real_api_mutation": {"all_observed_state_restored": True},
        "resets": resets, "baseline_sha256": hashlib.sha256(adapter.BASELINE.read_bytes()).hexdigest(),
        "table_counts": before["table_counts"], "fixture": before["fixture"],
        "frontend_status": "blocked: Next.js and SWC unavailable offline",
    }
    destination = adapter.RUNTIME / "backend-offline-validation.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"backend_component_validation": "passed", "artifact": str(destination), "ui_executed": False}))


if __name__ == "__main__":
    main()
