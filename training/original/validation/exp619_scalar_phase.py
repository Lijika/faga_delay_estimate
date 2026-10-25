#!/usr/bin/env python3
"""Fit a zero-preserving 16-level scalar quantizer of the frozen P table on r9."""
import argparse
import itertools
import json
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp615/validation").resolve()))
import exp615_phase_codes as prior

ROOT, BUILD = Path("validation/results/exp619"), Path("build/exp619")
PLAN = Path("experiment/实验619-有限周期残量的四位标量量化.md")
SOURCE = Path("../exp615/build/exp615/P.p5")
PAIRS, COUNT, SEED = 59904, 59904*480, 20261023619
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked


def optimal(values, counts, k):
    assert len(values) == len(counts) and values == sorted(set(values)) and 0 in values
    assert all(h > 0 for h in counts) and 0 < k < len(values)
    n, z = len(values), values.index(0)
    intervals = {}
    for i in range(n):
        for j in range(i+1, n+1):
            centers = [0] if i <= z < j else values[i:j]
            options = [(sum(counts[t]*abs(values[t]-c) for t in range(i, j)), c)
                       for c in centers]
            intervals[i, j] = min(options, key=lambda t: (t[0], abs(t[1]), t[1]))
    table = [[None]*(n+1) for _ in range(k+1)]
    cuts = {}
    table[0][0] = 0
    for level in range(1, k+1):
        for j in range(level, n+1):
            choices = [(table[level-1][i]+intervals[i, j][0], i)
                       for i in range(level-1, j) if table[level-1][i] is not None]
            table[level][j], cuts[level, j] = min(choices)
    centers, j = [], n
    for level in range(k, 0, -1):
        i = cuts[level, j]
        centers.append(intervals[i, j][1])
        j = i
    centers.sort(key=lambda c: (abs(c), c))
    assert j == 0 and centers[0] == 0 and len(set(centers)) == k
    loss = sum(h*min(abs(v-c) for c in centers) for v, h in zip(values, counts))
    assert loss == table[k][n]
    return centers, loss


def self_check():
    for values, counts, k in (
            (list(range(-8, 9, 2)), [1, 3, 2, 4, 7, 4, 2, 3, 1], 3),
            ([-4, -2, 0, 2], [1, 1, 1, 1], 2)):
        centers, actual = optimal(values, counts, k)
        exhaustive = min(sum(h*min(abs(v-c) for c in cs) for v, h in zip(values, counts))
                         for cs in itertools.combinations(values, k) if 0 in cs)
        assert actual == exhaustive and centers[0] == 0


def unpack(path):
    raw = Path(path).read_bytes()
    assert len(raw) == 14377024 and raw[:8] == b"EX619P01"
    assert struct.unpack("<3I", raw[8:20]) == (PAIRS, 480, 16)
    levels = np.frombuffer(raw, "i1", count=16, offset=32)
    assert levels[0] == 0 and len(np.unique(levels)) == 16
    packed = np.frombuffer(raw, "u1", offset=64)
    codes = np.empty(COUNT, "u1")
    codes[::2], codes[1::2] = packed & 15, packed >> 4
    return levels[codes].reshape(PAIRS, 480)


def prepare():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/"protocol-original.md")
    (ROOT/"installed-numpy-help.txt").write_text(np.packbits.__doc__+"\n"+np.bincount.__doc__)
    self_check()
    source = checked(SOURCE, dict(bytes=17971217,
        sha256="250f5175785d61479064ba03ee73fd7fdd5a64a93a32c6a674f61323d758f62a"))
    histogram_path = Path("../exp616/validation/results/exp616/diagnostic.json")
    histogram = read(histogram_path)
    assert histogram["exact_reconstruction"] and histogram["compared_values"] == COUNT
    assert all(histogram["source"][key] == source[key] for key in ("bytes", "sha256"))
    domain, counts = list(range(-32, 31, 2)), histogram["code_counts"]
    assert len(counts) == 32 and sum(counts) == COUNT
    centers, loss = optimal(domain, counts, 16)
    zero = sum(h*abs(v) for v, h in zip(domain, counts))
    passed = loss <= .15*zero and loss/COUNT <= .75 and 14377024 < 15000000
    report = dict(centers_ps=centers, counts=counts, loss_ps=loss, zero_loss_ps=zero,
                  ratio=loss/zero, mean_distortion_ps=loss/COUNT, gate=bool(passed),
                  synthetic_exhaustive_equal=True, direct_loss_equal_dp=True)
    write(ROOT/"prototype.json", report)
    paths = [Path(__file__), Path("tests/exp619_phase_codes.cpp"),
             Path("tests/exp619_phase_lookup.h"), PLAN, ROOT/"protocol-original.md",
             Path(prior.__file__), SOURCE, histogram_path]
    write(ROOT/"freeze.json", dict(files=[identity(p) for p in paths], source=source,
          baseline_head="841fc74f", seed=SEED, disk_free_start=shutil.disk_usage(".").free))
    if not passed:
        print("EXP619_PROTOTYPE_FAILED", report, flush=True)
        return
    values = prior.unpack(SOURCE, COUNT)
    old_codes = ((values.astype("i2")+32)//2).astype("u1")
    assert np.array_equal(np.bincount(old_codes.reshape(-1), minlength=32), counts)
    levels = np.array(centers, "i1")
    mapping = np.abs(np.array(domain, "i2")[:, None]-levels).argmin(axis=1).astype("u1")
    codes = mapping[old_codes.reshape(-1)]
    header = b"EX619P01"+struct.pack("<3I", PAIRS, 480, 16)+bytes(12)+levels.tobytes()+bytes(16)
    path = BUILD/"Q4.p4"
    with path.open("xb") as stream:
        stream.write(header)
        stream.write((codes[::2] | (codes[1::2] << 4)).tobytes())
    rebuilt = unpack(path)
    assert np.array_equal(rebuilt, levels[codes].reshape(PAIRS, 480))
    assert int(np.abs(values.astype("i2")-rebuilt).sum()) == loss
    report.update(asset=identity(path), full_pack_roundtrip=True, compared_values=COUNT)
    write(ROOT/"training.json", report)
    print("EXP619_PREPARED", report, flush=True)


def evaluate():
    for item in read(ROOT/"freeze.json")["files"]:
        checked(item["path"], item)
    trained = read(ROOT/"training.json")
    assert trained["gate"] and trained["full_pack_roundtrip"]
    checked(BUILD/"Q4.p4", trained["asset"])
    (ROOT/"compiler-help.txt").write_text(subprocess.check_output(["g++", "--help"], text=True))
    command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64",
               "-mtune=generic", "-Wall", "-Wextra", "-Werror",
               "tests/exp619_phase_codes.cpp", "-o", str(BUILD/"decode")]
    run = subprocess.run(command, capture_output=True, text=True)
    (ROOT/"compile.stdout").write_text(run.stdout)
    (ROOT/"compile.stderr").write_text(run.stderr)
    assert run.returncode == 0 and not run.stderr
    keys_path = Path("../exp615/build/exp615/keys.bin")
    original_freeze = read("../exp615/validation/results/exp615/freeze.json")
    checked(keys_path, original_freeze["keys"])
    run = subprocess.run([str(BUILD/"decode"), str(BUILD/"Q4.p4"), str(keys_path),
        str(BUILD/"native-full.i8"), str(BUILD/"native-query.i32")], capture_output=True, text=True)
    (ROOT/"decode.stdout").write_text(run.stdout)
    (ROOT/"decode.stderr").write_text(run.stderr)
    assert run.returncode == 0 and not run.stderr
    assert json.loads(run.stdout) == dict(full_values=COUNT, query_rows=1000000)
    table = unpack(BUILD/"Q4.p4")
    assert np.array_equal(table, np.fromfile(BUILD/"native-full.i8", "i1").reshape(PAIRS, 480))
    keys = np.fromfile(keys_path, "<u4", offset=12).reshape(1000000, 4)
    pair, context, qx, qy = keys.T
    far = qx+qy > 3
    correction = table[pair, context].astype("i4")
    correction[~far] = 0
    assert np.array_equal(correction, np.fromfile(BUILD/"native-query.i32", "<i4"))
    data = prior.prior.load()
    checked("../exp576/build/exp576/R8.f32", original_freeze["data"]["original_raw"])
    raw = np.fromfile("../exp576/build/exp576/R8.f32", "<f4")
    sys.path.insert(0, str(Path("../exp592/validation").resolve()))
    from exp592_xgb_audit import decode, points, transition
    reference = decode(raw, data["D64"], data["mandatory"])
    original = prior.unpack(SOURCE, COUNT)[pair, context].astype("i4")
    original[~far] = 0
    p_prediction = decode(raw, data["D64"]+original, data["mandatory"])
    prediction = decode(raw, data["D64"]+correction, data["mandatory"])
    assert np.array_equal(prediction[~far], reference[~far])
    with np.load("../exp585/build/exp585/evaluation.npz") as packed:
        partitions = {k[10:]: packed[k] for k in packed.files if k.startswith("partition_")}
    x = data["features"]
    dx, dy = x[:, 8]+x[:, 6], x[:, 9]+x[:, 7]
    partitions.update(source_family=x[:, 0].astype("i4"), direction=context//120,
        near_axis=((np.abs(dx) < 20) | (np.abs(dy) < 24)).astype("i4"),
        code_training_grid=(np.isin(qx, prior.QX) & np.isin(qy, prior.QY)).astype("i4"))
    result = transition(prediction, reference, data["truth"], partitions)
    family, inverse = np.unique(x[:, 0].astype("i4"), return_inverse=True)
    assert len(family) == 26
    sampled = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    counts = np.bincount(inverse)
    delta = points(prediction, data["truth"])-points(reference, data["truth"])
    sums = np.bincount(inverse, weights=delta)
    interval = np.quantile(sums[sampled].sum(axis=1)/counts[sampled].sum(axis=1), [.025, .975])
    p_delta = float((points(prediction, data["truth"])-points(p_prediction, data["truth"])).mean())
    passed = result["delta_accuracy_pp"] >= .10 and p_delta >= -.02 and interval[0] > 0 and all(
        g["delta_accuracy_pp"] >= -.03 for key, groups in result["groups"].items()
        if key in ("distance", "near_axis") for g in groups.values())
    prediction.astype("<i4").tofile(BUILD/"Q4-prediction.i32")
    result.update(ci95_delta_accuracy_pp=interval.tolist(), delta_to_P_pp=p_delta,
        quality_gate=bool(passed), full_native_decode_equal=True, near_bitwise_unchanged=True,
        prediction=identity(BUILD/"Q4-prediction.i32"), complete_program_verified=False)
    write(ROOT/"evaluation.json", dict(selected="Q4" if passed else None, comparison=result))
    print("EXP619_EVALUATED", result["candidate"]["accuracy_pp"],
          result["delta_accuracy_pp"], p_delta, bool(passed), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "evaluate"))
    args = parser.parse_args()
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp619")
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    started, cpu = time.monotonic(), time.process_time()
    {"prepare": prepare, "evaluate": evaluate}[args.stage]()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    write(ROOT/(args.stage+"-resources.json"), dict(cpu_s=time.process_time()-cpu+
          children.ru_utime+children.ru_stime, wall_s=time.monotonic()-started,
          own_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
          children_rss_bytes=children.ru_maxrss*1024, disk_free_end=shutil.disk_usage(".").free))


if __name__ == "__main__":
    main()
