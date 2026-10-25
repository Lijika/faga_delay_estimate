#!/usr/bin/env python3
"""Apply the exp704 parser delta to an isolated, verified exp688 build."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXPECTED = "8c5dec652cdcffae774c96b60e49c848a436622ac64a906caf0afc6068d4ecc1"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: build.py NEW_WORK_DIRECTORY")
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = work / "source"
    shutil.copytree(HERE.parent / "source", source, ignore=shutil.ignore_patterns("build", "__pycache__"))
    subprocess.run([sys.executable, "build.py"], cwd=source, check=True)
    baseline = json.loads((source / "build/build-report.json").read_text())
    identity = json.loads((HERE / "parser-identities.json").read_text())
    parser = source / "include/exp601_port_parser.h"
    assert sha256(parser) == identity["original"]["sha256"]
    shutil.copyfile(parser, source / "include/original_parser.h")
    shutil.copyfile(HERE / "exp601_port_parser.h", parser)
    assert sha256(parser) == identity["current"]["sha256"]
    commands = [next(c for c in baseline["commands"] if "src/worker.cpp" in c),
                baseline["commands"][-1]]
    for command in commands:
        subprocess.run(command, cwd=source, check=True)
    binary = source / "build/estimate"
    actual = sha256(binary)
    assert actual == EXPECTED, (actual, EXPECTED)
    test = source / "build/parser-test"
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
               "-march=x86-64", "-mtune=generic", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
               "-I", "src", "-I", "include", str(HERE / "exp704_port_decoder.cpp"),
               "build/architecture-resolver.o", "build/arch-text.o", "-o", str(test)]
    subprocess.run(command, cwd=source, check=True)
    checks = json.loads(subprocess.check_output([str(test), "arch"], cwd=source, text=True))
    assert checks == dict(checks=829072, ports=496, all_equal=True)
    headers = subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    dynamic = subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    assert "INTERP" not in headers and "(NEEDED)" not in dynamic
    assert binary.stat().st_size == 93380632
    report = dict(binary_sha256=actual, binary_bytes=binary.stat().st_size,
                  matches_exp704_and_exp706=True, static_linked=True, parser_check=checks,
                  compiler=baseline["compiler"], commands=commands + [command],
                  full_estimator_runs=0, full_1b_verified=False)
    (work / "stage-build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
