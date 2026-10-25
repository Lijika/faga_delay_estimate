#!/usr/bin/env python3
"""Audit the complete saved exp571 representation on r9 without request scoring."""
import os
from pathlib import Path
import resource
import socket
import time

import numpy as np
import xgboost as xgb

import exp557_evaluate as previous
from exp567_evaluate import json_leaves

ROOT, BUILD, OFFLINE = Path("validation/results/exp571"), Path("build/exp571"), Path("offline")
LEFT, RIGHT, RANK = 59904, 264960, 16


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp571")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    started, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True)
    meta = previous.read(OFFLINE / ROOT / "training.json")
    materialized = previous.read(OFFLINE / ROOT / "materialization.json")
    assert meta["all_training_checks"] and meta["shape"] == [LEFT, RIGHT]
    assert (meta["source_ports"], meta["target_ports"], meta["port_pairs"]) == (208, 288, LEFT)
    assert materialized["matrix_sha256"] == "c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86"
    assert materialized["complete_compressed_and_raw_sha"] and materialized["complete_inverse_transpose"]
    assert materialized["bytes"] == 31_744_327_680
    previous.real.check(OFFLINE / meta["center"]["path"], meta["center"])
    previous.real.check(OFFLINE / meta["freeze"]["path"], meta["freeze"])
    center = np.load(OFFLINE / BUILD / "center.npy")
    assert center.shape == (LEFT,) and center.dtype == np.dtype("<i2")
    frozen = previous.read(OFFLINE / ROOT / "freeze.json")
    feature_record = next(a for a in frozen["source_assets"] if a["path"].endswith("router-features.npy"))
    feature_path = Path("../exp557/offline/build/exp557/router-features.npy")
    previous.real.check(feature_path, feature_record)
    features = np.load(feature_path)
    router = previous.read(OFFLINE / ROOT / "initial-router.json")
    for item in [router["model"], *router["assets"]]:
        previous.real.check(OFFLINE / item["path"], item)
    model_path = OFFLINE / router["model"]["path"]
    trees = previous.read(model_path)["learner"]["gradient_booster"]["model"]["trees"]
    assert len(trees) == 1 and not trees[0]["categories"] and not any(trees[0]["split_type"])
    booster = xgb.Booster(); booster.load_model(model_path)
    native = booster.predict(xgb.DMatrix(features, nthread=1), pred_leaf=True).reshape(-1).astype("<i4")
    independent = json_leaves(trees[0], features)
    assert np.array_equal(native, independent)
    assert np.array_equal(native, np.load(OFFLINE / BUILD / "initial-native-leaf.npy"))
    initial_regions = np.load(OFFLINE / BUILD / "initial-regions.npy")
    assert np.array_equal(initial_regions, np.searchsorted(np.unique(native), native))
    assert np.bincount(initial_regions).tolist() == router["region_counts"]
    assert len(router["region_counts"]) <= 32 and min(router["region_counts"]) >= 32

    models = []
    for descriptor in meta["models"]:
        name, groups = descriptor["name"], descriptor["regions"]
        assert name in ("I", "K") and 1 <= groups <= 32 and descriptor["rank"] == RANK
        for item in descriptor["assets"]:
            previous.real.check(OFFLINE / item["path"], item)
        def load(suffix):
            return np.load(OFFLINE / BUILD / (name + "-" + suffix + ".npy"))
        left, right, regions = (load(s) for s in ("left", "right", "regions"))
        li, ri, le, re = (load(s) for s in ("left-integers", "right-integers", "left-exponent", "right-exponent"))
        assert left.shape == (groups, LEFT, RANK) and right.shape == (RIGHT, RANK)
        assert li.shape == left.shape and ri.shape == right.shape
        assert regions.shape == (RIGHT,) and regions.dtype == np.dtype("u1") and regions.max() < groups
        assert np.bincount(regions, minlength=groups).tolist() == descriptor["region_counts"]
        if name == "I":
            assert np.array_equal(regions, initial_regions)
        errors = [float(np.abs(basis.T @ basis - np.eye(RANK)).max()) for basis in left]
        assert max(errors) < 1e-10
        for floating, quantized, exponent in ((left, li, le), (right, ri, re)):
            assert np.isfinite(floating).all() and quantized.dtype == np.dtype("<i2")
            assert exponent.shape == (RANK,) and exponent.dtype == np.dtype("<i4")
            rounded = np.rint(np.ldexp(floating, -exponent))
            assert np.isfinite(rounded).all() and np.abs(rounded).max() <= 32767
            assert np.array_equal(rounded.astype("<i2"), quantized)
        exponent = le.astype(np.int64) + re
        minimum = int(exponent.min())
        lm, rm = np.abs(li.astype(np.int32)).max(axis=(0, 1)), np.abs(ri.astype(np.int32)).max(axis=0)
        bound = sum((int(a) * int(b)) << int(e - minimum) for a, b, e in zip(lm, rm, exponent))
        assert bound == descriptor["integer_sum_bound"] < 2**53
        assert minimum == descriptor["common_exponent"] > -1022 and exponent.max() < 970
        table_bytes = li.nbytes + ri.nbytes + regions.nbytes + center.nbytes + le.nbytes + re.nbytes
        assert table_bytes == descriptor["table_bytes"] <= 70_205_312
        models.append(dict(name=name, regions=groups, orthogonal_max_error=max(errors),
                           integer_sum_bound=bound, table_bytes=table_bytes))
    assert [m["name"] for m in models] == ["I", "K"]
    energy = meta["reference"]["input_energy"]
    assert abs(energy - 54862634.34903368) < 1e-9 * energy
    assert abs(meta["reference"]["squared"] - 1203634.579565436) < 1e-8 * energy
    for key in ("reference", "initial", "final"):
        diagnostic = meta[key]
        assert diagnostic["full_port_pairs"] == LEFT and diagnostic["geometries"] == RIGHT
        assert diagnostic["values"] == LEFT * RIGHT == sum(b["values"] for b in diagnostic["by_quotient_sum"])
        for metric in ("squared", "absolute"):
            assert abs(diagnostic[metric] - sum(b[metric] for b in diagnostic["by_quotient_sum"])) < 1e-9 * max(1., diagnostic[metric])
    optimization = previous.read(OFFLINE / ROOT / "optimization.json")
    assert 1 <= optimization["sweeps"] == len(optimization["records"]) <= 2
    old = meta["initial"]["squared"]
    for record in optimization["records"]:
        assert abs(record["before"] - old) <= 1e-9 * energy
        assert record["residual_energy"] <= record["after_assignment"] + 1e-9 * energy
        assert record["after_assignment"] <= record["before"] + 1e-9 * energy
        assert sum(g["keys"] for g in record["groups"]) == RIGHT
        total = 0.
        for group in record["groups"]:
            fitted = group["fit"]
            if fitted is not None:
                assert fitted["port_pairs"] == LEFT and fitted["rank"] == RANK
                assert fitted["keys"] == group["keys"] and max(fitted["orthogonal_errors"]) <= 1e-10
            expected = min(group["old_residual"], fitted["residual_energy"]) if fitted else group["old_residual"]
            assert abs(group["residual"] - expected) <= 1e-9 * energy
            total += expected
        assert abs(total - record["residual_energy"]) <= 1e-9 * energy
        old = record["residual_energy"]
    assert abs(old - meta["final"]["squared"]) <= 1e-9 * energy
    reduction = 1 - meta["final"]["absolute"] / meta["reference"]["absolute"]
    assert reduction == meta["relative_l1_reduction_vs_G"]
    assert bool(reduction >= .02) == meta["fixed_l1_gate_passed"]
    previous.write(ROOT / "saved-evidence-audit.json", dict(all_saved_checks=True,
        full_port_pairs=LEFT, geometries=RIGHT, models=models, complete_router_equality=True,
        relative_l1_reduction_vs_G=reduction, fixed_l1_gate_passed=bool(reduction >= .02),
        raw_matrix_recomputed=False, saved_reconstruction_statistics_recomputed=False,
        real_request_scoring_started=False, source=previous.identity(Path(__file__)),
        training=previous.identity(OFFLINE / ROOT / "training.json"), cpu_s=time.process_time() - cpu,
        wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
    print("EXP571_COMPLETE_SAVED_AUDIT", reduction, flush=True)


if __name__ == "__main__":
    main()
