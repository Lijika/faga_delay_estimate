#!/usr/bin/env python3
"""Calibrate fixed R8 leaves against the integer Q4 prediction on r9."""
import json
from pathlib import Path
import re
import resource
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp622/validation").resolve()))
import exp622_r8_specialization as old
sys.path.insert(0, str(Path("../exp614/validation").resolve()))
import exp614_gemini_features as data_source
sys.path.insert(0, str(Path("../exp592/validation").resolve()))
from exp592_xgb_audit import decode, points, transition

ROOT, BUILD = Path("validation/results/exp623"), Path("build/exp623")
PLAN = Path("experiment/实验623-Q4背景上的固定树叶值校准.md")
read, write, identity, check = old.read, old.write, old.identity, old.check
speed = old.speed
speed.ROOT = ROOT
ROWS, SEED = 1000000, 20261023623
OFFSETS = np.asarray([.25, -.25, .5, -.5, 1, -1, 2, -2, 4, -4, 8, -8, 16, -16, 32, -32], dtype="<f4")


def raw_sum(contributions):
    assert contributions.dtype == np.dtype("<f4") and contributions.shape[1] == 8
    result = np.zeros(len(contributions), dtype="<f4")
    for t in range(8):
        np.add(result, contributions[:, t], out=result)
    return result


def loss(raw, base, mandatory, truth):
    prediction = decode(raw, base, mandatory)
    return float(np.tanh(4 * np.abs(prediction.astype("f8") - truth) / truth).sum(dtype="f8"))


def update(work, tree, origin, base, mandatory, truth):
    before = loss(raw_sum(work), base, mandatory, truth)
    best, best_loss = np.float32(origin), before
    for offset in OFFSETS:
        trial = np.float32(origin + offset)
        work[:, tree] = trial
        candidate = loss(raw_sum(work), base, mandatory, truth)
        if candidate < best_loss - 1e-12:
            best, best_loss = trial, candidate
    work[:, tree] = best
    assert loss(raw_sum(work), base, mandatory, truth) == best_loss
    assert best_loss <= before
    return best, before, best_loss


def self_check():
    work = np.zeros((64, 8), dtype="<f4")
    base, mandatory = np.full(64, 1000, dtype="i4"), np.zeros(64, dtype="i4")
    v, a, b = update(work, 0, np.float32(0), base, mandatory, base)
    assert v == 0 and a == b == 0
    v, a, b = update(work, 0, np.float32(0), base, mandatory, base + 4)
    assert v == 4 and a > 0 and b == 0
    work[:] = [1e8, 1, -1e8, 3, 0, 0, 0, 0]
    assert np.all(raw_sum(work) == 3), "float32 original tree order"


def prepare():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    self_check()
    data = data_source.load()
    models, header = old.model_rows()
    original = np.asarray([[float.fromhex(v[:-1]) for v in row[2]] for row in models], dtype="<f4")
    original = original.reshape(64, 8, 16)
    np.save(BUILD / "original-values.npy", original)
    frozen = read("../exp619/validation/results/exp619/audit.json")["records"][1]["trace"]
    trace_path = Path("../exp619") / frozen["path"]
    check(trace_path, frozen)
    dtype = np.dtype(dict(names=["features", "response", "base", "mandatory", "prediction", "raw"],
        formats=[("<f4", (53,)), "<f8", "<i4", "<i4", "<i4", "<f4"],
        offsets=[0, 216, 224, 228, 232, 236], itemsize=240))
    trace = np.memmap(trace_path, dtype=dtype, mode="r", shape=(ROWS,))
    features = data["features"]
    assert np.array_equal(trace["features"].view("u4"), features.view("u4"))
    assert np.array_equal(trace["mandatory"], data["mandatory"]) and np.all(data["truth"] > 0)
    routes, folds = data["routes"], data["folds"]
    nx, ny = features[:, 8] + features[:, 6], features[:, 9] + features[:, 7]
    assert np.array_equal(routes, 4 * (2 * (nx < 0) + (ny < 0)) + 2 * (np.abs(nx) >= 20) + (np.abs(ny) >= 24))
    fields = dict(truth=data["truth"], base=trace["base"].copy(), mandatory=trace["mandatory"].copy(),
        routes=routes, folds=folds, source_family=features[:, 0].astype("i4"),
        distance=np.searchsorted([24, 100, 300], np.abs(nx) + np.abs(ny)),
        near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype("i4"),
        forced=features[:, 52].astype("i4"),
        target_mismatch=(data["d0"] + data["mandatory"] != data["truth"]).astype("i4"))
    np.savez(BUILD / "data.npz", **fields)
    paths = np.memmap(BUILD / "paths.u8", dtype="u1", mode="w+", shape=(4, ROWS, 8))
    f, cut = [np.asarray([m[j] for m in models]) for j in (0, 1)]
    row, tree = np.arange(ROWS)[:, None], np.arange(8)[None, :]
    oof = np.empty(ROWS, dtype="<f4")
    for fold in range(4):
        model = (16 * fold + routes).astype("i4")[:, None]
        path = np.zeros((ROWS, 8), dtype="u1")
        for depth in range(4):
            at = ((1 << depth) - 1 + path).astype("i4") * 8 + tree
            path = (2 * path + (features[row, f[model, at]] >= cut[model, at])).astype("u1")
        paths[fold] = path
        contributions = original[model, tree, path]
        raw = raw_sum(contributions)
        if fold == 0:
            assert np.array_equal(raw.view("u4"), trace["raw"].copy().view("u4"))
            raw.tofile(BUILD / "original-final.f32")
        else:
            mask = folds == fold - 1
            oof[mask] = raw[mask]
    paths.flush()
    expected = np.fromfile("../exp576/build/exp576/R8.f32", "<f4")
    assert np.array_equal(oof.view("u4"), expected.view("u4"))
    oof.tofile(BUILD / "original-oof.f32")
    write(ROOT / "prepare.json", dict(
        data=identity(BUILD / "data.npz"), paths=identity(BUILD / "paths.u8"),
        original_values=identity(BUILD / "original-values.npy"), model_header=identity(header),
        reference_trace=frozen, trace_path=str(trace_path), driver=identity(__file__),
        protocol=identity(ROOT / "protocol-original.md"), original_raw_bitwise=True,
        self_check=True, rows=ROWS, unique_rows=ROWS, port_pairs=59904,
        folds=[dict(fold=k, source_pin_overlap=int(np.intersect1d(
            data["clusters"][folds == k], data["clusters"][folds != k]).size))
            for k in range(3)], disk_free_start=shutil.disk_usage(".").free))
    assert all(r["source_pin_overlap"] == 0 for r in read(ROOT / "prepare.json")["folds"])
    print("EXP623_PREPARED", flush=True)


def load():
    frozen = read(ROOT / "prepare.json")
    for name, key in (("data.npz", "data"), ("paths.u8", "paths"), ("original-values.npy", "original_values")):
        check(BUILD / name, frozen[key])
    with np.load(BUILD / "data.npz") as packed:
        data = {k: packed[k] for k in packed.files}
    return data, np.memmap(BUILD / "paths.u8", dtype="u1", mode="r", shape=(4, ROWS, 8))


def train():
    self_check()
    data, paths = load()
    values = np.load(BUILD / "original-values.npy")
    records, forests = [], []
    started = time.process_time()
    for fold in range(4):
        for route in range(16):
            model = 16 * fold + route
            learn = data["routes"] == route
            if fold:
                learn &= data["folds"] != fold - 1
            indices = np.flatnonzero(learn)
            leaf = paths[fold, indices]
            contributions = values[model][np.arange(8)[None, :], leaf].copy()
            base, mandatory, truth = [data[k][indices] for k in ("base", "mandatory", "truth")]
            initial = loss(raw_sum(contributions), base, mandatory, truth)
            for sweep in range(2):
                for tree in range(8):
                    for tip in range(16):
                        members = np.flatnonzero(leaf[:, tree] == tip)
                        origin = values[model, tree, tip]
                        if len(members) < 64:
                            continue
                        work = contributions[members].copy()
                        v, a, b = update(work, tree, origin, base[members], mandatory[members], truth[members])
                        values[model, tree, tip] = v
                        contributions[members, tree] = v
                        records.append(dict(fold=fold, route=route, sweep=sweep, tree=tree, leaf=tip,
                            support=len(members), before=float(origin), after=float(v),
                            loss_before=a, loss_after=b))
            final = loss(raw_sum(contributions), base, mandatory, truth)
            assert final <= initial + 1e-8
            forests.append(dict(fold=fold, route=route, train_rows=len(indices),
                loss_before=initial, loss_after=final))
            print("EXP623_CALIBRATED", fold, route, len(indices), initial - final, flush=True)
            assert time.process_time() - started < 300, "offline prototype CPU budget"
    np.save(BUILD / "values.npy", values)
    raw_final, raw_oof = np.empty((2, ROWS), dtype="<f4")
    for fold in range(4):
        indices = np.arange(ROWS) if fold == 0 else np.flatnonzero(data["folds"] == fold - 1)
        model = 16 * fold + data["routes"][indices].astype("i4")
        contributions = values[model[:, None], np.arange(8)[None, :], paths[fold, indices]]
        raw = raw_sum(contributions)
        if fold == 0:
            raw_final[:] = raw
        else:
            raw_oof[indices] = raw
    raw_final.tofile(BUILD / "C-final.f32")
    raw_oof.tofile(BUILD / "C-oof.f32")
    write(ROOT / "training.json", dict(records=records, forests=forests, offsets=OFFSETS.tolist(),
        sweeps=2, support_min=64, values=identity(BUILD / "values.npy"),
        cpu_s=time.process_time() - started, train_monotone=True, selection_scores_seen=False,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    frozen = read(ROOT / "prepare.json")
    header = Path(frozen["model_header"]["path"]).read_text()
    position = 0

    def refreshed(match):
        nonlocal position
        v = values[position].reshape(-1)
        position += 1
        return "{{" + match[1] + "},{" + match[2] + "},{" + ",".join(float(x).hex() + "f" for x in v) + "}},"

    header = re.sub(r"^\{\{([^\n]+?)\},\{([^\n]+?)\},\{([^\n]+?)\}\},$", refreshed, header, flags=re.M)
    assert position == 64
    (BUILD / "exp579-models.h").write_text(header)
    write(ROOT / "model.json", dict(header=identity(BUILD / "exp579-models.h"),
        original=frozen["model_header"], thresholds_unchanged=True, features_unchanged=True,
        raw_final=identity(BUILD / "C-final.f32"), raw_oof=identity(BUILD / "C-oof.f32")))
    print("EXP623_TRAINED", flush=True)


def audit():
    freeze = read("../exp622/validation/results/exp622/build-freeze.json")
    check(Path("../exp622") / freeze["native"]["path"], freeze["native"])
    shutil.copyfile(Path("../exp622") / freeze["native"]["path"], BUILD / "native622.h")
    source = BUILD / "check.cpp"
    source.write_text("#include <initializer_list>\n" + old.CHECKER)
    speed.measured(["g++", "-std=c++17", "-O3", "-fno-fast-math", "-ffp-contract=off",
        "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror", "-DEXP579_AUDIT",
        "-I", str(BUILD), "-static", str(source), "-o", str(BUILD / "check")], "compile-check")
    assert not (ROOT / "compile-check.stderr").read_bytes()
    prepared = read(ROOT / "prepare.json")
    output = BUILD / "leaf-raw.bin"
    run = speed.measured([str(BUILD / "check"), prepared["trace_path"],
        "../exp579/build/exp579/queries.bin", "../exp579/build/exp579/folds.u8", str(output)], "check")
    actual = np.memmap(output, dtype=[("leaf", "<u4"), ("raw", "<f4")], mode="r", shape=(ROWS, 2))
    for column, name in enumerate(("final", "oof")):
        raw = np.fromfile(BUILD / f"C-{name}.f32", "<f4")
        assert np.array_equal(actual["raw"][:, column].copy().view("u4"), raw.view("u4"))
    write(ROOT / "audit.json", dict(run=run, output=identity(output),
        counters=read(ROOT / "check.stdout"), original_tree_order=True,
        python_cpp_final_bitwise=True, python_cpp_oof_bitwise=True,
        source=identity(source), model=identity(ROOT / "model.json")))
    print("EXP623_AUDIT_PASSED", flush=True)


def evaluate():
    assert read(ROOT / "audit.json")["python_cpp_oof_bitwise"]
    data, _ = load()
    baseline = decode(np.fromfile(BUILD / "original-oof.f32", "<f4"), data["base"], data["mandatory"])
    candidate = decode(np.fromfile(BUILD / "C-oof.f32", "<f4"), data["base"], data["mandatory"])
    partitions = {k: data[k] for k in ("source_family", "distance", "near_axis", "forced", "target_mismatch")}
    result = transition(candidate, baseline, data["truth"], partitions)
    delta = points(candidate, data["truth"]) - points(baseline, data["truth"])
    family = data["source_family"]
    counts, sums = np.bincount(family, minlength=26), np.bincount(family, weights=delta, minlength=26)
    sampled = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    interval = np.quantile(sums[sampled].sum(axis=1) / counts[sampled].sum(axis=1), [.025, .975])
    passed = bool(result["delta_accuracy_pp"] >= .01 and interval[0] > 0 and all(
        v["delta_accuracy_pp"] >= -.03 for key, group in result["groups"].items()
        if key in ("distance", "near_axis") for v in group.values()))
    final = decode(np.fromfile(BUILD / "C-final.f32", "<f4"), data["base"], data["mandatory"])
    old_final = decode(np.fromfile(BUILD / "original-final.f32", "<f4"), data["base"], data["mandatory"])
    training_diagnostic = transition(final, old_final, data["truth"], partitions)
    write(ROOT / "evaluation.json", dict(comparison=result, ci95_delta_accuracy_pp=interval.tolist(),
        quality_gate=passed, training_diagnostic=training_diagnostic, rows=ROWS, source_pin_oof=True,
        current_background="frozen full Q4", final_goal_verified=False,
        independent_new_requests_verified=False, complete_program_cpu_verified=False))
    print("EXP623_RESULT", result["delta_accuracy_pp"], interval.tolist(), passed, flush=True)


def build():
    assert read(ROOT / "evaluation.json")["quality_gate"]
    frozen = read("../exp622/validation/results/exp622/build-freeze.json")
    check("../exp622/build/exp622/T", frozen["binaries"]["T"])
    text = Path("../exp622/build/exp622/T-worker.cpp").read_text()
    (BUILD / "C-worker.cpp").write_text(text)
    for name in ("entry.cpp", "exp608_geometry.h", "exp596_csv_batch.h", "exp601_port_parser.h"):
        shutil.copyfile(Path("../exp622/build/exp622") / name, BUILD / name)
    command = read("../exp622/validation/results/exp622/compile-T.run.json")["command"]
    replacements = {"build/exp622": str(BUILD), "build/exp622/T-worker.cpp": str(BUILD / "C-worker.cpp"),
        "build/exp622/T.o": str(BUILD / "C.o")}
    speed.measured([replacements.get(a, a) for a in command], "compile-C")
    assert not (ROOT / "compile-C.stderr").read_bytes()
    link = read("../exp622/validation/results/exp622/link-T.run.json")["command"]
    replacements.update({"build/exp622/entry.cpp": str(BUILD / "entry.cpp"),
        "build/exp622/T": str(BUILD / "C")})
    speed.measured([replacements.get(a, a) for a in link], "link-C")
    assert not (ROOT / "link-C.stderr").read_bytes()
    assert (BUILD / "C").stat().st_size < 100000000
    static = subprocess.run(["ldd", str(BUILD / "C")], capture_output=True, text=True)
    assert "not a dynamic executable" in static.stdout + static.stderr
    source = BUILD / "C-worker.cpp"
    check(BUILD / "exp579-models.h", read(ROOT / "model.json")["header"])
    write(ROOT / "build-freeze.json", dict(binaries={
        "A": identity("../exp622/build/exp622/T"), "C": identity(BUILD / "C")},
        source=identity(source), model=identity(ROOT / "model.json"), reference=frozen,
        all_values_frozen_before_new_requests=True, driver=identity(__file__)))
    request = Path("../exp501/build/exp501/u-role/requests.csv")
    output = BUILD / "development-C.csv"
    data, _ = load()
    expected = decode(np.fromfile(BUILD / "C-final.f32", "<f4"), data["base"], data["mandatory"])
    expected.astype("<i4").tofile(BUILD / "expected.i32")
    run = speed.measured([str(BUILD / "C"), "-in", str(request), "-out", str(output)], "development-C")
    actual, truth, evidence, partitions = old.prior.complete.check_output(
        request, output, Path("../exp501/build/exp501/exact.csv"), BUILD / "expected.i32")
    assert np.array_equal(actual, expected) and np.array_equal(truth, data["truth"])
    assert run["threads"] == 1 and run["rss_bytes"] <= 2000000000
    assert read(run["stderr"]) == dict(rows=ROWS, unreachable=0, query_allocations=0)
    write(ROOT / "complete-check.json", dict(run=run, evidence=evidence,
        expected=identity(BUILD / "expected.i32"), model=identity(ROOT / "model.json"),
        final_prediction_exact=True, performance_comparison_pending=True))
    print("EXP623_COMPLETE_BUILT", flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp623")
    assert len(sys.argv) == 2 and sys.argv[1] in ("prepare", "train", "audit", "evaluate", "build")
    started = time.process_time()
    {"prepare": prepare, "train": train, "audit": audit, "evaluate": evaluate, "build": build}[sys.argv[1]]()
    write(ROOT / (sys.argv[1] + "-resources.json"), dict(cpu_s=time.process_time() - started,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        threads=len(list(Path("/proc/self/task").iterdir())), driver=identity(__file__)))
