#!/usr/bin/env python3
"""Export lossless training inputs using the original exp679 dataset loader."""
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np


def identity(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return dict(path=str(path), bytes=Path(path).stat().st_size, sha256=digest.hexdigest())


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_training.py HISTORICAL_RESEARCH_ROOT NEW_OUTPUT_DIRECTORY")
    root, output = (Path(p).resolve() for p in sys.argv[1:])
    output.mkdir(parents=True, exist_ok=False)
    os.chdir(root / "exp679")
    sys.path.insert(0, str(Path("validation").resolve()))
    import exp679_hv_cli as original
    data, features, event = original.dataset()
    assert np.array_equal(features, features.astype("<i2"))
    assert features.shape == (1_000_000, 71)
    for name, cols in (("features53", slice(0, 53)), ("features_extra18", slice(53, 71))):
        np.savez_compressed(output / (name + ".npz"), features=features[:, cols].astype("<i2"))
    with np.load("../exp623/build/exp623/data.npz") as q4, \
            np.load("../exp593/build/exp593/targets.npz") as target:
        assert np.array_equal(q4["truth"], data["truth"])
        assert np.array_equal(q4["folds"], data["folds"])
        values = {name: data[name] for name in
                  ("truth", "d0", "mandatory", "folds", "clusters", "pair", "routes")}
        values.update(base_q4=q4["base"], base_curve=data["base"],
                      base_d64=target["D64"], event=event)
        np.savez_compressed(output / "targets_splits.npz", **values)
    checks = []
    for fold in range(3):
        heldout, learn = data["folds"] == fold, data["folds"] != fold
        assert np.intersect1d(data["clusters"][heldout], data["clusters"][learn]).size == 0
        assert np.unique(data["pair"][heldout]).size == np.unique(data["pair"][learn]).size == 59904
        checks.append(dict(fold=fold, rows=int(heldout.sum()),
                           source_pin_overlap=0, port_pairs=59904))
    source_paths = [
        "../exp585/build/exp585/training.npz", "../exp593/build/exp593/targets.npz",
        "../exp623/build/exp623/data.npz", "../exp615/build/exp615/keys.bin",
        "../exp619/build/exp619/Q4.p4", "../exp654/build/exp654/D64.curves.u8",
        "../exp579/build/exp579/queries.bin", "../exp679/validation/exp679_hv_cli.py",
    ]
    report = dict(rows=len(features), numpy=np.__version__, feature_columns=71,
                  lossless_integer_features=True, feature_min=int(features.min()),
                  feature_max=int(features.max()), folds=checks,
                  event_counts=np.bincount(event, minlength=3).tolist(),
                  target_s8="d0 - base_q4", target_v8="d0 - base_curve",
                  training_weight="1000 / max(d0 + mandatory, 128)",
                  historical_development_data=True, full_estimator_runs=0,
                  inputs=[identity(Path(p)) for p in source_paths],
                  outputs=[identity(p) for p in sorted(output.glob("*.npz"))])
    (output / "export-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
