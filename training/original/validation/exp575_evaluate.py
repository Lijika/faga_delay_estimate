#!/usr/bin/env python3
"""Cross-fit the fixed distance-group candidates on the complete-port r9 1M."""
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

ROOT, BUILD = Path("validation/results/exp575-evaluation"), Path("build/exp575")
SOURCE = Path("offline/validation/results/exp575")
PLAN = Path("experiment/实验575-距离分组的非均匀秩预算.md")
ROWS, LEFT, RIGHT, SEED = 1000000, 59904, 264960, 20261021575
read, write, identity, real = previous.read, previous.write, previous.identity, previous.real


def compile_decoders():
    helped = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in helped
    (ROOT / "compiler-help.txt").write_text(helped)
    records = []
    for source, name in (("tests/exp575_geometry_decode.cpp", "geometry-decode"),
                         ("tests/exp554_real_kernel_function.cpp", "tree-decode")):
        command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64", "-mtune=generic",
                   "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", source,
                   "-o", str(BUILD / name)]
        result = subprocess.run(command, capture_output=True, text=True)
        record = dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        write(ROOT / (name + "-compiler.json"), record)
        assert result.returncode == 0 and not result.stderr, record
        helped = subprocess.run([str(BUILD / name), "--help"], capture_output=True, text=True)
        assert helped.returncode == 0 and helped.stdout.startswith("usage:")
        records.append(record)
    write(ROOT / "compiler.json", dict(version=subprocess.check_output(["g++", "--version"], text=True), builds=records))


def geometry(model, center, pair, column, scale, trend, zero, cycles, event, mandatory):
    name, parts = model["name"], model["parts"]
    path = BUILD / (name + "-geometry.bin")
    response = np.zeros(ROWS)
    header = b"EX575Q01" + struct.pack("<6I", LEFT, RIGHT, *[p["rank"] for p in parts],
                                          *[p["geometries"] for p in parts]) + bytes(32)
    assert len(header) == 64
    with path.open("xb") as stream:
        stream.write(header)
        stream.write(center.tobytes())
        for group, part in enumerate(parts):
            for asset in part["assets"]:
                real.check(Path("offline") / asset["path"], asset)
            load = lambda suffix: np.load(Path("offline/build/exp575") / (part["name"] + "-" + suffix + ".npy"))
            keys = load("keys")
            li, ri, le, re = [load(s) for s in ("left-integers", "right-integers", "left-exponent", "right-exponent")]
            for value in (le, li, re, ri):
                stream.write(value.tobytes())
            quotient = (column % 552) // 46 + column % 46
            mask = (quotient > 3) == bool(group)
            positions = np.searchsorted(keys, column[mask])
            assert np.array_equal(keys[positions], column[mask])
            prediction = np.zeros(int(mask.sum()))
            rows = pair[mask]
            for k in range(part["rank"]):
                product = li[rows, k].astype(np.int64) * ri[positions, k].astype(np.int64)
                prediction += product.astype(np.float64) * np.ldexp(1., int(le[k]) + int(re[k]))
            response[mask] = prediction
    assert path.stat().st_size == 64 + center.nbytes + sum(p["factor_bytes"] for p in parts)
    output = BUILD / (name + "-geometry.f64")
    record = previous.run([str(BUILD / "geometry-decode"), str(path), str(BUILD / "keys.i32"), str(output)], name + "-geometry")
    independent = np.fromfile(output, "<f8")
    assert independent.shape == (ROWS,) and np.array_equal(response.view("u8"), independent.view("u8"))
    value = response * scale + center[pair] + trend
    nominal = np.maximum(0, np.copysign(np.floor(np.abs(value) + .5), value).astype(np.int64))
    nominal[zero] = cycles[pair[zero] // 288]
    base = nominal + event[:, 4] + event[:, 6] - mandatory
    assert np.array_equal(base, nominal + event[:, 4] - event[:, 7])
    base.astype("<i4").tofile(BUILD / (name + "-base.i32"))
    write(ROOT / (name + "-geometry.json"), dict(model=identity(path), decoder=record, bitwise_equal=True,
          output=identity(output), base=identity(BUILD / (name + "-base.i32")),
          ranks=[p["rank"] for p in parts], port_pairs=LEFT, complete_geometry_index=True))
    return base


def report(predictions, truth, query, event, ports):
    score = {n: real.points(p, truth) for n, p in predictions.items()}
    names = [n for n in predictions if n.startswith("N") and not n.endswith("-base")]
    pairs = [(n, b) for n in names for b in ("exp354", "G32")]
    family = query[:, 4].astype(np.int32)
    counts = np.bincount(family)
    assert len(counts) == 26 and counts.min() > 0
    sums = np.column_stack([np.bincount(family, weights=score[a] - score[b]) for a, b in pairs])
    rng, boot = np.random.default_rng(SEED), np.empty((2000, len(pairs)))
    for i in range(len(boot)):
        sample = rng.integers(26, size=26)
        boot[i] = sums[sample].sum(axis=0) / counts[sample].sum()
    interval = np.quantile(boot, [.025, .975], axis=0)
    paired = {a + "-" + b: dict(delta_pp=float((score[a] - score[b]).mean()), ci95_pp=interval[:, i].tolist(),
              changed_rows=int(np.count_nonzero(predictions[a] != predictions[b])),
              better_rows=int(np.count_nonzero(score[a] > score[b])), worse_rows=int(np.count_nonzero(score[a] < score[b])),
              source_family_clusters=26) for i, (a, b) in enumerate(pairs)}
    statistics = {n: real.statistics(p, truth) for n, p in predictions.items()}
    partition = previous.grouping.partition(query, event)
    nx, ny = query[:, 2] - event[:, 0] + event[:, 2], query[:, 3] - event[:, 1] + event[:, 3]
    partition.update(source_port=ports[:, 0], target_port=ports[:, 1], nominal_direction=2 * (nx < 0) + (ny < 0))
    grouped = {family: {str(int(v)): {n: real.statistics(p[values == v], truth[values == v])
               for n, p in predictions.items()} for v in np.unique(values)} for family, values in partition.items()}
    gates = {}
    for name in names:
        short = [grouped["distance"][str(b)][name]["accuracy_pp"] -
                 grouped["distance"][str(b)]["exp354"]["accuracy_pp"] for b in (0, 1)]
        comparison = paired[name + "-exp354"]
        gates[name] = bool(statistics[name]["accuracy_pp"] >= 99.15 and comparison["delta_pp"] >= .05 and
                           comparison["ci95_pp"][0] > 0 and min(short) >= -.10)
    write(ROOT / "groups.json", grouped)
    write(ROOT / "report.json", dict(rows=ROWS, port_pairs=LEFT, statistics=statistics, paired=paired,
          quality_gates=gates, all_full_port=True, complete_geometry_equality=True, complete_residual_equality=True,
          development_only=True, final_elf_verified=False, production_cpu_verified=False, single_call_100ns_verified=False))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp575")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (2400, 2400))
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    training = read(SOURCE / "training.json")
    audit = read("validation/results/exp575/saved-evidence-audit.json")
    assert audit["all_saved_checks"]
    real.check(SOURCE / "training.json", audit["training"])
    models = [m for m in training["models"] if m["fixed_l1_gate_passed"]]
    assert models
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT / "protocol-evaluation.md")
    (ROOT / "installed-xgboost-help.txt").write_text(str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__)
    previous.ROOT, previous.BUILD = ROOT, BUILD
    previous.previous.ROOT, previous.trees.BUILD = ROOT, BUILD
    compile_decoders()
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = previous.previous.data()
    assert matrix.shape == (ROWS, 53) and read(ROOT / "input.json")["unique_rows"] == ROWS
    previous.features(BUILD / "features.f32", matrix)
    folds.tofile(BUILD / "folds.u8")
    center = np.load("offline/build/exp575/center.npy")
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
    old = read("../exp557/validation/results/exp557/G32.json")
    gpath = Path("../exp557") / old["predictions"]["path"]
    real.check(gpath, old["predictions"])
    predictions = {"exp354": production, "G32": np.fromfile(gpath, "<i4").astype(np.int64), "Q-base": oracle}
    assert predictions["G32"].shape == (ROWS,)
    assert abs(real.statistics(predictions["G32"], labels[:, 0])["accuracy_pp"] - old["statistics"]["accuracy_pp"]) < 1e-10
    frozen = [Path(__file__), PLAN, Path("tests/exp575_geometry_decode.cpp"), Path("tests/exp554_real_kernel_function.cpp"),
              SOURCE / "training.json", Path("validation/results/exp575/saved-evidence-audit.json"), ROOT / "input.json", gpath,
              Path("doc/eda比赛文件/arch/SRB_Gap.json")]
    frozen += list(Path("validation").glob("*.py"))
    write(ROOT / "evaluation-freeze.json", dict(files=[identity(p) for p in dict.fromkeys(frozen)],
          seed=SEED, port_pairs=LEFT, full_port_required=True, disk_free_start=free))
    bases = {}
    for model in models:
        name = model["name"]
        bases[name] = geometry(model, center, pair, column, scale, trend, zero, cycle, event, labels[:, 2])
        predictions[name + "-base"] = bases[name] + labels[:, 2]
        predictions[name + "-32"] = previous.train(name + "-32", bases[name], matrix, folds, labels, 32)
    best = max(bases, key=lambda n: real.statistics(predictions[n + "-32"], labels[:, 0])["accuracy_pp"])
    best_score = real.statistics(predictions[best + "-32"], labels[:, 0])["accuracy_pp"]
    if best_score >= 98.5:
        name = best + "-128"
        predictions[name] = previous.train(name, bases[best], matrix, folds, labels, 128)
        best_score = max(best_score, real.statistics(predictions[name], labels[:, 0])["accuracy_pp"])
    if best_score >= 99.15:
        extra = np.column_stack((matrix, bases[best])).astype("<f4")
        previous.features(BUILD / "features54.f32", extra)
        for suffix, rounds, eta in (("-tiny8", 8, .3), ("-tiny16", 16, .2)):
            predictions[best + suffix] = previous.train(best + suffix, bases[best], extra, folds, labels, rounds, 4, eta)
    report(predictions, labels[:, 0], query, event, ports)
    write(ROOT / "cost.json", dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free, production_timing=False))
    print("EXP575_COMPLETE_FULL_PORT_EVALUATION", flush=True)


if __name__ == "__main__":
    main()
