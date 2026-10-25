#!/usr/bin/env python3
"""Cross-fit routed residuals with a frozen background on the full-port r9 1M."""
import gc
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import time

import numpy as np
import xgboost as xgb

import exp557_evaluate as previous

ROOT, BUILD = Path("validation/results/exp576"), Path("build/exp576")
OLD = Path("../exp575")
SOURCE = OLD / "validation/results/exp575-evaluation"
PLAN = Path("experiment/实验576-共享几何路由的分组小残差模型.md")
ROWS, SEED = 1000000, 20261021576
real, trees = previous.real, previous.trees
read, write, identity = previous.read, previous.write, previous.identity


def compile_decoders():
    helped = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in helped
    (ROOT / "compiler-help.txt").write_text(helped)
    for source, name in (("tests/exp576_routed_residual.cpp", "routed-predict"),
                         ("tests/exp554_real_kernel_function.cpp", "original-predict")):
        command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64", "-mtune=generic",
                   "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", source,
                   "-o", str(BUILD / name)]
        result = subprocess.run(command, capture_output=True, text=True)
        write(ROOT / (name + "-compiler.json"), dict(command=command, exit_code=result.returncode,
              stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0 and not result.stderr
        help_run = subprocess.run([str(BUILD / name), "--help"], capture_output=True, text=True)
        assert help_run.returncode == 0 and help_run.stdout.startswith("usage:")
    write(ROOT / "compiler.json", dict(version=subprocess.check_output(["g++", "--version"], text=True)))


def model_list(name, groups, paths):
    assert len(paths) == 3 * groups
    path = BUILD / (name + "-models.txt")
    with path.open("x") as stream:
        stream.write(str(groups) + "\n" + "".join(str(p) + "\n" for p in paths))
    return path


def independent(name, listing, raw):
    output = BUILD / (name + "-independent.f32")
    command = [str(BUILD / "routed-predict"), str(BUILD / "features.f32"), str(BUILD / "folds.u8"),
               str(BUILD / "routes.u8"), str(listing), str(output)]
    record = previous.run(command, name + "-independent")
    restored = np.fromfile(output, "<f4")
    assert restored.shape == (ROWS,) and np.array_equal(raw.view("u4"), restored.view("u4"))
    counters = read(ROOT / (name + "-independent.stdout"))
    assert counters["port_pairs"] == 59904 and counters["kernel_allocations"] == 0
    return dict(run=record, counters=counters, output=identity(output), complete_bitwise_equal=True)


def train(name, groups, rounds, depth, eta, base, matrix, folds, routes, labels, pair):
    truth, d0, mandatory = labels[:, :3].T
    weights = (1000 / np.maximum(d0 + mandatory, 128)).astype("<f4")
    params = dict(objective="reg:absoluteerror", tree_method="hist", max_depth=depth, eta=eta,
                  max_bin=256, base_score=0, subsample=1., colsample_bytree=1.,
                  seed=previous.previous.SEED, nthread=4)
    raw, records, paths = np.empty(ROWS, dtype="<f4"), [], []
    for fold in range(3):
        for route in range(groups):
            mask = np.ones(ROWS, dtype=bool) if groups == 1 else routes == route
            learn, test = (folds != fold) & mask, (folds == fold) & mask
            assert learn.any() and test.any()
            started, cpu = time.monotonic(), time.process_time()
            dm = xgb.DMatrix(matrix[learn], label=(d0 - base)[learn].astype("<f4"),
                             weight=weights[learn], nthread=4)
            dt = xgb.DMatrix(matrix[test], nthread=4)
            booster = xgb.train(params, dm, num_boost_round=rounds)
            stem = f"{name}-{fold}-{route}"
            assets = trees.export_model(booster, stem)
            restored = xgb.Booster(); restored.load_model(BUILD / (stem + ".json"))
            native, back = booster.predict(dt), restored.predict(dt)
            assert np.isfinite(native).all() and np.array_equal(native.view("u4"), back.view("u4"))
            raw[test] = native
            fitted = trees.decode(booster.predict(dm), base[learn], mandatory[learn])
            predicted = trees.decode(native, base[test], mandatory[test])
            record = dict(fold=fold, route=route, groups=groups, params=params, rounds=rounds, assets=assets,
                  train_rows=int(learn.sum()), test_rows=int(test.sum()),
                  train_port_pairs=int(np.unique(pair[learn]).size),
                  test_port_pairs=int(np.unique(pair[test]).size),
                  train=real.statistics(fitted, truth[learn]), test=real.statistics(predicted, truth[test]),
                  cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started)
            write(ROOT / (stem + ".json"), record)
            records.append(record); paths.append(BUILD / (stem + ".bin"))
            print("EXP576_TRAINED", name, fold, route, record["cpu_s"], flush=True)
            del dm, dt, booster, restored
            gc.collect()
    assert np.isfinite(raw).all()
    raw.tofile(BUILD / (name + ".f32"))
    listing = model_list(name, groups, paths)
    decoded = independent(name, listing, raw)
    pred = trees.decode(raw, base, mandatory)
    pred.astype("<i4").tofile(BUILD / (name + ".i32"))
    sizes = [sum(r["assets"]["binary"]["bytes"] for r in records if r["fold"] == k) for k in range(3)]
    write(ROOT / (name + ".json"), dict(name=name, records=records, statistics=real.statistics(pred, truth),
          training_accuracy_pp=sum(r["train"]["accuracy_pp"] * r["train_rows"] for r in records) /
                               sum(r["train_rows"] for r in records),
          raw=identity(BUILD / (name + ".f32")), predictions=identity(BUILD / (name + ".i32")),
          decoder=decoded, fold_model_bytes=sizes, model_bytes_max=max(sizes), final_elf_verified=False))
    print("EXP576_RESULT", name, real.statistics(pred, truth)["accuracy_pp"], flush=True)
    return pred, listing


def report(predictions, truth, query, event, ports, routes):
    score = {n: real.points(p, truth) for n, p in predictions.items()}
    names = ("S8", "R8", "R32")
    pairs = [(n, "exp354") for n in names] + [("R8", "S8"), ("R32", "S32")]
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
              better_rows=int(np.count_nonzero(score[a] > score[b])),
              worse_rows=int(np.count_nonzero(score[a] < score[b])), source_family_clusters=26)
              for i, (a, b) in enumerate(pairs)}
    statistics = {n: real.statistics(p, truth) for n, p in predictions.items()}
    partition = previous.grouping.partition(query, event)
    partition.update(source_port=ports[:, 0], target_port=ports[:, 1],
                     nominal_direction=routes // 4, nominal_morphology=routes % 4, route=routes)
    grouped = {family: {str(int(v)): {n: real.statistics(p[values == v], truth[values == v])
               for n, p in predictions.items()} for v in np.unique(values)} for family, values in partition.items()}
    quality = {}
    for name in names:
        comparison = paired[name + "-exp354"]
        short = [grouped["distance"][str(k)][name]["accuracy_pp"] -
                 grouped["distance"][str(k)]["exp354"]["accuracy_pp"] for k in (0, 1)]
        quality[name] = bool(statistics[name]["accuracy_pp"] >= 99.15 and comparison["delta_pp"] >= .05 and
                             comparison["ci95_pp"][0] > 0 and min(short) >= -.10)
    mechanism = {name: bool(paired[name]["delta_pp"] >= .05 and paired[name]["ci95_pp"][0] > 0)
                 for name in ("R8-S8", "R32-S32")}
    write(ROOT / "groups.json", grouped)
    write(ROOT / "report.json", dict(rows=ROWS, port_pairs=59904, statistics=statistics, paired=paired,
          quality_gates=quality, mechanism_gates=mechanism,
          fixed_configuration_expansion_stopped=bool(max(statistics[n]["accuracy_pp"] for n in names) < 98.5),
          all_full_port=True, complete_residual_equality=True, background_frozen=True,
          development_only=True, final_elf_verified=False, production_cpu_verified=False,
          single_call_100ns_verified=False))


def timing(listings):
    comparisons = []
    deletions = []
    for shared, routed in (("S8", "R8"), ("S32", "R32")):
        runs = {shared: [], routed: []}
        for repeat in range(8):
            order = (shared, routed) if repeat % 2 == 0 else (routed, shared)
            for name in order:
                tag = f"timing-{shared}-{repeat}-{name}"
                output = BUILD / (tag + ".f32")
                command = [str(BUILD / "routed-predict"), str(BUILD / "features.f32"),
                           str(BUILD / "folds.u8"), str(BUILD / "routes.u8"), str(listings[name]), str(output)]
                record = previous.run(command, tag)
                counters = read(ROOT / (tag + ".stdout"))
                assert counters["rows"] == ROWS and counters["kernel_allocations"] == 0
                asset = identity(output)
                expected = identity(BUILD / (name + ".f32"))
                assert asset["sha256"] == expected["sha256"] and asset["bytes"] == expected["bytes"]
                if repeat:
                    runs[name].append(dict(repeat=repeat, kernel_cpu_s=counters["kernel_cpu_s"],
                                           process_cpu_s=record["cpu_s"]))
                deletions.append(dict(file=asset, retained=expected, rebuild=command))
                print("EXP576_REMOVE_DUPLICATE", str(output), flush=True)
                output.unlink()
        result = dict(shared=shared, routed=routed, runs=runs, warmups_per_model=1,
                      pairs=7, includes_route_arithmetic=True, production_timing=False)
        rng = np.random.default_rng(SEED)
        for metric in ("kernel_cpu_s", "process_cpu_s"):
            a, b = [np.asarray([r[metric] for r in runs[n]]) for n in (shared, routed)]
            gain = a - b
            samples = rng.integers(7, size=(2000, 7))
            interval = np.quantile(gain[samples].mean(axis=1), [.025, .975])
            result[metric] = dict(shared_mean=float(a.mean()), routed_mean=float(b.mean()),
                  shared_minus_routed=float(gain.mean()), ci95_s=interval.tolist(),
                  routed_speed_gate_passed=bool(interval[0] > 0))
        comparisons.append(result)
    write(ROOT / "timing.json", dict(comparisons=comparisons, complete_outputs_sha_equal=True,
          precomputed_features=True, csv_and_background_cost_included=False, production_timing=False))
    write(ROOT / "duplicate-cleanup.json", dict(files=deletions, bytes_released=sum(r["file"]["bytes"] for r in deletions)))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp576")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (2400, 2400))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    assert Path("doc/eda比赛文件/arch/SRB_Gap.json").is_file()
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol.md")
    (ROOT / "installed-xgboost-help.txt").write_text(str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__)
    previous.ROOT, previous.BUILD, previous.previous.ROOT, trees.BUILD = ROOT, BUILD, ROOT, BUILD
    compile_decoders()
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = previous.previous.data()
    assert matrix.shape == (ROWS, 53) and np.isfinite(matrix).all()
    assert np.array_equal(matrix[:, :4].astype(np.int32), query[:, 4:8])
    port_maps = []
    for side, start, count in ((0, 4, 208), (1, 6, 288)):
        mapping = np.unique(np.column_stack((ports[:, side], query[:, start:start + 2])), axis=0)
        assert mapping.shape == (count, 3) and np.array_equal(mapping[:, 0], np.arange(count))
        assert np.all((mapping[:, 1] >= 0) & (mapping[:, 1] < count // 8))
        assert np.all((mapping[:, 2] >= 0) & (mapping[:, 2] < 8))
        assert np.array_equal(np.sort(mapping[:, 1] * 8 + mapping[:, 2]), np.arange(count))
        port_maps.append(mapping.tolist())
    # Background indices follow the saved port order; coverage uses family/lane coordinates.
    write(ROOT / "port-mapping.json", dict(source=port_maps[0], target=port_maps[1], bijective=True))
    pair = ports[:, 0] * 288 + ports[:, 1]
    x, y = query[:, 2] - event[:, 0] + event[:, 2], query[:, 3] - event[:, 1] + event[:, 3]
    assert np.array_equal(matrix[:, 8] + matrix[:, 6], x)
    assert np.array_equal(matrix[:, 9] + matrix[:, 7], y)
    routes = (4 * (2 * (x < 0) + (y < 0)) + 2 * (np.abs(x) >= 20) + (np.abs(y) >= 24)).astype("u1")
    assert len(np.unique(routes)) == 16 and read(ROOT / "input.json")["unique_rows"] == ROWS
    previous.features(BUILD / "features.f32", matrix)
    folds.tofile(BUILD / "folds.u8"); routes.tofile(BUILD / "routes.u8")
    old, background = read(SOURCE / "N192-32.json"), read(SOURCE / "N192-geometry.json")
    files = [Path(__file__), PLAN, Path("doc/eda比赛文件/arch/SRB_Gap.json"),
             ROOT / "input.json", ROOT / "port-mapping.json",
             SOURCE / "N192-32.json", SOURCE / "N192-geometry.json"]
    for asset in (background["base"], background["model"], old["raw"], old["predictions"]):
        path = OLD / asset["path"]
        real.check(path, asset); files.append(path)
    base = np.fromfile(OLD / background["base"]["path"], "<i4").astype(np.int64)
    shared_raw = np.fromfile(OLD / old["raw"]["path"], "<f4")
    shared_pred = np.fromfile(OLD / old["predictions"]["path"], "<i4").astype(np.int64)
    assert base.shape == shared_raw.shape == shared_pred.shape == (ROWS,)
    assert np.array_equal(trees.decode(shared_raw, base, labels[:, 2]), shared_pred)
    assert abs(real.statistics(shared_pred, labels[:, 0])["accuracy_pp"] - old["statistics"]["accuracy_pp"]) < 1e-10
    paths = []
    for record in old["records"]:
        assert record["fold"] == len(paths)
        asset = record["assets"]["binary"]
        path = OLD / asset["path"]
        real.check(path, asset); files.append(path); paths.append(path)
    listing = model_list("S32", 1, paths)
    shared_raw.tofile(BUILD / "S32.f32")
    write(ROOT / "S32-independent.json", independent("S32", listing, shared_raw))
    output = BUILD / "original-default.f32"
    previous.run([str(BUILD / "original-predict"), str(BUILD / "features.f32"), str(BUILD / "folds.u8")]
                 + [str(p) for p in paths] + [str(output)], "original-default")
    assert identity(output)["sha256"] == identity(BUILD / "S32.f32")["sha256"]
    files += list(Path("validation").glob("*.py")) + list(Path("tests").glob("*.cpp"))
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in dict.fromkeys(files)], seed=SEED,
          full_port_required=True, disk_free_start=free, original_default_complete_bitwise_equal=True,
          background_accounted_bytes=86685696, background_blob=background["model"]))
    predictions = {"exp354": production, "Q-base": oracle, "N192-base": base + labels[:, 2], "S32": shared_pred}
    listings = {"S32": listing}
    for name, groups, rounds, depth, eta in (("S8", 1, 8, 4, .3), ("R8", 16, 8, 4, .3), ("R32", 16, 32, 8, .1)):
        predictions[name], listings[name] = train(name, groups, rounds, depth, eta,
              base, matrix, folds, routes, labels, pair)
    report(predictions, labels[:, 0], query, event, ports, routes)
    timing(listings)
    added = sum(p.stat().st_size for directory in (ROOT, BUILD) for p in directory.rglob("*") if p.is_file())
    assert added < 1000000000
    write(ROOT / "cost.json", dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, added_bytes=added,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free, production_timing=False))
    print("EXP576_COMPLETE_FULL_PORT_ROUTED_RESIDUAL", flush=True)


if __name__ == "__main__":
    main()
