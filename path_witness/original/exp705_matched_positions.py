#!/usr/bin/env python3
"""Hold the complete nominal key fixed and replay optimal words at four sites."""
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp686/validation").resolve()))
import exp686_event_boundary as prior

read, write, identity, check, speed = prior.read, prior.write, prior.identity, prior.check, prior.speed
ROOT, BUILD = Path("validation/results/exp705"), Path("build/exp705")
PLAN = Path("experiment/实验705-固定名义键的全端口位置配对与路径交叉重放.md")
ARCH = Path("../exp553/build/exp553/no-line-arch")
PAIRS, POSITIONS, SEED = 59904, 4, 20261025705
speed.ROOT = ROOT


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


def derive_tracer(text):
    def change(old, new):
        nonlocal text
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    change('#include "../build/exp552/trace/scaffold.cpp"',
           '#include "' + str(Path("../exp552/build/exp552/trace/scaffold.cpp").resolve()) + '"')
    change("gold[i] < 0)", "(gold[i] < 0 && gold[i] != -2))")
    change("if (answer != gold[i])", "if (answer < 0 || (gold[i] != -2 && answer != gold[i]))")
    return text


def prepare():
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    files = []
    for record in read("../exp553/validation/results/exp553/architecture.json")["files"]:
        files.append(check(Path("../exp553") / record["ablated"]["path"], record["ablated"]))
    query_id = read("../exp535/validation/results/exp535/input.json")["queries"]
    query_path = Path("../exp535") / query_id["path"]
    files.append(check(query_path, query_id))
    query = np.fromfile(query_path, "<i4", offset=12).reshape(-1, 10)
    assert len(query) == 1_000_000
    mapping_path = Path("../exp500/validation/results/exp500-preparation/mapping.json")
    mapping = read(mapping_path)
    files.append(identity(mapping_path))
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
    old = read("../exp553/validation/results/exp553/report.json")["components"]
    path = Path("../exp553") / old["path"]
    files.append(check(path, old))
    d0 = np.fromfile(path, "<i4").reshape(-1, 8)[:, 0]
    gold = np.full((PAIRS, POSITIONS), -2, "<i4")
    gold[:, 0] = d0[anchors]
    with (BUILD / "queries.bin").open("xb") as stream:
        stream.write(b"EX535Q01" + struct.pack("<I", rows.shape[0] * rows.shape[1]))
        stream.write(rows.astype("<i4").tobytes())
    gold.tofile(BUILD / "known.i32")
    anchors.astype("<u4").tofile(BUILD / "anchors.u32")
    delta.astype("<i4").tofile(BUILD / "delta.i32")
    old_trace = read("../exp552/validation/results/exp552/freeze.json")
    for record in old_trace["files"]:
        if record["path"].startswith("build/exp552/trace/"):
            files.append(check(Path("../exp552") / record["path"], record))
    tracer = Path("../exp552/tests/exp552_real_paths.cpp")
    files.append(identity(tracer))
    target = BUILD / "trace.cpp"
    target.write_text(derive_tracer(tracer.read_text()))
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
        "-Wno-unused-function", "-static", "-s", "-march=x86-64", "-mtune=generic",
        "-ffp-contract=off", str(target)]
    command += [str(Path("../exp552/build/exp552/trace/src") / p)
                for p in ("architecture.cpp", "router.cpp", "residue_estimator.cpp")]
    command += ["-o", str(BUILD / "trace")]
    speed.measured(command, "compile")
    assert not (ROOT / "compile.stderr").read_bytes()
    speed.measured([str(BUILD / "trace"), "--help"], "help")
    orbit_id = read("../exp552/validation/results/exp552/trace-freeze.json")["orbit"]
    orbit = Path("../exp501/build/exp501/tools/orbit.i16")
    files.append(check(orbit, orbit_id))
    files += [identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md", target,
        BUILD / "queries.bin", BUILD / "known.i32", BUILD / "anchors.u32", BUILD / "delta.i32")]
    write(ROOT / "freeze.json", dict(files=files, binary=identity(BUILD / "trace"),
        orbit=identity(orbit), rows=PAIRS * POSITIONS, pair_groups=PAIRS, positions=POSITIONS,
        anchor_rows=PAIRS, new_position_rows=3 * PAIRS, proposal_iterations=iteration,
        seed=SEED, label_independent_design=True, disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP705_PREPARED", PAIRS * POSITIONS, iteration, flush=True)


def trace():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"] + [frozen["binary"], frozen["orbit"]]:
        check(item["path"], item)
    resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))
    resource.setrlimit(resource.RLIMIT_AS, (3_000_000_000, 3_000_000_000))
    result = speed.measured([frozen["binary"]["path"], str(ARCH), str(BUILD / "queries.bin"),
        str(BUILD / "known.i32"), frozen["orbit"]["path"], str(BUILD / "paths")], "trace")
    assert result["threads"] == 1 and result["cpu_s"] <= 1800 and result["rss_bytes"] <= 3_000_000_000
    assert not (ROOT / "trace.stderr").read_bytes()
    report = json.loads((ROOT / "trace.stdout").read_text().splitlines()[-1])
    assert report["complete"] and report["rows"] == PAIRS * POSITIONS and report["pairs"] == PAIRS
    write(ROOT / "trace.json", report)
    print("EXP705_EXACT_COMPLETE", result["cpu_s"], flush=True)


def analyze():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"]:
        check(item["path"], item)
    report = read(ROOT / "trace.json")
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
    cross.tofile(BUILD / "cross.i32")
    normalized.astype("<i4").tofile(BUILD / "normalized.i32")
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
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp705")
    assert os.environ["OPENBLAS_NUM_THREADS"] == os.environ["OMP_NUM_THREADS"] == "1"
    assert sys.argv[1:] in (["prepare"], ["trace"], ["analyze"])
    dict(prepare=prepare, trace=trace, analyze=analyze)[sys.argv[1]]()
