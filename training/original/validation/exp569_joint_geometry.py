#!/usr/bin/env python3
"""Joint continuous and categorical geometry fit offline; tests belong to r9."""
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

import exp568_additive_geometry as previous

ROOT, BUILD = Path("validation/results/exp569"), Path("build/exp569")
PLAN = Path("experiment/实验569-连续几何基与加性码字的联合空间.md")
LEFT, RIGHT, RANK, GROUPS, CODES, WIDTH = 59904, 264960, 32, 8, 64, 544
read, write, identity = previous.read, previous.write, previous.identity


def save(name, value):
    path = BUILD / (name + ".npy")
    assert not path.exists() and np.isfinite(value).all()
    np.save(path, value)
    return identity(path)


def inverse_gram(trend, codes):
    gram = np.empty((WIDTH, WIDTH), dtype=np.float64)
    gram[:RANK, :RANK] = trend.T @ trend
    categorical, _, _, _ = previous.gram_inverse(codes)
    gram[RANK:, RANK:] = categorical
    for t in range(GROUPS):
        for d in range(RANK):
            gram[d, RANK+t*CODES:RANK+(t+1)*CODES] = np.bincount(
                codes[:, t], weights=trend[:, d], minlength=CODES)
    gram[RANK:, :RANK] = gram[:RANK, RANK:].T
    values, vectors = eigh(gram, check_finite=True, driver="evd")
    keep = values > values[-1]*1e-10
    assert values[0] >= -1e-9*values[-1] and int(keep.sum()) <= RANK+505
    inverse = (vectors[:, keep]/values[keep]) @ vectors[:, keep].T
    return gram, inverse, values, int(keep.sum())


def projected_fit(target, trend, codes):
    gram, inverse, _, rank = inverse_gram(trend, codes)
    rhs = np.empty((WIDTH, target.shape[1]), dtype=np.float64)
    rhs[:RANK] = trend.T @ target
    for t in range(GROUPS):
        for d in range(target.shape[1]):
            rhs[RANK+t*CODES:RANK+(t+1)*CODES, d] = np.bincount(
                codes[:, t], weights=target[:, d], minlength=CODES)
    coefficients = inverse @ rhs
    normal = float(np.abs(gram @ coefficients-rhs).max()) / max(1., float(np.abs(rhs).max()))
    assert normal <= 1e-6
    codebooks = coefficients[RANK:].reshape(GROUPS, CODES, target.shape[1])
    residual = target-trend @ coefficients[:RANK]
    for t in range(GROUPS):
        residual -= codebooks[t, codes[:, t]]
    objective = float(np.square(residual).sum())
    formula = float(np.square(target).sum()-2*np.sum(coefficients*rhs)+
                    np.sum((gram @ coefficients)*coefficients))
    assert abs(objective-formula) <= 1e-9*max(1., float(np.square(target).sum()))
    return codebooks, residual, objective, rank, normal


def recode(target, trend, initial):
    codes = initial.copy()
    books, residual, objective, rank, normal = projected_fit(target, trend, codes)
    records = [dict(sweep=0, objective=objective, rank=rank, normal=normal)]
    for sweep in range(1, 9):
        before, changed = objective, []
        for t in range(GROUPS):
            squared, count = np.square(books[t]).sum(axis=1), 0
            for start in range(0, RIGHT, 8192):
                stop = min(RIGHT, start+8192)
                old = codes[start:stop, t].copy()
                contribution = books[t, old]
                desired = residual[start:stop]+contribution
                score = 2*(desired @ books[t].T)-squared
                best, rows = np.argmax(score, axis=1), np.arange(stop-start)
                old_score = score[rows, old]
                improve = score[rows, best] > old_score+1e-12*np.maximum(1., np.abs(old_score))
                best = np.where(improve, best, old)
                codes[start:stop, t] = best
                residual[start:stop] += contribution-books[t, best]
                count += int(np.count_nonzero(improve))
            changed.append(count)
        assigned = float(np.square(residual).sum())
        assert assigned <= before+1e-9*max(1., before)
        books, residual, objective, rank, normal = projected_fit(target, trend, codes)
        assert objective <= assigned+1e-9*max(1., assigned)
        records.append(dict(sweep=sweep, objective_before=before, objective_after_assignment=assigned,
                            objective=objective, rank=rank, normal=normal, changed_by_group=changed))
        write(ROOT/("sweep-"+str(sweep)+".json"), records[-1])
        print("EXP569_RECODE", sweep, objective, sum(changed), flush=True)
    write(ROOT/"optimization.json", dict(records=records, sweeps=8, projected_only=True,
          changed_codes=int(np.count_nonzero(codes != initial))))
    return codes


def fit_full(rhs, gram, inverse, energy):
    coefficients = rhs @ inverse
    normal = float(np.abs(coefficients @ gram-rhs).max()) / max(1., float(np.abs(rhs).max()))
    error = float(energy-2*np.sum(coefficients*rhs)+np.sum((coefficients @ gram)*coefficients))
    assert normal <= 1e-6 and error >= -1e-9*energy
    return coefficients, error, normal


def quantize(values, axes):
    maximum = np.abs(values).max(axis=axes)
    exponent = np.ceil(np.log2(np.maximum(maximum, np.finfo(float).tiny)/32767)).astype("<i4")
    shape = [1]*values.ndim
    for i in range(values.ndim):
        if i not in axes:
            shape[i] = values.shape[i]
    scaled = np.rint(np.ldexp(values, -exponent.reshape(shape)))
    assert np.isfinite(scaled).all() and np.abs(scaled).max() <= 32767
    return scaled.astype("<i2"), exponent


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp569")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT/"protocol-original.md")
    source = read("../exp567/validation/results/exp567/training.json")
    initial_source = read("../exp568/validation/results/exp568/training.json")
    records = [p for p in source["assets"] if Path(p["path"]).stem in
               ("center", "projected-target", "output-projection", "row-sum", "row-energy")]
    records = [(Path("../exp567")/p["path"], p) for p in records]
    records += [(Path("../exp568")/p["path"], p) for p in initial_source["assets"]
                if Path(p["path"]).stem in ("leaves", "rhs")]
    global_model = read("../exp557/validation/results/exp557/G-model.json")
    record = next(p for p in global_model["assets"] if p["path"].endswith("G-right.npy"))
    records.append((Path("../exp557")/record["path"], record))
    assets_in, arrays = [], {}
    for path, expected in records:
        actual = identity(path)
        assert (actual["bytes"], actual["sha256"]) == (expected["bytes"], expected["sha256"])
        assets_in.append(actual)
        arrays[path.stem] = np.load(path)
    center, target, omega = (arrays[n] for n in ("center", "projected-target", "output-projection"))
    initial = arrays["leaves"]
    assert center.shape == (LEFT,) and initial.shape == (RIGHT, GROUPS)
    assert target.shape == (RIGHT, 64) and omega.shape == (LEFT, 64)
    trend = np.ascontiguousarray(arrays.pop("G-right")[:, :RANK])
    rms = np.sqrt(np.square(trend).mean(axis=0))
    assert (rms > 0).all()
    trend /= rms
    files = [Path(__file__), PLAN, ROOT/"protocol-original.md"]
    files += [Path("validation")/(n+".py") for n in
              ("exp568_additive_geometry", "exp567_leaf_dictionary", "exp557_conditional_geometry",
               "exp510_pair_geometry", "exp500_split_residues", "exp504_tail_rectangles",
               "exp208_nominal_parent_tree")]
    write(ROOT/"freeze.json", dict(files=[identity(p) for p in files], source_assets=assets_in,
          shape=[LEFT, RIGHT], trend_rank=RANK, port_pairs=LEFT, source_ports=208, target_ports=288,
          source_training=identity(Path("../exp568/validation/results/exp568/training.json")),
          energy_gate=previous.ENERGY_GATE, cpu_budget_s=18000, disk_free_start=free))
    (ROOT/"installed-library-help.txt").write_text(str(inspect.signature(eigh))+"\n"+eigh.__doc__)
    codes = recode(target, trend, initial)
    assets = [save("center", center), save("leaves", codes), save("trend", trend), save("trend-rms", rms)]
    nominal = previous.previous.previous
    old = nominal.old
    old.ROOT = ROOT
    nominal.ROOT = ROOT
    shutil.copyfile(old.PREPARATION/"mapping.json", ROOT/"mapping.json")
    values = old.materialize(ROOT/"materialization.json")
    assert read(ROOT/"materialization.json")["matrix_sha256"] == read(
        "../exp567/validation/results/exp567/materialization.json")["matrix_sha256"]
    trend_rhs, trend_cost = nominal.multiply(values, center, np.arange(RIGHT), trend, False, "joint-trend")
    help_text = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in help_text
    (ROOT/"compiler-help.txt").write_text(help_text)
    helper = BUILD/"aggregate.so"
    command = ["g++", "-std=c++17", "-O3", "-fopenmp", "-fPIC", "-shared", "-fno-fast-math",
               "-ffp-contract=off", "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
               "validation/exp567_leaf_aggregate.cpp", "-o", str(helper)]
    result = subprocess.run(command, capture_output=True, text=True)
    write(ROOT/"helper-compiler.json", dict(command=command, exit_code=result.returncode,
          stdout=result.stdout, stderr=result.stderr))
    assert result.returncode == 0 and not result.stderr
    function = ctypes.CDLL(str(helper.resolve())).aggregate
    function.argtypes, function.restype = [ctypes.c_void_p]*6, None
    inv_denom = np.ascontiguousarray(1/nominal.DENOM)
    rhs_codes, energy = np.zeros((LEFT, GROUPS*CODES)), np.zeros(LEFT)
    function(*(a.ctypes.data for a in (values, center, inv_denom, codes, rhs_codes, energy)))
    del values
    sums = rhs_codes.reshape(LEFT, GROUPS, CODES).sum(axis=2)
    sum_error = float(np.abs(sums-arrays["row-sum"][:, None]).max())/max(1., float(np.abs(arrays["row-sum"]).max()))
    energy_error = float(np.abs(energy-arrays["row-energy"]).max())/max(1., float(np.abs(energy).max()))
    rhs = np.column_stack((trend_rhs, rhs_codes))
    projected_rhs = np.empty((WIDTH, 64))
    projected_rhs[:RANK] = trend.T @ target
    for t in range(GROUPS):
        for d in range(64):
            projected_rhs[RANK+t*CODES:RANK+(t+1)*CODES, d] = np.bincount(
                codes[:, t], weights=target[:, d], minlength=CODES)
    projection_error = float(np.abs(rhs.T @ omega-projected_rhs).max())/max(1., float(np.abs(projected_rhs).max()))
    assert max(sum_error, energy_error, projection_error) <= 1e-10
    gram0, inverse0, _, rank0 = inverse_gram(trend, initial)
    initial_rhs = np.column_stack((trend_rhs, arrays["rhs"]))
    _, initial_error, initial_normal = fit_full(initial_rhs, gram0, inverse0, float(energy.sum()))
    assert initial_error <= initial_source["residual_energy"]+1e-8*float(energy.sum())
    trend_coeff = np.linalg.solve(trend.T @ trend, trend_rhs.T).T
    trend_error = float(energy.sum()-np.sum(trend_rhs*trend_coeff))
    del arrays, initial_rhs, gram0, inverse0, target, omega
    gram, inverse, eigenvalues, rank = inverse_gram(trend, codes)
    coefficients, error, normal = fit_full(rhs, gram, inverse, float(energy.sum()))
    floating_codes = coefficients[:, RANK:].reshape(LEFT, GROUPS, CODES)
    integer_codes, exponent_codes = quantize(floating_codes, (0, 2))
    integer_left, exponent_left = quantize(coefficients[:, :RANK], (0,))
    integer_right, exponent_right = quantize(trend, (0,))
    exponents = np.concatenate((exponent_left+exponent_right, exponent_codes))
    maxima = [int(np.abs(integer_left[:, d].astype(np.int32)).max())*
              int(np.abs(integer_right[:, d].astype(np.int32)).max()) for d in range(RANK)]
    maxima += [int(np.abs(integer_codes[:, t].astype(np.int32)).max()) for t in range(GROUPS)]
    bound = sum(v << int(e-exponents.min()) for v, e in zip(maxima, exponents))
    for name, value in [("rhs", rhs), ("row-energy", energy), ("gram", gram),
                        ("eigenvalues", eigenvalues), ("coefficients", coefficients),
                        ("integers", integer_codes), ("exponent", exponent_codes),
                        ("trend-left-integers", integer_left), ("trend-left-exponent", exponent_left),
                        ("trend-right-integers", integer_right), ("trend-right-exponent", exponent_right)]:
        assets.append(save(name, value))
    assets.append(identity(helper))
    table_bytes = 2*LEFT*WIDTH+RIGHT*(GROUPS+2*RANK)+2*LEFT+4*(GROUPS+2*RANK)
    new_bytes = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert new_bytes < 1000000000
    write(ROOT/"training.json", dict(assets=assets, source_assets=assets_in, shape=[LEFT, RIGHT],
          trend_rank=RANK, dictionary_rank=rank, initial_rank=rank0,
          code_occupancy=[int(len(np.unique(codes[:, t]))) for t in range(GROUPS)],
          input_energy=float(energy.sum()), residual_energy=error,
          trend_only_residual_energy=trend_error, code_only_residual_energy=initial_source["residual_energy"],
          initial_joint_residual_energy=initial_error, initial_normal_relative_error=initial_normal,
          normal_equation_relative_max_error=normal, aggregation_sum_relative_error=sum_error,
          aggregation_energy_relative_error=energy_error, aggregation_projection_relative_error=projection_error,
          energy_gate=previous.ENERGY_GATE, exact_energy_gate_passed=bool(error <= previous.ENERGY_GATE),
          integer_sum_bound=bound, common_exponent=int(exponents.min()),
          float64_reassociation_certified=bool(bound <= 2**53), table_bytes=table_bytes,
          source_ports=208, target_ports=288, port_pairs=LEFT, trend_projection_cost=trend_cost,
          all_training_checks=True, independent_tests=False, new_asset_bytes=new_bytes,
          cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP569_COMPLETE_OFFLINE_TRAINING", error, error <= previous.ENERGY_GATE, flush=True)


if __name__ == "__main__":
    main()
