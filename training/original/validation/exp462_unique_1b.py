#!/usr/bin/env python3
"""Measure complete, distinct eight-source 1B requests and score the same output."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import time

import exp208_nominal_parent_tree as common
from exp208_nominal_parent_tree import identity, write

ROOT = Path("validation/results/exp462")
BUILD = Path("build/exp462")
ARCH = Path("doc/eda比赛文件/arch")
ROWS = 1_000_000_000
SEED = 20261018462
SAMPLE_SEED = 20261018463
MASK = (1 << 64) - 1


def mix(value):
    value = ((value ^ (value >> 30)) * 0xbf58476d1ce4e5b9) & MASK
    value = ((value ^ (value >> 27)) * 0x94d049bb133111eb) & MASK
    return value ^ (value >> 31)


def permute(value, size, seed):
    half = max(1, ((size - 1).bit_length() + 1) // 2)
    mask = (1 << half) - 1
    keys = [mix(seed ^ ((0x9e3779b97f4a7c15 * (r + 1)) & MASK)) for r in range(6)]
    while True:
        left, right = divmod(value, 1 << half)
        for key in keys:
            left, right = right, left ^ (mix(right ^ key) & mask)
        value = (left << half) | right
        if value < size:
            return value


def compile_tool(sanitizer=False):
    binary = BUILD / ("unique-stream-san" if sanitizer else "unique-stream")
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
               "tests/exp462_unique_stream.cpp", "-o", str(binary)]
    if sanitizer:
        command[2:2] = ["-g", "-fsanitize=address,undefined"]
    result = subprocess.run(command, capture_output=True, text=True)
    (ROOT / (binary.name + "-build.stderr")).write_text(result.stderr)
    assert result.returncode == 0 and not result.stderr, result.stderr
    return {"command": command, "binary": identity(binary)}


def selfcheck(builds, sources, cells, ports):
    folder = BUILD / "selfcheck"
    folder.mkdir()
    checks = []
    for build in builds:
        binary = build["binary"]["path"]
        result = subprocess.run([binary, "selfcheck"], capture_output=True, text=True, check=True)
        assert not result.stderr
        checks.append({"binary": binary, "small_domains": json.loads(result.stdout)})
    binary = builds[0]["binary"]["path"]
    for seed in (0, SEED, MASK):
        inp, warm = folder / f"requests-{seed}.csv", folder / f"warm-{seed}.csv"
        result = subprocess.run([binary, "generate", BUILD / "sources.txt", BUILD / "cells.txt",
                                 BUILD / "ports.txt", "4096", str(seed), inp, warm],
                                capture_output=True, text=True, check=True)
        assert not result.stderr and inp.read_bytes() == warm.read_bytes()
        total = len(sources) * len(cells) * len(ports)
        expected = []
        for i in range(4096):
            source, target = divmod(permute(i, total, seed), len(cells) * len(ports))
            cell, port = divmod(target, len(ports))
            expected.append(sources[source] + "," + cells[cell] + ports[port])
        assert inp.read_text().splitlines() == ["From,To", *expected]
        checks.append({"seed": seed, "independent_python_rows": len(expected),
                       "generator": json.loads(result.stdout)})
    request = "From,To\n" + "\n".join(expected[:4]) + "\n"
    response = "From,To,delay\n" + "\n".join(
        p + "," + str(v) for p, v in zip(expected[:4], (0, -1, 2147483647, 100))) + "\n"
    positions = folder / "positions.txt"
    positions.write_text("0\n3\n")
    cases = {
        "valid": (request, response, "0\n3\n"),
        "short-input": ("\n".join(request.splitlines()[:-1]) + "\n", response, "0\n3\n"),
        "short-output": (request, "\n".join(response.splitlines()[:-1]) + "\n", "0\n3\n"),
        "extra-input": (request + expected[0] + "\n", response, "0\n3\n"),
        "extra-output": (request, response + expected[0] + ",1\n", "0\n3\n"),
        "input-eof": (request[:-1], response, "0\n3\n"),
        "output-eof": (request, response[:-1], "0\n3\n"),
        "input-header": (request.replace("From,To", "from,to", 1), response, "0\n3\n"),
        "output-header": (request, response.replace("delay", "Delay", 1), "0\n3\n"),
        "endpoint-order": (request, response.replace(expected[0], expected[1], 1), "0\n3\n"),
        "field-count": (request, response.replace(",100\n", ",100,1\n"), "0\n3\n"),
        "leading-zero": (request, response.replace(",100\n", ",0100\n"), "0\n3\n"),
        "plus-sign": (request, response.replace(",100\n", ",+100\n"), "0\n3\n"),
        "negative-zero": (request, response.replace(",0\n", ",-0\n"), "0\n3\n"),
        "bad-delay": (request, response.replace(",-1\n", ",-2\n"), "0\n3\n"),
        "overflow": (request, response.replace(",100\n", ",2147483648\n"), "0\n3\n"),
        "crlf": (request, response.replace("\n", "\r\n"), "0\n3\n"),
        "duplicate-position": (request, response, "0\n00\n"),
        "unsorted-position": (request, response, "3\n0\n"),
    }
    for build in builds:
        for name, (inp, out, pos) in cases.items():
            stem = folder / (Path(build["binary"]["path"]).name + "-" + name)
            stem.with_suffix(".in").write_text(inp)
            stem.with_suffix(".out").write_text(out)
            positions.write_text(pos)
            result = subprocess.run([build["binary"]["path"], "check", stem.with_suffix(".in"),
                                     stem.with_suffix(".out"), "4", positions,
                                     stem.with_suffix(".sample")], capture_output=True, text=True)
            assert (result.returncode == 0) == (name == "valid"), (name, result.stderr)
            assert "Sanitizer" not in result.stderr, result.stderr
            if name == "valid":
                assert json.loads(result.stdout)["contract_passed"]
                with stem.with_suffix(".sample").open() as stream:
                    sample = list(csv.DictReader(stream))
                assert [int(r["row"]) for r in sample] == [0, 3]
                assert [int(r["delay"]) for r in sample] == [0, 100]
            checks.append({"binary": build["binary"]["path"], "case": name,
                           "returncode": result.returncode, "stderr": result.stderr})
    write(ROOT / "selfcheck.json", {"all_passed": True, "checks": checks})


def prior_pairs():
    paths = sorted({p for base in ("build", "validation/results")
                    for p in Path(base).glob("exp*/**/*exact*.csv") if p.is_file()})
    known, used, skipped = set(), [], []
    for path in paths:
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            names = reader.fieldnames or []
            a = next((v for v in ("from", "From") if v in names), None)
            b = next((v for v in ("to", "To") if v in names), None)
            if a is None or b is None:
                skipped.append({"path": str(path), "headers": names})
                continue
            for row in reader:
                known.add((row[a], row[b]))
        used.append(identity(path))
    return known, {"files": used, "unsupported_headers": skipped, "unique_pairs": len(known)}


def prepare():
    import numpy as np
    reference = json.loads(Path("validation/results/exp461/report.json").read_text())
    assert reference["mean_cpu_s"]["f"] < 100 and reference["comparisons"]["f-p"]["ci95_s"][1] < 0
    ROOT.mkdir()
    BUILD.mkdir()
    shutil.copyfile("experiment/实验462-八源真实非重复1B诊断.md", ROOT / "protocol-original.md")
    shutil.copyfile("build/exp429/sources.txt", BUILD / "sources.txt")
    sources = (BUILD / "sources.txt").read_text().splitlines()
    cells = [f"SRB_{x}_{y}/" for x, y in sorted(
        (v["x"], v["y"]) for v in json.loads((ARCH / "SRB_Inst.json").read_text())["Inst"])]
    ports = [v["Name"] for v in json.loads((ARCH / "SRB_Port.json").read_text())["Port"]
             if v["Name"].startswith("Z")]
    for name, values in (("cells", cells), ("ports", ports)):
        (BUILD / (name + ".txt")).write_text("\n".join(values) + "\n")
    assert len(sources) == len(set(sources)) == 467300
    assert len(cells) == len(set(cells)) == 60200 and len(ports) == len(set(ports)) == 160
    builds = [compile_tool(), compile_tool(True)]
    selfcheck(builds, sources, cells, ports)
    known, exclusions = prior_pairs()
    total = len(sources) * len(cells) * len(ports)
    selected, removed = [], 0
    checks = {b: 0 for b in (12, 24, 50, 100)}
    for position in np.random.default_rng(SAMPLE_SEED).choice(ROWS, 40128, replace=False):
        source, target = divmod(permute(int(position), total, SEED), len(cells) * len(ports))
        cell, port = divmod(target, len(ports))
        a, b = sources[source], cells[cell] + ports[port]
        if (a, b) in known:
            removed += 1
            continue
        selected.append([int(position), a, b])
        if len(selected) == 40000:
            break
    assert len(selected) == 40000
    selected.sort()
    for row in selected:
        sx, sy = map(int, row[1].split("/")[0][4:].split("_"))
        tx, ty = map(int, row[2].split("/")[0][4:].split("_"))
        band = next((v for v in checks if abs(tx - sx) + abs(ty - sy) <= v), None)
        checked = band is not None and checks[band] < 2
        if checked:
            checks[band] += 1
        row.append(int(checked))
    assert sum(checks.values()) == 8
    (BUILD / "positions.txt").write_text("".join(str(p[0]) + "\n" for p in selected))
    write(BUILD / "sample.json", selected)
    with (BUILD / "labels.csv").open("x") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("kind", "from", "to", "label", "span_checked"))
        writer.writerows(("fresh", a, b, -2, c) for _, a, b, c in selected)
    exclusions["sample_pairs_removed"] = removed
    write(ROOT / "label-exclusion.json", exclusions)
    prior = json.loads(Path("validation/results/exp461/freeze.json").read_text())
    files = [Path("tests/exp462_unique_stream.cpp"), Path("src/csv.h"),
             Path("validation/exp462_unique_1b.py"), Path("validation/exp208_nominal_parent_tree.py"),
             ROOT / "protocol-original.md", ROOT / "selfcheck.json",
             *[BUILD / n for n in ("sources.txt", "cells.txt", "ports.txt", "positions.txt",
                                  "sample.json", "labels.csv")], *ARCH.glob("*.json"),
             Path("build/exp434/fields.txt"), Path("build/exp203/exact_labels"),
             Path("build/exp155/orbit.i16")]
    write(ROOT / "freeze.json", {
        "files": [identity(p) for p in files], "fields": prior["fields"],
        "binaries": {a: prior["baseline_binaries"][a] for a in ("f", "p")},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "rows": ROWS, "unique_pairs": ROWS, "universe": total, "seed": SEED,
        "sample_seed": SAMPLE_SEED, "sample_rows": len(selected), "orders": ["f", "p"],
        "cpu_core": 3, "timeout_s": 3600, "rss_limit_bytes": 2_000_000_000,
        "label_exclusion": identity(ROOT / "label-exclusion.json"),
        "local_tool": builds[0], "local_sanitizer": builds[1]})
    print("exp462 frozen; independent generator and checker selfchecks passed", flush=True)


def remote():
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026")
    frozen = json.loads((ROOT / "freeze.json").read_text())
    for item in frozen["files"] + frozen["fields"] + list(frozen["binaries"].values()):
        assert identity(item["path"]) == item, item["path"]
    assert shutil.disk_usage(".").free > 122_000_000_000
    build = compile_tool()
    write(ROOT / "binary.json", build)
    common.BUILD = ROOT
    common.fields = lambda p: json.loads(Path(p).read_text())
    generator = common.measured("generate", [
        build["binary"]["path"], "generate", BUILD / "sources.txt", BUILD / "cells.txt",
        BUILD / "ports.txt", ROWS, SEED, BUILD / "requests.csv", BUILD / "warmup.csv"], frozen)
    assert generator["summary"]["unique_pairs"] == generator["summary"]["inverse_checks"] == ROWS
    generator["input"] = identity(BUILD / "requests.csv")
    generator["warmup"] = identity(BUILD / "warmup.csv")
    write(ROOT / "generate.json", generator)
    runs = []
    for arm in frozen["orders"]:
        for full in (False, True):
            name = arm if full else "warm-" + arm
            inp = BUILD / ("requests.csv" if full else "warmup.csv")
            output = BUILD / (name + ".csv")
            run = common.measured(name, [frozen["binaries"][arm]["path"], ARCH,
                                         "build/exp434/fields.txt", inp, output, "bound"], frozen)
            assert run["summary"]["rows"] == (ROWS if full else 20000)
            assert run["summary"]["cache_hits"] == 0
            run["output"] = identity(output)
            write(ROOT / (name + ".json"), run)
            runs.append(run)
            if full and arm == "f":
                contract = common.measured("contract", [
                    build["binary"]["path"], "check", inp, output, ROWS, BUILD / "positions.txt",
                    BUILD / "predictions.csv"], frozen)
                assert contract["summary"]["sample_rows"] == frozen["sample_rows"]
                contract["sample"] = identity(BUILD / "predictions.csv")
                write(ROOT / "contract.json", contract)
    full = [r for r in runs if not r["name"].startswith("warm")]
    assert full[0]["output"]["sha256"] == full[1]["output"]["sha256"]
    assert ({k: v for k, v in full[0]["summary"].items() if k != "rss_bytes"} ==
            {k: v for k, v in full[1]["summary"].items() if k != "rss_bytes"})
    write(ROOT / "timing.json", {"all_passed": True, "runs": runs})
    expected = json.loads((BUILD / "sample.json").read_text())
    with (BUILD / "predictions.csv").open() as stream:
        actual = list(csv.DictReader(stream))
    assert [[int(r["row"]), r["From"], r["To"]] for r in actual] == [r[:3] for r in expected]
    common.fields = lambda p: {}
    labels = common.measured("labels", ["build/exp203/exact_labels", ARCH, BUILD / "labels.csv",
                                      "build/exp155/orbit.i16", BUILD / "exact.csv"], frozen)
    assert "labels_done rows=40000 known_checks=0 span_checks=8 threads=1" in (ROOT / "labels.stdout").read_text()
    write(ROOT / "labels.json", {"all_passed": True, "run": labels,
                                "output": identity(BUILD / "exact.csv")})
    print("EXP462_REMOTE_DONE", flush=True)


def analyze():
    import numpy as np
    from exp417_first_net import score
    started = time.process_time()
    frozen = json.loads((ROOT / "freeze.json").read_text())
    timing = json.loads((ROOT / "timing.json").read_text())
    labels = json.loads((ROOT / "labels.json").read_text())
    assert timing["all_passed"] and labels["all_passed"]
    assert identity(BUILD / "exact.csv") == labels["output"]
    assert identity(BUILD / "predictions.csv") == json.loads((ROOT / "contract.json").read_text())["sample"]
    with (BUILD / "exact.csv").open() as stream:
        gold = list(csv.DictReader(stream))
    with (BUILD / "predictions.csv").open() as stream:
        prediction = list(csv.DictReader(stream))
    assert len(gold) == len(prediction) == frozen["sample_rows"]
    assert all((g["from"], g["to"]) == (p["From"], p["To"]) for g, p in zip(gold, prediction))
    truth = np.array([int(g["exact"]) for g in gold])
    predicted = np.array([int(p["delay"]) for p in prediction])
    points = 100 * score(truth, predicted)
    _, groups = np.unique([g["from"] for g in gold], return_inverse=True)
    counts, sums = np.bincount(groups), np.bincount(groups, weights=points)
    rng = np.random.default_rng(SAMPLE_SEED)
    boot = []
    for _ in range(2000):
        ids = rng.integers(len(counts), size=len(counts))
        boot.append(sums[ids].sum() / counts[ids].sum())
    runs = {r["name"]: r for r in timing["runs"]}
    for run in runs.values():
        for item in run["files"]:
            assert identity(item["path"]) == item
        assert run["max_threads"] == 1 and run["rss_bytes"] <= frozen["rss_limit_bytes"]
    result = {
        "rows": ROWS, "unique_pairs": ROWS, "sample_rows": len(gold),
        "cpu_s": {a: runs[a]["cpu_s"] for a in ("f", "p")},
        "wall_s": {a: runs[a]["wall_s"] for a in ("f", "p")},
        "cpu_saving": 1 - runs["f"]["cpu_s"] / runs["p"]["cpu_s"],
        "accuracy_pp": float(points.mean()), "accuracy_ci95_pp": np.quantile(boot, [.025, .975]).tolist(),
        "accuracy_gate": bool(points.mean() > 99), "stage_1b_cpu_gate": runs["f"]["cpu_s"] <= 300,
        "max_rss_bytes": max(r["rss_bytes"] for r in runs.values()),
        "output_sha256": runs["f"]["output"]["sha256"], "changed_rows": 0,
        "summary": {k: v for k, v in runs["f"]["summary"].items() if k != "rss_bytes"},
        "exact_cpu_s": labels["run"]["cpu_s"], "accuracy_groups": {}, "distance_bands": {},
        "scope": "Complete eight-source unique 1B; full endpoints, static delivery and other architectures unverified.",
        "timing_uncertainty": "One full run per arm; no CPU interval estimated.",
        "exp323_reference": "exp429 same-distribution 1M CPU 101.535s; same-scale 1B not run."}
    for name in sorted({g["from"].split("/")[1] for g in gold}):
        mask = np.array([g["from"].endswith("/" + name) for g in gold])
        result["accuracy_groups"][name] = {"rows": int(mask.sum()), "accuracy_pp": float(points[mask].mean()),
                                          "mean_absolute_error": float(np.abs(predicted[mask] - truth[mask]).mean())}
    distances = []
    for g in gold:
        sx, sy = map(int, g["from"].split("/")[0][4:].split("_"))
        tx, ty = map(int, g["to"].split("/")[0][4:].split("_"))
        distances.append(abs(tx - sx) + abs(ty - sy))
    distances = np.array(distances)
    for low, high in ((0, 0), (1, 12), (13, 24), (25, 50), (51, 100), (101, 300), (301, 10000)):
        mask = (distances >= low) & (distances <= high)
        result["distance_bands"][f"{low}-{high}"] = {
            "rows": int(mask.sum()), "accuracy_pp": float(points[mask].mean()) if mask.any() else None}
    result["scoring_cpu_s"] = time.process_time() - started
    write(ROOT / "report.json", result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "remote", "analyze"))
    {"prepare": prepare, "remote": remote, "analyze": analyze}[parser.parse_args().stage]()
