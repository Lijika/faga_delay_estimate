#!/usr/bin/env python3
"""Validate conditional geometry and cross-fit residuals on the full-port r9 set."""
import gc
import inspect
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

import exp500_evaluate as quantization
import exp554_real_kernel_function as trees
import exp556_xgb_residual as previous
import exp549_complementarity as grouping
import exp535_real_map as real
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp557"), Path("build/exp557")
OFFLINE = Path("offline")
SOURCE = OFFLINE / ROOT
PLAN = Path("experiment/实验557-XGBoost条件几何空间与完整候选.md")
ROWS, LEFT, RIGHT, SEED = 1000000, 59904, 264960, 20261021557
read = real.read


def run(command, name):
    started = time.monotonic()
    with (ROOT / (name + ".stdout")).open("xb") as out, (ROOT / (name + ".stderr")).open("xb") as err:
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
            time.sleep(.01)
    record = dict(command=command, exit_code=os.waitstatus_to_exitcode(status), threads=threads,
                  cpu_s=usage.ru_utime + usage.ru_stime, wall_s=time.monotonic() - started,
                  rss_bytes=usage.ru_maxrss * 1024, production_timing=False)
    write(ROOT / (name + ".run.json"), record)
    assert record["exit_code"] == 0 and threads == 1, record
    assert not (ROOT / (name + ".stderr")).read_bytes()
    return record


def compile_decoders():
    help_text = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in help_text
    (ROOT / "compiler-help.txt").write_text(help_text)
    records = []
    for source, name in (("tests/exp557_geometry_decode.cpp", "geometry-decode"),
                         ("tests/exp554_real_kernel_function.cpp", "tree-decode")):
        command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64", "-mtune=generic",
                   "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", source,
                   "-o", str(BUILD / name)]
        built = subprocess.run(command, capture_output=True, text=True)
        record = dict(command=command, exit_code=built.returncode, stdout=built.stdout, stderr=built.stderr)
        records.append(record)
        write(ROOT / (name + "-compiler.json"), record)
        assert built.returncode == 0 and not built.stderr, record
        helped = subprocess.run([str(BUILD / name), "--help"], capture_output=True, text=True)
        assert helped.returncode == 0 and helped.stdout.startswith("usage:")
    write(ROOT / "compiler.json", dict(version=subprocess.check_output(["g++", "--version"], text=True),
                                        builds=records))


def json_leaves(tree, features):
    left, right = np.asarray(tree["left_children"]), np.asarray(tree["right_children"])
    split = np.asarray(tree["split_indices"])
    threshold = np.asarray(tree["split_conditions"], dtype="<f4")
    at = np.zeros(len(features), dtype=np.int32)
    for _ in range(3):
        rows = np.flatnonzero(left[at] >= 0)
        if not len(rows):
            break
        nodes = at[rows]
        at[rows] = np.where(features[rows, split[nodes]] < threshold[nodes], left[nodes], right[nodes])
    assert np.all(left[at] == -1)
    return at


def router(training):
    record = read(SOURCE / "router.json")
    for asset in record["assets"]:
        real.check(OFFLINE / asset["path"], asset)
    path = OFFLINE / "build/exp557/router.json"
    model = read(path)["learner"]["gradient_booster"]["model"]["trees"]
    assert len(model) == 1 and not model[0]["categories"] and not any(model[0]["split_type"])
    features = np.load(OFFLINE / "build/exp557/router-features.npy")
    stored = np.load(OFFLINE / "build/exp557/router-native-leaf.npy")
    regions = np.load(OFFLINE / "build/exp557/T-regions.npy")
    booster = xgb.Booster(); booster.load_model(path)
    native = booster.predict(xgb.DMatrix(features, nthread=4), pred_leaf=True).reshape(-1).astype("<i4")
    independent = json_leaves(model[0], features)
    assert np.array_equal(stored, native) and np.array_equal(native, independent)
    assert np.array_equal(regions, np.searchsorted(np.unique(native), native))
    boundary = []
    tree = model[0]
    for node, left in enumerate(tree["left_children"]):
        if left < 0:
            continue
        feature = tree["split_indices"][node]
        threshold = np.float32(tree["split_conditions"][node])
        for value in (np.nextafter(threshold, np.float32(-np.inf)), threshold,
                      np.nextafter(threshold, np.float32(np.inf))):
            candidate = features[0].copy(); candidate[feature] = value; boundary.append(candidate)
    boundary = np.asarray(boundary, dtype="<f4")
    native_boundary = booster.predict(xgb.DMatrix(boundary, nthread=4), pred_leaf=True).reshape(-1)
    assert np.array_equal(native_boundary, json_leaves(tree, boundary))
    write(ROOT / "router-check.json", dict(keys=RIGHT, leaves=record["leaves"], boundary_rows=len(boundary),
          complete_json_native_table_equality=True, source=identity(SOURCE / "router.json"),
          training=identity(training)))


def geometry(name, center, pair, column, scale, trend, zero, cycle, event, mandatory):
    model = read(SOURCE / (name + "-model.json"))
    assets = model["assets"][:]
    if name == "T":
        assets.append(next(a for a in read(SOURCE / "router.json")["assets"]
                           if a["path"].endswith("T-regions.npy")))
    for asset in assets:
        real.check(OFFLINE / asset["path"], asset)
    rank, regions = model["rank"], model["regions"]
    left = np.load(OFFLINE / BUILD / (name + "-left.npy"))
    right = np.load(OFFLINE / BUILD / (name + "-right.npy"))
    group = np.load(OFFLINE / BUILD / (name + "-regions.npy"))
    assert left.shape == (regions, LEFT, rank) and right.shape == (RIGHT, rank)
    assert group.shape == (RIGHT,) and group.dtype == np.dtype("u1") and group.max() < regions
    quantization.RANK = rank
    le, li, lf = quantization.quantize(left.reshape(regions * LEFT, rank))
    re, ri, rf = quantization.quantize(right)
    exponent = le.astype(np.int64) + re
    minimum = int(exponent.min())
    lm = np.abs(li.astype(np.int32)).max(axis=0)
    rm = np.abs(ri.astype(np.int32)).max(axis=0)
    bound = sum((int(a) * int(b)) << int(e - minimum) for a, b, e in zip(lm, rm, exponent))
    normal = minimum >= -1022 and bound.bit_length() + minimum <= 1024
    certificate = dict(integer_absolute_sum_bound=bound, common_exponent=minimum,
                       maximum_component_exponent=int(exponent.max()), normal_scaling=normal,
                       float64_reassociation_certified=bool(bound <= 2**53 and normal))
    path = BUILD / (name + "-geometry.bin")
    with path.open("xb") as stream:
        stream.write(b"EX557Q01" + struct.pack("<4I", LEFT, RIGHT, regions, rank) + bytes(40))
        for value in (center, group, le, li, re, ri):
            stream.write(value.tobytes())
    expected_bytes = 64 + 2 * LEFT + RIGHT + 8 * rank + 2 * (regions * LEFT + RIGHT) * rank
    assert path.stat().st_size == expected_bytes
    with path.open("rb") as stream:
        assert stream.read(64) == b"EX557Q01" + struct.pack("<4I", LEFT, RIGHT, regions, rank) + bytes(40)
        for value in (center, group, le, li, re, ri):
            assert stream.read(value.nbytes) == value.tobytes()
        assert not stream.read(1)
    rows = group[column].astype(np.int64) * LEFT + pair
    response = np.zeros(ROWS, dtype=np.float64)
    for k in range(rank):
        response += lf[rows, k].astype(np.float64) * rf[column, k].astype(np.float64)
    output = BUILD / (name + "-geometry.f64")
    record = run([str(BUILD / "geometry-decode"), str(path), str(BUILD / "keys.i32"), str(output)],
                 name + "-geometry")
    independent = np.fromfile(output, "<f8")
    assert independent.shape == (ROWS,) and np.array_equal(response.view("u8"), independent.view("u8"))
    value = response * scale + center[pair] + trend
    nominal = np.maximum(0, np.copysign(np.floor(np.abs(value) + .5), value).astype(np.int64))
    nominal[zero] = cycle[pair[zero] // 288]
    base = nominal + event[:, 4] + event[:, 6] - mandatory
    assert np.array_equal(base, nominal + event[:, 4] - event[:, 7])
    base.astype("<i4").tofile(BUILD / (name + "-base.i32"))
    record.update(model=identity(path), output=identity(output), bitwise_equal=True, rank=rank,
                  regions=regions, base=identity(BUILD / (name + "-base.i32")),
                  exact_accumulation=certificate)
    write(ROOT / (name + "-geometry.json"), record)
    return base


def train(name, base, matrix, folds, labels, rounds, depth=8, eta=.1):
    truth, d0, mandatory = labels[:, :3].T
    weights = (1000 / np.maximum(d0 + mandatory, 128)).astype("<f4")
    params = dict(objective="reg:absoluteerror", tree_method="hist", max_depth=depth, eta=eta,
                  max_bin=256, base_score=0, subsample=1., colsample_bytree=1.,
                  seed=previous.SEED, nthread=4)
    raw = np.empty(ROWS, dtype="<f4")
    records = []
    for k in range(3):
        started, cpu = time.monotonic(), time.process_time()
        learn, test = folds != k, folds == k
        dm = xgb.DMatrix(matrix[learn], label=(d0 - base)[learn].astype("<f4"),
                         weight=weights[learn], nthread=4)
        dt = xgb.DMatrix(matrix[test], nthread=4)
        booster = xgb.train(params, dm, num_boost_round=rounds)
        assets = trees.export_model(booster, f"{name}-{k}")
        restored = xgb.Booster(); restored.load_model(BUILD / f"{name}-{k}.json")
        native, back = booster.predict(dt), restored.predict(dt)
        assert np.isfinite(native).all() and np.array_equal(native.view("u4"), back.view("u4"))
        raw[test] = native
        train_pred = trees.decode(booster.predict(dm), base[learn], mandatory[learn])
        record = dict(fold=k, params=params, rounds=rounds, features=matrix.shape[1], assets=assets,
              train=real.statistics(train_pred, truth[learn]), cpu_s=time.process_time() - cpu,
              wall_s=time.monotonic() - started, full_port=True)
        records.append(record); write(ROOT / f"{name}-{k}.json", record)
        print("EXP557_TRAINED", name, k, flush=True)
        del dm, dt, booster, restored
        gc.collect()
    raw.tofile(BUILD / (name + ".f32"))
    feature_path = BUILD / ("features54.f32" if matrix.shape[1] == 54 else "features.f32")
    output = BUILD / (name + "-independent.f32")
    command = [str(BUILD / "tree-decode"), str(feature_path), str(BUILD / "folds.u8")]
    command += [str(BUILD / f"{name}-{k}.bin") for k in range(3)] + [str(output)]
    decoded = run(command, name + "-independent")
    independent = np.fromfile(output, "<f4")
    assert independent.shape == (ROWS,) and np.array_equal(raw.view("u4"), independent.view("u4"))
    pred = trees.decode(raw, base, mandatory)
    pred.astype("<i4").tofile(BUILD / (name + ".i32"))
    write(ROOT / (name + ".json"), dict(name=name, records=records, statistics=real.statistics(pred, truth),
          decoder=decoded, raw=identity(BUILD / (name + ".f32")), predictions=identity(BUILD / (name + ".i32")),
          complete_bitwise_equal=True))
    print("EXP557_RESULT", name, real.statistics(pred, truth)["accuracy_pp"], flush=True)
    return pred


def report(predictions, cluster, truth, query, event, ports):
    score = {n: real.points(p, truth) for n, p in predictions.items()}
    pairs = [(n, "exp354") for n in predictions if n[0] in "GFT" and "base" not in n]
    pairs += [("F32", "G32"), ("T32", "F32")]
    family = query[:, 4].astype(np.int32)
    counts = np.bincount(family)
    assert len(counts) == 26 and np.all(counts > 0)
    sums = np.column_stack([np.bincount(family, weights=score[a] - score[b]) for a, b in pairs])
    rng, boot = np.random.default_rng(SEED), np.empty((2000, len(pairs)))
    for i in range(len(boot)):
        sample = rng.integers(len(counts), size=len(counts))
        boot[i] = sums[sample].sum(axis=0) / counts[sample].sum()
    interval = np.quantile(boot, [.025, .975], axis=0)
    paired = {a + "-" + b: dict(delta_pp=float((score[a] - score[b]).mean()),
              ci95_pp=interval[:, i].tolist(), changed_rows=int(np.count_nonzero(predictions[a] != predictions[b])),
              better_rows=int(np.count_nonzero(score[a] > score[b])),
              worse_rows=int(np.count_nonzero(score[a] < score[b])), source_family_clusters=len(counts))
              for i, (a, b) in enumerate(pairs)}
    statistics = {n: real.statistics(p, truth) for n, p in predictions.items()}
    gates = {a: bool(statistics[a]["accuracy_pp"] >= 99.1 and paired[a + "-exp354"]["delta_pp"] >= .05 and
                     paired[a + "-exp354"]["ci95_pp"][0] > 0) for a, b in pairs if b == "exp354"}
    partition = grouping.partition(query, event)
    nx = query[:, 2] - event[:, 0] + event[:, 2]
    ny = query[:, 3] - event[:, 1] + event[:, 3]
    partition.update(source_port=ports[:, 0], target_port=ports[:, 1],
                     nominal_direction=2 * (nx < 0) + (ny < 0))
    grouped = {family: {str(int(v)): {n: real.statistics(p[values == v], truth[values == v])
               for n, p in predictions.items()} for v in np.unique(values)} for family, values in partition.items()}
    write(ROOT / "groups.json", grouped)
    write(ROOT / "report.json", dict(rows=ROWS, port_pairs=LEFT, statistics=statistics, paired=paired,
          quality_gates=gates, all_full_port=True, complete_geometry_equality=True,
          complete_residual_equality=True, development_only=True, final_elf_verified=False,
          production_cpu_verified=False, single_call_100ns_verified=False))


def features(path, matrix):
    with path.open("xb") as stream:
        stream.write(b"E554F001" + struct.pack("<II", ROWS, matrix.shape[1]))
        stream.write(matrix.astype("<f4").tobytes())


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp557")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (12000, 12000))
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    trained = read(SOURCE / "training.json")
    assert trained["all_training_checks"] and trained["values"] == LEFT * RIGHT
    real.check(OFFLINE / trained["freeze"]["path"], trained["freeze"])
    real.check(OFFLINE / trained["center"]["path"], trained["center"])
    (ROOT / "installed-xgboost-help.txt").write_text(str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__)
    compile_decoders(); router(SOURCE / "training.json")
    previous.ROOT, trees.BUILD = ROOT, BUILD
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = previous.data()
    assert matrix.shape == (ROWS, 53)
    features(BUILD / "features.f32", matrix); folds.tofile(BUILD / "folds.u8")
    center = np.load(OFFLINE / trained["center"]["path"])
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    x, y = query[:, 2] - event[:, 0] + event[:, 2], query[:, 3] - event[:, 1] + event[:, 3]
    ax, ay = np.abs(x), np.abs(y)
    assert np.all(ax <= 119) and np.all(ay <= 549)
    pair = ports[:, 0] * 288 + ports[:, 1]
    column = (((((2 * (x < 0) + (y < 0)) * 10 + ax % 10) * 12 + ay % 12) * 12 + ax // 10) * 46 + ay // 12)
    np.column_stack((pair, column)).astype("<i4").tofile(BUILD / "keys.i32")
    scale = 128 + 125 * (ax // 10) + 125 * (ay // 12)
    trend = 125 * (ax // 10) + np.where(y < 0, 125, 127) * (ay // 12)
    zero = (x == 0) & (y == 0) & (query[:, 8] == query[:, 9]) & (query[:, 4] < 20)
    cycles = read("../exp536/validation/results/exp536/oracle.json")
    assert cycles["complete"] and len(cycles["sources"]) == 208
    cycle = np.asarray([r["cycle_ps"] for r in cycles["sources"]])
    frozen = [Path(__file__), Path("tests/exp557_geometry_decode.cpp"), PLAN, SOURCE / "training.json",
              ROOT / "router-check.json", ROOT / "input.json"]
    baseline = Path("../exp556/build/exp556/R-32.i32")
    old = read("../exp556/validation/results/exp556/report.json")
    assert old["complete_generic_equality"] and old["development_only"]
    predictions = {"exp354": production, "Q-base": oracle,
                   "old-R32": np.fromfile(baseline, "<i4").astype(np.int64)}
    names = read("../exp554/validation/results/exp554/report.json")["prediction_names"]
    predictions["Q128"] = prior[:, names.index("capacity_Q")]
    assert predictions["old-R32"].shape == (ROWS,)
    assert abs(real.statistics(predictions["old-R32"], labels[:, 0])["accuracy_pp"] -
               old["statistics"]["R-32"]["accuracy_pp"]) < 1e-10
    frozen += [baseline, Path("../exp556/validation/results/exp556/report.json"),
               Path("tests/exp554_real_kernel_function.cpp")]
    frozen += [Path("validation") / (name + ".py") for name in
               ("exp500_evaluate", "exp500_split_residues", "exp504_tail_rectangles",
                "exp554_real_kernel_function", "exp556_xgb_residual", "exp549_complementarity",
                "exp535_real_map", "exp208_nominal_parent_tree")]
    write(ROOT / "evaluation-freeze.json", dict(files=[identity(p) for p in frozen], seed=SEED,
          port_pairs=LEFT, full_port_required=True, disk_free_start=free))
    bases = {}
    for name in ("G", "F", "T"):
        base = geometry(name, center, pair, column, scale, trend, zero, cycle, event, labels[:, 2])
        bases[name] = base; predictions[name + "-base"] = base + labels[:, 2]
        predictions[name + "32"] = train(name + "32", base, matrix, folds, labels, 32)
    best = max(bases, key=lambda n: real.statistics(predictions[n + "32"], labels[:, 0])["accuracy_pp"])
    best_score = real.statistics(predictions[best + "32"], labels[:, 0])["accuracy_pp"]
    if best_score >= 98.5:
        name = best + "128"
        predictions[name] = train(name, bases[best], matrix, folds, labels, 128)
        best_score = max(best_score, real.statistics(predictions[name], labels[:, 0])["accuracy_pp"])
    if best_score >= 99.1:
        extra = np.column_stack((matrix, bases[best])).astype("<f4")
        features(BUILD / "features54.f32", extra)
        for suffix, rounds, eta in (("tiny8", 8, .3), ("tiny16", 16, .2)):
            name = best + suffix
            predictions[name] = train(name, bases[best], extra, folds, labels, rounds, 4, eta)
    report(predictions, cluster, labels[:, 0], query, event, ports)
    assets = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert assets <= 2_000_000_000
    write(ROOT / "cost.json", dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, new_asset_bytes=assets,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free, freed_bytes=0, deleted_files=[]))
    print("EXP557_COMPLETE_FULL_PORT_EVALUATION", flush=True)


if __name__ == "__main__":
    main()
