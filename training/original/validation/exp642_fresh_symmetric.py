#!/usr/bin/env python3
"""Confirm frozen S8 on a new, source-pin-disjoint, full-port 10M on r9."""
import csv
import gzip
import io
import json
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path("../exp501/validation").resolve()))
import exp501_fresh_full_labels as labels
sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp642"), Path("build/exp642")
PLAN = Path("experiment/实验642-冻结S8对称残差树的新源端10M验证.md")
ROWS, SAMPLES, SEED = 10_000_000, 239_616, 20261023642
ARMS = ("A", "S8")
BINARIES = {"A": Path("../exp622/build/exp622/T"),
            "S8": Path("../exp640/build/exp640/S8")}
CHECKER = Path("../exp580/build/exp580/contract-check")
ARCH = Path("doc/eda比赛文件/arch")
HIDDEN = Path("../../build/hidden-suite-v1")
speed.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), str(path)


def freeze_check():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"]:
        check(item["path"], item)
    return frozen


def filter_stream(source, output, source_pins, known, sources, targets, wanted):
    si, ti = ({p.encode(): i for i, p in enumerate(ports)} for ports in (sources, targets))
    populations, sample = [0] * (len(si) * len(ti)), []
    accepted = rejected_source = rejected_pair = visited = 0
    assert source.readline() == b"From,To\n"
    output.write(b"From,To\n")
    for line in source:
        visited += 1
        assert line.endswith(b"\n") and b"\r" not in line and line.count(b",") == 1
        a, b = line[:-1].split(b",")
        if a in source_pins:
            rejected_source += 1
            continue
        if line[:-1] in known:
            rejected_pair += 1
            continue
        pair = si[a.split(b"/", 1)[1]] * len(ti) + ti[b.split(b"/", 1)[1]]
        populations[pair] += 1
        if populations[pair] <= 4:
            sample.append((accepted, a.decode(), b.decode()))
        output.write(line)
        accepted += 1
        if accepted == wanted:
            break
    assert accepted == wanted and min(populations) >= 4, (accepted, min(populations))
    assert len(sample) == 4 * len(populations) and sum(populations) == wanted
    return populations, sample, dict(visited_proposal_rows=visited,
        rejected_source_rows=rejected_source, rejected_history_rows=rejected_pair)


def prepare():
    self_check()
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    screened = read("../exp640/validation/results/exp640/timing-screen-report.json")
    assert screened["selected"] == "S8" and screened["comparisons"]["S8"]["screen_gate"]
    frozen = read("../exp640/validation/results/exp640/cli-freeze.json")
    for a, path in BINARIES.items():
        check(path, frozen["binaries"][a])
        linked = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
        assert "not a dynamic executable" in linked.stdout + linked.stderr
        assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(path)], text=True)
        assert path.stat().st_size < 100_000_000
    history = [Path("../exp588/build/exp588/known-local.csv.gz"),
        Path("../exp501/build/exp501/u-role/requests.csv"),
        Path("../exp562/build/exp562/u-role/requests.csv"),
        Path("../exp588/build/exp588/u-role/requests.csv"),
        Path("../exp624/build/exp624/u-role/requests.csv"),
        Path("../exp580/build/exp580/scale-exact.csv")]
    tools = read("../exp501/validation/results/exp501/freeze.json")["expected_tools"]
    for tool in tools:
        check(Path("../..") / tool["path"], tool)
    check(CHECKER, read("../exp580/validation/results/exp580/10m-freeze.json")["checker"])
    for tool in (HIDDEN / "make_hidden_suite", HIDDEN / "check_hidden_suite",
                 Path("../../build/exp203/exact_labels"), CHECKER):
        result = subprocess.run([str(tool), "--help"], capture_output=True, text=True)
        text = result.stdout + result.stderr
        assert "usage" in text.lower(), (tool, result.returncode, text[:200])
        (ROOT / (tool.name + "-help.txt")).write_text(text)
    files = [PLAN, ROOT / "protocol-original.md", Path(__file__), Path(labels.__file__),
             Path(speed.__file__), Path("../exp624/validation/exp624_fresh_leaf_validation.py"),
             Path("../exp575/offline/validation/results/exp575/mapping.json"), *ARCH.glob("*.json")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files],
        rows=ROWS, sample_rows=SAMPLES, proposal_rows=12_000_000,
        proposal_seed=20261024642, shuffle_seed=20261025642,
        binaries={a: identity(p) for a, p in BINARIES.items()}, checker=identity(CHECKER),
        selection=identity("../exp640/validation/results/exp640/timing-screen-report.json"),
        expected_tools=tools, history=[identity(p) for p in history],
        required_port_pairs=59904, source_ports=labels.roles()[0], target_ports=labels.roles()[1],
        sample_rule="first four per port pair after frozen independent global shuffle and filtering",
        untouched_scores=True, cpu_label_budget_s=5000, disk_free_start=shutil.disk_usage(".").free))
    print("EXP642_10M_FROZEN", flush=True)


def dataset():
    frozen = freeze_check()
    for tool in frozen["expected_tools"]:
        check(Path("../..") / tool["path"], tool)
    proposal = BUILD / "proposal"
    speed.measured([str(HIDDEN / "make_hidden_suite"), str(ARCH), str(HIDDEN / "reach.bin"),
        "U-role", str(frozen["proposal_rows"]), str(frozen["proposal_seed"]),
        str(frozen["shuffle_seed"]), str(proposal)], "generate-proposal")
    training = Path("../exp501/build/exp501/u-role/requests.csv")
    with training.open("rb") as stream:
        assert stream.readline() == b"From,To\n"
        source_pins = {line.split(b",", 1)[0] for line in stream}
    known = set()
    for item in frozen["history"]:
        path = Path(item["path"])
        check(path, item)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", newline="") as stream:
            reader = csv.DictReader(stream)
            a, b = ("From", "To") if "From" in reader.fieldnames else ("from", "to")
            for row in reader:
                if row[a].encode() not in source_pins:
                    known.add((row[a] + "," + row[b]).encode())
    generated = BUILD / "u-role"
    generated.mkdir()
    request = generated / "requests.csv"
    with (proposal / "requests.csv").open("rb") as source, request.open("xb") as output:
        populations, sample, filtering = filter_stream(source, output, source_pins, known,
            frozen["source_ports"], frozen["target_ports"], ROWS)
    source_count, history_count = len(source_pins), len(known)
    del source_pins, known
    speed.measured([str(HIDDEN / "check_hidden_suite"), str(ARCH), str(HIDDEN / "reach.bin"),
        str(HIDDEN / "independent/eligibility.bin"), "U-role", str(ROWS), str(request),
        str(generated / "check")], "input-check")
    checked = read(generated / "check/check.json")
    assert checked["status"] == "passed" and checked["unique_rows"] == ROWS
    write(ROOT / "10m-input.json", dict(input=identity(request), rows=ROWS, unique_rows=ROWS,
        port_pairs=59904, proposal=identity(proposal / "requests.csv"), filtering=filtering,
        training_source_pins=source_count, historical_pairs_after_source_filter=history_count,
        source_pin_overlap=0, registered_history_overlap=0, history=frozen["history"],
        minimum_pair_rows=min(populations), maximum_pair_rows=max(populations),
        independent_checker=identity(generated / "check/check.json")))
    write(BUILD / "pair-populations.json", populations)
    (BUILD / "positions.txt").write_text("".join(f"{p}\n" for p, _, _ in sample))
    pairs = [(a, b) for _, a, b in sample]
    assert len(pairs) == len(set(pairs)) == SAMPLES
    sample_request = BUILD / "sample-requests.csv"
    with sample_request.open("x", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["From", "To"])
        writer.writerows(pairs)
    coverage = labels.full_coverage(pairs)
    assert coverage["minimum_port_pair_rows"] == coverage["maximum_port_pair_rows"] == 4
    write(ROOT / "input.json", dict(input=identity(sample_request), coverage=coverage,
        rows=SAMPLES, scope="Exact-label sample; complete estimator input is 10m-input.json."))
    flags, bands = [], {}
    for a, b in pairs:
        xy = [tuple(map(int, p.split("/", 1)[0][4:].split("_"))) for p in (a, b)]
        distance = sum(abs(x - y) for x, y in zip(*xy))
        band = next(v for v in (12, 24, 50, 100, 300, 1000) if distance <= v)
        flags.append(int(bands.get(band, 0) < 2))
        bands[band] = bands.get(band, 0) + 1
    assert len(bands) == 6 and sum(flags) == 12
    shards = []
    for shard in range(4):
        path = BUILD / f"labels-{shard}.csv"
        with path.open("x", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["kind", "from", "to", "label", "span_checked"])
            for i in range(shard, SAMPLES, 4):
                writer.writerow(["exp642-first4-per-pair", *pairs[i], -2, flags[i]])
        shards.append(dict(shard=shard, rows=SAMPLES // 4,
            span_checks=sum(flags[shard::4]), input=identity(path)))
    tools = BUILD / "tools"
    tools.mkdir()
    for name, source in (("exact_labels", "../../build/exp203/exact_labels"),
                         ("orbit.i16", "../../build/exp155/orbit.i16")):
        shutil.copy2(source, tools / name)
    write(ROOT / "label-freeze.json", dict(shards=shards, rows=SAMPLES, input=identity(sample_request),
        population_input=identity(request), positions=identity(BUILD / "positions.txt"),
        population=identity(BUILD / "pair-populations.json"),
        tools=[identity(tools / name) for name in ("exact_labels", "orbit.i16")],
        source_freeze=identity(ROOT / "freeze.json"), labels_generated_on="r9",
        scope="Four offline single-thread exact shards; no full-population accuracy claim."))
    print("EXP642_NEW_10M_PREPARED", len(sample), flush=True)


def compute_labels():
    sys.path.insert(0, str(Path("../exp624/validation").resolve()))
    import exp624_fresh_leaf_validation as fresh
    # The existing merge checks every sampled request, shard index and exact row.
    fresh.ROOT, fresh.BUILD, fresh.PLAN = ROOT, BUILD, PLAN
    labels.ROOT, labels.BUILD, labels.PLAN, labels.ROWS = ROOT, BUILD, PLAN, SAMPLES
    labels.TOOLS = BUILD / "tools"
    fresh.speed.ROOT = ROOT
    fresh.compute_labels()


def points(prediction, truth):
    assert np.all(truth >= 0)
    result = 100 * (1 - np.tanh(4 * np.abs(prediction - truth) / np.maximum(1, truth)))
    result[truth == 0] = 100 * (prediction[truth == 0] == 0)
    return result


def accuracy_interval(values, pair, family, population):
    counts = np.bincount(pair, minlength=len(population))
    assert np.all(counts == 4) and np.all(population >= counts)
    weights = population[pair] / counts[pair]
    mean = float(np.average(values, weights=weights))
    masses = np.bincount(family, weights=weights, minlength=26)
    totals = np.bincount(family, weights=weights * values, minlength=26)
    assert masses.min() > 0
    chosen = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    family_ci = np.quantile(totals[chosen].sum(axis=1) / masses[chosen].sum(axis=1),
                           [.0125, .9875]).tolist()
    centers = np.bincount(pair, weights=values, minlength=len(population)) / counts
    variances = np.bincount(pair, weights=(values - centers[pair]) ** 2,
                           minlength=len(population)) / (counts - 1)
    variance = np.sum((population / population.sum()) ** 2 *
                      (1 - counts / population) * variances / counts)
    half = float(stats.norm.ppf(.9875)) * math.sqrt(float(variance))
    design_ci = [mean - half, mean + half]
    return dict(point_pp=mean, family_ci975_pp=family_ci, stratified_ci975_pp=design_ci,
        conservative_ci975_pp=[min(family_ci[0], design_ci[0]), max(family_ci[1], design_ci[1])])


def joint(delta, lower, saved):
    assert len(saved) == 12 and np.isfinite(saved).all()
    mean = float(np.mean(saved))
    half = float(stats.t.ppf(.9875, 11)) * statistics.stdev(saved) / math.sqrt(12)
    point = .8 * delta + mean * (1e9 / ROWS) / 120
    bound = .8 * lower + (mean - half) * (1e9 / ROWS) / 120
    return dict(saved_cpu_s=mean, simultaneous_ci_saved_s=[mean-half, mean+half],
        score_extrapolated_1b=point, conservative_ci95_score_lower=bound,
        score_gate=bool(point >= .005 and bound > 0))


def sample_labels():
    frozen = read(ROOT / "label-freeze.json")
    report = read(ROOT / "report.json")
    assert report["all_complete_label_checks"] and report["rows"] == SAMPLES
    for item in (report["exact"], frozen["positions"], frozen["population"]):
        check(item["path"], item)
    positions = np.asarray([int(v) for v in (BUILD / "positions.txt").read_text().splitlines()])
    population = np.asarray(read(BUILD / "pair-populations.json"))
    assert len(positions) == SAMPLES and np.all(np.diff(positions) > 0) and positions[-1] < ROWS
    assert population.shape == (59904,) and population.sum() == ROWS
    sources, targets = labels.roles()
    si, ti = dict(zip(sources, range(208))), dict(zip(targets, range(288)))
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    families = dict(zip(mapping["sources"], [v[0] for v in mapping["source_coordinates"]]))
    requests, truth, pairs = [], [], []
    groups = {k: [] for k in ("source_family", "distance", "near_axis", "direction")}
    with (BUILD / "exact.csv").open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        for i, row in enumerate(reader):
            assert len(row) == 7 and row[0] == str(i)
            a, b = [pin.split("/", 1) for pin in row[1:3]]
            xy = [tuple(map(int, p[0][4:].split("_"))) for p in (a, b)]
            dx, dy = xy[1][0] - xy[0][0], xy[1][1] - xy[0][1]
            requests.append(tuple(row[1:3]))
            truth.append(int(row[3]))
            pairs.append(si[a[1]] * 288 + ti[b[1]])
            for key, value in dict(source_family=families[a[1]],
                distance=np.searchsorted([24, 100, 300], abs(dx) + abs(dy), side="right"),
                near_axis=abs(dx) < 20 or abs(dy) < 24,
                direction=2 * (dx < 0) + (dy < 0)).items():
                groups[key].append(value)
    assert len(requests) == SAMPLES and min(truth) >= 0
    pair = np.asarray(pairs, dtype="i4")
    assert np.all(np.bincount(pair, minlength=59904) == 4)
    return positions, requests, np.asarray(truth), pair, {
        k: np.asarray(v, dtype="i4") for k, v in groups.items()}, population


def qualify():
    frozen = freeze_check()
    data = read(ROOT / "10m-input.json")
    request = BUILD / "u-role/requests.csv"
    check(request, data["input"])
    check(CHECKER, frozen["checker"])
    for a, path in BINARIES.items():
        check(path, frozen["binaries"][a])
    positions, requests, truth, pair, groups, population = sample_labels()
    weights = population[pair] / 4
    schedule = [ARMS, *([ARMS, ARMS[::-1]] * 6)]
    write(ROOT / "timing-freeze.json", dict(schedule=schedule, input=data["input"],
        labels=identity(BUILD / "exact.csv"), binaries=frozen["binaries"], driver=identity(__file__),
        seed=SEED, bootstrap_count=9999, minimum_score=.005, rows=ROWS, sample_rows=SAMPLES,
        intervals="97.5% family bootstrap envelope with stratified SRS normal CI; 97.5% paired t CPU"))
    timing, predictions, evidence, runs, deleted = {a: [] for a in ARMS}, {}, {}, [], []
    for iteration, order in enumerate(schedule):
        for a in order:
            output = BUILD / f"fresh-{iteration}-{a}.csv"
            assert not output.exists()
            command = [str(BINARIES[a]), "-in", str(request), "-out", str(output)]
            run = speed.measured(command, output.stem)
            counters, actual = read(run["stderr"]), identity(output)
            assert counters == dict(rows=ROWS, unreachable=0, query_allocations=0)
            assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] <= 3600
            if iteration == 0:
                sample = BUILD / f"{a}-sample.csv"
                contract_run = speed.measured([str(CHECKER), "check", str(request), str(output),
                    str(ROWS), str(BUILD / "positions.txt"), str(sample)], a + "-contract")
                contract = read(ROOT / (a + "-contract.stdout"))
                assert contract["contract_passed"] and contract["rows"] == ROWS
                assert contract["sample_rows"] == SAMPLES
                values = []
                with sample.open(newline="") as stream:
                    reader = csv.reader(stream)
                    assert next(reader) == ["row", "From", "To", "delay"]
                    for i, row in enumerate(reader):
                        assert len(row) == 4 and int(row[0]) == positions[i]
                        assert tuple(row[1:3]) == requests[i] and row[3] == str(int(row[3]))
                        values.append(int(row[3]))
                assert len(values) == SAMPLES and min(values) >= 0
                predictions[a] = np.asarray(values)
                evidence[a] = dict(contract=contract, contract_run=contract_run, sample=identity(sample),
                    output=actual, run=run)
            assert actual["sha256"] == evidence[a]["output"]["sha256"]
            run.update(arm=a, iteration=iteration, input=data["input"], output=actual, counters=counters)
            write(ROOT / (output.stem + "-evidence.json"), run)
            runs.append(run)
            if iteration:
                timing[a].append(run["cpu_s"])
                deleted.append(dict(file=actual, identical_to=evidence[a]["output"], rebuild_command=command))
                print("EXP642_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
                output.unlink()
            print("EXP642_TIMING", iteration, a, run["cpu_s"], flush=True)
    started, cpu = time.monotonic(), time.process_time()
    scores = {a: points(predictions[a], truth) for a in ARMS}
    delta = scores["S8"] - scores["A"]
    interval = accuracy_interval(delta, pair, groups["source_family"], population)
    comparison = joint(interval["point_pp"], interval["conservative_ci975_pp"][0],
                       np.asarray(timing["A"]) - timing["S8"])
    errors = {a: np.abs(predictions[a] - truth) for a in ARMS}
    summary = {a: dict(accuracy=accuracy_interval(scores[a], pair, groups["source_family"], population),
        mae_ps=float(np.average(errors[a], weights=weights)),
        exact_fraction=float(np.average(errors[a] == 0, weights=weights))) for a in ARMS}
    partitions = {key: {str(int(v)): dict(sample_rows=int((values == v).sum()),
        estimated_population_rows=float(weights[values == v].sum()),
        delta_accuracy_pp=float(np.average(delta[values == v], weights=weights[values == v])),
        accuracy_pp={a: float(np.average(scores[a][values == v], weights=weights[values == v]))
                     for a in ARMS}) for v in np.unique(values)} for key, values in groups.items()}
    quality = bool(interval["point_pp"] >= -.05 and interval["conservative_ci975_pp"][0] >= -.08 and all(
        g["delta_accuracy_pp"] >= -.15 for key, values in partitions.items()
        if key in ("distance", "near_axis") for g in values.values()))
    comparison.update(delta_accuracy_pp=interval["point_pp"], accuracy_interval=interval,
        quality_gate=quality, joint_gate=quality and comparison["score_gate"], groups=partitions,
        summary=summary, changed_sample_rows=int(np.count_nonzero(predictions["A"] != predictions["S8"])),
        improved_sample_rows=int(np.count_nonzero(errors["S8"] < errors["A"])),
        worse_sample_rows=int(np.count_nonzero(errors["S8"] > errors["A"])))
    write(ROOT / "evaluation.json", dict(comparison=comparison, evidence=evidence, timing=timing,
        runs=runs, rows=ROWS, unique_rows=ROWS, sample_rows=SAMPLES, port_pairs=59904,
        source_pin_overlap=0, heldout_used_for_selection=False, full_population_scored=False,
        cpu_1b_is_extrapolation=True, final_accuracy_goal_verified=False,
        zero_truth_sample_rows=int(np.count_nonzero(truth == 0)),
        group_geometry="original endpoint coordinate differences; same convention as exp580/620",
        scoring_cpu_s=time.process_time()-cpu, scoring_wall_s=time.monotonic()-started,
        deleted_duplicates=deleted, released_bytes=sum(r["file"]["bytes"] for r in deleted),
        disk_free_end=shutil.disk_usage(".").free))
    print("EXP642_10M_RESULT", comparison["delta_accuracy_pp"], comparison["saved_cpu_s"],
          comparison["joint_gate"], flush=True)


def self_check():
    lines = [b"SRB_0_0/S,SRB_1_0/T\n", b"SRB_0_1/S,SRB_1_1/T\n"]
    lines += [f"SRB_2_{i}/S,SRB_3_{i}/T\n".encode() for i in range(8)]
    output = io.BytesIO()
    population, selected, rejected = filter_stream(io.BytesIO(b"From,To\n" + b"".join(lines)),
        output, {b"SRB_0_0/S"}, {lines[1][:-1]}, ["S"], ["T"], 8)
    assert population == [8] and [v[0] for v in selected] == list(range(4))
    assert output.getvalue() == b"From,To\n" + b"".join(lines[2:])
    assert rejected == dict(visited_proposal_rows=10, rejected_source_rows=1, rejected_history_rows=1)
    assert joint(0., 0., np.full(12, .02))["score_gate"]
    assert not joint(0., 0., np.zeros(12))["score_gate"]
    assert np.array_equal(points(np.array([0, 1, 100]), np.array([0, 0, 100])), [100, 0, 100])
    pair = np.repeat(np.arange(26), 4)
    interval = accuracy_interval(np.full(104, .25), pair, pair, np.full(26, 400))
    assert all(abs(v - .25) < 1e-12 for v in interval["conservative_ci975_pp"])
    interval = accuracy_interval(np.tile([-1., 1., -1., 1.], 26), pair, pair, np.full(26, 400))
    assert interval["family_ci975_pp"] == [0., 0.]
    assert interval["conservative_ci975_pp"][0] < 0 < interval["conservative_ci975_pp"][1]
    print("EXP642_SELF_CHECK_PASSED", flush=True)


if __name__ == "__main__":
    assert len(sys.argv) == 2 and sys.argv[1] in ("self-check", "prepare", "dataset", "labels", "qualify")
    if sys.argv[1] != "self-check":
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp642")
    {"self-check": self_check, "prepare": prepare, "dataset": dataset,
     "labels": compute_labels, "qualify": qualify}[sys.argv[1]]()
