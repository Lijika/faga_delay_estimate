#!/usr/bin/env python3
"""Check the full published subset and recompute its population-weighted Acc."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from make_subset import ORIGINAL_COUNT, PAIRS, SELECTED_COUNT, identity, point, selection

HERE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_subset.py NEW_REPORT_JSON")
    report_path = Path(sys.argv[1])
    manifest = json.loads((HERE / "subset-manifest.json").read_text())
    path = HERE / "exp688-exact-subset.csv.gz"
    assert identity(path) == manifest["output"]
    chosen = selection()
    seen = np.zeros_like(chosen)
    population = np.zeros(PAIRS, "i8")
    values = np.empty((PAIRS, SELECTED_COUNT), "f8")
    counts = np.zeros(PAIRS, "i4")
    mapping = json.loads((HERE.parent / "path_witness/query_source/mapping.json").read_text())
    si, ti = {n: i for i, n in enumerate(mapping["sources"])}, \
             {n: i for i, n in enumerate(mapping["targets"])}
    requests = set()
    weights = 0.0
    seen_rows = 0
    previous_index, previous_input_row = -1, -1
    with gzip.open(path, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            p, rank = int(row["pair_id"]), int(row["rank_within_original_64"])
            index, input_row = int(row["sample_index"]), int(row["input_row"])
            assert index > previous_index and input_row > previous_input_row
            assert 0 <= index < PAIRS * ORIGINAL_COUNT and 0 <= input_row < 1_000_000_000
            previous_index, previous_input_row = index, input_row
            a, b = row["From"], row["To"]
            assert p == si[a.split("/", 1)[1]] * 288 + ti[b.split("/", 1)[1]]
            assert (a, b) not in requests
            requests.add((a, b))
            assert chosen[p, rank] and not seen[p, rank]
            seen[p, rank] = True
            n = int(row["population_pair_rows"])
            assert population[p] in (0, n)
            population[p] = n
            assert float(row["sample_weight"]) == n / SELECTED_COUNT
            assert float(row["original_sample_weight"]) == n / ORIGINAL_COUNT
            weights += float(row["sample_weight"])
            assert row["split"] == "historical_1b_reviewed"
            assert row["source_pin_seen_in_training"] in ("0", "1")
            seen_rows += int(row["source_pin_seen_in_training"])
            values[p, counts[p]] = point(int(row["exp688_prediction"]), int(row["exact_delay"]))
            counts[p] += 1
    assert np.array_equal(seen, chosen) and np.all(counts == SELECTED_COUNT)
    assert population.sum() == weights == 1_000_000_000
    assert seen_rows == manifest["subset_source_pin_seen_rows"]
    mass = population / population.sum()
    accuracy = float(mass @ values.mean(axis=1))
    variance = float(np.sum(mass**2 * (1 - SELECTED_COUNT / population)
                            * values.var(axis=1, ddof=1) / SELECTED_COUNT))
    assert abs(accuracy - manifest["subset_weighted_accuracy_pp"]) < 1e-10
    result = dict(passed=True, rows=len(requests), port_pairs=PAIRS,
                  rows_per_pair=SELECTED_COUNT, unique_requests=len(requests),
                  weighted_accuracy_pp=accuracy, weight_sum=weights,
                  stratified_standard_error_pp=math.sqrt(variance),
                  source_pin_seen_rows=seen_rows, exact_generation_rerun=False,
                  predictions_from_original_complete_exp688_run=True)
    with report_path.open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
