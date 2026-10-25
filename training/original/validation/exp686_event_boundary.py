#!/usr/bin/env python3
"""Isolate the frozen V8 expert and compare complete, identical 100M outputs."""
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp686"), Path("build/exp686")
PLAN = Path("experiment/实验686-低频专家函数边界与公共路径成本.md")
OLD = Path("../exp684/build/exp684/V8")
ARMS = ("A", "V", "N")
BINS = {
    "A": Path("../exp654/build/exp654/B"),
    "V": OLD / "C",
    "N": BUILD / "N",
}
speed.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    got = identity(path)
    assert all(got[k] == expected[k] for k in ("bytes", "sha256")), str(path)
    return got


def patch(text):
    old = "static inline double replacement679("
    assert text.count(old) == 1
    return text.replace(old, "static __attribute__((noinline)) double replacement679(")


def self_check():
    text = "a\nstatic inline double replacement679(int a) { return a; }\nb\n"
    assert patch(text).replace("static __attribute__((noinline))", "static inline") == text
    for bad in ("", text + text):
        try:
            patch(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError("patch accepted missing or ambiguous target")
    assert len(set(itertools.permutations(ARMS))) == 6


def build():
    self_check()
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    old = read("../exp684/validation/results/exp684/V8/build-freeze.json")
    check(BINS["V"], old["binaries"]["C"])
    frozen_files = {Path(v["path"]).name: v for v in old["files"]}
    sources = []
    for src in sorted(OLD.iterdir()):
        if src.suffix not in (".cpp", ".h"):
            continue
        if src.name not in frozen_files:
            continue
        check(src, frozen_files[src.name])
        dst = BUILD / src.name
        if src.name == "replacement679.h":
            dst.write_text(patch(src.read_text()))
        else:
            shutil.copyfile(src, dst)
        sources.append(dict(original=identity(src), current=identity(dst)))
    assert (BUILD / "replacement679.h").exists() and (BUILD / "worker.cpp").exists()
    commands = {}
    for stage in ("compile", "link"):
        command = read(f"../exp684/validation/results/exp684/V8/{stage}-C.run.json")["command"]
        command = [s.replace("build/exp684/V8", str(BUILD)) for s in command]
        if stage == "link":
            assert command[-1] == str(BUILD / "C")
            command[-1] = str(BINS["N"])
        commands[stage] = command
        speed.measured(command, stage)
        assert not (ROOT / f"{stage}.stderr").read_bytes()
    assert BINS["N"].stat().st_size < 100_000_000
    result = subprocess.run(["ldd", str(BINS["N"])], capture_output=True, text=True)
    assert "not a dynamic executable" in result.stdout + result.stderr
    assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(BINS["N"])], text=True)
    (ROOT / "objdump-help.txt").write_text(subprocess.check_output(["objdump", "--help"], text=True))
    assembly = subprocess.check_output(["objdump", "-drC", str(BUILD / "C.o")], text=True)
    (ROOT / "N-disassembly.txt").write_text(assembly)
    assert "replacement679(" in assembly
    evidence = read("../exp685/validation/results/exp685/100m-report.json")
    score = read("../exp685/validation/results/exp685/score/accuracy.json")
    assert score["comparisons"]["V8"]["quality_gate"]
    request = Path("../exp685") / evidence["input"]["path"]
    check(request, evidence["input"])
    for a, old_arm in (("A", "A"), ("V", "V8")):
        expected = read("../exp685/validation/results/exp685/freeze.json")["binaries"][old_arm]
        check(BINS[a], expected)
    write(ROOT / "freeze.json", dict(
        sources=sources, commands=commands, binaries={a: identity(p) for a, p in BINS.items()},
        input=identity(request), old_report=identity("../exp685/validation/results/exp685/100m-report.json"),
        old_score=identity("../exp685/validation/results/exp685/score/accuracy.json"),
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md")],
        schedule=[list(ARMS), *map(list, itertools.permutations(ARMS))],
        disk_free_start_bytes=shutil.disk_usage(".").free,
        new_training_runs=0, new_exact_rows=0, static_elf=True))
    print("EXP686_BUILT", identity(BINS["N"]), flush=True)


def run():
    self_check()
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"] + list(frozen["binaries"].values()) + [frozen["input"],
            frozen["old_report"], frozen["old_score"]]:
        check(item["path"], item)
    old = read(frozen["old_report"]["path"])
    score = read(frozen["old_score"]["path"])
    request = frozen["input"]["path"]
    checker = Path("../exp685").resolve() / "build/exp685/contract-check"
    if not checker.exists():
        source = read("../exp685/validation/results/exp685/A-contract.run.json")["command"][0]
        checker = (Path("../exp685") / source).resolve()
    prior_checker = read("../exp685/validation/results/exp685/freeze.json")["checker"]
    check(checker, prior_checker)
    positions = Path("../exp685/build/exp685/expanded/positions.txt")
    timing, runs, deleted, retained = {a: [] for a in ARMS}, [], [], {}
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            reference = old["evidence"]["A" if arm == "A" else "V8"]
            retained_path = Path("../exp685") / reference["output"]["path"]
            if iteration == 0:
                check(retained_path, reference["output"])
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            assert not output.exists() and shutil.disk_usage(".").free > 5_100_000_000
            command = [str(BINS[arm]), "-in", request, "-out", str(output)]
            record = speed.measured(command, output.stem)
            assert record["exit_code"] == 0 and record["threads"] == 1
            assert record["rss_bytes"] <= 2_000_000_000 and record["wall_s"] <= 3600
            assert record["cpu_s"] < 100
            counters = read(record["stderr"])
            assert counters == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            actual = check(output, reference["output"])
            record.update(arm=arm, iteration=iteration, input=frozen["input"], output=actual, counters=counters)
            write(ROOT / f"{output.stem}-evidence.json", record)
            if iteration == 0:
                sample = BUILD / f"{arm}-sample.csv"
                speed.measured([str(checker), "check", request, str(output), "100000000",
                                str(positions), str(sample)], arm + "-contract")
                contract = read(ROOT / f"{arm}-contract.stdout")
                assert contract["contract_passed"] and contract["rows"] == 100_000_000
                assert contract["sample_rows"] == 1_916_928
                check(sample, reference["sample"])
                retained[arm] = dict(run=record, contract=contract, sample=identity(sample),
                    identical_retained_output=identity(retained_path), old_scored_evidence=reference)
            else:
                timing[arm].append(record["cpu_s"])
            deletion = dict(file=actual, identical_to=dict(reference["output"], path=str(retained_path)),
                            rebuild_command=command)
            write(ROOT / f"{output.stem}-cleanup.json", deletion)
            print("EXP686_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
            output.unlink()
            deleted.append(deletion)
            runs.append(record)
            print("EXP686_TIMING", iteration, arm, record["cpu_s"], flush=True)
    from scipy import stats
    import math
    def interval(values):
        mean = statistics.mean(values)
        half = float(stats.t.ppf(.99375, 5)) * statistics.stdev(values) / math.sqrt(6)
        return dict(point_s=mean, ci9875_s=[mean-half, mean+half])
    saved = interval([a-b for a, b in zip(timing["A"], timing["N"])])
    mechanism = interval([a-b for a, b in zip(timing["V"], timing["N"])])
    estimate = score["comparisons"]["V8"]["delta_accuracy"]
    point = .8*estimate["point_pp"] + saved["point_s"]/12
    lower = .8*estimate["conservative_ci9875_pp"][0] + saved["ci9875_s"][0]/12
    write(ROOT / "100m-report.json", dict(
        rows=100_000_000, unique_rows=100_000_000, port_pairs=59904, timing=timing,
        runs=runs, evidence=retained, deleted_duplicates=deleted,
        released_bytes=sum(v["file"]["bytes"] for v in deleted),
        disk_free_end_bytes=shutil.disk_usage(".").free, saved_cpu_vs_A=saved,
        saved_cpu_vs_V=mechanism, reused_accuracy=estimate,
        score_extrapolated_1b=point, conservative_ci95_score_lower=lower,
        quality_gate=True, joint_gate=bool(point >= .005 and lower > 0),
        same_complete_run_cpu_and_accuracy=True, exact_sample_rows=1_916_928,
        new_exact_rows=0, complete_1b_runs=0, platform_verified=False))
    print("EXP686_RESULT", saved, mechanism, point, lower, flush=True)


if __name__ == "__main__":
    assert len(sys.argv) == 2
    if sys.argv[1] != "self-check":
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp686")
    {"build": build, "run": run, "self-check": self_check}[sys.argv[1]]()
