#!/usr/bin/env python3
"""Independently decode and score the full-port shared leaf model on r9."""
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

import exp557_evaluate as previous

ROOT, BUILD = Path("validation/results/exp567"), Path("build/exp567")
OFFLINE = Path("offline")
SOURCE = OFFLINE / ROOT
PLAN = Path("experiment/实验567-共享几何叶字典与完整端口系数.md")
ROWS, LEFT, RIGHT, TREES, LEAVES, SEED = 1000000, 59904, 264960, 8, 64, 20261021567
read, write, identity, real = previous.read, previous.write, previous.identity, previous.real
previous.ROOT, previous.BUILD = ROOT, BUILD


def json_leaves(tree, features, probes=None):
    left, right = np.asarray(tree["left_children"]), np.asarray(tree["right_children"])
    split = np.asarray(tree["split_indices"])
    threshold = np.asarray(tree["split_conditions"], dtype="<f4")
    at = np.zeros(len(features), dtype=np.int32)
    for _ in range(7):
        rows = np.flatnonzero(left[at] >= 0)
        if not len(rows):
            break
        nodes = at[rows]
        if probes is not None:
            unique, first = np.unique(nodes, return_index=True)
            for node, index in zip(unique, first):
                feature = split[node]
                for value in (np.nextafter(threshold[node], np.float32(-np.inf)), threshold[node],
                              np.nextafter(threshold[node], np.float32(np.inf))):
                    candidate = features[rows[index]].copy()
                    candidate[feature] = value
                    probes.append(candidate)
        at[rows] = np.where(features[rows, split[nodes]] < threshold[nodes], left[nodes], right[nodes])
    assert np.all(left[at] == -1)
    return at


def router(training):
    for record in training["assets"]:
        real.check(OFFLINE / record["path"], record)
    path = OFFLINE / BUILD / "rules.json"
    model = read(path)["learner"]["gradient_booster"]["model"]["trees"]
    features = np.load(OFFLINE / BUILD / "features.npy")
    leaves = np.load(OFFLINE / BUILD / "leaves.npy")
    stored = np.load(OFFLINE / BUILD / "native-leaves.npy")
    assert features.shape == (RIGHT, 14) and leaves.shape == stored.shape == (RIGHT, TREES)
    assert leaves.dtype == np.dtype("u1") and len(model) == TREES and leaves.max() < 64
    booster = xgb.Booster(); booster.load_model(path)
    native = booster.predict(xgb.DMatrix(features, nthread=4), pred_leaf=True).reshape(RIGHT, TREES).astype("<i4")
    probes = []
    for t, tree in enumerate(model):
        assert not tree["categories"] and not any(tree["split_type"])
        independent = json_leaves(tree, features, probes)
        assert np.array_equal(stored[:, t], native[:, t]) and np.array_equal(native[:, t], independent)
        ids = np.unique(native[:, t])
        assert ids.tolist() == training["node_ids"][t]
        assert np.array_equal(leaves[:, t], np.searchsorted(ids, native[:, t]))
    probes = np.asarray(probes, dtype="<f4")
    boundary = booster.predict(xgb.DMatrix(probes, nthread=4), pred_leaf=True).reshape(len(probes), TREES)
    for t, tree in enumerate(model):
        assert np.array_equal(boundary[:, t], json_leaves(tree, probes))
    write(ROOT / "router-check.json", dict(keys=RIGHT, trees=TREES, boundary_rows=len(probes),
          complete_json_native_table_equality=True, training=identity(SOURCE / "training.json")))
    return leaves


def coefficients(training, leaves):
    center = np.load(OFFLINE / BUILD / "center.npy")
    floating = np.load(OFFLINE / BUILD / "coefficients.npy")
    exponent = np.load(OFFLINE / BUILD / "exponent.npy")
    integer = np.load(OFFLINE / BUILD / "integers.npy")
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    assert floating.shape == integer.shape == (LEFT, TREES, LEAVES)
    assert floating.dtype == np.dtype("<f8") and integer.dtype == np.dtype("<i2")
    assert exponent.shape == (TREES,) and exponent.dtype == np.dtype("<i4")
    assert exponent.min() > -500 and exponent.max() < 500
    rounded = np.rint(np.ldexp(floating, -exponent[None, :, None]))
    assert np.isfinite(floating).all() and np.abs(rounded).max() <= 32767
    assert np.array_equal(rounded.astype("<i2"), integer)
    restored = np.ldexp(integer.astype(np.float64), exponent[None, :, None])
    error = float(np.abs(floating-restored).max(axis=2).sum(axis=1).max())
    assert abs(error-training["quantized_coefficient_max_error"]) <= 1e-14
    gram = np.zeros((512, 512), dtype=np.float64)
    for t in range(TREES):
        for u in range(TREES):
            gram[t*64:(t+1)*64, u*64:(u+1)*64] = np.bincount(
                64*leaves[:, t].astype(np.int64)+leaves[:, u], minlength=4096).reshape(64, 64)
    assert np.array_equal(gram, np.load(OFFLINE / BUILD / "gram.npy"))
    rhs = np.load(OFFLINE / BUILD / "rhs.npy")
    normal = float(np.abs(floating.reshape(LEFT, 512)@gram-rhs).max()) / max(1., float(np.abs(rhs).max()))
    assert normal <= 1e-6
    bound = sum(int(np.abs(integer[:, t].astype(np.int32)).max()) << int(exponent[t]-exponent.min())
                for t in range(TREES))
    normal_scaling = int(exponent.min()) >= -1022 and bound.bit_length()+int(exponent.min()) <= 1024
    assert bound == training["integer_sum_bound"] and normal_scaling
    assert bool(bound <= 2**53) == training["float64_reassociation_certified"]
    write(ROOT / "coefficient-check.json", dict(complete_gram_equality=True, complete_quantization_equality=True,
          coefficient_count=integer.size, normal_equation_relative_max_error=normal,
          integer_sum_bound=bound, normal_scaling=normal_scaling,
          float64_reassociation_certified=bool(bound <= 2**53 and normal_scaling),
          quantized_coefficient_max_error=error, port_pairs=LEFT, geometries=RIGHT))
    return center, floating, restored, exponent, integer


def compile_decoders():
    helped = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in helped
    (ROOT / "compiler-help.txt").write_text(helped)
    for source, name in (("tests/exp567_leaf_decode.cpp", "leaf-decode"),
                         ("tests/exp554_real_kernel_function.cpp", "tree-decode")):
        command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64", "-mtune=generic",
                   "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", source, "-o", str(BUILD/name)]
        result = subprocess.run(command, capture_output=True, text=True)
        write(ROOT / (name+"-compiler.json"), dict(command=command, exit_code=result.returncode,
              stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0 and not result.stderr
        assert subprocess.check_output([str(BUILD/name), "--help"], text=True).startswith("usage:")


def geometry(name, encoding, center, floating, exponent, integer, leaves, query, ports, event, mandatory):
    pair = ports[:, 0]*288+ports[:, 1]
    x, y = query[:, 2]-event[:, 0]+event[:, 2], query[:, 3]-event[:, 1]+event[:, 3]
    ax, ay = np.abs(x), np.abs(y)
    assert np.all(ax <= 119) and np.all(ay <= 549)
    column = (((((2*(x<0)+(y<0))*10+ax%10)*12+ay%12)*12+ax//10)*46+ay//12)
    path = BUILD / (name+"-geometry.bin")
    with path.open("xb") as stream:
        stream.write(b"EX567L01"+struct.pack("<5I", LEFT, RIGHT, TREES, LEAVES, encoding)+bytes(36))
        for value in (center, leaves, exponent, integer if encoding else floating):
            stream.write(value.tobytes())
    if not encoding:
        np.column_stack((pair, column)).astype("<i4").tofile(BUILD/"keys.i32")
    response = np.zeros(ROWS, dtype=np.float64)
    for t in range(TREES):
        response += floating[pair, t, leaves[column, t]]
    output = BUILD / (name+"-geometry.f64")
    decoded = previous.run([str(BUILD/"leaf-decode"), str(path), str(BUILD/"keys.i32"), str(output)], name+"-geometry")
    independent = np.fromfile(output, "<f8")
    assert independent.shape == response.shape and np.array_equal(independent.view("u8"), response.view("u8"))
    scale = 128+125*(ax//10)+125*(ay//12)
    trend = 125*(ax//10)+np.where(y<0, 125, 127)*(ay//12)
    value = response*scale+center[pair]+trend
    nominal = np.maximum(0, np.copysign(np.floor(np.abs(value)+.5), value).astype(np.int64))
    zero = (x==0)&(y==0)&(query[:, 8]==query[:, 9])&(query[:, 4]<20)
    cycle = read("../exp536/validation/results/exp536/oracle.json")
    assert cycle["complete"] and len(cycle["sources"]) == 208
    cycles = np.asarray([r["cycle_ps"] for r in cycle["sources"]])
    nominal[zero] = cycles[ports[zero, 0]]
    base = nominal+event[:, 4]+event[:, 6]-mandatory
    assert np.array_equal(base, nominal+event[:, 4]-event[:, 7])
    base.astype("<i4").tofile(BUILD/(name+"-base.i32"))
    write(ROOT/(name+"-geometry.json"), dict(model=identity(path), output=identity(output),
          base=identity(BUILD/(name+"-base.i32")), bitwise_equal=True, decoder=decoded,
          zero_rows=int(zero.sum()), source_ports=208, target_ports=288, port_pairs=LEFT))
    return base


def report(predictions, query, event, ports, truth):
    scores = {n: real.points(p, truth) for n, p in predictions.items()}
    pairs = [(n, "exp354") for n in predictions if n.startswith("L") and not n.endswith("base")]
    pairs += [("L32", "F32"), ("L32", "G32"), ("L-base", "Lf-base")]
    family = query[:, 4].astype(np.int32)
    counts = np.bincount(family)
    assert len(counts) == 26 and counts.min() > 0
    sums = np.column_stack([np.bincount(family, weights=scores[a]-scores[b]) for a, b in pairs])
    rng, boot = np.random.default_rng(SEED), np.empty((2000, len(pairs)))
    for i in range(len(boot)):
        sample = rng.integers(len(counts), size=len(counts))
        boot[i] = sums[sample].sum(axis=0)/counts[sample].sum()
    interval = np.quantile(boot, [.025, .975], axis=0)
    paired = {a+"-"+b: dict(delta_pp=float((scores[a]-scores[b]).mean()), ci95_pp=interval[:, i].tolist(),
              changed_rows=int(np.count_nonzero(predictions[a]!=predictions[b])),
              better_rows=int(np.count_nonzero(scores[a]>scores[b])),
              worse_rows=int(np.count_nonzero(scores[a]<scores[b])), source_family_clusters=26)
              for i, (a, b) in enumerate(pairs)}
    statistics = {n: real.statistics(p, truth) for n, p in predictions.items()}
    gates = {a: bool(statistics[a]["accuracy_pp"]>=99.15 and paired[a+"-exp354"]["delta_pp"]>=.05 and
                    paired[a+"-exp354"]["ci95_pp"][0]>0) for a, b in pairs if b=="exp354"}
    partition = previous.grouping.partition(query, event)
    x, y = query[:, 2]-event[:, 0]+event[:, 2], query[:, 3]-event[:, 1]+event[:, 3]
    partition.update(source_port=ports[:, 0], target_port=ports[:, 1], nominal_direction=2*(x<0)+(y<0))
    grouped = {key: {str(int(v)): {n: real.statistics(p[values==v], truth[values==v])
               for n, p in predictions.items()} for v in np.unique(values)} for key, values in partition.items()}
    write(ROOT/"groups.json", grouped)
    write(ROOT/"report.json", dict(rows=ROWS, port_pairs=LEFT, statistics=statistics, paired=paired,
          quality_gates=gates, all_full_port=True, complete_geometry_equality=True,
          complete_residual_equality=True, development_only=True, independent_requests_used=0,
          final_elf_verified=False, production_cpu_verified=False, single_call_100ns_verified=False))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp567")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (2400, 2400))
    resource.setrlimit(resource.RLIMIT_AS, (8<<30, 8<<30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT/"protocol-original.md")
    (ROOT/"installed-xgboost-help.txt").write_text(str(inspect.signature(xgb.train))+"\n"+xgb.train.__doc__)
    trained = read(SOURCE/"training.json")
    assert trained["all_training_checks"] and trained["shape"] == [LEFT, RIGHT]
    leaves = router(trained)
    center, floating, restored, exponent, integer = coefficients(trained, leaves)
    compile_decoders()
    previous.previous.ROOT, previous.trees.BUILD = ROOT, BUILD
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = previous.previous.data()
    assert matrix.shape == (ROWS, 53)
    previous.features(BUILD/"features.f32", matrix); folds.tofile(BUILD/"folds.u8")
    frozen = [Path(__file__), PLAN, ROOT/"protocol-original.md", Path("tests/exp567_leaf_decode.cpp"),
              Path("tests/exp554_real_kernel_function.cpp"), SOURCE/"training.json", ROOT/"input.json"]
    frozen.append(Path("doc/eda比赛文件/arch/SRB_Gap.json"))
    frozen += [Path("validation")/(n+".py") for n in
               ("exp557_evaluate", "exp500_evaluate", "exp554_real_kernel_function", "exp556_xgb_residual",
                "exp549_complementarity", "exp535_real_map", "exp208_nominal_parent_tree")]
    write(ROOT/"evaluation-freeze.json", dict(files=[identity(p) for p in frozen], seed=SEED,
          rows=ROWS, port_pairs=LEFT, full_port_required=True, disk_free_start=free))
    base_float = geometry("Lf", 0, center, floating, exponent, integer, leaves, query, ports, event, labels[:, 2])
    base = geometry("L", 1, center, restored, exponent, integer, leaves, query, ports, event, labels[:, 2])
    predictions = {"exp354": production, "Q-base": oracle,
                   "Lf-base": base_float+labels[:, 2], "L-base": base+labels[:, 2]}
    del floating, restored
    for name in ("F32", "G32"):
        meta = read("../exp557/validation/results/exp557/"+name+".json")
        path = Path("../exp557")/meta["predictions"]["path"]
        real.check(path, meta["predictions"])
        predictions[name] = np.fromfile(path, "<i4").astype(np.int64)
        assert abs(real.statistics(predictions[name], labels[:, 0])["accuracy_pp"]-meta["statistics"]["accuracy_pp"])<1e-10
    predictions["L32"] = previous.train("L32", base, matrix, folds, labels, 32)
    raw = np.fromfile(BUILD/"L32.f32", "<f4")
    predictions["Lf32"] = previous.trees.decode(raw, base_float, labels[:, 2])
    predictions["Lf32"].astype("<i4").tofile(BUILD/"Lf32.i32")
    best_score = real.statistics(predictions["L32"], labels[:, 0])["accuracy_pp"]
    if best_score >= 98.5:
        predictions["L128"] = previous.train("L128", base, matrix, folds, labels, 128)
        best_score = max(best_score, real.statistics(predictions["L128"], labels[:, 0])["accuracy_pp"])
    if best_score >= 99.15:
        extra = np.column_stack((matrix, base)).astype("<f4")
        previous.features(BUILD/"features54.f32", extra)
        for suffix, rounds, eta in (("tiny8", 8, .3), ("tiny16", 16, .2)):
            name = "L"+suffix
            predictions[name] = previous.train(name, base, extra, folds, labels, rounds, 4, eta)
    report(predictions, query, event, ports, labels[:, 0])
    gc.collect()
    assets = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert assets < 1000000000
    write(ROOT/"cost.json", dict(cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024, new_asset_bytes=assets,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free, freed_bytes=0, deleted_files=[]))
    print("EXP567_COMPLETE_FULL_PORT_EVALUATION", flush=True)


if __name__ == "__main__":
    main()
