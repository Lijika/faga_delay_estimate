#!/usr/bin/env python3
"""Reassemble the original exp203 exact label solver from frozen source files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXPECTED = "3ba200cacb1f0e93485599fe0f02ddb06e4efbdf25befc9bbcba4fad7712a8d4"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_exact.py NEW_WORK_DIRECTORY")
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    frozen = work / "build/exp158"
    shutil.copytree(HERE.parent / "path_witness/solver", frozen)
    for name in ("router.cpp", "router.h", "residue_estimator.cpp"):
        shutil.copyfile(HERE / "exact_original" / name, frozen / "src" / name)
    (work / "tests").mkdir()
    shutil.copyfile(HERE.parent / "path_witness/original/exp203_exact_labels.cpp",
                    work / "tests/exp203_exact_labels.cpp")
    (work / "build/exp203").mkdir()
    identities = json.loads((HERE / "exact_original/exp203-frozen.json").read_text())["identities"]
    verified = []
    for item in identities:
        relative = item["path"].split("/EDA2026/", 1)[-1]
        path = work / relative
        if path.is_file() and (relative.startswith("build/exp158/")
                               or relative == "tests/exp203_exact_labels.cpp"):
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], relative
            verified.append(relative)
    assert len(verified) >= 20
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-DMADV_COLLAPSE=25", "-o", "build/exp203/exact_labels",
               "tests/exp203_exact_labels.cpp", "build/exp158/src/architecture.cpp",
               "build/exp158/src/router.cpp", "build/exp158/src/residue_estimator.cpp"]
    subprocess.run(command, cwd=work, check=True)
    binary = work / "build/exp203/exact_labels"
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    report = dict(command=command, source_files_verified=verified,
                  binary_bytes=binary.stat().st_size, binary_sha256=digest,
                  matches_frozen_exp683_label_solver=digest == EXPECTED,
                  compiler=subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                  offline_tool=True)
    (work / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if digest != EXPECTED:
        raise SystemExit("Solver build differs; use the recorded GCC 11.4 toolchain for byte identity.")


if __name__ == "__main__":
    main()
