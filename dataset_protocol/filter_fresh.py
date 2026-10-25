#!/usr/bin/env python3
"""Apply the exp685 or exp720 exclusion sets to a frozen 120M U-role proposal."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from export_exclusions import pin_id

HERE = Path(__file__).resolve().parent


def accept(source, target, blocked_sources, blocked_pairs):
    if source in blocked_sources:
        return 1
    if (source << 32) | target in blocked_pairs:
        return 2
    return 0


def filter_stream(source, target, blocked_sources, blocked_pairs, ports,
                  source_roles, target_roles, wanted):
    si = {p: i for i, p in enumerate(source_roles)}
    ti = {p: i for i, p in enumerate(target_roles)}
    population, rejected = [0] * (len(si) * len(ti)), [0, 0, 0]
    reader, writer = csv.reader(source), csv.writer(target, lineterminator="\n")
    assert next(reader) == ["From", "To"]
    writer.writerow(["From", "To"])
    accepted, visited = 0, 0
    for a, b in reader:
        visited += 1
        reason = accept(pin_id(a, ports), pin_id(b, ports), blocked_sources, blocked_pairs)
        if reason:
            rejected[reason] += 1
            continue
        population[si[a.split("/", 1)[1]] * len(ti) + ti[b.split("/", 1)[1]]] += 1
        writer.writerow([a, b])
        accepted += 1
        if accepted == wanted:
            break
    assert accepted == wanted
    return population, dict(accepted=accepted, visited_proposal_rows=visited,
                            rejected_source_rows=rejected[1], rejected_history_rows=rejected[2],
                            rows=accepted, independent_uniqueness_check_required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal_csv", type=Path)
    parser.add_argument("new_output_directory", type=Path)
    parser.add_argument("--protocol", choices=("exp685", "exp720"), default="exp720")
    args = parser.parse_args()
    assert [accept(1, 2, {1}, {(3 << 32) | 4}), accept(3, 4, {1}, {(3 << 32) | 4}),
            accept(3, 5, {1}, {(3 << 32) | 4})] == [1, 2, 0]
    data = HERE / "exclusions"
    manifest = json.loads((data / "manifest.json").read_text())
    for r in manifest["outputs"]:
        path = data / r["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"], path
    with np.load(data / "training-source-pins.npz") as packed:
        sources = set(map(int, packed["ids"]))
    known = set()
    for path in sorted(data.glob("history-*.npz")):
        with np.load(path) as packed:
            known.update(map(int, packed["keys"]))
    assert len(sources) == manifest["source_pins"] and len(known) == manifest["history_pairs"]
    if args.protocol == "exp720":
        extension = json.loads((data / "exp720-extension.json").read_text())
        record = extension["output"]
        path = data / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        with np.load(path) as packed:
            added = set(map(int, packed["keys"]))
        assert len(added) == extension["added_pairs"] and known.isdisjoint(added)
        assert not any((key >> 32) in sources for key in added)
        known.update(added)
        assert len(known) == extension["combined_pairs"]
    port_path = HERE.parent / "source/arch/SRB_Port.json"
    assert hashlib.sha256(port_path.read_bytes()).hexdigest() == manifest["source_port_order_sha256"]
    ports = {p["Name"]: i for i, p in enumerate(json.loads(port_path.read_text())["Port"])}
    mapping = json.loads((HERE.parent / "path_witness/query_source/mapping.json").read_text())
    args.new_output_directory.mkdir(parents=True, exist_ok=False)
    with args.proposal_csv.open(newline="") as source, \
            (args.new_output_directory / "requests.csv").open("x", newline="") as target:
        population, report = filter_stream(source, target, sources, known, ports,
                                          mapping["sources"], mapping["targets"], 100_000_000)
    assert min(population) >= 32
    report["protocol"] = args.protocol
    (args.new_output_directory / "pair-populations.json").write_text(json.dumps(population) + "\n")
    (args.new_output_directory / "filter-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
