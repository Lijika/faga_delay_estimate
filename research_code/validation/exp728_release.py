#!/usr/bin/env python3
"""Publish the equivalent coordinate-mask evaluator and validate its complete billion rows."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp728"), Path("build/exp728")
PLAN = Path("experiment/实验728-坐标掩码阶段接入与完整1B.md")
BASE = Path("../exp727")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
execution.ROOT = ROOT


def context():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp728")
    audit = read(BASE/"validation/results/exp727/independent-audit.json")
    assert audit["all_checks_passed"] and audit["selected"]
    check(BASE/"validation/results/exp727/100m-report.json", audit["report"])
    check(BASE/"validation/results/exp727/freeze.json", audit["freeze"])
    frozen = read(BASE/"validation/results/exp727/freeze.json")
    candidate = BASE/frozen["binaries"]["C"]["path"]
    check(candidate, frozen["binaries"]["C"])
    return audit, frozen, candidate


def clean():
    audit, frozen, candidate = context()
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    write(ROOT/"clean-freeze.json", dict(
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md")],
        candidate=identity(candidate), audit=audit, disk_free_start_bytes=shutil.disk_usage(".").free))
    assert candidate.stat().st_size < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(candidate)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(candidate)], text=True)
    empty = BUILD/"empty"
    empty.mkdir()
    shutil.copy2(candidate, empty/"estimate")
    assert [p.name for p in empty.iterdir()] == ["estimate"]
    request = Path(frozen["input"]["path"])
    check(request, frozen["input"])
    retained = check(frozen["reference"]["path"], frozen["reference"])
    output = BUILD/"empty-100m.csv"
    command = ["/usr/bin/env", "-i", "/bin/sh", "-c",
        'cd "$1" && exec ./estimate -in "$2" -out "$3"', "--",
        str(empty.resolve()), str(request.resolve()), str(output.resolve())]
    run = execution.measured(command, "empty-100m")
    assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
    assert run["cpu_s"] < 100 and run["wall_s"] <= 3600
    assert read(ROOT/"empty-100m.stderr") == dict(rows=100_000_000, unreachable=0, query_allocations=0)
    actual = check(output, retained)
    write(ROOT/"package-check.json", dict(all_passed=True, binary=identity(candidate),
        empty_directory=True, empty_environment=True, static_linked=True, rows=100_000_000,
        run=run, output=actual, contract_reused=frozen["contract_reused"], exact_sample_rows=1_916_928))
    write(ROOT/"clean-cleanup.json", dict(file=actual, retained=retained, rebuild_command=command))
    print("EXP728_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
    output.unlink()
    print("EXP728_CLEAN_PASSED", run["cpu_s"], flush=True)


def billion():
    _, frozen, candidate = context()
    assert read(ROOT/"package-check.json")["all_passed"]
    assert read(ROOT/"stage-publication.json")["bin_sha256"] == frozen["binaries"]["C"]["sha256"]
    for item in read(ROOT/"clean-freeze.json")["files"]:
        check(item["path"], item)
    previous_root = Path("../exp722")
    previous = read(previous_root/"validation/results/exp722/1b-report.json")
    decision = read(previous_root/"validation/results/exp722/1b-decision.json")
    cpu_report = Path("../exp725/validation/results/exp725/1b-report.json")
    cpu_baseline = read(cpu_report)
    assert read(cpu_report.parent/"independent-audit.json")["all_checks_passed"]
    assert cpu_baseline["input"] == previous["input"]
    assert cpu_baseline["output"]["sha256"] == previous["output"]["sha256"]
    assert read(previous_root/"validation/results/exp722/close-audit.json")["all_checks_passed"]
    assert decision["quality_gate"] and previous["unique_rows"] == 1_000_000_000
    check(previous_root/"validation/results/exp722/1b-report.json", decision["report"])
    check(previous_root/"validation/results/exp722/score-1b/accuracy.json", decision["score"])
    retained = read(previous_root/"validation/results/exp722/exp722-1b-retained.json")
    assert retained["full_roundtrip_passed"] and retained["original"] == previous["output"]
    archive = previous_root/retained["archive"]["path"]
    check(archive, retained["archive"])
    request = Path(previous["input"]["path"])
    check(request, previous["input"])
    assert shutil.disk_usage(".").free > 42_000_000_000
    output = BUILD/"1b.csv"
    assert not output.exists()
    write(ROOT/"1b-freeze.json", dict(binary=identity(candidate), input=previous["input"],
        expected_output=previous["output"], retained=retained, cpu=8,
        previous_report=identity(previous_root/"validation/results/exp722/1b-report.json"),
        previous_score=identity(previous_root/"validation/results/exp722/score-1b/accuracy.json"),
        previous_cpu_report=identity(cpu_report),
        disk_free_start_bytes=shutil.disk_usage(".").free,
        process_snapshot=subprocess.check_output(["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True)))
    before, archive_before = request.stat(), archive.stat()
    command = ["taskset", "-c", "8", str(candidate), "-in", str(request), "-out", str(output)]
    run = execution.measured(command, "1b")
    after, archive_after = request.stat(), archive.stat()
    for a, b in ((before, after), (archive_before, archive_after)):
        assert (a.st_ino, a.st_size, a.st_mtime_ns) == (b.st_ino, b.st_size, b.st_mtime_ns)
    assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
    assert run["cpu_s"] <= 3600 and run["wall_s"] <= 3600
    assert read(ROOT/"1b.stderr") == dict(rows=1_000_000_000, unreachable=0, query_allocations=0)
    actual = check(output, previous["output"])
    write(ROOT/"1b-report.json", dict(all_checks_passed=True, binary=identity(candidate),
        input=previous["input"], output=actual, run=run, rows=1_000_000_000,
        unique_rows=1_000_000_000, port_pairs=59904, exact_sample_rows=3_833_856,
        complete_output_identical=True, contract_reused=previous["contract"], score_reused=decision["score"],
        accuracy=decision["accuracy"], accuracy_delta_pp=0, new_exact_rows=0,
        baseline_run=cpu_baseline["run"], baseline_cpu_historical=True, one_candidate_run=True,
        historical_cpu_saved_s=cpu_baseline["run"]["cpu_s"]-run["cpu_s"],
        cpu_200s_goal=run["cpu_s"] < 200, cpu_100s_goal=run["cpu_s"] <= 100,
        final_accuracy_above_99_verified=False, platform_verified=False))
    write(ROOT/"1b-cleanup.json", dict(file=actual, retained=retained, archive=identity(archive),
        complete_roundtrip_evidence_reused=True, rebuild_command=command,
        restore_shell="bash", restore_command=f"paste -d, {request} <(zstd -dq -c {archive}) > {output}"))
    print("EXP728_REMOVE_DUPLICATE", output, actual["bytes"], actual["sha256"], flush=True)
    output.unlink()
    write(ROOT/"retention-complete.json", dict(all_checks_passed=True, deleted=str(output),
        released_bytes=actual["bytes"], disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP728_1B_COMPLETE", run["cpu_s"], decision["accuracy"]["point_pp"], flush=True)


def publish(mode, label):
    assert Path.cwd() == Path("/home/lhjysyx/EDA2026") and mode in ("stage", "billion")
    assert label.startswith("exp728-coordinate-masks-generic-") and "/" not in label and ".." not in label
    archive = Path("subm/versions")/label
    assert not archive.exists(), "immutable version exists"
    audit = read("validation/results/exp727/independent-audit.json")
    checked = read(ROOT/"package-check.json")
    assert audit["all_checks_passed"] and audit["selected"] and checked["all_passed"]
    binary = Path("build/exp727/estimate")
    program = check(binary, checked["binary"])
    assert program["bytes"] < 100_000_000 and binary.stat().st_mode & 0o777 == 0o755
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    expected = read("validation/results/exp725/package.json" if mode == "stage" else ROOT/"stage-publication.json")
    assert identity("estimate")["sha256"] == expected["bin_sha256"]
    evidence = [Path("validation/results/exp727")/n for n in
                ("freeze.json", "100m-report.json", "independent-audit.json")]
    evidence += [ROOT/n for n in ("protocol-original.md", "clean-freeze.json", "package-check.json")]
    extra = {}
    if mode == "billion":
        report = read(ROOT/"1b-report.json")
        assert report["all_checks_passed"] and report["complete_output_identical"]
        assert read(ROOT/"independent-audit.json")["all_checks_passed"]
        assert report["binary"]["sha256"] == program["sha256"]
        evidence += [ROOT/n for n in ("1b-freeze.json", "1b-report.json", "independent-audit.json")]
        extra = dict(cpu_1b_s=report["run"]["cpu_s"], accuracy_1b=report["accuracy"],
                     exact_sample_rows=report["exact_sample_rows"], one_1b_candidate_run=True)
    manifest = dict(version_label=label, algorithm_version="D64-curves-T2D6-V8-compiled-M-fused-csv-coordinate-masks-SSE2",
        publication_status="stage_release", complete_1b_measured=mode == "billion",
        final_accuracy_goal_verified=False, final_accuracy_required_pp=99, platform_score_verified=False,
        other_cpu_performance_verified=False, full_1b_exact_accuracy_verified=False,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_working_tree_dirty=True, bin_sha256=program["sha256"], bin_bytes=program["bytes"],
        packaged_utc=datetime.now(timezone.utc).isoformat(), generic_entry=True, selected_kernel="SSE2",
        optional_isa_not_required=True, link_mode="static; all architecture and model assets embedded",
        paired_100m=audit, previous_entry=identity("estimate"),
        previous_package=read("subm/latest/identity.json")["version_label"],
        build_directory="r9r4900:~/lhjwork/eda2026/research/exp727",
        build_driver="validation/exp727_coordinate_masks.py build",
        compile_and_link_commands=read("validation/results/exp727/freeze.json")["commands"],
        package_command=f"python3 validation/exp728_release.py publish-{mode} {label}",
        evidence=[identity(p) for p in evidence], **extra)
    archive.mkdir()
    shutil.copy2(binary, archive/"bin-estimate")
    with zipfile.ZipFile(archive/"submission.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(binary, "bin/estimate")
    with zipfile.ZipFile(archive/"submission.zip") as z:
        assert z.namelist() == ["bin/estimate"] and z.testzip() is None
        assert (z.getinfo("bin/estimate").external_attr >> 16) & 0o777 == 0o755
        assert hashlib.sha256(z.read("bin/estimate")).hexdigest() == program["sha256"]
    container = identity(archive/"submission.zip")
    manifest.update(zip_sha256=container["sha256"], zip_bytes=container["bytes"])
    write(archive/"version.json", manifest)
    (archive/"identities.txt").write_text(f"{program['sha256']}  bin-estimate\n{container['sha256']}  submission.zip\n")
    for p in evidence:
        shutil.copy2(p, archive/(p.parent.name+"-"+p.name))
    with tempfile.TemporaryDirectory(dir="build/exp727", prefix="publish-") as tmp:
        temporary = Path(tmp)
        for name, original in (("submission.zip", "submission.zip"), ("estimate-bin", "bin-estimate"),
                               ("estimate", "bin-estimate")):
            shutil.copy2(archive/original, temporary/name)
        write(temporary/"identity.json", dict(manifest, immutable_source=str(archive)))
        os.replace(temporary/"estimate", "estimate")
        for name in ("submission.zip", "estimate-bin", "identity.json"):
            os.replace(temporary/name, Path("subm/latest")/name)
    with Path("subm/versions/INDEX.txt").open("a") as out:
        out.write(f"{label}  bin={program['sha256']}  zip={container['sha256']}\n")
    shutil.copy2(archive/"submission.zip", "subm/submission.zip")
    assert identity("estimate")["sha256"] == identity("subm/latest/estimate-bin")["sha256"] == program["sha256"]
    assert identity("subm/submission.zip")["sha256"] == identity("subm/latest/submission.zip")["sha256"] == container["sha256"]
    write(ROOT/("stage-publication.json" if mode == "stage" else "package.json"), manifest)
    print("EXP728_PUBLISHED", label, program["sha256"], flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("publish-stage", "publish-billion"):
        publish(sys.argv[1].split("-")[1], sys.argv[2])
    else:
        assert sys.argv[1:] in (["clean"], ["1b"])
        dict(clean=clean, **{"1b": billion})[sys.argv[1]]()
