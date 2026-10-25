#!/usr/bin/env python3
"""Factor certified whole-word Line maps without discarding return crossings."""
from pathlib import Path
import resource
import shutil
import struct
import sys

import numpy as np

import exp709_cost_skeleton as execution
import exp711_support_functions as shared

ROOT, BUILD = Path("validation/results/exp721"), Path("build/exp721")
PLAN = Path("experiment/实验721-完整词Line归一化与共享行偏置.md")
SOURCE = Path("build/exp710/full.bin")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
CELL = np.dtype([("end", "<u2"), ("shift", "<i2"), ("block", "<u2"), ("line", "<u2")])
BAND = np.dtype([("end", "<u2"), ("row", "<u4"), ("bias", "<u2")])
execution.ROOT = ROOT


def original_maps(raw):
    pos = 0
    while pos < len(raw):
        gid, nb, nr, nc, dx, dy = struct.unpack_from("<IHHIhh", raw, pos)
        pos += 16
        bands = np.frombuffer(raw, "<u2", 2*nb, pos).reshape(nb, 2)
        pos += 4*nb
        rows = [struct.unpack_from("<IHH", raw, pos+8*i) for i in range(nr)]
        pos += 8*nr
        cells = np.frombuffer(raw, CELL, nc, pos)
        pos += 8*nc
        expanded = []
        for start, count, pad in rows:
            assert not pad and count
            c = cells[start:start+count]
            assert len(c) == count and c[-1]["end"] == 120
            assert np.all(np.diff(c["end"].astype(int)) > 0)
            values = c[np.searchsorted(c["end"], np.arange(120), side="right")]
            expanded.append(np.column_stack([values[n] for n in ("shift", "block", "line")]))
        assert bands[-1, 0] == 550 and np.all(np.diff(bands[:, 0].astype(int)) > 0)
        indices = bands[np.searchsorted(bands[:, 0], np.arange(550), side="right"), 1]
        yield gid, dx, dy, np.asarray(expanded, "i4")[indices]
    assert pos == len(raw)


def prefixes():
    px, py = np.zeros(121, "i4"), np.zeros(551, "i4")
    for line in read("doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]["Line"]:
        assert line["direction"] in ("vertical", "horizontal") and line["delay"] >= 0
        p = px if line["direction"] == "vertical" else py
        p[line["site"]+1] += line["delay"]
    return px.cumsum(), py.cumsum()


def endpoint_line(grid, dx, dy, px, py):
    valid = grid[:, :, 0] != -32768
    y, x = np.nonzero(valid)
    ex, ey = x+dx+grid[y, x, 0], y+dy
    assert np.all((ex >= 0) & (ex < 120) & (ey >= 0) & (ey < 550))
    line = np.zeros(valid.shape, "i4")
    line[y, x] = np.abs(px[ex]-px[x])+np.abs(py[ey]-py[y])
    assert np.all(grid[:, :, 2][valid] >= line[valid])
    return valid, line


def normalize(grid, endpoint, arm):
    valid = grid[:, :, 0] != -32768
    assert np.all(grid[:, :, 1:][~valid] == 0)
    values = grid.copy()
    if "N" in arm:
        values[:, :, 2] -= endpoint
    bias = np.zeros(550, "i4")
    if "R" in arm:
        bias = np.where(valid, values[:, :, 2], 65536).min(axis=1)
        bias[bias == 65536] = 0
        values[:, :, 2] -= np.where(valid, bias[:, None], 0)
    assert np.all((values[:, :, 1:] >= 0) & (values[:, :, 1:] <= 65535))
    assert np.all((bias >= 0) & (bias <= 65535))
    return values, bias


def encode_row(values):
    ends = np.r_[np.flatnonzero(np.any(values[1:] != values[:-1], axis=1))+1, 120]
    cells = np.empty(len(ends), CELL)
    cells["end"] = ends
    for i, name in enumerate(("shift", "block", "line")):
        cells[name] = values[ends-1, i]
    return cells.tobytes()


def ordered_counts(ends, size):
    return shared.comparisons(tuple((int(e), i) for i, e in enumerate(ends)), size)[0]


def serialize(maps, columns, rows):
    co, ro = [0], [0]
    for value in columns:
        co.append(co[-1]+len(value)//8)
    for value in rows:
        ro.append(ro[-1]+len(value)//8)
    assert max(co[-1], ro[-1], len(rows), len(columns)) < 2**32
    return b"EX721G01"+struct.pack("<5I", len(maps), len(columns), len(rows), co[-1], ro[-1])+\
        b"".join(struct.pack("<IhhI", *m) for m in maps)+\
        np.asarray(co, "<u4").tobytes()+np.asarray(ro, "<u4").tobytes()+\
        b"".join(columns)+b"".join(rows)


def verify(raw, source, arm, px, py):
    assert raw[:8] == b"EX721G01"
    nm, nc, nr, nb, ne = struct.unpack_from("<5I", raw, 8)
    maps = [struct.unpack_from("<IhhI", raw, 28+12*i) for i in range(nm)]
    pos = 28+12*nm
    co = np.frombuffer(raw, "<u4", nc+1, pos)
    pos += 4*(nc+1)
    ro = np.frombuffer(raw, "<u4", nr+1, pos)
    pos += 4*(nr+1)
    bands = np.frombuffer(raw, BAND, nb, pos)
    pos += 8*nb
    cells = np.frombuffer(raw, CELL, ne, pos)
    assert pos+8*ne == len(raw) and co[0] == ro[0] == 0 and co[-1] == nb and ro[-1] == ne
    assert np.all(np.diff(co) > 0) and np.all(np.diff(ro) > 0)
    points = total = 0
    for record, original in zip(maps, original_maps(source)):
        gid, dx, dy, column = record
        assert (gid, dx, dy) == original[:3]
        g = original[3]
        b = bands[co[column]:co[column+1]]
        assert b[-1]["end"] == 550 and np.all(np.diff(b["end"].astype(int)) > 0)
        actual = np.empty_like(g)
        begin = 0
        for band in b:
            end, rid, bias = map(int, (band["end"], band["row"], band["bias"]))
            row = cells[ro[rid]:ro[rid+1]]
            assert row[-1]["end"] == 120 and np.all(np.diff(row["end"].astype(int)) > 0)
            expanded = row[np.searchsorted(row["end"], np.arange(120), side="right")]
            value = np.column_stack([expanded[n] for n in ("shift", "block", "line")]).astype("i4")
            value[:, 2] += np.where(value[:, 0] != -32768, bias, 0)
            actual[begin:end] = value
            begin = end
        if "N" in arm:
            actual[:, :, 2] += endpoint_line(g, dx, dy, px, py)[1]
        assert np.array_equal(actual, g)
        points += 66000
        total += 1
    assert total == nm == 1036
    return points


def self_check(px, py):
    g = np.zeros((550, 120, 3), "i4")
    g[:, :, 0] = -32768
    for x, extra in ((3, 18), (4, 26)):
        g[10, x] = (0, 292, int(px[x+6]-px[x])+extra)
    valid, endpoint = endpoint_line(g, 6, 0, px, py)
    assert valid.sum() == 2
    for arm in ("F", "N", "R", "NR"):
        v, b = normalize(g, endpoint, arm)
        recovered = v[:, :, 2]+np.where(valid, b[:, None], 0)+("N" in arm)*endpoint
        assert np.array_equal(recovered, g[:, :, 2])
        if arm == "NR":
            assert b[10] == 18 and v[10, 3, 2] == 0 and v[10, 4, 2] == 8
    assert np.array_equal(ordered_counts([120], 120), np.ones(120))


def compute():
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    frozen = read(ROOT/"freeze.json")
    for item in frozen["inputs"]:
        check(item["path"], item)
    px, py = prefixes()
    self_check(px, py)
    source = SOURCE.read_bytes()
    sample = np.fromfile("build/exp710/samples.u32", "<u4")
    catalog = np.fromfile("build/exp710/catalogue.i32", "<i4").reshape(-1, 6)
    strata = np.fromfile("build/exp710/strata.u16", "<u2")
    previous = read("validation/results/exp710/report.json")
    population = read("validation/results/exp710/freeze.json")["population_stratum_counts"]
    frequency = np.bincount(catalog[:, 0], minlength=previous["unique_motion_words"])
    directory = previous["reports"]["F"]["exact_binding_directory_bytes"]
    reports = {}
    for arm in ("F", "N", "R", "NR"):
        rows, columns, maps = [], [], []
        row_ids, column_ids, row_depths, depths, sizes = {}, {}, {}, {}, {}
        valid_points = return_points = max_excess = 0
        for gid, dx, dy, grid in original_maps(source):
            valid, endpoint = endpoint_line(grid, dx, dy, px, py)
            excess = grid[:, :, 2]-endpoint
            valid_points += int(valid.sum())
            return_points += int(np.count_nonzero(excess > 0))
            max_excess = max(max_excess, int(excess.max()))
            values, bias = normalize(grid, endpoint, arm)
            rb, local = [], set()
            for row in values:
                raw = encode_row(row)
                rid = shared.intern(raw, row_ids, rows)
                rb.append(rid)
                local.add(rid)
                if rid not in row_depths:
                    row_depths[rid] = int(ordered_counts(np.frombuffer(raw, CELL)["end"], 120).max())
            rb = np.asarray(rb, "<u4")
            ends = np.r_[np.flatnonzero((rb[1:] != rb[:-1]) | (bias[1:] != bias[:-1]))+1, 550]
            bands = np.empty(len(ends), BAND)
            bands["end"], bands["row"], bands["bias"] = ends, rb[ends-1], bias[ends-1]
            cid = shared.intern(bands.tobytes(), column_ids, columns)
            maps.append((gid, dx, dy, cid))
            sizes[gid] = 16+8*len(ends)+8*len(local)+sum(len(rows[rid]) for rid in local)
            cy = ordered_counts(ends, 550)
            depths[gid] = max(int(cy[y])+row_depths[int(rb[y])] for y in range(550))
        raw = serialize(maps, columns, rows)
        path = BUILD/(arm+".bin")
        with path.open("xb") as stream:
            stream.write(raw)
        points = verify(path.read_bytes(), source, arm, px, py)
        v = np.asarray([sizes[int(catalog[i, 0])] for i in sample], "f8")/frequency[catalog[sample, 0]]
        estimate = variance = 0.
        for h, nh in enumerate(population):
            x = v[strata[sample] == h]
            assert len(x) == 10
            estimate += nh*float(x.mean())
            variance += nh**2*(1-10/nh)*float(x.var(ddof=1))/10
        upper = estimate+1.96*variance**.5+directory
        depth = np.asarray([depths[int(catalog[i, 0])] for i in sample])
        reports[arm] = dict(file=identity(path), maps=len(maps), certified_positions=points,
            unique_rows=len(rows), unique_columns=len(columns), local_sample_bytes=sum(sizes.values()),
            valid_points=valid_points, positive_excess_points=return_points, max_line_excess=max_excess,
            estimated_unshared_pool_bytes=estimate+directory,
            design_standard_error_bytes=variance**.5, approximate_unshared_upper95_bytes=upper,
            exact_binding_directory_bytes=directory, shared_sample_bytes=len(raw),
            comparison_quantiles=np.quantile(depth, [0,.5,.9,.95,.99,1]).tolist(),
            within_8_comparisons_fraction=float((depth <= 8).mean()),
            capacity_gate=upper <= 33_554_432, comparisons_gate=float((depth <= 8).mean()) >= .8)
        print("EXP721_ARM", arm, reports[arm], flush=True)
    nr = reports["NR"]
    write(ROOT/"report.json", dict(all_checks_passed=True, reports=reports,
        selected=nr["capacity_gate"] and nr["comparisons_gate"],
        selection="NR fixed before results", complete_estimator_runs=0, new_exact_rows=0,
        all_pool_measured=False, unknown_selector_available=False, cpu_claim=False, accuracy_claim=False,
        removed_bytes=0, disk_free_end_bytes=shutil.disk_usage(".").free))


def main():
    assert sys.argv[1:] in (["run"], ["compute"])
    if sys.argv[1] == "compute":
        compute()
        return
    assert not ROOT.exists() and not BUILD.exists()
    assert read("validation/results/exp710/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    files = [SOURCE, Path("build/exp710/samples.u32"), Path("build/exp710/catalogue.i32"),
        Path("build/exp710/strata.u16"), Path("validation/results/exp710/freeze.json"),
        Path("validation/results/exp710/report.json"), Path("validation/results/exp710/independent-audit.json"),
        Path("doc/eda比赛文件/arch/SRB_Gap.json"), Path(__file__), Path(shared.__file__),
        Path(execution.__file__), PLAN, ROOT/"protocol-original.md"]
    write(ROOT/"freeze.json", dict(inputs=[identity(p) for p in files],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    result = execution.measured([sys.executable, __file__, "compute"], "component")
    assert result["threads"] == 1 and result["rss_bytes"] <= 512 << 20 and result["cpu_s"] <= 600
    write(ROOT/"completion.json", dict(all_checks_passed=True, run=result))
    print("EXP721_COMPLETE", read(ROOT/"report.json")["selected"], flush=True)


if __name__ == "__main__":
    main()
