#!/usr/bin/env python3
"""Freeze, measure and check one complete C2400 nominal parent tree."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path("build/exp208")
RESULTS = Path("validation/results")
SOURCE = Path("tests/exp208_nominal_parent_tree_2400.cpp")
PLAN = Path("experiment/实验208-C1单源2400预算容量与覆盖原型.md")
FREEZE = RESULTS / "exp208-frozen.json"
RUN = RESULTS / "exp208-run.json"
REPORT = RESULTS / "exp208-report.json"
INPUT = RESULTS / "exp174-predictions.csv"
OLD = Path("build/exp171/raw/ZSEA[0].u8")
OLD_FRAME = Path("build/exp171/ZSEA[0].zstd19")
BINARY = BUILD / "parent_tree"
COMPRESSOR = BUILD / "zstd_capacity"
COUNTERS = ("outside_box", "unknown_initial", "broken_parent", "hop_cap", "missing_arc",
            "nominal_budget", "invalid_hop", "endpoint_mismatch", "invalid_terminal", "legal")
BANDS = ("0", "1-12", "13-24", "25-50", "51-100", "101-300", "301+")


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def read(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def fields(path):
    line = next(line for line in Path(path).read_text().splitlines() if line.startswith("summary "))
    out = {}
    for field in line.split()[1:]:
        key, value = field.split("=", 1)
        try:
            out[key] = int(value)
        except ValueError:
            try:
                out[key] = float(value)
            except ValueError:
                out[key] = value
    return out


def query_command(raw, meta, output, repeats, requests=None, count=6176):
    return [str(BINARY), "query", "doc/eda比赛文件/arch", str(raw),
            str(meta["dx_min"]), str(meta["dy_min"]),
            str(meta["dx_max"] - meta["dx_min"] + 1),
            str(meta["dy_max"] - meta["dy_min"] + 1), str(meta["budget"]),
            str(requests or BUILD / "requests.txt"), str(output), str(repeats), str(count)]


def compile_binary(command, name):
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    (BUILD / f"{name}.stderr").write_text(result.stderr)
    assert result.returncode == 0 and not result.stderr, result.stderr


def freeze():
    assert not any(p.exists() for p in (BUILD, FREEZE, RUN, REPORT))
    trees = json.loads((RESULTS / "exp171-source-trees.json").read_text())
    assert identity(OLD) == trees["sources"]["ZSEA[0]"]["raw"]
    assert identity(OLD_FRAME) == trees["sources"]["ZSEA[0]"]["compressed"]["frame"]
    assert json.loads((RESULTS / "exp171-evidence-check.json").read_text())["all_passed"]
    funnel = json.loads((RESULTS / "exp206-coverage.json").read_text())
    assert funnel["larger_budget_pilot_mechanism_gate"]
    assert identity("build/exp206/funnel.csv") == funnel["funnel"]
    prior = json.loads((RESULTS / "exp206-frozen.json").read_text())
    expected = next(row for row in prior["identities"] if row["path"] == str(INPUT))
    assert identity(INPUT) == expected
    BUILD.mkdir()
    (BUILD / "src").mkdir()
    for path in sorted(Path("src").iterdir()):
        if path.suffix in (".cpp", ".h"):
            shutil.copy2(path, BUILD / "src" / path.name)
    prefix = Path("tests/exp167_explicit_path_directory.cpp").read_text().split(
        "\nint main(int argc, char** argv)")[0]
    (BUILD / "scaffold.hpp").write_text(prefix.replace('"../src/', '"src/'))
    (BUILD / "periodic_theory_probe.cpp").write_text(
        Path("tests/periodic_theory_probe.cpp").read_text().replace('"../src/', '"src/'))
    shutil.copy2(SOURCE, BUILD / "probe.cpp")
    shutil.copy2(PLAN, BUILD / "protocol.md")
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-DMADV_COLLAPSE=25", "-static", "-s", "-o", str(BINARY), str(BUILD / "probe.cpp")]
    command += [str(BUILD / "src" / name) for name in
                ("architecture.cpp", "router.cpp", "residue_estimator.cpp")]
    command += ["-lzstd"]
    compile_binary(command, "compile")
    text = Path("validation/exp129_zstd_capacity.cpp").read_text()
    assert text.count("230'031'360") == 1
    (BUILD / "zstd_capacity.cpp").write_text(
        text.replace("source.size() != 230'031'360", "source.empty()"))
    zcommand = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-static", "-s",
                "-o", str(COMPRESSOR), str(BUILD / "zstd_capacity.cpp"), "-lzstd"]
    compile_binary(zcommand, "zstd-compile")
    library = subprocess.check_output(["g++", "-print-file-name=libzstd.a"], text=True).strip()
    version = subprocess.check_output(["pkg-config", "--modversion", "libzstd"], text=True).strip()
    assert version == "1.5.5"
    local_check()
    inputs = read(INPUT)
    assert len(inputs) == 6176 and len({(r["from"], r["to"]) for r in inputs}) == 6176
    with (BUILD / "requests.txt").open("x") as stream:
        for row in inputs:
            stream.write(f'{row["from"]} {row["to"]} {row["exact"]}\n')
    remote = [Path(__file__).relative_to(ROOT), BINARY, COMPRESSOR, BUILD / "requests.txt",
              OLD, OLD_FRAME, *sorted(Path("doc/eda比赛文件/arch").glob("*.json"))]
    paths = remote + [SOURCE, BUILD / "protocol.md", INPUT, Path("build/exp206/funnel.csv"),
                     Path("build/exp202/features.csv"), Path("estimate"), Path("build/submission/estimate"),
                     Path("build/exp205/estimate-selector"), RESULTS / "exp171-source-trees.json",
                     RESULTS / "exp171-evidence-check.json", RESULTS / "exp206-coverage.json",
                     RESULTS / "exp206-frozen.json", RESULTS / "exp205-evidence-check.json",
                     Path("tests/exp167_explicit_path_directory.cpp"), Path("tests/periodic_theory_probe.cpp"),
                     Path("validation/exp129_zstd_capacity.cpp"), Path("validation/exp198_mapped_parent.py")]
    paths += [BUILD / name for name in ("probe.cpp", "scaffold.hpp", "periodic_theory_probe.cpp",
                                       "zstd_capacity.cpp", "self-check.json")]
    paths += sorted((BUILD / "src").iterdir())
    old_meta = trees["sources"]["ZSEA[0]"]["metadata"] | {"budget": 1200}
    formal = identity("estimate")
    assert formal["sha256"] == "aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c"
    write(FREEZE, {"experiment": 208, "head": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip(), "identities": [identity(p) for p in paths],
        "remote_inputs": list(map(str, remote)), "compile_command": command,
        "compressor_compile": zcommand, "compiler": subprocess.check_output(
            ["g++", "--version"], text=True).splitlines()[0],
        "zstd_version": version, "zstd_static_library": identity(Path(library).resolve()),
        "source": "ZSEA[0]", "budget": 2400, "old_metadata": old_meta,
        "cpu_core": 3, "timeout_s": 900, "rss_limit_bytes": 2_000_000_000,
        "repetitions": 200, "pairs": 5, "orders": ["old-new", "new-old", "old-new", "new-old", "old-new"],
        "gate": {"new_long_legal_rows_min": 10, "added_oracle_pp_min": 0.01,
                 "single_source_capacity_bytes": (100_000_000 - 80_784_016 - 1_000_000) // 10,
                 "incremental_query_us_max": 5.0, "restore_cpu_s_max": 0.25},
        "disk_available_start_bytes": 475_956_355_072,
        "scope": "known exp174 development requests; identity mapping of one tree; no new exact labels",
        "statistics": "deterministic development accuracy; paired df4 t95 CPU, five pairs; no production claim"})
    print("exp208 frozen after small-tree, terminal, checksum and EOF checks", flush=True)


def local_check():
    folder = BUILD / "selfcheck"
    folder.mkdir()
    result = subprocess.run([str(BINARY), "generate", "doc/eda比赛文件/arch", str(folder), "120"],
                            capture_output=True, text=True, check=True, timeout=60)
    (folder / "generate.stdout").write_text(result.stdout)
    assert not result.stderr
    meta = fields(folder / "generate.stdout")
    requests = folder / "requests.txt"
    requests.write_text("SRB_33_300/ZSEA[0] SRB_33_300/ZSEA[0] 0\n"
                        "SRB_33_300/ZSEA[0] SRB_34_300/ISEA[0] 9\n")
    rows = folder / "rows.csv"
    subprocess.run(query_command(folder / "target.u8", meta, rows, 1, requests, 2),
                   check=True, timeout=60)
    assert [int(r["upper"]) for r in read(rows)] == [0, 9]
    raw, frame = folder / "target.u8", folder / "target.zstd19"
    subprocess.run([str(COMPRESSOR), "19", str(raw), str(frame), "/dev/null", "-"], check=True, timeout=60)
    output = folder / "restored.u8"
    subprocess.run([str(BINARY), "restore", str(frame), str(output)], check=True, timeout=60)
    assert raw.read_bytes() == output.read_bytes()
    damaged = bytearray(frame.read_bytes())
    damaged[-1] ^= 1
    for name, data in (("checksum", damaged), ("eof", frame.read_bytes() + b"\0")):
        bad = folder / f"{name}.zstd19"
        bad.write_bytes(data)
        check = subprocess.run([str(BINARY), "restore", str(bad), "-"], capture_output=True, timeout=60)
        assert check.returncode != 0
    write(BUILD / "self-check.json", {"all_passed": True, "budget": 120, "summary": meta,
          "same_pin_and_zero_hop_terminal": True, "roundtrip": True,
          "corrupt_checksum_rejected": True, "trailing_byte_rejected": True})


def verify(remote=False):
    frozen = json.loads(FREEZE.read_text())
    required = set(frozen["remote_inputs"]) if remote else None
    for entry in frozen["identities"]:
        if required is None or entry["path"] in required:
            assert identity(entry["path"]) == entry, entry["path"]
    return frozen


def measured(name, args, frozen):
    stem = BUILD / name
    command = ["/usr/bin/time", "-f", "%U,%S,%M,%e", "-o", str(stem.with_suffix(".time")),
               "taskset", "-c", str(frozen["cpu_core"]), *map(str, args)]
    with stem.with_suffix(".stdout").open("x") as out, stem.with_suffix(".stderr").open("x") as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
        start, max_threads = time.monotonic(), 0
        while process.poll() is None:
            pending, seen = [process.pid], set()
            while pending:
                pid = pending.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                try:
                    max_threads = max(max_threads, len(list(Path(f"/proc/{pid}/task").iterdir())))
                    pending += [int(p) for p in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
                except (FileNotFoundError, ProcessLookupError):
                    pass
            if time.monotonic() - start > frozen["timeout_s"]:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise TimeoutError(name)
            time.sleep(0.02)
    timing = stem.with_suffix(".time").read_text().split(",")
    assert len(timing) == 4 and process.returncode == 0, name
    user, system, rss, wall = map(float, timing)
    record = {"name": name, "command": command, "returncode": process.returncode,
              "cpu_s": user + system, "wall_s": wall, "rss_bytes": int(rss) * 1024,
              "max_threads": max_threads,
              "files": [identity(stem.with_suffix(s)) for s in (".stdout", ".stderr", ".time")]}
    if stem.with_suffix(".stdout").stat().st_size:
        record["summary"] = fields(stem.with_suffix(".stdout"))
    assert not stem.with_suffix(".stderr").stat().st_size, name
    assert 1 <= max_threads <= 1 and rss * 1024 <= frozen["rss_limit_bytes"], name
    assert user + system <= frozen["timeout_s"] and wall <= frozen["timeout_s"], name
    print(f"{name} cpu={user + system:.3f}s rss={int(rss) * 1024}", flush=True)
    return record


def remote():
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026")
    assert not RUN.exists() and not (BUILD / "remote-run.json").exists()
    frozen = verify(remote=True)
    record = {"experiment": 208, "machine": "r9r4900", "cwd": str(Path.cwd()),
              "freeze": identity(FREEZE), "binary": identity(BINARY), "compressor": identity(COMPRESSOR),
              "cpu": subprocess.check_output(["lscpu"], text=True),
              "environment": subprocess.check_output(
                  ["ps", "-eo", "pid,comm,pcpu", "--sort=-pcpu"], text=True), "runs": []}

    def run(name, args):
        row = measured(name, args, frozen)
        record["runs"].append(row)
        (BUILD / "remote-run.json").write_text(json.dumps(record, indent=2) + "\n")
        return row

    gen = run("generate", [BINARY, "generate", "doc/eda比赛文件/arch", BUILD, 2400])
    meta = gen["summary"]
    assert meta["budget"] == 2400 and meta["bound_errors"] == 0 and meta["threads"] == 1
    for layout, raw in (("dense", BUILD / "parents.u8"), ("target", BUILD / "target.u8")):
        frame = BUILD / f"{layout}.zstd19"
        run(f"compress-{layout}", [COMPRESSOR, 19, raw, frame, "/dev/null", "-"])
        restored = BUILD / f"{layout}-restored.u8"
        run(f"restore-{layout}", [BINARY, "restore", frame, restored])
        assert identity(raw)["sha256"] == identity(restored)["sha256"]
    run("restore-old", [BINARY, "restore", OLD_FRAME, BUILD / "old-restored.u8"])
    assert identity(OLD)["sha256"] == identity(BUILD / "old-restored.u8")["sha256"]
    expected = {}
    for block in range(-1, frozen["pairs"]):
        order = ("old", "new") if block == -1 else frozen["orders"][block].split("-")
        for label in order:
            raw = OLD if label == "old" else BUILD / "target-restored.u8"
            shape = frozen["old_metadata"] if label == "old" else meta
            output = BUILD / f"{label}-{block}.csv"
            row = run(f"query-{label}-{block}", query_command(
                raw, shape, output, frozen["repetitions"]))
            current = identity(output)
            expected.setdefault(label, current["sha256"])
            assert current["sha256"] == expected[label]
            row["output"] = current
    record["outputs"] = [identity(BUILD / name) for name in (
        "parents.u8", "distances.u16", "target.u8", "dense.zstd19", "target.zstd19",
        "dense-restored.u8", "target-restored.u8", "old-restored.u8")]
    record["all_passed"] = True
    write(RUN, record)
    print("EXP208_REMOTE_DONE", flush=True)


def check_tree(meta):
    import numpy as np

    nx, ny = meta["dx_max"] - meta["dx_min"] + 1, meta["dy_max"] - meta["dy_min"] + 1
    parents = np.fromfile(BUILD / "target.u8", dtype=np.uint8).reshape(160, ny, nx)
    dense = np.fromfile(BUILD / "parents.u8", dtype=np.uint8).reshape(nx, ny, 160)
    assert np.array_equal(dense.transpose(2, 1, 0), parents)
    dist = np.fromfile(BUILD / "distances.u16", dtype="<u2").reshape(nx, ny, 160)
    distances = dist.transpose(2, 1, 0).astype(np.int32)
    assert np.array_equal(parents == 255, distances == 65535)
    assert np.sum(parents == 254) == np.sum(distances == 0) == 1
    assert parents[0, -meta["dy_min"], -meta["dx_min"]] == 254
    assert np.all(distances[distances != 65535] <= 2400)
    arch = Path("doc/eda比赛文件/arch")
    nets = {n["from"]: n for n in json.loads((arch / "SRB_Net.json").read_text())["Nets"]}
    names = [p["Name"] for p in json.loads((arch / "SRB_Port.json").read_text())["Port"]
             if p["Name"] in nets]
    arcs = {}
    for arc in json.loads((arch / "SRB_Arc.json").read_text())["Arcs"]:
        key = arc["from"], arc["to"]
        arcs[key] = min(arcs.get(key, arc["delay"]), arc["delay"])
    vx = np.array([nets[n]["delta x"] for n in names])
    vy = np.array([nets[n]["delta y"] for n in names])
    weights = np.array([[arcs.get((nets[p]["to"], q), 65535) for q in names]
                        for p in names], dtype=np.int32)
    certificates = 0
    for z in range(160):
        y, x = np.where(parents[z] < 160)
        p = parents[z, y, x]
        px, py = x - vx[p], y - vy[p]
        assert np.all((px >= 0) & (px < nx) & (py >= 0) & (py < ny))
        before, after = distances[p, py, px], distances[z, y, x]
        assert np.all(before < after) and np.all(before + weights[p, z] == after)
        certificates += len(x)
    relaxations = 0
    for p in range(160):
        x0, x1 = max(0, -vx[p]), min(nx, nx - vx[p])
        y0, y1 = max(0, -vy[p]), min(ny, ny - vy[p])
        allowed = np.zeros((ny, nx), dtype=bool)
        allowed[y0:y1, x0:x1] = True
        assert not np.any((distances[p] <= 2400 - weights[p].min()) & ~allowed)
        before = distances[p, y0:y1, x0:x1]
        for q in np.flatnonzero(weights[p] != 65535):
            after = distances[q, y0 + vy[p]:y1 + vy[p], x0 + vx[p]:x1 + vx[p]]
            parent = parents[q, y0 + vy[p]:y1 + vy[p], x0 + vx[p]:x1 + vx[p]]
            candidate = before + weights[p, q]
            active = candidate <= 2400
            assert np.all(after[active] <= candidate[active])
            assert np.all(parent[active & (after == candidate)] <= p)
            relaxations += int(active.sum())
    assert certificates + 1 == meta["finite"] == meta["settled"]
    assert certificates == meta["parent_certificates"] and relaxations == meta["relaxations"]
    old = np.fromfile(OLD, dtype=np.uint8).reshape(160, 233, 195)
    x, y = -97 - meta["dx_min"], -116 - meta["dy_min"]
    common = parents[:, y:y + 233, x:x + 195]
    old_finite = old != 255
    assert np.array_equal(common[old_finite], old[old_finite])
    assert np.array_equal(distances[:, y:y + 233, x:x + 195] <= 1200, old_finite)
    assert int(np.sum(distances <= 1200)) == int(old_finite.sum())
    return {"parent_certificates": certificates, "bellman_edges": relaxations,
            "old_finite_parents_preserved": int(old_finite.sum()), "layouts_equal": True,
            "minimum_index_optimal_parent": True, "all_passed": True}


def analyze():
    from exp198_mapped_parent import point_of

    frozen = verify()
    assert not REPORT.exists()
    assert subprocess.check_output(["git", "show", f"HEAD:{FREEZE}"]) == FREEZE.read_bytes()
    record = json.loads(RUN.read_text())
    assert record["freeze"] == identity(FREEZE) and record["all_passed"]
    for row in record["outputs"]:
        assert identity(row["path"]) == row
    runs = {r["name"]: r for r in record["runs"]}
    for row in record["runs"]:
        for entry in row["files"] + ([row["output"]] if "output" in row else []):
            assert identity(entry["path"]) == entry
        assert row["returncode"] == 0 and row["max_threads"] == 1
        assert row["rss_bytes"] <= frozen["rss_limit_bytes"] and row["wall_s"] <= frozen["timeout_s"]
    meta = runs["generate"]["summary"]
    tree = check_tree(meta)
    for name, raw in (("dense", BUILD / "parents.u8"), ("target", BUILD / "target.u8"),
                      ("old", OLD)):
        assert identity(BUILD / f"{name}-restored.u8")["sha256"] == identity(raw)["sha256"]
    labels = read(INPUT)
    old, new = read(BUILD / "old-0.csv"), read(BUILD / "new-0.csv")
    features = read("build/exp202/features.csv")
    funnel = read("build/exp206/funnel.csv")
    assert len(old) == len(new) == len(labels) == len(features) == 6176 and len(funnel) == 8 * 6176
    joined = []
    for i, (label, a, b, feature) in enumerate(zip(labels, old, new, features)):
        for row in (a, b):
            assert (int(row["index"]), row["from"], row["to"], row["exact"]) == (
                i, label["from"], label["to"], label["exact"])
            assert sum(int(row[k]) for k in COUNTERS) == int(row["attempts"])
            assert (int(row["upper"]) >= 0) == (int(row["legal"]) > 0)
            if int(row["upper"]) >= 0:
                assert int(row["slack"]) == int(row["upper"]) - int(label["exact"]) >= 0
            assert all(int(row[k]) == 0 for k in
                       ("broken_parent", "hop_cap", "missing_arc", "nominal_budget", "invalid_terminal"))
        assert (feature["from"], feature["to"], feature["exact"]) == (
            label["from"], label["to"], label["exact"])
        modes = funnel[i * 8:(i + 1) * 8]
        for mode, row in enumerate(modes):
            assert (int(row["index"]), int(row["mode"]), row["from"], row["to"]) == (
                i, mode, label["from"], label["to"])
        u7 = min((int(r["upper"]) for r in modes[1:] if int(r["upper"]) >= 0), default=-1)
        count7 = sum(int(r["legal"]) for r in modes[1:])
        assert u7 == int(feature["u"]) and count7 == int(feature["valid_count"])
        assert int(b["legal"]) >= int(a["legal"])
        ua, ub, p, c, exact = map(int, (a["upper"], b["upper"], label["baseline"], feature["c"], label["exact"]))
        assert (min(p, ua) if p > 0 and ua >= 0 else p) == int(label["single"])
        if ua >= 0:
            assert 0 <= ub <= ua
            assert int(modes[0]["legal"]) >= int(a["legal"]) and 0 <= int(modes[0]["upper"]) <= ua
        oracle = lambda base, u: max(point_of(exact, base), point_of(exact, u)) if u >= 0 else point_of(exact, base)
        combined_u = min((u for u in (u7, ub) if u >= 0), default=-1)
        clamp = lambda base, u: min(base, u) if base > 0 and u >= 0 else base
        joined.append({"index": i, "from": label["from"], "to": label["to"], "band": label["band"],
            "weight": float(label["weight"]), "exact": exact, "p": p, "c": c,
            "old_u": ua, "new_u": ub, "old_legal": int(a["legal"]), "new_legal": int(b["legal"]),
            "u0": int(modes[0]["upper"]), "count0": int(modes[0]["legal"]), "u7": u7, "count7": count7,
            "newly_legal": ua < 0 <= ub, "new_to_family": u7 < 0 <= ub,
            "old_oracle": oracle(p, ua), "new_oracle": oracle(p, ub),
            "added_oracle": oracle(c, combined_u) - oracle(c, u7),
            "clamp_gain": point_of(exact, clamp(p, ub)) - point_of(exact, clamp(p, ua))})
    joined_path = RESULTS / "exp208-comparison.csv"
    with joined_path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(joined[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(joined)
    total = math.fsum(r["weight"] for r in joined)
    bands = {}
    for band in BANDS:
        subset = [r for r in joined if r["band"] == band]
        indexes = [r["index"] for r in subset]
        bands[band] = {
            "rows": len(subset), "source_rows": sum(int(old[i]["source_arc"]) >= 0 for i in indexes),
            "old_legal_rows": sum(r["old_u"] >= 0 for r in subset),
            "new_legal_rows": sum(r["new_u"] >= 0 for r in subset),
            "newly_legal_rows": sum(r["newly_legal"] for r in subset),
            "u7_legal_rows": sum(r["u7"] >= 0 for r in subset),
            "new_to_u7_rows": sum(r["new_to_family"] for r in subset),
            "new_coverage_global_percent": 100 * math.fsum(r["weight"] for r in subset if r["newly_legal"]) / total,
            "single_source_oracle_gain_pp": 100 * math.fsum(r["weight"] * (r["new_oracle"] - r["old_oracle"]) for r in subset) / total,
            "added_oracle_pp": 100 * math.fsum(r["weight"] * r["added_oracle"] for r in subset) / total,
            "clamp_gain_pp": 100 * math.fsum(r["weight"] * r["clamp_gain"] for r in subset) / total,
            "old_counters": {k: sum(int(old[i][k]) for i in indexes) for k in COUNTERS},
            "new_counters": {k: sum(int(new[i][k]) for i in indexes) for k in COUNTERS},
            "new_slack_ps": [int(new[i]["slack"]) for i in indexes if int(new[i]["legal"]) > 0]}
    deltas = []
    timing = {}
    for label in ("old", "new"):
        timing[label] = [runs[f"query-{label}-{i}"]["summary"]["query_cpu_s"] /
                         frozen["repetitions"] for i in range(frozen["pairs"])]
    deltas = [b - a for a, b in zip(timing["old"], timing["new"])]
    mean = statistics.mean(deltas)
    width = 2.7764451051977987 * statistics.stdev(deltas) / math.sqrt(len(deltas))
    capacity = {layout: identity(BUILD / f"{layout}.zstd19") for layout in ("dense", "target")}
    selected = min(capacity, key=lambda name: capacity[name]["bytes"])
    size = capacity[selected]["bytes"]
    novel = sum(bands[band]["newly_legal_rows"] for band in ("101-300", "301+"))
    oracle_gain = sum(band["added_oracle_pp"] for band in bands.values())
    gate = frozen["gate"]
    gates = {"coverage": novel >= gate["new_long_legal_rows_min"],
             "oracle": oracle_gain >= gate["added_oracle_pp_min"],
             "capacity_ten_sources_assumption": size <= gate["single_source_capacity_bytes"],
             "query_cost": 1e6 * (mean + width) / 6176 <= gate["incremental_query_us_max"],
             "restore_cost": runs[f"restore-{selected}"]["summary"]["restore_cpu_s"] <= gate["restore_cpu_s_max"]}
    write(REPORT, {"experiment": 208, "freeze": identity(FREEZE), "run": identity(RUN),
        "tree": tree, "summary": meta, "by_band": bands, "comparison": identity(joined_path),
        "capacity": capacity, "selected_layout": selected,
        "same_size_ten_new_sources_plus_selector_and_reserve_bytes": 80_784_016 + 1_000_000 + 10 * size,
        "query_cpu_per_6176_s": timing, "query_difference_s": deltas,
        "query_difference_ci95_s": [mean - width, mean + width],
        "query_difference_us_per_request": 1e6 * mean / 6176,
        "restore": {label: runs[f"restore-{label}"] for label in ("old", "dense", "target")},
        "new_long_legal_rows": novel, "added_oracle_pp": oracle_gain,
        "gates": gates, "pilot_gate": all(gates.values()), "all_correctness_passed": True,
        "limits": "one source identity mapping; known exp174 development labels; oracle is a selection upper bound; "
                  "instrumented query component with warm tables; other sources, production CPU, new requests and platform unverified"})
    print(json.dumps({"summary": meta, "gates": gates, "bytes": size, "new_long_legal_rows": novel,
                      "added_oracle_pp": oracle_gain, "query_delta_us": 1e6 * mean / 6176}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "remote", "analyze"))
    args = parser.parse_args()
    os.chdir(ROOT)
    {"freeze": freeze, "remote": remote, "analyze": analyze}[args.stage]()
