#!/usr/bin/env python3
"""Replay every original word at all four sites; compare every saved cross record."""
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from unpack import identity, unpack
HERE = Path(__file__).resolve().parent
PAIRS, POSITIONS = 59904, 4
ARCH = HERE / "solver/no-line-arch"
def read(path):
    return json.loads(Path(path).read_text())
def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")

def graph():
    names = [p["Name"] for p in read(ARCH / "SRB_Port.json")["Port"]]
    ids = {name: i for i, name in enumerate(names)}
    exists = np.zeros((550, 120), dtype=bool)
    for inst in read(ARCH / "SRB_Inst.json")["Inst"]:
        exists[inst["y"], inst["x"]] = True
    arcs = np.full((len(names), len(names)), -1, dtype="i4")
    np.fill_diagonal(arcs, 0)
    for arc in read(ARCH / "SRB_Arc.json")["Arcs"]:
        p, q, fee = ids[arc["from"]], ids[arc["to"]], arc["delay"]
        arcs[p, q] = fee if arcs[p, q] < 0 else min(arcs[p, q], fee)
    nets = {ids[n["from"]]: n for n in read(ARCH / "SRB_Net.json")["Nets"]}
    z = np.asarray(sorted(nets), dtype="i4")
    dx = np.zeros(len(names), dtype="i4")
    dy = dx.copy()
    dest = np.full(len(names), -1, dtype="i4")
    for p, net in nets.items():
        dx[p], dy[p], dest[p] = net["delta x"], net["delta y"], ids[net["to"]]
    assert len(z) == 160 and not any(g["delay"] for g in read(ARCH / "SRB_Gap.json")["Gap"]["Line"])
    return names, exists, arcs, z, dx, dy, dest

def present(x, y, exists):
    inside = (x >= 0) & (x < 120) & (y >= 0) & (y < 550)
    result = np.zeros(x.shape, dtype=bool)
    result[inside] = exists[y[inside], x[inside]]
    return result

def landing(x, y, u, v):
    compressed = x - 14 * ((y % 100 < 50) & (x >= 90))
    step = compressed + u
    bx = np.where(u != 0, step + 14 * ((y % 100 < 50) & (step >= 76)), x)
    by = y + v
    return bx, by, 292 * (bx - x != u)

def analyze():
    report = read(HERE / "original/trace.json")
    query = np.fromfile(BUILD / "queries.bin", "<i4", offset=12).reshape(-1, 10)
    lengths = np.fromfile(BUILD / "paths.lengths.u32", "<u4")
    words = np.fromfile(BUILD / "paths.words.u8", "u1")
    sums = np.fromfile(BUILD / "paths.summary.i32", "<i4").reshape(-1, 8)
    assert len(lengths) == len(query) and lengths.sum() == len(words) == report["hops"]
    assert np.all(sums[:, 1] == 0) and np.array_equal(sums[:, 5], lengths)
    names, exists, arcs, z, dx, dy, dest = graph()
    assert z.tolist() == report["z_ports"] and [names[p] for p in z] == report["z_names"]
    offsets = np.r_[0, np.cumsum(lengths, dtype="i8")]
    answer = sums[:, 0] + sums[:, 2]
    known = np.fromfile(BUILD / "known.i32", "<i4")
    assert np.array_equal(answer[known >= 0], known[known >= 0])
    ax, ay, fee = landing(query[:, 0], query[:, 1], dx[query[:, 8]], dy[query[:, 8]])
    delta = query[:, 2:4] - np.column_stack((ax - dx[query[:, 8]], ay - dy[query[:, 8]]))
    expected_delta = np.fromfile(BUILD / "delta.i32", "<i4").reshape(PAIRS, 2)
    assert np.array_equal(delta.reshape(PAIRS, POSITIONS, 2),
                          np.repeat(expected_delta[:, None, :], POSITIONS, axis=1))
    normalized = (answer - fee).reshape(PAIRS, POSITIONS)
    spread = np.ptp(normalized, axis=1)
    records = []
    for source_slot in range(POSITIONS):
        for target_slot in range(POSITIONS):
            source = np.arange(PAIRS) * POSITIONS + source_slot
            target = np.arange(PAIRS) * POSITIONS + target_slot
            x, y, port = [query[target, col].copy() for col in (0, 1, 8)]
            arc_cost, block_cost = np.zeros(PAIRS, "i4"), np.zeros(PAIRS, "i4")
            reason, bad_step = np.zeros(PAIRS, "i4"), np.full(PAIRS, -1, "i4")
            for depth in range(int(lengths[source].max())):
                active = np.flatnonzero((reason == 0) & (lengths[source] > depth))
                codes = words[offsets[source[active]] + depth]
                out = z[codes]
                arc = arcs[port[active], out]
                assert np.all(arc >= 0)
                bx, by, block = landing(x[active], y[active], dx[out], dy[out])
                inside = (bx >= 0) & (bx < 120) & (by >= 0) & (by < 550)
                valid = present(bx, by, exists)
                failed = active[~valid]
                reason[failed] = np.where(inside[~valid], 2, 1)
                bad_step[failed] = depth
                good = active[valid]
                arc_cost[good] += arc[valid]
                block_cost[good] += block[valid]
                x[good], y[good], port[good] = bx[valid], by[valid], dest[out[valid]]
            active = np.flatnonzero(reason == 0)
            arc = arcs[port[active], query[target[active], 9]]
            assert np.all(arc >= 0)
            arc_cost[active] += arc
            aligned = (x == query[target, 2]) & (y == query[target, 3])
            reason[(reason == 0) & ~aligned] = 3
            cost = arc_cost + block_cost
            valid = reason == 0
            assert np.all(cost[valid] >= answer[target[valid]])
            if source_slot == target_slot:
                assert valid.all() and np.array_equal(cost, answer[target])
                assert np.array_equal(arc_cost, sums[source, 0])
                assert np.array_equal(block_cost, sums[source, 2])
            uphill = normalized[:, source_slot] < normalized[:, target_slot]
            unchanged = valid & ((cost - fee[target]) == normalized[:, source_slot])
            assert not np.any(uphill & unchanged)
            reason[valid & ((cost - fee[target]) != normalized[:, source_slot])] = 4
            records.append(np.column_stack((reason, bad_step, x, y, cost,
                cost - answer[target], uphill)).astype("<i4"))
    cross = np.stack(records, axis=1)
    assert np.array_equal(cross, np.fromfile(BUILD / "cross.i32", "<i4").reshape(PAIRS,16,7))
    cross.tofile(ROOT / "cross.i32")
    assert np.array_equal(normalized, np.fromfile(BUILD / "normalized.i32", "<i4").reshape(PAIRS,4))
    normalized.astype("<i4").tofile(ROOT / "normalized.i32")
    def describe(mask):
        values = spread[mask]
        r = cross[mask]
        uphill = r[:, :, 6].astype(bool)
        causes = np.bincount(r[:, :, 0][uphill], minlength=5)
        return dict(pairs=int(mask.sum()), range_quantiles_ps=np.quantile(
            values, [0, .25, .5, .75, .9, .95, .99, 1]).tolist(),
            changed_pairs=int((values > 0).sum()), range_ge20_pairs=int((values >= 20).sum()),
            uphill_transfers=int(uphill.sum()), uphill_reason_counts=causes.tolist(),
            legal_same_endpoint_transfers=int(np.isin(r[:, :, 0], [0, 4]).sum()))
    full = describe(np.ones(PAIRS, dtype=bool))
    counts = np.asarray(full["uphill_reason_counts"])
    primary = int(counts.argmax()) if counts.sum() else None
    groups = {}
    anchor = query[::POSITIONS]
    for name, values in dict(source_family=anchor[:, 4],
            direction=2 * (expected_delta[:, 0] < 0) + (expected_delta[:, 1] < 0),
            distance=np.searchsorted([24, 100, 300], abs(expected_delta).sum(axis=1))).items():
        groups[name] = {str(int(v)): describe(values == v) for v in np.unique(values)}
    write(ROOT / "groups.json", groups)
    write(ROOT / "report.json", dict(all_checks_passed=True, full=full,
        position_research_gate=full["range_ge20_pairs"] >= .05 * PAIRS,
        dominant_reason=primary if counts.sum() and counts[primary] >= .5 * counts.sum() else None,
        reason_names=["unchanged_valid", "outside_chip", "missing_tile", "changed_endpoint", "changed_fee"],
        cross_axes=["pair", "source_slot*4+target_slot", "column"],
        cross_columns=["reason", "first_invalid_step", "final_x", "final_y", "cost",
                       "cost_minus_target_D0", "uphill"],
        full_port_pairs=PAIRS, positions=POSITIONS, rows=PAIRS * POSITIONS,
        known_anchor_labels_verified=PAIRS, new_exact_positions=3 * PAIRS,
        complete_estimator_runs=0, new_training_runs=0, generalization_claim=False,
        files=[identity(p) for p in (BUILD / "paths.lengths.u32", BUILD / "paths.words.u8",
            BUILD / "paths.summary.i32", BUILD / "cross.i32", BUILD / "normalized.i32")],
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP705_ANALYSIS_COMPLETE", full, flush=True)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: replay.py NEW_WORK_DIRECTORY")
    work = Path(sys.argv[1]).resolve()
    unpack(work)
    BUILD, ROOT = work / "data", work / "replay"
    ROOT.mkdir(exist_ok=False)
    analyze()
    expected, actual = read(HERE / "original/report.json"), read(ROOT / "report.json")
    assert actual["full"] == expected["full"]
    assert read(ROOT / "groups.json") == read(HERE / "original/groups.json")
    print("All 958464 cross records and frozen group statistics match.")
