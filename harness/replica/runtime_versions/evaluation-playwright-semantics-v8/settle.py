"""Opt-in single-lane bounded load/network/DOM+AX stability checks.

No counterpart state or expected business tree enters this module. Repeated
captures test only consecutive equality in this lane; website actions are never
retried. The worker writes a private deadline for the external runner watchdog.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
import importlib.util
_diagnostic_spec=importlib.util.spec_from_file_location("replica_acquisition_diagnostics",Path(__file__).with_name("acquisition_diagnostics.py"))
_diagnostic_module=importlib.util.module_from_spec(_diagnostic_spec)
_diagnostic_spec.loader.exec_module(_diagnostic_module)
capture_summary=_diagnostic_module.capture_summary
exception_summary=_diagnostic_module.exception_summary

DEFAULTS = {"version":"single-lane-dom-ax-playwright/v2", "enabled":False,
            "load_state":"domcontentloaded", "load_timeout_ms":2000,
            "networkidle_timeout_ms":3000, "network_quiet_ms":500, "sample_interval_ms":200,
            "sample_window_ms":3000, "stable_samples":2,
            "total_timeout_ms":8000, "watchdog_grace_ms":500}


def normalize_policy(value=None):
    if value in (None, False): value={"enabled":False}
    if value is True: value={"enabled":True}
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):
        raise ValueError("settle policy must contain only the registered v1 fields")
    policy={**DEFAULTS, **value}
    if not isinstance(policy["enabled"],bool) or policy["version"]!=DEFAULTS["version"] or policy["load_state"] not in {"domcontentloaded","load"}:
        raise ValueError("invalid settle policy version/state/enabled flag")
    for key in ("load_timeout_ms","networkidle_timeout_ms","network_quiet_ms","sample_interval_ms","sample_window_ms","total_timeout_ms","watchdog_grace_ms","stable_samples"):
        if isinstance(policy[key],bool) or not isinstance(policy[key],int): raise ValueError("integer settle bounds required")
    if not 50 <= policy["sample_interval_ms"] <= 1000 or not 2 <= policy["stable_samples"] <= 10:
        raise ValueError("settle sampling interval/count outside registered bounds")
    if not 100 <= policy["total_timeout_ms"] <= 60000 or not 0 <= policy["watchdog_grace_ms"] <= 2000:
        raise ValueError("settle total/watchdog bounds outside registered bounds")
    if not 100 <= policy["network_quiet_ms"] <= policy["networkidle_timeout_ms"]:
        raise ValueError("fresh network quiet window must fit its phase bound")
    for key in ("load_timeout_ms","networkidle_timeout_ms","sample_window_ms"):
        if not 1 <= policy[key] <= policy["total_timeout_ms"]: raise ValueError("settle phase bound exceeds total")
    if policy["sample_window_ms"] < policy["sample_interval_ms"]*(policy["stable_samples"]-1):
        raise ValueError("sample window cannot establish the registered consecutive count")
    return policy


def policy_hash(policy):
    return hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def run(page, policy, capture, canonicalize, status_path, *, label, action, source_location=None, pending_requests=lambda:0, network_diagnostics=lambda:None):
    policy=normalize_policy(policy)
    result={"enabled":policy["enabled"],"status":"not_requested","policy_sha256":policy_hash(policy),
            "label":label,"action":action,"source_location":source_location,"samples":[],"phases":[],"sample_diagnostics":[],
            "signature_scope":"entire canonical DOM and Chromium AX plus complete Playwright DOM-derived per-frame semantics; sequential non-atomic capture; no counterpart input or business-field ignore list",
            "website_action_retries":0,"counterpart_input":False}
    if not policy["enabled"]: return result
    started=time.monotonic(); deadline=started+policy["total_timeout_ms"]/1000
    result.update(status="running", started_monotonic=started,deadline_monotonic=deadline,
                  watchdog_deadline_monotonic=deadline+policy["watchdog_grace_ms"]/1000)
    status_path=Path(status_path)
    def persist():
        result["elapsed_seconds"]=time.monotonic()-started
        diagnostics=network_diagnostics()
        if diagnostics is not None:result["network_diagnostics"]=diagnostics
        temp=status_path.with_name(status_path.name+".next")
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        temp.replace(status_path)
    def fail(reason,error=None):
        result.update(status="unconfirmed",reason=reason)
        if error: result["error_type"]=exception_summary(error)["error_type"]
        persist();return result
    persist()
    for state,bound in ((policy["load_state"],policy["load_timeout_ms"]),("networkidle",policy["networkidle_timeout_ms"])):
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0:return fail("total_timeout_before_"+state)
        phase_start=time.monotonic()
        try:
            page.wait_for_load_state(state,timeout=max(1,min(bound,remaining)))
            result["phases"].append({"state":state,"status":"ready","elapsed_seconds":time.monotonic()-phase_start})
        except Exception as error:
            result["phases"].append({"state":state,"status":"unconfirmed","elapsed_seconds":time.monotonic()-phase_start})
            return fail("native_"+state+"_timeout_or_failure",error)
        persist()
        if state == "networkidle":
            # Playwright lifecycle networkidle may already be latched from a
            # prior load. Require a fresh quiet interval as well, after this
            # action, while pumping this lane's native browser event queue.
            quiet_since=None; maximum_pending=0
            phase_deadline=min(deadline,phase_start+bound/1000)
            while time.monotonic()<phase_deadline:
                now=time.monotonic(); count=pending_requests(); maximum_pending=max(maximum_pending,count)
                if count:
                    quiet_since=None
                elif quiet_since is None:
                    quiet_since=now
                elif (now-quiet_since)*1000>=policy["network_quiet_ms"]:
                    result["phases"].append({"state":"fresh_network_quiet","status":"ready","elapsed_seconds":now-phase_start,"maximum_pending_requests":maximum_pending})
                    break
                page.wait_for_timeout(max(1,min(25,int((phase_deadline-now)*1000))))
            else:
                result["phases"].append({"state":"fresh_network_quiet","status":"unconfirmed","elapsed_seconds":time.monotonic()-phase_start,"maximum_pending_requests":maximum_pending})
                return fail("network_not_quiet_within_bound")
            persist()
    sample_deadline=min(deadline,time.monotonic()+policy["sample_window_ms"]/1000)
    previous=None;consecutive=0
    while time.monotonic()<sample_deadline:
        if pending_requests():return fail("network_resumed_during_samples")
        capture_started=time.monotonic(); snapshot=None; canonical=None
        diagnostic={"attempt":len(result["sample_diagnostics"])+1,"stage":"capture"}
        stage_started=capture_started
        try:
            snapshot=capture(page)
            diagnostic["capture_seconds"]=time.monotonic()-stage_started
            diagnostic["stage"]="canonicalize";stage_started=time.monotonic()
            canonical=canonicalize(snapshot)
            diagnostic["canonicalize_seconds"]=time.monotonic()-stage_started
            diagnostic["stage"]="digest";stage_started=time.monotonic()
            digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            diagnostic["digest_seconds"]=time.monotonic()-stage_started
        except Exception as error:
            diagnostic.update(**capture_summary(snapshot,canonical),**exception_summary(error),outcome="error",failure_stage=diagnostic["stage"],failed_stage_seconds=time.monotonic()-stage_started)
            result["sample_diagnostics"].append(diagnostic)
            return fail("sample_acquisition_failure",error)
        diagnostic.update(**capture_summary(snapshot,canonical),outcome="unsupported" if canonical.get("unsupported") else "acquired",whole_attempt_seconds=time.monotonic()-capture_started)
        result["sample_diagnostics"].append(diagnostic)
        # A slow/hung renderer is also bounded by the independent runner watchdog;
        # no sample ending after its predeclared window can establish stability.
        if time.monotonic()>sample_deadline:return fail("sample_window_or_total_timeout")
        if canonical.get("unsupported"):return fail("unsupported_sample_acquisition")
        consecutive=consecutive+1 if digest==previous else 1
        previous=digest
        result["samples"].append({"index":len(result["samples"])+1,"canonical_sha256":digest,
                                  "capture_seconds":time.monotonic()-capture_started,"consecutive_equal":consecutive})
        if consecutive>=policy["stable_samples"]:
            result.update(status="stable",consecutive_equal=consecutive);persist();return result
        persist()
        remaining_ms=int((sample_deadline-time.monotonic())*1000)
        if remaining_ms<=0:break
        page.wait_for_timeout(min(policy["sample_interval_ms"],remaining_ms))
    return fail("no_consecutive_stability_within_window")
