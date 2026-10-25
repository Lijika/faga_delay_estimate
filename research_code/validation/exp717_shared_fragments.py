#!/usr/bin/env python3
"""Certify shared fixed geometry fragments on the frozen exp705 corpus."""
from collections import Counter
import itertools
import json
from pathlib import Path
import resource
import shutil
import socket
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp717"), Path("build/exp717")
PLAN = Path("experiment/实验717-跨词固定连接片段的共享几何程序.md")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
execution.ROOT = ROOT


def words_at(prefix):
    text = Path(str(prefix)+".words.u8").read_bytes()
    lengths = np.fromfile(str(prefix)+".lengths.u32", "<u4")
    ends = np.r_[0, np.cumsum(lengths)].astype("i8")
    assert ends[-1] == len(text)
    return [text[a:b] for a, b in zip(ends[:-1], ends[1:])]


def options(word, at):
    yield 1, 1
    for width in range(1, 5):
        span = 2*width
        while at+span <= len(word):
            if word[at+span-width:at+span] != word[at:at+width]:
                break
            yield span, width
            span += width


def partition(word, motion, dictionary):
    costs, spans = [0]*(len(word)+1), [0]*len(word)
    for at in range(len(word)-1, -1, -1):
        choices = [s for s, _ in options(word, at)]
        choices.extend(n for n in range(2, min(12, len(word)-at)+1)
                       if motion[at:at+n] in dictionary)
        span = min(choices, key=lambda n: (costs[at+n], -n))
        spans[at], costs[at] = span, 1+costs[at+span]
    return costs[0], spans


def old_spans(word):
    costs, spans = [0]*(len(word)+1), [0]*len(word)
    for at in range(len(word)-1, -1, -1):
        span, _ = min(options(word, at), key=lambda sw: (costs[at+sw[0]], sw[1], -sw[0]))
        spans[at], costs[at] = span, 1+costs[at+span]
    return spans


def self_check():
    dictionary = {b"\x00\x01\x00", b"\x01\x00", b"\x01\x01\x00"}
    def brute(w):
        if not w:
            return 0
        spans = {s for s, _ in options(w, 0)}
        spans.update(len(v) for v in dictionary if w.startswith(v))
        return 1+min(brute(w[s:]) for s in spans)
    count = 0
    for size in range(9):
        for letters in itertools.product((0, 1), repeat=size):
            word = bytes(letters)
            assert partition(word, word, dictionary)[0] == brute(word)
            count += 1
    return count


def prepare():
    assert not ROOT.exists() and not BUILD.exists()
    assert read("../exp716/validation/results/exp716/100m-report.json")["selected"] == "A"
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    previous = read("../exp715/validation/results/exp715/freeze.json")
    inputs = [check(p["path"], p) for p in previous["inputs"]]
    old = read("../exp715/validation/results/exp715/report.json")
    counts = next(p for p in old["files"] if p["path"] == "build/exp715/counts.u32")
    inputs.append(check("../exp715/"+counts["path"], counts))
    headers = []
    for tag in (710, 715):
        source = Path("tests")/("exp710_motion_words.cpp" if tag == 710 else "exp715_repeat_words.cpp")
        target = BUILD/f"exp{tag}_functions.h"
        text = source.read_text()
        target.write_text(text[:text.index("int main(")])
        headers.extend((source, target))
    source = Path("tests/exp193_word_macro.cpp")
    text = source.read_text()
    target = BUILD/"exp193_analytic.h"
    target.write_text(text[text.index("ResolvedEdge analytic("):text.index("\nResolvedEdge replay(")]+"\n")
    headers.extend((source, target))
    include = Path("../exp589/src")
    objects = [Path("../exp580/build/exp580/architecture-resolver.o"),
               Path("../exp579/build/exp579/arch-text.o")]
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror",
               "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
               "-I", str(include), "-I", str(BUILD), "tests/exp717_shared_fragments.cpp",
               *map(str, objects), "-static", "-o", str(BUILD/"shared-fragments")]
    execution.measured(command, "compile")
    assert not (ROOT/"compile.stderr").read_bytes()
    write(ROOT/"freeze.json", dict(inputs=inputs, source="../exp705/build/exp705",
        files=[identity(p) for p in (Path(__file__), Path("tests/exp717_shared_fragments.cpp"),
               PLAN, ROOT/"protocol-original.md", *headers, include/"architecture.h", *objects,
               *sorted(Path("../../doc/eda比赛文件/arch").glob("*.json")))],
        compile_command=command, binary=identity(BUILD/"shared-fragments"),
        max_fragments=512, max_fragment_length=12, holdout_source_lanes=[3, 7],
        tiny_exhaustive_cases=self_check(), disk_free_start_bytes=shutil.disk_usage(".").free))


def analyze(frozen):
    data = Path(frozen["source"])
    q = np.fromfile(data/"queries.bin", "<i4", offset=12).reshape(-1, 10)
    sums = np.fromfile(data/"paths.summary.i32", "<i4").reshape(-1, 8)
    values = np.fromfile(BUILD/"counts.u32", "<u4").reshape(-1, 6).astype("i8")
    assert values.shape == (239616, 6) and np.all(values[:, 2] <= values[:, 1])
    def metrics(mask):
        v = values[mask]
        return dict(rows=len(v), baseline_mean_calls=float(v[:, 1].mean()),
            candidate_mean_calls=float(v[:, 2].mean()),
            call_reduction_fraction=float(1-v[:, 2].sum()/v[:, 1].sum()),
            call_quantiles=np.quantile(v[:, 2], [.5, .9, .99, 1]).tolist(),
            actual_comparison_quantiles=np.quantile(v[:, 3], [.5, .9, .99, 1]).tolist(),
            worst_comparison_quantiles=np.quantile(v[:, 4], [.5, .9, .99, 1]).tolist(),
            at_most_four_fraction=float((v[:, 2] <= 4).mean()))
    holdout = q[:, 5] % 4 == 3
    by_split = {"train": metrics(~holdout), "holdout": metrics(holdout)}
    groups = {}
    for name, labels in (("source_family", q[:, 4]), ("net_jump", sums[:, 7] != 0)):
        for value in np.unique(labels):
            groups[f"{name}-{int(value)}"] = metrics(holdout & (labels == value))
    component = read(ROOT/"component.stdout")
    files = [identity(p) for p in sorted(BUILD.iterdir()) if p.suffix in (".u8", ".u32", ".u16", ".i16", ".bin", ".csv")]
    sizes = {Path(p["path"]).name: p["bytes"] for p in files}
    geometry_bytes = sum(sizes[name] for name in ("maps.bin", "geometry.lengths.u32",
        "geometry.words.u8", "types.u8", "motions.i16")) + 4*component["geometry_fragments"]
    observed_bytes = geometry_bytes + sizes["bindings.bin"] + sizes["terms.u16"]
    assert sizes["maps.bin"] == component["map_bytes"]
    h = by_split["holdout"]
    gates = dict(mean=h["call_reduction_fraction"] >= .3, p90=h["call_quantiles"][1] <= 4,
        p99=h["call_quantiles"][2] <= 8, geometry=geometry_bytes <= 3_000_000,
        observed=observed_bytes <= 8_388_608)
    write(ROOT/"report.json", dict(all_checks_passed=True, selected=all(gates.values()), gates=gates,
        splits=by_split, holdout_groups=groups, component=component, files=files,
        geometry_bytes=geometry_bytes, observed_program_bytes=observed_bytes,
        explicit_map_offset_bytes=4*component["geometry_fragments"],
        unknown_displacement_selector_available=False, full_estimator_runs=0, new_exact_rows=0,
        accuracy_claim=False, holdout_applies_only_to_dictionary_selection=True,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP717_COMPLETE", json.dumps(dict(splits=by_split, gates=gates,
        geometry_bytes=geometry_bytes, observed_program_bytes=observed_bytes)), flush=True)


def run():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["inputs"]+frozen["files"]+[frozen["binary"]]:
        check(item["path"], item)
    cpu, memory = resource.getrlimit(resource.RLIMIT_CPU), resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_CPU, (1800, cpu[1]))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, memory[1]))
    try:
        result = execution.measured([str(BUILD/"shared-fragments"), frozen["source"], str(BUILD),
            "../../doc/eda比赛文件/arch", "../exp715/build/exp715/counts.u32"], "component")
    finally:
        resource.setrlimit(resource.RLIMIT_CPU, cpu);resource.setrlimit(resource.RLIMIT_AS, memory)
    assert result["threads"] == 1 and result["rss_bytes"] <= 1 << 30
    assert read(ROOT/"component.stdout")["all_checks_passed"]
    analyze(frozen)


def audit(data):
    report = read(ROOT/"report.json")
    for item in report["files"]:
        check(item["path"], item)
    original = words_at(data/"paths")
    selected = words_at(BUILD/"selected")
    geometry = words_at(BUILD/"geometry")
    q = np.fromfile(data/"queries.bin", "<i4", offset=12).reshape(-1, 10)
    summaries = np.fromfile(data/"paths.summary.i32", "<i4").reshape(-1, 8)
    types = (BUILD/"types.u8").read_bytes()
    motions = [bytes(types[c] for c in w) for w in original]
    delta = np.fromfile(BUILD/"motions.i16", "<i2").reshape(-1, 2)
    freq = Counter()
    for row, (w, m) in enumerate(zip(original, motions)):
        if q[row, 5] % 4 == 3:
            continue
        choices = old_spans(w)
        at = 0
        while at < len(w):
            if choices[at] != 1:
                at += choices[at]
                continue
            start = at
            while at < len(w) and choices[at] == 1:
                at += 1
            for begin in range(start, at):
                freq.update(m[begin:begin+size] for size in range(2, min(12, at-begin)+1))
    expected = sorted((w for w in freq if freq[w] >= 2), key=lambda w: (-freq[w]*(len(w)-1), w))[:512]
    assert expected == selected
    assert np.array_equal([freq[w] for w in selected], np.fromfile(BUILD/"selected.counts.u32", "<u4"))
    dtype = np.dtype([("start", "<u4"), ("arc", "<i4"), ("dx", "<i2"), ("dy", "<i2"),
                      ("source", "<u2"), ("target", "<u2")])
    bindings = np.fromfile(BUILD/"bindings.bin", dtype)
    terms = np.fromfile(BUILD/"terms.u16", "<u2")
    counts = np.fromfile(BUILD/"counts.u32", "<u4").reshape(-1, 6)
    assert len(bindings) == len(original) == 239616 and len(terms) == report["component"]["terms"]
    assert np.array_equal(np.column_stack((bindings["source"], bindings["target"])), q[:, 8:10])
    assert np.array_equal(bindings["arc"], summaries[:, 0])
    assert np.array_equal(np.column_stack((bindings["dx"], bindings["dy"])), summaries[:, 3:5])
    maps, offset = [], 0
    raw = (BUILD/"maps.bin").read_bytes()
    rowdtype = np.dtype([("start", "<u4"), ("count", "<u2"), ("reserved", "<u2")])
    celldtype = np.dtype([("end", "<u2"), ("shift", "<i2"), ("block", "<u2"), ("line", "<u2")])
    while offset < len(raw):
        ident, nband, nrow, ncell, dx, dy = struct.unpack_from("<IHHIhh", raw, offset)
        offset += 16
        bands = np.frombuffer(raw, "<u2", 2*nband, offset).reshape(-1, 2);offset += 4*nband
        rows = np.frombuffer(raw, rowdtype, nrow, offset);offset += 8*nrow
        cells = np.frombuffer(raw, celldtype, ncell, offset);offset += 8*ncell
        assert ident == len(maps) and nband and nrow and ncell
        assert bands[-1, 0] == 550 and np.all(np.diff(bands[:, 0].astype(int)) > 0)
        assert int(bands[:, 1].max()) < nrow
        assert np.array_equal(delta[list(geometry[ident])].sum(axis=0), [dx, dy])
        for r in rows:
            c = cells[int(r["start"]):int(r["start"])+int(r["count"])]
            assert len(c) == r["count"] and len(c) and c[-1]["end"] == 120
            assert np.all(np.diff(c["end"].astype(int)) > 0) and r["reserved"] == 0
        maps.append((bands, rows, cells, dx, dy))
    assert offset == len(raw) and len(maps) == len(geometry) == report["component"]["geometry_fragments"]
    dictionary = set(selected)
    for row, (w, m) in enumerate(zip(original, motions)):
        start = int(bindings[row]["start"])
        end = int(bindings[row+1]["start"]) if row+1 < len(bindings) else len(terms)
        refs = terms[start:end]
        assert end >= start and len(refs) == counts[row, 2]
        assert b"".join(geometry[int(j)] for j in refs) == m
        assert partition(w, m, dictionary)[0] == len(refs)
        x, y, block, line = int(q[row, 0]), int(q[row, 1]), 0, 0
        for j in refs:
            bands, rows, cells, dx, dy = maps[int(j)]
            r = rows[bands[np.searchsorted(bands[:, 0], y, side="right"), 1]]
            c = cells[int(r["start"]):int(r["start"])+int(r["count"])]
            v = c[np.searchsorted(c["end"], x, side="right")]
            assert v["shift"] != -32768
            x += dx+int(v["shift"]);y += dy
            block += int(v["block"]);line += int(v["line"])
            assert 0 <= x < 120 and 0 <= y < 550
        assert (x, y) == tuple(q[row, 2:4]) and block == summaries[row, 2]
        assert int(bindings[row]["arc"])+block+line == counts[row, 5]
    result = dict(all_checks_passed=True, dictionary_reselected=True, rows=len(original),
        minimum_calls_recomputed=True, full_port_bindings_preserved=True,
        maps_decoded=len(maps), serialized_original_position_costs_equal=True,
        all_grid_raw_replay_reused=True, tiny_exhaustive_cases=self_check(),
        report=identity(ROOT/"report.json"))
    write(ROOT/"independent-audit.json", result)
    print("EXP717_AUDIT", json.dumps(result), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "audit":
        audit(Path(sys.argv[2]))
    else:
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp717")
        assert sys.argv[1:] in (["prepare"], ["run"])
        dict(prepare=prepare, run=run)[sys.argv[1]]()
