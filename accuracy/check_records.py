#!/usr/bin/env python3
"""Validate every published record, both predictions, and the representative CSV."""
import csv
import gzip
import json
from pathlib import Path
import sys

import numpy as np
from make_subset import ORIGINAL_COUNT, PAIRS, SELECTED_COUNT, identity, selection

HERE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_records.py NEW_REPORT_JSON")
    manifest = json.loads((HERE / "records-manifest.json").read_text())
    for record in manifest["outputs"]:
        assert identity(HERE / record["path"]) == {
            k: record[k] for k in ("bytes", "sha256")}, record["path"]
    mapping = json.loads((HERE / "record-mapping.json").read_text())
    population = np.asarray(mapping["population_pair_rows"], "<u4")
    ports = mapping["ports"]
    arch_ports = json.loads((HERE.parent / "source/arch/SRB_Port.json").read_text())["Port"]
    assert ports == [p["Name"] for p in arch_ports] and len(set(ports)) == 496
    assert len(mapping["sources"]) == 208 and len(mapping["targets"]) == 288
    parts = []
    for record in manifest["outputs"]:
        if not record["path"].endswith(".npz"):
            continue
        assert record["start_index"] == sum(len(p["pair_id"]) for p in parts)
        with np.load(HERE / record["path"], allow_pickle=False) as packed:
            part = {k: packed[k] for k in packed.files}
        assert all(len(v) == record["rows"] for v in part.values())
        parts.append(part)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    n = len(data["pair_id"])
    assert n == manifest["rows"] == PAIRS * ORIGINAL_COUNT
    expected_types = dict(endpoints="<u2", input_row="<u4", pair_id="<u2", rank="u1",
        exact_delay="<i4", exp688_prediction="<i4", exp728_prediction="<i4",
        source_pin_seen_in_training="u1")
    assert set(data) == set(expected_types)
    for k, dtype in expected_types.items():
        assert data[k].dtype == np.dtype(dtype), k
    q = data["endpoints"].astype("<u8")
    assert q.shape == (n, 6) and np.all(q[:, (0, 3)] < 120)
    assert np.all(q[:, (1, 4)] < 550) and np.all(q[:, (2, 5)] < 496)
    cells = json.loads((HERE.parent / "source/arch/SRB_Inst.json").read_text())["Inst"]
    actual_cells = {int(c["y"]) * 120 + int(c["x"]) for c in cells}
    assert np.isin(q[:, 1] * 120 + q[:, 0], list(actual_cells)).all()
    assert np.isin(q[:, 4] * 120 + q[:, 3], list(actual_cells)).all()
    a = (q[:, 1] * 120 + q[:, 0]) * 496 + q[:, 2]
    b = (q[:, 4] * 120 + q[:, 3]) * 496 + q[:, 5]
    assert np.all(a != b) and len(np.unique((a << 32) | b)) == n
    si = np.array([mapping["sources"].index(p) if p in mapping["sources"] else -1 for p in ports])
    ti = np.array([mapping["targets"].index(p) if p in mapping["targets"] else -1 for p in ports])
    assert np.all(si[q[:, 2]] >= 0) and np.all(ti[q[:, 5]] >= 0)
    pair = data["pair_id"].astype("i8")
    assert np.array_equal(pair, si[q[:, 2]] * 288 + ti[q[:, 5]])
    assert np.all(np.bincount(pair, minlength=PAIRS) == ORIGINAL_COUNT)
    assert np.array_equal(np.sort(pair * ORIGINAL_COUNT + data["rank"]), np.arange(n))
    positions = data["input_row"].astype("i8")
    assert np.all(np.diff(positions) > 0) and 0 <= positions[0] < positions[-1] < 1_000_000_000
    with np.load(HERE.parent / "dataset_protocol/exclusions/training-source-pins.npz") as packed:
        seen = np.isin(a, packed["ids"])
    assert np.array_equal(seen, data["source_pin_seen_in_training"])
    assert int(seen.sum()) == manifest["full_source_pin_seen_rows"]
    assert population.shape == (PAIRS,) and population.sum() == 1_000_000_000
    weights = population[pair] / ORIGINAL_COUNT
    assert weights.sum() == 1_000_000_000
    truth = data["exact_delay"].astype("f8")
    assert truth.min() >= 0
    results = {}
    all_scores = {}
    for version in ("exp688", "exp728"):
        prediction = data[version + "_prediction"]
        assert prediction.min() >= 0
        points = 100 * (1 - np.tanh(4 * np.abs(prediction - truth) / np.maximum(truth, 1)))
        points[truth == 0] = 100 * (prediction[truth == 0] == 0)
        all_scores[version] = points
        accuracy = float(weights @ points / weights.sum())
        assert abs(accuracy - manifest["full_accuracy_pp"][version]) < 1e-10
        sums = np.bincount(pair, weights=points, minlength=PAIRS)
        sums2 = np.bincount(pair, weights=points**2, minlength=PAIRS)
        variance = np.maximum(0, (sums2 - sums**2 / ORIGINAL_COUNT) / (ORIGINAL_COUNT - 1))
        se = np.sqrt(np.sum((population / population.sum())**2 *
            (1 - ORIGINAL_COUNT / population) * variance / ORIGINAL_COUNT))
        results[version] = dict(accuracy_pp=accuracy, stratified_standard_error_pp=float(se))
    assert np.count_nonzero(data["exp688_prediction"] != data["exp728_prediction"]) == manifest["changed_rows"]
    chosen = selection()
    wanted = np.flatnonzero(chosen[pair, data["rank"]])
    with gzip.open(HERE / "exp728-exact-subset.csv.gz", "rt", newline="") as stream:
        reader = csv.DictReader(stream)
        for index in wanted:
            row = next(reader)
            sx, sy, sp, tx, ty, tp = q[index]
            assert row["From"] == f"SRB_{sx}_{sy}/{ports[sp]}"
            assert row["To"] == f"SRB_{tx}_{ty}/{ports[tp]}"
            assert int(row["sample_index"]) == index
            assert int(row["input_row"]) == positions[index]
            assert int(row["pair_id"]) == pair[index]
            assert int(row["rank_within_original_64"]) == data["rank"][index]
            for key in ("exact_delay", "exp688_prediction", "exp728_prediction",
                        "source_pin_seen_in_training"):
                assert int(row[key]) == data[key][index]
            pop = population[pair[index]]
            assert int(row["population_pair_rows"]) == pop
            assert float(row["sample_weight"]) == pop / SELECTED_COUNT
            assert float(row["original_sample_weight"]) == pop / ORIGINAL_COUNT
            assert row["split"] == "historical_1b_reviewed"
        assert next(reader, None) is None
    assert len(wanted) == manifest["selected_rows"] == PAIRS * SELECTED_COUNT
    for version, points in all_scores.items():
        w = population[pair[wanted]] / SELECTED_COUNT
        assert abs(float(w @ points[wanted] / w.sum()) -
                   manifest["subset_accuracy_pp"][version]) < 1e-10
    result = dict(passed=True, rows=n, unique_requests=n, port_pairs=PAIRS,
        subset_rows=len(wanted), endpoint_reconstruction_verified=True,
        source_pin_seen_verified=True, sample_weights_verified=True,
        score=results, delta_accuracy_pp=results["exp728"]["accuracy_pp"] -
            results["exp688"]["accuracy_pp"],
        exact_generation_rerun=False, complete_estimator_runs=0,
        scope="Frozen historical outputs and existing exact labels")
    with Path(sys.argv[1]).open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
