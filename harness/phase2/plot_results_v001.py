"""Export fixed-denominator results and the independent compliance sensitivity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .records import sha256, write_new_json
from .report_lineage_v001 import checked_validity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--validity", required=True)
    parser.add_argument("--output-prefix", required=True)
    args = parser.parse_args()
    raw_path, validity_path = Path(args.raw), Path(args.validity)
    raw, validity = checked_validity(raw_path, validity_path)
    paired = validity["compliant_paired_sensitivity"]
    if paired["status"] != "available":
        raise ValueError("no compliant pairs to visualize; do not substitute an unpaired cohort")
    prefix = Path(args.output_prefix)
    targets = [prefix.with_suffix(suffix) for suffix in (".png", ".pdf", ".provenance.json")]
    if any(path.exists() for path in targets):
        raise FileExistsError("figure artifacts already exist")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"passed": "#2a9d8f", "failed": "#e76f51", "unable_to_confirm": "#e9c46a",
              "unsafe_reset": "#8b5fbf", "infrastructure_error": "#6c757d", "not_run": "#b6b6b6", "correct": "#2a9d8f",
              "incorrect": "#e76f51", "unknown": "#e9c46a", "unscorable": "#b6b6b6"}
    cohorts = [(raw["conditions"], f"Registered cohort: {raw['overall']['case_denominator']} cases"),
               (paired["conditions"], f"Compliant paired sensitivity: {paired['overall']['case_denominator']} cases")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.8), constrained_layout=True)
    for column, (conditions, title) in enumerate(cohorts):
        for row_index, (field, denominator, label) in enumerate([
                ("task_counts", "case_denominator", "Task outcomes"),
                ("prediction_counts", "prediction_field_denominator", "Whole-task prediction fields")]):
            ax = axes[row_index, column]
            statuses = [key for key in colors if any(conditions[group][field].get(key, 0) for group in ("A", "B"))]
            for y, group in enumerate(("A", "B")):
                counts = conditions[group][field]
                total = conditions[group][denominator]
                if sum(counts.values()) != total or set(counts) - set(colors):
                    raise ValueError("chart categories do not exhaust the fixed denominator")
                left = 0.0
                for status in statuses:
                    count = counts.get(status, 0)
                    width = count / total * 100
                    ax.barh(y, width, left=left, color=colors[status],
                            label=status.replace("_", " ") if y == 0 else None, height=0.52)
                    if width >= 7:
                        ax.text(left + width / 2, y, str(count), ha="center", va="center", fontsize=10)
                    left += width
                ax.text(101, y, f"n={total}", va="center", fontsize=9)
            ax.set_title(title + "\n" + label, fontsize=11)
            ax.set_yticks([0, 1], ["A: executable model", "B: prose knowledge"])
            ax.invert_yaxis()
            ax.set_xlim(0, 116)
            ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.33), ncol=2, frameon=False, fontsize=9)
            ax.spines[["top", "right", "left"]].set_visible(False)
    seeds = ", ".join(map(str, paired["paired_seeds"]))
    fig.suptitle(f"Phase two frozen evaluation | paired seeds: {seeds}\n"
                 f"{validity['diagnostic_only_case_count']} registered cases are diagnostic only; no strict speed claim.", fontsize=12)
    fig.savefig(targets[0], dpi=220, bbox_inches="tight")
    fig.savefig(targets[1], bbox_inches="tight")
    plt.close(fig)
    write_new_json(targets[2], {"raw_report_sha256": sha256(raw_path), "validity_report_sha256": sha256(validity_path),
                   "generator_sha256": sha256(Path(__file__)), "paired_seeds": paired["paired_seeds"],
                   "lineage_validator_sha256": sha256(Path(__file__).with_name("report_lineage_v001.py")),
                   "artifacts": {path.name: sha256(path) for path in targets[:2]},
                   "registered_case_denominator": 180, "original_results_rewritten": False})
    print(json.dumps({"figure": str(targets[0]), "pdf": str(targets[1])}))


if __name__ == "__main__":
    main()
