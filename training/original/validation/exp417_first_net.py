#!/usr/bin/env python3
"""Measure mandatory first-Net events against the frozen exp416 rows."""
import csv
import json
from pathlib import Path
import time

import numpy as np

from exp413_affine_tail import Field, SLOPES, accumulate, identity
from exp416_geometry_residual import split

ROOT = Path("validation/results/exp417")


def compose(nominal, gap, remaining_line, same, valid):
    return np.where(same, 0, np.where(valid, nominal + gap + remaining_line, -1))


def score(g, p):
    return np.where(g > 0, 1 - np.tanh(4 * np.abs(p - g) / np.maximum(g, 1)),
                    (g == p).astype(float))


def self_check():
    answer = compose(np.array([441, 999, 999]), np.array([275, 0, 0]),
                     np.array([275, 0, 0]), np.array([False, True, False]),
                     np.array([True, False, False]))
    assert answer.tolist() == [991, 0, -1]
    assert score(np.array([991, 0, -1]), answer).tolist() == [1, 1, 1]


def run():
    started = time.process_time()
    with Path("validation/results/exp416/rows.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (ROOT / "events.csv").open(newline="") as stream:
        events = list(csv.DictReader(stream))
    assert len(rows) == len(events) == 15477
    assert all((r["from"], r["to"]) == (e["from"], e["to"]) for r, e in zip(rows, events))
    fields = {"ZSEA[0]": Field("build/exp413/sea.bin"),
              "ZLE[0]": Field("build/exp413/le.bin")}
    names = [r["Name"] for r in json.loads(
        Path("doc/eda比赛文件/arch/SRB_Port.json").read_text())["Port"]]
    ordinal = {names[int(p)]: i for i, p in enumerate(fields["ZSEA[0]"].ports)}
    truth = np.array([int(r["exact"]) for r in rows], dtype=np.int64)
    old = np.array([int(r["predicted"]) for r in rows], dtype=np.int64)
    nominal = np.array([int(r["nominal"]) for r in rows], dtype=np.int64)
    valid = np.array([e["valid"] == "1" for e in events])
    same = np.array([e["same_pin"] == "1" for e in events])
    gap = np.array([int(e["gap"]) for e in events])
    remaining = np.array([int(e["remaining_line"]) for e in events])
    shifted = nominal.copy()
    reason = np.full(len(rows), "", dtype=object)
    dx = np.empty(len(rows), dtype=np.int64)
    dy = np.empty(len(rows), dtype=np.int64)
    for i, (r, e) in enumerate(zip(rows, events)):
        tx, ty, tp = split(r["to"])
        dx[i] = tx - int(e["ax"]) + int(e["net_dx"])
        dy[i] = ty - int(e["ay"]) + int(e["net_dy"])
        if not same[i] and valid[i] and dx[i] == dy[i] == 0 and tp == r["source"]:
            reason[i] = "nonempty_collision"
    certificates = 0
    for source, field in fields.items():
        mask = np.array([r["source"] == source for r in rows]) & valid & ~same & (reason == "")
        inside = (np.abs(dx) <= field.rx) & (np.abs(dy) <= field.ry)
        reason[mask & ~inside] = "outside_field"
        ids = np.flatnonzero(mask & inside)
        ports = np.array([ordinal[split(rows[i]["to"])[2]] for i in ids])
        values = field.values[dy[ids] + field.ry, dx[ids] + field.rx, ports].astype(np.int64)
        bound = np.full(len(ids), 1 << 60, dtype=np.int64)
        for side in field.boundary:
            best = np.max(side[:, None] + SLOPES[:, 0, None] * dx[ids] +
                          SLOPES[:, 1, None] * dy[ids] + field.phi[:, ports], axis=0)
            bound = np.minimum(bound, best)
        certified = (values < 1000000000) & (120 * values <= bound)
        reason[ids[~certified]] = "uncertified"
        shifted[ids[certified]] = values[certified]
        certificates += int(certified.sum())
    b = compose(nominal, gap, remaining, same, valid)
    c = compose(shifted, gap, remaining, same, valid)
    c[reason != ""] = old[reason != ""]
    assert np.all(c >= -1) and np.all(truth[~valid & ~same] == -1)
    masks = {"all": np.ones(len(rows), dtype=bool), "certified_shift": reason == ""}
    for key in ("regular_proxy", "boundary", "block_rectangle", "near_axis"):
        masks[key] = np.array([r[key] == "True" for r in rows])
    for source in fields:
        masks[source] = np.array([r["source"] == source for r in rows])
        masks[source + "/regular_proxy"] = masks[source] & masks["regular_proxy"]
    stats, paired = {}, {}
    for name, prediction in (("A", old), ("B", b), ("C", c)):
        for group, mask in masks.items():
            accumulate(stats, name + "/" + group, truth, prediction, mask)
        delta = 100 * (score(truth, prediction) - score(truth, old))
        paired[name] = {"delta_accuracy_pp": float(delta.mean()),
                        "changed_rows": int(np.sum(prediction != old)),
                        "improved_rows": int(np.sum(delta > 0)),
                        "worsened_rows": int(np.sum(delta < 0))}
    for entry in stats.values():
        entry["accuracy_pp"] = 100 * entry["score_sum"] / entry["rows"]
        entry["mean_absolute_error"] = entry["error_sum"] / entry["rows"]
        entry["mean_relative_error"] = entry["relative_sum"] / entry["rows"]
        entry["over"] = entry["rows"] - entry["equal"] - entry["under"]
    _, groups = np.unique([r["from"] for r in rows], return_inverse=True)
    count = np.bincount(groups)
    delta = 100 * (score(truth, c) - score(truth, old))
    summed = np.bincount(groups, weights=delta)
    rng = np.random.default_rng(20261018417)
    boots = np.empty(2000)
    for repeat in range(len(boots)):
        sample = rng.integers(0, len(count), len(count))
        boots[repeat] = summed[sample].sum() / count[sample].sum()
    ci = np.quantile(boots, [.025, .975]).tolist()
    records = []
    for i, row in enumerate(rows):
        records.append(dict(row, B=int(b[i]), C=int(c[i]), first_gap=int(gap[i]),
                            remaining_line=int(remaining[i]), shifted_nominal=int(shifted[i]),
                            shifted_dx=int(dx[i]), shifted_dy=int(dy[i]), fallback=str(reason[i])))
    witness = [r for r in records if r["from"] == "SRB_90_463/ZLE[0]" and
               r["to"] == "SRB_92_469/ZSEA[2]"]
    assert len(witness) == 1
    w = witness[0]
    assert [int(w[k]) for k in ("exact", "nominal", "line", "first_gap", "remaining_line", "C")] == [
        991, 441, 0, 275, 275, 991]
    with (ROOT / "rows.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    passed = (stats["C/all"]["accuracy_pp"] >= 98 and all(
        stats["C/" + s + "/regular_proxy"]["accuracy_pp"] >= 99 for s in fields) and ci[0] > 0)
    report = {
        "rows": len(rows), "events": identity(ROOT / "events.csv"), "stats": stats, "paired": paired,
        "bootstrap": {"unit": "complete source pin", "groups": len(count), "repeats": 2000,
                      "seed": 20261018417, "C_minus_A_accuracy_pp_95pct": ci,
                      "scope": "Conditional development-set effect; new requests still required."},
        "shift_certified_rows": certificates,
        "fallback_counts": {str(k): int(v) for k, v in zip(*np.unique(reason, return_counts=True)) if k},
        "witness_550ps": w,
        "worst_C": sorted(records, key=lambda r: abs(r["C"] - int(r["exact"])) /
                          max(1, int(r["exact"])), reverse=True)[:20],
        "main_gate_pass": passed, "cpu_s": time.process_time() - started,
        "scope": "Fixed two-source public Z-to-Z development subset; not full 1M accuracy or CPU."}
    with (ROOT / "report.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"rows": len(rows), "acc": {a: stats[a + "/all"]["accuracy_pp"]
                                               for a in ("A", "B", "C")},
                      "gate_pass": passed, "fallbacks": report["fallback_counts"],
                      "delta_ci": ci}, indent=2))


if __name__ == "__main__":
    self_check()
    run()
