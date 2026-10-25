#!/usr/bin/env python3
"""Select eight of the 64 exp683 labels per pair without reading their values."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

SEED = 202610250688
PAIRS, ORIGINAL_COUNT, SELECTED_COUNT = 59904, 64, 8


def identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return dict(bytes=path.stat().st_size, sha256=digest.hexdigest())


def point(prediction, exact):
    if exact == 0:
        return 100.0 if prediction == 0 else 0.0
    return 100 * (1 - math.tanh(4 * abs(prediction - exact) / exact))


def selection(seed=SEED):
    rng = np.random.default_rng(seed)
    result = np.zeros((PAIRS, ORIGINAL_COUNT), dtype=bool)
    for row in result:
        row[rng.choice(ORIGINAL_COUNT, SELECTED_COUNT, replace=False)] = True
    assert np.all(result.sum(axis=1) == SELECTED_COUNT)
    assert point(0, 0) == point(100, 100) == 100 and point(1, 0) == 0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exact_directory", type=Path)
    parser.add_argument("prediction_csv", type=Path)
    parser.add_argument("training_requests", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    base, out = args.exact_directory, args.output_directory
    out.mkdir(parents=True, exist_ok=True)
    chosen = selection()
    sources = (base / "sources").read_text().splitlines()
    targets = (base / "targets").read_text().splitlines()
    si, ti = dict(zip(sources, range(208))), dict(zip(targets, range(288)))
    population = np.asarray(json.loads((base / "pair-populations.json").read_text()), "i8")
    assert len(si) == 208 and len(ti) == 288 and population.sum() == 1_000_000_000
    with args.training_requests.open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        training_pins = {row[0] for row in reader}
    files = [base / n for n in ("exact.csv", "positions.txt", "pair-populations.json",
                                "sources", "targets", "sampling-plan.bin")]
    files += [args.prediction_csv, args.training_requests]
    provenance = {str(p): identity(p) for p in files}
    counts = np.zeros(PAIRS, "i4")
    full_points, subset_points = np.zeros((2, PAIRS), "f8")
    source_seen, selected_seen = 0, 0
    output = out / "exp688-exact-subset.csv.gz"
    with (base / "exact.csv").open(newline="") as truth, \
            args.prediction_csv.open(newline="") as predictions, \
            (base / "positions.txt").open() as positions, output.open("xb") as raw:
        exact_reader, pred_reader = csv.reader(truth), csv.reader(predictions)
        assert next(exact_reader) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        assert next(pred_reader) == ["row", "From", "To", "delay"]
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, \
                io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
            writer = csv.writer(text, lineterminator="\n")
            writer.writerow(["sample_index", "input_row", "pair_id", "rank_within_original_64",
                             "From", "To", "exact_delay", "exp688_prediction",
                             "population_pair_rows", "sample_weight", "original_sample_weight",
                             "split", "source_pin_seen_in_training"])
            previous = -1
            kept = 0
            for i, label in enumerate(exact_reader):
                prediction = next(pred_reader)
                row = int(next(positions))
                assert int(label[0]) == i and int(prediction[0]) == row and row > previous
                assert label[1:3] == prediction[1:3]
                pair = si[label[1].split("/", 1)[1]] * 288 + ti[label[2].split("/", 1)[1]]
                rank = int(counts[pair])
                assert rank < ORIGINAL_COUNT
                counts[pair] += 1
                exact, predicted = int(label[3]), int(prediction[3])
                assert exact >= 0 and predicted >= 0
                score = point(predicted, exact)
                full_points[pair] += score
                seen = label[1] in training_pins
                source_seen += seen
                if chosen[pair, rank]:
                    writer.writerow([i, row, pair, rank, *label[1:3], exact, predicted,
                                     int(population[pair]), population[pair] / SELECTED_COUNT,
                                     population[pair] / ORIGINAL_COUNT,
                                     "historical_1b_reviewed", int(seen)])
                    subset_points[pair] += score
                    selected_seen += seen
                    kept += 1
                previous = row
            assert next(pred_reader, None) is None and next(positions, None) is None
    assert np.all(counts == ORIGINAL_COUNT) and kept == PAIRS * SELECTED_COUNT
    full_acc = float(population @ (full_points / ORIGINAL_COUNT) / population.sum())
    assert abs(full_acc - 98.65806165706272) < 1e-10
    report = dict(seed=SEED, numpy=np.__version__, original_rows=int(counts.sum()),
                  selected_rows=kept, port_pairs=PAIRS, rows_per_pair=SELECTED_COUNT,
                  sampling="independent SRSWOR 8 of 64 in each pair; original SRSWOR 64 of N_pair",
                  weight="N_pair / 8", original_weight="N_pair / 64",
                  selected_before_values=True, historical_split="historical_1b_reviewed",
                  prospective_holdout=False, full_weighted_accuracy_pp=full_acc,
                  subset_weighted_accuracy_pp=float(population @ (subset_points / SELECTED_COUNT)
                                                    / population.sum()),
                  original_source_pin_seen_rows=source_seen,
                  subset_source_pin_seen_rows=selected_seen, inputs=provenance,
                  output=identity(output), complete_estimator_runs=0)
    (out / "subset-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "inputs"}, indent=2))


if __name__ == "__main__":
    main()
