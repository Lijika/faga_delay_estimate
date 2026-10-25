#!/usr/bin/env python3
"""Publish the verified direct decoder using the existing immutable layout."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from exp602_package import identity, read, write

ROOT = Path("validation/results/exp706")


def package(mode, label):
    assert Path.cwd() == Path("/home/lhjysyx/EDA2026")
    assert mode in ("stage", "billion")
    assert label.startswith("exp706-direct-port-generic-") and "/" not in label and ".." not in label
    archive = Path("subm/versions") / label
    assert not archive.exists(), "immutable version already exists"
    binary = Path("build/exp704/C")
    assert binary.stat().st_mode & 0o777 == 0o755
    program = identity(binary)
    frozen = read("validation/results/exp704/freeze.json")
    audit = read(ROOT / "audit.json")
    checked = read(ROOT / "package-check.json")
    scale = read("validation/results/exp704/100m-report.json")
    assert audit["all_checks_passed"] and audit["qualifies"] and scale["qualifies"]
    assert identity("validation/results/exp704/100m-report.json") == audit["report"]
    assert checked["all_passed"] and checked["empty_directory"] and checked["empty_environment"]
    assert checked["static_linked"] and checked["rows"] == checked["unique_rows"] == 100_000_000
    assert all(program[k] == checked["binary"][k] == frozen["binaries"]["C"][k] for k in ("bytes", "sha256"))
    assert program["bytes"] < 100_000_000
    runs = [r for r in scale["runs"] if r["arm"] == "C"]
    assert len(runs) == 7
    for run in [checked["run"], *[r["run"] for r in runs]]:
        assert run["exit_code"] == 0 and run["threads"] == 1
        assert run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] < 100 and run["wall_s"] <= 3600
    assert all(r["output"]["sha256"] == checked["output"]["sha256"] for r in runs)
    assert checked["contract"]["contract_passed"] and checked["contract"]["sample_rows"] == 1_916_928
    linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
    assert "not a dynamic executable" in linked.stdout + linked.stderr
    assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(binary)], text=True)
    evidence = [ROOT / name for name in ("audit.json", "package-check.json",
                "protocol-original.md", "clean-freeze.json")]
    evidence += [Path("validation/results/exp704") / name for name in
                 ("freeze.json", "100m-report.json", "protocol-original.md", "compile.run.json",
                  "link.run.json", "parser-test.stdout")]
    evidence += [Path("validation/results/exp685/score/accuracy.json"),
                 Path("build/exp704/exp601_port_parser.h")]
    completed = {}
    if mode == "billion":
        report = read(ROOT / "1b-report.json")
        assert report["all_checks_passed"] and report["complete_outputs_identical"]
        assert report["rows"] == report["unique_rows"] == 1_000_000_000 and report["port_pairs"] == 59904
        assert report["contract"]["contract_passed"] and report["exact_sample_rows"] == 3_833_856
        for arm, record in report["runs"].items():
            assert all(record["binary"][k] == frozen["binaries"][arm][k] for k in ("bytes", "sha256"))
            assert record["run"] == read(ROOT / f"1b-{arm}.run.json")
            assert record["run"]["exit_code"] == 0 and record["run"]["threads"] == 1
            assert record["run"]["rss_bytes"] <= 2_000_000_000 and record["run"]["wall_s"] <= 3600
        assert report["runs"]["A"]["output"]["sha256"] == report["runs"]["C"]["output"]["sha256"]
        assert abs(report["saved_s"] - (report["runs"]["A"]["run"]["cpu_s"] -
                                      report["runs"]["C"]["run"]["cpu_s"])) < 1e-12
        completed = dict(cpu_1b_s=report["runs"]["C"]["run"]["cpu_s"],
            saved_1b_s=report["saved_s"], cpu_200s_goal=report["cpu_200s_goal"],
            cpu_100s_goal=report["cpu_100s_goal"], accuracy_1b=report["accuracy"],
            delta_accuracy_1b_pp=0, one_1b_pair_only=True)
        evidence += [ROOT / name for name in ("1b-freeze.json", "1b-report.json",
            "1b-A.run.json", "1b-C.run.json", "archive-exp688-verification.json")]
        evidence += [Path("validation/results/exp688/1b-accuracy.json")]
    for path in evidence:
        assert path.is_file(), path
    manifest = dict(version_label=label, algorithm_version="D64-curves-u8-S8-V8-direct-ports-generic-SSE2",
        publication_status="stage_release", complete_1b_measured=mode == "billion",
        final_accuracy_goal_verified=False, final_accuracy_required_pp=99,
        platform_score_verified=False, other_cpu_performance_verified=False,
        full_1b_exact_accuracy_verified=False,
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_working_tree_dirty=True, bin_sha256=program["sha256"], bin_bytes=program["bytes"],
        packaged_utc=datetime.now(timezone.utc).isoformat(),
        link_mode="static; five architectures, compressed geometry and fixed models embedded",
        generic_entry=True, selected_kernel="SSE2", optional_isa_not_required=True,
        paired_100m=audit, previous_entry=identity("estimate"),
        previous_package=read("subm/latest/identity.json")["version_label"],
        commands={stage: read(f"validation/results/exp704/{stage}.run.json")["command"]
                  for stage in ("compile", "link")},
        build_directory="r9r4900:~/lhjwork/eda2026/research/exp704",
        build_driver="validation/exp704_direct_port.py build",
        package_command=f"python3 validation/exp706_package.py {mode} {label}",
        evidence=[identity(path) for path in evidence], **completed)
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
    (archive / "identities.txt").write_text(
        f"{program['sha256']}  bin-estimate\n{container['sha256']}  submission.zip\n")
    for path in evidence:
        shutil.copy2(path, archive / (path.parent.name + "-" + path.name))
    latest = Path("subm/latest")
    with tempfile.TemporaryDirectory(dir="build/exp704", prefix="publish-") as temporary:
        staging = Path(temporary)
        for name, source in (("submission.zip", "submission.zip"), ("estimate-bin", "bin-estimate"),
                             ("estimate", "bin-estimate")):
            shutil.copy2(archive / source, staging / name)
        write(staging / "identity.json", dict(manifest, immutable_source=str(archive)))
        os.replace(staging / "estimate", "estimate")
        for name in ("submission.zip", "estimate-bin", "identity.json"):
            os.replace(staging / name, latest / name)
    with Path("subm/versions/INDEX.txt").open("a") as stream:
        stream.write(f"{label}  bin={program['sha256']}  zip={container['sha256']}\n")
    shutil.copy2(archive / "submission.zip", "subm/submission.zip")
    assert identity("estimate")["sha256"] == identity(latest / "estimate-bin")["sha256"] == program["sha256"]
    assert identity("subm/submission.zip")["sha256"] == container["sha256"]
    write(ROOT / ("stage-publication.json" if mode == "stage" else "package.json"), manifest)
    print("EXP706_PUBLISHED", label, program["bytes"], container["bytes"], flush=True)


if __name__ == "__main__":
    assert len(sys.argv) == 3
    package(sys.argv[1], sys.argv[2])
