#!/usr/bin/env python3
"""Recreate all exp705 coordinates and anchor labels from the frozen million rows."""
from pathlib import Path
import struct
import sys
import numpy as np
from replay import HERE, PAIRS, POSITIONS, graph, landing, present, read
from unpack import identity, unpack
SEED = 20261025705

def generate(work):
    unpack(work)
    BUILD = work / "generated"
    BUILD.mkdir(exist_ok=False)
    query_path = work / "query_source/anchors-source-queries.bin"
    query = np.fromfile(query_path, "<i4", offset=12).reshape(-1, 10)
    assert len(query) == 1_000_000
    mapping_path = HERE / "query_source/mapping.json"
    mapping = read(mapping_path)
    _, exists, _, _, dx, dy, _ = graph()
    smap = np.full(496, -1, "i4")
    tmap = smap.copy()
    smap[mapping["source_ids"]] = np.arange(208)
    tmap[mapping["target_ids"]] = np.arange(288)
    pair = smap[query[:, 8]] * 288 + tmap[query[:, 9]]
    assert pair.min() == 0 and pair.max() == PAIRS - 1
    same = np.all(query[:, :2] == query[:, 2:4], axis=1) & (query[:, 8] == query[:, 9])
    eligible = np.flatnonzero(~same)
    unique, where = np.unique(pair[eligible], return_index=True)
    assert np.array_equal(unique, np.arange(PAIRS))
    anchors = eligible[where]
    origin = query[anchors]
    u, v = dx[origin[:, 8]], dy[origin[:, 8]]
    ax, ay, _ = landing(origin[:, 0], origin[:, 1], u, v)
    delta = origin[:, 2:4] - np.column_stack((ax - u, ay - v))
    rows = np.repeat(origin[:, None, :], POSITIONS, axis=1)
    selected = np.zeros((PAIRS, POSITIONS), dtype=bool)
    selected[:, 0] = True
    rng = np.random.default_rng(SEED)
    xlow, xhigh = np.maximum(0, -delta[:, 0] - 14), np.minimum(119, 119 - delta[:, 0] + 14)
    ylow = np.maximum.reduce((np.zeros(PAIRS, "i4"), -delta[:, 1], -v))
    yhigh = np.minimum.reduce((np.full(PAIRS, 549, "i4"), 549 - delta[:, 1], 549 - v))
    for iteration in range(4096):
        p, slot = np.nonzero(~selected)
        if not len(p):
            break
        sx = rng.integers(xlow[p], xhigh[p] + 1)
        sy = rng.integers(ylow[p], yhigh[p] + 1)
        bx, by, _ = landing(sx, sy, u[p], v[p])
        tx, ty = bx + delta[p, 0] - u[p], by + delta[p, 1] - v[p]
        valid = present(sx, sy, exists) & present(bx, by, exists) & present(tx, ty, exists)
        valid &= (sx != tx) | (sy != ty) | (origin[p, 8] != origin[p, 9])
        proposal = np.column_stack((sx, sy, tx, ty))
        # Process slots in order so two proposals cannot enter the same group twice.
        for k in range(1, POSITIONS):
            use = np.flatnonzero(valid & (slot == k))
            distinct = ~np.any(np.all(rows[p[use], :, :4] == proposal[use, None, :], axis=2)
                               & selected[p[use]], axis=1)
            use = use[distinct]
            rows[p[use], k, :4] = proposal[use]
            selected[p[use], k] = True
    assert selected.all(), f"insufficient legal positions: {int((~selected).sum())}"
    # Labels are read only after the complete coordinate design is fixed.
    path = work / "query_source/anchors-source-components.i32"
    d0 = np.fromfile(path, "<i4").reshape(-1, 8)[:, 0]
    gold = np.full((PAIRS, POSITIONS), -2, "<i4")
    gold[:, 0] = d0[anchors]
    with (BUILD / "queries.bin").open("xb") as stream:
        stream.write(b"EX535Q01" + struct.pack("<I", rows.shape[0] * rows.shape[1]))
        stream.write(rows.astype("<i4").tobytes())
    gold.tofile(BUILD / "known.i32")
    anchors.astype("<u4").tofile(BUILD / "anchors.u32")
    delta.astype("<i4").tofile(BUILD / "delta.i32")
    for name in ("queries.bin", "known.i32", "anchors.u32", "delta.i32"):
        assert identity(BUILD/name)["sha256"] == identity(work/"data"/name)["sha256"], name
    print("All four generated inputs match frozen SHA-256; iterations:", iteration)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate_queries.py WORK_DIRECTORY")
    generate(Path(sys.argv[1]).resolve())
