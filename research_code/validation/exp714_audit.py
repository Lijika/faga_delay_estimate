#!/usr/bin/env python3
"""Audit the saved exp714 component, paired runs and duplicate cleanup."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path("validation/results/exp714")


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    frozen, report = read("freeze.json"), read("100m-report.json")
    component = read("component-check.stdout")
    assert component == frozen["component"] == dict(
        all_equal=True, queries=239616, folds=4, corners=99200, prepared_bytes=56)
    assert read("component-check.run.json")["exit_code"] == 0
    assert len(frozen["schedule"]) == 7 and len(report["runs"]) == 14
    timings, removed = {"A": [], "C": []}, 0
    for iteration, order in enumerate(frozen["schedule"]):
        for offset, arm in enumerate(order):
            stem = f"100m-{iteration}-{arm}"
            run, evidence, cleanup = [read(stem + suffix) for suffix in
                                      (".run.json", "-evidence.json", "-cleanup.json")]
            assert evidence == report["runs"][2 * iteration + offset]
            assert evidence["run"] == run and evidence["arm"] == arm
            assert evidence["iteration"] == iteration
            assert run["command"][:4] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"]]
            assert run["command"][4:] == ["-in", frozen["input"]["path"],
                                          "-out", evidence["output"]["path"]]
            assert run["exit_code"] == 0 and run["threads"] == 1
            assert run["rss_bytes"] <= 300_000_000 and run["wall_s"] <= 3600
            assert run["cpu_s"] == run["user_s"] + run["sys_s"] < 100
            assert read(stem + ".stderr") == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            for key in ("bytes", "sha256"):
                assert evidence["output"][key] == frozen["reference"][key]
            assert cleanup["file"] == evidence["output"] and cleanup["deleted"]
            assert cleanup["retained"] == frozen["reference"]
            assert cleanup["rebuild_command"] == run["command"]
            removed += evidence["output"]["bytes"]
            if iteration:
                timings[arm].append(run["cpu_s"])
    assert timings == report["timings_s"]
    differences = [a - c for a, c in zip(timings["A"], timings["C"])]
    mean = sum(differences) / 6
    half = 2.570581835636314 * (sum((x - mean)**2 for x in differences) / 30)**.5
    assert abs(mean - report["saved_s"]) < 1e-12
    assert all(abs(a-b) < 1e-12 for a, b in zip(
        [mean - half, mean + half], report["paired_ci95_s"]))
    assert report["means_s"] == {arm: statistics.mean(v) for arm, v in timings.items()}
    assert report["selected"] == ("C" if mean >= .5 and mean - half > 0 else "A")
    assert report["all_checks_passed"] and report["complete_outputs_identical"]
    assert report["quality_delta_pp"] == 0 and report["exact_sample_rows"] == 1_916_928
    assert report["new_exact_rows"] == 0 and removed == report["removed_bytes"]
    audit = dict(all_checks_passed=True, component_equal=True, audited_full_runs=14,
        all_outputs_match_frozen_reference=True, paired_saved_s=mean,
        paired_ci95_s=[mean-half, mean+half], selected=report["selected"], removed_bytes=removed,
        duplicate_checks_reused=True, independent_raw_output_rehash=False,
        report_sha256=hashlib.sha256((ROOT / "100m-report.json").read_bytes()).hexdigest())
    (ROOT / "independent-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
