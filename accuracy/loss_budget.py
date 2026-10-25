#!/usr/bin/env python3
"""Decompose the existing exp728 weighted Acc loss without running the estimator."""
import json
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: loss_budget.py NEW_REPORT_JSON")
    root = Path(__file__).resolve().parents[1]
    source = root / "validation/results/exp722/score-1b/accuracy.json"
    score = json.loads(source.read_text())
    overall = score["accuracy"]["C"]["point_pp"]
    groups = {}
    for name in ("distance", "near_axis", "event", "direction", "source_family"):
        records = []
        for key, r in score["groups"][name].items():
            fraction = r["estimated_population_rows"] / 1_000_000_000
            accuracy = r["accuracy_pp"]["C"]
            records.append(dict(group=key, population_fraction=fraction,
                accuracy_pp=accuracy, population_loss_pp=fraction * (100 - accuracy)))
        assert abs(sum(r["population_fraction"] for r in records) - 1) < 1e-12
        assert abs(sum(r["population_loss_pp"] for r in records) - (100 - overall)) < 1e-10
        groups[name] = records
    result = dict(source=str(source.relative_to(root)), exp728_accuracy_pp=overall,
        delta_needed_to_reach_99_pp=99 - overall, strict_target_requires_more=True,
        groups=groups, scope="Historical 1B stratified estimate; partitions overlap across group types",
        oracle_interpretation="Perfect predictions only in a group recover its population_loss_pp",
        complete_estimator_runs=0)
    with Path(sys.argv[1]).open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps(groups["event"], indent=2))


if __name__ == "__main__":
    main()
