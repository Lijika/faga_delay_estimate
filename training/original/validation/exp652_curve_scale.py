#!/usr/bin/env python3
"""Compare frozen D64 distance curves and S8 on a fresh complete 100M."""
import csv
import gzip
import math
import os
from pathlib import Path
import resource
import shutil
import socket
import statistics
import subprocess
import sys
import time

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path("../exp642/validation").resolve()))
import exp642_fresh_symmetric as fresh
import exp652_curve_cli as cli

ROOT, BUILD, PLAN = cli.ROOT, cli.BUILD, cli.PLAN
ROWS, SAMPLES, SEED, PAIRS = 100_000_000, 239_616, 20261024652, 6
ARMS, BINARIES = ("A", "C"), {"A": cli.BASELINE, "C": BUILD / "C"}
read, write, identity, check = cli.read, cli.write, cli.identity, cli.check
speed, labels, HIDDEN, CHECKER = fresh.speed, fresh.labels, fresh.HIDDEN, fresh.CHECKER
speed.ROOT = ROOT
fresh.ROOT, fresh.BUILD, fresh.PLAN = ROOT, BUILD, PLAN
fresh.ROWS, fresh.SEED = ROWS, SEED
labels.ROOT, labels.BUILD, labels.PLAN, labels.ROWS = ROOT, BUILD, PLAN, SAMPLES
labels.TOOLS = BUILD / "tools"


def joint(delta, lower, saved):
    assert len(saved) == PAIRS and np.isfinite(saved).all()
    mean = float(np.mean(saved))
    half = float(stats.t.ppf(.9875, PAIRS - 1)) * statistics.stdev(saved) / math.sqrt(PAIRS)
    point = .8 * delta + mean * 10 / 120
    bound = .8 * lower + (mean - half) * 10 / 120
    return dict(saved_cpu_s=mean, ci975_saved_cpu_s=[mean - half, mean + half],
        score_extrapolated_1b=point, conservative_ci95_score_lower=bound,
        score_gate=bool(point >= .005 and bound > 0))


def self_check():
    assert joint(.1, .09, np.full(PAIRS, -.5))["score_gate"]
    assert not joint(.1, .09, np.full(PAIRS, -1.))["score_gate"]
    assert abs(joint(.1, .09, np.zeros(PAIRS))["score_extrapolated_1b"] - .08) < 1e-12
    print("EXP652_SELF_CHECK_PASSED", flush=True)


def prepare():
    self_check()
    frozen = cli.freeze_check()
    assert read(ROOT / "numeric-audit.json")["final_prediction_equal"]
    assert not (ROOT / "freeze.json").exists()
    history = [Path("../exp588/build/exp588/known-local.csv.gz"),
        Path("../exp501/build/exp501/u-role/requests.csv"),
        Path("../exp562/build/exp562/u-role/requests.csv"),
        Path("../exp588/build/exp588/u-role/requests.csv"),
        Path("../exp624/build/exp624/u-role/requests.csv"),
        Path("../exp642/build/exp642/u-role/requests.csv"),
        Path("../exp580/build/exp580/scale-exact.csv"),
        Path("../exp643/build/exp643/S8-sample.csv"),
        Path("../exp644/build/exp644/1b-sample.csv"),
        Path("../exp649/build/exp649/sample-requests.csv")]
    tools = read("../exp501/validation/results/exp501/freeze.json")["expected_tools"]
    for tool in tools:
        check(Path("../..") / tool["path"], tool)
    for tool in (HIDDEN / "make_hidden_suite", HIDDEN / "check_hidden_suite",
                 Path("../../build/exp203/exact_labels"), CHECKER):
        result = subprocess.run([str(tool), "--help"], capture_output=True, text=True)
        text = result.stdout + result.stderr
        assert "usage" in text.lower(), (tool, result.returncode)
        (ROOT / (tool.name + "-help.txt")).write_text(text)
    files = [Path(__file__), Path(fresh.__file__), Path(labels.__file__), PLAN,
        ROOT / "protocol-original.md", ROOT / "build-freeze.json", ROOT / "numeric-audit.json",
        Path("../exp624/validation/exp624_fresh_leaf_validation.py"),
        Path("../exp575/offline/validation/results/exp575/mapping.json"),
        HIDDEN / "reach.bin", HIDDEN / "independent/eligibility.bin",
        *Path("doc/eda比赛文件/arch").glob("*.json")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files],
        binaries=frozen["binaries"], checker=identity(CHECKER), rows=ROWS,
        sample_rows=SAMPLES, proposal_rows=120_000_000, proposal_seed=20261025652,
        shuffle_seed=20261026652, expected_tools=tools,
        history=[identity(p) for p in history], source_ports=labels.roles()[0],
        target_ports=labels.roles()[1], required_port_pairs=59904,
        sample_rule="first four per port pair after independent global shuffle and filtering",
        schedule=[ARMS, *([ARMS, ARMS[::-1]] * (PAIRS // 2))], seed=SEED,
        untouched_scores=True, cpu_label_budget_s=5000,
        disk_free_start_bytes=shutil.disk_usage(".").free))
    assert shutil.disk_usage(".").free > 22_000_000_000
    print("EXP652_FRESH_100M_FROZEN", flush=True)


def dataset():
    frozen = fresh.freeze_check()
    proposal = BUILD / "proposal"
    speed.measured([str(HIDDEN / "make_hidden_suite"), str(fresh.ARCH), str(HIDDEN / "reach.bin"),
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
        population, sample, filtering = fresh.filter_stream(source, output, source_pins, known,
            frozen["source_ports"], frozen["target_ports"], ROWS)
    source_count, history_count = len(source_pins), len(known)
    del source_pins, known
    speed.measured([str(HIDDEN / "check_hidden_suite"), str(fresh.ARCH), str(HIDDEN / "reach.bin"),
        str(HIDDEN / "independent/eligibility.bin"), "U-role", str(ROWS), str(request),
        str(generated / "check")], "input-check")
    checked = read(generated / "check/check.json")
    assert checked["status"] == "passed" and checked["unique_rows"] == ROWS
    write(ROOT / "100m-input.json", dict(input=identity(request), rows=ROWS, unique_rows=ROWS,
        port_pairs=59904, proposal=identity(proposal / "requests.csv"), filtering=filtering,
        training_source_pins=source_count, historical_pairs_after_source_filter=history_count,
        source_pin_overlap=0, registered_history_overlap=0, history=frozen["history"],
        minimum_pair_rows=min(population), maximum_pair_rows=max(population),
        independent_checker=identity(generated / "check/check.json")))
    write(BUILD / "pair-populations.json", population)
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
        rows=SAMPLES, scope="Exact sample of the frozen complete 100M population in 100m-input.json."))
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
                writer.writerow(["exp652-first4-per-pair", *pairs[i], -2, flags[i]])
        shards.append(dict(shard=shard, rows=SAMPLES // 4,
            span_checks=sum(flags[shard::4]), input=identity(path)))
    tools = BUILD / "tools"
    tools.mkdir()
    for name, source in (("exact_labels", "../../build/exp203/exact_labels"),
                         ("orbit.i16", "../../build/exp155/orbit.i16")):
        shutil.copy2(source, tools / name)
    write(ROOT / "label-freeze.json", dict(shards=shards, rows=SAMPLES,
        input=identity(sample_request), population_input=identity(request),
        positions=identity(BUILD / "positions.txt"), population=identity(BUILD / "pair-populations.json"),
        tools=[identity(tools / name) for name in ("exact_labels", "orbit.i16")],
        source_freeze=identity(ROOT / "freeze.json"), labels_generated_on="r9",
        scope="Four offline single-thread exact shards; full-population accuracy remains unverified."))
    print("EXP652_NEW_100M_PREPARED", len(sample), flush=True)


def compute_labels():
    # Reuse exp624's shard runner directly, avoiding its unrelated training imports.
    frozen = read(ROOT / "label-freeze.json")
    labels.freeze_check()
    for item in frozen["tools"] + [s["input"] for s in frozen["shards"]]:
        check(item["path"], item)
    children = []
    for shard in range(4):
        name = f"labels-{shard}"
        out = (ROOT / (name + ".stdout")).open("xb")
        err = (ROOT / (name + ".stderr")).open("xb")
        command = [str(labels.TOOLS / "exact_labels"), str(labels.ARCH),
            str(BUILD / (name + ".csv")), str(labels.TOOLS / "orbit.i16"),
            str(BUILD / f"exact-{shard}.csv")]
        child = subprocess.Popen(command, stdout=out, stderr=err)
        children.append(dict(child=child, shard=shard, command=command,
            out=out, err=err, started=time.monotonic(), threads=0))
    write(ROOT / "label-pids.json", dict(pids=[dict(pid=c["child"].pid, shard=c["shard"],
        command=c["command"]) for c in children], hard_timeout_wall_s=2400))
    results = []
    while children:
        for item in children[:]:
            child = item["child"]
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if not pid:
                item["threads"] = max(item["threads"], len(list(Path(f"/proc/{child.pid}/task").iterdir())))
                assert time.monotonic() - item["started"] <= 2400, "offline label wall budget"
                continue
            child.returncode = os.waitstatus_to_exitcode(status)
            item["out"].close()
            item["err"].close()
            run = dict(command=item["command"], exit_code=child.returncode, threads=item["threads"],
                cpu_s=usage.ru_utime + usage.ru_stime, rss_bytes=usage.ru_maxrss * 1024,
                wall_s=time.monotonic() - item["started"], host=socket.gethostname())
            write(ROOT / f"labels-{item['shard']}.run.json", run)
            assert run["exit_code"] == 0 and run["threads"] == 1
            results.append((item["shard"], run))
            children.remove(item)
            print("EXP652_LABEL_SHARD_COMPLETE", item["shard"], run["cpu_s"], flush=True)
        time.sleep(.25)
    results.sort()
    assert sum(r["cpu_s"] for _, r in results) <= 5000
    write(ROOT / "label-computation.json", dict(all_exited_zero=True, runs=[r for _, r in results],
        host=socket.gethostname(), outputs=[identity(BUILD / f"exact-{i}.csv") for i in range(4)]))
    labels.verify()


def qualify():
    frozen = fresh.freeze_check()
    population_input = read(ROOT / "100m-input.json")
    request = BUILD / "u-role/requests.csv"
    check(request, population_input["input"])
    check(CHECKER, frozen["checker"])
    cli.freeze_check()
    positions, requests, truth, pair, groups, population = fresh.sample_labels()
    weights = population[pair] / 4
    write(ROOT / "timing-freeze.json", dict(schedule=frozen["schedule"], input=population_input["input"],
        labels=identity(BUILD / "exact.csv"), binaries=frozen["binaries"], driver=identity(__file__),
        seed=SEED, bootstrap_count=9999, minimum_score=.005, minimum_accuracy_pp=.02,
        rows=ROWS, sample_rows=SAMPLES))
    timing, predictions, evidence, runs, deleted = {a: [] for a in ARMS}, {}, {}, [], []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            command = [str(BINARIES[arm]), "-in", str(request), "-out", str(output)]
            run = speed.measured(command, output.stem)
            actual, counters = identity(output), read(run["stderr"])
            assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] < 100 and run["wall_s"] <= 3600
            assert counters == dict(rows=ROWS, unreachable=0, query_allocations=0)
            if iteration == 0:
                sample = BUILD / f"{arm}-sample.csv"
                contract_run = speed.measured([str(CHECKER), "check", str(request),
                    str(output), str(ROWS), str(BUILD / "positions.txt"), str(sample)], arm + "-contract")
                contract = read(ROOT / (arm + "-contract.stdout"))
                assert contract["contract_passed"] and contract["rows"] == ROWS
                assert contract["sample_rows"] == len(truth) == SAMPLES
                values = []
                with sample.open(newline="") as stream:
                    reader = csv.reader(stream)
                    assert next(reader) == ["row", "From", "To", "delay"]
                    for i, row in enumerate(reader):
                        assert len(row) == 4 and int(row[0]) == positions[i]
                        assert tuple(row[1:3]) == requests[i] and row[3] == str(int(row[3]))
                        values.append(int(row[3]))
                assert len(values) == SAMPLES and min(values) >= 0
                predictions[arm] = np.asarray(values)
                evidence[arm] = dict(output=actual, sample=identity(sample), run=run,
                    contract=contract, contract_run=contract_run)
            assert all(actual[k] == evidence[arm]["output"][k] for k in ("bytes", "sha256"))
            run.update(arm=arm, iteration=iteration, output=actual,
                input=population_input["input"], counters=counters)
            write(ROOT / (output.stem + "-evidence.json"), run)
            runs.append(run)
            if iteration:
                timing[arm].append(run["cpu_s"])
                deleted.append(dict(file=actual, identical_to=evidence[arm]["output"], rebuild_command=command))
                print("EXP652_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
                output.unlink()
            print("EXP652_TIMING", iteration, arm, run["cpu_s"], flush=True)
    started, cpu = time.monotonic(), time.process_time()
    scores = {a: fresh.points(predictions[a], truth) for a in ARMS}
    delta = scores["C"] - scores["A"]
    interval = fresh.accuracy_interval(delta, pair, groups["source_family"], population)
    comparison = joint(interval["point_pp"], interval["conservative_ci975_pp"][0],
        np.asarray(timing["A"]) - timing["C"])
    partitions = {key: {str(int(v)): dict(sample_rows=int((values == v).sum()),
        estimated_population_rows=float(weights[values == v].sum()),
        delta_accuracy_pp=float(np.average(delta[values == v], weights=weights[values == v])),
        accuracy_pp={a: float(np.average(scores[a][values == v], weights=weights[values == v]))
                     for a in ARMS}) for v in np.unique(values)} for key, values in groups.items()}
    quality = bool(interval["point_pp"] >= .02 and interval["conservative_ci975_pp"][0] > 0 and all(
        g["delta_accuracy_pp"] >= -.03 for key, values in partitions.items()
        if key in ("distance", "near_axis", "direction", "forced") for g in values.values()))
    errors = {a: np.abs(predictions[a] - truth) for a in ARMS}
    comparison.update(delta_accuracy_pp=interval["point_pp"], accuracy_interval=interval,
        quality_gate=quality, joint_gate=quality and comparison["score_gate"], groups=partitions,
        changed_sample_rows=int(np.count_nonzero(predictions["A"] != predictions["C"])),
        improved_sample_rows=int(np.count_nonzero(errors["C"] < errors["A"])),
        worse_sample_rows=int(np.count_nonzero(errors["C"] > errors["A"])))
    summary = {a: dict(accuracy=fresh.accuracy_interval(scores[a], pair, groups["source_family"], population),
        mae_ps=float(np.average(errors[a], weights=weights)),
        exact_fraction=float(np.average(errors[a] == 0, weights=weights))) for a in ARMS}
    write(ROOT / "100m-report.json", dict(comparison=comparison, summary=summary, timing=timing,
        runs=runs, evidence=evidence, rows=ROWS, unique_rows=ROWS, port_pairs=59904,
        sample_rows=SAMPLES, source_pin_overlap=0, registered_history_overlap=0,
        heldout_used_for_selection=False, full_population_scored=False, cpu_1b_is_extrapolation=True,
        final_accuracy_goal_verified=False, zero_truth_sample_rows=int(np.count_nonzero(truth == 0)),
        scoring_cpu_s=time.process_time() - cpu, scoring_wall_s=time.monotonic() - started,
        deleted_duplicates=deleted, released_bytes=sum(v["file"]["bytes"] for v in deleted),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP652_100M_RESULT", comparison["delta_accuracy_pp"], comparison["saved_cpu_s"],
          comparison["joint_gate"], flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp652")
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert len(sys.argv) == 2 and sys.argv[1] in ("self-check", "prepare", "dataset", "labels", "qualify")
    {"self-check": self_check, "prepare": prepare, "dataset": dataset,
     "labels": compute_labels, "qualify": qualify}[sys.argv[1]]()
