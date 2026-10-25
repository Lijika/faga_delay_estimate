#!/usr/bin/env python3
"""Offline geometry recoding with fixed capacity; independent checks run on r9."""
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
from scipy.linalg import eigh

import exp567_leaf_dictionary as previous

ROOT, BUILD = Path("validation/results/exp568"), Path("build/exp568")
PLAN = Path("experiment/实验568-共享几何码字的联合拟合与离线重编码.md")
LEFT, RIGHT, GROUPS, CODES, WIDTH = 59904, 264960, 8, 64, 512
ENERGY_GATE = 1203634.579565436
read, write, identity = previous.read, previous.write, previous.identity


def save(name, value):
    path = BUILD / (name + ".npy")
    assert not path.exists() and np.isfinite(value).all()
    np.save(path, value)
    return identity(path)


def gram_inverse(codes):
    gram = np.zeros((WIDTH, WIDTH), dtype=np.float64)
    for t in range(GROUPS):
        for u in range(t, GROUPS):
            count = np.bincount(codes[:, t].astype(np.int64)*CODES+codes[:, u],
                                minlength=CODES*CODES).reshape(CODES, CODES)
            gram[t*CODES:(t+1)*CODES, u*CODES:(u+1)*CODES] = count
            gram[u*CODES:(u+1)*CODES, t*CODES:(t+1)*CODES] = count.T
    eigenvalues, basis = eigh(gram, check_finite=True, driver="evd")
    keep = eigenvalues > eigenvalues[-1]*1e-10
    assert eigenvalues[0] >= -1e-9*eigenvalues[-1] and int(keep.sum()) <= 505
    return gram, eigenvalues, (basis[:, keep]/eigenvalues[keep])@basis[:, keep].T, int(keep.sum())


def projected_fit(target, codes):
    gram, _, inverse, rank = gram_inverse(codes)
    rhs = np.zeros((WIDTH, target.shape[1]), dtype=np.float64)
    for t in range(GROUPS):
        for d in range(target.shape[1]):
            rhs[t*CODES:(t+1)*CODES, d] = np.bincount(
                codes[:, t], weights=target[:, d], minlength=CODES)
    coefficients = (inverse@rhs).reshape(GROUPS, CODES, target.shape[1])
    normal = float(np.abs(gram @ coefficients.reshape(WIDTH, -1)-rhs).max())
    normal /= max(1., float(np.abs(rhs).max()))
    assert normal <= 1e-6
    residual = target.copy()
    for t in range(GROUPS):
        residual -= coefficients[t, codes[:, t]]
    objective = float(np.square(residual).sum())
    linear = coefficients.reshape(WIDTH, -1)
    formula = float(np.square(target).sum()-2*np.sum(linear*rhs)+np.sum((gram@linear)*linear))
    assert abs(objective-formula) <= 1e-9*max(1., float(np.square(target).sum()))
    return coefficients, residual, objective, rank, normal


def recode(target, initial):
    codes = initial.copy()
    codebooks, residual, objective, rank, normal = projected_fit(target, codes)
    records = [dict(sweep=0, objective=objective, rank=rank, normal=normal)]
    for sweep in range(1, 9):
        before = objective
        changed = []
        for t in range(GROUPS):
            squared = np.square(codebooks[t]).sum(axis=1)
            count = 0
            for start in range(0, RIGHT, 8192):
                stop = min(RIGHT, start+8192)
                old = codes[start:stop, t].copy()
                contribution = codebooks[t, old]
                desired = residual[start:stop]+contribution
                score = 2*(desired@codebooks[t].T)-squared
                best = np.argmax(score, axis=1)
                rows = np.arange(stop-start)
                old_score = score[rows, old]
                improve = score[rows, best] > old_score+1e-12*np.maximum(1., np.abs(old_score))
                best = np.where(improve, best, old)
                codes[start:stop, t] = best
                residual[start:stop] += contribution-codebooks[t, best]
                count += int(np.count_nonzero(improve))
            changed.append(count)
        assigned = float(np.square(residual).sum())
        assert assigned <= before+1e-9*max(1., before)
        codebooks, residual, objective, rank, normal = projected_fit(target, codes)
        assert objective <= assigned+1e-9*max(1., assigned)
        record = dict(sweep=sweep, objective_before=before, objective_after_assignment=assigned,
                      objective=objective, changed_by_group=changed, rank=rank, normal=normal)
        records.append(record)
        write(ROOT/("sweep-"+str(sweep)+".json"), record)
        print("EXP568_RECODE", sweep, objective, sum(changed), flush=True)
    write(ROOT/"optimization.json", dict(records=records, sweeps=8, projected_only=True,
          initial=identity(Path("../exp567/build/exp567/leaves.npy")),
          changed_codes=int(np.count_nonzero(codes != initial))))
    return codes


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp568")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT/"protocol-original.md")
    source = read("../exp567/validation/results/exp567/training.json")
    assert source["all_training_checks"] and source["shape"] == [LEFT, RIGHT]
    names = ("center", "projected-target", "leaves", "output-projection", "row-sum", "row-energy")
    source_assets = []
    arrays = {}
    for name in names:
        path = Path("../exp567/build/exp567")/(name+".npy")
        record = next(r for r in source["assets"] if r["path"] == "build/exp567/"+name+".npy")
        actual = identity(path)
        assert (actual["bytes"], actual["sha256"]) == (record["bytes"], record["sha256"])
        source_assets.append(actual)
        arrays[name] = np.load(path)
    target, initial = arrays["projected-target"], arrays["leaves"]
    center, omega = arrays["center"], arrays["output-projection"]
    assert target.shape == (RIGHT, 64) and target.dtype == np.dtype("<f8")
    assert initial.shape == (RIGHT, GROUPS) and initial.dtype == np.dtype("u1") and initial.max() < CODES
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    files = [Path(__file__), Path("validation/exp567_leaf_aggregate.cpp"), PLAN, ROOT/"protocol-original.md"]
    files += [Path("validation")/(n+".py") for n in
              ("exp567_leaf_dictionary", "exp557_conditional_geometry", "exp510_pair_geometry",
               "exp500_split_residues", "exp504_tail_rectangles", "exp208_nominal_parent_tree")]
    write(ROOT/"freeze.json", dict(files=[identity(p) for p in files], source_assets=source_assets,
          shape=[LEFT, RIGHT], source_ports=208, target_ports=288, port_pairs=LEFT,
          source_training=identity(Path("../exp567/validation/results/exp567/training.json")),
          energy_gate=ENERGY_GATE, cpu_budget_s=18000, disk_free_start=free))
    (ROOT/"installed-library-help.txt").write_text(str(inspect.signature(eigh))+"\n"+eigh.__doc__)
    codes = recode(target, initial)
    assets = [save("center", center), save("leaves", codes)]
    old = previous.previous.old
    old.ROOT = ROOT
    shutil.copyfile(old.PREPARATION/"mapping.json", ROOT/"mapping.json")
    values = old.materialize(ROOT/"materialization.json")
    assert read(ROOT/"materialization.json")["matrix_sha256"] == read(
        "../exp567/validation/results/exp567/materialization.json")["matrix_sha256"]
    helped = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in helped
    (ROOT/"compiler-help.txt").write_text(helped)
    helper = BUILD/"aggregate.so"
    command = ["g++", "-std=c++17", "-O3", "-fopenmp", "-fPIC", "-shared", "-fno-fast-math",
               "-ffp-contract=off", "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
               "validation/exp567_leaf_aggregate.cpp", "-o", str(helper)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    write(ROOT/"helper-compiler.json", dict(command=command, exit_code=compiled.returncode,
          stdout=compiled.stdout, stderr=compiled.stderr))
    assert compiled.returncode == 0 and not compiled.stderr
    function = ctypes.CDLL(str(helper.resolve())).aggregate
    function.argtypes, function.restype = [ctypes.c_void_p]*6, None
    inverse = np.ascontiguousarray(1/previous.previous.DENOM)
    rhs, energy = np.zeros((LEFT, WIDTH), dtype=np.float64), np.zeros(LEFT, dtype=np.float64)
    function(*(a.ctypes.data for a in (values, center, inverse, codes, rhs, energy)))
    assert np.isfinite(rhs).all() and np.isfinite(energy).all() and (energy >= 0).all()
    sums = rhs.reshape(LEFT, GROUPS, CODES).sum(axis=2)
    sum_error = float(np.abs(sums-arrays["row-sum"][:, None]).max())/max(1., float(np.abs(arrays["row-sum"]).max()))
    energy_error = float(np.abs(energy-arrays["row-energy"]).max())/max(1., float(np.abs(energy).max()))
    projected_rhs = np.empty((WIDTH, 64), dtype=np.float64)
    for t in range(GROUPS):
        for d in range(64):
            projected_rhs[t*CODES:(t+1)*CODES, d] = np.bincount(codes[:, t], weights=target[:, d], minlength=CODES)
    projection_error = float(np.abs(rhs.T@omega-projected_rhs).max())/max(1., float(np.abs(projected_rhs).max()))
    assert max(sum_error, energy_error, projection_error) <= 1e-10
    del values, arrays, omega, target
    gram, eigenvalues, inverse_gram, rank = gram_inverse(codes)
    coefficients = (rhs@inverse_gram).reshape(LEFT, GROUPS, CODES)
    linear = coefficients.reshape(LEFT, WIDTH)
    normal = float(np.abs(linear@gram-rhs).max())/max(1., float(np.abs(rhs).max()))
    assert normal <= 1e-6
    error = float(energy.sum()-2*np.sum(linear*rhs)+np.sum((linear@gram)*linear))
    assert error >= -1e-9*float(energy.sum())
    maximum = np.abs(coefficients).max(axis=(0, 2))
    exponent = np.ceil(np.log2(np.maximum(maximum, np.finfo(float).tiny)/32767)).astype("<i4")
    scaled = np.ldexp(coefficients, -exponent[None, :, None])
    integers = np.rint(scaled)
    assert np.isfinite(integers).all() and np.abs(integers).max() <= 32767
    integers = integers.astype("<i2")
    restored = np.ldexp(integers.astype(np.float64), exponent[None, :, None])
    quant_error = float(np.abs(coefficients-restored).max(axis=2).sum(axis=1).max())
    bound = sum(int(np.abs(integers[:, t].astype(np.int32)).max()) << int(exponent[t]-exponent.min())
                for t in range(GROUPS))
    assets += [save("rhs", rhs), save("row-energy", energy), save("gram", gram), save("eigenvalues", eigenvalues),
               save("coefficients", coefficients), save("exponent", exponent), save("integers", integers)]
    assets.append(identity(helper))
    table_bytes = 2*LEFT*WIDTH+RIGHT*GROUPS+2*LEFT+4*GROUPS
    new_bytes = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert new_bytes < 1000000000
    write(ROOT/"training.json", dict(assets=assets, shape=[LEFT, RIGHT], dictionary_rank=rank,
          code_occupancy=[int(len(np.unique(codes[:, t]))) for t in range(GROUPS)],
          normal_equation_relative_max_error=normal, input_energy=float(energy.sum()),
          aggregation_sum_relative_error=sum_error, aggregation_energy_relative_error=energy_error,
          aggregation_projection_relative_error=projection_error, residual_energy=error,
          energy_gate=ENERGY_GATE, exact_energy_gate_passed=bool(error <= ENERGY_GATE),
          prior_energy=source["residual_energy"], quantized_coefficient_max_error=quant_error,
          integer_sum_bound=bound, common_exponent=int(exponent.min()),
          float64_reassociation_certified=bound <= 2**53, table_bytes=table_bytes,
          source_ports=208, target_ports=288, port_pairs=LEFT,
          all_training_checks=True, independent_tests=False, source_assets=source_assets,
          cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
          new_asset_bytes=new_bytes, disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP568_COMPLETE_OFFLINE_TRAINING", error, error <= ENERGY_GATE, flush=True)


if __name__ == "__main__":
    main()
