import copy
import json

import pytest

from harness.tests.test_phase2_reporting_v002 import complete_archive, write
from harness.tests.test_phase2_validity_v001 import ARGS, qualified_archive
from harness.phase2.handoff_v003 import build_handoff
from harness.phase2.records import sha256
from harness.phase2.report_lineage_v001 import (
    checked_handoff, checked_reference, check_presentation_sidecars,
    check_raw_totals, check_truth_index,
)
from harness.phase2.validity_report_v001 import build_validity_report


def test_same_hash_in_wrong_reference_role_is_rejected(tmp_path):
    first, other = tmp_path / "first.json", tmp_path / "other.json"
    write(first, {"generic": "same bytes do not establish the expected file role"})
    other.write_bytes(first.read_bytes())
    refs = {"evaluation_report": {"path": "other.json", "sha256": sha256(other)}}
    with pytest.raises(ValueError, match="wrong input role"):
        checked_reference(refs, "evaluation_report", experiment=tmp_path, expected=first)


def test_aggregate_or_denominator_tampering_is_rejected(complete_archive):
    root, _ = complete_archive
    raw = json.loads((root / "reports/full.json").read_text(encoding="utf-8"))
    check_raw_totals(raw)
    wrong = copy.deepcopy(raw)
    wrong["overall"]["prediction_field_denominator"] = 539
    with pytest.raises(ValueError, match="totals differ"):
        check_raw_totals(wrong)
    wrong = copy.deepcopy(raw)
    wrong["runs"][0]["summary"]["task_counts"]["passed"] = 30
    with pytest.raises(ValueError, match="run totals"):
        check_raw_totals(wrong)


def test_handoff_revalidation_cannot_promote_quarantined_knowledge(qualified_archive):
    root, _ = qualified_archive
    write(root / "reports/validity.json", build_validity_report(*ARGS, experiment=root))
    handoff = build_handoff(*ARGS, "reports/validity.json", experiment=root)
    path = root / "handoff/final.json"
    write(path, handoff)
    checked_handoff(path, expected_paths={"evaluation_report": root / ARGS[1]}, experiment=root)
    handoff["quarantined_packages"][0]["phase_three_access_allowed"] = True
    write(path, handoff)
    with pytest.raises(ValueError, match="independent admission chain"):
        checked_handoff(path, experiment=root)


def test_mixed_presentation_artifacts_are_rejected(tmp_path):
    raw, validity, handoff = [tmp_path / (name + ".json") for name in ("raw", "validity", "handoff")]
    for path in (raw, validity, handoff):
        write(path, {"name": path.stem})
    evidence, figure = tmp_path / "evidence.md", tmp_path / "figure.png"
    evidence.write_text("generic index", encoding="utf-8")
    figure.write_bytes(b"generic image fixture")
    e = {"report_sha256": sha256(raw), "handoff_sha256": sha256(handoff),
         "index_sha256": sha256(evidence), "selection_uses_outcome_score": False}
    f = {"raw_report_sha256": sha256(raw), "validity_report_sha256": sha256(validity),
         "registered_case_denominator": 180, "artifacts": {figure.name: sha256(figure)}}
    write(evidence.with_suffix(".provenance.json"), e)
    write(figure.with_suffix(".provenance.json"), f)
    args = {"raw_path": raw, "validity_path": validity, "handoff_path": handoff}
    check_presentation_sidecars(evidence, figure, **args)
    evidence.write_text("different index", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence index"):
        check_presentation_sidecars(evidence, figure, **args)
    evidence.write_text("generic index", encoding="utf-8")
    f["raw_report_sha256"] = sha256(validity)
    write(figure.with_suffix(".provenance.json"), f)
    with pytest.raises(ValueError, match="figure provenance"):
        check_presentation_sidecars(evidence, figure, **args)


def test_truth_archive_requires_each_distinct_registered_case(complete_archive):
    root, independent = complete_archive
    raw_path = root / "reports/full.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    archive = root / "private/truth"
    refs = []
    for run in raw["runs"]:
        for case in run["cases"]:
            source = f"evaluations/{run['run_id']}/case-{case['case_index']:02d}/case-manifest.json"
            path = archive / run["run_id"] / f"case-{case['case_index']:02d}.json"
            write(path, {"run_id": run["run_id"], "case_index": case["case_index"], "case_id": case["case_id"],
                         "source_case_manifest_path": source, "source_case_manifest_sha256": run["case_manifest_hashes"][source]})
            refs.append({"path": path.relative_to(archive).as_posix(), "sha256": sha256(path)})
    index_path = archive / "archive-index.json"
    index = {"schema_version": 1, "kind": "independent_truth_originals_archive", "status": "complete", "denominator": 180,
             "report_sha256": sha256(raw_path), "schedule_sha256": raw["schedule_sha256"], "case_archives": refs}
    write(index_path, index)
    independent["truth_archive_index"] = {"path": index_path.relative_to(root).as_posix(), "sha256": sha256(index_path)}
    independent_path = root / "reviews/independent.json"
    write(independent_path, independent)
    check_truth_index(index_path, independent_path, raw_path, experiment=root)
    index["case_archives"][-1] = copy.deepcopy(index["case_archives"][0])
    write(index_path, index)
    independent["truth_archive_index"]["sha256"] = sha256(index_path)
    write(independent_path, independent)
    with pytest.raises(ValueError, match="duplicate"):
        check_truth_index(index_path, independent_path, raw_path, experiment=root)
