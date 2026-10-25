#!/usr/bin/env python3
"""Validate the frozen Q4 on correction-unseen 1M, then complete unique 10M."""
import csv
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp619/validation").resolve()))
import exp619_complete_candidate as prior

ROOT, BUILD = Path("validation/results/exp620"), Path("build/exp620")
PLAN = Path("experiment/实验620-冻结Q4的独立修正验证与完整10M.md")
read, write, identity, check = prior.read, prior.write, prior.identity, prior.checked
speed = prior.speed
speed.ROOT = ROOT
complete = prior.previous.prior.old.complete
points = complete.real.points
SEED = 20261023620
ARMS = ("A", "Q4")
BINARIES = {"A": Path("../exp609/build/exp609/F"),
            "Q4": Path("../exp619/build/exp619/Q4")}


def compare(predictions, truth, partitions, weight, timing, rows):
    assert set(predictions) == set(ARMS) and weight.shape == truth.shape
    assert np.all(weight > 0) and abs(float(weight.sum()) - rows) < 1e-6
    delta = points(predictions["Q4"], truth) - points(predictions["A"], truth)
    family = partitions["source_family"]
    counts = np.bincount(family, weights=weight, minlength=26)
    sums = np.bincount(family, weights=weight * delta, minlength=26)
    assert len(counts) == 26 and counts.min() > 0
    rng = np.random.default_rng(SEED)
    sampled = rng.integers(26, size=(9999, 26))
    accuracy = sums[sampled].sum(axis=1) / counts[sampled].sum(axis=1)
    extra = np.asarray(timing["Q4"]) - timing["A"]
    rounds = 3 if rows == 100000000 else 6
    assert extra.shape == (rounds,)
    cpu = extra[rng.integers(rounds, size=(9999, rounds))].mean(axis=1)
    accuracy_point = float(np.average(delta, weights=weight))
    joint = .8 * accuracy - (1e9 / rows) * cpu / 120
    joint_point = .8 * accuracy_point - (1e9 / rows) * extra.mean() / 120
    groups = {name: {str(int(k)): dict(
        sample_rows=int((values == k).sum()),
        delta_accuracy_pp=float(np.average(delta[values == k], weights=weight[values == k])))
        for k in np.unique(values)} for name, values in partitions.items()}
    quality = (accuracy_point >= .10 and np.quantile(accuracy, .025) > 0 and all(
        v["delta_accuracy_pp"] >= -.03 for key, group in groups.items()
        if key in ("distance", "near_axis") for v in group.values()))
    return dict(accuracy_pp={a: float(np.average(points(p, truth), weights=weight))
        for a, p in predictions.items()}, delta_accuracy_pp=accuracy_point,
        ci95_delta_accuracy_pp=np.quantile(accuracy, [.025, .975]).tolist(),
        changed_sample_rows=int(np.count_nonzero(predictions["Q4"] != predictions["A"])),
        extra_cpu_s=float(extra.mean()), ci95_extra_cpu_s=np.quantile(cpu, [.025, .975]).tolist(),
        score_extrapolated_1b=float(joint_point),
        ci95_score_extrapolated_1b=np.quantile(joint, [.025, .975]).tolist(),
        quality_gate=bool(quality),
        joint_gate=bool(quality and joint_point >= .01 and np.quantile(joint, .025) > 0),
        groups=groups, full_population_scored=rows == 1000000,
        cpu_1b_is_extrapolation=True, final_accuracy_goal_verified=False)


def self_check():
    family = np.repeat(np.arange(26), 2)
    truth = np.full(52, 1000, dtype="i8")
    p = {"A": truth + 10, "Q4": truth.copy()}
    result = compare(p, truth, dict(source_family=family, distance=family % 4,
        near_axis=family % 2), np.ones(52), {"A": [1.] * 6, "Q4": [1.] * 6}, 52)
    assert result["quality_gate"] and result["joint_gate"]
    assert result["changed_sample_rows"] == 52 and result["extra_cpu_s"] == 0
    assert result["accuracy_pp"]["Q4"] == 100
    equal = compare({"A": truth, "Q4": truth}, truth, dict(source_family=family),
        np.full(52, 2.), {"A": [1.] * 6, "Q4": [1.] * 6}, 104)
    assert equal["delta_accuracy_pp"] == 0 and not equal["joint_gate"]
    large = compare(p, truth, dict(source_family=family), np.full(52, 1e8 / 52),
        {"A": [1.] * 3, "Q4": [1.] * 3}, 100000000)
    assert large["joint_gate"] and large["extra_cpu_s"] == 0


def sample_labels(rows):
    base = Path("../exp580/build/exp580")
    exact = base / "scale-exact.csv"
    frozen = read("../exp580/validation/results/exp580/offline-label-report.json")
    check(exact, frozen["exact"])
    assert frozen["all_complete"]
    assert not read("../exp580/validation/results/exp580/offline-label-freeze.json")["training_overlap"]
    positions = list(map(int, (base / "scale-input/positions.txt").read_text().splitlines()))
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    families = dict(zip(mapping["sources"], [v[0] for v in mapping["source_coordinates"]]))
    sources, targets = [(base / (name + ".txt")).read_text().splitlines()
                        for name in ("sources", "targets")]
    si, ti = dict(zip(sources, range(208))), dict(zip(targets, range(288)))
    requests, truth, pair = [], [], []
    partitions = {k: [] for k in ("source_family", "distance", "near_axis", "direction")}
    with exact.open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        for i, row in enumerate(reader):
            assert len(row) == 7 and row[0] == str(i)
            a, b = [pin.split("/", 1) for pin in row[1:3]]
            cells = [tuple(map(int, p[0][4:].split("_"))) for p in (a, b)]
            dx, dy = cells[1][0] - cells[0][0], cells[1][1] - cells[0][1]
            requests.append(tuple(row[1:3]))
            truth.append(int(row[3]))
            pair.append(si[a[1]] * 288 + ti[b[1]])
            for key, value in dict(source_family=families[a[1]],
                    distance=np.searchsorted([24, 100, 300], abs(dx) + abs(dy), side="right"),
                    near_axis=abs(dx) < 20 or abs(dy) < 24,
                    direction=2 * (dx < 0) + (dy < 0)).items():
                partitions[key].append(value)
    assert len(requests) == len(set(requests)) == len(positions) == 239616
    assert positions == sorted(set(positions))
    pair = np.asarray(pair, dtype="i4")
    assert np.all(np.bincount(pair, minlength=59904) == 4)
    population = np.asarray(read(base / f"scale-input/pair-populations-{rows}.json"))
    assert population.shape == (59904,) and population.min() >= 4 and population.sum() == rows
    return positions, requests, np.asarray(truth), pair, {
        k: np.asarray(v, dtype="i4") for k, v in partitions.items()}, population[pair] / 4


def run(mode):
    if mode == "1m":
        ROOT.mkdir(parents=True, exist_ok=False)
        BUILD.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(PLAN, ROOT / "protocol-original.md")
        self_check()
    else:
        assert read(ROOT / "1m-report.json")["comparison"]["joint_gate"]
        if mode == "100m":
            assert read(ROOT / "10m-report.json")["comparison"]["joint_gate"]
            self_check()
    frozen = read("../exp619/validation/results/exp619/build-freeze.json")
    for name, path in BINARIES.items():
        check(path, frozen["binaries"][name])
        linked = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
        assert "not a dynamic executable" in linked.stdout + linked.stderr
        assert path.stat().st_size < 100000000
    rows = {"1m": 1000000, "10m": 10000000, "100m": 100000000}[mode]
    if mode == "1m":
        reference = read("../exp588/validation/results/exp588/evaluation.json")["evidence"]["D64"]
        request = Path("../exp588/build/exp588/u-role/requests.csv")
        exact = Path("../exp588/build/exp588/exact.csv")
        check(exact, reference["labels"])
    else:
        old = read(f"../exp609/validation/results/exp609/{mode}-report.json")
        reference = dict(input=old["input"], output=old["reference"]["output"]
            if mode == "10m" else old["output"])
        request = Path(f"../exp580/build/exp580/scale-input/requests-{mode}.csv")
        positions, requests, truth, pair, partitions, weight = sample_labels(rows)
    check(request, reference["input"])
    schedule = [ARMS, ARMS, ARMS[::-1], ARMS] if mode == "100m" else [
        ARMS, *([ARMS, ARMS[::-1]] * 3)]
    if mode == "100m":
        assert shutil.disk_usage(".").free > 10000000000
    write(ROOT / (mode + "-freeze.json"), dict(binaries={a: identity(p) for a, p in BINARIES.items()},
        input=identity(request), reference=reference, schedule=schedule, seed=SEED,
        driver=identity(__file__), protocol=identity(ROOT / "protocol-original.md"),
        current_protocol=identity(PLAN),
        disk_free_start=shutil.disk_usage(".").free, scores_previously_seen=False,
        data_history="exp588: background-used, correction-unseen" if mode == "1m"
        else "exp580: existing unique stream and frozen stratified exact sample"))
    timing, evidence, predictions, runs, deleted = {a: [] for a in ARMS}, {}, {}, [], []
    for iteration, order in enumerate(schedule):
        for arm in order:
            output = BUILD / f"{mode}-{iteration}-{arm}.csv"
            command = [str(BINARIES[arm]), "-in", str(request), "-out", str(output)]
            measured = speed.measured(command, output.stem)
            counters, actual = read(measured["stderr"]), identity(output)
            assert measured["threads"] == 1 and measured["rss_bytes"] <= 2000000000
            assert measured["cpu_s"] <= 3600
            assert counters == dict(rows=rows, unreachable=0, query_allocations=0)
            if iteration == 0:
                if arm == "A":
                    assert all(actual[k] == reference["output"][k] for k in ("bytes", "sha256"))
                if mode == "1m":
                    p, truth, record, partitions = complete.check_output(request, output, exact)
                    predictions[arm], evidence[arm] = p, record
                    weight = np.ones(rows)
                else:
                    sample = BUILD / f"{mode}-{arm}-sample.csv"
                    contract = speed.measured(["../exp580/build/exp580/contract-check", "check",
                        str(request), str(output), str(rows),
                        "../exp580/build/exp580/scale-input/positions.txt", str(sample)],
                        mode + "-" + arm + "-contract")
                    checked = read(ROOT / (mode + "-" + arm + "-contract.stdout"))
                    assert checked["contract_passed"]
                    values = []
                    with sample.open(newline="") as stream:
                        reader = csv.reader(stream)
                        assert next(reader) == ["row", "From", "To", "delay"]
                        for i, row in enumerate(reader):
                            assert len(row) == 4 and int(row[0]) == positions[i]
                            assert tuple(row[1:3]) == requests[i] and row[3] == str(int(row[3]))
                            values.append(int(row[3]))
                    assert len(values) == len(truth) and min(values) >= 0
                    predictions[arm] = np.asarray(values)
                    evidence[arm] = dict(output=actual, contract=checked, contract_run=contract,
                        sample=identity(sample), labels=identity("../exp580/build/exp580/scale-exact.csv"))
            assert all(actual[k] == evidence[arm]["output"][k] for k in ("bytes", "sha256"))
            measured.update(arm=arm, iteration=iteration, output=actual, counters=counters)
            write(ROOT / (output.stem + "-evidence.json"), measured)
            runs.append(measured)
            if iteration:
                timing[arm].append(measured["cpu_s"])
                deleted.append(dict(file=actual, identical_to=evidence[arm]["output"], rebuild_command=command))
                output.unlink()
            print("EXP620_RUN", mode, iteration, arm, measured["cpu_s"], flush=True)
    result = compare(predictions, truth, partitions, weight, timing, rows)
    for a, p in predictions.items():
        p.astype("<i4").tofile(BUILD / (mode + "-" + a + "-prediction.i32"))
    write(ROOT / (mode + "-report.json"), dict(comparison=result, evidence=evidence, runs=runs,
        timing=timing, rows=rows, unique_rows=rows, port_pairs=59904,
        deleted_duplicates=deleted, released_bytes=sum(v["file"]["bytes"] for v in deleted),
        disk_free_end=shutil.disk_usage(".").free))
    print("EXP620_RESULT", mode, result["accuracy_pp"], result["extra_cpu_s"],
          result["score_extrapolated_1b"], result["joint_gate"], flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp620")
    assert sys.argv[1:] in (["1m"], ["10m"], ["100m"])
    run(sys.argv[1])
