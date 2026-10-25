#!/usr/bin/env python3
"""Project certified word maps to support and share equal row/column functions."""
import json
from pathlib import Path
import resource
import shutil
import struct
import sys

import numpy as np

import exp709_cost_skeleton as execution
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp711"), Path("build/exp711")
PLAN = Path("experiment/实验711-纯支持函数的语义合并与跨词共享.md")
SOURCE = Path("build/exp710/support.bin")
execution.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def original_maps(raw):
    pos = 0
    while pos < len(raw):
        gid, nb, nr, nc, dx, dy = struct.unpack_from("<IHHIhh", raw, pos)
        pos += 16
        bands = np.frombuffer(raw, "<u2", 2 * nb, pos).reshape(nb, 2)
        pos += 4 * nb
        offsets = [struct.unpack_from("<IHH", raw, pos + 8*i) for i in range(nr)]
        pos += 8 * nr
        cells = np.frombuffer(raw, "<i2", 3 * nc, pos).reshape(nc, 3)
        pos += 6 * nc
        rows = []
        for start, count, pad in offsets:
            assert pad == 0
            rows.append(tuple((int(c[0]), int(c[1])) for c in cells[start:start+count]))
        yield gid, dx, dy, tuple(map(tuple, bands.tolist())), rows
    assert pos == len(raw)


def merge(sequence):
    result = []
    for end, value in sequence:
        if result and result[-1][1] == value:
            result[-1] = (end, value)
        else:
            result.append((end, value))
    return tuple(result)


def intern(value, dictionary, values):
    if value not in dictionary:
        dictionary[value] = len(values)
        values.append(value)
    return dictionary[value]


def expand(row, size):
    result = np.empty(size, dtype="<i4")
    start = 0
    for end, value in row:
        assert start < end <= size
        result[start:end] = value
        start = end
    assert start == size
    return result


def comparisons(sequence, size):
    counts = np.zeros(size, dtype="<u2")
    values = []
    for x in range(size):
        lo, hi = 0, len(sequence)
        while lo < hi:
            counts[x] += 1
            mid = (lo + hi)//2
            if sequence[mid][0] <= x:
                lo = mid + 1
            else:
                hi = mid
        assert lo < len(sequence)
        values.append(sequence[lo][1])
    return counts, values


def grid(bands, rows):
    xrows = np.array([expand(row, 120) for row in rows], dtype="<i2")
    ids = expand(bands, 550)
    return xrows[ids]


def self_check():
    assert merge([(30, -32768), (70, -32768), (120, -32768)]) == ((120, -32768),)
    assert merge([(30, 0), (70, 14), (120, 14)]) == ((30, 0), (120, 14))
    row = ((119, 0), (120, -14))
    assert expand(row, 120)[119] == -14
    band = ((549, 0), (550, 1))
    g = grid(band, [((120, -32768),), row])
    assert g[548, 119] == -32768 and g[549, 119] == -14
    counts, values = comparisons(band, 550)
    assert values == expand(band, 550).tolist() and counts.max() == 2
    dictionary, pool = {}, []
    assert intern(row, dictionary, pool) == intern(row, dictionary, pool) == 0


def serialize(maps, columns, rows):
    col_offsets, row_offsets = [0], [0]
    for column in columns:
        col_offsets.append(col_offsets[-1] + len(column))
    for row in rows:
        row_offsets.append(row_offsets[-1] + len(row))
    data = bytearray(b"EX711G01" + struct.pack("<5I", len(maps), len(columns), len(rows),
                                             col_offsets[-1], row_offsets[-1]))
    for record in maps:
        data += struct.pack("<IhhI", *record)
    data += np.asarray(col_offsets, "<u4").tobytes()
    data += np.asarray(row_offsets, "<u4").tobytes()
    for column in columns:
        for end, row in column:
            data += struct.pack("<HI", end, row)
    for row in rows:
        for end, shift in row:
            data += struct.pack("<Hh", end, shift)
    return data


def verify_serialized(raw, source):
    assert raw[:8] == b"EX711G01"
    nm, nc, nr, nb, ne = struct.unpack_from("<5I", raw, 8)
    pos = 28
    maps = [struct.unpack_from("<IhhI", raw, pos + 12*i) for i in range(nm)]
    pos += 12 * nm
    cols = np.frombuffer(raw, "<u4", nc+1, pos)
    pos += 4 * (nc+1)
    rows = np.frombuffer(raw, "<u4", nr+1, pos)
    pos += 4 * (nr+1)
    bands = np.frombuffer(raw, np.dtype([("end", "<u2"), ("row", "<u4")]), nb, pos)
    pos += 6 * nb
    cells = np.frombuffer(raw, np.dtype([("end", "<u2"), ("shift", "<i2")]), ne, pos)
    pos += 4 * ne
    assert pos == len(raw) and cols[-1] == nb and rows[-1] == ne
    assert cols[0] == rows[0] == 0 and np.all(np.diff(cols) > 0) and np.all(np.diff(rows) > 0)
    points = 0
    for record, original in zip(maps, original_maps(source)):
        gid, dx, dy, col = record
        assert (gid, dx, dy) == original[:3]
        cb = bands[cols[col]:cols[col+1]]
        assert cb[-1]["end"] == 550 and np.all(np.diff(cb["end"].astype(int)) > 0)
        chosen = np.searchsorted(cb["end"], np.arange(550), side="right")
        actual = np.empty((550, 120), dtype="<i2")
        for index in np.unique(chosen):
            rid = int(cb[index]["row"])
            cr = cells[rows[rid]:rows[rid+1]]
            assert cr[-1]["end"] == 120 and np.all(np.diff(cr["end"].astype(int)) > 0)
            actual[chosen == index] = cr["shift"][np.searchsorted(cr["end"], np.arange(120), side="right")]
        assert np.array_equal(actual, grid(original[3], original[4]))
        points += 66000
    assert nm == len(list(original_maps(source)))
    return points


def compute():
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    self_check()
    frozen = read(ROOT / "freeze.json")
    for item in frozen["inputs"]:
        current = identity(item["path"])
        assert all(current[k] == item[k] for k in ("bytes", "sha256"))
    source = SOURCE.read_bytes()
    row_ids, col_ids, rows, columns, maps = {}, {}, [], [], []
    sizes, depths = {}, {}
    original_rows = original_bands = 0
    for gid, dx, dy, bands, old_rows in original_maps(source):
        pure_rows = [merge(row) for row in old_rows]
        used = {}
        for end, rid in bands:
            used.setdefault(pure_rows[rid], len(used))
        local_rows = list(used)
        local_bands = merge((end, used[pure_rows[rid]]) for end, rid in bands)
        sizes[gid] = 16 + 4*len(local_bands) + 8*len(local_rows) + 4*sum(map(len, local_rows))
        original_rows += len(old_rows)
        original_bands += len(bands)
        rb = [intern(row, row_ids, rows) for row in local_rows]
        column = tuple((end, rb[rid]) for end, rid in local_bands)
        cid = intern(column, col_ids, columns)
        maps.append((gid, dx, dy, cid))
        assert np.array_equal(grid(bands, old_rows), grid(local_bands, local_rows))
        cy, chosen = comparisons(local_bands, 550)
        cx = [int(comparisons(row, 120)[0].max()) for row in local_rows]
        depths[gid] = max(int(cy[y]) + cx[chosen[y]] for y in range(550))
    raw = serialize(maps, columns, rows)
    path = BUILD / "support-functions.bin"
    with path.open("xb") as handle:
        handle.write(raw)
    points = verify_serialized(path.read_bytes(), source)
    sample = np.fromfile("build/exp710/samples.u32", "<u4")
    catalogue = np.fromfile("build/exp710/catalogue.i32", "<i4").reshape(-1, 6)
    depth = np.array([depths[int(catalogue[i, 0])] for i in sample])
    compact = len(raw) <= .25*len(source)
    small = float((depth <= 8).mean()) >= .8
    write(ROOT / "report.json", dict(all_checks_passed=True, maps=len(maps),
        certified_positions=points, unique_rows=len(rows), unique_columns=len(columns),
        original_rows=original_rows, original_y_segments=original_bands,
        A_bytes=len(source), P_bytes=sum(sizes.values()), G_bytes=len(raw),
        G_over_A=len(raw)/len(source), within_8_comparisons_fraction=float((depth<=8).mean()),
        comparison_quantiles=np.quantile(depth,[0,.5,.9,.95,.99,1]).tolist(),
        compact_gate=compact, small_state_gate=small, expand_pool=compact and small,
        file=identity(path), full_pool_estimate=False, accuracy_claim=False,
        full_estimator_runs=0, new_exact_rows=0))
    print("EXP711_COMPONENT_PASSED", len(raw), compact, small, flush=True)


def main():
    assert sys.argv[1:] in (["run"], ["compute"])
    if sys.argv[1] == "compute":
        compute()
        return
    assert not ROOT.exists() and not BUILD.exists()
    assert read("validation/results/exp710/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    inputs = [SOURCE, Path("build/exp710/samples.u32"), Path("build/exp710/catalogue.i32"),
              Path("validation/results/exp710/report.json"),
              Path("validation/results/exp710/independent-audit.json"),
              Path(__file__), PLAN, ROOT / "protocol-original.md"]
    write(ROOT / "freeze.json", dict(inputs=[identity(p) for p in inputs],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    result = execution.measured([sys.executable, __file__, "compute"], "component")
    assert result["threads"] == 1 and result["rss_bytes"] <= 512 << 20 and result["cpu_s"] <= 600
    write(ROOT / "completion.json", dict(all_checks_passed=True,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print(json.dumps(read(ROOT / "report.json"), indent=2))


if __name__ == "__main__":
    main()
