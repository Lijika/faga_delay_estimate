#!/usr/bin/env python3
"""Align all exp683 exact labels with the frozen exp688 and exp728 predictions."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path

import numpy as np
from make_subset import ORIGINAL_COUNT, PAIRS, SELECTED_COUNT, SEED, identity, point, selection


def endpoint(text, ports):
    cell, port = text.split("/", 1)
    assert cell.startswith("SRB_")
    x, y = map(int, cell[4:].split("_"))
    assert 0 <= x < 120 and 0 <= y < 550
    return x, y, ports[port]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exact_directory", type=Path)
    parser.add_argument("exp688_sample", type=Path)
    parser.add_argument("exp728_sample", type=Path)
    parser.add_argument("training_requests", type=Path)
    parser.add_argument("port_json", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    base, out = args.exact_directory, args.output_directory
    out.mkdir(parents=True, exist_ok=False)
    chosen = selection()
    sources, targets = [(base / name).read_text().splitlines() for name in ("sources", "targets")]
    si, ti = {p: i for i, p in enumerate(sources)}, {p: i for i, p in enumerate(targets)}
    ports = [p["Name"] for p in json.loads(args.port_json.read_text())["Port"]]
    port_ids = {p: i for i, p in enumerate(ports)}
    assert len(si) == 208 and len(ti) == 288 and len(port_ids) == 496
    population = np.asarray(json.loads((base / "pair-populations.json").read_text()), "<u4")
    assert population.shape == (PAIRS,) and population.sum() == 1_000_000_000
    with args.training_requests.open(newline="") as stream:
        training_pins = {row["From"] for row in csv.DictReader(stream)}
    assert len(training_pins) == 960505
    inputs = {str(p): identity(p) for p in [
        base / "exact.csv", base / "positions.txt", base / "pair-populations.json",
        base / "sources", base / "targets", base / "sampling-plan.bin",
        args.exp688_sample, args.exp728_sample, args.training_requests, args.port_json,
    ]}
    assert inputs[str(args.exp688_sample)]["sha256"] == \
        "3ab7c420e59997e0c4a7f7130db175871ee2b484eb587c4def283cc038bf499b"
    assert inputs[str(args.exp728_sample)]["sha256"] == \
        "d2d720d58edd83fdf4644cdb65f1eed9acbb1b4b1d04f74cf27748e98b36fb37"
    rows = PAIRS * ORIGINAL_COUNT
    data = {
        "endpoints": np.empty((rows, 6), "<u2"),
        "input_row": np.empty(rows, "<u4"),
        "pair_id": np.empty(rows, "<u2"),
        "rank": np.empty(rows, "u1"),
        "exact_delay": np.empty(rows, "<i4"),
        "exp688_prediction": np.empty(rows, "<i4"),
        "exp728_prediction": np.empty(rows, "<i4"),
        "source_pin_seen_in_training": np.empty(rows, "u1"),
    }
    counts = np.zeros(PAIRS, "<u4")
    sums, subset_sums = np.zeros((2, PAIRS)), np.zeros((2, PAIRS))
    output = out / "exp728-exact-subset.csv.gz"
    kept, changed = 0, 0
    with (base / "exact.csv").open(newline="") as truth, \
            args.exp688_sample.open(newline="") as old, \
            args.exp728_sample.open(newline="") as new, \
            (base / "positions.txt").open() as positions, output.open("xb") as raw:
        exact_reader, old_reader, new_reader = map(csv.reader, (truth, old, new))
        assert next(exact_reader) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        assert next(old_reader) == next(new_reader) == ["row", "From", "To", "delay"]
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, \
                io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
            writer = csv.writer(text, lineterminator="\n")
            writer.writerow(["sample_index", "input_row", "pair_id", "rank_within_original_64",
                "From", "To", "exact_delay", "exp688_prediction", "exp728_prediction",
                "population_pair_rows", "sample_weight", "original_sample_weight",
                "split", "source_pin_seen_in_training"])
            previous = -1
            for i, label in enumerate(exact_reader):
                assert i < rows
                a, b = next(old_reader), next(new_reader)
                row = int(next(positions))
                assert int(label[0]) == i and int(a[0]) == int(b[0]) == row and row > previous
                assert label[1:3] == a[1:3] == b[1:3]
                pair = si[label[1].split("/", 1)[1]] * 288 + ti[label[2].split("/", 1)[1]]
                rank = int(counts[pair])
                assert rank < ORIGINAL_COUNT
                counts[pair] += 1
                sx, sy, sp = endpoint(label[1], port_ids)
                tx, ty, tp = endpoint(label[2], port_ids)
                exact, p688, p728 = int(label[3]), int(a[3]), int(b[3])
                assert min(exact, p688, p728) >= 0
                seen = label[1] in training_pins
                for key, value in dict(endpoints=(sx, sy, sp, tx, ty, tp), input_row=row,
                    pair_id=pair, rank=rank, exact_delay=exact, exp688_prediction=p688,
                    exp728_prediction=p728, source_pin_seen_in_training=seen).items():
                    data[key][i] = value
                scores = np.array([point(p688, exact), point(p728, exact)])
                sums[:, pair] += scores
                changed += p688 != p728
                if chosen[pair, rank]:
                    writer.writerow([i, row, pair, rank, *label[1:3], exact, p688, p728,
                        int(population[pair]), population[pair] / SELECTED_COUNT,
                        population[pair] / ORIGINAL_COUNT, "historical_1b_reviewed", int(seen)])
                    subset_sums[:, pair] += scores
                    kept += 1
                previous = row
            assert i + 1 == rows
            assert next(old_reader, None) is next(new_reader, None) is next(positions, None) is None
    assert np.all(counts == ORIGINAL_COUNT) and kept == PAIRS * SELECTED_COUNT
    accuracy = sums @ population / ORIGINAL_COUNT / population.sum()
    assert np.allclose(accuracy, [98.65806165706269, 98.6448996487895], rtol=0, atol=1e-10)
    outputs = [dict(path=output.name, **identity(output))]
    for start in (0, rows // 2):
        path = out / f"exact-records-{start // (rows // 2):02d}.npz"
        np.savez_compressed(path, **{k: v[start:start + rows // 2] for k, v in data.items()})
        outputs.append(dict(path=path.name, start_index=start, rows=rows // 2, **identity(path)))
    mapping = dict(ports=ports, sources=sources, targets=targets,
                   population_pair_rows=population.tolist(),
                   endpoint_columns=["source_x", "source_y", "source_port_id",
                                     "target_x", "target_y", "target_port_id"])
    (out / "record-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    outputs.append(dict(path="record-mapping.json", **identity(out / "record-mapping.json")))
    report = dict(rows=rows, selected_rows=kept, port_pairs=PAIRS, full_samples_per_pair=64,
        subset_samples_per_pair=8, subset_seed=SEED, selected_before_values=True,
        split="historical_1b_reviewed", prospective_holdout=False, full_weight="N_pair/64",
        subset_weight="N_pair/8", exact_delay_unit="ps",
        full_accuracy_pp=dict(zip(("exp688", "exp728"), accuracy.tolist())),
        subset_accuracy_pp=dict(zip(("exp688", "exp728"),
            (subset_sums @ population / SELECTED_COUNT / population.sum()).tolist())),
        changed_rows=changed, full_source_pin_seen_rows=int(data["source_pin_seen_in_training"].sum()),
        prediction728_sample_origin="exp722; exp722/725/728 complete output SHA identical",
        inputs=inputs, outputs=outputs, numpy=np.__version__, complete_estimator_runs=0)
    (out / "records-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("inputs", "outputs")}, indent=2))


if __name__ == "__main__":
    main()
