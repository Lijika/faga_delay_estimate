#!/usr/bin/env python3
"""Build the frozen request tools and restore their verified reachability indexes."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare.py NEW_WORK_DIRECTORY")
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((HERE / "generator/toolchain-original.json").read_text())
    for name, expected in frozen["files"].items():
        if "/" in name:
            assert hashlib.sha256((HERE / "generator" / name).read_bytes()).hexdigest() == expected
    for item in json.loads((HERE / "data/manifest.json").read_text()):
        packed = HERE.parent / item["published"]
        raw = gzip.decompress(packed.read_bytes())
        assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
        (work / packed.stem).write_bytes(raw)
    source = HERE / "generator"
    flags = ["-O3", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    subprocess.run(["g++", *flags, "-c", str(source / "src/architecture.cpp"),
                    "-o", str(work / "architecture.o")], check=True)
    for tool in ("make_hidden_suite", "check_hidden_suite", "hidden_reach"):
        subprocess.run(["g++", *flags, str(source / "scripts" / (tool + ".cpp")),
                        str(work / "architecture.o"), "-o", str(work / tool)], check=True)
        help_run = subprocess.run([str(work / tool), "--help"], capture_output=True, text=True)
        assert "usage:" in help_run.stdout + help_run.stderr
    sampler = HERE.parent / "training/original/validation/exp683_stratified_sample.cpp"
    subprocess.run(["g++", *flags, str(sampler), "-o", str(work / "stratified-sample")], check=True)
    report = dict(generator_source_commit="26f0b04", source_hashes_passed=True,
                  reachability_indexes_verified=True, tools_compiled=True,
                  complete_request_populations_generated=0, complete_estimator_runs=0)
    (work / "prepare-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
