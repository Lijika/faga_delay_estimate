#!/usr/bin/env python3
"""Measure certified fixed-path evaluation after shared dense-row expansion."""
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp718"), Path("build/exp718")
PLAN = Path("experiment/实验718-共享片段稠密行的直接寻址成本.md")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
execution.ROOT = ROOT
SEED, EVALUATIONS = 20261025718, 239616*64


def prepare():
    assert not ROOT.exists() and not BUILD.exists()
    assert read("../exp717/validation/results/exp717/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True);BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    previous = read("../exp717/validation/results/exp717/report.json")
    names = {"maps.bin", "bindings.bin", "terms.u16", "counts.u32"}
    inputs = [check("../exp717/"+p["path"], p) for p in previous["files"] if Path(p["path"]).name in names]
    assert len(inputs) == 4
    query = next(p for p in read("../exp717/validation/results/exp717/freeze.json")["inputs"]
                 if Path(p["path"]).name == "queries.bin")
    inputs.append(check(query["path"], query))
    text = Path("tests/exp710_motion_words.cpp").read_text()
    definitions = text[text.index("struct Value710"):text.index("\nMap710 compile710")]
    text = Path("tests/exp717_shared_fragments.cpp").read_text()
    definitions += "\n"+text[text.index("struct Binding717"):text.index("\nstd::vector<unsigned> partition717")]
    (BUILD/"exp718_records.h").write_text(definitions)
    order = np.random.default_rng(SEED).permutation(239616).astype("<u4")
    order.tofile(BUILD/"order.u32")
    command = ["g++", "-std=c++17", "-O3", "-march=x86-64", "-mtune=generic",
        "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
        "-I", str(BUILD), "tests/exp718_dense_fragments.cpp", "-static",
        "-o", str(BUILD/"dense-fragments")]
    execution.measured(command, "compile")
    assert not (ROOT/"compile.stderr").read_bytes()
    arguments = ["../exp717/build/exp717", query["path"], str(BUILD/"order.u32")]
    execution.measured([str(BUILD/"dense-fragments"), *arguments, "C", "0"], "component-check")
    component = read(ROOT/"component-check.stdout")
    assert component["all_equal"] and component["grid_points"] == 64284000
    assert component["queries"] == 239616 and component["negative_cases"] == 479232
    write(ROOT/"freeze.json", dict(inputs=inputs, command=command, binary=identity(BUILD/"dense-fragments"),
        arguments=arguments, component=component, seed=SEED, round_rotation=9973, evaluations=EVALUATIONS,
        schedule=[list(s) for s in ("AD", "AD", "DA", "AD", "DA", "AD", "DA")],
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md",
               Path("tests/exp710_motion_words.cpp"), Path("tests/exp717_shared_fragments.cpp"),
               Path("tests/exp718_dense_fragments.cpp"), BUILD/"exp718_records.h", BUILD/"order.u32")],
        cpuinfo=Path("/proc/cpuinfo").read_text().split("\n\n")[0],
        compiler=subprocess.check_output(["g++", "--version"], text=True),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP718_BUILD", component, flush=True)


def run():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["inputs"]+frozen["files"]+[frozen["binary"]]:
        check(item["path"], item)
    assert frozen["component"]["dense_bytes"] <= 33_554_432
    (ROOT/"processes-before.txt").write_text(subprocess.check_output(
        ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
    timings, records = {"A": [], "D": []}, []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            stem = f"component-{iteration}-{arm}"
            command = ["taskset", "-c", "8", frozen["binary"]["path"], *frozen["arguments"], arm, "64"]
            result = execution.measured(command, stem)
            metrics = read(ROOT/(stem+".stdout"))
            assert metrics["all_equal"] and metrics["arm"] == arm
            assert metrics["evaluations"] == EVALUATIONS
            assert metrics["dense_bytes"] == frozen["component"]["dense_bytes"]
            assert result["threads"] == 1 and result["rss_bytes"] < 512 << 20
            assert result["cpu_s"] <= 600 and result["wall_s"] <= 900
            if records:
                assert metrics["checksum"] == records[0]["metrics"]["checksum"]
            records.append(dict(iteration=iteration, arm=arm, run=result, metrics=metrics))
            if iteration:
                timings[arm].append(metrics["loop_cpu_s"]*1e9/EVALUATIONS)
            print("EXP718_RUN", iteration, arm, metrics["loop_cpu_s"]*1e9/EVALUATIONS, flush=True)
    differences = [a-d for a, d in zip(timings["A"], timings["D"])]
    mean = statistics.mean(differences)
    half = 2.570581835636314*statistics.stdev(differences)/math.sqrt(6)
    means = {a: statistics.mean(v) for a, v in timings.items()}
    gates = dict(cpu_budget=means["D"] <= 40, reduction=means["D"] <= .7*means["A"],
                 positive_interval=mean-half > 0, memory=frozen["component"]["dense_bytes"] <= 33_554_432)
    write(ROOT/"report.json", dict(all_checks_passed=True, means_ns=means, timings_ns=timings,
        paired_saved_ns=mean, paired_ci95_ns=[mean-half, mean+half], gates=gates, selected=all(gates.values()),
        runs=records, known_recipe_component_only=True, request_repetitions_per_run=64,
        new_exact_rows=0, full_estimator_runs=0, accuracy_claim=False,
        selector_parsing_models_csv_included=False, removed_bytes=0,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP718_COMPLETE", means, gates, flush=True)


def audit():
    frozen, report = read(ROOT/"freeze.json"), read(ROOT/"report.json")
    assert frozen["schedule"] == [list(s) for s in ("AD", "AD", "DA", "AD", "DA", "AD", "DA")]
    assert report["all_checks_passed"] and len(report["runs"]) == 14
    assert read(ROOT/"component-check.stdout") == frozen["component"]
    assert read(ROOT/"component-check.run.json")["exit_code"] == 0
    times, checksums = {"A": [], "D": []}, set()
    for iteration, order in enumerate(frozen["schedule"]):
        for offset, arm in enumerate(order):
            stem = f"component-{iteration}-{arm}"
            entry = report["runs"][2*iteration+offset]
            run_record, metrics = read(ROOT/(stem+".run.json")), read(ROOT/(stem+".stdout"))
            assert entry == dict(iteration=iteration, arm=arm, run=run_record, metrics=metrics)
            assert run_record["exit_code"] == 0 and run_record["threads"] == 1
            assert run_record["rss_bytes"] < 512 << 20 and run_record["cpu_s"] <= 600
            assert run_record["command"] == ["taskset", "-c", "8", frozen["binary"]["path"],
                                           *frozen["arguments"], arm, "64"]
            assert metrics["all_equal"] and metrics["evaluations"] == 15_335_424 and metrics["arm"] == arm
            checksums.add(metrics["checksum"])
            if iteration:
                times[arm].append(metrics["loop_cpu_s"]*1e9/15_335_424)
    assert len(checksums) == 1 and times == report["timings_ns"]
    means = {a: sum(v)/6 for a, v in times.items()}
    diff = [a-d for a, d in zip(times["A"], times["D"])]
    mean = sum(diff)/6
    half = 2.570581835636314*(sum((d-mean)**2 for d in diff)/30)**.5
    assert all(abs(means[a]-report["means_ns"][a]) < 1e-10 for a in "AD")
    assert abs(mean-report["paired_saved_ns"]) < 1e-10
    assert all(abs(x-y) < 1e-10 for x, y in zip((mean-half, mean+half), report["paired_ci95_ns"]))
    gates = dict(cpu_budget=means["D"] <= 40, reduction=means["D"] <= .7*means["A"],
                 positive_interval=mean-half > 0, memory=frozen["component"]["dense_bytes"] <= 33_554_432)
    assert gates == report["gates"] and report["selected"] == all(gates.values())
    assert report["new_exact_rows"] == report["full_estimator_runs"] == 0
    result = dict(all_checks_passed=True, paired_statistics_recomputed=True,
        audited_runs=14, same_checksum=True, selected=report["selected"],
        grid_equivalence_reused=True, generic_known_recipe_component_only=True, report=identity(ROOT/"report.json"))
    write(ROOT/"independent-audit.json", result)
    print("EXP718_AUDIT", result, flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["audit"]:
        audit()
    else:
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp718")
        assert sys.argv[1:] in (["prepare"], ["run"])
        dict(prepare=prepare, run=run)[sys.argv[1]]()
