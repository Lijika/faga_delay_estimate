#!/usr/bin/env python3
"""Train full-port local spaces using complete reconstruction assignments on l7."""
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np
import xgboost as xgb

import exp557_conditional_geometry as local
from exp569_joint_geometry import quantize

ROOT, BUILD = Path("validation/results/exp571"), Path("build/exp571")
PLAN = Path("experiment/实验571-完整重建路由的局部子空间.md")
LEFT, RIGHT, RANK, CAP, SEED = 59904, 264960, 16, 32, 20261021571
read, write, identity, save = local.read, local.write, local.identity, local.save


def source_arrays():
    training = read("../exp557/validation/results/exp557/training.json")
    router = read("../exp557/validation/results/exp557/router.json")
    assert training["all_training_checks"] and training["shape"] == [LEFT, RIGHT]
    records = [training["center"], *training["models"][0]["assets"], *router["assets"]]
    wanted = {"center", "G-left", "G-right", "router-features", "router-target"}
    arrays, assets = {}, []
    for record in records:
        path = Path("../exp557") / record["path"]
        if path.stem not in wanted:
            continue
        actual = identity(path)
        assert (actual["bytes"], actual["sha256"]) == (record["bytes"], record["sha256"])
        arrays[path.stem] = np.load(path)
        assets.append(actual)
    assert set(arrays) == wanted
    assert arrays["center"].shape == (LEFT,)
    assert arrays["G-left"].shape == (1, LEFT, 96)
    assert arrays["G-right"].shape == arrays["router-target"].shape == (RIGHT, 96)
    assert arrays["router-features"].shape == (RIGHT, 14)
    return arrays, assets


def initialize(features, target):
    assert xgb.__version__ == "3.0.5"
    (ROOT / "installed-library-help.txt").write_text(
        f"xgboost={xgb.__version__} numpy={np.__version__}\n" +
        str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__ + "\n" +
        str(inspect.signature(xgb.Booster.predict)) + "\n" + xgb.Booster.predict.__doc__)
    params = dict(objective="reg:squarederror", booster="gbtree", tree_method="hist", device="cpu",
                  multi_strategy="multi_output_tree", num_parallel_tree=1, max_depth=5, eta=1.,
                  base_score=0., reg_lambda=0., reg_alpha=0., gamma=0., min_child_weight=128.,
                  max_bin=256, subsample=1., colsample_bytree=1., seed=SEED, nthread=8)
    matrix = xgb.DMatrix(features, label=target, nthread=8)
    booster = xgb.train(params, matrix, num_boost_round=1)
    path = BUILD / "initial-router.json"
    booster.save_model(path)
    (ROOT / "initial-router-config.json").write_text(booster.save_config() + "\n")
    native = booster.predict(matrix, pred_leaf=True).reshape(-1).astype("<i4")
    assert native.shape == (RIGHT,)
    leaves = np.unique(native)
    regions = np.searchsorted(leaves, native).astype("u1")
    counts = np.bincount(regions)
    assert 1 <= len(counts) <= CAP and counts.min() >= RANK + 16
    write(ROOT / "initial-router.json", dict(params=params, leaves=leaves.tolist(),
          region_counts=counts.tolist(), model=identity(path),
          assets=[save("initial-native-leaf", native), save("initial-regions", regions)]))
    print("EXP571_INITIAL_REGIONS", counts.tolist(), flush=True)
    return regions


def diagnostics(values, center, left, right, regions, name):
    groups = len(left)
    keys = [np.flatnonzero(regions == g) for g in range(groups)]
    coordinates = local.old.coordinates()
    bands = np.searchsorted([1, 4, 16], coordinates[:, 3] + coordinates[:, 4], side="right")
    column_energy = np.zeros(RIGHT)
    squared, absolute, counts = np.zeros(4), np.zeros(4), np.zeros(4, dtype=np.int64)
    started, cpu = time.monotonic(), time.process_time()
    for g in range(groups):
        selected = keys[g]
        if not len(selected):
            continue
        for start, block in local.blocks(values, center, selected):
            column_energy[selected] += np.square(block).sum(axis=0)
            residual = block - left[g, start:start + len(block)] @ right[selected].T
            for band in range(4):
                part = residual[:, bands[selected] == band]
                squared[band] += float(np.square(part).sum())
                absolute[band] += float(np.abs(part).sum())
                counts[band] += part.size
    assert counts.sum() == LEFT * RIGHT
    record = dict(name=name, full_port_pairs=LEFT, geometries=RIGHT, values=int(counts.sum()),
                  squared=float(squared.sum()), absolute=float(absolute.sum()),
                  by_quotient_sum=[dict(band=b, values=int(counts[b]), squared=float(squared[b]),
                                      absolute=float(absolute[b])) for b in range(4)],
                  input_energy=float(column_energy.sum()), cpu_s=time.process_time() - cpu,
                  wall_s=time.monotonic() - started, training_diagnostic_only=True)
    assert np.isfinite(column_energy).all() and (column_energy >= 0).all()
    write(ROOT / (name + "-diagnostics.json"), record)
    print("EXP571_DIAGNOSTICS", name, record["squared"], record["absolute"], flush=True)
    return record, column_energy


def export_model(name, left, right, regions, residual):
    groups = len(left)
    assert left.shape == (groups, LEFT, RANK) and right.shape == (RIGHT, RANK)
    assert regions.shape == (RIGHT,) and regions.dtype == np.dtype("u1") and regions.max() < groups
    assert np.isfinite(left).all() and np.isfinite(right).all()
    for basis in left:
        assert np.abs(basis.T @ basis - np.eye(RANK)).max() < 1e-10
    li, le = quantize(left.reshape(-1, RANK), (0,))
    ri, re = quantize(right, (0,))
    li = li.reshape(groups, LEFT, RANK)
    exponent = le.astype(np.int64) + re
    minimum = int(exponent.min())
    lm = np.abs(li.astype(np.int32)).max(axis=(0, 1))
    rm = np.abs(ri.astype(np.int32)).max(axis=0)
    bound = sum((int(a) * int(b)) << int(e - minimum) for a, b, e in zip(lm, rm, exponent))
    assert bound < 2**53 and minimum > -1022 and exponent.max() < 970
    arrays = {name + "-left": left, name + "-right": right, name + "-regions": regions,
              name + "-left-integers": li, name + "-right-integers": ri,
              name + "-left-exponent": le, name + "-right-exponent": re}
    model = dict(name=name, rank=RANK, regions=groups, port_pairs=LEFT, geometries=RIGHT,
                 region_counts=np.bincount(regions, minlength=groups).tolist(),
                 residual_energy=residual, assets=[save(key, value) for key, value in arrays.items()],
                 integer_sum_bound=bound, common_exponent=minimum,
                 table_bytes=li.nbytes + ri.nbytes + regions.nbytes + 2 * LEFT + le.nbytes + re.nbytes)
    assert model["table_bytes"] <= 70_205_312
    write(ROOT / (name + "-model.json"), model)
    return model


def improve(values, center, left, right, regions, column_energy, residual, rng):
    groups = len(left)
    energy, records = float(column_energy.sum()), []
    all_keys, rows = np.arange(RIGHT), np.arange(RIGHT)
    for sweep in range(1, 3):
        before = residual
        factor = left.transpose(1, 0, 2).reshape(LEFT, groups * RANK)
        projected, projection = local.multiply(values, center, all_keys, factor, True, f"route-{sweep}")
        del factor
        projected = projected.reshape(RIGHT, groups, RANK)
        difference = float(np.abs(projected[rows, regions] - right).max())
        assert difference <= 1e-9 * max(1., float(np.abs(right).max()))
        score = np.square(projected).sum(axis=2)
        current = score[rows, regions]
        best = np.argmax(score, axis=1)
        gain = score[rows, best] - current
        move = gain > 1e-12 * np.maximum(1., np.maximum(np.abs(current), score[rows, best]))
        assigned = np.where(move, best, regions).astype("u1")
        route_residual = energy - float(score[rows, assigned].sum())
        assert abs(energy - float(current.sum()) - before) <= 1e-9 * max(1., energy)
        assert -1e-9 * energy <= route_residual <= before + 1e-9 * max(1., energy)
        new_left, new_right, group_records = left.copy(), np.empty_like(right), []
        residual = 0.
        for g in range(groups):
            keys = np.flatnonzero(assigned == g)
            old_right = projected[keys, g]
            old_error = float(column_energy[keys].sum() - np.square(old_right).sum())
            new_right[keys] = old_right
            accepted, fitted = False, None
            if len(keys) >= RANK + 16:
                candidate_left, candidate_right, fitted = local.fit(
                    values, center, keys, RANK, f"adaptive-{sweep}-{g:02d}", rng)
                if fitted["residual_energy"] <= old_error:
                    new_left[g], new_right[keys] = candidate_left, candidate_right
                    accepted = True
            group_error = fitted["residual_energy"] if accepted else old_error
            residual += group_error
            group_records.append(dict(group=g, keys=len(keys), old_residual=old_error,
                                      accepted=accepted, residual=group_error, fit=fitted))
        assert -1e-9 * energy <= residual <= route_residual + 1e-9 * max(1., energy)
        improvement = (before - residual) / max(1., before)
        record = dict(sweep=sweep, before=before, after_assignment=route_residual,
                      residual_energy=residual, relative_improvement=improvement,
                      changed_geometries=int(move.sum()), current_projection_max_error=difference,
                      projection=projection, groups=group_records)
        write(ROOT / f"sweep-{sweep}.json", record)
        records.append(record)
        left, right, regions = new_left, new_right, assigned
        del projected, score
        export_model(f"checkpoint-{sweep}", left, right, regions, residual)
        print("EXP571_SWEEP", sweep, residual, improvement, int(move.sum()), flush=True)
        if improvement < .005:
            break
    write(ROOT / "optimization.json", dict(records=records, sweeps=len(records),
          stop_reason="improvement_below_0.5_percent" if records[-1]["relative_improvement"] < .005 else "two_sweeps"))
    return left, right, regions, residual


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp571")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    assert not ROOT.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    local.ROOT, local.BUILD, local.old.ROOT = ROOT, BUILD, ROOT
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    shutil.copyfile(local.old.PREPARATION / "mapping.json", ROOT / "mapping.json")
    arrays, assets = source_arrays()
    files = [Path(__file__), PLAN, ROOT / "protocol-original.md", ROOT / "mapping.json"]
    files += [Path("validation") / (name + ".py") for name in (
        "exp557_conditional_geometry", "exp569_joint_geometry", "exp568_additive_geometry",
        "exp567_leaf_dictionary", "exp510_pair_geometry", "exp500_split_residues",
        "exp504_tail_rectangles", "exp208_nominal_parent_tree")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files], source_assets=assets,
          source_ports=208, target_ports=288, port_pairs=LEFT, shape=[LEFT, RIGHT],
          seed=SEED, cpu_budget_s=18000, rank=RANK, maximum_regions=CAP,
          hostname=socket.gethostname(), disk_free_start=free))
    values = local.old.materialize(ROOT / "materialization.json")
    assert read(ROOT / "materialization.json")["matrix_sha256"] == \
        "c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86"
    center = arrays.pop("center")
    center_asset = save("center", center)
    regions = initialize(arrays.pop("router-features"), arrays.pop("router-target"))
    baseline, baseline_energy = diagnostics(values, center, arrays.pop("G-left"), arrays.pop("G-right"),
                                             np.zeros(RIGHT, dtype="u1"), "G-reference")
    assert abs(baseline["squared"] - 1203634.579565436) <= 1e-8 * baseline["input_energy"]
    rng = np.random.default_rng(SEED)
    left = np.empty((int(regions.max()) + 1, LEFT, RANK))
    right = np.empty((RIGHT, RANK))
    residual = 0.
    for g in range(len(left)):
        keys = np.flatnonzero(regions == g)
        left[g], right[keys], record = local.fit(values, center, keys, RANK, f"initial-{g:02d}", rng)
        residual += record["residual_energy"]
    initial, column_energy = diagnostics(values, center, left, right, regions, "I")
    assert np.allclose(column_energy, baseline_energy, rtol=1e-12, atol=1e-8)
    assert abs(initial["squared"] - residual) <= 1e-9 * initial["input_energy"]
    models = [export_model("I", left, right, regions, residual)]
    left, right, regions, residual = improve(values, center, left, right, regions, column_energy, residual, rng)
    final, check_energy = diagnostics(values, center, left, right, regions, "K")
    assert np.allclose(check_energy, column_energy, rtol=1e-12, atol=1e-8)
    assert abs(final["squared"] - residual) <= 1e-9 * final["input_energy"]
    models.append(export_model("K", left, right, regions, residual))
    reduction = 1 - final["absolute"] / baseline["absolute"]
    advance = bool(reduction >= .02)
    new_bytes = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert new_bytes < 1_500_000_000
    write(ROOT / "training.json", dict(all_training_checks=True, shape=[LEFT, RIGHT],
          source_ports=208, target_ports=288, port_pairs=LEFT, models=models, center=center_asset,
          reference=baseline, initial=initial, final=final, relative_l1_reduction_vs_G=reduction,
          fixed_l1_gate_passed=advance, independent_tests=False, real_request_scoring_started=False,
          new_asset_bytes=new_bytes, freeze=identity(ROOT / "freeze.json"),
          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP571_COMPLETE_OFFLINE_TRAINING", reduction, advance, flush=True)


if __name__ == "__main__":
    main()
