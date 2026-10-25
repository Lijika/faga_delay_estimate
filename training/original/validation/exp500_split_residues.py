#!/usr/bin/env python3
"""Train the fixed full-residue rank128 model in two offline query-group shards."""
import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import time

import numpy as np
from scipy.linalg import qr, svd

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp500"), Path("build/exp500")
LABELS = Path("../exp499")
PREPARATION = Path("validation/results/exp500-preparation")
PLAN = Path("experiment/实验500-全端口完整余类的分组受限投影.md")
SHARDS = {"lhj-NF5280M5": (0, 9), "lhj-R4900-G3": (9, 18)}
BASE_LEFT, LEFT, RIGHT, RANK, GEOM = 6656, 66560, 13248, 128, 552
SEED, STEPS, DELTA = 20261019500, 12, 2. ** -12
DENOM = 128 + 125 * (np.arange(GEOM) // 46) + 125 * (np.arange(GEOM) % 46)
DENOM_FULL = np.tile(DENOM, 24)


def read(path):
    return json.loads(Path(path).read_text())


def left_key(source, targets, dx):
    sf, sl = map(int, source)
    tf, tl = targets.T
    p0 = (sl & 1) + 2 * (tl & 1)
    p1 = ((sl >> 1) & 1) + 2 * ((tl >> 1) & 1)
    p2 = ((sl >> 2) & 1) + 2 * ((tl >> 2) & 1)
    return (((((sf * 4 + p0) * 4 + p1) * 4 + p2) * 2 + tf % 2) * 2 + dx)


def prepare():
    assert socket.gethostname() in SHARDS
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    source = read(PREPARATION / "source-freeze.json")
    for row in source["files"]:
        assert identity(row["path"]) == row
    mapping = read(PREPARATION / "mapping.json")
    assert len(mapping["source_ids"]) == 208 and len(mapping["target_ids"]) == 288
    fields = read(PREPARATION / "fields.json")
    assert len(fields) == 208 and [r["number"] for r in fields] == list(range(208))
    previous = read(PREPARATION / "label-report.json")
    assert previous["evidence_passed"] and previous["certified_values"] == 18 * LEFT * RIGHT
    for number, row in enumerate(fields):
        assert row["source"] == mapping["sources"][number]
        actual = identity(LABELS / row["asset"]["path"])
        assert (actual["bytes"], actual["sha256"]) == \
               (row["asset"]["bytes"], row["asset"]["sha256"])
    shutil.copyfile(PREPARATION / "mapping.json", ROOT / "mapping.json")
    frozen_files = [identity(p) for p in (
        Path(__file__).resolve().relative_to(Path.cwd()), PREPARATION / "source-freeze.json",
        PREPARATION / "fields.json", PREPARATION / "label-report.json",
        ROOT / "protocol-original.md", ROOT / "mapping.json")]
    write(ROOT / "freeze.json", dict(
        files=frozen_files, shard=SHARDS[socket.gethostname()],
        source_ports=208, target_ports=288, contexts=480,
        groups=18, group_shape=[LEFT, RIGHT], rank=RANK, steps=STEPS,
        delta=DELTA, seed=SEED, values=18 * LEFT * RIGHT,
        disk_free_bytes=shutil.disk_usage(".").free, hostname=socket.gethostname(),
        new_exact_labels=0))
    print("EXP500_PREPARED", SHARDS[socket.gethostname()], flush=True)


def materialize(begin, end):
    started, cpu = time.monotonic(), time.process_time()
    mapping = read(ROOT / "mapping.json")
    sc, tc = [np.array(mapping[name + "_coordinates"]) for name in ("source", "target")]
    assert sc.shape == (208, 2) and tc.shape == (288, 2)
    data = np.empty((end - begin, LEFT, RIGHT), dtype="<i2")
    seen = np.zeros((end - begin, LEFT, 2), dtype=bool)
    fields = read(PREPARATION / "fields.json")
    for s, row in enumerate(fields):
        path = LABELS / row["asset"]["path"]
        packed = path.read_bytes()
        assert len(packed) == row["asset"]["bytes"]
        assert hashlib.sha256(packed).hexdigest() == row["asset"]["sha256"]
        raw = lzma.decompress(packed)
        assert len(raw) == row["raw_bytes"] and hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
        assert raw[:8] == b"EX499D01"
        assert struct.unpack("<6i", raw[8:32]) == (mapping["source_ids"][s], 288, 4, 120, 12, 46)
        assert np.array_equal(np.frombuffer(raw, "<i4", offset=32, count=288), mapping["target_ids"])
        values = np.frombuffer(raw, "<i2", offset=1184).reshape(4, 10, 12, 288, GEOM)
        for q in range(begin, end):
            targets = np.flatnonzero(tc[:, 0] // 2 == q)
            assert len(targets) == 16
            for dx in range(2):
                rows = (np.arange(10)[:, None] * BASE_LEFT +
                        left_key(sc[s], tc[targets], dx)[None, :]).ravel()
                assert len(np.unique(rows)) == 160 and np.all((0 <= rows) & (rows < LEFT))
                for dy in range(2):
                    assert not seen[q - begin, rows, dy].any()
                    block = values[2 * dx + dy].take(targets, axis=2).transpose(0, 2, 1, 3)
                    data[q - begin, rows, dy * 6624:(dy + 1) * 6624] = block.reshape(160, 6624)
                    assert np.array_equal(data[q - begin, rows, dy * 6624:(dy + 1) * 6624],
                                          block.reshape(160, 6624))
                    seen[q - begin, rows, dy] = True
        print("EXP500_SOURCE_MATERIALIZED", s, flush=True)
    assert seen.all()
    write(ROOT / "materialization.json", dict(
        shard=[begin, end], shape=list(data.shape), scalar_values=int(data.size),
        bijective_rows_and_columns=True, complete_asset_sha_checked=True,
        immediate_roundtrip=True, source_ports=208, target_ports=288,
        contexts=480, cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    return data


def orthogonal(matrix):
    q, _ = qr(matrix, mode="economic", check_finite=True, overwrite_a=True)
    error = float(np.max(np.abs(q.T @ q - np.eye(q.shape[1]))))
    assert error <= 1e-10
    return q, error


def factors(basis, target):
    small = basis.T @ target
    u, singular, vt = svd(small, full_matrices=False, check_finite=True, lapack_driver="gesdd")
    left = basis @ u[:, :RANK]
    right = vt[:RANK].T * singular[:RANK]
    signs = np.where(left[np.argmax(np.abs(left), axis=0), np.arange(RANK)] < 0, -1, 1)
    left *= signs
    right *= signs
    assert np.isfinite(left).all() and np.isfinite(right).all()
    assert np.max(np.abs(left.T @ left - np.eye(RANK))) <= 1e-10
    return left, right, singular


def losses(matrix, left, right):
    squared, huber = 0., 0.
    for start in range(0, LEFT, 1024):
        residual = left[start:start + 1024] @ right.T - matrix[start:start + 1024]
        squared += float(np.square(residual).sum())
        absolute = np.abs(residual)
        quadratic = np.minimum(absolute, DELTA)
        huber += float(np.sum(.5 * quadratic**2 + DELTA * (absolute - quadratic)))
    return squared, huber


def save_factors(out, stage, left, right):
    records = []
    for name, value in (("left", left), ("right", right)):
        path = out / f"{stage}-{name}.npy"
        assert not path.exists()
        np.save(path, value)
        assert np.array_equal(np.load(path), value)
        records.append(identity(path))
    return records


def train():
    assert socket.gethostname() in SHARDS and os.environ["OPENBLAS_NUM_THREADS"] == "8"
    frozen = read(ROOT / "freeze.json")
    for row in frozen["files"]:
        assert identity(row["path"]) == row
    begin, end = SHARDS[socket.gethostname()]
    data = materialize(begin, end)
    groups = []
    for q in range(begin, end):
        started, cpu = time.monotonic(), time.process_time()
        out = BUILD / f"q{q:02d}"
        out.mkdir()
        matrix = data[q - begin].astype(np.float64)
        matrix /= DENOM_FULL
        rng = np.random.default_rng(SEED + q)
        basis, error = orthogonal(matrix @ rng.standard_normal((RIGHT, RANK + 32)))
        errors = [error]
        for _ in range(2):
            side, error = orthogonal(matrix.T @ basis)
            basis, error2 = orthogonal(matrix @ side)
            errors.extend([error, error2])
        left, right, spectrum = factors(basis, matrix)
        initial_sse, initial_huber = losses(matrix, left, right)
        energy = sum(float(np.square(matrix[start:start + 1024]).sum())
                     for start in range(0, LEFT, 1024))
        projection_energy = float(np.square(spectrum[:RANK]).sum())
        assert abs(energy - initial_sse - projection_energy) <= 1e-9 * max(1., energy)
        initial_files = save_factors(out, "initial", left, right)
        history = [dict(step=0, squared_error=initial_sse, huber=initial_huber)]
        print("EXP500_INITIAL_COMPLETE", q, initial_huber, flush=True)
        for step in range(1, STEPS + 1):
            step_started, step_cpu = time.monotonic(), time.process_time()
            target = np.empty_like(matrix)
            old_distance = 0.
            for start in range(0, LEFT, 1024):
                prediction = left[start:start + 1024] @ right.T
                gradient = np.clip(prediction - matrix[start:start + 1024], -DELTA, DELTA)
                target[start:start + 1024] = prediction - gradient
                old_distance += float(np.square(gradient).sum())
            rng = np.random.default_rng(20261020500 + 100 * q + step)
            additions = target @ rng.standard_normal((RIGHT, 32))
            basis, orthogonal_error = orthogonal(np.column_stack((left, additions)))
            preserved_error = float(np.max(np.abs(left - basis @ (basis.T @ left))))
            assert preserved_error <= 1e-10
            new_left, new_right, _ = factors(basis, target)
            new_distance = 0.
            for start in range(0, LEFT, 1024):
                error = new_left[start:start + 1024] @ new_right.T - target[start:start + 1024]
                new_distance += float(np.square(error).sum())
            squared, huber = losses(matrix, new_left, new_right)
            assert new_distance <= old_distance + 1e-9 * max(1., old_distance)
            assert huber <= history[-1]["huber"] + 1e-9 * max(1., history[-1]["huber"])
            history.append(dict(step=step, squared_error=squared, huber=huber,
                                projection_distance=new_distance, old_projection_distance=old_distance,
                                orthogonal_error=orthogonal_error, preserved_error=preserved_error,
                                cpu_s=time.process_time() - step_cpu,
                                wall_s=time.monotonic() - step_started))
            left, right = new_left, new_right
            del target
            print("EXP500_STEP_COMPLETE", q, step, huber, flush=True)
        final_files = save_factors(out, "huber", left, right)
        record = dict(group=q, shape=[LEFT, RIGHT], rank=RANK, steps=STEPS, delta=DELTA,
                      initial_range_orthogonal_errors=errors, energy=energy,
                      initial_projection_energy=projection_energy, history=history,
                      initial=initial_files, final=final_files, all_training_checks=True,
                      cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
                      rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                      hostname=socket.gethostname())
        write(ROOT / f"group-{q:02d}.json", record)
        groups.append(record)
        del matrix
        print("EXP500_GROUP_COMPLETE", q, record["wall_s"], record["rss_bytes"], flush=True)
    write(ROOT / "training.json", dict(
        groups=groups, shard=[begin, end], all_training_checks=True,
        source_ports=208, target_ports=288, contexts=480, rank=RANK, steps=STEPS,
        freeze=identity(ROOT / "freeze.json"), disk_free_bytes=shutil.disk_usage(".").free))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "train"))
    args = parser.parse_args()
    {"prepare": prepare, "train": train}[args.stage]()
