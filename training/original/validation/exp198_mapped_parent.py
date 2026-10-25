#!/usr/bin/env python3
"""Freeze, run and independently check mapped parent-tree replay."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/exp198"
RESULTS = ROOT / "validation/results"
PROTOCOL = ROOT / "experiment/实验198-C1映射前驱链真实重放精度探针.md"
CPP = ROOT / "tests/exp198_mapped_parent_paths.cpp"
FREEZE = RESULTS / "exp198-frozen.json"
RUN = RESULTS / "exp198-run.json"
REPORT = RESULTS / "exp198-mapped-parent.json"
CHECK = RESULTS / "exp198-evidence-check.json"
ARCH = ROOT / "doc/eda比赛文件/arch"
PREDICTIONS = RESULTS / "exp174-predictions.csv"
TREES = RESULTS / "exp171-source-trees.json"
MODES = ("cycle1", "cycle2", "cycle3", "cycle4", "cycle5", "cycle6", "cycle7", "xor4")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def point_of(exact, prediction):
    if exact <= 0:
        return 1.0 if prediction == exact else 0.0
    return 1.0 - math.tanh(4.0 * abs(prediction - exact) / exact)


def evaluate(rows):
    weight = math.fsum(float(row["weight"]) for row in rows)
    values = [int(row["prediction"]) for row in rows]
    return {
        "rows": len(rows),
        "accuracy_percent": 100 * math.fsum(
            float(row["weight"]) * point_of(int(row["exact"]), value)
            for row, value in zip(rows, values)) / weight,
        "weighted_exact_percent": 100 * math.fsum(
            float(row["weight"]) * (int(row["exact"]) == value)
            for row, value in zip(rows, values)) / weight,
        "changed": sum(int(row["baseline"]) != value for row, value in zip(rows, values)),
        "worsened": sum(
            point_of(int(row["exact"]), value) < point_of(int(row["exact"]), int(row["baseline"]))
            for row, value in zip(rows, values)),
        "false_finite": sum(int(row["exact"]) < 0 and value >= 0 for row, value in zip(rows, values)),
        "false_unreachable": sum(int(row["exact"]) >= 0 and value < 0 for row, value in zip(rows, values)),
    }


def self_check():
    assert point_of(100, 100) == 1.0
    assert point_of(-1, -1) == 1.0
    assert point_of(-1, 0) == 0.0
    rows = [{"exact": "100", "weight": "1", "prediction": "100", "baseline": "101"}]
    assert evaluate(rows)["accuracy_percent"] == 100.0
    assert len(set(MODES)) == 8


def verify():
    frozen = json.loads(FREEZE.read_text())
    for item in frozen["identities"]:
        assert identity(ROOT / item["path"]) == item
    assert subprocess.check_output(
        ["git", "show", f"HEAD:{FREEZE.relative_to(ROOT)}"], cwd=ROOT) == FREEZE.read_bytes()
    return frozen


def freeze():
    self_check()
    assert not any(path.exists() for path in (BUILD, FREEZE, RUN, REPORT, CHECK))
    exp190 = json.loads((RESULTS / "exp190-lane-automorphism.json").read_text())
    assert exp190["complete_maps"] == list(MODES)
    assert json.loads((RESULTS / "exp190-evidence-check.json").read_text())["all_passed"]
    trees = json.loads(TREES.read_text())["sources"]
    BUILD.mkdir()
    manifest = BUILD / "manifest.tsv"
    with manifest.open("x") as stream:
        for name, entry in trees.items():
            meta = entry["metadata"]
            stream.write(f"{name}\t{meta['index']}\t{meta['dx_min']}\t{meta['dy_min']}\t"
                         f"{meta['dx_max'] - meta['dx_min'] + 1}\t"
                         f"{meta['dy_max'] - meta['dy_min'] + 1}\t"
                         f"{(ROOT / entry['raw']['path']).resolve()}\n")
    binary = BUILD / "mapped_parent_paths"
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-I", str(ROOT / "src"), "-o", str(binary), str(CPP),
               str(ROOT / "src/architecture.cpp")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    (BUILD / "compile.stderr").write_text(result.stderr)
    assert result.returncode == 0 and not result.stderr, result.stderr
    paths = [PROTOCOL, CPP, Path(__file__), PREDICTIONS, TREES,
             RESULTS / "exp190-lane-automorphism.json",
             RESULTS / "exp190-evidence-check.json", RESULTS / "exp190-frozen.json",
             manifest, binary, *sorted(ARCH.glob("*.json"))]
    paths += [ROOT / entry["raw"]["path"] for entry in trees.values()]
    save(FREEZE, {
        "experiment": 198,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "command": command,
        "modes": list(MODES),
        "binary": identity(binary),
        "identities": [identity(path) for path in paths],
        "request_count": 6176,
        "source_count": 40,
        "scope": "real replay of mapped nominal parent paths; exact is offline audit only",
        "stop": "no timing, no production integration, no change to prior gates",
    })
    print(json.dumps(identity(FREEZE), indent=2, ensure_ascii=False))


def run():
    frozen = verify()
    assert not RUN.exists() and not REPORT.exists()
    output = BUILD / "mapped-parent.csv"
    command = [frozen["binary"]["path"], str(ARCH), str(PREDICTIONS),
               str(BUILD / "manifest.tsv"), str(output)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    (BUILD / "run.stdout").write_text(result.stdout)
    (BUILD / "run.stderr").write_text(result.stderr)
    assert result.returncode == 0 and not result.stderr, result.stderr
    save(RUN, {"experiment": 198, "freeze": identity(FREEZE), "command": command,
               "stdout": identity(BUILD / "run.stdout"), "stderr": identity(BUILD / "run.stderr"),
               "output": identity(output)})
    rows = list(csv.DictReader(output.open(newline="")))
    assert len(rows) == 6176 * 9
    by_mode = {mode: [row for row in rows if row["mode"] == mode] for mode in (*MODES, "combined")}
    scores = {mode: evaluate(by_mode[mode]) for mode in by_mode}
    baseline_rows = []
    for row in by_mode["combined"]:
        baseline_rows.append({**row, "prediction": row["baseline"]})
    scores["baseline"] = evaluate(baseline_rows)
    summary = {
        "experiment": 198,
        "freeze": identity(FREEZE),
        "run": identity(RUN),
        "output": identity(output),
        "scores": scores,
        "mode_gain_pp": {
            mode: scores[mode]["accuracy_percent"] - scores["baseline"]["accuracy_percent"]
            for mode in by_mode
        },
        "modes": list(MODES),
        "combined": {
            "oracle_gate": scores["combined"]["accuracy_percent"] -
            scores["baseline"]["accuracy_percent"] >= 0.10,
            "min_paths": min(int(row["valid_paths"]) for row in by_mode["combined"]),
            "rows_with_paths": sum(int(row["valid_paths"]) > 0 for row in by_mode["combined"]),
        },
        "limits": "fixed exp174 development set; no new requests, CPU or online selector",
    }
    save(REPORT, summary)
    print(json.dumps(summary["mode_gain_pp"], indent=2, ensure_ascii=False))


def check():
    frozen = verify()
    assert not CHECK.exists()
    report = json.loads(REPORT.read_text())
    run_record = json.loads(RUN.read_text())
    output = ROOT / run_record["output"]["path"]
    assert identity(output) == run_record["output"]
    rows = list(csv.DictReader(output.open(newline="")))
    assert len(rows) == 6176 * 9
    by_mode = {mode: [row for row in rows if row["mode"] == mode] for mode in (*MODES, "combined")}
    assert all(len(values) == 6176 for values in by_mode.values())
    labels = list(csv.DictReader(PREDICTIONS.open(newline="")))
    for mode, values in by_mode.items():
        for index, row in enumerate(values):
            label = labels[index]
            assert int(row["index"]) == index
            assert row["from"] == label["from"] and row["to"] == label["to"]
            assert int(row["exact"]) == int(label["exact"])
            assert int(row["baseline"]) == int(label["all"])
            upper = int(row["upper"])
            prediction = int(row["prediction"])
            if upper >= 0 and int(label["exact"]) >= 0:
                assert upper >= int(label["exact"])
            if int(label["exact"]) < 0:
                assert upper < 0 and prediction < 0
            assert prediction == (
                min(int(label["all"]), upper) if upper >= 0 and int(label["all"]) >= 0
                else upper if upper >= 0 else int(label["all"]))
    scores = {mode: evaluate(values) for mode, values in by_mode.items()}
    baseline_rows = [{**row, "prediction": row["baseline"]} for row in by_mode["combined"]]
    scores["baseline"] = evaluate(baseline_rows)
    assert report["scores"] == scores
    assert report["mode_gain_pp"]["combined"] >= report["mode_gain_pp"]["cycle1"] - 1e-12
    save(CHECK, {"experiment": 198, "all_passed": True, "freeze": identity(FREEZE),
                 "report": identity(REPORT), "output": identity(output),
                 "rows": len(rows), "scores": scores,
                 "limits": report["limits"]})
    print(json.dumps({"all_passed": True, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("self-check", "freeze", "run", "check"))
    args = parser.parse_args()
    self_check()
    {"freeze": freeze, "run": run, "check": check}.get(args.stage, lambda: print("self-check passed"))()
