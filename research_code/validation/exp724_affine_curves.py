#!/usr/bin/env python3
"""Test a shared pair plane before the frozen two-code curve construction."""
import os
from pathlib import Path
import resource
import shutil
import sys
import time

import numpy as np

import exp689_full_response as previous

ROOT, BUILD = Path("validation/results/exp724"), Path("build/exp724")
PLAN = Path("experiment/实验724-端口对仿射主体与双码距离形状.md")
OLD = Path("validation/results/exp689")
read, write, identity, checked = previous.read, previous.write, previous.identity, previous.checked
GRID, T, V, W, HOLD = previous.GRID, previous.T, previous.V, previous.W, previous.HOLD
PAIRS, CELLS = previous.PAIRS, previous.CELLS


def configure():
    previous.ROOT, previous.BUILD = ROOT, BUILD
    previous.START = time.monotonic()


def arrays():
    old = read(OLD/"extraction.json")
    for item in old["assets"]:
        checked(item["path"], item)
    return [np.fromfile("build/exp689/"+n+".i16", "<i2").reshape(CELLS, 542)
            for n in ("values", "truth", "baseline")]


def plane(values):
    x = np.column_stack((np.ones(542), GRID)).astype("f8")
    mean = values.reshape(PAIRS, 2, 542)[:, :, T].mean(axis=1)
    normal = (x[T].T*W[T])@x[T]
    rhs = (mean*W[T])@x[T]
    beta = np.linalg.solve(normal, rhs.T).T
    assert np.allclose(beta@normal, rhs, rtol=1e-11, atol=1e-10)
    quantized = np.floor(64*beta+.5).astype("i8")
    assert quantized.min() >= -(2**31) and quantized.max() < 2**31
    restored = (np.matmul(quantized, x.astype("i8").T)+32)//64
    bound = (1+GRID.sum(axis=1))/128+.5
    assert np.all(np.abs(restored-beta@x.T) <= bound+1e-10)
    ids = np.linspace(0, PAIRS-1, 64, dtype=int)
    weighted_x = x[T]*np.sqrt(W[T, None])
    for i in ids:
        independent = np.linalg.lstsq(weighted_x, mean[i]*np.sqrt(W[T]), rcond=None)[0]
        assert np.allclose(independent, beta[i], rtol=1e-10, atol=1e-8)
    quantized.astype("<i4").tofile(BUILD/"pair-plane.i32")
    assert np.array_equal(np.fromfile(BUILD/"pair-plane.i32", "<i4").reshape(PAIRS, 3), quantized)
    residual = previous.i16(values.astype("i4")-np.repeat(restored, 2, axis=0))
    assert np.array_equal(residual.astype("i4")+np.repeat(restored, 2, axis=0), values)
    write(ROOT/"plane-check.json", dict(
        normal_rank=int(np.linalg.matrix_rank(normal)), independent_lstsq_checks=len(ids),
        coefficient_min=quantized.min(axis=0).tolist(), coefficient_max=quantized.max(axis=0).tolist(),
        fixedpoint_max_error_ps=float(np.max(np.abs(restored-beta@x.T))),
        fixedpoint_bound_ps=float(bound.max()), exact_decomposition=True,
        residual_min=int(residual.min()), residual_max=int(residual.max()),
        asset=identity(BUILD/"pair-plane.i32")))
    return residual, np.repeat(restored, 2, axis=0)


def fit(values, fit_ids):
    rng = np.random.default_rng(previous.SEED)
    assert np.array_equal(rng.choice(np.flatnonzero(~HOLD), 16384, replace=False), fit_ids)
    samples = values[fit_ids].astype("i4")
    centers = [samples[rng.choice(len(samples), 256, replace=False)].copy()]
    a, _ = previous.assign(samples, centers[0], "init-0")
    remainder = samples-centers[0][a]
    centers.append(remainder[rng.choice(len(samples), 128, replace=False)].copy())
    b, loss = previous.assign(remainder, centers[1], "init-1")
    chosen, history = [a, b], [float(loss.sum())]
    for iteration in range(8):
        for side in (0, 1):
            remainder = samples-centers[1-side][chosen[1-side]]
            for k in range(len(centers[side])):
                selected = remainder[chosen[side] == k]
                if len(selected):
                    centers[side][k] = previous.median(selected)
            chosen[side], loss = previous.assign(remainder, centers[side], f"fit-{iteration}-{side}")
            total = float(loss.sum())
            assert total <= history[-1]+1e-10*max(1., history[-1])
            history.append(total)
        print("EXP724_FIT", iteration+1, history[-1], flush=True)
    a, _ = previous.assign(values, centers[0], "all-init-0")
    b, loss = previous.assign(values.astype("i4")-centers[0][a], centers[1], "all-init-1")
    chosen, encoding = [a, b], [float(loss.sum())]
    for iteration in range(4):
        for side in (0, 1):
            remainder = values.astype("i4")-centers[1-side][chosen[1-side]]
            chosen[side], loss = previous.assign(remainder, centers[side], f"all-{iteration}-{side}")
            total = float(loss.sum())
            assert total <= encoding[-1]+1e-10*max(1., encoding[-1])
            encoding.append(total)
    code = chosen[0].astype("<u2") | (chosen[1].astype("<u2") << 8)
    packed = previous.pack(code)
    assert np.array_equal(previous.unpack(packed, CELLS), code)
    packed.tofile(BUILD/"codes.p15")
    for k, center in enumerate(centers):
        previous.i16(center).tofile(BUILD/f"centers-{k}.i16")
        assert np.array_equal(np.fromfile(BUILD/f"centers-{k}.i16", "<i2").reshape(center.shape), center)
    return centers, chosen, history, encoding


def evaluate(truth, baseline, candidate):
    reports = {}
    for name, selected in (("T", T), ("V", V)):
        reports[name] = {}
        for label, rows in (("heldout_source", HOLD), ("construction_source", ~HOLD),
                            ("all", np.ones(CELLS, bool)),
                            ("heldout_phase0", HOLD & (np.arange(CELLS) % 2 == 0)),
                            ("heldout_phase1", HOLD & (np.arange(CELLS) % 2 == 1))):
            reports[name][label] = {}
            for group, mask in (("all", np.ones(len(selected), bool)),
                                ("qx_short", GRID[selected, 0] < 2),
                                ("qy_short", GRID[selected, 1] < 2)):
                columns = selected[mask]
                gt, old, new = [a[rows][:, columns].astype("i4") for a in (truth, baseline, candidate)]
                losses = [float((np.abs(p-gt)*W[columns]).sum()) for p in (old, new)]
                scores = [float(previous.points(p, gt).mean()) for p in (old, new)]
                reports[name][label][group] = dict(values=int(gt.size),
                    old_weighted_l1=losses[0], new_weighted_l1=losses[1],
                    weighted_l1_ratio=losses[1]/losses[0], old_nominal_score_pp=scores[0],
                    new_nominal_score_pp=scores[1], nominal_delta_pp=scores[1]-scores[0])
    test = reports["V"]["heldout_source"]
    selected = (test["all"]["weighted_l1_ratio"] <= 1.02 and test["all"]["nominal_delta_pp"] >= -.01
                and all(test[k]["nominal_delta_pp"] >= -.03 for k in ("qx_short", "qy_short")))
    return reports, selected


def run():
    assert os.environ["OPENBLAS_NUM_THREADS"] == os.environ["OMP_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_AS, (8_000_000_000, 8_000_000_000))
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    configure()
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    old_report, old_audit, old_freeze = [read(OLD/n) for n in ("report.json", "close-audit.json", "freeze.json")]
    assert old_audit["all_checks_passed"]
    checked(OLD/"report.json", old_audit["report"])
    input_ids = next(x for x in old_freeze["files"] if x["path"] == "build/exp689/fit-ids.u32")
    checked(input_ids["path"], input_ids)
    fit_ids = np.fromfile(input_ids["path"], "<u4")
    budget = old_freeze["budget_bytes"]+4*PAIRS*3*4
    assert budget == 99_810_933 and budget < 100_000_000
    write(ROOT/"freeze.json", dict(
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md",
            Path(previous.__file__), Path("validation/exp650_curve_assign.cpp"),
            OLD/"freeze.json", OLD/"extraction.json", OLD/"report.json", OLD/"close-audit.json",
            Path(input_ids["path"]))],
        input_arrays=read(OLD/"extraction.json")["assets"], budget_bytes=budget, q=64,
        codebook_seed=previous.SEED, fit_rows=len(fit_ids), iterations=8, encode_sweeps=4,
        complete_program_runs=0, new_exact_labels=0, disk_free_start_bytes=shutil.disk_usage(".").free))
    (ROOT/"installed-help.txt").write_text(np.linalg.solve.__doc__+"\n"+np.linalg.lstsq.__doc__)
    # Reuse the already checked exact assignment kernel without rebuilding it.
    shutil.copy2("build/exp689/assign", BUILD/"assign")
    write(ROOT/"assignment-kernel.json", dict(source=identity("build/exp689/assign"), copied=identity(BUILD/"assign")))
    previous.run([str(BUILD/"assign"), "--self-check"], "native-self-check")
    every = np.arange(32768, dtype="<u2")
    assert np.array_equal(previous.unpack(previous.pack(every), len(every)), every)
    for n in range(-200, 201):
        assert (n+32)//64 == int(np.floor(n/64+.5))
    W[T].astype("<f8").tofile(BUILD/"weights.f64")
    values, truth, baseline = arrays()
    residual, restored = plane(values)
    centers, chosen, history, encoding = fit(residual, fit_ids)
    candidate = np.maximum(truth.astype("i4")-values+restored+
                           centers[0][chosen[0]]+centers[1][chosen[1]], 0)
    reports, selected = evaluate(truth, baseline, candidate)
    usage = previous.resources()
    assert usage["cpu_s"] <= 1200 and usage["wall_s"] <= 1800
    assert usage["peak_process_rss_bytes"] <= 8_000_000_000
    comparison = old_report["reports"]["V"]["heldout_source"]["all"]
    test = reports["V"]["heldout_source"]["all"]
    write(ROOT/"report.json", dict(all_structure_checks_passed=True, selected=selected,
        reports=reports, resources=usage, training_losses=history, encoding_losses=encoding,
        against_exp689_nominal_delta_pp=test["new_nominal_score_pp"]-comparison["new_nominal_score_pp"],
        against_exp689_weighted_l1_ratio=test["new_weighted_l1"]/comparison["new_weighted_l1"],
        budget_bytes=budget, complete_program_runs=0, new_exact_labels=0,
        assets=[identity(BUILD/n) for n in ("pair-plane.i32", "codes.p15", "centers-0.i16", "centers-1.i16")]))
    print("EXP724_COMPLETE", selected, test, flush=True)


def audit():
    report, frozen = read(ROOT/"report.json"), read(ROOT/"freeze.json")
    for item in frozen["files"]+report["assets"]:
        checked(item["path"], item)
    assert all(np.all(np.diff(report[k]) <= 1e-8) for k in ("training_losses", "encoding_losses"))
    raw = (BUILD/"codes.p15").read_bytes()
    code = np.array([(int.from_bytes(raw[i*15//8:i*15//8+3], "little") >> (i*15%8)) & 32767
                     for i in range(CELLS)], dtype="u2")
    coefficients = np.fromfile(BUILD/"pair-plane.i32", "<i4").reshape(PAIRS, 3).astype("i8")
    curves = [np.fromfile(BUILD/f"centers-{k}.i16", "<i2").reshape(n, 542).astype("i4")
              for k, n in enumerate((256, 128))]
    values, truth, baseline = arrays()
    rebuilt_plane = np.empty((PAIRS, 542), "i4")
    for g, (qx, qy) in enumerate(GRID):
        numerator = coefficients[:, 0]+coefficients[:, 1]*int(qx)+coefficients[:, 2]*int(qy)+32
        rebuilt_plane[:, g] = np.floor_divide(numerator, 64)
    candidate = np.maximum(truth.astype("i4")-values+np.repeat(rebuilt_plane, 2, axis=0)
                           +curves[0][code & 255]+curves[1][code >> 8], 0)
    reports, selected = evaluate(truth, baseline, candidate)
    for scope in reports:
        for rows in reports[scope]:
            for group in reports[scope][rows]:
                for name, value in reports[scope][rows][group].items():
                    assert abs(value-report["reports"][scope][rows][group][name]) <= 1e-9
    gt, before, after = (a[HOLD][:, V].astype("f8") for a in (truth, baseline, candidate))
    assert np.all(gt > 0)
    delta = float((100*(np.tanh(4*np.abs(before-gt)/gt)-np.tanh(4*np.abs(after-gt)/gt))).mean())
    assert abs(delta-reports["V"]["heldout_source"]["all"]["nominal_delta_pp"]) < 1e-10
    assert selected == report["selected"]
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True, selected=selected,
        decoded_cells=CELLS, independently_decoded_planes=PAIRS*542, paired_nominal_delta_pp=delta,
        aggregation_reused=True, scalar_decode_independent=True,
        report=identity(ROOT/"report.json"), auditor=identity(__file__)))
    print("EXP724_AUDIT", selected, delta, flush=True)


if __name__ == "__main__":
    assert sys.argv[1:] in (["run"], ["audit"])
    dict(run=run, audit=audit)[sys.argv[1]]()
