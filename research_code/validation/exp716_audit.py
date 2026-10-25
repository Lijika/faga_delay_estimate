#!/usr/bin/env python3
"""Recompute the frozen exp716 paired tests from individual run evidence."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path("validation/results/exp716")


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    frozen, report = read("freeze.json"), read("100m-report.json")
    component = read("component-check.stdout")
    assert component == frozen["component"] == dict(
        all_equal=True, synthetic_dots=165600, real_dots=298560, queries=239616,
        folds=4, corners=99200, shared_geometry_bytes=69303616, shared_sum_bytes=597120)
    assert read("component-check.run.json")["exit_code"] == 0
    expected_order = ["AVW", "AVW", "WVA", "VAW", "WAV", "AWV", "VWA"]
    assert frozen["schedule"] == [list(s) for s in expected_order]
    assert len(report["runs"]) == 21
    timings, removed = {a: [] for a in "AVW"}, 0
    for iteration, order in enumerate(expected_order):
        for offset, arm in enumerate(order):
            stem = f"100m-{iteration}-{arm}"
            run, evidence, cleanup = [read(stem + suffix) for suffix in
                                      (".run.json", "-evidence.json", "-cleanup.json")]
            assert evidence == report["runs"][3 * iteration + offset]
            assert evidence["run"] == run and evidence["arm"] == arm
            assert evidence["iteration"] == iteration
            assert run["command"] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                                     "-in", frozen["input"]["path"], "-out", evidence["output"]["path"]]
            assert run["exit_code"] == 0 and run["threads"] == 1
            assert run["rss_bytes"] <= 300_000_000 and run["wall_s"] <= 3600
            assert run["cpu_s"] == run["user_s"] + run["sys_s"] < 100
            assert read(stem + ".stderr") == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            if arm != "A":
                assert read(stem + ".stdout") == dict(worker716="V256" if arm == "V" else "V512")
            for key in ("bytes", "sha256"):
                assert evidence["output"][key] == frozen["reference"][key]
            assert cleanup["file"] == evidence["output"] and cleanup["deleted"]
            assert cleanup["retained"] == frozen["reference"]
            assert cleanup["rebuild_command"] == run["command"]
            removed += evidence["output"]["bytes"]
            if iteration:
                timings[arm].append(run["cpu_s"])
    assert timings == report["timings_s"]
    means = {arm: statistics.mean(v) for arm, v in timings.items()}
    assert means == report["means_s"]
    stats = {}
    for arm in "VW":
        differences = [a - c for a, c in zip(timings["A"], timings[arm])]
        mean = sum(differences) / 6
        half = 3.163381449748624 * (sum((d - mean)**2 for d in differences) / 30)**.5
        record = report["stats"][arm]
        assert abs(record["saved_s"] - mean) < 1e-12
        assert all(abs(x - y) < 1e-12 for x, y in zip(
            record["simultaneous_ci95_s"], (mean - half, mean + half)))
        qualifies = mean >= .5 and mean - half > 0
        assert record["qualifies"] == qualifies
        stats[arm] = dict(saved_s=mean, simultaneous_ci95_s=[mean-half, mean+half], qualifies=qualifies)
    eligible = [a for a in "VW" if stats[a]["qualifies"]]
    selected = min(eligible, key=means.get) if eligible else "A"
    assert report["selected"] == selected
    assert report["all_checks_passed"] and report["complete_outputs_identical"]
    assert report["accuracy_delta_pp"] == 0 and report["exact_sample_rows"] == 1_916_928
    assert report["new_exact_rows"] == 0 and removed == report["removed_bytes"]
    for arm in "FVW":
        assert frozen["binaries"][arm]["bytes"] < 100_000_000
        assert all(s not in (ROOT / (arm+"-sections.txt")).read_text()
                   for s in (".init_array", ".ctors"))
        assert "_GLOBAL__sub_I" not in (ROOT / (arm+"-symbols.txt")).read_text()
    audit = dict(all_checks_passed=True, component_equal=True, audited_full_runs=21,
        all_outputs_match_frozen_reference=True, stats=stats, selected=selected, removed_bytes=removed,
        duplicate_checks_reused=True, independent_raw_output_rehash=False,
        generic_startup_disassembly_checked=False, masked_cpu_execution_checked=False,
        report_sha256=hashlib.sha256((ROOT / "100m-report.json").read_bytes()).hexdigest())
    (ROOT / "independent-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
