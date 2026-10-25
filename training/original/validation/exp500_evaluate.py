#!/usr/bin/env python3
"""Stream all full-port, full-residue predictions and paired scores on r9."""
import argparse
import ctypes
import hashlib
import json
import lzma
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import time

import numpy as np

import exp500_split_residues as training
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = training.ROOT, training.BUILD
LEFT, RIGHT, RANK = training.LEFT, training.RIGHT, training.RANK
STAGES = ("initial", "huber", "tables", "verify")
SOURCE = Path("tests/exp500_stream_decode.cpp")
LIBRARY = BUILD / "stream_decode.so"
MODEL = BUILD / "model.bin.xz"
METRICS = ("values", "changed", "score_sum", "abs_error_sum",
           "max_abs_error", "min_error", "max_error")


def read(path):
    return json.loads(Path(path).read_text())


def metadata(mapping):
    sc = np.array(mapping["source_coordinates"], dtype=np.int32)
    tc = np.array(mapping["target_coordinates"], dtype=np.int32)
    rows = np.full((18, LEFT, 8), -1, dtype=np.int32)
    for s, (sf, sl) in enumerate(sc):
        for q in range(18):
            target = np.flatnonzero(tc[:, 0] // 2 == q)
            for dx in range(2):
                for rx in range(10):
                    key = rx * 6656 + training.left_key(sc[s], tc[target], dx)
                    assert len(set(key)) == 16 and np.all(rows[q, key, 0] == -1)
                    rows[q, key] = np.column_stack((
                        np.full(16, s), target, np.full(16, sf), np.full(16, sl),
                        tc[target], np.full(16, dx), np.full(16, rx)))
    assert np.all(rows >= 0)
    # Independently invert each mixed-radix row to its port coordinates.
    value = np.arange(LEFT)
    dx, value = value % 2, value // 2
    low, value = value % 2, value // 2
    p2, value = value % 4, value // 4
    p1, value = value % 4, value // 4
    p0, value = value % 4, value // 4
    sf, rx = value % 26, value // 26
    sl = p0 % 2 + 2 * (p1 % 2) + 4 * (p2 % 2)
    tl = p0 // 2 + 2 * (p1 // 2) + 4 * (p2 // 2)
    for q in range(18):
        expected = np.column_stack((sf, sl, 2 * q + low, tl, dx, rx))
        assert np.array_equal(rows[q, :, 2:], expected)
    return rows


def prepare():
    mapping = read(ROOT / "mapping.json")
    rows = metadata(mapping)
    np.save(BUILD / "row-metadata.npy", rows)
    files = [SOURCE, Path(__file__).resolve().relative_to(Path.cwd()),
             Path(training.__file__).resolve().relative_to(Path.cwd()),
             Path("validation/exp208_nominal_parent_tree.py"),
             ROOT / "mapping.json", ROOT / "protocol-original.md",
             training.PREPARATION / "evaluation-protocol.md",
             training.PREPARATION / "fields.json", training.PREPARATION / "label-report.json",
             BUILD / "row-metadata.npy"]
    for directory, shard in ((ROOT, [9, 18]), (ROOT / "offline-l7", [0, 9])):
        freeze_path, train_path = directory / "freeze.json", directory / "training.json"
        frozen, trained = read(freeze_path), read(train_path)
        actual, expected = identity(freeze_path), trained["freeze"]
        assert (actual["bytes"], actual["sha256"]) == (expected["bytes"], expected["sha256"])
        assert frozen["shard"] == trained["shard"] == shard and trained["all_training_checks"]
        assert [r["group"] for r in trained["groups"]] == list(range(*shard))
        for row in trained["groups"]:
            assert read(ROOT / f"group-{row['group']:02d}.json") == row
        for row in frozen["files"]:
            assert identity(row["path"]) == row
        files.extend((freeze_path, train_path, directory / "materialization.json"))
    for q in range(18):
        path = ROOT / f"group-{q:02d}.json"
        record = read(path)
        assert record["group"] == q and record["all_training_checks"]
        assert record["shape"] == [LEFT, RIGHT] and record["rank"] == RANK
        assert record["steps"] == 12 and record["delta"] == training.DELTA
        assert [row["step"] for row in record["history"]] == list(range(13))
        for a, b in zip(record["history"], record["history"][1:]):
            assert b["huber"] <= a["huber"] + 1e-9 * max(1., a["huber"])
            assert b["projection_distance"] <= b["old_projection_distance"] + \
                   1e-9 * max(1., b["old_projection_distance"])
            assert b["orthogonal_error"] <= 1e-10 and b["preserved_error"] <= 1e-10
        for row in record["initial"] + record["final"]:
            assert identity(row["path"]) == row
            files.append(Path(row["path"]))
        files.append(path)
    compiler = subprocess.check_output(["g++", "--version"], text=True)
    options = "\n".join(subprocess.check_output(["g++", "--help=" + group], text=True)
                        for group in ("common", "optimizers", "c++"))
    assert "-fopenmp" in options and "-ffp-contract" in options
    (ROOT / "decoder-compiler.txt").write_text(compiler)
    (ROOT / "decoder-options.txt").write_text(options)
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror",
               "-ffp-contract=off", "-fopenmp", "-fPIC", "-shared", str(SOURCE), "-o", str(LIBRARY)]
    result = subprocess.run(command, capture_output=True, text=True)
    (ROOT / "decoder-build.stdout").write_text(result.stdout)
    (ROOT / "decoder-build.stderr").write_text(result.stderr)
    assert result.returncode == 0 and not result.stderr, result.stderr
    files.append(LIBRARY)
    write(ROOT / "evaluation-freeze.json", dict(
        files=[identity(p) for p in files], compiler_command=command,
        groups=18, rank=128, source_ports=208, target_ports=288, contexts=480,
        values_per_stage=18 * LEFT * RIGHT, scored_values_per_stage=208 * 288 * 239 * 1099,
        stages=STAGES, scalar_checks_per_stage=208 * 288 * 480,
        output_order="group, natural left row, (dy, ry, geometry) column",
        row_metadata_bijective=True, disk_free_bytes=shutil.disk_usage(".").free))
    print("EXP500_EVALUATION_PREPARED", flush=True)


def check_freeze():
    frozen = read(ROOT / "evaluation-freeze.json")
    for row in frozen["files"]:
        assert identity(row["path"]) == row
    return frozen


def quantize(value):
    maximum = np.abs(value).max(axis=0)
    exponent = np.zeros(RANK, dtype="<i4")
    nonzero = maximum > 0
    exponent[nonzero] = np.ceil(np.log2(maximum[nonzero] / 32767)).astype("<i4")
    scaled = np.ldexp(value, -exponent)
    rounded = np.copysign(np.floor(np.abs(scaled) + .5), scaled)
    assert np.isfinite(rounded).all() and np.abs(rounded).max() <= 32767
    integer = rounded.astype("<i2")
    restored = np.ldexp(integer.astype(np.float64), exponent)
    assert np.array_equal(restored, restored.astype(np.float32))
    return exponent, integer, restored.astype(np.float32)


def models():
    check_freeze()
    digest = hashlib.sha256()
    raw_bytes = 0
    with MODEL.open("xb") as asset, lzma.LZMAFile(asset, "wb", preset=6) as stream:
        def emit(value):
            nonlocal raw_bytes
            digest.update(value)
            raw_bytes += len(value)
            stream.write(value)
        emit(b"EX500Q01" + struct.pack("<4I", 18, LEFT, RIGHT, RANK))
        for q in range(18):
            emit(struct.pack("<I", q))
            for side in ("left", "right"):
                value = np.load(BUILD / f"q{q:02d}/huber-{side}.npy")
                exponent, integer, _ = quantize(value)
                emit(exponent.tobytes())
                emit(integer.tobytes())
    restored_digest = hashlib.sha256()
    restored_bytes = 0
    with lzma.open(MODEL) as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            restored_digest.update(block)
            restored_bytes += len(block)
    assert restored_bytes == raw_bytes and restored_digest.digest() == digest.digest()
    write(ROOT / "model.json", dict(
        asset=identity(MODEL), raw_bytes=raw_bytes, raw_sha256=digest.hexdigest(),
        full_lossless_roundtrip=True, float32_body_bytes=4 * 18 * (LEFT + RIGHT) * RANK,
        int16_body_bytes=2 * 18 * (LEFT + RIGHT) * RANK,
        compression="XZ preset6"))
    print("EXP500_MODEL_COMPLETE", MODEL.stat().st_size, flush=True)


def read_group(stream, q):
    assert stream.read(4) == struct.pack("<I", q)
    result = []
    for count in (LEFT, RIGHT):
        raw = stream.read(4 * RANK)
        assert len(raw) == 4 * RANK
        exponent = np.frombuffer(raw, "<i4")
        raw = stream.read(2 * count * RANK)
        assert len(raw) == 2 * count * RANK
        integer = np.frombuffer(raw, "<i2").reshape(count, RANK)
        result.append(np.ldexp(integer.astype(np.float32), exponent))
    return result


def statistics(mapping, array):
    keys = ["all", "near_axis", "interior"]
    keys += [f"direction/{d}" for d in range(4)]
    keys += [f"residue/{p // 12}/{p % 12}" for p in range(120)]
    keys += ["source/" + s for s in mapping["sources"]]
    keys += ["target/" + t for t in mapping["targets"]]
    keys += ["source_family/" + s for s in mapping["source_families"]]
    keys += ["target_family/" + t for t in mapping["target_families"]]
    keys += ["a8/all", "a8/near_axis", "a8/interior"]
    assert len(keys) == 688
    result = {}
    for key, values in zip(keys, array):
        row = dict(zip(METRICS, map(float, values)))
        for name in METRICS:
            if name != "score_sum":
                assert row[name] == int(row[name])
                row[name] = int(row[name])
        assert row["values"] > 0
        row["accuracy_pp"] = 100 * row["score_sum"] / row["values"]
        row["mae_ps"] = row["abs_error_sum"] / row["values"]
        result[key] = row
    return result


def evaluate():
    frozen = check_freeze()
    assert identity(MODEL) == read(ROOT / "model.json")["asset"]
    mapping = read(ROOT / "mapping.json")
    rows = np.load(BUILD / "row-metadata.npy")
    assert np.array_equal(rows, metadata(mapping))
    ids = [np.array(mapping[key], dtype="<i4") for key in ("source_ids", "target_ids")]
    materialization = ROOT / "evaluation-materialization"
    materialization.mkdir()
    shutil.copyfile(ROOT / "mapping.json", materialization / "mapping.json")
    training.ROOT = materialization
    data = training.materialize(0, 18)
    summaries = {s: np.zeros((688, 7), dtype=np.float64) for s in STAGES}
    paired = {s: np.zeros(4, dtype=np.float64) for s in STAGES}
    hashes = {s: hashlib.sha256() for s in STAGES}
    library = ctypes.CDLL(str(LIBRARY.resolve()))
    call = library.exp500_block
    call.argtypes = [ctypes.c_int] * 4 + [ctypes.c_void_p] * 10
    call.restype = ctypes.c_int
    decode_cpu = {s: 0. for s in STAGES}
    decode_wall = {s: 0. for s in STAGES}
    independent_checks = 0
    started, cpu = time.monotonic(), time.process_time()
    with lzma.open(MODEL) as stream:
        assert stream.read(24) == b"EX500Q01" + struct.pack("<4I", 18, LEFT, RIGHT, RANK)
        for q in range(18):
            factor = {}
            for stage in ("initial", "huber"):
                factor[stage] = [np.ascontiguousarray(np.load(BUILD / f"q{q:02d}/{stage}-{side}.npy"))
                                 for side in ("left", "right")]
            factor["tables"] = [quantize(value)[2] for value in factor["huber"]]
            factor["verify"] = read_group(stream, q)
            for a, b in zip(factor["tables"], factor["verify"]):
                assert np.array_equal(a, b)
            for stage in STAGES:
                left, right = factor[stage]
                assert left.shape == (LEFT, RANK) and right.shape == (RIGHT, RANK)
                assert np.isfinite(left).all() and np.isfinite(right).all()
                factor[stage] = [np.ascontiguousarray(left), np.ascontiguousarray(right.T)]
            for begin in range(0, LEFT, 128):
                count = min(128, LEFT - begin)
                outputs = {}
                for stage in STAGES:
                    left, right = factor[stage]
                    out = np.empty((count, RIGHT), dtype="<i4")
                    previous = outputs.get("tables" if stage == "verify" else "initial")
                    arguments = [rows[q], *ids, data[q, begin:begin + count],
                                 left, right, previous, out, summaries[stage], paired[stage]]
                    stage_start, stage_cpu = time.monotonic(), time.process_time()
                    code = call(q, begin, count, left.dtype.itemsize,
                                *[None if a is None else a.ctypes.data for a in arguments])
                    assert code == 0, (q, begin, stage, code)
                    decode_cpu[stage] += time.process_time() - stage_cpu
                    decode_wall[stage] += time.monotonic() - stage_start
                    hashes[stage].update(memoryview(out).cast("B"))
                    outputs[stage] = out
                    # A second implementation checks every endpoint pair and direction at rx=0.
                    if begin < 6656:
                        for offset in range(count):
                            s, t, sf, sl, tf, tl, dx, rx = map(int, rows[q, begin + offset])
                            if rx != 0:
                                continue
                            for dy in range(2):
                                ry = (s + t + dx + dy) % 12
                                g = (31 * s + t + 17 * (2 * dx + dy) + 7 * ry) % 552
                                column = (12 * dy + ry) * 552 + g
                                total = sum(float(left[begin + offset, k]) * float(right[k, column])
                                            for k in range(RANK))
                                trend = 125 * (g // 46) + (125 if dy else 127) * (g % 46)
                                value = total * training.DENOM[g] + trend
                                expected = max(0, int(np.copysign(np.floor(abs(value) + .5), value)))
                                if ry == 0 and g == 0 and ids[0][s] == ids[1][t]:
                                    expected = 0
                                assert out[offset, column] == expected
                                independent_checks += 1
                    if stage == "verify":
                        assert np.array_equal(outputs["tables"], out)
            print("EXP500_GROUP_EVALUATED", q, flush=True)
        assert not stream.read(1)
    reports = {}
    for stage in STAGES:
        stats = statistics(mapping, summaries[stage])
        assert stats["all"]["values"] == frozen["scored_values_per_stage"]
        assert paired[stage][3] == frozen["scalar_checks_per_stage"]
        assert stats["near_axis"]["values"] == 3130642944
        assert stats["a8/all"]["values"] == 257647104
        assert stats["near_axis"]["values"] + stats["interior"]["values"] == stats["all"]["values"]
        for prefix in ("source/", "target/", "direction/", "residue/", "source_family/", "target_family/"):
            assert sum(v["values"] for k, v in stats.items() if k.startswith(prefix)) == stats["all"]["values"]
        reports[stage] = dict(
            stats=stats, decoded_values=frozen["values_per_stage"],
            output_bytes=4 * frozen["values_per_stage"], output_sha256=hashes[stage].hexdigest(),
            scalar_checks=int(paired[stage][3]), paired_to="tables" if stage == "verify" else "initial",
            changed_rectangle=int(paired[stage][0]), improved_valid=int(paired[stage][1]),
            worsened_valid=int(paired[stage][2]), decode_cpu_s=decode_cpu[stage],
            decode_wall_s=decode_wall[stage], scope="Offline full-domain decode and score; no production CPU.")
        write(ROOT / f"{stage}-score.json", reports[stage])
    assert hashes["tables"].digest() == hashes["verify"].digest()
    assert np.array_equal(summaries["tables"], summaries["verify"])
    assert independent_checks == 4 * 208 * 288 * 4
    write(ROOT / "evaluation.json", dict(
        stages=STAGES, all_full_domain_checks=True, python_scalar_checks=independent_checks,
        cpp_scalar_checks_per_stage=frozen["scalar_checks_per_stage"],
        raw_output_sha_verified=True, wall_s=time.monotonic() - started,
        cpu_s=time.process_time() - cpu,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    print("EXP500_COMPLETE_EVALUATION", flush=True)


def check():
    frozen = check_freeze()
    evaluation = read(ROOT / "evaluation.json")
    assert evaluation["all_full_domain_checks"] and evaluation["raw_output_sha_verified"]
    reports = {s: read(ROOT / f"{s}-score.json") for s in STAGES}
    assert reports["tables"]["stats"] == reports["verify"]["stats"]
    assert reports["tables"]["output_sha256"] == reports["verify"]["output_sha256"]
    groups = []
    for family in read(ROOT / "mapping.json")["source_families"]:
        key = "source_family/" + family
        initial, final = [reports[s]["stats"][key] for s in ("initial", "tables")]
        assert initial["values"] == final["values"]
        groups.append([final["score_sum"] - initial["score_sum"], initial["values"]])
    groups = np.array(groups)
    rng = np.random.default_rng(training.SEED)
    sampled = groups[rng.integers(0, 26, size=(2000, 26))].sum(axis=1)
    interval = np.quantile(100 * sampled[:, 0] / sampled[:, 1], [.025, .975]).tolist()
    delta = 100 * groups[:, 0].sum() / groups[:, 1].sum()
    stats = reports["tables"]["stats"]
    quantization_loss = reports["huber"]["stats"]["all"]["accuracy_pp"] - stats["all"]["accuracy_pp"]
    model = read(ROOT / "model.json")
    assert identity(MODEL) == model["asset"] and model["full_lossless_roundtrip"]
    write(ROOT / "report.json", dict(
        evidence_passed=True, values_per_stage=frozen["values_per_stage"],
        scored_values_per_stage=frozen["scored_values_per_stage"],
        nominal_score_pp=stats["all"]["accuracy_pp"], near_axis_score_pp=stats["near_axis"]["accuracy_pp"],
        initial_score_pp=reports["initial"]["stats"]["all"]["accuracy_pp"],
        huber_score_pp=reports["huber"]["stats"]["all"]["accuracy_pp"],
        delta_pp=float(delta), source_family_bootstrap_95=interval,
        mechanism_gate=bool(delta >= .005 and interval[0] > 0),
        quality_gate=bool(stats["all"]["accuracy_pp"] >= 99.97 and stats["near_axis"]["accuracy_pp"] >= 99.9),
        quantization_loss_pp=quantization_loss, quantization_gate=abs(quantization_loss) <= .01,
        static_asset_bytes=model["asset"]["bytes"], float32_table_body_bytes=model["float32_body_bytes"],
        capacity_gate=model["asset"]["bytes"] <= 80_000_000 and model["float32_body_bytes"] <= 1_500_000_000,
        scope="Complete nominal development domain. Actual graph accuracy, full-program CPU, "
              "single-thread resources and deployment remain unverified."))
    print("EXP500_EVIDENCE_PASSED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "models", "evaluate", "check"))
    args = parser.parse_args()
    assert socket.gethostname() == "lhj-R4900-G3"
    globals()[args.stage]()
