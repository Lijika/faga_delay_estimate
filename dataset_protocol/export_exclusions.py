#!/usr/bin/env python3
"""Encode exp685's historical exclusions losslessly, without carrying labels."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def pin_id(pin, ports):
    cell, port = pin.split("/", 1)
    x, y = map(int, cell[4:].split("_"))
    assert cell.startswith("SRB_") and 0 <= x < 120 and 0 <= y < 550
    return (y * 120 + x) * 496 + ports[port]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_exclusions.py HISTORICAL_RESEARCH_ROOT NEW_OUTPUT_DIRECTORY")
    root, out = (Path(p).resolve() for p in sys.argv[1:])
    out.mkdir(parents=True, exist_ok=False)
    base = root / "exp685"
    freeze = json.loads((base / "validation/results/exp685/freeze.json").read_text())
    expected = json.loads((base / "validation/results/exp685/100m-input.json").read_text())
    arch = root / "exp679/doc/eda比赛文件/arch/SRB_Port.json"
    ports = {p["Name"]: i for i, p in enumerate(json.loads(arch.read_text())["Port"])}
    train = root / "exp501/build/exp501/u-role/requests.csv"
    with train.open(newline="") as stream:
        source_ids = {pin_id(r["From"], ports) for r in csv.DictReader(stream)}
    assert len(source_ids) == expected["training_source_pins"]
    keys = set()
    checked = []
    for item in freeze["history"]:
        path = (base / item["path"]).resolve()
        assert path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"], path
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", newline="") as stream:
            reader = csv.DictReader(stream)
            a, b = ("From", "To") if "From" in reader.fieldnames else ("from", "to")
            for row in reader:
                source = pin_id(row[a], ports)
                if source not in source_ids:
                    keys.add((source << 32) | pin_id(row[b], ports))
        checked.append(item)
        print("checked", item["path"], "unique keys", len(keys), flush=True)
    assert len(keys) == expected["historical_pairs_after_source_filter"]
    np.savez_compressed(out / "training-source-pins.npz", ids=np.array(sorted(source_ids), "<u4"))
    array = np.array(sorted(keys), "<u8")
    for start in range(0, len(array), 2_000_000):
        np.savez_compressed(out / f"history-{start // 2_000_000:02d}.npz",
                            keys=array[start:start + 2_000_000])
    report = dict(source_pins=len(source_ids), history_pairs=len(keys),
                  lossless_encoding="pin=(y*120+x)*496+port_id; key=(source<<32)|target",
                  source_port_order_sha256=sha256(arch), history_inputs=checked,
                  outputs=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha256(p))
                           for p in sorted(out.glob("*.npz"))],
                  labels_included=False, complete_estimator_runs=0)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("EXCLUSION_EXPORT_COMPLETE", len(keys), flush=True)


if __name__ == "__main__":
    main()
