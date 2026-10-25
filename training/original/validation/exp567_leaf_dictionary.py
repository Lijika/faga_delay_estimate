#!/usr/bin/env python3
"""Fit shared geometry rules and full-port leaf coefficients offline on l7."""
import ctypes
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import time

import numpy as np
import scipy
from scipy.linalg import eigh
import xgboost as xgb

import exp557_conditional_geometry as previous

ROOT, BUILD = Path("validation/results/exp567"), Path("build/exp567")
PLAN = Path("experiment/实验567-共享几何叶字典与完整端口系数.md")
LEFT, RIGHT, TREES, LEAVES, WIDTH, SEED = 59904, 264960, 8, 64, 512, 20261021567
read, write, identity = previous.read, previous.write, previous.identity


def save(name, value):
    path = BUILD / (name + ".npy")
    assert not path.exists() and np.isfinite(value).all()
    np.save(path, value)
    return identity(path)


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp567")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    old = previous.old
    old.ROOT = ROOT
    shutil.copyfile(old.PREPARATION / "mapping.json", ROOT / "mapping.json")
    source = read("../exp557/validation/results/exp557/training.json")
    center_path = Path("../exp557") / source["center"]["path"]
    center_record = identity(center_path)
    assert (center_record["bytes"], center_record["sha256"]) == (source["center"]["bytes"], source["center"]["sha256"])
    center = np.load(center_path)
    features = np.load("../exp557/build/exp557/router-features.npy")
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    assert features.shape == (RIGHT, 14) and features.dtype == np.dtype("<f4")
    files = [Path(__file__), Path("validation/exp567_leaf_aggregate.cpp"), PLAN,
             ROOT / "protocol-original.md", ROOT / "mapping.json", center_path,
             Path("../exp557/build/exp557/router-features.npy")]
    files += [Path("validation") / (n + ".py") for n in
              ("exp557_conditional_geometry", "exp510_pair_geometry", "exp500_split_residues",
               "exp504_tail_rectangles", "exp208_nominal_parent_tree")]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files], seed=SEED,
          shape=[LEFT, RIGHT], source_ports=208, target_ports=288, port_pairs=LEFT,
          hostname=socket.gethostname(), cpu_budget_s=18000, disk_free_start=free))
    (ROOT / "installed-library-help.txt").write_text(
        f"numpy={np.__version__} scipy={scipy.__version__} xgboost={xgb.__version__}\n" +
        str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__ + "\n" +
        str(inspect.signature(xgb.Booster.predict)) + "\n" + xgb.Booster.predict.__doc__ + "\n" +
        str(inspect.signature(eigh)) + "\n" + eigh.__doc__)
    values = old.materialize(ROOT / "materialization.json")
    assert read(ROOT / "materialization.json")["matrix_sha256"] == read(
        "../exp510/validation/results/exp510/materialization.json")["matrix_sha256"]
    rng = np.random.default_rng(SEED)
    omega = (2 * rng.integers(0, 2, size=(LEFT, 64), dtype=np.int8) - 1).astype(np.float64) / 8
    target = np.zeros((RIGHT, 64), dtype=np.float64)
    row_sum, row_energy = np.empty(LEFT), np.empty(LEFT)
    for start in range(0, LEFT, 288):
        block = values[start:start+288].astype(np.float64)
        block -= center[start:start+len(block), None]
        block /= previous.DENOM
        target += block.T @ omega[start:start+len(block)]
        row_sum[start:start+len(block)] = block.sum(axis=1)
        row_energy[start:start+len(block)] = np.square(block).sum(axis=1)
        if start % (16*288) == 0:
            print("EXP567_OUTPUT_PROJECTION", start, flush=True)
    assets = [save("center", center), save("features", features), save("output-projection", omega),
              save("projected-target", target), save("row-sum", row_sum)]
    del block
    dm = xgb.DMatrix(features, label=target.astype("<f4"), nthread=8)
    params = dict(objective="reg:squarederror", booster="gbtree", tree_method="hist", device="cpu",
                  multi_strategy="multi_output_tree", num_parallel_tree=1, max_depth=6, eta=.5,
                  base_score=0., reg_lambda=0., reg_alpha=0., gamma=0., min_child_weight=1.,
                  max_bin=256, subsample=1., colsample_bytree=1., seed=SEED, nthread=8)
    model = xgb.train(params, dm, num_boost_round=TREES)
    model.save_model(BUILD / "rules.json")
    native = model.predict(dm, pred_leaf=True).astype("<i4").reshape(RIGHT, TREES)
    leaves = np.empty_like(native, dtype="u1")
    node_ids = []
    for t in range(TREES):
        ids = np.unique(native[:, t])
        assert 1 <= len(ids) <= LEAVES
        leaves[:, t] = np.searchsorted(ids, native[:, t]).astype("u1")
        node_ids.append(ids.tolist())
    assets += [identity(BUILD / "rules.json"), save("native-leaves", native), save("leaves", leaves)]
    del dm, features, native, model
    print("EXP567_RULES_TRAINED", [len(ids) for ids in node_ids], flush=True)
    helper_source = Path("validation/exp567_leaf_aggregate.cpp")
    helper = BUILD / "leaf-aggregate.so"
    help_text = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in help_text
    (ROOT / "compiler-help.txt").write_text(help_text)
    command = ["g++", "-std=c++17", "-O3", "-fopenmp", "-fPIC", "-shared", "-fno-fast-math",
               "-ffp-contract=off", "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
               str(helper_source), "-o", str(helper)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    write(ROOT / "helper-compiler.json", dict(command=command, exit_code=compiled.returncode,
          stdout=compiled.stdout, stderr=compiled.stderr))
    assert compiled.returncode == 0 and not compiled.stderr
    function = ctypes.CDLL(str(helper.resolve())).aggregate
    function.argtypes = [ctypes.c_void_p] * 6
    function.restype = None
    inverse = np.ascontiguousarray(1 / previous.DENOM)
    rhs, energy = np.zeros((LEFT, WIDTH), dtype=np.float64), np.zeros(LEFT, dtype=np.float64)
    function(*(a.ctypes.data for a in (values, center, inverse, leaves, rhs, energy)))
    assert np.isfinite(rhs).all() and np.isfinite(energy).all() and (energy >= 0).all()
    sums = rhs.reshape(LEFT, TREES, LEAVES).sum(axis=2)
    sum_error = float(np.abs(sums-row_sum[:, None]).max()) / max(1., float(np.abs(row_sum).max()))
    energy_error = float(np.abs(energy-row_energy).max()) / max(1., float(np.abs(row_energy).max()))
    projected_rhs = rhs.T @ omega
    aggregated_target = np.zeros((WIDTH, 64), dtype=np.float64)
    for t in range(TREES):
        np.add.at(aggregated_target[t*64:(t+1)*64], leaves[:, t], target)
    projection_error = float(np.abs(projected_rhs-aggregated_target).max()) / max(1., float(np.abs(aggregated_target).max()))
    assert max(sum_error, energy_error, projection_error) <= 1e-10
    del omega, target
    del values
    assets += [save("rhs", rhs), save("row-energy", energy)]
    gram = np.empty((WIDTH, WIDTH), dtype=np.float64)
    for t in range(TREES):
        for u in range(t, TREES):
            count = np.bincount(leaves[:, t].astype(np.int64)*LEAVES + leaves[:, u], minlength=4096).reshape(64, 64)
            gram[t*64:(t+1)*64, u*64:(u+1)*64] = count
            gram[u*64:(u+1)*64, t*64:(t+1)*64] = count.T
    eigenvalues, basis = eigh(gram, check_finite=True, driver="evd")
    keep = eigenvalues > eigenvalues[-1] * 1e-10
    assert eigenvalues[0] >= -1e-9 * eigenvalues[-1] and int(keep.sum()) <= 505
    inverse_gram = (basis[:, keep] / eigenvalues[keep]) @ basis[:, keep].T
    coefficients = (rhs @ inverse_gram).reshape(LEFT, TREES, LEAVES)
    linear = coefficients.reshape(LEFT, WIDTH)
    normal = float(np.abs(linear @ gram-rhs).max()) / max(1., float(np.abs(rhs).max()))
    assert normal <= 1e-6
    error = float(energy.sum() - 2*np.sum(linear*rhs) + np.sum((linear@gram)*linear))
    assert error >= -1e-9 * float(energy.sum())
    maximum = np.abs(coefficients).max(axis=(0, 2))
    exponent = np.ceil(np.log2(np.maximum(maximum, np.finfo(float).tiny)/32767)).astype("<i4")
    scaled = np.ldexp(coefficients, -exponent[None, :, None])
    integers = np.rint(scaled)
    assert np.isfinite(integers).all() and np.abs(integers).max() <= 32767
    integers = integers.astype("<i2")
    restored = np.ldexp(integers.astype(np.float64), exponent[None, :, None])
    quant_error = float(np.abs(coefficients-restored).max(axis=2).sum(axis=1).max())
    bound = sum(int(np.abs(integers[:, t].astype(np.int32)).max()) << int(exponent[t]-exponent.min())
                for t in range(TREES))
    assets += [save("gram", gram), save("eigenvalues", eigenvalues), save("coefficients", coefficients),
               save("exponent", exponent), save("integers", integers)]
    bytes_ = 2*LEFT*WIDTH + RIGHT*TREES + 2*LEFT + 4*TREES
    assert bytes_ < 95_000_000
    write(ROOT / "training.json", dict(params=params, rounds=TREES, assets=assets,
          node_ids=node_ids, eigenvalue_cutoff_relative=1e-10, dictionary_rank=int(keep.sum()),
          normal_equation_relative_max_error=normal, input_energy=float(energy.sum()),
          aggregation_sum_relative_error=sum_error, aggregation_energy_relative_error=energy_error,
          aggregation_projection_relative_error=projection_error,
          residual_energy=error, quantized_coefficient_max_error=quant_error,
          integer_sum_bound=bound, common_exponent=int(exponent.min()),
          float64_reassociation_certified=bound <= 2**53,
          table_bytes=bytes_, shape=[LEFT, RIGHT], source_ports=208, target_ports=288, port_pairs=LEFT,
          all_training_checks=True, independent_tests=False, source_center=center_record,
          cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
          new_asset_bytes=sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file()),
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP567_COMPLETE_OFFLINE_TRAINING", flush=True)


if __name__ == "__main__":
    main()
