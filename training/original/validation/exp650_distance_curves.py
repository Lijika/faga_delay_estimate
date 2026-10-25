#!/usr/bin/env python3
"""Fit full distance-residual curves from separate source ports, with scalar inclusion."""
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp639/validation").resolve()))
import exp639_fused_axis as finite
prior, scalar = finite.prior, finite.scalar
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked
sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed

ROOT, BUILD = Path("validation/results/exp650"), Path("build/exp650")
PLAN = Path("experiment/实验650-冻结D64残量的共享距离曲线原型.md")
PAIRS, CELLS, SEED, FIT_ROWS = 59904, 59904 * 12, 20261024650, 16384
GRID = [(x, y) for x in range(12) for y in range(46) if x + y > 3]
TRAIN = [(x, y) for x in (0, 1, 3, 5, 7, 9, 11)
         for y in (0, 1, 4, 8, 16, 28, 44) if x + y > 3]
VALID = [(x, y) for x in (0, 1, 2, 4, 6, 8, 10)
         for y in (0, 1, 3, 6, 12, 22, 36, 45) if x + y > 3]
T, V = np.array([GRID.index(g) for g in TRAIN]), np.array([GRID.index(g) for g in VALID])
WEIGHTS = 1 / (128 + 125 * np.array(GRID).sum(axis=1)).astype("f8")
HOLDOUT = ((np.arange(CELLS) // (288 * 12)) // 8) % 4 == 0
speed.ROOT = ROOT


def median(values):
    n = len(values)
    at = ((n - 1) // 2, n // 2)
    ordered = np.partition(values, at, axis=0)
    return np.clip(np.zeros(values.shape[1], "i2"), ordered[at[0]], ordered[at[1]])


def self_check():
    assert len(GRID) == 542 and not set(TRAIN) & set(VALID)
    assert len(T) <= 64 and np.all(WEIGHTS > 0)
    assert len(np.unique(np.flatnonzero(HOLDOUT) // (288 * 12))) == 56
    assert np.array_equal(median(np.array([[-4, -4, 2], [-2, 2, 4]], "i2")), [-2, 0, 2])
    context = np.arange(12)[:, None]
    qx, qy = np.asarray(GRID).T
    assert np.array_equal(prior.local(context, qx[None], qy[None]),
                          context * 542 + np.arange(542)[None])
    finite.self_check()


def prepare():
    self_check()
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    checked(prior.GEOMETRY, read("../exp589/validation/results/exp589/candidate-freeze.json")["arms"]["D64"]["geometry"])
    q4 = Path("../exp619/build/exp619/Q4.p4")
    checked(q4, read("../exp619/validation/results/exp619/training.json")["asset"])
    certificate = read(prior.PREPARATION / "label-report.json")
    assert certificate["evidence_passed"] and certificate["certified_values"] == PAIRS * 264960
    assert not read("../exp649/validation/results/exp649/100m-report.json")["comparison"]["joint_gate"]
    fit_ids = np.random.default_rng(SEED).choice(np.flatnonzero(~HOLDOUT), FIT_ROWS, replace=False)
    assert len(np.unique(fit_ids)) == FIT_ROWS and not HOLDOUT[fit_ids].any()
    fit_ids.astype("<u4").tofile(BUILD / "fit-ids.u32")
    sources = [Path(__file__), Path("validation/exp650_curve_assign.cpp"), PLAN,
        ROOT / "protocol-original.md", prior.GEOMETRY, q4, BUILD / "fit-ids.u32",
        prior.PREPARATION / "mapping.json", prior.PREPARATION / "fields.json",
        prior.PREPARATION / "label-report.json", Path(prior.__file__), Path(finite.__file__),
        Path(scalar.__file__), Path(inspect.getsourcefile(prior.load_field))]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in sources],
        train=TRAIN, validation=VALID, grid=GRID, seed=SEED, initialization_seed=20261025650,
        fit_rows=FIT_ROWS, cells=CELLS, heldout_source_ports=56,
        numpy=np.__version__, self_check_passed=True, frozen_before_values=True,
        full_asset_budget_bytes=64 + PAIRS * 480 + 4 * 256 * 542 * 2 + 56_503_992 + 8_500_000,
        new_exact_labels=0, complete_program_runs=0,
        disk_free_start_bytes=shutil.disk_usage(".").free))
    (ROOT / "installed-numpy-help.txt").write_text(np.partition.__doc__ + "\n" + np.random.Generator.choice.__doc__)
    (ROOT / "compiler-help.txt").write_text(subprocess.check_output(["g++", "--help"], text=True))
    speed.measured(["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64",
        "-mtune=generic", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
        "validation/exp650_curve_assign.cpp", "-o", str(BUILD / "assign")], "compile")
    assert not (ROOT / "compile.stderr").read_bytes()
    speed.measured([str(BUILD / "assign"), "--self-check"], "native-self-check")
    assert read(ROOT / "native-self-check.stdout")["self_check_passed"]
    return fit_ids


def extract():
    center, left, right, ls, rs = prior.model()
    qx, qy = np.array(GRID).T
    col = prior.local(np.arange(12)[:, None], qx[None], qy[None]).ravel()
    rhs, scale = right[col].astype("f8"), rs[col].astype("f8")
    errors = np.memmap(BUILD / "errors.i16", "<i2", "w+", shape=(PAIRS, 12, 542))
    mapping, fields = read(prior.PREPARATION / "mapping.json"), read(prior.PREPARATION / "fields.json")
    assert [r["number"] for r in fields] == list(range(208))
    assert len(mapping["sources"]) == 208 and len(mapping["targets"]) == 288
    records, audits = [], 0
    for item in fields:
        source = item["number"]
        field = prior.load_field(item, mapping)
        pairs = np.arange(source * 288, (source + 1) * 288)
        product = left[pairs].astype("f8") @ rhs.T
        assert np.array_equal(product, np.rint(product))
        value = product * ls[pairs].astype("f8")[:, None]
        value *= scale[None]
        value = value.reshape(288, 12, 542)
        value *= (128 + 125 * qx + 125 * qy)[None, None]
        value += center[pairs, None, None]
        value += (125 * qx)[None, None]
        value += (127 * qy)[None, None]
        nominal = (np.maximum(value, 0) + .5).astype("i4")
        truth = field[0, 0][..., qx, qy].transpose(1, 0, 2).astype("i4")
        truth += (125 * qx + 127 * qy)[None, None]
        residual = truth - nominal
        assert np.abs(residual).max() <= 32767
        errors[pairs] = residual
        if source in (0, 207):
            for target, ry, g in ((0, 0, 0), (73, 3, 113), (171, 8, 351), (287, 11, 541)):
                p = source * 288 + target
                x, y = GRID[g]
                c = int(prior.local(ry, x, y))
                dot = int(np.sum(left[p].astype("i4") * right[c].astype("i4")))
                v = float(dot) * float(ls[p]) * float(rs[c])
                v *= 128 + 125 * x + 125 * y
                v += int(center[p])
                v += 125 * x
                v += 127 * y
                truth_one = int(field[0, 0, ry, target, x, y]) + 125 * x + 127 * y
                assert int(nominal[target, ry, g]) == int(max(v, 0) + .5)
                assert int(errors[p, ry, g]) == truth_one - int(max(v, 0) + .5)
                audits += 1
        records.append(dict(source=source, asset=item["asset"], raw_sha256=item["raw_sha256"],
            residual_min=int(residual.min()), residual_max=int(residual.max())))
        if source % 16 == 0:
            print("EXP650_FIELD", source, flush=True)
    errors.flush()
    write(ROOT / "extraction.json", dict(errors=identity(BUILD / "errors.i16"),
        cells=CELLS, nominal_values=CELLS * 542, source_records=records,
        independent_dot_and_field_audits=audits, directions=1, rx=[0]))
    return errors.reshape(CELLS, 542)


def assign(values_path, centers, name, count):
    path = BUILD / (name + "-centers.i16")
    np.ascontiguousarray(centers[:, T], dtype="<i2").tofile(path)
    prefix = BUILD / name
    run = speed.measured([str(BUILD / "assign"), str(values_path), str(path),
        str(BUILD / "weights.f64"), str(count), str(len(T)), str(prefix)], name)
    assert run["exit_code"] == 0 and run["threads"] == 1 and run["cpu_s"] <= 600
    codes = np.fromfile(str(prefix) + ".codes.u8", "u1")
    losses = np.fromfile(str(prefix) + ".losses.f64", "<f8")
    assert len(codes) == len(losses) == count and np.isfinite(losses).all()
    return codes, losses


def fit(errors, fit_ids):
    samples = np.asarray(errors[fit_ids])
    levels = np.fromfile("../exp619/build/exp619/Q4.p4", "i1", count=16, offset=32)
    assert levels[0] == 0 and len(np.unique(levels)) == 16
    centers = np.empty((256, 542), "<i2")
    centers[:16] = levels[:, None]
    initial = np.random.default_rng(20261025650).choice(FIT_ROWS, 240, replace=False)
    centers[16:] = samples[initial]
    np.ascontiguousarray(samples[:, T], dtype="<i2").tofile(BUILD / "fit-values.i16")
    WEIGHTS[T].astype("<f8").tofile(BUILD / "weights.f64")
    codes, losses = assign(BUILD / "fit-values.i16", centers, "fit-0", FIT_ROWS)
    history = [float(losses.sum())]
    for iteration in range(1, 7):
        for code in range(16, 256):
            selected = samples[codes == code]
            if len(selected):
                centers[code] = median(selected)
        assert np.array_equal(centers[:16], np.broadcast_to(levels[:, None], (16, 542)))
        codes, losses = assign(BUILD / "fit-values.i16", centers, f"fit-{iteration}", FIT_ROWS)
        total = float(losses.sum())
        assert total <= history[-1] + 1e-10 * max(1., history[-1])
        history.append(total)
        print("EXP650_FIT", iteration, total, flush=True)
    path = BUILD / "all-train.i16"
    np.ascontiguousarray(errors[:, T], dtype="<i2").tofile(path)
    codes, losses = assign(path, centers, "all", CELLS)
    scalar_codes = np.empty(CELLS, "u1")
    for start in range(0, CELLS, 8192):
        end = min(start + 8192, CELLS)
        values = errors[start:end][:, T].astype("i4")
        scalar_codes[start:end], best = finite.choose_levels(values, WEIGHTS[T], levels)
        assert np.all(losses[start:end] <= best + 1e-10 * np.maximum(1., best))
    audit_ids = np.random.default_rng(SEED + 2).choice(CELLS, 64, replace=False)
    for i in audit_ids:
        options = (np.abs(errors[i, T].astype("i4")[None] - centers[:, T]) * WEIGHTS[T]).sum(axis=1)
        best = 0
        for c in range(1, 256):
            if options[c] < options[best] - 1e-12 * max(1., options[best]):
                best = c
        assert int(codes[i]) == best
        assert abs(losses[i] - options[best]) <= 1e-10 * max(1., losses[i])
    asset = BUILD / "D0-rx0.curves"
    with asset.open("xb") as stream:
        stream.write(b"EX650C01" + struct.pack("<6I", PAIRS, 1, 12, 542, 256, 2) + bytes(32))
        stream.write(codes.tobytes())
        stream.write(centers.tobytes())
    raw = asset.read_bytes()
    decoded_codes = np.frombuffer(raw, "u1", count=CELLS, offset=64)
    decoded_centers = np.frombuffer(raw, "<i2", offset=64 + CELLS).reshape(256, 542)
    assert np.array_equal(decoded_codes, codes) and np.array_equal(decoded_centers, centers)
    write(ROOT / "training.json", dict(asset=identity(asset), losses=history,
        all_training_cells_scalar_inclusion=True, independent_native_assign_audits=64,
        full_asset_roundtrip=True, constants_preserved=True,
        code_counts=np.bincount(codes, minlength=256).tolist(),
        training_nominal_values=CELLS * len(T), validation_nominal_values=CELLS * len(V)))
    return centers, codes, scalar_codes, levels


def evaluate(errors, centers, codes, scalar_codes, levels):
    old = scalar.unpack(Path("../exp619/build/exp619/Q4.p4"))[:, :12].reshape(-1).astype("i4")
    matched = levels[scalar_codes].astype("i4")
    qx, qy = np.asarray(VALID).T
    groups = dict(all=np.ones(len(V), bool), qx_short=qx < 2, qy_short=qy < 2,
                  interior=(qx >= 2) & (qy >= 2))
    totals = {side: {scope: {g: dict(old=0., matched=0., curves=0., values=0)
        for g in groups} for scope in ("rectangle", "physical")}
        for side in ("all", "heldout_source", "construction_source")}
    for start in range(0, CELLS, 8192):
        end = min(start + 8192, CELLS)
        values = errors[start:end][:, V].astype("i4")
        curve = centers[codes[start:end]][:, V].astype("i4")
        losses = dict(old=np.abs(values - old[start:end, None]),
            matched=np.abs(values - matched[start:end, None]), curves=np.abs(values - curve))
        ry = np.arange(start, end) % 12
        for side, rows in (("all", np.ones(end - start, bool)),
                           ("heldout_source", HOLDOUT[start:end]),
                           ("construction_source", ~HOLDOUT[start:end])):
            for scope in ("rectangle", "physical"):
                valid = (12 * qy[None] + ry[:, None] <= 549) if scope == "physical" else np.ones_like(values, bool)
                for g, columns in groups.items():
                    mask = rows[:, None] & valid & columns[None]
                    weights = WEIGHTS[V][None] * mask
                    record = totals[side][scope][g]
                    record["values"] += int(mask.sum())
                    for name, loss in losses.items():
                        record[name] += float((loss * weights).sum())
    primary = totals["heldout_source"]["physical"]["all"]
    primary_gate = all(primary["curves"] <= .95 * primary[name] for name in ("old", "matched"))
    overall = totals["all"]["physical"]["all"]
    overall_gate = all(overall["curves"] <= overall[name] for name in ("old", "matched"))
    group_gate = all(v["curves"] <= v[name] for key, v in totals["heldout_source"]["physical"].items()
        if key != "all" for name in ("old", "matched"))
    write(ROOT / "report.json", dict(totals=totals, primary_gate=bool(primary_gate),
        overall_gate=bool(overall_gate), group_gate=bool(group_gate),
        continue_full=bool(primary_gate and overall_gate and group_gate),
        source_split="Codebooks fit other sources; each heldout source cell selects its code on T only.",
        validation_values_in_codebook_construction_sources=True,
        validation_values_in_heldout_codebook_training=False,
        full_population_scored=False, complete_program_measured=False,
        new_exact_labels=0, final_accuracy_goal_verified=False))
    print("EXP650_RESULT", primary["curves"] / primary["old"],
          primary["curves"] / primary["matched"], primary_gate, overall_gate, group_gate, flush=True)


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp650")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
    started, cpu = time.monotonic(), time.process_time()
    fit_ids = prepare()
    errors = extract()
    evaluate(errors, *fit(errors, fit_ids))
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    files = [p for p in BUILD.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    wall = time.monotonic() - started
    combined = time.process_time() - cpu + child.ru_utime + child.ru_stime
    assert total <= 1_200_000_000 and wall <= 1800 and combined <= 3600
    write(ROOT / "resources.json", dict(cpu_s=combined, wall_s=wall,
        own_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        child_rss_bytes=child.ru_maxrss * 1024, new_file_bytes=total,
        complete_program_runs=0, disk_free_end_bytes=shutil.disk_usage(".").free))


if __name__ == "__main__":
    main()
