#!/usr/bin/env python3
"""Evaluate fixed affine tails against certified nominal distance fields."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import numpy as np

SLOPES = np.array([[1500, 1270], [1500, -1250], [-1500, 1270], [-1500, -1250]])
ROOT = Path("validation/results/exp413")


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def anchors(coordinates, period, start):
    values = np.asarray(coordinates, dtype=np.int64)
    magnitude = np.abs(values)
    outside = magnitude >= start + period
    last = np.where(outside, start + (magnitude - start) % period, magnitude)
    count = np.where(outside, (magnitude - last) // period, 0)
    sign = np.where(values < 0, -1, 1)
    return sign * last, sign * np.where(outside, last - period, last), count


def extend(f11, f01, f10, f00, nx, ny):
    return f11 + nx * (f11 - f01) + ny * (f11 - f10) + nx * ny * (
        f11 - f01 - f10 + f00)


def self_check():
    x = np.arange(-119, 120)
    y = np.arange(-549, 550)
    x1, x0, nx = (v[:, None] for v in anchors(x, 20, 40))
    y1, y0, ny = anchors(y, 24, 48)
    for mixed in (0, 3):
        f = lambda a, b: 10000 + 7 * a + 11 * b + mixed * a * b
        actual = extend(f(x1, y1), f(x0, y1), f(x1, y0), f(x0, y0), nx, ny)
        assert np.array_equal(actual, f(x[:, None], y))
    for period, start, coords in ((20, 40, x), (24, 48, y)):
        last, previous, count = anchors(coords, period, start)
        assert np.array_equal(last + count * (last - previous), coords)
        assert np.all(np.abs(last) < start + period)
        assert np.all((coords - last) % period == 0)


class Field:
    def __init__(self, path):
        with Path(path).open("rb") as stream:
            assert stream.read(8) == b"EX413D01"
            self.rx, self.ry, self.n, self.source = struct.unpack("<4i", stream.read(16))
            self.ports = np.frombuffer(stream.read(4 * self.n), dtype="<i4").copy()
            self.phi = np.frombuffer(stream.read(16 * self.n), dtype="<i4").reshape(4, self.n).copy()
            self.boundary = np.frombuffer(stream.read(128), dtype="<i8").reshape(4, 4).copy()
            offset = stream.tell()
        self.shape = (2 * self.ry + 1, 2 * self.rx + 1, self.n)
        assert Path(path).stat().st_size == offset + int(np.prod(self.shape)) * 4
        self.values = np.memmap(path, mode="r", dtype="<i4", offset=offset, shape=self.shape)
        assert self.n == 160 and self.values[self.ry, self.rx, self.source] == 0

    def row(self, xs, y):
        return self.values[int(y) + self.ry, np.asarray(xs) + self.rx].astype(np.int64)

    def certified(self, xs, y, truth):
        bound = np.full(truth.shape, 1 << 60, dtype=np.int64)
        for side in self.boundary:
            best = np.full(truth.shape, -(1 << 60), dtype=np.int64)
            for k, (a, b) in enumerate(SLOPES):
                best = np.maximum(best, side[k] + a * xs[:, None] + b * y + self.phi[k])
            bound = np.minimum(bound, best)
        return (truth < 1000000000) & (120 * truth <= bound)


def accumulate(stats, key, truth, prediction, mask):
    g, p = truth[mask], prediction[mask]
    if not len(g):
        return
    error = np.abs(p - g)
    relative = error / np.maximum(g, 1)
    points = np.where(g > 0, 1 - np.tanh(4 * relative), (p == g).astype(float))
    s = stats.setdefault(key, dict(rows=0, equal=0, within_one_percent=0, under=0,
                                  score_sum=0.0, error_sum=0, relative_sum=0.0,
                                  max_error=0, max_relative=0.0))
    s["rows"] += int(len(g))
    s["equal"] += int(np.sum(error == 0))
    s["within_one_percent"] += int(np.sum(relative <= .01))
    s["under"] += int(np.sum(p < g))
    s["score_sum"] += float(points.sum())
    s["error_sum"] += int(error.sum())
    s["relative_sum"] += float(relative.sum())
    s["max_error"] = max(s["max_error"], int(error.max()))
    s["max_relative"] = max(s["max_relative"], float(relative.max()))


def analyze(path):
    started = time.process_time()
    field = Field(path)
    names = [r["Name"] for r in json.loads(
        Path("doc/eda比赛文件/arch/SRB_Port.json").read_text())["Port"]]
    x = np.arange(-119, 120)
    x1, x0, nx = anchors(x, 20, 40)
    stats, witnesses = {}, {"A": [], "B": []}
    certified_count = 0
    uncertified_examples = []
    for y in range(-549, 550):
        truth = field.row(x, y)
        certified = field.certified(x, y, truth)
        certified_count += int(certified.sum())
        if len(uncertified_examples) < 8 and np.any(~certified):
            i, p = np.argwhere(~certified)[0]
            uncertified_examples.append([int(x[i]), y, names[int(field.ports[p])], int(truth[i, p])])
        y1, y0, ny = (int(v) for v in anchors(y, 24, 48))
        a = (ny + 1) * field.row(x, y1) - ny * field.row(x, y0)
        b = extend(field.row(x1, y1), field.row(x0, y1),
                   field.row(x1, y0), field.row(x0, y0), nx[:, None], ny)
        for model, predicted in (("A", a), ("B", b)):
            tail_x = np.ones(len(x), dtype=bool) if ny else (
                np.zeros(len(x), dtype=bool) if model == "A" else nx > 0)
            tail = np.broadcast_to(tail_x[:, None], truth.shape)
            assert np.array_equal(predicted[~tail], truth[~tail])
            mask = certified & tail
            accumulate(stats, model + "/certified_tail", truth, predicted, mask)
            accumulate(stats, model + "/all_certified", truth, predicted, certified)
            side = "y_positive" if y >= 72 else "y_negative" if y <= -72 else "x_tail"
            for band, xm in (("near_axis", np.abs(x) < 20), ("interior", np.abs(x) >= 20)):
                accumulate(stats, model + "/" + side + "/" + band, truth, predicted,
                           mask & xm[:, None])
            for tag in ("ZL", "ZQ", "ZD", "ZS"):
                pm = np.array([names[int(p)].startswith(tag) for p in field.ports])
                accumulate(stats, model + "/target_" + tag, truth, predicted, mask & pm)
            error = np.where(mask, np.abs(predicted - truth), -1)
            at = int(error.argmax())
            i, p = np.unravel_index(at, error.shape)
            if error[i, p] > 0:
                witnesses[model].append({
                    "x": int(x[i]), "y": y, "port": names[int(field.ports[p])],
                    "truth": int(truth[i, p]), "prediction": int(predicted[i, p]),
                    "error": int(error[i, p]), "x_anchor": int(x1[i]),
                    "y_anchor": y1, "nx": int(nx[i]), "ny": ny,
                    "mixed_difference": int(field.row(x1[i:i+1], y1)[0, p] -
                        field.row(x0[i:i+1], y1)[0, p] -
                        field.row(x1[i:i+1], y0)[0, p] +
                        field.row(x0[i:i+1], y0)[0, p])})
    for s in stats.values():
        s["accuracy_pp"] = 100 * s["score_sum"] / s["rows"]
        s["mean_relative_error"] = s["relative_sum"] / s["rows"]
        s["mean_absolute_error"] = s["error_sum"] / s["rows"]
        s["exact_fraction"] = s["equal"] / s["rows"]
    capacities = {"A_u16_core_bytes": 160 * 160 * 239 * 143 * 2,
                  "B_u16_core_bytes": 160 * 160 * 119 * 143 * 2}
    return {"source": names[int(field.ports[field.source])], "field": identity(path),
            "report_states": 239 * 1099 * 160, "certified_states": certified_count,
            "uncertified_examples": uncertified_examples, "stats": stats,
            "worst_examples": {m: sorted(ws, key=lambda w: -w["error"])[:12]
                               for m, ws in witnesses.items()},
            "capacity_all_160_sources": capacities,
            "max_stored_core_value": int(field.values[field.ry-71:field.ry+72,
                                                      field.rx-119:field.rx+120].max()),
            "tail_gate_pass": {m: stats[m + "/certified_tail"]["accuracy_pp"] >= 99.5
                              for m in ("A", "B")},
            "analysis_cpu_s": time.process_time() - started,
            "scope": "Deterministic nominal state grid, two selected source ports; not request accuracy."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("fields", nargs="*")
    args = parser.parse_args()
    self_check()
    if args.self_check:
        print("affine, mixed, signs and residue boundaries passed")
    for path in args.fields:
        result = analyze(path)
        out = ROOT / (Path(path).stem + "-analysis.json")
        with out.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({"source": result["source"], "certified": result["certified_states"],
                          "tail_acc": {m: result["stats"][m + "/certified_tail"]["accuracy_pp"]
                                       for m in ("A", "B")}}), flush=True)


if __name__ == "__main__":
    main()
