#!/usr/bin/env python3
"""Controlled full-port XGBoost residual learning on the certified r9 development set."""
import gc
import hashlib
import inspect
import io
import json
import lzma
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import time

import numpy as np
import xgboost as xgb

import exp554_real_kernel_function as previous
import exp535_real_map as real
import exp549_complementarity as groups
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp556"), Path("build/exp556")
PLAN = Path("experiment/实验556-XGBoost物理趋势与双通道残差的受控学习.md")
ROWS, RANK, SEED = 1_000_000, 96, 20261020554
OLD = Path("../exp554")
read = real.read


def checked(path, expected):
    return real.check(path, expected)


def data():
    report = read(OLD / "validation/results/exp554/report.json")
    assert report["all_checks_passed"] and report["all_full_port"]
    records = []
    for key in ("labels", "predictions"):
        records.append(checked(OLD / report[key]["path"], report[key]))
    labels = np.fromfile(OLD / report["labels"]["path"], "<i4").reshape(ROWS, 4).astype(np.int64)
    frozen = read(OLD / "validation/results/exp554/input.json")
    records.append(checked(OLD / frozen["queries"]["path"], frozen["queries"]))
    query = np.fromfile(OLD / frozen["queries"]["path"], "<i4", offset=12).reshape(ROWS, 10)
    split = read(OLD / "validation/results/exp554/split.json")
    for row in split["assets"]:
        records.append(checked(OLD / row["path"], row))
    folds = np.fromfile(OLD / "build/exp554/folds.u8", "u1")
    cluster = np.fromfile(OLD / "build/exp554/clusters.i32", "<i4")
    ports = np.fromfile(OLD / "build/exp554/ports.i32", "<i4").reshape(ROWS, 2)
    definition = read(OLD / "validation/results/exp554/features.json")
    records.append(checked(OLD / definition["asset"]["path"], definition["asset"]))
    matrix = np.fromfile(OLD / definition["asset"]["path"], "<f4", offset=16).reshape(ROWS, -1)
    assert matrix.shape[1] == len(definition["names"])
    prior = np.fromfile(OLD / report["predictions"]["path"], "<i4").reshape(ROWS, -1)
    oracle = prior[:, report["prediction_names"].index("O")].astype(np.int64)
    production = prior[:, report["prediction_names"].index("exp354")].astype(np.int64)
    event_path = Path("../exp536/build/exp536/events.i32")
    expected = next(r for r in read(OLD / "validation/results/exp554/freeze.json")["files"]
                    if r["path"] == str(event_path))
    records.append(checked(event_path, expected))
    event = np.fromfile(event_path, "<i4").reshape(ROWS, 9).astype(np.int64)
    pair = ports[:, 0] * 288 + ports[:, 1]
    partitions = []
    for k in range(3):
        test, full, half = folds == k, folds != k, folds == (k + 1) % 3
        for name, mask in (("test", test), ("full", full), ("half", half)):
            counts = np.bincount(pair[mask], minlength=59904)
            assert len(counts) == 59904 and counts.min() > 0
            partitions.append(dict(fold=k, name=name, rows=int(mask.sum()), pairs=59904,
                                   minimum=int(counts.min()), maximum=int(counts.max())))
        assert not np.intersect1d(cluster[test], cluster[full]).size
    assert np.all(labels[:, 0] > 0) and np.array_equal(labels[:, 1] + labels[:, 2], prior[:, 0])
    write(ROOT / "input.json", dict(records=records, partitions=partitions,
          unique_rows=frozen["unique_rows"], pairs=59904, cluster_disjoint=True,
          development_only=True, source_names=definition["names"]))
    return labels, query, ports, event, matrix, folds, cluster, oracle, production, prior


def physical(query, ports, event, oracle, mandatory):
    folder = Path("../exp510")
    meta = read(folder / "validation/results/exp510/r96-model.json")
    asset = checked(folder / meta["asset"]["path"], meta["asset"])
    raw = lzma.decompress((folder / meta["asset"]["path"]).read_bytes())
    assert len(raw) == meta["raw_bytes"] and hashlib.sha256(raw).hexdigest() == meta["raw_sha256"]
    assert raw[:20] == b"EX510Q01" + struct.pack("<3I", 59904, 264960, RANK)
    (BUILD / "trend.bin").write_bytes(raw)
    stream = io.BytesIO(raw[20:])
    sides = []
    for n in (59904, 264960):
        exponent = np.frombuffer(stream.read(4 * RANK), "<i4")
        integer = np.frombuffer(stream.read(2 * n * RANK), "<i2").reshape(n, RANK)
        sides.append(np.ldexp(integer.astype(np.float64), exponent))
    assert not stream.read(1)
    del raw
    left, right = sides
    x = query[:, 2] - event[:, 0] + event[:, 2]
    y = query[:, 3] - event[:, 1] + event[:, 3]
    ax, ay = np.abs(x), np.abs(y)
    assert np.all(ax <= 119) and np.all(ay <= 549)
    column = (((((2 * (x < 0) + (y < 0)) * 10 + ax % 10) * 12 + ay % 12) * 12 +
               ax // 10) * 46 + ay // 12).astype(np.int32)
    pair = ports[:, 0] * 288 + ports[:, 1]
    keys = np.column_stack((pair, column)).astype("<i4")
    keys.tofile(BUILD / "trend-keys.i32")
    response = np.zeros(ROWS, dtype=np.float64)
    contributions = np.empty((ROWS, 8), dtype=np.float64)
    for k in range(RANK):
        value = left[pair, k] * right[column, k]
        response += value
        if k < 8:
            contributions[:, k] = value
    response.tofile(BUILD / "trend-python.f64")
    command = [str(BUILD / "trend-decode"), str(BUILD / "trend.bin"),
               str(BUILD / "trend-keys.i32"), str(BUILD / "trend-cpp.f64")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0 and not result.stderr, result.stderr
    restored = np.fromfile(BUILD / "trend-cpp.f64", "<f8")
    assert np.array_equal(response.view("u8"), restored.view("u8"))
    scale = 128 + 125 * (ax // 10) + 125 * (ay // 12)
    periodic = 125 * (ax // 10) + np.where(y < 0, 125, 127) * (ay // 12)
    nominal = previous.decode(response * scale, periodic, np.zeros(ROWS, dtype=np.int64))
    cycles = read("../exp536/validation/results/exp536/oracle.json")
    cycle = np.asarray([r["cycle_ps"] for r in cycles["sources"]])
    assert cycles["complete"] and len(cycle) == 208
    zero = (x == 0) & (y == 0) & (query[:, 8] == query[:, 9]) & (query[:, 4] < 20)
    nominal[zero] = cycle[ports[zero, 0]]
    base = nominal + event[:, 4] + event[:, 6] - mandatory
    assert np.array_equal(event[:, 4] + event[:, 6] - mandatory, event[:, 4] - event[:, 7])
    extra = dict(nominal_rx=ax % 10, nominal_ry=ay % 12, nominal_qx=ax // 10,
                 nominal_qy=ay // 12, nominal_sign=2 * (x < 0) + (y < 0),
                 axis_ratio=(ax // 10) / (1 + ax // 10 + ay // 12),
                 small_axis=np.minimum(ax / 10, ay / 12), response_base=base)
    for k in range(8):
        extra[f"port_factor_{k}"] = left[pair, k]
        extra[f"geometry_factor_{k}"] = right[column, k]
        extra[f"response_factor_{k}"] = contributions[:, k] * scale
    extra = np.column_stack(list(extra.values())).astype("<f4"), list(extra)
    write(ROOT / "trend.json", dict(asset=asset, raw_bytes=meta["raw_bytes"],
          keys=identity(BUILD / "trend-keys.i32"), output=identity(BUILD / "trend-cpp.f64"),
          complete_bitwise_equal=True, rows=ROWS, positive_cycle_rows=int(zero.sum()),
          physical=real.statistics(base + mandatory, oracle), extra_names=extra[1],
          source_cycle_metadata=identity("../exp536/validation/results/exp536/oracle.json")))
    return base, extra


def compile_decoders():
    commands = []
    for source, name in ((Path("tests/exp556_trend_decode.cpp"), "trend-decode"),):
        command = ["g++", "-std=c++17", "-O3", "-static", "-fno-fast-math", "-ffp-contract=off",
                   "-Wall", "-Wextra", str(source), "-o", str(BUILD / name)]
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0 and not result.stderr, result.stderr
        commands.append(command)
    source = Path("tests/exp554_real_kernel_function.cpp").read_text()
    old = "trees <= 128 && count <= 128 * 511"
    assert source.count(old) == 1
    source = source.replace(old, "trees <= 512 && count <= 512 * 2047")
    (BUILD / "tree-decode.cpp").write_text(source)
    command = ["g++", "-std=c++17", "-O3", "-static", "-fno-fast-math", "-ffp-contract=off",
               "-Wall", "-Wextra", str(BUILD / "tree-decode.cpp"), "-o", str(BUILD / "tree-decode")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0 and not result.stderr, result.stderr
    commands.append(command)
    write(ROOT / "compiler.json", dict(commands=commands,
          version=subprocess.check_output(["g++", "--version"], text=True),
          binaries=[identity(BUILD / n) for n in ("tree-decode", "trend-decode")]))


def train(name, offset, matrix, width, folds, labels, cluster, production, old_raw,
          params_change=None, half=False, weighting="original"):
    truth, d0, mandatory = labels[:, :3].T
    params = dict(objective="reg:absoluteerror", tree_method="hist", max_depth=8,
                  eta=.1, max_bin=256, base_score=0, subsample=1., colsample_bytree=1.,
                  seed=SEED, nthread=4)
    params.update(params_change or {})
    weights = 1000 / np.maximum(truth if weighting == "score" else d0 + mandatory, 128)
    raw = {r: np.empty(ROWS, dtype="<f4") for r in (32, 128, 512)}
    pair = np.fromfile(OLD / "build/exp554/ports.i32", "<i4").reshape(ROWS, 2)
    pair = pair[:, 0] * 288 + pair[:, 1]
    records = []
    for k in range(3):
        test = folds == k
        learn = folds == (k + 1) % 3 if half else folds != k
        assert np.bincount(pair[learn], minlength=59904).min() > 0
        w = weights[learn].copy()
        if weighting == "pair":
            counts = np.bincount(pair[learn], minlength=59904)
            w /= counts[pair[learn]]
            w *= weights[learn].sum() / w.sum()
        w = w.astype("<f4")
        started, cpu = time.monotonic(), time.process_time()
        dm = xgb.DMatrix(matrix[learn, :width], label=(d0 - offset)[learn].astype("<f4"),
                         weight=w, nthread=4)
        dt = xgb.DMatrix(matrix[test, :width], nthread=4)
        booster = xgb.train(params, dm, num_boost_round=512)
        assets = previous.export_model(booster, f"{name}-{k}")
        restored = xgb.Booster()
        restored.load_model(BUILD / f"{name}-{k}.json")
        training = {}
        for rounds in raw:
            predicted = booster.predict(dt, iteration_range=(0, rounds))
            back = restored.predict(dt, iteration_range=(0, rounds))
            assert np.array_equal(predicted.view("u4"), back.view("u4"))
            assert np.isfinite(predicted).all()
            raw[rounds][test] = predicted
            train_raw = booster.predict(dm, iteration_range=(0, rounds))
            fitted = previous.decode(train_raw, offset[learn], mandatory[learn])
            training[str(rounds)] = dict(real=real.statistics(fitted, truth[learn]),
                  kernel=real.statistics(fitted - mandatory[learn], d0[learn]))
        record = dict(name=name, fold=k, full_port=True, train_rows=int(learn.sum()),
                      test_rows=int(test.sum()), params=params, weighting=weighting,
                      width=width, assets=assets, training=training,
                      cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started)
        records.append(record)
        write(ROOT / f"{name}-{k}.json", record)
        print("EXP556_TRAINED", name, k, record["cpu_s"], flush=True)
        del dm, dt, booster, restored
        gc.collect()
    if name == "J":
        assert np.array_equal(raw[128].view("u4"), old_raw.view("u4")), "J128 differs from exp554"
    result = dict(name=name, records=records, checkpoints={})
    for rounds, value in raw.items():
        value.tofile(BUILD / f"{name}-{rounds}.f32")
        pred = previous.decode(value, offset, mandatory)
        pred.astype("<i4").tofile(BUILD / f"{name}-{rounds}.i32")
        result["checkpoints"][str(rounds)] = dict(
            real=real.statistics(pred, truth), kernel=real.statistics(pred - mandatory, d0),
            training_accuracy_pp=sum(r["training"][str(rounds)]["real"]["accuracy_pp"] * r["train_rows"]
                                     for r in records) / sum(r["train_rows"] for r in records))
    command = [str(BUILD / "tree-decode"), str(BUILD / "features.f32"), str(BUILD / "folds.u8")]
    command += [str(BUILD / f"{name}-{k}.bin") for k in range(3)] + [str(BUILD / f"{name}-cpp.f32")]
    started = time.monotonic()
    with (ROOT / f"{name}.stdout").open("xb") as out, (ROOT / f"{name}.stderr").open("xb") as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        threads = 0
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            try:
                threads = max(threads, len(list(Path(f"/proc/{child.pid}/task").iterdir())))
            except FileNotFoundError:
                pass
            time.sleep(.05)
        child.returncode = os.waitstatus_to_exitcode(status)
    assert child.returncode == 0 and threads == 1
    assert not (ROOT / f"{name}.stderr").read_bytes()
    generic = np.fromfile(BUILD / f"{name}-cpp.f32", "<f4")
    assert np.array_equal(generic.view("u4"), raw[512].view("u4"))
    result["decoder"] = dict(cpu_s=usage.ru_utime + usage.ru_stime,
          wall_s=time.monotonic() - started, rss_bytes=usage.ru_maxrss * 1024, threads=threads,
          bitwise_equal=True, output=identity(BUILD / f"{name}-cpp.f32"), production_timing=False)
    result["model_bytes_max"] = max(r["assets"]["binary"]["bytes"] for r in records)
    write(ROOT / f"{name}.json", result)
    print("EXP556_COMPLETE", name, result["checkpoints"]["512"]["real"]["accuracy_pp"], flush=True)
    return result


def finish(results, labels, bases, cluster, query, event, ports, production):
    truth, d0, mandatory = labels[:, :3].T
    predictions = {"L": d0 + mandatory, "exp354": production}
    for name, base in bases.items():
        predictions[name + "-base"] = base + mandatory
    for result in results:
        for rounds in (32, 128, 512):
            name = result["name"] + f"-{rounds}"
            predictions[name] = np.fromfile(BUILD / f"{name}.i32", "<i4").astype(np.int64)
    scores = {name: real.points(pred, truth) for name, pred in predictions.items()}
    pairings = [(r["name"] + "-512", "exp354") for r in results]
    pairings += [(r["name"] + "-512", "E-512") for r in results if r["name"] not in ("J", "R", "E")]
    pairings += [("R-512", "J-512"), ("E-512", "R-512")]
    pairings += [(name + "-512", name + "-128") for name in ("J", "R", "E")]
    counts = np.bincount(cluster)
    delta = np.column_stack([scores[a] - scores[b] for a, b in pairings])
    sums = np.column_stack([np.bincount(cluster, weights=delta[:, i]) for i in range(len(pairings))])
    rng = np.random.default_rng(SEED)
    boot = np.empty((2000, len(pairings)))
    for i in range(len(boot)):
        sample = rng.integers(len(counts), size=len(counts))
        boot[i] = sums[sample].sum(axis=0) / counts[sample].sum()
    interval = np.quantile(boot, [.025, .975], axis=0)
    paired = {}
    for i, (a, b) in enumerate(pairings):
        paired[a + "-" + b] = dict(delta_pp=float(delta[:, i].mean()), ci95_pp=interval[:, i].tolist(),
              better_rows=int(np.sum(scores[a] > scores[b])), worse_rows=int(np.sum(scores[a] < scores[b])),
              changed_rows=int(np.sum(predictions[a] != predictions[b])), source_pin_clusters=len(counts))
    partition = groups.partition(query, event)
    partition.update(source_port=ports[:, 0], target_port=ports[:, 1])
    grouped = {}
    for family, values in partition.items():
        grouped[family] = {str(int(v)): {n: real.statistics(p[values == v], truth[values == v])
                                       for n, p in predictions.items()}
                           for v in np.unique(values)}
    write(ROOT / "groups.json", grouped)
    stats = {n: real.statistics(p, truth) for n, p in predictions.items()}
    gates = {}
    for r in results:
        key = r["name"] + "-512"
        comparison = paired[key + "-exp354"]
        gates[r["name"]] = bool(r["name"] != "Q" and stats[key]["accuracy_pp"] >= 99.10 and
              comparison["delta_pp"] >= .05 and comparison["ci95_pp"][0] > 0)
    write(ROOT / "report.json", dict(rows=ROWS, source_ports=208, target_ports=288, port_pairs=59904,
          results=results, statistics=stats, paired=paired, quality_gates=gates,
          complete_generic_equality=True, complete_trend_equality=True,
          development_only=True, final_elf_verified=False, production_cpu_verified=False))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp556")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (28800, 28800))
    resource.setrlimit(resource.RLIMIT_AS, (32 << 30, 32 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    (ROOT / "installed-xgboost-help.txt").write_text(
        str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__ + "\n" +
        str(inspect.signature(xgb.DMatrix)) + "\n" + xgb.DMatrix.__doc__)
    compile_decoders()
    labels, query, ports, event, matrix, folds, cluster, oracle, production, old_predictions = data()
    rbase, (extra, names) = physical(query, ports, event, oracle, labels[:, 2])
    width = matrix.shape[1]
    matrix = np.column_stack((matrix, extra)).astype("<f4")
    assert np.isfinite(matrix).all() and matrix.shape[1] <= 128
    with (BUILD / "features.f32").open("xb") as stream:
        stream.write(b"E554F001" + struct.pack("<II", ROWS, matrix.shape[1]))
        stream.write(matrix.tobytes())
    folds.tofile(BUILD / "folds.u8")
    write(ROOT / "features.json", dict(columns=matrix.shape[1], previous_columns=width,
          extra_names=names, output=identity(BUILD / "features.f32")))
    files = [Path(__file__), PLAN, Path("tests/exp556_trend_decode.cpp"),
             Path("tests/exp554_real_kernel_function.cpp"), ROOT / "input.json", ROOT / "trend.json"]
    files += [Path("validation") / (n + ".py") for n in
              ("exp554_real_kernel_function", "exp535_real_map", "exp549_complementarity", "exp208_nominal_parent_tree")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files], seed=SEED,
          xgboost=xgb.__version__, rounds=512, disk_free_start=free, all_full_port=True))
    previous.BUILD = BUILD
    checked(OLD / "build/exp554/native.f32", read(OLD / "validation/results/exp554/training.json")["native"])
    native = np.fromfile(OLD / "build/exp554/native.f32", "<f4").reshape(ROWS, 6)[:, 4]
    bases = dict(J=labels[:, 3], R=rbase, Q=oracle - labels[:, 2])
    results = []
    for name in ("J", "R", "E"):
        base = bases["J" if name == "J" else "R"]
        result = train(name, base, matrix, width if name != "E" else matrix.shape[1], folds,
                       labels, cluster, production, native)
        results.append(result)
    rscore = real.statistics(rbase + labels[:, 2], labels[:, 0])["accuracy_pp"]
    best = max(r["checkpoints"]["512"]["real"]["accuracy_pp"] for r in results[1:])
    proceed = best >= 98.5 and best - rscore >= .2
    write(ROOT / "expansion-gate.json", dict(best_accuracy_pp=best, base_accuracy_pp=rscore,
                                             passed=proceed))
    if proceed:
        variants = [
            ("bins", dict(max_bin=1024), False, "original"),
            ("square", dict(objective="reg:squarederror"), False, "original"),
            ("huber", dict(objective="reg:pseudohubererror", huber_slope=16.), False, "original"),
            ("depth", dict(max_depth=10), False, "original"),
            ("approx", dict(tree_method="approx"), False, "original"),
            ("score", {}, False, "score"),
            ("pair", {}, False, "pair"),
            ("half", {}, True, "original"),
            ("regular", dict(min_child_weight=8, subsample=.8, colsample_bytree=.9), False, "original"),
            ("Q", {}, False, "original"),
        ]
        for name, params, half, weighting in variants:
            result = train(name, bases["Q" if name == "Q" else "R"], matrix, matrix.shape[1],
                           folds, labels, cluster, production, native, params, half, weighting)
            results.append(result)
    finish(results, labels, bases, cluster, query, event, ports, production)
    assets = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert assets <= 4_000_000_000
    write(ROOT / "cost.json", dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, new_asset_bytes=assets,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free, deleted_files=[],
          freed_bytes=0, production_runs=0))
    print("EXP556_FULL_PORT_CONTROLLED_RESIDUAL_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
