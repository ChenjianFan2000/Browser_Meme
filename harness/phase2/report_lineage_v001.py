"""Verify exact input roles before presenting frozen experiment results."""
from __future__ import annotations

from pathlib import Path

from .handoff_v002 import contained
from .handoff_v003 import build_handoff
from .records import sha256
from .report_v002 import aggregate, read
from .run_learning import EXPERIMENT
from .validity_report_v001 import build_validity_report


def checked_reference(references, name, *, experiment=EXPERIMENT, expected=None):
    reference = references.get(name)
    if not isinstance(reference, dict):
        raise ValueError("missing named reference: " + name)
    path = contained(experiment, reference["path"])
    if expected is not None and path.resolve() != Path(expected).resolve(strict=True):
        raise ValueError("reference has wrong input role: " + name)
    if sha256(path) != reference.get("sha256"):
        raise ValueError("named reference hash mismatch: " + name)
    return path


def check_raw_totals(raw):
    expected = {(f"{condition.lower()}-seed-{seed}", condition, seed)
                for seed in (1729, 2718, 3141) for condition in ("A", "B")}
    runs = raw.get("runs", [])
    identities = [(row["run_id"], row["condition"], row["seed"]) for row in runs]
    if (raw.get("schema_version") != 2 or raw.get("status") != "complete"
            or len(identities) != 6 or set(identities) != expected):
        raise ValueError("complete fixed six-run report required")
    for run in runs:
        indices = [row["case_index"] for row in run["cases"]]
        if len(indices) != 30 or set(indices) != set(range(1, 31)):
            raise ValueError("each run must retain 30 distinct cases")
        if run["summary"] != aggregate(run["cases"]):
            raise ValueError("run totals differ from case rows")
    conditions = {condition: aggregate([case for run in runs if run["condition"] == condition
                                        for case in run["cases"]]) for condition in ("A", "B")}
    overall = aggregate([case for run in runs for case in run["cases"]])
    if raw.get("conditions") != conditions or raw.get("overall") != overall:
        raise ValueError("overall or condition totals differ from case rows")
    if (overall["case_denominator"] != 180 or overall["prediction_field_denominator"] != 540
            or overall["archived_evaluation_count"] != 180
            or any(row["case_denominator"] != 90 or row["prediction_field_denominator"] != 270
                   for row in conditions.values())):
        raise ValueError("registered denominators must remain 180/540 and 90/270 per condition")


def checked_validity(raw_path, validity_path, *, experiment=EXPERIMENT):
    raw, validity = read(raw_path), read(validity_path)
    check_raw_totals(raw)
    refs = validity.get("references", {})
    paths = {name: checked_reference(refs, name, experiment=experiment,
                                     expected=raw_path if name == "evaluation_report" else None)
             for name in ("learning_review", "evaluation_report", "independent_review", "deviations")}
    expected = build_validity_report(paths["learning_review"], paths["evaluation_report"],
                                    paths["independent_review"], deviations=paths["deviations"],
                                    experiment=experiment)
    if validity != expected:
        raise ValueError("validity differs from independently bound raw records")
    return raw, validity


def checked_handoff(handoff_path, *, expected_paths=None, experiment=EXPERIMENT):
    handoff = read(handoff_path)
    refs = handoff.get("management_reviews", {})
    expected_paths = expected_paths or {}
    paths = {name: checked_reference(refs, name, experiment=experiment, expected=expected_paths.get(name))
             for name in ("learning_review", "evaluation_report", "independent_review", "deviations", "validity_report")}
    raw = read(paths["evaluation_report"])
    check_raw_totals(raw)
    expected = build_handoff(paths["learning_review"], paths["evaluation_report"],
                             paths["independent_review"], paths["validity_report"],
                             deviations=paths["deviations"], experiment=experiment)
    if handoff != expected:
        raise ValueError("handoff differs from the final independent admission chain")
    return handoff, paths


def check_presentation_sidecars(evidence_path, figure_path, *, raw_path, validity_path, handoff_path):
    evidence_path, figure_path = Path(evidence_path), Path(figure_path)
    evidence_sidecar = evidence_path.with_suffix(".provenance.json")
    figure_sidecar = figure_path.with_suffix(".provenance.json")
    evidence, figure = read(evidence_sidecar), read(figure_sidecar)
    if (evidence.get("report_sha256") != sha256(raw_path)
            or evidence.get("handoff_sha256") != sha256(handoff_path)
            or evidence.get("index_sha256") != sha256(evidence_path)
            or evidence.get("selection_uses_outcome_score") is not False):
        raise ValueError("evidence index provenance differs from final inputs")
    if (figure.get("raw_report_sha256") != sha256(raw_path)
            or figure.get("validity_report_sha256") != sha256(validity_path)
            or figure.get("registered_case_denominator") != 180
            or figure.get("artifacts", {}).get(figure_path.name) != sha256(figure_path)):
        raise ValueError("figure provenance differs from final inputs")
    return evidence_sidecar, figure_sidecar


def check_truth_index(index_path, independent_path, raw_path, *, experiment=EXPERIMENT):
    independent, raw = read(independent_path), read(raw_path)
    checked_reference(independent, "truth_archive_index", experiment=experiment, expected=index_path)
    index = read(index_path)
    if (index.get("schema_version") != 1 or index.get("kind") != "independent_truth_originals_archive"
            or index.get("status") != "complete" or index.get("denominator") != 180
            or index.get("report_sha256") != sha256(raw_path)
            or index.get("report_sha256") != independent.get("evaluation_report_sha256")
            or index.get("schedule_sha256") != raw["schedule_sha256"]
            or index.get("schedule_sha256") != independent.get("formal_schedule_sha256")):
        raise ValueError("truth archive does not bind the final report and independent review")
    expected = {(run["run_id"], case["case_index"]): (run, case)
                for run in raw["runs"] for case in run["cases"]}
    entries, seen_paths, seen_cases = index.get("case_archives", []), set(), set()
    if len(entries) != 180:
        raise ValueError("truth archive must contain 180 case manifests")
    for reference in entries:
        manifest_path = contained(Path(index_path).parent, reference["path"])
        if manifest_path in seen_paths or sha256(manifest_path) != reference["sha256"]:
            raise ValueError("duplicate or changed truth case manifest")
        seen_paths.add(manifest_path)
        item = read(manifest_path)
        key = (item["run_id"], item["case_index"])
        if key in seen_cases or key not in expected:
            raise ValueError("truth archive case identity differs")
        seen_cases.add(key)
        run, case = expected[key]
        source = f"evaluations/{key[0]}/case-{key[1]:02d}/case-manifest.json"
        if (item["case_id"] != case["case_id"] or item["source_case_manifest_path"] != source
                or item["source_case_manifest_sha256"] != run["case_manifest_hashes"].get(source)):
            raise ValueError("truth case manifest differs from the frozen raw case binding")
    if seen_cases != set(expected):
        raise ValueError("truth archive does not cover the exact registered cases")
