#!/usr/bin/env python3
"""Recompute the frozen parser experiment from individual run records."""
import json
from pathlib import Path
import statistics

from exp208_nominal_parent_tree import identity, write

ROOT = Path("validation/results/exp723")


def read(name):
    return json.loads((ROOT/name).read_text())


def main():
    frozen, report = read("freeze.json"), read("100m-report.json")
    assert frozen["schedule"] == [list(s) for s in ("AC", "AC", "CA", "AC", "CA", "AC", "CA")]
    component = read("component.stdout")
    assert component == frozen["component"] and component["all_equal"] and component["guard_pages_passed"]
    assert component["checks"] == 1_775_888 and component["reader_rows"] == 45_003
    assert read("component.run.json")["exit_code"] == 0
    times, released, maximum_rss = dict(A=[], C=[]), 0, 0
    assert len(report["runs"]) == 14
    for iteration, order in enumerate(frozen["schedule"]):
        for offset, arm in enumerate(order):
            stem = f"100m-{iteration}-{arm}"
            run, evidence, cleanup = [read(stem+suffix) for suffix in
                                      (".run.json", "-evidence.json", "-cleanup.json")]
            assert evidence == report["runs"][2*iteration+offset]
            assert evidence["run"] == run and evidence["arm"] == arm and evidence["iteration"] == iteration
            assert run["command"] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                "-in", frozen["input"]["path"], "-out", evidence["output"]["path"]]
            assert run["exit_code"] == 0 and run["threads"] == 1
            assert run["rss_bytes"] <= 2_000_000_000 and run["wall_s"] <= 3600
            assert abs(run["cpu_s"]-run["user_s"]-run["sys_s"]) < 1e-10 and run["cpu_s"] < 100
            assert read(stem+".stderr") == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            assert all(evidence["output"][k] == frozen["reference"][k] for k in ("bytes", "sha256"))
            assert cleanup["file"] == evidence["output"] and cleanup["retained"] == frozen["reference"]
            assert cleanup["rebuild_command"] == run["command"]
            released += evidence["output"]["bytes"]
            maximum_rss = max(maximum_rss, run["rss_bytes"])
            if iteration:
                times[arm].append(run["cpu_s"])
    assert report["timing"] == times
    differences = [a-c for a, c in zip(times["A"], times["C"])]
    mean = sum(differences)/6
    half = 2.570581835636314*(sum((v-mean)**2 for v in differences)/30)**.5
    assert abs(mean-report["saved_s"]) < 1e-12
    assert all(abs(a-b) < 1e-12 for a, b in zip([mean-half, mean+half], report["ci95_saved_s"]))
    selected = mean >= .5 and mean-half > 0
    assert report["selected"] == selected and report["all_checks_passed"]
    assert report["complete_outputs_identical"] and report["accuracy_delta_pp"] == 0
    assert report["exact_sample_rows"] == 1_916_928 and report["new_exact_rows"] == 0
    assert released == report["released_duplicate_bytes"]
    assert report["score_reused"] == frozen["score_reused"] and report["contract_reused"] == frozen["contract_reused"]
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True, selected=selected,
        mean_cpu_s={arm: statistics.mean(v) for arm, v in times.items()},
        saved_s=mean, ci95_saved_s=[mean-half, mean+half], maximum_rss_bytes=maximum_rss,
        complete_runs=14, exact_sample_rows=1_916_928, released_duplicate_bytes=released,
        output_hash_evidence_reused=True, deleted_outputs_reread=False,
        report=identity(ROOT/"100m-report.json"), freeze=identity(ROOT/"freeze.json"),
        auditor=identity(__file__)))
    print("EXP723_AUDIT", selected, mean, flush=True)


if __name__ == "__main__":
    main()
