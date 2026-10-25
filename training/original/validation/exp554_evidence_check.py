#!/usr/bin/env python3
"""Check saved exp554 evidence without executing the estimator or training."""
import hashlib
import json
from pathlib import Path

ROOT = Path("validation/results/exp554")
read = lambda path: json.loads(Path(path).read_text())


def main():
    report = read(ROOT / "report.json")
    split = read(ROOT / "split.json")
    training = read(ROOT / "training.json")
    independent = read(ROOT / "independent.json")
    groups = read(ROOT / "groups.json")
    freeze = read(ROOT / "freeze.json")
    cost = read(ROOT / "cost.json")
    manifest = read("validation/results/exp554-launch/received.json")
    for record in manifest["files"]:
        p = Path(record["local_path"])
        assert p.stat().st_size == record["bytes"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == record["sha256"], str(p)
    assert report["rows"] == 1_000_000 and report["sources"] == 208 and report["targets"] == 288
    assert report["pairs"] == 59904 and report["all_checks_passed"]
    assert report["all_full_port"] and report["all_cluster_disjoint"]
    assert not report["independent_queries"]
    assert split["all_full_port"] and split["all_cluster_disjoint"] and split["development_only"]
    assert sum(r["rows"] for r in split["folds"]) == report["rows"]
    assert sum(r["clusters"] for r in split["folds"]) == 960505
    assert len(split["folds"]) == 3
    for row in split["folds"]:
        assert row["rows"] + row["train_rows"] == report["rows"]
        assert row["pairs"] == 59904 and row["min_pair_rows"] >= 1 and row["cluster_disjoint"]
    assert len(training["records"]) == 18 and training["xgboost_version"] == "3.0.5"
    names = report["prediction_names"]
    assert names[:3] == ["L", "O", "exp354"] and len(names) == 9
    assert independent["all_bitwise_equal"] and not independent["production_timing"]
    assert {r["name"] for r in independent["runs"]} == set(names[3:])
    for run in independent["runs"]:
        assert run["exit_code"] == 0 and run["threads"] == 1 and run["bitwise_equal"]
        assert run["counters"]["rows"] == report["rows"] and run["output"]["bytes"] == 4_000_000
    for name in names:
        overall = report["statistics"][name]
        assert overall["rows"] == report["rows"]
        assert overall["exact_rows"] + overall["under_rows"] + overall["over_rows"] == report["rows"]
        for family in groups.values():
            rows = [group[name] for group in family.values()]
            for key in ("rows", "squared_ps", "exact_rows", "under_rows", "over_rows"):
                assert sum(r[key] for r in rows) == overall[key], (name, key)
            for key in ("accuracy_pp", "mae_ps", "mean_error_ps"):
                value = sum(r[key] * r["rows"] for r in rows) / report["rows"]
                assert abs(value - overall[key]) < 1e-8, (name, key)
    for name in names[3:]:
        rows = [r for r in training["records"] if r["name"] == name]
        assert len(rows) == 3
        assert sum(r["train"]["rows"] for r in rows) == 2_000_000
        assert sum(r["validation"]["rows"] for r in rows) == report["rows"]
        assert sum(r["validation"]["squared_ps"] for r in rows) == report["statistics"][name]["squared_ps"]
        d = report["decomposition"][name]
        assert d["representation_squared_ps"] + d["coupling_squared_ps"] - 2 * d["error_coupling_cross_ps"] == report["statistics"][name]["squared_ps"]
    for row in report["paired"].values():
        assert row["better_rows"] + row["worse_rows"] + row["equal_score_rows"] == report["rows"]
        assert row["draws"] == 2000 and row["clusters"] == 960505
        assert row["ci95_pp"][0] <= row["delta_pp"] <= row["ci95_pp"][1]
    old = read("validation/results/exp553/report.json")
    for name in ("L", "O", "exp354"):
        assert report["statistics"][name] == old["statistics"][name]
    plan = ROOT / "protocol-original.md"
    expected = next(r for r in freeze["files"] if r["path"] == str(plan))
    assert hashlib.sha256(plan.read_bytes()).hexdigest() == expected["sha256"]
    assert cost["assets_bytes"] <= 1_000_000_000 and cost["production_runs"] == 0
    assert cost["deleted_files"] == [] and cost["freed_bytes"] == 0
    print("EXP554_SAVED_FULL_PORT_FUNCTION_EVIDENCE_PASSED")


if __name__ == "__main__":
    main()
