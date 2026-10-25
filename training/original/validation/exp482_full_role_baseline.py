#!/usr/bin/env python3
"""Freeze and measure a complete U-role 1M with mandatory endpoint coverage."""
import argparse
import collections
import csv
import json
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import time

from exp208_nominal_parent_tree import identity, write

ROOT = Path("validation/results/exp482")
BUILD = Path("build/exp482")
ARCH = Path("doc/eda比赛文件/arch")
PLAN = Path("experiment/实验482-全端口非重复1M基准与覆盖检查.md")
HIDDEN = Path("build/hidden-suite-v1")
ROWS = 1_000_000
ARMS = {
    "A": ("build/exp320/narrow/estimate", ""),
    "B": ("build/exp320/narrow/estimate", "-cache-mb 0"),
    "C": ("build/exp353/estimate", ""),
}


def roles():
    ports = json.loads((ARCH/"SRB_Port.json").read_text())["Port"]
    arcs = json.loads((ARCH/"SRB_Arc.json").read_text())["Arcs"]
    nets = json.loads((ARCH/"SRB_Net.json").read_text())["Nets"]
    outgoing = {a["from"] for a in arcs} | {n["from"] for n in nets}
    sources = [p["Name"] for p in ports
               if not p["Name"].startswith("I") and p["Name"] in outgoing]
    targets = [p["Name"] for p in ports if p["Direction"].lower() == "output"]
    assert len(sources) == 208 and len(targets) == 288
    return sources, targets


def coverage(rows):
    sources, targets = roles()
    left = collections.Counter(a.split("/", 1)[1] for a, b in rows)
    right = collections.Counter(b.split("/", 1)[1] for a, b in rows)
    assert set(left) == set(sources), sorted(set(sources)-set(left))
    assert set(right) == set(targets), sorted(set(targets)-set(right))
    return {"source_ports": len(left), "target_ports": len(right),
            "from_port_counts": dict(left), "to_port_counts": dict(right)}


def measured(name, command):
    with (ROOT/(name+".stdout")).open("xb") as out, (ROOT/(name+".stderr")).open("xb") as err:
        result = subprocess.run(
            ["/usr/bin/time", "-f", "user=%U sys=%S wall=%e rss_kib=%M exit=%x",
             "-o", str(ROOT/(name+".time")), *map(str, command)], stdout=out, stderr=err)
    assert result.returncode == 0, (name, result.returncode)
    return {"command": list(map(str, command)), "time": (ROOT/(name+".time")).read_text()}


def prepare():
    ROOT.mkdir()
    BUILD.mkdir()
    (ROOT/"protocol-original.md").write_bytes(PLAN.read_bytes())
    protected = [identity(p) for p in ("estimate", "src/residue_estimator.cpp",
                                      "src/residue_estimator.h", "src/xgb_residual_base47_fast.h")]
    files = [Path(__file__).resolve().relative_to(Path.cwd()), ROOT/"protocol-original.md", Path("scripts/run_scale.py"),
             Path("scripts/verify_scale_output.py"), Path("validation/exp208_nominal_parent_tree.py"),
             *ARCH.glob("*.json")]
    write(ROOT/"freeze.json", {
        "files": [identity(p) for p in files], "protected": protected,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_ports": roles()[0], "target_ports": roles()[1],
        "rows": ROWS, "orders": ["ABC", "CBA", "ABC"],
        "baseline_sha256": "14b6fea221e7158c6acab1a51768a9e83ba7e570f5744e6416490cd1ffae1b1a",
        "formal_sha256": protected[0]["sha256"],
        "disk_start_bytes": shutil.disk_usage(".").free})
    print("exp482 protocol and complete endpoint sets frozen", flush=True)


def remote():
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026")
    frozen = json.loads((ROOT/"freeze.json").read_text())
    for item in frozen["files"]:
        assert identity(item["path"]) == item, item["path"]
    BUILD.mkdir(exist_ok=True)
    tools = [HIDDEN/"make_hidden_suite", HIDDEN/"check_hidden_suite", HIDDEN/"reach.bin",
             HIDDEN/"independent/eligibility.bin", Path("build/exp203/exact_labels"),
             Path("build/exp155/orbit.i16")]
    binaries = {a: identity(binary) for a, (binary, _) in ARMS.items()}
    assert binaries["A"]["sha256"] == frozen["baseline_sha256"]
    assert binaries["C"]["sha256"] == frozen["formal_sha256"]
    write(ROOT/"remote-freeze.json", {"files": [identity(p) for p in tools],
          "binaries": binaries, "disk_start_bytes": shutil.disk_usage(".").free,
          "machine": subprocess.check_output(["uname", "-a"], text=True).strip()})
    data = BUILD/"u-role"
    measured("generate", [HIDDEN/"make_hidden_suite", ARCH, HIDDEN/"reach.bin",
             "U-role", ROWS, 20261018482, 20261019482, data])
    measured("input-check", [HIDDEN/"check_hidden_suite", ARCH, HIDDEN/"reach.bin",
             HIDDEN/"independent/eligibility.bin", "U-role", ROWS, data/"requests.csv", data/"check"])
    shutil.copyfile(data/"check/check.json", ROOT/"input-check.json")
    with (data/"requests.csv").open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        pairs = [tuple(row) for row in reader]
    assert len(pairs) == ROWS and len(set(pairs)) == ROWS
    input_identity = identity(data/"requests.csv")
    write(ROOT/"input.json", {**input_identity, "rows": ROWS, "unique_rows": ROWS,
                              "coverage": coverage(pairs)})
    positions = sorted(random.Random(20261020482).sample(range(ROWS), 40000))
    sample = [pairs[i] for i in positions]
    sample_coverage = coverage(sample)
    with (BUILD/"labels.csv").open("x") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["kind", "from", "to", "label", "span_checked"])
        for j, (a, b) in enumerate(sample):
            writer.writerow(["fresh-full-role", a, b, -2, int(j < 8)])
    write(ROOT/"sample-freeze.json", {"request": identity(BUILD/"labels.csv"),
          "positions": positions, "seed": 20261020482, "coverage": sample_coverage,
          "scope": "Uniform fresh sample for baseline calibration; future development data."})
    print("exp482 complete 1M and exact sample cover 208 source / 288 target ports", flush=True)
    del pairs
    runs = []
    schedule = [("warm-"+a, a) for a in ARMS]
    schedule += [(a+str(i), a) for i, order in enumerate(frozen["orders"], 1) for a in order]
    expected = None
    for name, arm in schedule:
        binary, extra = ARMS[arm]
        output = BUILD/(name+".csv")
        command = ["taskset", "-c", "3", "python3", "scripts/run_scale.py",
                   "--binary", binary, "--arch", str(ARCH), "--input", str(data/"requests.csv"),
                   "--input-meta", str(ROOT/"input.json"), "--output", str(output),
                   "--time-log", str(ROOT/(name+".time")),
                   "--stderr-log", str(ROOT/(name+".stderr")),
                   "--json", str(ROOT/(name+".json")),
                   "--estimator-timeout-seconds", "3600", "--extra", extra]
        subprocess.run(command, check=True)
        row = json.loads((ROOT/(name+".json")).read_text())
        assert row["exit_code"] == 0 and row["observed_max_threads"] == 1
        assert row["max_rss_kib"]*1024 <= 2_000_000_000 and row["cpu_seconds"] <= 3600
        out_identity = identity(output)
        if expected is None:
            expected = out_identity["sha256"]
            subprocess.run(["python3", "scripts/verify_scale_output.py", "--mode", "unique",
                            "--input", str(data/"requests.csv"), "--output", str(output),
                            "--expect-rows", str(ROWS), "--json", str(ROOT/"output-check.json")],
                           check=True, stdout=subprocess.DEVNULL)
        assert out_identity["sha256"] == expected, name
        row.update(name=name, arm=arm, output_identity=out_identity)
        runs.append(row)
        print(name, row["cpu_seconds"], out_identity["sha256"], flush=True)
    write(ROOT/"timing.json", {"runs": runs, "output_sha256": expected,
                               "changed_rows": 0, "full_contract": identity(ROOT/"output-check.json")})
    measured("labels", ["taskset", "-c", "3", "build/exp203/exact_labels", ARCH,
                       BUILD/"labels.csv", "build/exp155/orbit.i16", BUILD/"exact.csv"])
    with (BUILD/"A1.csv").open(newline="") as stream, (BUILD/"predictions.csv").open("x") as out:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To", "delay"]
        wanted = set(positions)
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["row", "From", "To", "delay"])
        for i, row in enumerate(reader):
            if i in wanted:
                writer.writerow([i, *row])
    write(ROOT/"labels.json", {"output": identity(BUILD/"exact.csv"),
          "prediction": identity(BUILD/"predictions.csv"), "sample": identity(BUILD/"labels.csv"),
          "cost": (ROOT/"labels.time").read_text()})
    print("EXP482_REMOTE_DONE", flush=True)


def analyze():
    import numpy as np
    from exp417_first_net import score
    from exp462_unique_1b import prior_pairs
    started = time.process_time()
    timing = json.loads((ROOT/"timing.json").read_text())
    sample = json.loads((ROOT/"sample-freeze.json").read_text())
    labels = json.loads((ROOT/"labels.json").read_text())
    for item in labels["output"], labels["prediction"], labels["sample"]:
        assert identity(item["path"]) == item
    with (BUILD/"exact.csv").open() as stream:
        gold = list(csv.DictReader(stream))
    with (BUILD/"predictions.csv").open() as stream:
        prediction = list(csv.DictReader(stream))
    pairs = [(r["from"], r["to"]) for r in gold]
    assert len(gold) == len(prediction) == 40000
    assert pairs == [(r["From"], r["To"]) for r in prediction]
    assert coverage(pairs) == sample["coverage"]
    truth = np.array([int(r["exact"]) for r in gold])
    actual = np.array([int(r["delay"]) for r in prediction])
    assert np.all(truth >= 0)
    points = 100*score(truth, actual)
    _, group = np.unique([p[0] for p in pairs], return_inverse=True)
    counts, sums = np.bincount(group), np.bincount(group, weights=points)
    rng = np.random.default_rng(20261021482)
    bootstrap = []
    for _ in range(2000):
        selected = rng.integers(len(counts), size=len(counts))
        bootstrap.append(sums[selected].sum()/counts[selected].sum())
    runs = {r["name"]: r for r in timing["runs"]}
    means = {a: statistics.mean(runs[a+str(i)]["cpu_seconds"] for i in (1,2,3)) for a in ARMS}
    comparisons = {}
    for a, b in (("B", "A"), ("C", "A"), ("C", "B")):
        delta = [runs[a+str(i)]["cpu_seconds"]-runs[b+str(i)]["cpu_seconds"] for i in (1,2,3)]
        mean = statistics.mean(delta)
        margin = 4.302652729911275*statistics.stdev(delta)/(3**.5)+.02
        comparisons[a+"-"+b] = {"mean_delta_s": mean, "ci95_s": [mean-margin,mean+margin],
                                "paired_delta_s": delta, "saved_percent": 100*(1-means[a]/means[b])}
    _, exclusions = prior_pairs()
    # The new labels are already present locally; exclude their own file from history.
    own = identity(BUILD/"exact.csv")
    previous_files = [p for p in exclusions["files"] if p["path"] != own["path"]]
    previous = set()
    for item in previous_files:
        with Path(item["path"]).open() as stream:
            reader = csv.DictReader(stream)
            names = reader.fieldnames
            a = "from" if "from" in names else "From"
            b = "to" if "to" in names else "To"
            previous.update((r[a],r[b]) for r in reader)
    write(ROOT/"label-history.json", {"checked_files": previous_files,
          "overlap": [i for i, p in enumerate(pairs) if p in previous],
          "scope": "Existing exact CSV filenames scanned; this round is baseline development."})
    groups = {}
    distance = np.array([sum(abs(int(x)-int(y)) for x,y in zip(
        a.split("/")[0].split("_")[1:], b.split("/")[0].split("_")[1:])) for a,b in pairs])
    tags = {"all": np.ones(len(pairs), dtype=bool)}
    for side in (0,1):
        for family in ("Z", "A", "S"):
            tags[("source_" if side == 0 else "target_")+family] = np.array(
                [p[side].split("/")[1].startswith(family) for p in pairs])
    for low, high in ((0,0),(1,12),(13,24),(25,50),(51,100),(101,300),(301,1000)):
        tags[f"distance_{low}_{high}"] = (distance>=low)&(distance<=high)
    for name, mask in tags.items():
        if np.any(mask):
            error = np.abs(actual[mask]-truth[mask])
            groups[name] = {"rows": int(mask.sum()), "accuracy_pp": float(points[mask].mean()),
                            "mae_ps": float(error.mean()), "max_error_ps": int(error.max())}
    write(ROOT/"report.json", {"rows": ROWS, "profile": "U-role",
          "coverage": {"source_ports": 208, "target_ports": 288},
          "sample_rows": 40000, "mean_cpu_s": means, "comparisons": comparisons,
          "accuracy_pp": float(points.mean()), "accuracy_ci95_pp": np.quantile(bootstrap,[.025,.975]).tolist(),
          "paired_accuracy_delta_pp": 0, "changed_rows": 0, "groups": groups,
          "max_rss_bytes": max(r["max_rss_kib"]*1024 for r in runs.values()),
          "output_sha256": timing["output_sha256"], "analysis_cpu_s": time.process_time()-started,
          "scope": "Complete full-role 1M published baselines; 40k exact sample; no new estimator."})
    print((ROOT/"report.json").read_text(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "remote", "analyze"))
    globals()[parser.parse_args().stage]()
