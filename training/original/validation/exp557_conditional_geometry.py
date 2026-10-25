#!/usr/bin/env python3
"""Offline complete-port centered geometry factors; independent tests run on r9."""
import hashlib
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np
import scipy
from scipy.linalg import svd
import xgboost as xgb

import exp510_pair_geometry as old

ROOT, BUILD = Path("validation/results/exp557"), Path("build/exp557")
PLAN = Path("experiment/实验557-XGBoost条件几何空间与完整候选.md")
LEFT, RIGHT, BLOCK, SEED = 59904, 264960, 288, 20261021557
DENOM = old.DENOM.astype(np.float64)
read, write, identity = old.read, old.write, old.identity


def save(name, value):
    path = BUILD / (name + ".npy")
    assert not path.exists()
    np.save(path, value)
    assert np.array_equal(value, np.load(path, mmap_mode="r"))
    return identity(path)


def blocks(values, center, keys):
    for start in range(0, LEFT, BLOCK):
        block = values[start:start + BLOCK, :][:, keys].astype(np.float64)
        block -= center[start:start + len(block), None]
        block /= DENOM[keys]
        yield start, block


def multiply(values, center, keys, factor, transpose, label):
    started, cpu = time.monotonic(), time.process_time()
    result = np.zeros((len(keys) if transpose else LEFT, factor.shape[1]), dtype=np.float64)
    assert factor.shape[0] == (LEFT if transpose else len(keys))
    for start, block in blocks(values, center, keys):
        if transpose:
            result += block.T @ factor[start:start + len(block)]
        else:
            result[start:start + len(block)] = block @ factor
    assert np.isfinite(result).all()
    record = dict(label=label, transpose=transpose, cpu_s=time.process_time() - cpu,
                  wall_s=time.monotonic() - started)
    print("EXP557_MULTIPLY", label, record["wall_s"], flush=True)
    write(ROOT / (label + "-multiply.json"), record)
    return result, record


def fit(values, center, keys, rank, name, rng):
    width = rank + 16
    omega = rng.standard_normal((len(keys), width))
    product = np.empty((LEFT, width), dtype=np.float64)
    energy = 0.
    for start, block in blocks(values, center, keys):
        product[start:start + len(block)] = block @ omega
        energy += float(np.square(block).sum())
    del omega
    basis, error = old.orthogonal(product)
    del product
    errors, passes = [error], []
    product, record = multiply(values, center, keys, basis, True, name + "-power-T")
    passes.append(record)
    side, error = old.orthogonal(product)
    errors.append(error)
    del product
    product, record = multiply(values, center, keys, side, False, name + "-power-F")
    passes.append(record)
    del side
    basis, error = old.orthogonal(product)
    errors.append(error)
    del product
    projected, record = multiply(values, center, keys, basis, True, name + "-small")
    passes.append(record)
    small_energy = float(np.square(projected).sum())
    u, singular, vt = svd(projected.T, full_matrices=False, check_finite=True, lapack_driver="gesdd")
    assert abs(small_energy - float(np.square(singular).sum())) <= 1e-9 * max(1., small_energy)
    left = basis @ u[:, :rank]
    signs = np.where(left[np.argmax(np.abs(left), axis=0), np.arange(rank)] < 0, -1, 1)
    left *= signs
    errors.append(float(np.abs(left.T @ left - np.eye(rank)).max()))
    del basis, projected, u
    right, record = multiply(values, center, keys, left, True, name + "-projection")
    passes.append(record)
    expected = (vt[:rank].T * singular[:rank]) * signs
    projection_error = float(np.max(np.abs(right - expected)))
    assert projection_error <= 1e-9 * max(1., float(singular[0]))
    del vt, expected
    squared = 0.
    for start, block in blocks(values, center, keys):
        residual = block - left[start:start + len(block)] @ right.T
        squared += float(np.square(residual).sum())
    remainder = energy - float(np.square(right).sum())
    assert abs(squared - remainder) <= 1e-9 * max(1., energy)
    assert max(errors) <= 1e-10
    record = dict(name=name, keys=len(keys), port_pairs=LEFT, rank=rank, range_width=width,
                  input_energy=energy, residual_energy=squared, energy_difference=remainder,
                  projection_max_error=projection_error, orthogonal_errors=errors,
                  singular_values=singular.tolist(), passes=passes)
    write(ROOT / (name + ".json"), record)
    print("EXP557_REGION_TRAINED", name, flush=True)
    return left, right, record


def router(center, values):
    assert xgb.__version__ == "3.0.5"
    with (ROOT / "installed-library-help.txt").open("a") as stream:
        stream.write(f"\nxgboost={xgb.__version__}\n" + str(inspect.signature(xgb.train)) + "\n" +
                     xgb.train.__doc__ + "\n" + str(inspect.signature(xgb.DMatrix)) + "\n" +
                     xgb.DMatrix.__doc__ + "\n" + str(inspect.signature(xgb.Booster.predict)) + "\n" +
                     xgb.Booster.predict.__doc__)
    inputs = []
    training = read("../exp510/validation/results/exp510/training.json")
    for record in training["factors"]:
        actual = identity(Path("../exp510") / record["path"])
        assert (actual["bytes"], actual["sha256"]) == (record["bytes"], record["sha256"])
        inputs.append(actual)
    left = np.load("../exp510/build/exp510/left.npy")
    right = np.load("../exp510/build/exp510/right.npy")
    assert left.shape == (LEFT, 96) and right.shape == (RIGHT, 96)
    target = right - (left.T @ center)[None, :] / DENOM[:, None]
    independent, projection = multiply(values, center, np.arange(RIGHT), left, True, "centered-old-projection")
    difference = float(np.max(np.abs(independent - target)))
    assert difference <= 1e-9 * max(1., float(np.abs(target).max()))
    del independent, left, right
    d, rx, ry, qx, qy = old.coordinates().T
    x, y = rx + 10 * qx, ry + 12 * qy
    fields = dict(direction=d, neg_dx=d // 2, neg_dy=d % 2, rx=rx, ry=ry, qx=qx, qy=qy,
                  x=x, y=y, quotient_sum=qx + qy, ratio_x=qx / (1 + qx + qy),
                  slope=qx / (1 + qy), axis_x=qx == 0, axis_y=qy == 0)
    features = np.column_stack(list(fields.values())).astype("<f4")
    target = target.astype("<f4")
    assert np.isfinite(features).all() and np.isfinite(target).all()
    assets = [save("router-features", features), save("router-target", target)]
    dm = xgb.DMatrix(features, label=target, nthread=8)
    params = dict(objective="reg:squarederror", booster="gbtree", tree_method="hist", device="cpu",
                  multi_strategy="multi_output_tree", num_parallel_tree=1, max_depth=2, eta=1.,
                  base_score=0., reg_lambda=0., reg_alpha=0., gamma=0., min_child_weight=1.,
                  max_bin=256, subsample=1., colsample_bytree=1., seed=SEED, nthread=8)
    booster = xgb.train(params, dm, num_boost_round=1)
    model_path = BUILD / "router.json"
    booster.save_model(model_path)
    assets.append(identity(model_path))
    native = booster.predict(dm, pred_leaf=True).reshape(-1).astype("<i4")
    assert native.shape == (RIGHT,)
    leaves = np.unique(native)
    assert 1 <= len(leaves) <= 4
    region = np.searchsorted(leaves, native).astype("u1")
    assets += [save("router-native-leaf", native), save("T-regions", region)]
    record = dict(params=params, features=list(fields), source_factors=inputs,
                  centered_projection_max_error=difference, centered_projection=projection,
                  assets=assets, leaves=leaves.tolist(), region_counts=np.bincount(region).tolist(),
                  projection_dimensions=96, independent_router_validation_host="r9r4900",
                  independent_router_validation=False)
    write(ROOT / "router.json", record)
    print("EXP557_ROUTER_TRAINED", record["region_counts"], flush=True)
    return region


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp557")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    assert xgb.__version__ == "3.0.5" and read("installed-versions.json")["exit_code"] == 0
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    assert not ROOT.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    shutil.copyfile(old.PREPARATION / "mapping.json", ROOT / "mapping.json")
    old.ROOT = ROOT
    (ROOT / "installed-library-help.txt").write_text(
        f"numpy={np.__version__} scipy={scipy.__version__}\n" +
        str(inspect.signature(svd)) + "\n" + svd.__doc__)
    paths = [Path(__file__), PLAN, ROOT / "protocol-original.md", ROOT / "mapping.json",
             old.PREPARATION / "fields.json", old.PREPARATION / "label-report.json"]
    paths += [Path("validation") / (n + ".py") for n in
              ("exp510_pair_geometry", "exp500_split_residues", "exp504_tail_rectangles", "exp208_nominal_parent_tree")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in paths], seed=SEED,
          source_ports=208, target_ports=288, port_pairs=LEFT, shape=[LEFT, RIGHT],
          cpu_budget_s=18000, disk_free_start=free, hostname=socket.gethostname()))
    values = old.materialize(ROOT / "materialization.json")
    assert read(ROOT / "materialization.json")["matrix_sha256"] == read("../exp510/validation/results/exp510/materialization.json")["matrix_sha256"]
    center = np.empty(LEFT, dtype="<i2")
    weights = 1 / np.square(DENOM)
    for start in range(0, LEFT, BLOCK):
        mean = values[start:start + BLOCK].astype(np.float64) @ weights / weights.sum()
        rounded = np.copysign(np.floor(np.abs(mean) + .5), mean)
        assert np.all((-32768 <= rounded) & (rounded <= 32767))
        center[start:start + len(mean)] = rounded.astype("<i2")
    center_asset = save("center", center)
    region = router(center, values)
    rng = np.random.default_rng(SEED)
    models = []
    for name, rank, groups in (("G", 96, np.zeros(RIGHT, dtype="u1")),
                               ("F", 64, old.coordinates()[:, 0].astype("u1")), ("T", 64, region)):
        n = int(groups.max()) + 1
        left = np.empty((n, LEFT, rank), dtype=np.float64)
        right = np.empty((RIGHT, rank), dtype=np.float64)
        records = []
        for g in range(n):
            keys = np.flatnonzero(groups == g)
            assert len(keys) >= rank + 16
            left[g], right[keys], record = fit(values, center, keys, rank, name + f"-{g}", rng)
            records.append(record)
        assets = [save(name + "-left", left), save(name + "-right", right)]
        if name != "T":
            assets.append(save(name + "-regions", groups))
        model = dict(name=name, rank=rank, regions=n, assets=assets, groups=records,
                     factor_int16_bytes=2 * (n * LEFT + RIGHT) * rank,
                     source_ports=208, target_ports=288, port_pairs=LEFT, values=LEFT * RIGHT)
        models.append(model)
        write(ROOT / (name + "-model.json"), model)
        del left, right
        print("EXP557_MODEL_TRAINED", name, flush=True)
    assets = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert assets <= 3_000_000_000
    write(ROOT / "training.json", dict(models=models, center=center_asset, all_training_checks=True,
          shape=[LEFT, RIGHT], values=LEFT * RIGHT, freeze=identity(ROOT / "freeze.json"),
          source_ports=208, target_ports=288, port_pairs=LEFT, independent_tests=False,
          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          new_asset_bytes=assets, disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP557_COMPLETE_OFFLINE_TRAINING", flush=True)


if __name__ == "__main__":
    main()
