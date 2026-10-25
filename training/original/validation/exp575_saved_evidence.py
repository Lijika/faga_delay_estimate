#!/usr/bin/env python3
"""Audit full saved distance-group factors on r9 without request inference."""
import json
import os
from pathlib import Path
import resource
import socket
import time

import numpy as np

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD, OFFLINE = Path("validation/results/exp575"), Path("build/exp575"), Path("offline")
LEFT, RIGHT = 59904, 264960


def read(path):
    return json.loads(Path(path).read_text())


def check(record, path=None):
    found = identity(OFFLINE / record["path"] if path is None else path)
    assert (found["bytes"], found["sha256"]) == (record["bytes"], record["sha256"])


def metric(record, columns, counts):
    assert record["full_port_pairs"] == LEFT and record["geometries"] == columns
    assert record["values"] == LEFT * columns == sum(b["values"] for b in record["by_quotient_sum"])
    assert [b["values"] for b in record["by_quotient_sum"]] == counts
    for name in ("squared", "absolute"):
        assert np.isfinite(record[name]) and record[name] >= 0
        assert abs(record[name] - sum(b[name] for b in record["by_quotient_sum"])) <= 1e-9 * max(1., record[name])


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp575")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    started, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True)
    training = read(OFFLINE / ROOT / "training.json")
    assert training["all_training_checks"] and training["shape"] == [LEFT, RIGHT]
    assert training["port_pairs"] == LEFT
    check(training["freeze"])
    frozen = read(OFFLINE / ROOT / "freeze.json")
    assert frozen["split_quotient_sum"] == 3 and frozen["near_ranks"] == [128, 192] and frozen["far_rank"] == 96
    for item in frozen["files"]:
        if item["path"].startswith("../exp571-recovery-01/"):
            check(item, OFFLINE / ROOT / "G-reference-diagnostics.json")
        else:
            check(item)
    for item in frozen["source_assets"]:
        assert item["path"].startswith("../exp557/")
        check(item, Path("../exp557/offline") / item["path"][len("../exp557/"):])
    materialized = read(OFFLINE / ROOT / "materialization.json")
    assert materialized["matrix_sha256"] == "c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86"
    assert materialized["complete_compressed_and_raw_sha"] and materialized["complete_inverse_transpose"]
    assert materialized["bytes"] == LEFT * RIGHT * 2
    check(training["center"])
    check(training["regions"])
    center = np.load(OFFLINE / BUILD / "center.npy")
    regions = np.load(OFFLINE / BUILD / "regions.npy")
    qsum = (np.arange(RIGHT) % 552) // 46 + np.arange(RIGHT) % 46
    bands = np.select((qsum == 0, qsum <= 3, qsum <= 15), (0, 1, 2), default=3)
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    assert regions.shape == (RIGHT,) and regions.dtype == np.dtype("u1")
    assert np.array_equal(regions, qsum > 3) and np.bincount(regions).tolist() == [4800, 260160]
    full_counts = (np.bincount(bands, minlength=4) * LEFT).tolist()
    reference = training["reference"]
    metric(reference, RIGHT, full_counts)
    assert reference == read(OFFLINE / ROOT / "G-reference-diagnostics.json")
    gleft = np.load("../exp557/offline/build/exp557/G-left.npy")[0]
    gright = np.load("../exp557/offline/build/exp557/G-right.npy")
    candidates = {(r["group"], r["maximum_rank"]): r for r in training["candidates"]}
    assert set(candidates) == {(0, 128), (0, 192), (1, 96)}
    audited, models = {}, []
    assert [m["name"] for m in training["models"]] == ["N128", "N192"]
    for model, near_rank, upper in zip(training["models"], (128, 192), (78403072, 86685696)):
        assert len(model["parts"]) == 2
        for group, part in enumerate(model["parts"]):
            rank = part["rank"]
            maximum = near_rank if group == 0 else 96
            assert 1 <= rank <= maximum and part["port_pairs"] == LEFT
            assert part["name"] == f"group-{group}-r{maximum}"
            candidate = candidates[(group, maximum)]
            keys = np.flatnonzero(regions == group)
            counts = (np.bincount(bands[keys], minlength=4) * LEFT).tolist()
            for result in (part["diagnostic"], candidate["new"], candidate["reference"]):
                metric(result, len(keys), counts)
            use_g = candidate["new"]["absolute"] >= candidate["reference"]["absolute"]
            assert (part["origin"] == "G") == use_g
            chosen = candidate["reference"] if use_g else candidate["new"]
            for name in ("squared", "absolute"):
                assert part["diagnostic"][name] == chosen[name]
            if part["name"] in audited:
                assert part == audited[part["name"]]["descriptor"]
                continue
            for item in part["assets"]:
                check(item)
            load = lambda suffix: np.load(OFFLINE / BUILD / (part["name"] + "-" + suffix + ".npy"))
            left, right = load("left"), load("right")
            li, ri, le, re = [load(s) for s in ("left-integers", "right-integers", "left-exponent", "right-exponent")]
            assert np.array_equal(load("keys"), keys) and part["geometries"] == len(keys)
            assert left.shape == li.shape == (LEFT, rank) and right.shape == ri.shape == (len(keys), rank)
            orthogonal = float(np.abs(left.T @ left - np.eye(rank)).max())
            assert orthogonal < 1e-10
            if use_g:
                assert rank == 96 and np.array_equal(left, gleft) and np.array_equal(right, gright[keys])
            for floating, integer, exponent in ((left, li, le), (right, ri, re)):
                assert np.isfinite(floating).all() and integer.dtype == np.dtype("<i2")
                assert exponent.shape == (rank,) and exponent.dtype == np.dtype("<i4")
                rounded = np.rint(np.ldexp(floating, -exponent))
                assert np.abs(rounded).max() <= 32767 and np.array_equal(rounded.astype("<i2"), integer)
            exponent = le.astype(np.int64) + re
            minimum = int(exponent.min())
            lm, rm = np.abs(li.astype(np.int32)).max(axis=0), np.abs(ri.astype(np.int32)).max(axis=0)
            bound = sum((int(a) * int(b)) << int(e - minimum) for a, b, e in zip(lm, rm, exponent))
            assert bound == part["integer_sum_bound"] < 2**53
            assert minimum == part["common_exponent"] > -1022 and exponent.max() < 970
            assert part["factor_bytes"] == li.nbytes + ri.nbytes + le.nbytes + re.nbytes
            audited[part["name"]] = dict(descriptor=part, orthogonal_max_error=orthogonal, integer_sum_bound=bound)
        diagnostic = model["diagnostic"]
        metric(diagnostic, RIGHT, full_counts)
        for name in ("squared", "absolute", "input_energy"):
            assert diagnostic[name] == sum(p["diagnostic"][name] for p in model["parts"])
        reduction = 1 - diagnostic["absolute"] / reference["absolute"]
        assert reduction == model["relative_l1_reduction_vs_G"] >= -1e-12
        assert bool(reduction >= .02) == model["fixed_l1_gate_passed"]
        size = sum(p["factor_bytes"] for p in model["parts"]) + center.nbytes + regions.nbytes
        assert size == model["table_bytes"] <= upper
        models.append(dict(name=model["name"], ranks=[p["rank"] for p in model["parts"]], table_bytes=size,
                           relative_l1_reduction_vs_G=reduction, fixed_l1_gate_passed=model["fixed_l1_gate_passed"]))
    write(ROOT / "saved-evidence-audit.json", dict(all_saved_checks=True, full_port_pairs=LEFT, geometries=RIGHT,
          models=models, parts=[dict(name=n, orthogonal_max_error=a["orthogonal_max_error"],
                                    integer_sum_bound=a["integer_sum_bound"]) for n, a in audited.items()],
          raw_matrix_recomputed=False, saved_reconstruction_statistics_recomputed=False,
          source=identity(Path(__file__)), training=identity(OFFLINE / ROOT / "training.json"),
          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    print("EXP575_COMPLETE_SAVED_AUDIT", flush=True)


if __name__ == "__main__":
    main()
