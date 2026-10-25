#!/usr/bin/env python3
"""Separate a fixed word's periodic geometry from its finite boundary support."""
from pathlib import Path
import resource
import shutil
import struct
import sys

import numpy as np

import exp721_line_normalization as prior

read, write, identity, check = prior.read, prior.write, prior.identity, prior.check
ROOT, BUILD = Path("validation/results/exp729"), Path("build/exp729")
PLAN = Path("experiment/实验729-固定词周期核与有限边界守卫分离.md")
CELL = np.dtype([("end", "u1"), ("mask", "u1"), ("shift", "<i2"),
                 ("block", "<u2"), ("line", "<u2")])
prior.execution.ROOT = ROOT


def periodic(grid):
    values = np.zeros((100, 120, 3), "i4")
    masks = np.zeros((100, 120), "u1")
    for phase in range(100):
        layers = grid[phase::100]
        valid = layers[:, :, 0] != -32768
        mask = (valid * (1 << np.arange(len(layers)))[:, None]).sum(axis=0)
        masks[phase] = mask
        for bits in np.unique(mask):
            if bits:
                low = int(bits) & -int(bits)
                assert int(bits) & (int(bits)+low) == 0, ("disconnected bands", phase, int(bits))
        first = valid.argmax(axis=0)
        values[phase] = layers[first, np.arange(120)]
        values[phase, mask == 0] = 0
        for layer, present in zip(layers, valid):
            assert np.array_equal(layer[present], values[phase, present]), ("nonperiodic cost", phase)
    return values, masks


def phase_values(grid, arm, dx, dy, px, py):
    raw = grid.copy()
    if arm == "N":
        raw[:, :, 2] -= prior.endpoint_line(grid, dx, dy, px, py)[1]
    values, masks = periodic(raw)
    bias = np.zeros(100, "i4")
    if arm == "N":
        bias = np.where(masks != 0, values[:, :, 2], 65536).min(axis=1)
        bias[bias == 65536] = 0
        values[:, :, 2] -= np.where(masks != 0, bias[:, None], 0)
    assert np.all((values[:, :, 0] >= -32768) & (values[:, :, 0] <= 32767))
    assert np.all((values[:, :, 1:] >= 0) & (values[:, :, 1:] <= 65535))
    assert np.all((bias >= 0) & (bias <= 65535)) and np.all(masks < 64)
    return values, masks, bias


def row_bytes(values, masks):
    changed = np.any(values[1:] != values[:-1], axis=1) | (masks[1:] != masks[:-1])
    ends = np.r_[np.flatnonzero(changed)+1, 120]
    cells = np.empty(len(ends), CELL)
    cells["end"], cells["mask"] = ends, masks[ends-1]
    for i, name in enumerate(("shift", "block", "line")):
        cells[name] = values[ends-1, i]
    return cells.tobytes()


def serialize(maps, columns, rows):
    raw = prior.serialize(maps, columns, rows)
    return b"EX729P01"+raw[8:]


def verify(raw, source, arm, px, py):
    assert raw[:8] == b"EX729P01"
    nm, nc, nr, nb, ne = struct.unpack_from("<5I", raw, 8)
    maps = [struct.unpack_from("<IhhI", raw, 28+12*i) for i in range(nm)]
    pos = 28+12*nm
    co = np.frombuffer(raw, "<u4", nc+1, pos)
    pos += 4*(nc+1)
    ro = np.frombuffer(raw, "<u4", nr+1, pos)
    pos += 4*(nr+1)
    bands = np.frombuffer(raw, prior.BAND, nb, pos)
    pos += 8*nb
    cells = np.frombuffer(raw, CELL, ne, pos)
    assert pos+8*ne == len(raw) and co[0] == ro[0] == 0 and co[-1] == nb and ro[-1] == ne
    assert np.all(np.diff(co) > 0) and np.all(np.diff(ro) > 0)
    assert np.all(cells["mask"] < 64)
    count = points = 0
    for record, original in zip(maps, prior.original_maps(source)):
        gid, dx, dy, column = record
        assert (gid, dx, dy) == original[:3]
        b = bands[co[column]:co[column+1]]
        assert b[-1]["end"] == 100 and np.all(np.diff(b["end"].astype(int)) > 0)
        values = np.zeros((100, 120, 3), "i4")
        masks = np.zeros((100, 120), "u1")
        begin = 0
        for band in b:
            end, rid, bias = map(int, (band["end"], band["row"], band["bias"]))
            row = cells[ro[rid]:ro[rid+1]]
            assert row[-1]["end"] == 120 and np.all(np.diff(row["end"].astype(int)) > 0)
            expanded = row[np.searchsorted(row["end"], np.arange(120), side="right")]
            value = np.column_stack([expanded[n] for n in ("shift", "block", "line")]).astype("i4")
            value[:, 2] += np.where(expanded["mask"] != 0, bias, 0)
            values[begin:end], masks[begin:end] = value, expanded["mask"]
            begin = end
        y = np.arange(550)
        valid = (masks[y % 100] & (1 << (y//100))[:, None]) != 0
        actual = values[y % 100].copy()
        actual[~valid] = (-32768, 0, 0)
        if arm == "N":
            yy, xx = np.nonzero(valid)
            ex, ey = xx+dx+actual[yy, xx, 0], yy+dy
            assert np.all((ex >= 0) & (ex < 120) & (ey >= 0) & (ey < 550))
            actual[yy, xx, 2] += np.abs(px[ex]-px[xx])+np.abs(py[ey]-py[yy])
        assert np.array_equal(actual, original[3]), gid
        count += 1
        points += 66000
    assert count == nm == 1036
    return points


def self_check(px, py):
    g = np.zeros((550, 120, 3), "i4")
    g[:, :, 0] = -32768
    line = int(px[10]-px[7])+18
    g[103, 7] = g[203, 7] = (0, 292, line)
    for arm in ("P", "N"):
        values, masks, bias = phase_values(g, arm, 3, 0, px, py)
        assert masks[3, 7] == 6 and np.count_nonzero(masks) == 1
        assert values[3, 7, 2]+bias[3] == (18 if arm == "N" else line)
        assert CELL.itemsize == 8 and len(row_bytes(values[3], masks[3])) == 24
    for which in ("gap", "cost"):
        bad = g.copy()
        if which == "gap":
            bad[203, 7], bad[303, 7] = (-32768, 0, 0), g[203, 7]
        else:
            bad[203, 7, 2] += 1
        try:
            periodic(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(("negative control accepted", which))


def estimate(sizes, catalog, sample, strata, population, frequency, directory):
    values = np.asarray([sizes[int(catalog[i, 0])] for i in sample], "f8")/frequency[catalog[sample, 0]]
    total = variance = 0.
    for h, nh in enumerate(population):
        x = values[strata[sample] == h]
        assert len(x) == 10
        total += nh*float(x.mean())
        variance += nh**2*(1-10/nh)*float(x.var(ddof=1))/10
    return dict(point_bytes=total+directory, design_se_bytes=variance**.5,
                approximate_upper95_bytes=total+directory+1.96*variance**.5)


def compute():
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    for item in read(ROOT/"freeze.json")["inputs"]:
        check(item["path"], item)
    px, py = prior.prefixes()
    self_check(px, py)
    source = prior.SOURCE.read_bytes()
    catalog = np.fromfile("build/exp710/catalogue.i32", "<i4").reshape(-1, 6)
    sample = np.fromfile("build/exp710/samples.u32", "<u4")
    strata = np.fromfile("build/exp710/strata.u16", "<u2")
    population = read("validation/results/exp710/freeze.json")["population_stratum_counts"]
    old = read("validation/results/exp710/report.json")
    frequency = np.bincount(catalog[:, 0], minlength=old["unique_motion_words"])
    directory = old["reports"]["F"]["exact_binding_directory_bytes"]
    reports = {}
    for arm in ("P", "N"):
        rows, columns, maps, row_ids, column_ids = [], [], [], {}, {}
        sizes, dense, valid_points = {}, {}, 0
        for gid, dx, dy, grid in prior.original_maps(source):
            values, masks, bias = phase_values(grid, arm, dx, dy, px, py)
            valid_points += int(np.count_nonzero(grid[:, :, 0] != -32768))
            rb, local = [], set()
            for row, mask in zip(values, masks):
                rid = prior.shared.intern(row_bytes(row, mask), row_ids, rows)
                rb.append(rid)
                local.add(rid)
            rb = np.asarray(rb, "<u4")
            ends = np.r_[np.flatnonzero((rb[1:] != rb[:-1]) | (bias[1:] != bias[:-1]))+1, 100]
            bands = np.empty(len(ends), prior.BAND)
            bands["end"], bands["row"], bands["bias"] = ends, rb[ends-1], bias[ends-1]
            cid = prior.shared.intern(bands.tobytes(), column_ids, columns)
            maps.append((gid, dx, dy, cid))
            sizes[gid] = 16+8*len(ends)+8*len(local)+sum(len(rows[rid]) for rid in local)
            dense[gid] = 16+100*8+len(local)*120*8
        raw = serialize(maps, columns, rows)
        path = BUILD/(arm+".bin")
        with path.open("xb") as out:
            out.write(raw)
        points = verify(path.read_bytes(), source, arm, px, py)
        compressed = estimate(sizes, catalog, sample, strata, population, frequency, directory)
        restored = estimate(dense, catalog, sample, strata, population, frequency, directory)
        reports[arm] = dict(file=identity(path), maps=len(maps), unique_rows=len(rows),
            unique_columns=len(columns), certified_positions=points, valid_points=valid_points,
            shared_sample_bytes=len(raw), local_sample_bytes=sum(sizes.values()),
            compressed_unshared_pool=compressed, restored_unshared_pool=restored,
            exact_binding_directory_bytes=directory,
            capacity_gate=compressed["approximate_upper95_bytes"] <= 32 << 20,
            memory_gate=restored["approximate_upper95_bytes"] <= 1 << 30)
        print("EXP729_ARM", arm, reports[arm], flush=True)
    n = reports["N"]
    write(ROOT/"report.json", dict(all_checks_passed=True, reports=reports,
        selected=n["capacity_gate"] and n["memory_gate"], negative_controls_passed=2,
        selection="N fixed before results", all_pool_measured=False,
        unknown_selector_available=False, complete_estimator_runs=0, new_exact_rows=0,
        cpu_claim=False, accuracy_claim=False, removed_bytes=0,
        disk_free_end_bytes=shutil.disk_usage(".").free))


def audit():
    failure, frozen = read(ROOT/"restore-failure.json"), read(ROOT/"freeze.json")
    for item in frozen["inputs"]:
        path = Path(item["path"])
        check(ROOT/"driver-before-restore-fix.py" if path.resolve() == Path(__file__).resolve() else path, item)
    px, py = prior.prefixes()
    self_check(px, py)
    source = prior.SOURCE.read_bytes()
    catalog = np.fromfile("build/exp710/catalogue.i32", "<i4").reshape(-1, 6)
    sample = np.fromfile("build/exp710/samples.u32", "<u4")
    strata = np.fromfile("build/exp710/strata.u16", "<u2")
    population = read("validation/results/exp710/freeze.json")["population_stratum_counts"]
    old = read("validation/results/exp710/report.json")
    frequency = np.bincount(catalog[:, 0], minlength=old["unique_motion_words"])
    directory = old["reports"]["F"]["exact_binding_directory_bytes"]
    reports = {}
    for arm, item in zip(("P", "N"), failure["artifacts"]):
        path = Path(item["path"])
        check(path, item)
        raw = path.read_bytes()
        points = verify(raw, source, arm, px, py)
        nm, nc, nr, nb, ne = struct.unpack_from("<5I", raw, 8)
        records = [struct.unpack_from("<IhhI", raw, 28+12*i) for i in range(nm)]
        pos = 28+12*nm
        co = np.frombuffer(raw, "<u4", nc+1, pos)
        pos += 4*(nc+1)
        ro = np.frombuffer(raw, "<u4", nr+1, pos)
        pos += 4*(nr+1)
        bands = np.frombuffer(raw, prior.BAND, nb, pos)
        sizes, dense = {}, {}
        for gid, dx, dy, column in records:
            b = bands[co[column]:co[column+1]]
            ids = np.unique(b["row"])
            sizes[gid] = 16+8*len(b)+8*len(ids)+sum(int(ro[i+1]-ro[i])*8 for i in ids)
            dense[gid] = 16+100*8+len(ids)*120*8
        compressed = estimate(sizes, catalog, sample, strata, population, frequency, directory)
        restored = estimate(dense, catalog, sample, strata, population, frequency, directory)
        reports[arm] = dict(file=item, maps=nm, unique_rows=nr, unique_columns=nc,
            certified_positions=points, shared_sample_bytes=len(raw), local_sample_bytes=sum(sizes.values()),
            compressed_unshared_pool=compressed, restored_unshared_pool=restored,
            exact_binding_directory_bytes=directory,
            capacity_gate=compressed["approximate_upper95_bytes"] <= 32 << 20,
            memory_gate=restored["approximate_upper95_bytes"] <= 1 << 30)
    n = reports["N"]
    result = dict(all_checks_passed=True, reports=reports,
        selected=n["capacity_gate"] and n["memory_gate"], negative_controls_passed=2,
        selection="N fixed before results", all_pool_measured=False,
        unknown_selector_available=False, complete_estimator_runs=0, new_exact_rows=0,
        cpu_claim=False, accuracy_claim=False, removed_bytes=0,
        original_assets_reused=True, independent_layout_and_cost_recalculation=True,
        decoder=identity(__file__), failure=identity(ROOT/"restore-failure.json"),
        disk_free_end_bytes=shutil.disk_usage(".").free)
    write(ROOT/"report.json", result)
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True,
        report=identity(ROOT/"report.json"), artifacts=failure["artifacts"],
        corrected_decoder=identity(__file__), full_positions_per_arm=68_376_000))
    print("EXP729_AUDIT", result["selected"], n, flush=True)


def main():
    assert sys.argv[1:] in (["run"], ["compute"], ["audit"])
    if sys.argv[1] == "audit":
        audit()
        return
    if sys.argv[1] == "compute":
        compute()
        return
    assert not ROOT.exists() and not BUILD.exists()
    assert read("validation/results/exp710/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    files = [prior.SOURCE, Path("build/exp710/catalogue.i32"), Path("build/exp710/samples.u32"),
        Path("build/exp710/strata.u16"), Path("validation/results/exp710/freeze.json"),
        Path("validation/results/exp710/report.json"), Path("validation/results/exp710/independent-audit.json"),
        Path("doc/eda比赛文件/arch/SRB_Gap.json"), Path(__file__), Path(prior.__file__),
        Path(prior.shared.__file__), Path(prior.execution.__file__), PLAN, ROOT/"protocol-original.md"]
    write(ROOT/"freeze.json", dict(inputs=[identity(p) for p in files],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    result = prior.execution.measured([sys.executable, __file__, "compute"], "component")
    assert result["threads"] == 1 and result["rss_bytes"] <= 512 << 20 and result["cpu_s"] <= 600
    write(ROOT/"completion.json", dict(all_checks_passed=True, run=result))
    print("EXP729_COMPLETE", read(ROOT/"report.json")["selected"], flush=True)


if __name__ == "__main__":
    main()
