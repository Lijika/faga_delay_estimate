#!/usr/bin/env python3
"""Fit complete port-pair / geometry factors using bounded float64 blocks."""
import argparse
import hashlib
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np
import scipy
from scipy.linalg import svd

from exp208_nominal_parent_tree import identity, write
from exp500_split_residues import orthogonal
from exp504_tail_rectangles import PREPARATION, load_field, read

ROOT, BUILD = Path("validation/results/exp510"), Path("build/exp510")
PLAN = Path("experiment/实验510-完整端口对与全部几何的双表分解.md")
LEFT, RIGHT, CAPS, WIDTH = 59904, 264960, (64, 96), 128
SEED, BLOCK = 20261019510, 288
DENOM = np.tile(128 + 125 * (np.arange(552) // 46) + 125 * (np.arange(552) % 46), 480)


def prepare():
    assert socket.gethostname() == "lhj-NF5280M5" and Path.cwd().name == "exp510"
    assert not ROOT.exists() and not BUILD.exists()
    inputs = []
    for row in read(PREPARATION / "source-freeze.json")["files"]:
        actual = identity(Path("../exp500") / row["path"])
        assert (actual["bytes"], actual["sha256"]) == (row["bytes"], row["sha256"])
        inputs.append(Path(actual["path"]))
    labels = read(PREPARATION / "label-report.json")
    assert labels["evidence_passed"] and labels["certified_values"] == LEFT * RIGHT
    mapping = read(PREPARATION / "mapping.json")
    for key, count in (("source", 208), ("target", 288)):
        assert len(set(mapping[key + "_ids"])) == count
        assert len(set(mapping[key + "s"])) == count
    fields = read(PREPARATION / "fields.json")
    assert [row["number"] for row in fields] == list(range(208))
    for row in fields:
        assert row["source"] == mapping["sources"][row["number"]]
        actual = identity(Path("../exp499") / row["asset"]["path"])
        assert (actual["bytes"], actual["sha256"]) == (row["asset"]["bytes"], row["asset"]["sha256"])
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    shutil.copyfile(PREPARATION / "mapping.json", ROOT / "mapping.json")
    (ROOT / "installed-svd-help.txt").write_text(str(inspect.signature(svd)) + "\n" + svd.__doc__)
    files = [
        Path("validation/exp510_pair_geometry.py"), Path("validation/exp500_split_residues.py"),
        Path("validation/exp504_tail_rectangles.py"), Path("validation/exp208_nominal_parent_tree.py"),
        Path("validation/exp510_evaluate.py"), Path("validation/exp500_evaluate.py"),
        Path("tests/exp510_stream_decode.cpp"),
        Path("validation/results/exp510-launch/driver.py"),
        ROOT / "protocol-original.md", ROOT / "mapping.json",
        PREPARATION / "source-freeze.json", *inputs,
    ]
    write(ROOT / "freeze.json", dict(
        files=[identity(path) for path in dict.fromkeys(files)], source_ports=208,
        target_ports=288, port_pairs=LEFT, contexts=480, values=LEFT * RIGHT,
        shape=[LEFT, RIGHT], caps=CAPS, range_width=WIDTH, power_iterations=2,
        seed=SEED, row_block=BLOCK, numpy=np.__version__, scipy=scipy.__version__,
        hostname=socket.gethostname(), disk_free_bytes=shutil.disk_usage(".").free))
    print("EXP510_PREPARED", flush=True)


def check_freeze():
    frozen = read(ROOT / "freeze.json")
    for row in frozen["files"]:
        assert identity(row["path"]) == row
    return frozen


def coordinates():
    value = np.arange(RIGHT, dtype=np.int32)
    j, value = value % 46, value // 46
    i, value = value % 12, value // 12
    ry, value = value % 12, value // 12
    rx, d = value % 10, value // 10
    rebuilt = ((((d * 10 + rx) * 12 + ry) * 12 + i) * 46 + j)
    assert np.array_equal(rebuilt, np.arange(RIGHT)) and d.max() == 3
    x, y = rx + 10 * i, ry + 12 * j
    valid = (y <= 549) & ((x != 0) | (d // 2 == 0)) & ((y != 0) | (d % 2 == 0))
    assert int(valid.sum()) == 239 * 1099
    assert int(np.count_nonzero(valid & ((x < 20) | (y < 24)))) * LEFT == 3130642944
    return np.column_stack((d, rx, ry, i, j))


def materialize(destination):
    started, cpu = time.monotonic(), time.process_time()
    mapping, fields = read(ROOT / "mapping.json"), read(PREPARATION / "fields.json")
    assert [row["number"] for row in fields] == list(range(208))
    coordinates()
    values = np.empty((LEFT, RIGHT), dtype="<i2")
    digest = hashlib.sha256()
    for row in fields:
        s = row["number"]
        original = load_field(row, mapping)
        block = values[288 * s:288 * (s + 1)]
        block[:] = original.transpose(3, 0, 1, 2, 4, 5).reshape(288, RIGHT)
        restored = block.reshape(288, 4, 10, 12, 12, 46).transpose(1, 2, 3, 0, 4, 5)
        assert np.array_equal(restored, original)
        digest.update(memoryview(block).cast("B"))
        print("EXP510_SOURCE_MATERIALIZED", s, flush=True)
    write(destination, dict(
        shape=list(values.shape), dtype=values.dtype.str, matrix_sha256=digest.hexdigest(),
        bytes=values.nbytes, scalar_values=values.size, source_ports=208, target_ports=288,
        port_pairs=LEFT, contexts=480, complete_compressed_and_raw_sha=True,
        complete_inverse_transpose=True, coordinate_bijection=True,
        cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    return values


def matrix_blocks(values):
    for start in range(0, LEFT, BLOCK):
        block = values[start:start + BLOCK].astype(np.float64)
        block /= DENOM
        yield start, block


def multiply(values, factor, transpose, label):
    started, cpu = time.monotonic(), time.process_time()
    width = factor.shape[1]
    assert factor.shape[0] == (LEFT if transpose else RIGHT)
    result = np.zeros((RIGHT if transpose else LEFT, width), dtype=np.float64)
    for start, block in matrix_blocks(values):
        if transpose:
            result += block.T @ factor[start:start + len(block)]
        else:
            result[start:start + len(block)] = block @ factor
    assert np.isfinite(result).all()
    print("EXP510_MULTIPLY_COMPLETE", label, time.monotonic() - started, flush=True)
    return result, dict(label=label, transpose=transpose, columns=width,
                        cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started)


def train():
    assert socket.gethostname() == "lhj-NF5280M5" and Path.cwd().name == "exp510"
    assert os.environ.get("OPENBLAS_NUM_THREADS") == "8"
    check_freeze()
    assert not (ROOT / "training.json").exists()
    assert not any((BUILD / (side + ".npy")).exists() for side in ("left", "right"))
    started, cpu = time.monotonic(), time.process_time()
    write(ROOT / "environment.json", dict(
        hostname=socket.gethostname(), load=os.getloadavg(),
        meminfo=Path("/proc/meminfo").read_text(), numpy=np.__version__,
        scipy=scipy.__version__, blas_threads=8))
    values = materialize(ROOT / "materialization.json")
    rng = np.random.default_rng(SEED)
    omega = rng.standard_normal((RIGHT, WIDTH))
    product, first = multiply(values, omega, False, "initial")
    del omega
    basis, error = orthogonal(product)
    del product
    orthogonal_errors, passes = [error], [first]
    for step in range(2):
        product, record = multiply(values, basis, True, f"power-{step}-transpose")
        passes.append(record)
        side, error = orthogonal(product)
        orthogonal_errors.append(error)
        del product
        product, record = multiply(values, side, False, f"power-{step}-forward")
        passes.append(record)
        del side
        basis, error = orthogonal(product)
        orthogonal_errors.append(error)
        del product
    projected, record = multiply(values, basis, True, "small-matrix")
    passes.append(record)
    energy_small = float(np.square(projected).sum())
    u, singular, vt = svd(projected.T, full_matrices=False, check_finite=True, lapack_driver="gesdd")
    assert u.shape == (WIDTH, WIDTH) and vt.shape == (WIDTH, RIGHT)
    assert np.isfinite(singular).all() and np.all(singular[:-1] >= singular[1:])
    assert abs(energy_small - float(np.square(singular).sum())) <= 1e-9 * max(1., energy_small)
    left = basis @ u[:, :max(CAPS)]
    signs = np.where(left[np.argmax(np.abs(left), axis=0), np.arange(max(CAPS))] < 0, -1, 1)
    left *= signs
    orthogonal_errors.append(float(np.abs(left.T @ left - np.eye(max(CAPS))).max()))
    assert max(orthogonal_errors) <= 1e-10
    del projected, basis, u
    right, record = multiply(values, left, True, "independent-projection")
    passes.append(record)
    expected = (vt[:max(CAPS)].T * singular[:max(CAPS)]) * signs
    projection_error = float(np.max(np.abs(right - expected)))
    assert projection_error <= 1e-9 * max(1., float(singular[0]))
    del vt, expected
    assert left.shape == (LEFT, max(CAPS)) and right.shape == (RIGHT, max(CAPS))
    energy, errors = 0., {rank: 0. for rank in CAPS}
    for start, block in matrix_blocks(values):
        energy += float(np.square(block).sum())
        for rank in CAPS:
            residual = block - left[start:start + len(block), :rank] @ right[:, :rank].T
            errors[rank] += float(np.square(residual).sum())
        if start % (16 * BLOCK) == 0:
            print("EXP510_FULL_RESIDUAL_BLOCK", start // BLOCK, flush=True)
    checks = {}
    for rank in CAPS:
        projected_energy = float(np.square(right[:, :rank]).sum())
        remainder = energy - projected_energy
        assert abs(errors[rank] - remainder) <= 1e-9 * max(1., energy)
        checks[str(rank)] = dict(residual_energy=errors[rank], projected_energy=projected_energy,
                                 energy_difference=remainder)
    assert errors[96] <= errors[64] + 1e-9 * max(1., energy)
    assets = []
    for name, factor in (("left", left), ("right", right)):
        path = BUILD / (name + ".npy")
        assert not path.exists()
        np.save(path, factor)
        assert np.array_equal(factor, np.load(path))
        assets.append(identity(path))
    check_freeze()
    write(ROOT / "training.json", dict(
        factors=assets, rank=max(CAPS), caps=CAPS, range_width=WIDTH, passes=passes,
        singular_values=singular.tolist(), orthogonal_errors=orthogonal_errors,
        projection_max_error=projection_error, input_energy=energy, residual_checks=checks,
        shape=[LEFT, RIGHT], values=LEFT * RIGHT, source_ports=208, target_ports=288,
        port_pairs=LEFT, contexts=480, all_training_checks=True,
        materialization=identity(ROOT / "materialization.json"), freeze=identity(ROOT / "freeze.json"),
        cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    print("EXP510_FULL_PORT_TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "train"))
    args = parser.parse_args()
    {"prepare": prepare, "train": train}[args.stage]()
