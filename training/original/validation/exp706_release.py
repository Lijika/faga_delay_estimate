#!/usr/bin/env python3
"""Qualify the direct decoder and compare complete billion-row executions."""
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import statistics
import subprocess
import sys

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp706"), Path("build/exp706")
PLAN = Path("experiment/实验706-直接端口目录阶段接入与完整1B.md")
BASE = Path("../exp704")
BINS = dict(A=Path("../exp686/build/exp686/N"), C=BASE / "build/exp704/C")


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    got = identity(path)
    assert all(got[k] == expected[k] for k in ("bytes", "sha256")), str(path)
    return got


def audit():
    base = Path("validation/results/exp704")
    frozen, report = read(base / "freeze.json"), read(base / "100m-report.json")
    schedule = [["A", "C"], ["A", "C"], ["C", "A"], ["A", "C"],
                ["C", "A"], ["A", "C"], ["C", "A"]]
    assert frozen["schedule"] == schedule and len(report["runs"]) == 14
    timing = dict(A=[], C=[])
    for index, record in enumerate(report["runs"]):
        iteration, slot = divmod(index, 2)
        arm = schedule[iteration][slot]
        assert record["iteration"] == iteration and record["arm"] == arm
        run = record["run"]
        raw = read(base / f"100m-{iteration}-{arm}.run.json")
        assert run == raw
        assert run["command"][:4] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"]]
        assert run["command"][4:6] == ["-in", frozen["input"]["path"]]
        assert run["exit_code"] == 0 and run["threads"] == 1
        assert run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] < 100 and run["wall_s"] <= 3600
        assert read(base / Path(run["stderr"]).name) == dict(
            rows=100_000_000, unreachable=0, query_allocations=0)
        assert all(record["output"][k] == frozen["expected_output"][k] for k in ("bytes", "sha256"))
        if iteration:
            timing[arm].append(run["cpu_s"])
    saved = [a-c for a, c in zip(timing["A"], timing["C"])]
    mean = statistics.mean(saved)
    half = 2.570581835636314 * statistics.stdev(saved) / math.sqrt(6)
    assert timing == report["timings_s"] and abs(mean - report["saved_s"]) < 1e-12
    assert max(abs(x-y) for x, y in zip((mean-half, mean+half), report["ci95_saved_s"])) < 1e-12
    assert report["qualifies"] == (mean > 0 and mean-half > 0)
    assert report["qualifies"] and report["same_output_all_runs"]
    check("validation/exp704_direct_port.py", frozen["files"][0])
    previous = read("validation/results/exp685/100m-report.json")["evidence"]["V8"]
    assert all(previous["output"][k] == frozen["expected_output"][k] for k in ("bytes", "sha256"))
    assert previous["contract"]["contract_passed"] and previous["contract"]["sample_rows"] == 1_916_928
    write(ROOT / "audit.json", dict(all_checks_passed=True, qualifies=True,
        complete_100m_runs=14, outputs_per_arm=7, saved_s=mean, ci95_saved_s=[mean-half, mean+half],
        mean_cpu_s={a: statistics.mean(v) for a, v in timing.items()},
        report=identity(base / "100m-report.json"), freeze=identity(base / "freeze.json"),
        contract=previous["contract"], exact_sample_rows=1_916_928,
        accuracy=identity("validation/results/exp685/score/accuracy.json")))
    print("EXP706_AUDIT_PASSED", mean, [mean-half, mean+half], flush=True)


def context():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp706")
    sys.path.insert(0, str(Path("../exp580/validation").resolve()))
    import exp580_complete_speed as speed
    speed.ROOT = ROOT
    audit_result = read(ROOT / "audit.json")
    assert audit_result["all_checks_passed"] and audit_result["qualifies"]
    check(BASE / "validation/results/exp704/100m-report.json", audit_result["report"])
    frozen = read(BASE / "validation/results/exp704/freeze.json")
    for arm, path in BINS.items():
        check(path, frozen["binaries"][arm])
    return speed, frozen


def clean():
    speed, frozen = context()
    assert not BUILD.exists()
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    write(ROOT / "clean-freeze.json", dict(binary=frozen["binaries"]["C"],
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md")],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    assert frozen["binaries"]["C"]["bytes"] < 100_000_000
    linked = subprocess.run(["ldd", str(BINS["C"])], capture_output=True, text=True)
    assert "not a dynamic executable" in linked.stdout + linked.stderr
    assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(BINS["C"])], text=True)
    directory = BUILD / "empty-check"
    directory.mkdir()
    program = directory / "estimate"
    shutil.copy2(BINS["C"], program)
    assert [p.name for p in directory.iterdir()] == ["estimate"]
    check(program, frozen["binaries"]["C"])
    request = check(frozen["input"]["path"], frozen["input"])
    reference = Path("../exp703/build/exp703/warmup.csv")
    check(reference, frozen["expected_output"])
    output = BUILD / "empty-100m.csv"
    command = ["/usr/bin/env", "-i", "/bin/sh", "-c",
        'cd "$1" && exec ./estimate -in "$2" -out "$3"', "--",
        str(directory.resolve()), request["path"], str(output.resolve())]
    run = speed.measured(command, "empty-100m")
    assert run["exit_code"] == 0 and run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
    assert run["cpu_s"] < 100 and run["wall_s"] <= 3600
    assert read(run["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
    actual = check(output, frozen["expected_output"])
    write(ROOT / "package-check.json", dict(all_passed=True, binary=identity(program),
        empty_directory=True, empty_environment=True, static_linked=True, rows=100_000_000,
        unique_rows=100_000_000, port_pairs=59904, run=run, output=actual,
        contract=read(ROOT / "audit.json")["contract"]))
    write(ROOT / "clean-duplicate.json", dict(file=actual, identical_to=identity(reference),
        rebuild_command=command, released_bytes=actual["bytes"]))
    output.unlink()
    print("EXP706_CLEAN_PASSED", run["cpu_s"], flush=True)


def billion():
    speed, frozen = context()
    assert read(ROOT / "package-check.json")["all_passed"]
    publication = read(ROOT / "stage-publication.json")
    assert publication["bin_sha256"] == frozen["binaries"]["C"]["sha256"]
    for item in read(ROOT / "clean-freeze.json")["files"]:
        check(item["path"], item)
    previous = read("../exp688/validation/results/exp688/1b-report.json")
    assert previous["rows"] == previous["unique_rows"] == 1_000_000_000
    assert previous["port_pairs"] == 59904 and previous["contract"]["contract_passed"]
    archive = read(ROOT / "archive-exp688-verification.json")
    assert archive["all_checks_passed"] and archive["uncompressed"] == previous["output"]
    request = Path("../../build/hidden-suite-v1/role-1b/requests.csv")
    check(request, previous["input"])
    accuracy = read("../exp688/validation/results/exp688/1b-accuracy.json")
    assert accuracy["evidence"]["C"]["source_output"] == previous["output"]
    assert previous["exact_sample_rows"] == 3_833_856
    write(ROOT / "1b-freeze.json", dict(binaries=frozen["binaries"], input=previous["input"],
        expected_output=previous["output"], schedule=["A", "C"], cpu=8,
        previous_report=identity("../exp688/validation/results/exp688/1b-report.json"),
        previous_accuracy=identity("../exp688/validation/results/exp688/1b-accuracy.json"),
        archive=identity(ROOT / "archive-exp688-verification.json"),
        stage_publication=identity(ROOT / "stage-publication.json"),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    runs = {}
    for arm in ("A", "C"):
        assert shutil.disk_usage(".").free > 42_000_000_000
        output = BUILD / f"1b-{arm}.csv"
        assert not output.exists()
        command = ["taskset", "-c", "8", str(BINS[arm]), "-in", str(request), "-out", str(output)]
        before = request.stat()
        run = speed.measured(command, "1b-" + arm)
        after = request.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_ino, after.st_size, after.st_mtime_ns)
        assert run["exit_code"] == 0 and run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
        assert run["cpu_s"] <= 3600 and run["wall_s"] <= 3600
        assert read(run["stderr"]) == dict(rows=1_000_000_000, unreachable=0, query_allocations=0)
        actual = check(output, previous["output"])
        record = dict(run=run, output=actual, binary=frozen["binaries"][arm],
            accuracy_pp=accuracy["accuracy"]["C"]["point_pp"], exact_sample_rows=3_833_856)
        runs[arm] = record
        write(ROOT / f"1b-{arm}-evidence.json", record)
        write(ROOT / f"1b-{arm}-cleanup.json", dict(file=actual, retained=archive,
            rebuild_command=command, deleted=True))
        print("EXP706_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
        output.unlink()
        print("EXP706_1B_ARM", arm, run["cpu_s"], flush=True)
    write(ROOT / "1b-report.json", dict(all_checks_passed=True, runs=runs, input=previous["input"],
        rows=1_000_000_000, unique_rows=1_000_000_000, port_pairs=59904,
        exact_sample_rows=3_833_856, accuracy=accuracy["accuracy"]["C"], accuracy_delta_pp=0,
        contract=previous["contract"], complete_outputs_identical=True,
        saved_s=runs["A"]["run"]["cpu_s"]-runs["C"]["run"]["cpu_s"],
        cpu_200s_goal=runs["C"]["run"]["cpu_s"] < 200,
        cpu_100s_goal=runs["C"]["run"]["cpu_s"] <= 100,
        one_pair_only=True, input_previously_observed=True, new_exact_rows=0,
        platform_verified=False, disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP706_1B_COMPLETE", runs["C"]["run"]["cpu_s"], flush=True)


if __name__ == "__main__":
    assert len(sys.argv) == 2
    paused = []
    try:
        if sys.argv[1] in ("clean", "billion"):
            for path in Path("/proc").iterdir():
                if not path.name.isdigit():
                    continue
                try:
                    args = (path / "cmdline").read_bytes().split(b"\0")
                    if args and args[0] == b"zstd" and b"research/exp688/build/exp688/1b.csv" in args:
                        assert (path / "cwd").resolve() == Path("/home/lhj/lhjwork/eda2026")
                        os.kill(int(path.name), signal.SIGSTOP)
                        paused.append(int(path.name))
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
            write(ROOT / (sys.argv[1] + "-archive-paused.json"), dict(pids=paused))
            (ROOT / (sys.argv[1] + "-processes.txt")).write_text(subprocess.check_output(
                ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
        dict(audit=audit, clean=clean, billion=billion)[sys.argv[1]]()
    finally:
        for pid in paused:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        if sys.argv[1] in ("clean", "billion"):
            write(ROOT / (sys.argv[1] + "-archive-resumed.json"), dict(pids=paused))
