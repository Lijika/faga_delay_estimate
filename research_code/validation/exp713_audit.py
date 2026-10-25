#!/usr/bin/env python3
"""Rebuild exp713 predictions and statistics independently of the fit driver."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT, BUILD = Path("validation/results/exp713"), Path("build/exp713")


def read(path):
    return json.loads(Path(path).read_text())


def checked(item):
    p = Path(item["path"])
    assert p.stat().st_size == item["bytes"]
    assert hashlib.sha256(p.read_bytes()).hexdigest() == item["sha256"], str(p)


def main():
    report, frozen = read(ROOT / "report.json"), read(ROOT / "freeze.json")
    for item in frozen["inputs"]:
        checked(item)
    with np.load("../exp623/build/exp623/data.npz") as data:
        truth, base, mandatory, folds, routes = (
            data[k] for k in ("truth", "base", "mandatory", "folds", "routes"))
    with np.load("../exp585/build/exp585/training.npz") as data:
        x, clusters = data["features"][:, :53], data["clusters"]
        assert np.array_equal(folds, data["folds"])
    n = len(truth)
    assert n == 1_000_000 and (truth > 0).all()
    pair, context, qx, qy = np.fromfile("../exp615/build/exp615/keys.bin", "<u4",
                                      offset=12).reshape(n, 4).T.astype("i8")
    far = qx + qy > 3
    scalar = Path("../exp619/build/exp619/Q4.p4").read_bytes()
    packed = np.frombuffer(scalar, "u1", offset=64)
    at = pair * 480 + context
    old = np.frombuffer(scalar, "i1", count=16, offset=32)[
        (packed[at // 2] >> (4 * (at % 2))) & 15].astype("i8")
    old[~far] = 0
    curve = Path("../exp654/build/exp654/D64.curves.u8").read_bytes()
    directory = np.frombuffer(curve, "u1", count=59904 * 480, offset=64)
    values = np.frombuffer(curve, "u1", offset=64 + 59904 * 480).reshape(4, 256, 542)
    before = np.array([4, 7, 9, 10, 10, 10, 10, 10, 10, 10, 10, 10])
    local = qx[far] * 46 + qy[far] - before[qx[far]]
    correction = np.zeros(n, "i8")
    correction[far] = values[context[far] // 120, directory[at[far]], local].astype("i8") - 55
    base = base.astype("i8") - old + correction
    ax, ay, tx, ty = x[:, 28:32].astype("i4").T
    low, high = np.minimum(ay, ty), np.maximum(ay, ty)
    bands = sum((low < y) & (high > y + 49) for y in range(0, 550, 100))
    vertical = (ax >= 76) & (ax <= 89) & (tx >= 76) & (tx <= 89) & (bands > 0)
    support = np.fromfile(BUILD / "features.u16", "<u2").reshape(n, 4)[:, 2:]
    bits = ((support[:, :, None] >> np.arange(16)) & 1).reshape(n, 32)
    population = read(ROOT / "support-check.json")["support_bit_population"]
    assert np.array_equal(bits.astype("<f4").mean(axis=0), population)
    raws = dict(A=np.fromfile("../exp640/build/exp640/S8-raw.f64", "<f8"),
                C=np.fromfile("../exp656/build/exp656/S8-raw.f64", "<f8"))
    for arm in ("P", "R"):
        features = np.column_stack((x if arm == "P" else np.column_stack((x[:, :26], x[:, 50:53])), bits))
        result = np.empty(n, "<f8")
        training = read(ROOT / (arm + "-training.json"))
        assert len(training["records"]) == 48
        for record in training["records"]:
            checked(record["model"])
            fold, route = record["fold"], record["route"]
            learn, test = (folds != fold) & (routes == route), (folds == fold) & (routes == route)
            assert not np.intersect1d(clusters[learn], clusters[test]).size
            assert (int(learn.sum()), int(test.sum())) == (record["train_rows"], record["test_rows"])
            model = read(record["model"]["path"])
            assert model["scale_and_bias"] == [1, [0]]
            mapping = {f["feature_index"]: f["flat_feature_index"]
                       for f in model["features_info"]["float_features"]}
            raw = np.zeros(int(test.sum()), "<f8")
            for tree in model["oblivious_trees"][:8]:
                leaf = np.zeros(len(raw), "i4")
                for j, split in enumerate(tree["splits"] or []):
                    leaf += (features[test, mapping[split["float_feature_index"]]] >
                             split["border"]).astype("i4") * (1 << j)
                raw += np.asarray(tree["leaf_values"])[leaf]
            result[test] = raw
        checked(training["raw"])
        assert np.array_equal(result, np.fromfile(BUILD / (arm + "-raw.f64"), "<f8"))
        raws[arm] = result
    replacement = np.fromfile("../exp678/build/exp678/HV8-raw.f64", "<f8")
    scores, predictions = {}, {}
    for arm, raw in raws.items():
        raw[vertical] = replacement[vertical]
        pred = np.floor(np.maximum(0, base + raw) + .5).astype("i8") + mandatory
        assert np.array_equal(pred, np.fromfile(BUILD / (arm + "-prediction.i32"), "<i4"))
        score = 100 * (1 - np.tanh(4 * np.abs(pred - truth) / truth))
        scores[arm], predictions[arm] = score, pred
        assert abs(float(score.mean()) - report["metrics"][arm]["accuracy_pp"]) < 1e-11
        assert np.array_equal(pred[vertical], predictions["A"][vertical])
    family = x[:, 0].astype("i4")
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(20261025713).integers(26, size=(9999, 26))
    for name, entry in report["comparisons"].items():
        arm, reference = name.split("-")
        diff = scores[arm] - scores[reference]
        totals = np.bincount(family, weights=diff, minlength=26)
        interval = np.quantile(totals[draws].sum(axis=1) / counts[draws].sum(axis=1),
                               [.00625, .99375])
        assert abs(float(diff.mean()) - entry["delta_accuracy_pp"]) < 1e-12
        assert np.array_equal(interval, entry["four_comparison_simultaneous_family_ci95_pp"])
        assert np.count_nonzero(predictions[arm] != predictions[reference]) == entry["changed_rows"]
        assert not entry["quality_gate"]
    assert report["selected"] is None and report["all_checks_passed"]
    audit = dict(all_checks_passed=True, independently_decoded_models=96, rows=n,
                 curve_base_and_integer_predictions_equal=True, source_pin_overlap=0,
                 four_paired_statistics_equal=True, V_rows=int(vertical.sum()), selected=None,
                 report_sha256=hashlib.sha256((ROOT / "report.json").read_bytes()).hexdigest())
    (ROOT / "independent-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
