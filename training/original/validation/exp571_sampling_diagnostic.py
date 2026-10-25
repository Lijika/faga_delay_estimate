#!/usr/bin/env python3
"""Compare complete development requests with uniform geometry training weights."""
import os
from pathlib import Path
import resource
import socket

import numpy as np

import exp557_evaluate as previous


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp571")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    root = Path("validation/results/exp571-sampling")
    root.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    source = Path("../exp570/validation/results/exp570-recovery-01/input.json")
    inputs = previous.read(source)
    assert inputs["unique_rows"] == 1_000_000 and inputs["pairs"] == 59904
    for item in inputs["records"]:
        previous.real.check(Path(item["path"]), item)
    queries = np.fromfile("../exp554/build/exp554/queries.bin", "<i4", offset=12).reshape(-1, 10)
    events = np.fromfile("../exp536/build/exp536/events.i32", "<i4").reshape(-1, 9)
    ports = np.fromfile("../exp554/build/exp554/ports.i32", "<i4").reshape(-1, 2)
    folds = np.fromfile("../exp554/build/exp554/folds.u8", "u1")
    assert len(queries) == len(events) == len(ports) == len(folds) == 1_000_000
    pair = ports[:, 0] * 288 + ports[:, 1]
    for k in range(3):
        for mask in (folds == k, folds != k):
            assert np.bincount(pair[mask], minlength=59904).min() > 0
    x, y = queries[:, 2] - events[:, 0] + events[:, 2], queries[:, 3] - events[:, 1] + events[:, 3]
    ax, ay = np.abs(x), np.abs(y)
    assert (ax <= 119).all() and (ay <= 549).all()
    column = (((((2 * (x < 0) + (y < 0)) * 10 + ax % 10) * 12 + ay % 12) * 12 + ax // 10) * 46 + ay // 12)
    keys = np.fromfile("../exp570/build/exp570-recovery-01/keys.i32", "<i4").reshape(-1, 2)
    assert np.array_equal(keys, np.column_stack((pair, column)))
    counts = np.bincount(column, minlength=264960)
    all_columns = np.arange(264960)
    uniform_q = all_columns % 46 + all_columns // 46 % 12
    request_q = ax // 10 + ay // 12
    assert np.array_equal(request_q, uniform_q[column])
    uniform_band = np.searchsorted([1, 4, 16], uniform_q, side="right")
    request_band = np.searchsorted([1, 4, 16], request_q, side="right")
    uniform_counts, request_counts = np.bincount(uniform_band), np.bincount(request_band)
    uniform_fraction, request_fraction = uniform_counts / 264960., request_counts / 1_000_000.
    previous.write(root / "diagnostic.json", dict(rows=1_000_000, port_pairs=59904,
        all_folds_and_complements_full_port=True, geometry_keys_in_requests=int(np.count_nonzero(counts)),
        total_geometry_keys=264960, maximum_key_rows=int(counts.max()),
        uniform_geometry_counts=uniform_counts.tolist(), request_counts=request_counts.tolist(),
        uniform_fractions=uniform_fraction.tolist(), request_fractions=request_fraction.tolist(),
        request_to_uniform_ratio=(request_fraction / uniform_fraction).tolist(),
        total_variation_over_geometry_keys=float(.5 * np.abs(counts / 1_000_000. - 1 / 264960.).sum()),
        input=previous.identity(source), keys=previous.identity("../exp570/build/exp570-recovery-01/keys.i32"),
        source=previous.identity(Path(__file__)), model_changes=0, model_reruns=0,
        development_distribution_only=True, independent_requests_used=0))
    print("EXP571_FULL_PORT_SAMPLING_DIAGNOSTIC", request_counts.tolist(), flush=True)


if __name__ == "__main__":
    main()
