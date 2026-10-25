#!/usr/bin/env python3
"""Validate frozen leaf calibration on new full-port source-pin-disjoint requests."""
import csv
import gzip
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp623/validation").resolve()))
import exp623_leaf_calibration as prior
sys.path.insert(0, str(Path("../exp501/validation").resolve()))
import exp501_fresh_full_labels as labels

ROOT, BUILD = Path("validation/results/exp624"), Path("build/exp624")
PLAN = Path("experiment/实验624-冻结叶校准的源端隔离新1M.md")
read, write, identity, check = prior.read, prior.write, prior.identity, prior.check
speed = prior.speed
speed.ROOT = ROOT
labels.ROOT, labels.BUILD, labels.PLAN = ROOT, BUILD, PLAN
labels.TOOLS, labels.REFERENCE = BUILD / "tools", Path("../..")
ROWS, SEED = 1000000, 20261023624
BINARIES = {"A": Path("../exp622/build/exp622/T"), "C": Path("../exp623/build/exp623/C")}


def prepare():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    frozen = read("../exp623/validation/results/exp623/build-freeze.json")
    assert read("../exp623/validation/results/exp623/complete-check.json")["final_prediction_exact"]
    for arm, path in BINARIES.items():
        check(path, frozen["binaries"][arm])
    tools = read("../exp501/validation/results/exp501/freeze.json")["expected_tools"]
    for tool in tools:
        check(Path("../..") / tool["path"], tool)
    history = [Path("../exp588/build/exp588/known-local.csv.gz"),
        Path("../exp501/build/exp501/u-role/requests.csv"),
        Path("../exp562/build/exp562/u-role/requests.csv"),
        Path("../exp588/build/exp588/u-role/requests.csv"),
        Path("../exp580/build/exp580/scale-exact.csv")]
    for tool in ("build/hidden-suite-v1/make_hidden_suite", "build/hidden-suite-v1/check_hidden_suite",
                 "build/exp203/exact_labels"):
        command = [str(Path("../..") / tool), "--help"]
        result = subprocess.run(command, capture_output=True, text=True)
        output = result.stdout + result.stderr
        assert "usage" in output.lower(), (tool, result.returncode, output[:200])
        (ROOT / (Path(tool).name + "-help.txt")).write_text(output)
    write(ROOT / "freeze.json", dict(
        files=[identity(PLAN), identity(ROOT / "protocol-original.md"), identity(__file__)],
        rows=ROWS, proposal_rows=1200000, proposal_seed=20261024624, shuffle_seed=20261025624,
        binaries={a: identity(p) for a, p in BINARIES.items()}, expected_tools=tools,
        history=[identity(p) for p in history], required_port_pairs=59904,
        source_ports=labels.roles()[0], target_ports=labels.roles()[1],
        untouched_scores=True, cpu_label_budget_s=5000,
        disk_free_start=shutil.disk_usage(".").free))
    print("EXP624_FROZEN", flush=True)


def dataset():
    frozen = labels.freeze_check()
    hidden = Path("../../build/hidden-suite-v1")
    proposal = BUILD / "proposal"
    speed.measured([str(hidden / "make_hidden_suite"), str(labels.ARCH), str(hidden / "reach.bin"),
        "U-role", str(frozen["proposal_rows"]), str(frozen["proposal_seed"]),
        str(frozen["shuffle_seed"]), str(proposal)], "generate-proposal")
    training = Path("../exp501/build/exp501/u-role/requests.csv")
    with training.open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        source_pins = {row[0] for row in reader}
    with (proposal / "requests.csv").open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        candidates = [tuple(row) for row in reader if row[0] not in source_pins]
    eligible, excluded = set(candidates), set()
    assert len(eligible) == len(candidates)
    history = []
    for item in frozen["history"]:
        path = Path(item["path"])
        check(path, item)
        opener = gzip.open if path.suffix == ".gz" else open
        count = hits = 0
        with opener(path, "rt", newline="") as stream:
            reader = csv.DictReader(stream)
            names = reader.fieldnames
            a, b = ("From", "To") if "From" in names else ("from", "to")
            for row in reader:
                key = row[a], row[b]
                if key in eligible:
                    excluded.add(key)
                    hits += 1
                count += 1
        history.append(dict(file=item, rows=count, proposal_matches=hits))
    pairs = [p for p in candidates if p not in excluded][:ROWS]
    assert len(pairs) == ROWS and len(set(pairs)) == ROWS
    assert not ({p[0] for p in pairs} & source_pins)
    generated = BUILD / "u-role"
    generated.mkdir()
    request = generated / "requests.csv"
    with request.open("x", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["From", "To"])
        writer.writerows(pairs)
    complete = labels.full_coverage(pairs)
    speed.measured([str(hidden / "check_hidden_suite"), str(labels.ARCH), str(hidden / "reach.bin"),
        str(hidden / "independent/eligibility.bin"), "U-role", str(ROWS), str(request),
        str(generated / "check")], "input-check")
    checked = read(generated / "check/check.json")
    assert checked["status"] == "passed" and checked["unique_rows"] == ROWS
    write(ROOT / "input.json", dict(input=identity(request), rows=ROWS, unique_rows=ROWS,
        proposal=identity(proposal / "requests.csv"), source_disjoint_proposals=len(candidates),
        excluded_prior_requests=len(excluded), prior_exact_overlap=0, source_pin_overlap=0,
        training_source_pins=len(source_pins), coverage=complete, history=history,
        independent_checker=identity(generated / "check/check.json"),
        scope="new source pins relative to exp501; same architecture and complete port pairs"))
    flags, bands = [], {}
    for a, b in pairs:
        coords = [tuple(map(int, p.split("/", 1)[0][4:].split("_"))) for p in (a, b)]
        distance = sum(abs(x - y) for x, y in zip(*coords))
        band = next(v for v in (0, 12, 24, 50, 100, 1000) if distance <= v)
        flags.append(int(bands.get(band, 0) < 2))
        bands[band] = bands.get(band, 0) + 1
    assert len(bands) == 6 and sum(flags) == 12
    shards = []
    for shard in range(4):
        path = BUILD / f"labels-{shard}.csv"
        with path.open("x", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["kind", "from", "to", "label", "span_checked"])
            for i in range(shard, ROWS, 4):
                writer.writerow(["fresh-full-role", *pairs[i], -2, flags[i]])
        shards.append(dict(shard=shard, rows=ROWS // 4,
            span_checks=sum(flags[shard::4]), input=identity(path)))
    labels.TOOLS.mkdir()
    for name, source in (("exact_labels", "../../build/exp203/exact_labels"),
                         ("orbit.i16", "../../build/exp155/orbit.i16")):
        shutil.copyfile(source, labels.TOOLS / name)
    (labels.TOOLS / "exact_labels").chmod(0o755)
    write(ROOT / "label-freeze.json", dict(shards=shards, rows=ROWS, input=identity(request),
        tools=[identity(labels.TOOLS / name) for name in ("exact_labels", "orbit.i16")],
        source_freeze=identity(ROOT / "freeze.json"), labels_generated_on="r9",
        scope="four offline single-thread exact computations; estimator timing occurs afterwards"))
    print("EXP624_NEW_1M_PREPARED", flush=True)


def compute_labels():
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
            print("EXP624_LABEL_SHARD_COMPLETE", item["shard"], run["cpu_s"], flush=True)
        time.sleep(.25)
    results.sort()
    assert sum(r["cpu_s"] for _, r in results) <= 5000
    write(ROOT / "label-computation.json", dict(all_exited_zero=True, runs=[r for _, r in results],
        host=socket.gethostname(), outputs=[identity(BUILD / f"exact-{i}.csv") for i in range(4)]))
    labels.verify()


def qualify():
    frozen = labels.freeze_check()
    assert read(ROOT / "report.json")["all_complete_label_checks"]
    for a, path in BINARIES.items():
        check(path, frozen["binaries"][a])
    request, exact = BUILD / "u-role/requests.csv", BUILD / "exact.csv"
    schedule = [("A", "C"), *([("A", "C"), ("C", "A")] * 6)]
    write(ROOT / "timing-freeze.json", dict(schedule=schedule, input=identity(request),
        labels=identity(exact), binaries=frozen["binaries"], driver=identity(__file__),
        bootstrap_count=9999, seed=SEED, accuracy_min_pp=.005, score_min=.002))
    timing, predictions, evidence, runs, deleted = {a: [] for a in BINARIES}, {}, {}, [], []
    for iteration, order in enumerate(schedule):
        for arm in order:
            output = BUILD / f"fresh-{iteration}-{arm}.csv"
            command = [str(BINARIES[arm]), "-in", str(request), "-out", str(output)]
            run = speed.measured(command, output.stem)
            counters = read(run["stderr"])
            assert counters == dict(rows=ROWS, unreachable=0, query_allocations=0)
            assert run["threads"] == 1 and run["rss_bytes"] <= 2000000000 and run["cpu_s"] <= 3600
            actual = identity(output)
            if not iteration:
                p, truth, record, partitions = prior.old.prior.complete.check_output(request, output, exact)
                predictions[arm], evidence[arm] = p, dict(record, output=actual)
            assert actual["sha256"] == evidence[arm]["output"]["sha256"]
            run.update(arm=arm, iteration=iteration, input=identity(request), output=actual, counters=counters)
            write(ROOT / (output.stem + "-evidence.json"), run)
            runs.append(run)
            if iteration:
                timing[arm].append(run["cpu_s"])
                deleted.append(dict(file=actual, identical_to=evidence[arm]["output"], rebuild_command=command))
                print("EXP624_CLEANUP", str(output), actual["sha256"], flush=True)
                output.unlink()
            print("EXP624_RUN", iteration, arm, run["cpu_s"], flush=True)
    result = prior.transition(predictions["C"], predictions["A"], truth, partitions)
    delta = prior.points(predictions["C"], truth) - prior.points(predictions["A"], truth)
    family = partitions["source_family"]
    counts, sums = np.bincount(family, minlength=26), np.bincount(family, weights=delta, minlength=26)
    rng = np.random.default_rng(SEED)
    chosen = rng.integers(26, size=(9999, 26))
    accuracy = sums[chosen].sum(axis=1) / counts[chosen].sum(axis=1)
    extra = np.asarray(timing["C"]) - timing["A"]
    cpu = extra[rng.integers(12, size=(9999, 12))].mean(axis=1)
    joint = .8 * accuracy - 1000 * cpu / 120
    point = .8 * result["delta_accuracy_pp"] - 1000 * extra.mean() / 120
    quality = bool(result["delta_accuracy_pp"] >= .005 and np.quantile(accuracy, .025) > 0 and all(
        g["delta_accuracy_pp"] >= -.03 for k, groups in result["groups"].items()
        if k in ("distance", "near_axis") for g in groups.values()))
    result.update(ci95_delta_accuracy_pp=np.quantile(accuracy, [.025, .975]).tolist(),
        extra_cpu_s=float(extra.mean()), ci95_extra_cpu_s=np.quantile(cpu, [.025, .975]).tolist(),
        score_extrapolated_1b=float(point), ci95_score_extrapolated_1b=np.quantile(joint, [.025, .975]).tolist(),
        quality_gate=quality, joint_gate=bool(quality and point >= .002 and np.quantile(joint, .025) > 0))
    write(ROOT / "evaluation.json", dict(comparison=result, evidence=evidence, timing=timing, runs=runs,
        rows=ROWS, unique_rows=ROWS, source_pin_overlap=0, heldout_used_for_selection=False,
        cpu_1b_is_extrapolation=True, final_accuracy_goal_verified=False,
        deleted_duplicates=deleted, released_bytes=sum(r["file"]["bytes"] for r in deleted),
        disk_free_end=shutil.disk_usage(".").free))
    print("EXP624_RESULT", result["delta_accuracy_pp"], result["extra_cpu_s"], result["joint_gate"], flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp624")
    assert len(sys.argv) == 2 and sys.argv[1] in ("prepare", "dataset", "labels", "qualify")
    {"prepare": prepare, "dataset": dataset, "labels": compute_labels, "qualify": qualify}[sys.argv[1]]()
