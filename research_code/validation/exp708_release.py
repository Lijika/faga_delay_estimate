#!/usr/bin/env python3
"""Qualify and publish the selected exp707 worker, then measure a full 1B pair."""
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import zipfile

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp708"), Path("build/exp708")
PLAN = Path("experiment/实验708-准备编译阶段接入与完整1B.md")


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    return actual


def audit():
    base = Path("validation/results/exp707")
    frozen, report = read(base / "freeze.json"), read(base / "100m-report.json")
    schedule = [["A", "M", "C"], *[list(p) for p in itertools.permutations(("A", "M", "C"))]]
    assert frozen["schedule"] == schedule and len(report["runs"]) == 21
    times = {a: [] for a in ("A", "M", "C")}
    for index, record in enumerate(report["runs"]):
        iteration, slot = divmod(index, 3)
        arm = schedule[iteration][slot]
        assert record["iteration"] == iteration and record["arm"] == arm
        raw = read(base / f"100m-{iteration}-{arm}.run.json")
        assert record["run"] == raw and raw["exit_code"] == 0 and raw["threads"] == 1
        assert raw["command"][:4] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"]]
        assert raw["command"][4:6] == ["-in", frozen["input"]["path"]]
        assert raw["rss_bytes"] <= 2_000_000_000 and raw["cpu_s"] < 100 and raw["wall_s"] <= 3600
        assert read(base / Path(raw["stderr"]).name) == dict(
            rows=100_000_000, unreachable=0, query_allocations=0)
        assert all(record["output"][k] == frozen["expected_output"][k] for k in ("bytes", "sha256"))
        if iteration:
            times[arm].append(raw["cpu_s"])
    assert times == report["timings_s"]
    eligible, stats = [], {}
    for arm in ("M", "C"):
        d = [a-c for a, c in zip(times["A"], times[arm])]
        mean = statistics.mean(d)
        half = 3.163381449748624 * statistics.stdev(d) / math.sqrt(6)
        s = report["stats"][arm]
        assert abs(s["saved_s"] - mean) < 1e-12
        assert max(abs(x-y) for x, y in zip(s["simultaneous_ci95_s"], (mean-half, mean+half))) < 1e-12
        assert s["qualifies"] == (mean-half > 0)
        if s["qualifies"]:
            eligible.append(arm)
        stats[arm] = s
    assert eligible
    selected = min(eligible, key=lambda a: statistics.mean(times[a]))
    assert selected == report["selected"]
    previous = read("validation/results/exp685/100m-report.json")["evidence"]["V8"]
    assert previous["contract"]["contract_passed"]
    assert previous["output"]["sha256"] == frozen["expected_output"]["sha256"]
    ROOT.mkdir(parents=True, exist_ok=True)
    write(ROOT / "audit.json", dict(all_passed=True, selected=selected, stats=stats,
        mean_cpu_s={a: statistics.mean(t) for a, t in times.items()},
        report=identity(base / "100m-report.json"), freeze=identity(base / "freeze.json"),
        binaries=dict(A=frozen["binaries"]["A"], C=frozen["binaries"][selected]),
        contract=previous["contract"], exact_sample_rows=1_916_928))
    print("EXP708_AUDIT_PASSED", selected, stats[selected], flush=True)


def context():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp708")
    sys.path.insert(0, str(Path("../exp580/validation").resolve()))
    import exp580_complete_speed as speed
    speed.ROOT = ROOT
    audited = read(ROOT / "audit.json")
    assert audited["all_passed"]
    check("../exp707/validation/results/exp707/100m-report.json", audited["report"])
    frozen = read("../exp707/validation/results/exp707/freeze.json")
    selected = audited["selected"]
    binaries = dict(A=Path("../exp704/build/exp704/C"), C=Path("../exp707") / frozen["binaries"][selected]["path"])
    for arm, p in binaries.items():
        check(p, audited["binaries"][arm])
    return speed, audited, frozen, binaries


def clean():
    speed, audited, frozen, binaries = context()
    assert not BUILD.exists()
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    write(ROOT / "clean-freeze.json", dict(files=[identity(p) for p in
        (Path(__file__), PLAN, ROOT / "protocol-original.md")],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    directory = BUILD / "empty"
    directory.mkdir()
    program = directory / "estimate"
    shutil.copy2(binaries["C"], program)
    check(program, audited["binaries"]["C"])
    assert audited["binaries"]["C"]["bytes"] < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(program)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(program)], text=True)
    assert [p.name for p in directory.iterdir()] == ["estimate"]
    check(frozen["input"]["path"], frozen["input"])
    output = BUILD / "empty-100m.csv"
    command = ["/usr/bin/env", "-i", "/bin/sh", "-c",
        'cd "$1" && exec ./estimate -in "$2" -out "$3"', "--",
        str(directory.resolve()), frozen["input"]["path"], str(output.resolve())]
    run = speed.measured(command, "empty-100m")
    assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000 and run["wall_s"] <= 3600
    assert read(run["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
    actual = check(output, frozen["expected_output"])
    reference = check("../exp703/build/exp703/warmup.csv", frozen["expected_output"])
    write(ROOT / "package-check.json", dict(all_passed=True, binary=identity(program),
        empty_directory=True, empty_environment=True, static_linked=True, run=run,
        rows=100_000_000, output=actual, contract=audited["contract"]))
    print("EXP708_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
    output.unlink()
    write(ROOT / "clean-cleanup.json", dict(file=actual, retained=reference,
        rebuild_command=command, deleted=True))
    print("EXP708_CLEAN_PASSED", run["cpu_s"], flush=True)


def billion():
    speed, audited, frozen, binaries = context()
    assert read(ROOT / "package-check.json")["all_passed"]
    assert read(ROOT / "stage-publication.json")["bin_sha256"] == audited["binaries"]["C"]["sha256"]
    for f in read(ROOT / "clean-freeze.json")["files"]:
        check(f["path"], f)
    previous = read("../exp706/validation/results/exp706/1b-report.json")
    assert previous["all_checks_passed"] and previous["rows"] == 1_000_000_000
    expected = previous["runs"]["C"]["output"]
    archive = read("../exp706/validation/results/exp706/archive-exp688-verification.json")
    assert archive["all_checks_passed"]
    assert all(expected[k] == archive["uncompressed"][k] for k in ("bytes", "sha256"))
    request = Path("../../build/hidden-suite-v1/role-1b/requests.csv")
    check(request, previous["input"])
    write(ROOT / "1b-freeze.json", dict(binaries={a: identity(p) for a, p in binaries.items()},
        input=previous["input"], expected_output=expected, schedule=["A", "C"], cpu=8,
        previous=identity("../exp706/validation/results/exp706/1b-report.json"),
        retained=archive, disk_free_start_bytes=shutil.disk_usage(".").free))
    (ROOT / "processes-before.txt").write_text(subprocess.check_output(
        ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
    runs = {}
    for arm in ("A", "C"):
        assert shutil.disk_usage(".").free > 42_000_000_000
        output = BUILD / f"1b-{arm}.csv"
        assert not output.exists()
        command = ["taskset", "-c", "8", str(binaries[arm]), "-in", str(request), "-out", str(output)]
        before = request.stat()
        run = speed.measured(command, "1b-" + arm)
        after = request.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
        assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000 and run["wall_s"] <= 3600
        assert read(run["stderr"]) == dict(rows=1_000_000_000, unreachable=0, query_allocations=0)
        actual = check(output, expected)
        runs[arm] = dict(run=run, output=actual, binary=audited["binaries"][arm])
        write(ROOT / f"1b-{arm}-evidence.json", runs[arm])
        print("EXP708_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
        output.unlink()
        write(ROOT / f"1b-{arm}-cleanup.json", dict(file=actual, retained=archive,
            rebuild_command=command, deleted=True))
        print("EXP708_1B_ARM", arm, run["cpu_s"], flush=True)
    write(ROOT / "1b-report.json", dict(all_checks_passed=True, runs=runs,
        rows=1_000_000_000, unique_rows=1_000_000_000, port_pairs=59904,
        input=previous["input"], exact_sample_rows=3_833_856, accuracy=previous["accuracy"],
        accuracy_delta_pp=0, contract=previous["contract"], complete_outputs_identical=True,
        saved_s=runs["A"]["run"]["cpu_s"]-runs["C"]["run"]["cpu_s"],
        one_pair_only=True, input_previously_observed=True, new_exact_rows=0,
        cpu_100s_goal=runs["C"]["run"]["cpu_s"] <= 100,
        cpu_200s_goal=runs["C"]["run"]["cpu_s"] < 200,
        platform_verified=False, disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP708_1B_COMPLETE", runs["C"]["run"]["cpu_s"], flush=True)


def publish(mode, label):
    assert Path.cwd() == Path("/home/lhjysyx/EDA2026")
    assert mode in ("stage", "billion")
    assert label.startswith("exp708-compiled-prepare-") and "/" not in label and ".." not in label
    archive = Path("subm/versions") / label
    assert not archive.exists(), "immutable version exists"
    audited, checked = read(ROOT / "audit.json"), read(ROOT / "package-check.json")
    assert audited["all_passed"] and checked["all_passed"] and checked["static_linked"]
    binary = Path("build/exp707") / audited["selected"] / "estimate"
    program = check(binary, audited["binaries"]["C"])
    assert all(program[k] == checked["binary"][k] for k in ("bytes", "sha256"))
    assert program["bytes"] < 100_000_000 and binary.stat().st_mode & 0o777 == 0o755
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    evidence = [ROOT / n for n in ("audit.json", "package-check.json", "clean-freeze.json", "protocol-original.md")]
    evidence += [Path("validation/results/exp707") / n for n in ("freeze.json", "100m-report.json")]
    complete = {}
    if mode == "billion":
        scale = read(ROOT / "1b-report.json")
        assert scale["all_checks_passed"] and scale["complete_outputs_identical"]
        for arm, record in scale["runs"].items():
            assert record["run"] == read(ROOT / f"1b-{arm}.run.json")
            assert record["run"]["exit_code"] == 0 and record["run"]["threads"] == 1
        complete = dict(cpu_1b_s=scale["runs"]["C"]["run"]["cpu_s"], saved_1b_s=scale["saved_s"],
                        accuracy_1b=scale["accuracy"], one_1b_pair_only=True)
        evidence += [ROOT / n for n in ("1b-freeze.json", "1b-report.json", "1b-A.run.json", "1b-C.run.json")]
    manifest = dict(version_label=label, algorithm_version="D64-curves-S8-V8-compiled-prepare-" + audited["selected"],
        publication_status="stage_release", complete_1b_measured=mode == "billion",
        final_accuracy_goal_verified=False, final_accuracy_required_pp=99, platform_score_verified=False,
        full_1b_exact_accuracy_verified=False, other_cpu_performance_verified=False,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_working_tree_dirty=True, bin_sha256=program["sha256"], bin_bytes=program["bytes"],
        packaged_utc=datetime.now(timezone.utc).isoformat(), generic_entry=True, selected_kernel="SSE2",
        optional_isa_not_required=True, link_mode="static; all architecture and model assets embedded",
        paired_100m=audited, previous_entry=identity("estimate"),
        previous_package=read("subm/latest/identity.json")["version_label"],
        build_directory="r9r4900:~/lhjwork/eda2026/research/exp707",
        build_driver="validation/exp707_compiled_prepare.py build",
        commands=read("validation/results/exp707/freeze.json")["commands"][audited["selected"]],
        package_command=f"python3 validation/exp708_release.py publish-{mode} {label}",
        evidence=[identity(p) for p in evidence], **complete)
    archive.mkdir()
    shutil.copy2(binary, archive / "bin-estimate")
    with zipfile.ZipFile(archive / "submission.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(binary, "bin/estimate")
    with zipfile.ZipFile(archive / "submission.zip") as z:
        assert z.namelist() == ["bin/estimate"] and z.testzip() is None
        assert (z.getinfo("bin/estimate").external_attr >> 16) & 0o777 == 0o755
        assert hashlib.sha256(z.read("bin/estimate")).hexdigest() == program["sha256"]
    container = identity(archive / "submission.zip")
    manifest.update(zip_sha256=container["sha256"], zip_bytes=container["bytes"])
    write(archive / "version.json", manifest)
    (archive / "identities.txt").write_text(f"{program['sha256']}  bin-estimate\n{container['sha256']}  submission.zip\n")
    for p in evidence:
        shutil.copy2(p, archive / (p.parent.name + "-" + p.name))
    with tempfile.TemporaryDirectory(dir="build/exp707", prefix="publish-") as tmp:
        staging = Path(tmp)
        for name, source in (("submission.zip", "submission.zip"), ("estimate-bin", "bin-estimate"),
                             ("estimate", "bin-estimate")):
            shutil.copy2(archive / source, staging / name)
        write(staging / "identity.json", dict(manifest, immutable_source=str(archive)))
        os.replace(staging / "estimate", "estimate")
        for name in ("submission.zip", "estimate-bin", "identity.json"):
            os.replace(staging / name, Path("subm/latest") / name)
    with Path("subm/versions/INDEX.txt").open("a") as f:
        f.write(f"{label}  bin={program['sha256']}  zip={container['sha256']}\n")
    shutil.copy2(archive / "submission.zip", "subm/submission.zip")
    assert identity("estimate")["sha256"] == identity("subm/latest/estimate-bin")["sha256"] == program["sha256"]
    assert identity("subm/submission.zip")["sha256"] == identity("subm/latest/submission.zip")["sha256"] == container["sha256"]
    write(ROOT / ("stage-publication.json" if mode == "stage" else "package.json"), manifest)
    print("EXP708_PUBLISHED", label, program["sha256"], flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("publish-stage", "publish-billion"):
        publish(sys.argv[1].split("-")[1], sys.argv[2])
    else:
        assert len(sys.argv) == 2 and sys.argv[1] in ("audit", "clean", "billion")
        dict(audit=audit, clean=clean, billion=billion)[sys.argv[1]]()
