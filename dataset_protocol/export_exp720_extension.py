#!/usr/bin/env python3
"""Export the one additional historical request set excluded by exp720."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from export_exclusions import pin_id, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research_root", type=Path)
    parser.add_argument("new_directory", type=Path)
    args = parser.parse_args()
    root, out = args.research_root.resolve(), args.new_directory
    out.mkdir(parents=True, exist_ok=False)
    freeze = json.loads((root / "exp720/validation/results/exp720/freeze.json").read_text())
    expected = json.loads((root / "exp720/validation/results/exp720/100m-input.json").read_text())
    added = root / "exp685/build/exp685/expanded/sample-requests.csv"
    record = next(r for r in freeze["history"]
                  if (root / "exp720" / r["path"]).resolve() == added)
    assert added.stat().st_size == record["bytes"] and sha256(added) == record["sha256"]
    port_path = root / "exp652/doc/eda比赛文件/arch/SRB_Port.json"
    ports = {p["Name"]: i for i, p in enumerate(json.loads(port_path.read_text())["Port"])}
    with (root / "exp501/build/exp501/u-role/requests.csv").open(newline="") as stream:
        training = {pin_id(r["From"], ports) for r in csv.DictReader(stream)}
    keys = set()
    with added.open(newline="") as stream:
        for r in csv.DictReader(stream):
            source = pin_id(r["From"], ports)
            assert source not in training
            keys.add((source << 32) | pin_id(r["To"], ports))
    assert len(training) == 960505 and len(keys) == 1916928
    assert expected["historical_pairs_after_source_filter"] == 20391557 + len(keys)
    np.savez_compressed(out / "exp720-additional.npz", keys=np.array(sorted(keys), "<u8"))
    path = out / "exp720-additional.npz"
    report = dict(protocol="exp720", original_exp685_pairs=20391557, added_pairs=len(keys),
        combined_pairs=expected["historical_pairs_after_source_filter"], source_pin_overlap=0,
        original_input=record, output=dict(path=path.name, bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
        labels_included=False, complete_estimator_runs=0)
    (out / "exp720-extension.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
