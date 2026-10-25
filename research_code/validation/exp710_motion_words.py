#!/usr/bin/env python3
"""Compile fixed motion words while retaining each complete port witness."""
import json
from pathlib import Path
import resource
import shutil
import struct
import subprocess
import sys

import numpy as np
import exp709_cost_skeleton as execution
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp710"), Path("build/exp710")
PLAN = Path("experiment/实验710-端口见证与几何词支持的共享容量.md")
SEED = 20261025710
execution.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def checked(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    return actual


def prepare(directory, manifest):
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    records = {Path(r["source"]).name: r for r in read(manifest)
               if r["source"].startswith("exp705/build/exp705/")}
    names = ["queries.bin", "paths.lengths.u32", "paths.words.u8", "paths.summary.i32", "delta.i32"]
    inputs = [checked(directory / n, records[n]) for n in names]
    q = np.fromfile(directory / "queries.bin", "<i4", offset=12).reshape(-1, 10)
    delta = np.fromfile(directory / "delta.i32", "<i4").reshape(-1, 2)
    assert len(q) == 239616 and delta.shape == (59904, 2)
    assert (directory / "queries.bin").read_bytes()[:12] == b"EX535Q01" + struct.pack("<I", len(q))
    direction = np.repeat(2 * (delta[:, 0] < 0) + (delta[:, 1] < 0), 4)
    strata = q[:, 4] * 4 + direction
    assert np.array_equal(np.unique(strata), np.arange(104))
    rng = np.random.default_rng(SEED)
    chosen = np.concatenate([rng.choice(np.flatnonzero(strata == h), 10, replace=False)
                             for h in range(104)]).astype("<u4")
    assert len(chosen) == len(np.unique(chosen)) == 1040
    chosen.tofile(BUILD / "samples.u32")
    strata.astype("<u2").tofile(BUILD / "strata.u16")
    text = Path("tests/exp193_word_macro.cpp").read_text()
    begin = text.index("ResolvedEdge analytic(")
    end = text.index("\nResolvedEdge replay(", begin)
    (BUILD / "exp193_analytic.h").write_text(text[begin:end] + "\n")
    files = [Path(__file__), PLAN, ROOT / "protocol-original.md", Path("tests/exp710_motion_words.cpp"),
        Path("tests/exp193_word_macro.cpp"), BUILD / "exp193_analytic.h", BUILD / "samples.u32",
        BUILD / "strata.u16", Path(execution.__file__)]
    objects = [Path("build/exp707/local/architecture.o"), Path("build/exp707/local/embedded.o")]
    provenance = Path("validation/results/exp707/local-compare-provenance.json")
    previous_command = read(provenance)["link_command"]
    include = Path(previous_command[previous_command.index("-I") + 1])
    arch = Path("doc/eda比赛文件/arch")
    files += [provenance, *objects, include / "architecture.h",
              include / "embedded_resolver_data.h", *sorted(arch.glob("*.json"))]
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "-I", str(include), "-I", str(BUILD), "tests/exp710_motion_words.cpp",
        *map(str, objects), "-static", "-o", str(BUILD / "compile-words")]
    execution.measured(command, "compile")
    assert not (ROOT / "compile.stderr").read_bytes()
    write(ROOT / "freeze.json", dict(inputs=inputs, files=[identity(p) for p in files],
        binary=identity(BUILD / "compile-words"), directory=str(directory), arch=str(arch),
        compile_command=command, seed=SEED, sample_rows=len(chosen),
        sample_stratum_counts=np.bincount(strata[chosen], minlength=104).tolist(),
        population_stratum_counts=np.bincount(strata, minlength=104).tolist(),
        sample_without_labels=True, disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP710_PREPARED", len(chosen), flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for record in frozen["files"] + frozen["inputs"] + [frozen["binary"]]:
        checked(record["path"], record)
    command = [frozen["binary"]["path"], frozen["directory"], str(BUILD / "samples.u32"),
               str(BUILD), frozen["arch"]]
    # Only the offline component process receives these limits.
    old_cpu = resource.getrlimit(resource.RLIMIT_CPU)
    old_as = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_CPU, (1800, old_cpu[1]))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, old_as[1]))
    try:
        result = execution.measured(command, "component")
    finally:
        resource.setrlimit(resource.RLIMIT_CPU, old_cpu)
        resource.setrlimit(resource.RLIMIT_AS, old_as)
    assert result["threads"] == 1 and result["rss_bytes"] <= 512 << 20 and result["cpu_s"] <= 1800
    report = read(ROOT / "component.stdout")
    assert report["all_equal"] and report["rows"] == 239616
    write(ROOT / "component.json", report)
    print("EXP710_COMPONENT_PASSED", report, flush=True)


def check_serialized(path, full, catalog, q, sums, sample_by_geometry):
    raw, offset, total = path.read_bytes(), 0, 0
    while offset < len(raw):
        geom, nband, nrow, ncell, dx, dy = struct.unpack_from("<IHHIhh", raw, offset)
        offset += 16
        bands = np.frombuffer(raw, "<u2", 2 * nband, offset).reshape(nband, 2)
        offset += 4 * nband
        rows = np.frombuffer(raw, np.dtype([("start", "<u4"), ("count", "<u2"), ("pad", "<u2")]),
                             nrow, offset)
        offset += 8 * nrow
        dtype = np.dtype([("end", "<u2"), ("shift", "<i2"), ("block", "<u2")] +
                         ([("line", "<u2")] if full else []))
        cells = np.frombuffer(raw, dtype, ncell, offset)
        offset += dtype.itemsize * ncell
        assert len(bands) and bands[-1, 0] == 550 and np.all(np.diff(bands[:, 0].astype(int)) > 0)
        assert bands[:, 1].max() < nrow
        for row in rows:
            begin, count = int(row["start"]), int(row["count"])
            c = cells[begin:begin+count]
            assert len(c) == count and count and c[-1]["end"] == 120
            assert np.all(np.diff(c["end"].astype(int)) > 0)
        i = sample_by_geometry[geom]
        x, y = map(int, q[i, :2])
        row = rows[bands[np.searchsorted(bands[:, 0], y, side="right"), 1]]
        c = cells[int(row["start"]):int(row["start"]) + int(row["count"])]
        cell = c[np.searchsorted(c["end"], x, side="right")]
        assert cell["shift"] != -32768 and x + dx + cell["shift"] == q[i, 2] and y + dy == q[i, 3]
        assert cell["block"] == sums[i, 2]
        if full:
            assert cell["line"] == catalog[i, 4]
        total += 1
    assert offset == len(raw) and total == len(sample_by_geometry)
    return dict(file=identity(path), decoded_maps=total, original_query_costs_equal=True)


def analyze():
    frozen, component = read(ROOT / "freeze.json"), read(ROOT / "component.json")
    assert component["all_equal"]
    directory = Path(frozen["directory"])
    catalog = np.fromfile(BUILD / "catalogue.i32", "<i4").reshape(-1, 6)
    q = np.fromfile(directory / "queries.bin", "<i4", offset=12).reshape(-1, 10)
    sums = np.fromfile(directory / "paths.summary.i32", "<i4").reshape(-1, 8)
    sample = np.fromfile(BUILD / "samples.u32", "<u4")
    strata = np.fromfile(BUILD / "strata.u16", "<u2")
    maps = np.genfromtxt(BUILD / "maps.csv", delimiter=",", names=True, dtype=None, encoding="ascii")
    sample_by_geometry = {}
    for i in sample:
        sample_by_geometry.setdefault(int(catalog[i, 0]), int(i))
    assert len(sample_by_geometry) == component["sampled_motion_words"]
    frequency = np.bincount(catalog[:, 0], minlength=component["motion_words"])
    pair = np.arange(len(q)) // 4
    bindings = len(np.unique(np.column_stack((pair, catalog[:, 0])), axis=0))
    directory_bytes = (59904 + 1) * 4 + bindings * 8 + component["motion_words"] * 4
    reports = {}
    for kind in ("S", "F"):
        subset = maps[maps["kind"] == kind]
        by_id = {int(r["geometry_id"]): r for r in subset}
        assert by_id.keys() == sample_by_geometry.keys()
        values = np.array([by_id[int(catalog[i, 0])]["bytes"] for i in sample], dtype="f8")
        comparisons = np.array([by_id[int(catalog[i, 0])]["max_ordered_comparisons"] for i in sample])
        # Row sampling estimates each unique geometry once through inverse multiplicity.
        contributions = values / frequency[catalog[sample, 0]]
        total, variance = 0., 0.
        for h, population in enumerate(frozen["population_stratum_counts"]):
            v = contributions[strata[sample] == h]
            assert len(v) == 10
            total += population * float(v.mean())
            variance += population**2 * (1 - len(v)/population) * float(v.var(ddof=1)) / len(v)
        se = variance**.5
        serialized = check_serialized(BUILD / ("full.bin" if kind == "F" else "support.bin"),
                                     kind == "F", catalog, q, sums, sample_by_geometry)
        assert int(subset["bytes"].sum()) == serialized["file"]["bytes"]
        reports[kind] = dict(sample_word_bytes_quantiles=np.quantile(values, [0,.5,.9,.95,.99,1]).tolist(),
            comparison_quantiles=np.quantile(comparisons, [0,.5,.9,.95,.99,1]).tolist(),
            within_8_ordered_comparisons_fraction=float((comparisons <= 8).mean()),
            extra_terminal_and_valid_checks=3,
            estimated_geometry_bytes=total, design_standard_error_bytes=se,
            approximate_geometry_ci95_bytes=[max(0,total-1.96*se),total+1.96*se],
            exact_binding_directory_bytes=directory_bytes,
            estimated_total_bytes=total+directory_bytes,
            entire_pool_3mb_gate=total+directory_bytes+1.96*se < 3_000_000,
            small_state_gate=float((comparisons <= 8).mean()) >= .8,
            serialized=serialized)
    report = dict(all_checks_passed=True, component=component, reports=reports, bindings=bindings,
        unique_full_words=component["full_words"], unique_motion_words=component["motion_words"],
        motion_rle_count_quantiles=np.quantile(catalog[:, 5], [0,.5,.9,.95,.99,1]).tolist(),
        fixed_corpus_only=True, unknown_displacement_selector_available=False,
        new_exact_rows=0, full_estimator_runs=0, accuracy_claim=False,
        theoretical_note="端口见证与几何词转移的分离共享",
        disk_free_end_bytes=shutil.disk_usage(".").free)
    write(ROOT / "report.json", report)
    print("EXP710_COMPLETE", {k: {n: r[n] for n in ("estimated_total_bytes",
        "within_8_ordered_comparisons_fraction", "entire_pool_3mb_gate")} for k, r in reports.items()}, flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        assert sys.argv[1:] in (["run"], ["analyze"]), \
            "usage: exp710_motion_words.py prepare DATA_DIRECTORY MANIFEST | run | analyze"
        dict(run=run, analyze=analyze)[sys.argv[1]]()
