#!/usr/bin/env python3
"""Freeze a small reachability audit across all endpoint ports and gap geometry."""
import csv
import json
import random
from pathlib import Path

import numpy as np

root = Path("build/hidden-suite-v1")
report = json.loads((root / "independent/geometry.json").read_text())
ports = report["ports"]
with (root / "independent/eligibility.bin").open("rb") as handle:
    assert handle.read(8) == b"HEQUAL01"
    cells = np.frombuffer(handle.read(60200 * 4), dtype="<u4").copy()
    source = np.frombuffer(handle.read(60200 * 496), dtype="u1").reshape(60200, 496).copy()
    target = np.frombuffer(handle.read(60200 * 496), dtype="u1").reshape(60200, 496).copy()
    direct = np.frombuffer(handle.read(496 * 496), dtype="u1").reshape(496, 496).copy()
    assert handle.read() == b""
tile_at = {int(c): i for i, c in enumerate(cells)}
sources, targets = report["from_port_ids"], report["to_port_ids"]
rng = random.Random(2026101601)
rows = []


def pin(t, p):
    return f"SRB_{int(cells[t]) % 120}_{int(cells[t]) // 120}/{ports[p]['Name']}"


def add(kind, ft, fp, tt, tp, plain):
    reach = bool(source[ft, fp] and target[tt, tp]) or (ft == tt and bool(direct[fp, tp] or fp == tp))
    rows.append((kind, pin(ft, fp), pin(tt, tp), "", int(plain), int(reach)))


for i, fp in enumerate(sources):
    ft, tt = rng.randrange(60200), rng.randrange(60200)
    add("all-source", ft, fp, tt, targets[i % len(targets)], i % 32 == 0)
for i, tp in enumerate(targets):
    ft, tt = rng.randrange(60200), rng.randrange(60200)
    add("all-target", ft, sources[i % len(sources)], tt, tp, i % 32 == 0)
# Includes coordinates at every chip edge and each side of the Block column.
points = [(16, 0), (119, 0), (0, 100), (0, 549), (119, 549), (75, 0), (90, 0),
          (75, 49), (90, 49), (76, 50), (89, 50), (75, 99), (90, 99),
          (76, 150), (89, 150), (75, 549), (90, 549), (57, 249), (58, 250)]
for i, (x, y) in enumerate(points):
    ft = tile_at[y * 120 + x]
    for j in range(4):
        tt = tile_at[points[(i + j + 1) % len(points)][1] * 120 + points[(i + j + 1) % len(points)][0]]
        add("geometry", ft, sources[(i * 13 + j) % len(sources)], tt,
            targets[(i * 17 + j) % len(targets)], j == 0)
for p in [p for p in sources if ports[p]["Name"][0] in "AS"]:
    candidates = [t for t in targets if direct[p, t]]
    assert candidates
    ft = tile_at[0 * 120 + 16]
    add("local-direct", ft, p, ft, rng.choice(candidates), True)
for p in sources:
    invalid = np.flatnonzero(source[:, p] == 0)
    if len(invalid):
        add("dead-source", int(invalid[0]), p, tile_at[300 * 120 + 60],
            targets[len(rows) % len(targets)], len(rows) % 32 == 0)
for p in targets:
    invalid = np.flatnonzero(target[:, p] == 0)
    if len(invalid):
        add("dead-target", tile_at[300 * 120 + 60], sources[len(rows) % len(sources)],
            int(invalid[0]), p, len(rows) % 32 == 0)
with (root / "reach-exact-rows.csv").open("x", newline="") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["kind", "from", "to", "label", "plain_check", "expected_reachable"])
    writer.writerows(rows)
print(json.dumps({"rows": len(rows), "plain_checks": sum(r[4] for r in rows),
                  "expected_unreachable": sum(not r[5] for r in rows)}))
