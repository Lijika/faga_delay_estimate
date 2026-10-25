#!/usr/bin/env python3
"""Cross-fit compact functions of the full-port real no-Line distance on r9."""
import gc
import json
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

import exp535_real_map as real
import exp549_complementarity as prior
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp554"), Path("build/exp554")
PLAN = Path("experiment/实验554-真实无Line距离核的紧凑联合函数.md")
ROWS, SEED, DRAWS = 1_000_000, 20261020554, 2000
BUDGETS = dict(small=(4, 32), capacity=(8, 128))
ARMS = tuple(f"{budget}_{arm}" for budget in BUDGETS for arm in ("T", "J", "Q"))
read = real.read


def split(indices, cluster):
    sizes = np.bincount(cluster)
    rng = np.random.default_rng(SEED)
    assignment = rng.integers(3, size=len(sizes), dtype=np.uint8)
    pair = indices[:, 0] * 288 + indices[:, 1]
    rows_by_pair = np.argsort(pair, kind="stable")
    pair_start = np.r_[0, np.cumsum(np.bincount(pair, minlength=59904))]
    rows_by_cluster = np.argsort(cluster, kind="stable")
    cluster_start = np.r_[0, np.cumsum(sizes)]
    counts = np.bincount(pair * 3 + assignment[cluster], minlength=59904 * 3).reshape(59904, 3)
    repairs = []
    for p, fold in zip(*np.where(counts == 0)):
        if counts[p, fold]:
            continue
        candidates = np.unique(cluster[rows_by_pair[pair_start[p]:pair_start[p + 1]]])
        candidates = sorted(candidates.tolist(), key=lambda c: (sizes[c], c))
        for c in candidates:
            old = int(assignment[c])
            selected = rows_by_cluster[cluster_start[c]:cluster_start[c + 1]]
            affected, number = np.unique(pair[selected], return_counts=True)
            if np.all(counts[affected, old] > number):
                counts[affected, old] -= number
                counts[affected, fold] += number
                assignment[c] = fold
                repairs.append(dict(cluster=int(c), old=old, new=int(fold), rows=len(selected)))
                break
        else:
            raise AssertionError(("cannot obtain full-port cluster split", int(p), int(fold)))
    folds = assignment[cluster]
    assert np.all(counts > 0)
    assert np.array_equal(counts, np.bincount(pair * 3 + folds, minlength=59904 * 3).reshape(59904, 3))
    records = []
    for k in range(3):
        test, train = folds == k, folds != k
        assert not np.intersect1d(np.unique(cluster[test]), np.unique(cluster[train])).size
        assert np.bincount(pair[train], minlength=59904).min() > 0
        records.append(dict(fold=k, rows=int(test.sum()), train_rows=int(train.sum()),
                            pairs=59904, min_pair_rows=int(counts[:, k].min()),
                            clusters=int(np.unique(cluster[test]).size), cluster_disjoint=True))
    folds.tofile(BUILD / "folds.u8")
    cluster.astype("<i4").tofile(BUILD / "clusters.i32")
    indices.astype("<i4").tofile(BUILD / "ports.i32")
    write(ROOT / "split.json", dict(folds=records, repairs=repairs, seed=SEED,
          assets=[identity(BUILD / n) for n in ("folds.u8", "clusters.i32", "ports.i32")],
          all_full_port=True, all_cluster_disjoint=True, development_only=True))
    return folds


def features(query, event):
    sx, sy, tx, ty = query[:, :4].T
    sf, sl, tf, tl = query[:, 4:8].T
    ax, ay = event[:, :2].T
    x, y = tx - ax, ty - ay
    trend = 125 * (np.abs(x) // 10) + np.where(y < 0, 125, 127) * (np.abs(y) // 12)
    fee = event[:, 4] - event[:, 7]
    assert np.all(fee >= 0)
    same = (sx == tx) & (sy == ty) & (query[:, 8] == query[:, 9])
    assert not np.any(same), "this development input has no same-pin rows"
    fields = dict(sf=sf, sl=sl, tf=tf, tl=tl, source_logic=sf >= 20, target_logic=tf >= 20,
                  first_dx=event[:, 2], first_dy=event[:, 3], dx=x, dy=y,
                  abs_dx=np.abs(x), abs_dy=np.abs(y), neg_dx=x < 0, neg_dy=y < 0,
                  rx=x % 10, ry=y % 12, abs_rx=np.abs(x) % 10, abs_ry=np.abs(y) % 12,
                  qx=np.abs(x) // 10, qy=np.abs(y) // 12, lane_xor=sl ^ tl,
                  lane_difference=sl - tl, trend=trend)
    for bit in range(3):
        fields[f"lane_pair_{bit}"] = ((sl >> bit) & 1) + 2 * ((tl >> bit) & 1)
    relative_count = len(fields)
    side = lambda a: np.where(a < 76, 0, np.where(a < 90, 1, 2))
    fields.update(sx=sx, sy=sy, ax=ax, ay=ay, tx=tx, ty=ty,
                  sx_right=119 - sx, ax_right=119 - ax, tx_right=119 - tx,
                  sy_top=549 - sy, ay_top=549 - ay, ty_top=549 - ty,
                  source_side=side(sx), arrival_side=side(ax), target_side=side(tx),
                  source_band=sy % 100, arrival_band=ay % 100, target_band=ty % 100,
                  source_block_row=(sy % 100) < 50, arrival_block_row=(ay % 100) < 50,
                  target_block_row=(ty % 100) < 50, source_ycell=sy // 100,
                  arrival_ycell=ay // 100, target_ycell=ty // 100,
                  first_block=fee,
                  compressed_dx=(tx - 14 * ((ty % 100 < 50) & (tx >= 90))) -
                                (ax - 14 * ((ay % 100 < 50) & (ax >= 90))))
    forced = prior.partition(query, event)["forced_detour"]
    fields["forced_detour"] = forced
    matrix = np.column_stack(list(fields.values())).astype("<f4")
    assert matrix.shape == (ROWS, len(fields)) and np.all(np.isfinite(matrix))
    with (BUILD / "features.f32").open("xb") as stream:
        stream.write(b"E554F001" + struct.pack("<II", ROWS, matrix.shape[1]))
        stream.write(matrix.tobytes())
    write(ROOT / "features.json", dict(names=list(fields), relative_count=relative_count,
          columns=matrix.shape[1], asset=identity(BUILD / "features.f32"),
          source="query, certified first-Net event, official map only"))
    return matrix, relative_count, trend + fee


def export_model(booster, stem):
    path = BUILD / (stem + ".json")
    booster.save_model(path)
    learner = read(path)["learner"]
    assert float(learner["learner_model_param"]["base_score"]) == 0
    trees = learner["gradient_booster"]["model"]["trees"]
    roots, arrays, offset = [], [], 0
    dtype = np.dtype([("left", "<i4"), ("right", "<i4"), ("feature", "<i4"), ("value", "<f4")])
    for tree in trees:
        assert not tree["categories"] and not any(tree["split_type"])
        nodes = np.empty(len(tree["left_children"]), dtype=dtype)
        roots.append(offset)
        for key, field in (("left", "left_children"), ("right", "right_children")):
            values = np.asarray(tree[field], dtype=np.int32)
            nodes[key] = np.where(values < 0, -1, values + offset)
        nodes["feature"] = tree["split_indices"]
        nodes["value"] = tree["split_conditions"]
        assert np.all(np.isfinite(nodes["value"]))
        arrays.append(nodes)
        offset += len(nodes)
    output = BUILD / (stem + ".bin")
    with output.open("xb") as stream:
        stream.write(b"E554M001" + struct.pack("<III", len(trees), offset,
                     int(learner["learner_model_param"]["num_feature"])))
        stream.write(np.asarray(roots, dtype="<u4").tobytes())
        stream.write(np.concatenate(arrays).tobytes())
    return dict(json=identity(path), binary=identity(output), trees=len(trees), nodes=offset)


def decode(raw, base, mandatory):
    shifted = raw.astype(np.float64) + base
    rounded = np.copysign(np.floor(np.abs(shifted) + .5), shifted).astype(np.int64)
    return np.maximum(0, rounded) + mandatory


def train(matrix, relative_count, base, d0, mandatory, oracle, truth, folds):
    raw = np.empty((ROWS, len(ARMS)), dtype="<f4")
    weights = (1000 / np.maximum(d0 + mandatory, 128)).astype(np.float32)
    records = []
    for col, name in enumerate(ARMS):
        budget, arm = name.split("_")
        depth, rounds = BUDGETS[budget]
        offset = oracle - mandatory if arm == "Q" else base
        width = relative_count if arm == "T" else matrix.shape[1]
        for k in range(3):
            learn, test = folds != k, folds == k
            started, cpu = time.monotonic(), time.process_time()
            dm = xgb.DMatrix(matrix[learn, :width], label=(d0 - offset)[learn].astype(np.float32),
                             weight=weights[learn], nthread=4)
            params = dict(objective="reg:absoluteerror", tree_method="hist", max_depth=depth,
                          eta=.1, max_bin=256, base_score=0, subsample=1., colsample_bytree=1.,
                          seed=SEED, nthread=4)
            booster = xgb.train(params, dm, num_boost_round=rounds)
            assets = export_model(booster, f"{name}-{k}")
            restored = xgb.Booster()
            restored.load_model(BUILD / f"{name}-{k}.json")
            dt = xgb.DMatrix(matrix[test, :width], nthread=4)
            predicted = booster.predict(dt)
            recovered = restored.predict(dt)
            assert np.array_equal(predicted.view(np.uint32), recovered.view(np.uint32))
            assert np.all(np.isfinite(predicted))
            raw[test, col] = predicted
            training_raw = booster.predict(dm)
            assert np.all(np.isfinite(training_raw))
            training_path = BUILD / f"{name}-{k}.train.f32"
            training_raw.astype("<f4").tofile(training_path)
            training = decode(training_raw, offset[learn], mandatory[learn])
            validation = decode(predicted, offset[test], mandatory[test])
            record = dict(name=name, fold=k, params=params, rounds=rounds, assets=assets,
                          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
                          train_raw=identity(training_path),
                          train=real.statistics(training, truth[learn]),
                          validation=real.statistics(validation, truth[test]),
                          train_kernel=real.statistics(training - mandatory[learn], d0[learn]),
                          validation_kernel=real.statistics(validation - mandatory[test], d0[test]))
            records.append(record)
            write(ROOT / f"{name}-{k}.json", record)
            print("EXP554_TRAINED", name, k, flush=True)
            del dm, dt, booster, restored
            gc.collect()
    raw.tofile(BUILD / "native.f32")
    write(ROOT / "training.json", dict(records=records, native=identity(BUILD / "native.f32"),
                                      xgboost_version=xgb.__version__))
    return raw, records


def independent(raw):
    version = subprocess.check_output(["g++", "--version"], text=True)
    help_text = subprocess.check_output(["g++", "--help=common"], text=True)
    assert "-ffp-contract" in help_text
    binary = BUILD / "predict"
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror", "-static", "-s",
               "-march=x86-64", "-mtune=generic", "-ffp-contract=off", "tests/exp554_real_kernel_function.cpp",
               "-o", str(binary)]
    built = subprocess.run(command, capture_output=True, text=True)
    write(ROOT / "build.json", dict(command=command, version=version, exit_code=built.returncode,
                                    stdout=built.stdout, stderr=built.stderr))
    assert built.returncode == 0 and not built.stderr, built.stderr
    help_run = subprocess.run([str(binary), "--help"], capture_output=True, text=True)
    assert help_run.returncode == 0 and help_run.stdout.startswith("usage: predict FEATURES FOLDS")
    runs = []
    for col, name in enumerate(ARMS):
        output = BUILD / (name + ".independent.f32")
        command = [str(binary), str(BUILD / "features.f32"), str(BUILD / "folds.u8")]
        command += [str(BUILD / f"{name}-{k}.bin") for k in range(3)] + [str(output)]
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
                time.sleep(.02)
            child.returncode = os.waitstatus_to_exitcode(status)
        assert child.returncode == 0 and threads == 1
        assert not (ROOT / (name + ".stderr")).read_bytes()
        predicted = np.fromfile(output, "<f4")
        assert predicted.shape == (ROWS,) and np.array_equal(predicted.view(np.uint32), raw[:, col].view(np.uint32))
        counts = read(ROOT / (name + ".stdout"))
        assert counts["rows"] == ROWS and counts["threads"] == 1
        record = dict(name=name, command=command, exit_code=child.returncode,
                      cpu_s=usage.ru_utime + usage.ru_stime, wall_s=time.monotonic() - started,
                      rss_bytes=usage.ru_maxrss * 1024, threads=threads, counters=counts,
                      output=identity(output), bitwise_equal=True)
        runs.append(record)
        write(ROOT / (name + ".run.json"), record)
        print("EXP554_INDEPENDENT_PASSED", name, flush=True)
    write(ROOT / "independent.json", dict(binary=identity(binary), runs=runs,
                                          all_bitwise_equal=True, production_timing=False))


def report(raw, base, d0, mandatory, oracle, truth, production, cluster, query, event, indices, models):
    predictions = {"L": d0 + mandatory, "O": oracle, "exp354": production}
    for col, name in enumerate(ARMS):
        offset = oracle - mandatory if name.endswith("_Q") else base
        predictions[name] = decode(raw[:, col], offset, mandatory)
    names = list(predictions)
    array = np.column_stack(list(predictions.values())).astype("<i4")
    array.tofile(BUILD / "predictions.i32")
    np.column_stack((truth, d0, mandatory, base)).astype("<i4").tofile(BUILD / "labels.i32")
    stats = {name: real.statistics(p, truth) for name, p in predictions.items()}
    scores = {name: real.points(p, truth) for name, p in predictions.items()}
    pairs = [(f"{b}_J", f"{b}_T") for b in BUDGETS]
    pairs += [(name, "O" if name.endswith("_Q") else "exp354") for name in ARMS]
    delta = np.column_stack([scores[a] - scores[b] for a, b in pairs])
    counts = np.bincount(cluster)
    sums = np.column_stack([np.bincount(cluster, weights=delta[:, i]) for i in range(len(pairs))])
    rng, boot = np.random.default_rng(SEED), np.empty((DRAWS, len(pairs)))
    for draw in range(DRAWS):
        sample = rng.integers(len(counts), size=len(counts))
        boot[draw] = sums[sample].sum(axis=0) / counts[sample].sum()
    interval = np.quantile(boot, [.025, .975], axis=0)
    paired = {}
    for i, (a, b) in enumerate(pairs):
        paired[a + "-" + b] = dict(delta_pp=float(delta[:, i].mean()), ci95_pp=interval[:, i].tolist(),
            better_rows=int(np.sum(scores[a] > scores[b])), worse_rows=int(np.sum(scores[a] < scores[b])),
            equal_score_rows=int(np.sum(scores[a] == scores[b])),
            changed_rows=int(np.sum(predictions[a] != predictions[b])),
            unit="complete source pin", clusters=len(counts), draws=DRAWS, seed=SEED)
    partition = prior.partition(query, event)
    partition.update(source_port=indices[:, 0], target_port=indices[:, 1],
                     row_band=2 * (query[:, 1] % 100 < 50) + (query[:, 3] % 100 < 50))
    groups = {}
    for family, values in partition.items():
        groups[family] = {str(int(v)): {n: real.statistics(p[values == v], truth[values == v])
                                      for n, p in predictions.items()} for v in np.unique(values)}
    coupling = truth - d0 - mandatory
    assert np.all(coupling >= 0)
    decomposed = {}
    for name in ARMS:
        e = predictions[name] - d0 - mandatory
        assert np.array_equal(predictions[name] - truth, e - coupling)
        e2, c2, ec = int(e @ e), int(coupling @ coupling), int(e @ coupling)
        assert e2 + c2 - 2 * ec == stats[name]["squared_ps"]
        decomposed[name] = dict(representation_squared_ps=e2, coupling_squared_ps=c2,
                               error_coupling_cross_ps=ec, score_loss_bound_pp=float(np.mean(400 * np.abs(e) / truth)))
    gates = {}
    shared_bytes = (BUILD / "predict").stat().st_size + sum(
        p.stat().st_size for p in Path("doc/eda比赛文件/arch").glob("*.json"))
    for budget in BUDGETS:
        name = budget + "_J"
        effect = paired[name + "-" + budget + "_T"]
        comparison = paired[name + "-exp354"]
        size = max(m["assets"]["binary"]["bytes"] for m in models if m["name"] == name)
        component_size = size + shared_bytes
        capacity = 8_000_000 if budget == "small" else 80_000_000
        gates[budget] = dict(geometry_mechanism=bool(effect["delta_pp"] >= .05 and effect["ci95_pp"][0] > 0),
            direct_quality=bool(stats[name]["accuracy_pp"] >= 99.1 and comparison["delta_pp"] >= .05
                                and comparison["ci95_pp"][0] > 0 and component_size <= capacity),
            model_bytes_max=size, known_component_bytes=component_size, component_budget=capacity,
            final_elf_validated=False,
            oracle_conditioned=bool(paired[budget + "_Q-O"]["delta_pp"] >= .05 and
                                    paired[budget + "_Q-O"]["ci95_pp"][0] > 0))
    write(ROOT / "groups.json", groups)
    write(ROOT / "report.json", dict(rows=ROWS, sources=208, targets=288, pairs=59904,
          all_full_port=True, all_cluster_disjoint=True, independent_queries=False,
          statistics=stats, paired=paired, decomposition=decomposed, gates=gates,
          prediction_names=names, predictions=identity(BUILD / "predictions.i32"),
          labels=identity(BUILD / "labels.i32"), all_checks_passed=True))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp554")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (14400, 14400))
    resource.setrlimit(resource.RLIMIT_AS, (32 << 30, 32 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    old = Path("../exp553")
    freeze = read(old / "validation/results/exp553/freeze.json")
    asset_paths = ["../exp500/validation/results/exp500-preparation/mapping.json",
                   "../exp501/validation/results/exp501/report.json", "../exp502/validation/results/exp502/report.json",
                   "../exp536/build/exp536/events.i32", "../exp536/build/exp536/predictions.i32"]
    assets = [real.check(p, next(r for r in freeze["files"] if r["path"] == p)) for p in asset_paths]
    for a in freeze["files"]:
        if a["path"].startswith("doc/eda比赛文件/arch/"):
            assets.append(real.check(a["path"], a))
    real.BUILD = BUILD
    query, indices, truth, production, cluster, inputs = real.inputs(*[read(p) for p in asset_paths[:3]])
    assert inputs["queries"]["sha256"] == "aa0cd63f7e83be6d5a12169f0318ae0d4cfc510aa705de1f898611524a9165c1"
    assert inputs["unique_rows"] == ROWS and inputs["min_pair_rows"] >= 3 and np.all(truth > 0)
    write(ROOT / "input.json", inputs)
    previous = read(old / "validation/results/exp553/report.json")
    replay = read(old / "validation/results/exp553/replay.json")
    for a in (previous["components"], replay["distance"]):
        assets.append(real.check(old / a["path"], a))
    component = np.fromfile(old / previous["components"]["path"], "<i4").reshape(ROWS, 8).astype(np.int64)
    d0 = np.fromfile(old / replay["distance"]["path"], "<i4").astype(np.int64)
    assert np.array_equal(d0, component[:, 0])
    mandatory = component[:, 1]
    event = np.fromfile(asset_paths[3], "<i4").reshape(ROWS, 9).astype(np.int64)
    oracle = np.fromfile(asset_paths[4], "<i4").reshape(ROWS, 6)[:, 2].astype(np.int64)
    assert np.array_equal(component[:, 2], d0 + mandatory)
    assert real.statistics(d0 + mandatory, truth) == previous["statistics"]["L"]
    folds = split(indices, cluster)
    matrix, relative_count, base = features(query, event)
    files = [Path(__file__), Path("tests/exp554_real_kernel_function.cpp"), ROOT / "protocol-original.md"]
    files += [Path("validation") / (name + ".py") for name in
              ("exp535_real_map", "exp549_complementarity", "exp208_nominal_parent_tree")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files] + assets + inputs["inputs"],
          seed=SEED, draws=DRAWS, xgboost=xgb.__version__, disk_free_start=free))
    raw, models = train(matrix, relative_count, base, d0, mandatory, oracle, truth, folds)
    del matrix
    gc.collect()
    independent(raw)
    report(raw, base, d0, mandatory, oracle, truth, production, cluster, query, event, indices, models)
    assets_size = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert assets_size <= 1_000_000_000
    write(ROOT / "cost.json", dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          assets_bytes=assets_size, disk_free_start=free, disk_free_end=shutil.disk_usage(".").free,
          deleted_files=[], freed_bytes=0, production_runs=0))
    print("EXP554_FULL_PORT_REAL_KERNEL_FUNCTION_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
