#!/usr/bin/env python3
"""Validate fixed D64 residual curves over all phases and four directions."""
import gc
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp650/validation").resolve()))
import exp650_distance_curves as proto

prior, finite, scalar = proto.prior, proto.finite, proto.scalar
read, write, identity, checked = proto.read, proto.write, proto.identity, proto.checked
ROOT, BUILD = Path("validation/results/exp651"), Path("build/exp651")
PLAN = Path("experiment/实验651-共享距离残量曲线的全相位四方向验证.md")
PAIRS, PHASES, CELLS, FIT_ROWS = 59904, 120, 59904 * 120, 16384
GRID, TRAIN, VALID, T, V, WEIGHTS = proto.GRID, proto.TRAIN, proto.VALID, proto.T, proto.V, proto.WEIGHTS
HOLDOUT = ((np.arange(CELLS) // (288 * PHASES)) // 8) % 4 == 0
NATIVE = Path("../exp650/build/exp650/assign")
proto.speed.ROOT = ROOT


def self_check():
    proto.self_check()
    assert len(np.unique(np.flatnonzero(HOLDOUT) // (288 * PHASES))) == 56
    context = np.arange(480)[:, None]
    qx, qy = np.asarray(GRID).T
    assert np.array_equal(prior.local(context, qx[None], qy[None]),
                          context * 542 + np.arange(542)[None])
    for direction in range(4):
        phase = np.arange(PHASES)[:, None]
        dx, dy = 10 * qx[None] + phase // 12, 12 * qy[None] + phase % 12
        physical = ((dx <= 119) & (dy <= 549)
                    & ((dx > 0) | (direction // 2 == 0))
                    & ((dy > 0) | (direction % 2 == 0)))
        assert physical.shape == (PHASES, 542) and physical.any(axis=1).all()
    a = np.arange(PAIRS * 480, dtype="u4").reshape(PAIRS, 480)
    for d in range(4):
        view = a[:, d * PHASES:(d + 1) * PHASES].reshape(-1)
        for j in (0, 119, CELLS - 1):
            assert view[j] == (j // PHASES) * 480 + d * PHASES + j % PHASES


def prepare():
    self_check()
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    assert read("../exp650/validation/results/exp650/close-audit.json")["all_checks_passed"]
    assert shutil.disk_usage(".").free >= 70_000_000_000
    checked(prior.GEOMETRY, read("../exp589/validation/results/exp589/candidate-freeze.json")["arms"]["D64"]["geometry"])
    q4 = Path("../exp619/build/exp619/Q4.p4")
    checked(q4, read("../exp619/validation/results/exp619/training.json")["asset"])
    fits = []
    eligible = np.flatnonzero(~HOLDOUT)
    for direction in range(4):
        selected = np.random.default_rng(20261024651 + direction).choice(eligible, FIT_ROWS, replace=False)
        assert len(np.unique(selected)) == FIT_ROWS and not HOLDOUT[selected].any()
        selected.astype("<u4").tofile(BUILD / f"D{direction}-fit-ids.u32")
        fits.append(selected)
    mapping = read(prior.PREPARATION / "mapping.json")
    fields = read(prior.PREPARATION / "fields.json")
    certificate = read(prior.PREPARATION / "label-report.json")
    assert certificate["evidence_passed"] and certificate["certified_values"] == PAIRS * 264960
    assert [r["number"] for r in fields] == list(range(208))
    assert len(mapping["sources"]) == 208 and len(mapping["targets"]) == 288
    sources = [Path(__file__), PLAN, ROOT / "protocol-original.md", prior.GEOMETRY, q4, NATIVE,
               Path(proto.__file__), Path(finite.__file__), Path(scalar.__file__), Path(prior.__file__),
               Path(inspect.getsourcefile(prior.load_field)), prior.PREPARATION / "mapping.json",
               prior.PREPARATION / "fields.json", prior.PREPARATION / "label-report.json",
               *(BUILD / f"D{d}-fit-ids.u32" for d in range(4))]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in sources],
        train=TRAIN, validation=VALID, grid=GRID, fit_rows_per_direction=FIT_ROWS,
        seeds=[20261024651 + d for d in range(4)],
        initialization_seeds=[20261025651 + d for d in range(4)],
        cells_per_direction=CELLS, heldout_source_ports=56, numpy=np.__version__,
        self_check_passed=True, frozen_before_values=True, new_exact_labels=0,
        complete_program_runs=0, disk_free_start_bytes=shutil.disk_usage(".").free))
    (ROOT / "installed-numpy-help.txt").write_text(np.take.__doc__ + "\n" + np.memmap.__doc__)
    WEIGHTS[T].astype("<f8").tofile(BUILD / "weights.f64")
    proto.speed.measured([str(NATIVE), "--self-check"], "native-self-check")
    assert read(ROOT / "native-self-check.stdout")["self_check_passed"]
    return fits, mapping, fields


def nominal(center, left, right, ls, rs, pairs, contexts, coords, paired=False):
    qx, qy = np.asarray(coords).T
    columns = prior.local(contexts[:, None], qx[None], qy[None])
    direction = contexts[0] // PHASES
    if paired:
        product = np.einsum("ik,ijk->ij", left[direction * PAIRS + pairs].astype("f8"),
                            right[columns].astype("f8"), optimize=False)
        value = product * ls[direction * PAIRS + pairs].astype("f8")[:, None]
        value *= rs[columns].astype("f8")
    else:
        columns = columns.ravel()
        product = left[direction * PAIRS + pairs].astype("f8") @ right[columns].astype("f8").T
        value = product * ls[direction * PAIRS + pairs].astype("f8")[:, None]
        value *= rs[columns].astype("f8")[None]
        value = value.reshape(len(pairs), len(contexts), len(coords))
    assert np.array_equal(product, np.rint(product))
    value *= 128 + 125 * qx + 125 * qy
    value += center[pairs][(...,) + (None,) * (value.ndim - 1)]
    value += 125 * qx
    value += (125 if direction % 2 else 127) * qy
    return (np.maximum(value, 0) + .5).astype("i4")


def extract(fits, mapping, fields):
    model = prior.model()
    qx, qy = np.asarray(TRAIN + VALID).T
    gx, gy = np.asarray(GRID).T
    train, valid, samples = [], [], []
    for d in range(4):
        train.append(np.memmap(BUILD / f"D{d}-train.i16", "<i2", "w+", shape=(PAIRS, PHASES, len(T))))
        valid.append(np.memmap(BUILD / f"D{d}-valid.i16", "<i2", "w+", shape=(PAIRS, PHASES, len(V))))
        samples.append(np.empty((FIT_ROWS, 542), "<i2"))
    audits, records = 0, []
    for item in fields:
        source = item["number"]
        field = prior.load_field(item, mapping)
        pairs = np.arange(source * 288, (source + 1) * 288)
        ranges = []
        for d in range(4):
            contexts = d * PHASES + np.arange(PHASES)
            predicted = nominal(*model, pairs, contexts, TRAIN + VALID)
            truth = field[d][..., qx, qy].transpose(2, 0, 1, 3).reshape(288, PHASES, len(qx)).astype("i4")
            truth += 125 * qx + (125 if d % 2 else 127) * qy
            errors = truth - predicted
            assert abs(errors).max() <= 32767
            train[d][pairs], valid[d][pairs] = errors[..., :len(T)], errors[..., len(T):]
            positions = np.flatnonzero((fits[d] // (288 * PHASES)) == source)
            chosen = fits[d][positions]
            fp, phase = chosen // PHASES, chosen % PHASES
            if len(chosen):
                predicted_fit = nominal(*model, fp, d * PHASES + phase, GRID, True)
                truth_fit = field[d, phase // 12, phase % 12, fp % 288][:, gx, gy].astype("i4")
                truth_fit += 125 * gx + (125 if d % 2 else 127) * gy
                residual_fit = truth_fit - predicted_fit
                assert abs(residual_fit).max() <= 32767
                assert np.array_equal(residual_fit[:, T], errors[fp % 288, phase, :len(T)])
                assert np.array_equal(residual_fit[:, V], errors[fp % 288, phase, len(T):])
                samples[d][positions] = residual_fit
            if source in (0, 207):
                center, left, right, ls, rs = model
                for target, phase_one, g in ((0, 0, 0), (73, 39, 17), (171, 104, 61), (287, 119, 92)):
                    pair, context = source * 288 + target, d * PHASES + phase_one
                    x, y = (TRAIN + VALID)[g]
                    column = int(prior.local(context, x, y))
                    dot = sum(int(a) * int(b) for a, b in zip(left[d * PAIRS + pair], right[column]))
                    value = dot * float(ls[d * PAIRS + pair]) * float(rs[column])
                    value *= 128 + 125 * x + 125 * y
                    value += int(center[pair])
                    value += 125 * x
                    value += (125 if d % 2 else 127) * y
                    expected = int(field[d, phase_one // 12, phase_one % 12, target, x, y])
                    expected += 125 * x + (125 if d % 2 else 127) * y
                    assert errors[target, phase_one, g] == expected - int(max(value, 0) + .5)
                    audits += 1
            ranges.append(dict(direction=d, minimum=int(errors.min()), maximum=int(errors.max())))
        records.append(dict(source=source, raw_sha256=item["raw_sha256"], ranges=ranges))
        if source % 8 == 0:
            print("EXP651_FIELD", source, flush=True)
    for d in range(4):
        train[d].flush()
        valid[d].flush()
        samples[d].tofile(BUILD / f"D{d}-samples.i16")
    old = np.memmap("../exp650/build/exp650/errors.i16", "<i2", "r", shape=(PAIRS, 12, 542))
    for start in range(0, PAIRS, 288):
        assert np.array_equal(train[0][start:start + 288, :12], old[start:start + 288][:, :, T])
        assert np.array_equal(valid[0][start:start + 288, :12], old[start:start + 288][:, :, V])
    del old, train, valid
    gc.collect()
    write(ROOT / "extraction.json", dict(files=[identity(BUILD / f"D{d}-{name}.i16")
        for d in range(4) for name in ("train", "valid", "samples")],
        source_records=records, independent_integer_dot_audits=audits,
        sample_training_and_validation_equal=True, exp650_full_rx0_equal=True,
        nominal_values_per_cell=len(T) + len(V)))
    return samples


def assign(path, centers, name, count):
    cp = BUILD / (name + "-centers.i16")
    np.ascontiguousarray(centers[:, T], dtype="<i2").tofile(cp)
    prefix = BUILD / name
    run = proto.speed.measured([str(NATIVE), str(path), str(cp), str(BUILD / "weights.f64"),
                               str(count), str(len(T)), str(prefix)], name)
    assert run["threads"] == 1 and run["cpu_s"] <= 600
    codes = np.fromfile(str(prefix) + ".codes.u8", "u1")
    losses = np.fromfile(str(prefix) + ".losses.f64", "<f8")
    assert len(codes) == len(losses) == count and np.isfinite(losses).all()
    return codes, losses


def fit(direction, samples, levels):
    centers = np.empty((256, 542), "<i2")
    centers[:16] = levels[:, None]
    selected = np.random.default_rng(20261025651 + direction).choice(FIT_ROWS, 240, replace=False)
    centers[16:] = samples[selected]
    path = BUILD / f"D{direction}-fit-values.i16"
    np.ascontiguousarray(samples[:, T], dtype="<i2").tofile(path)
    codes, losses = assign(path, centers, f"D{direction}-fit-0", FIT_ROWS)
    history = [float(losses.sum())]
    for iteration in range(1, 7):
        for code in range(16, 256):
            selected = samples[codes == code]
            if len(selected):
                centers[code] = proto.median(selected)
        assert np.array_equal(centers[:16], np.broadcast_to(levels[:, None], (16, 542)))
        codes, losses = assign(path, centers, f"D{direction}-fit-{iteration}", FIT_ROWS)
        history.append(float(losses.sum()))
        assert history[-1] <= history[-2] + 1e-10 * max(1., history[-2])
    train = np.memmap(BUILD / f"D{direction}-train.i16", "<i2", "r", shape=(CELLS, len(T)))
    codes, losses = np.empty(CELLS, "u1"), np.empty(CELLS, "f8")
    for part in range(10):
        start, end = part * proto.CELLS, (part + 1) * proto.CELLS
        path = BUILD / "assign-values.i16"
        train[start:end].tofile(path)
        codes[start:end], losses[start:end] = assign(path, centers, f"D{direction}-part-{part}", end - start)
    scalar_codes = np.empty(CELLS, "u1")
    for start in range(0, CELLS, 8192):
        end = min(start + 8192, CELLS)
        scalar_codes[start:end], best = finite.choose_levels(train[start:end].astype("i4"), WEIGHTS[T], levels)
        assert np.all(losses[start:end] <= best + 1e-10 * np.maximum(1., best))
    audit_ids = np.random.default_rng(20261027651 + direction).choice(CELLS, 64, replace=False)
    for i in audit_ids:
        options = (abs(train[i].astype("i4")[None] - centers[:, T]) * WEIGHTS[T]).sum(axis=1)
        best = 0
        for c in range(1, 256):
            if options[c] < options[best] - 1e-12 * max(1., options[best]):
                best = c
        assert codes[i] == best and abs(losses[i] - options[best]) <= 1e-10 * max(1., losses[i])
    write(ROOT / f"D{direction}-training.json", dict(losses=history,
        all_training_cells_scalar_inclusion=True, independent_native_assign_audits=64,
        constants_preserved=True, code_counts=np.bincount(codes, minlength=256).tolist()))
    return centers, codes, scalar_codes


def evaluate(direction, centers, codes, scalar_codes, levels, old):
    valid = np.memmap(BUILD / f"D{direction}-valid.i16", "<i2", "r", shape=(CELLS, len(V)))
    old = old[:, direction * PHASES:(direction + 1) * PHASES].reshape(-1).astype("i4")
    qx, qy = np.asarray(VALID).T
    groups = dict(all=np.ones(len(V), bool), qx_short=qx < 2, qy_short=qy < 2,
                  interior=(qx >= 2) & (qy >= 2))
    totals = {side: {scope: {g: dict(old=0., matched=0., curves=0., values=0) for g in groups}
        for scope in ("rectangle", "physical")} for side in ("all", "heldout_source", "construction_source")}
    rx_totals = [dict(old=0., matched=0., curves=0., values=0) for _ in range(10)]
    for start in range(0, CELLS, 8192):
        end = min(start + 8192, CELLS)
        values = valid[start:end].astype("i4")
        curve = centers[codes[start:end]][:, V].astype("i4")
        losses = dict(old=abs(values - old[start:end, None]),
                      matched=abs(values - levels[scalar_codes[start:end], None]),
                      curves=abs(values - curve))
        phase = np.arange(start, end) % PHASES
        dx, dy = 10 * qx[None] + phase[:, None] // 12, 12 * qy[None] + phase[:, None] % 12
        physical = ((dx <= 119) & (dy <= 549)
                    & ((dx > 0) | (direction // 2 == 0)) & ((dy > 0) | (direction % 2 == 0)))
        for side, rows in (("all", np.ones(end - start, bool)),
                           ("heldout_source", HOLDOUT[start:end]),
                           ("construction_source", ~HOLDOUT[start:end])):
            for scope in ("rectangle", "physical"):
                for g, columns in groups.items():
                    mask = rows[:, None] & columns[None]
                    if scope == "physical":
                        mask = mask & physical
                    record = totals[side][scope][g]
                    record["values"] += int(mask.sum())
                    weights = WEIGHTS[V][None] * mask
                    for name, loss in losses.items():
                        record[name] += float((loss * weights).sum())
        for rx, record in enumerate(rx_totals):
            mask = HOLDOUT[start:end, None] & physical & (phase[:, None] // 12 == rx)
            record["values"] += int(mask.sum())
            for name, loss in losses.items():
                record[name] += float((loss * WEIGHTS[V][None] * mask).sum())
    primary = totals["heldout_source"]["physical"]["all"]
    primary_gate = all(primary["curves"] <= .95 * primary[name] for name in ("old", "matched"))
    overall = totals["all"]["physical"]["all"]
    overall_gate = all(overall["curves"] <= overall[name] for name in ("old", "matched"))
    group_gate = all(v["curves"] <= v[name] for key, v in totals["heldout_source"]["physical"].items()
                     if key != "all" for name in ("old", "matched"))
    rx_gate = all(v["curves"] <= v[name] for v in rx_totals for name in ("old", "matched"))
    passed = bool(primary_gate and overall_gate and group_gate and rx_gate)
    write(ROOT / f"D{direction}-report.json", dict(totals=totals, rx_totals=rx_totals,
        primary_gate=bool(primary_gate), overall_gate=bool(overall_gate),
        group_gate=bool(group_gate), rx_gate=bool(rx_gate), gate=passed))
    print("EXP651_DIRECTION", direction, primary["curves"] / primary["old"],
          primary["curves"] / primary["matched"], passed, flush=True)
    return passed


def cached_quality(codes, centers):
    sys.path.insert(0, str(Path("../exp592/validation").resolve()))
    from exp592_xgb_audit import decode, points, stats, transition
    data_path = Path("../exp623/build/exp623/data.npz")
    raw_path = Path("../exp640/build/exp640/S8-raw.f64")
    keys_path = Path("../exp615/build/exp615/keys.bin")
    checked(data_path, read("../exp623/validation/results/exp623/prepare.json")["data"])
    checked(raw_path, read("../exp640/validation/results/exp640/training.json")["raw"]["S8"])
    checked(keys_path, read("../exp615/validation/results/exp615/freeze.json")["keys"])
    write(ROOT / "evaluation-freeze.json", dict(inputs=[identity(p) for p in (data_path, raw_path, keys_path)],
        seed=20261026651, bootstrap=9999, independent_requests=False, complete_program_runs=0))
    with np.load(data_path) as packed:
        data = {k: packed[k] for k in packed.files}
    pair, context, qx, qy = np.fromfile(keys_path, "<u4", offset=12).reshape(-1, 4).T
    raw = np.fromfile(raw_path, "<f8")
    far = qx + qy > 3
    old = scalar.unpack(Path("../exp619/build/exp619/Q4.p4"))[pair, context].astype("i4")
    old[~far] = 0
    correction = np.zeros(len(pair), "i4")
    g = prior.local(np.zeros(int(far.sum()), "i4"), qx[far], qy[far])
    correction[far] = centers[context[far] // PHASES, codes[pair[far], context[far]], g]
    base = data["base"] - old + correction
    a, b = decode(raw, data["base"], data["mandatory"]), decode(raw, base, data["mandatory"])
    assert stats(a, data["truth"]) == read("../exp647/validation/results/exp647/report.json")["metrics"]["A"]
    assert np.array_equal(a[~far], b[~far])
    partitions = {k: data[k] for k in ("source_family", "distance", "near_axis", "forced")}
    partitions["direction"] = context // PHASES
    result = transition(b, a, data["truth"], partitions)
    family = data["source_family"]
    counts = np.bincount(family, minlength=26)
    assert len(counts) == 26 and (counts > 0).all()
    delta = points(b, data["truth"]) - points(a, data["truth"])
    sums = np.bincount(family, weights=delta, minlength=26)
    draws = np.random.default_rng(20261026651).integers(26, size=(9999, 26))
    interval = np.quantile(sums[draws].sum(axis=1) / counts[draws].sum(axis=1), [.025, .975]).tolist()
    group_minimum = min(v["delta_accuracy_pp"] for k, group in result["groups"].items()
                        if k in ("distance", "near_axis", "direction", "forced") for v in group.values())
    passed = result["delta_accuracy_pp"] >= .02 and interval[0] > 0 and group_minimum >= -.03
    zero = np.zeros(len(pair), "f8")
    result.update(ci95_delta_accuracy_pp=interval, changed_rows=int((a != b).sum()),
                  quality_gate=bool(passed), near_unchanged=True)
    write(ROOT / "evaluation.json", dict(comparison=result, continue_cli=bool(passed),
        no_tree_metrics=dict(original=stats(decode(zero, data["base"], data["mandatory"]), data["truth"]),
                             curves=stats(decode(zero, base, data["mandatory"]), data["truth"])),
        independent_requests=False, complete_program_measured=False, new_exact_labels=0))
    print("EXP651_CACHED", result["delta_accuracy_pp"], interval, bool(passed), flush=True)


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp651")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (7200, 7200))
    started, cpu = time.monotonic(), time.process_time()
    fits, mapping, fields = prepare()
    samples = extract(fits, mapping, fields)
    old = scalar.unpack(Path("../exp619/build/exp619/Q4.p4"))
    levels = np.fromfile("../exp619/build/exp619/Q4.p4", "i1", count=16, offset=32)
    all_codes, all_centers, gates = np.empty((PAIRS, 480), "u1"), [], []
    for direction in range(4):
        centers, codes, scalar_codes = fit(direction, samples[direction], levels)
        gates.append(evaluate(direction, centers, codes, scalar_codes, levels, old))
        all_codes[:, direction * PHASES:(direction + 1) * PHASES] = codes.reshape(PAIRS, PHASES)
        all_centers.append(centers)
    all_centers = np.asarray(all_centers, dtype="<i2")
    asset = BUILD / "D64.curves"
    with asset.open("xb") as stream:
        stream.write(b"EX651C01" + struct.pack("<6I", PAIRS, 4, PHASES, 542, 256, 2) + bytes(32))
        stream.write(all_codes.tobytes())
        stream.write(all_centers.tobytes())
    raw = asset.read_bytes()
    assert len(raw) == 29_864_000
    assert np.array_equal(np.frombuffer(raw, "u1", count=PAIRS * 480, offset=64).reshape(PAIRS, 480), all_codes)
    assert np.array_equal(np.frombuffer(raw, "<i2", offset=64 + PAIRS * 480).reshape(4, 256, 542), all_centers)
    write(ROOT / "nominal-decision.json", dict(direction_gates=gates, continue_cached=all(gates),
        asset=identity(asset), full_roundtrip=True, all_phases_and_directions=True,
        new_exact_labels=0, complete_program_runs=0, final_accuracy_goal_verified=False))
    if all(gates):
        del samples, old
        gc.collect()
        cached_quality(all_codes, all_centers)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall, combined = time.monotonic() - started, time.process_time() - cpu + child.ru_utime + child.ru_stime
    total = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert combined <= 7200 and wall <= 3600 and total <= 6_500_000_000
    write(ROOT / "resources.json", dict(cpu_s=combined, wall_s=wall, new_file_bytes=total,
        own_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        child_rss_bytes=child.ru_maxrss * 1024, complete_program_runs=0,
        disk_free_end_bytes=shutil.disk_usage(".").free))


if __name__ == "__main__":
    main()
