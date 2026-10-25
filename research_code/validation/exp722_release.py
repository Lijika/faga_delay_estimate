#!/usr/bin/env python3
"""Release the qualified T2D6 worker and score its complete 1B output."""
from datetime import datetime, timezone
import hashlib
import inspect
import json
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

ROOT, BUILD = Path("validation/results/exp722"), Path("build/exp722")
PLAN = Path("experiment/实验722-T2D6阶段接入与完整1B.md")
BASE = Path("../exp720")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
execution.ROOT = ROOT


def measured(command, name):
    result = execution.measured(command, name)
    result["stderr"] = str(ROOT/(name+".stderr"))
    return result


def context():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp722")
    audit = read(BASE/"validation/results/exp720/independent-audit.json")
    assert audit["all_checks_passed"] and audit["selected"]
    check(BASE/"validation/results/exp720/decision.json", audit["decision"])
    frozen = read(BASE/"validation/results/exp720/freeze.json")
    candidate = BASE/"build/exp720/estimate"
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
        candidate=identity(candidate), audit=identity(BASE/"validation/results/exp720/independent-audit.json"),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    assert candidate.stat().st_size < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(candidate)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(candidate)], text=True)
    empty = BUILD/"empty"
    empty.mkdir()
    shutil.copy2(candidate, empty/"estimate")
    assert [p.name for p in empty.iterdir()] == ["estimate"]
    prior = read(BASE/"validation/results/exp720/100m-report.json")
    reference = prior["evidence"]["C"]
    request = BASE/prior["input"]["path"]
    check(request, prior["input"])
    retained = check(BASE/reference["output"]["path"], reference["output"])
    output = BUILD/"empty-100m.csv"
    command = ["/usr/bin/env", "-i", "/bin/sh", "-c",
        'cd "$1" && exec ./estimate -in "$2" -out "$3"', "--",
        str(empty.resolve()), str(request.resolve()), str(output.resolve())]
    run = measured(command, "empty-100m")
    assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
    assert run["cpu_s"] < 100 and run["wall_s"] <= 3600
    assert read(run["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
    actual = check(output, reference["output"])
    write(ROOT/"package-check.json", dict(all_passed=True, binary=identity(candidate),
        empty_directory=True, empty_environment=True, static_linked=True, rows=100_000_000,
        run=run, output=actual, contract=reference["contract"], exact_sample_rows=1_916_928))
    deletion = dict(file=actual, identical_to=retained, rebuild_command=command)
    write(ROOT/"clean-cleanup.json", deletion)
    print("EXP722_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
    output.unlink()
    print("EXP722_CLEAN_PASSED", run["cpu_s"], flush=True)


def billion():
    _, frozen, candidate = context()
    assert read(ROOT/"package-check.json")["all_passed"]
    assert read(ROOT/"stage-publication.json")["bin_sha256"] == frozen["binaries"]["C"]["sha256"]
    for item in read(ROOT/"clean-freeze.json")["files"]:
        check(item["path"], item)
    previous = read("../exp708/validation/results/exp708/1b-report.json")
    labels = read("../exp683/validation/results/exp683/1b/report.json")
    assert previous["all_checks_passed"] and previous["unique_rows"] == 1_000_000_000
    assert previous["port_pairs"] == 59904
    assert labels["all_complete_label_checks"] and labels["span_checks"] == 12
    assert labels["rows"] == labels["unique_rows"] == 3_833_856
    request = Path("../../build/hidden-suite-v1/role-1b/requests.csv")
    check(request, previous["input"])
    checker = Path("../exp580/build/exp580/contract-check")
    check(checker, read("../exp679/validation/results/exp679/freeze.json")["checker"])
    positions = Path("../exp683/build/exp683/1b/positions.txt")
    check(positions, read("../exp683/validation/results/exp683/1b/label-freeze.json")["positions"])
    baseline_sample = read("../exp688/validation/results/exp688/1b-accuracy.json")["evidence"]["C"]
    baseline = previous["runs"]["C"]
    assert all(baseline["output"][k] == baseline_sample["source_output"][k] for k in ("bytes", "sha256"))
    check(baseline_sample["sample"]["path"], baseline_sample["sample"])
    assert shutil.disk_usage(".").free > 42_000_000_000
    output, sampled = BUILD/"1b.csv", BUILD/"1b-sample.csv"
    assert not output.exists() and not sampled.exists()
    write(ROOT/"1b-freeze.json", dict(binary=identity(candidate), input=previous["input"],
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"stage-publication.json",
            Path("../exp708/validation/results/exp708/1b-report.json"),
            Path("../exp688/validation/results/exp688/1b-accuracy.json"),
            Path("../exp683/validation/results/exp683/1b/report.json"))],
        checker=identity(checker), positions=identity(positions), baseline_sample=baseline_sample,
        baseline=baseline, cpu=8, new_exact_rows=0, disk_free_start_bytes=shutil.disk_usage(".").free,
        process_snapshot=subprocess.check_output(["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True)))
    before = request.stat()
    run = measured(["taskset", "-c", "8", str(candidate), "-in", str(request), "-out", str(output)], "1b")
    after = request.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
    assert run["cpu_s"] <= 3600 and run["wall_s"] <= 3600
    assert read(run["stderr"]) == dict(rows=1_000_000_000, unreachable=0, query_allocations=0)
    contract_run = measured([str(checker), "check", str(request), str(output), "1000000000",
                            str(positions), str(sampled)], "1b-contract")
    contract = read(ROOT/"1b-contract.stdout")
    assert contract["contract_passed"] and contract["rows"] == 1_000_000_000
    assert contract["sample_rows"] == 3_833_856
    evidence = dict(A=dict(output=baseline["output"], run=baseline["run"],
                          sample=baseline_sample["sample"], contract=baseline_sample["contract"],
                          contract_run=baseline_sample["contract_run"]),
                    C=dict(output=identity(output), run=run, sample=identity(sampled),
                           contract=contract, contract_run=contract_run))
    write(ROOT/"1b-report.json", dict(all_checks_passed=True, binary=identity(candidate), input=previous["input"],
        rows=1_000_000_000, unique_rows=1_000_000_000, port_pairs=59904,
        run=run, output=evidence["C"]["output"], sample=evidence["C"]["sample"], evidence=evidence,
        contract=contract, contract_run=contract_run, exact_sample_rows=3_833_856, new_exact_rows=0,
        input_previously_observed=True, one_candidate_run=True, baseline_cpu_historical=True,
        cpu_200s_goal=run["cpu_s"] < 200, cpu_100s_goal=run["cpu_s"] <= 100,
        platform_verified=False, disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP722_1B_COMPLETE", run["cpu_s"], flush=True)


def score():
    context()
    sys.path.insert(0, str(Path("../exp683/validation").resolve()))
    import exp683_expanded_score as scoring
    import numpy as np
    source = inspect.getsource(scoring.main)
    changes = [
        ("base = Path('validation/results/exp683')/case", "base = Path('../exp683/validation/results/exp683/1b')"),
        ("build = Path('build/exp683')/case", "build = Path('../exp683/build/exp683/1b')"),
        ("root = base/('score-'+report_path.parent.name)", f"root = Path('{ROOT/'score-1b'}')"),
    ]
    for a, b in changes:
        assert source.count(a) == 1
        source = source.replace(a, b)
    start = source.index("    complete_reports = [report_path]")
    end = source.index("    assert report['port_pairs'] == 59904", start)
    source = source[:start]+"""    complete_reports = [report_path,
        Path('../exp708/validation/results/exp708/1b-report.json'),
        Path('../exp688/validation/results/exp688/1b-accuracy.json')]
    runs = {a: dict(output=e['output'], run=e['run'], input=report['input'])
            for a,e in report['evidence'].items()}
"""+source[end:]
    assert source.count("    write(root/'accuracy.json',result)") == 1
    source = source.replace("    write(root/'accuracy.json',result)",
        "    result['V_predictions_unchanged'] = bool(np.array_equal(\n"
        "        predictions['A'][groups['event']==2], predictions['C'][groups['event']==2]))\n"
        "    write(root/'accuracy.json',result)")
    compile(source, "exp722-score.py", "exec")
    (BUILD/"score.py").write_text(source)
    report = read(ROOT/"1b-report.json")
    cached = {a: dict(source_output=e["output"], source_run=e["run"], sample=e["sample"],
                     contract=e["contract"], contract_run=e["contract_run"]) for a, e in report["evidence"].items()}
    namespace = dict(vars(scoring))
    exec(compile(source, str(BUILD/"score.py"), "exec"), namespace)
    namespace["main"]("1b", ROOT/"1b-report.json", cached)
    result = read(ROOT/"score-1b/accuracy.json")
    assert abs(result["accuracy"]["A"]["point_pp"]-98.65806165706272) < 1e-9
    delta = result["delta_accuracy"]
    minimum = min(v for k, g in result["group_delta_accuracy_pp"].items()
                  if k in ("distance", "direction", "near_axis") for v in g.values())
    gate = delta["point_pp"] >= -.03 and delta["conservative_ci975_pp"][0] >= -.05 and minimum >= -.10
    assert result["V_predictions_unchanged"]
    write(ROOT/"1b-decision.json", dict(all_checks_passed=True, quality_gate=gate,
        minimum_group_delta_pp=minimum, delta=delta, accuracy=result["accuracy"]["C"],
        score=identity(ROOT/"score-1b/accuracy.json"), report=identity(ROOT/"1b-report.json"),
        final_accuracy_above_99_verified=False, platform_verified=False))
    print("EXP722_1B_QUALITY", gate, result["accuracy"]["C"], delta, flush=True)


def publish(mode, label):
    assert Path.cwd() == Path("/home/lhjysyx/EDA2026") and mode in ("stage", "billion")
    assert label.startswith("exp722-t2d6-generic-") and "/" not in label and ".." not in label
    archive = Path("subm/versions")/label
    assert not archive.exists(), "immutable version exists"
    base = Path("validation/results/exp720")
    audit, checked = read(base/"independent-audit.json"), read(ROOT/"package-check.json")
    assert audit["all_checks_passed"] and audit["selected"] and checked["all_passed"]
    binary = Path("build/exp720/estimate")
    program = check(binary, checked["binary"])
    assert program["bytes"] < 100_000_000 and binary.stat().st_mode & 0o777 == 0o755
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    evidence = [base/n for n in ("freeze.json", "build-freeze.json", "numeric-audit.json", "100m-report.json",
                                 "independent-audit.json", "decision.json")]
    evidence += [ROOT/n for n in ("protocol-original.md", "clean-freeze.json", "package-check.json")]
    extra = {}
    if mode == "billion":
        report, decision = read(ROOT/"1b-report.json"), read(ROOT/"1b-decision.json")
        assert decision["all_checks_passed"] and decision["quality_gate"]
        check(ROOT/"1b-report.json", decision["report"])
        check(ROOT/"score-1b/accuracy.json", decision["score"])
        assert report["binary"]["sha256"] == program["sha256"]
        extra = dict(cpu_1b_s=report["run"]["cpu_s"], accuracy_1b=decision["accuracy"],
                     delta_accuracy_1b=decision["delta"], one_1b_candidate_run=True)
        evidence += [ROOT/n for n in ("1b-freeze.json", "1b-report.json", "1b-decision.json")]
        expected_entry = read(ROOT/"stage-publication.json")["bin_sha256"]
    else:
        expected_entry = read("validation/results/exp708/package.json")["bin_sha256"]
    assert identity("estimate")["sha256"] == expected_entry
    manifest = dict(version_label=label, algorithm_version="D64-curves-T2D6-V8-compiled-M-generic-SSE2",
        publication_status="stage_release", complete_1b_measured=mode == "billion",
        final_accuracy_goal_verified=False, final_accuracy_required_pp=99, platform_score_verified=False,
        other_cpu_performance_verified=False, full_1b_exact_accuracy_verified=False,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_working_tree_dirty=True, bin_sha256=program["sha256"], bin_bytes=program["bytes"],
        packaged_utc=datetime.now(timezone.utc).isoformat(), generic_entry=True, selected_kernel="SSE2",
        optional_isa_not_required=True, link_mode="static; all architecture and model assets embedded",
        paired_100m=audit, previous_entry=identity("estimate"),
        previous_package=read("subm/latest/identity.json")["version_label"],
        build_directory="r9r4900:~/lhjwork/eda2026/research/exp720",
        build_driver="validation/exp720_leaf_cli.py build",
        compile_command=read(base/"build-freeze.json")["compile_command"],
        link_command=read(base/"build-freeze.json")["link_command"],
        package_command=f"python3 validation/exp722_release.py publish-{mode} {label}",
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
    with tempfile.TemporaryDirectory(dir="build/exp720", prefix="publish-") as tmp:
        temporary = Path(tmp)
        for name, original in (("submission.zip", "submission.zip"), ("estimate-bin", "bin-estimate"),
                               ("estimate", "bin-estimate")):
            shutil.copy2(archive/original, temporary/name)
        write(temporary/"identity.json", dict(manifest, immutable_source=str(archive)))
        os.replace(temporary/"estimate", "estimate")
        for name in ("submission.zip", "estimate-bin", "identity.json"):
            os.replace(temporary/name, Path("subm/latest")/name)
    with Path("subm/versions/INDEX.txt").open("a") as f:
        f.write(f"{label}  bin={program['sha256']}  zip={container['sha256']}\n")
    shutil.copy2(archive/"submission.zip", "subm/submission.zip")
    assert identity("estimate")["sha256"] == identity("subm/latest/estimate-bin")["sha256"] == program["sha256"]
    assert identity("subm/submission.zip")["sha256"] == identity("subm/latest/submission.zip")["sha256"] == container["sha256"]
    write(ROOT/("stage-publication.json" if mode == "stage" else "package.json"), manifest)
    print("EXP722_PUBLISHED", label, program["sha256"], flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("publish-stage", "publish-billion"):
        publish(sys.argv[1].split("-")[1], sys.argv[2])
    else:
        assert sys.argv[1:] in ([s] for s in ("clean", "1b", "score"))
        dict(clean=clean, **{"1b": billion}, score=score)[sys.argv[1]]()
