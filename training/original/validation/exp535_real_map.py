#!/usr/bin/env python3
"""Separate complete full-port representation and real-geometry errors on r9."""
import csv
import hashlib
import json
import lzma
import os
from pathlib import Path
import resource
import socket
import struct
import subprocess
import time

import numpy as np

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp535"), Path("build/exp535")
PLAN = Path("experiment/实验535-全端口真实地图的表示误差与几何误差.md")
BASE, LABELS, RECOVERY = Path("../exp532"), Path("../exp499"), Path("../exp534")
REAL, PUBLISHED = Path("../exp501"), Path("../exp502")
ROWS, NL, NR, RANK = 1_000_000, 66560, 13248, 128
ARMS = ("oracle_original", "oracle_compressed", "model_original", "model_compressed", "exp354")
read = lambda path: json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert (actual["bytes"], actual["sha256"]) == (expected["bytes"], expected["sha256"]), str(path)
    return actual


def coordinates(query, transformed):
    sx, sy, tx, ty = query[:, :4].T
    if transformed:
        sx = sx - 14 * ((sy % 100 < 50) & (sx >= 90))
        tx = tx - 14 * ((ty % 100 < 50) & (tx >= 90))
    return tx - sx, ty - sy


def keys(query, transformed):
    x, y = coordinates(query, transformed)
    dx, dy, ax, ay = (x < 0).astype(int), (y < 0).astype(int), np.abs(x), np.abs(y)
    sf, sl, tf, tl = query[:, 4:8].T
    p = [(sl >> bit & 1) + 2 * (tl >> bit & 1) for bit in range(3)]
    left = (((((sf * 4 + p[0]) * 4 + p[1]) * 4 + p[2]) * 2 + tf % 2) * 2 + dx)
    row = ax % 10 * 6656 + left
    column = (12 * dy + ay % 12) * 552 + (ax // 10) * 46 + ay // 12
    # Invert all mixed-radix fields independently of the forward expression.
    value = left.copy()
    recovered_dx, value = value % 2, value // 2
    low, value = value % 2, value // 2
    digits = []
    for _ in range(3):
        digits.append(value % 4)
        value //= 4
    assert np.array_equal(value, sf) and np.array_equal(recovered_dx, dx)
    assert np.array_equal(low, tf % 2)
    assert np.array_equal(sum((digits[2 - k] % 2) * 2 ** k for k in range(3)), sl)
    assert np.array_equal(sum((digits[2 - k] // 2) * 2 ** k for k in range(3)), tl)
    assert np.all((0 <= ax) & (ax <= 119) & (0 <= ay) & (ay <= 549))
    assert np.all((0 <= row) & (row < NL) & (0 <= column) & (column < NR))
    return row, column, ax, ay, dx, dy


def inputs(mapping, label_report, output_report):
    requests = REAL / label_report["input"]["path"]
    exact = REAL / label_report["exact"]["path"]
    published = PUBLISHED / "build/exp502/C1.csv"
    expected = next(r["output"] for r in output_report["runs"] if r["name"] == "C1")
    identities = [check(p, row) for p, row in zip(
        (requests, exact, published), (label_report["input"], label_report["exact"], expected))]
    sources, targets = [dict(zip(mapping[k], range(len(mapping[k])))) for k in ("sources", "targets")]
    sc, tc = [np.asarray(mapping[k + "_coordinates"]) for k in ("source", "target")]
    query = np.empty((ROWS, 10), dtype="<i4")
    indices = np.empty((ROWS, 2), dtype=np.int32)
    truth, production, cluster = [np.empty(ROWS, dtype=np.int64) for _ in range(3)]
    clusters, seen = {}, set()
    counts = np.zeros((208, 288), dtype=np.int64)
    with requests.open(newline="") as a, exact.open(newline="") as b, published.open(newline="") as c:
        readers = [csv.reader(s) for s in (a, b, c)]
        assert next(readers[0]) == ["From", "To"]
        assert next(readers[1]) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        assert next(readers[2]) == ["From", "To", "delay"]
        for i in range(ROWS):
            request, label, baseline = [next(r) for r in readers]
            assert len(request) == 2 and len(label) == 7 and len(baseline) == 3
            assert label[0] == str(i) and label[1:3] == request == baseline[:2]
            pair = tuple(request)
            assert pair not in seen
            seen.add(pair)
            parsed = [pin.split("/", 1) for pin in request]
            cells = [tuple(map(int, p[0][4:].split("_"))) for p in parsed]
            assert all(p[0].startswith("SRB_") for p in parsed)
            s, t = sources[parsed[0][1]], targets[parsed[1][1]]
            indices[i] = s, t
            query[i] = (*cells[0], *cells[1], *sc[s], *tc[t],
                        mapping["source_ids"][s], mapping["target_ids"][t])
            truth[i], production[i] = int(label[3]), int(baseline[2])
            assert str(truth[i]) == label[3] and str(production[i]) == baseline[2]
            assert truth[i] >= 0 and production[i] >= 0
            counts[s, t] += 1
            cluster[i] = clusters.setdefault(request[0], len(clusters))
        assert all(next(r, None) is None for r in readers)
    assert np.all(counts > 0) and int(counts.sum()) == ROWS
    for mode in range(2):
        keys(query, mode)
    instances = read("doc/eda比赛文件/arch/SRB_Inst.json")["Inst"]
    valid = np.zeros((120, 550), dtype=bool)
    for row in instances:
        valid[row["x"], row["y"]] = True
    assert valid.sum() == 60200
    assert valid[query[:, 0], query[:, 1]].all() and valid[query[:, 2], query[:, 3]].all()
    with (BUILD / "queries.bin").open("xb") as stream:
        stream.write(b"EX535Q01" + struct.pack("<I", ROWS))
        stream.write(query.tobytes())
    return query, indices, truth, production, cluster, dict(
        inputs=identities, unique_rows=len(seen), min_pair_rows=int(counts.min()),
        clusters=len(clusters), pairs=int(np.count_nonzero(counts)), rows=ROWS,
        queries=identity(BUILD / "queries.bin"))


def oracle(query, indices, mapping, fields):
    answer = np.empty((ROWS, 2), dtype="<i4")
    restored = []
    for s, field in enumerate(fields):
        assert field["number"] == s and field["source"] == mapping["sources"][s]
        path = LABELS / field["asset"]["path"]
        asset = check(path, field["asset"])
        raw = lzma.decompress(path.read_bytes())
        assert len(raw) == field["raw_bytes"] and hashlib.sha256(raw).hexdigest() == field["raw_sha256"]
        assert raw[:8] == b"EX499D01"
        assert struct.unpack("<6i", raw[8:32]) == (mapping["source_ids"][s], 288, 4, 120, 12, 46)
        assert np.array_equal(np.frombuffer(raw, "<i4", offset=32, count=288), mapping["target_ids"])
        values = np.frombuffer(raw, "<i2", offset=1184).reshape(4, 10, 12, 288, 552)
        selected = np.flatnonzero(indices[:, 0] == s)
        for mode in range(2):
            _, _, ax, ay, dx, dy = keys(query[selected], mode)
            value = values[2 * dx + dy, ax % 10, ay % 12, indices[selected, 1],
                           ax // 10 * 46 + ay // 12].astype(np.int32)
            value += 125 * (ax // 10) + np.where(dy, 125, 127) * (ay // 12)
            assert np.all(value >= 0)
            answer[selected, mode] = value
        restored.append(dict(source=s, rows=len(selected), asset=asset, complete_raw_sha_checked=True))
        print("EXP535_SOURCE_EXTRACTED", s, flush=True)
    answer.tofile(BUILD / "oracle.i32")
    write(ROOT / "oracle.json", dict(complete=True, sources=restored,
                                   output=identity(BUILD / "oracle.i32")))
    return answer


def model(query, recovery):
    tables = RECOVERY / recovery["table_asset"]["path"]
    check(tables, recovery["table_asset"])
    assert recovery["complete_table_recovery"] and recovery["complete_port_domain"]
    compiler = subprocess.check_output(["g++", "--version"], text=True)
    help_text = subprocess.check_output(["g++", "--help=common"], text=True)
    assert "-ffp-contract" in help_text
    binary = BUILD / "predict"
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror",
               "-static", "-march=x86-64", "-mtune=generic", "-ffp-contract=off",
               "tests/exp535_real_map.cpp", "-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True)
    write(ROOT / "build.json", dict(command=command, compiler=compiler, exit_code=result.returncode,
                                   stdout=result.stdout, stderr=result.stderr))
    assert result.returncode == 0 and not result.stderr, result.stderr
    output = BUILD / "model.i32"
    started = time.monotonic()
    with (ROOT / "query.stdout").open("xb") as out, (ROOT / "query.stderr").open("xb") as err:
        child = subprocess.Popen([str(binary), str(tables), str(BUILD / "queries.bin"), str(output)],
                                 stdout=out, stderr=err)
        threads = 0
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            tasks = Path(f"/proc/{child.pid}/task")
            if tasks.exists():
                threads = max(threads, len(list(tasks.iterdir())))
            time.sleep(.05)
    record = dict(exit_code=os.waitstatus_to_exitcode(status), cpu_s=usage.ru_utime + usage.ru_stime,
                  rss_bytes=usage.ru_maxrss * 1024, wall_s=time.monotonic() - started,
                  threads=threads)
    write(ROOT / "query-run.json", record)
    assert record["exit_code"] == 0 and record["threads"] == 1
    assert record["rss_bytes"] <= 2000000000 and record["wall_s"] <= 3600
    metrics = read(ROOT / "query.stderr")
    assert metrics["rows"] == ROWS and metrics["predictions"] == 2 * ROWS
    assert metrics["table_bytes"] == 735510528
    actual = np.fromfile(output, "<i4").reshape(ROWS, 2)
    table = np.memmap(tables, mode="r", dtype="<f4", shape=(18, (NL + NR) * RANK))
    for mode in range(2):
        row, column, ax, ay, _, dy = keys(query, mode)
        for q in range(18):
            selected = np.flatnonzero(query[:, 6] // 2 == q)
            values = np.zeros(len(selected))
            for k in range(RANK):
                values += table[q, row[selected] * RANK + k].astype(float) * \
                          table[q, NL * RANK + column[selected] * RANK + k].astype(float)
            i, j = ax[selected] // 10, ay[selected] // 12
            values = values * (128 + 125 * i + 125 * j) + 125 * i + np.where(dy[selected], 125, 127) * j
            expected = np.maximum(0, np.copysign(np.floor(np.abs(values) + .5), values)).astype(np.int32)
            zero = (ax[selected] == 0) & (ay[selected] == 0) & (query[selected, 8] == query[selected, 9])
            expected[zero] = 0
            assert np.array_equal(actual[selected, mode], expected), (mode, q)
    write(ROOT / "model.json", dict(complete=True, predictions_checked=2 * ROWS,
                                  threads=threads, output=identity(output), binary=identity(binary)))
    return actual


def points(pred, gold):
    positive = gold > 0
    result = (pred == gold).astype(float) * 100
    result[positive] = 100 * (1 - np.tanh(4 * np.abs(pred[positive] - gold[positive]) / gold[positive]))
    return result


def statistics(pred, gold):
    error = pred.astype(np.int64) - gold
    return dict(rows=len(gold), accuracy_pp=float(points(pred, gold).mean()),
                mean_error_ps=float(error.mean()), mae_ps=float(np.abs(error).mean()),
                squared_ps=int(np.dot(error, error)), exact_rows=int(np.sum(error == 0)),
                under_rows=int(np.sum(error < 0)), over_rows=int(np.sum(error > 0)))


def decompose(truth, nominal, predicted, line):
    result = []
    for mode in range(2):
        geometry = truth - nominal[:, mode] - line
        representation = nominal[:, mode].astype(np.int64) - predicted[:, mode]
        complete = truth - predicted[:, mode] - line
        assert np.array_equal(complete, geometry + representation)
        g, r, c = [int(np.dot(a, a)) for a in (geometry, representation, complete)]
        cross = 2 * int(np.dot(geometry, representation))
        assert c == g + r + cross
        result.append(dict(mode=mode, geometry_squared_ps=g, representation_squared_ps=r,
                           cross_squared_ps=cross, total_squared_ps=c))
    return result


def score(query, truth, production, clusters, nominal, predicted):
    sx, sy, tx, ty = query[:, :4].T
    gaps = read("doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]["Line"]
    line = np.zeros(ROWS, dtype=np.int32)
    for gap in gaps:
        a, b = (sx, tx) if gap["direction"] == "vertical" else (sy, ty)
        line += gap["delay"] * ((np.minimum(a, b) <= gap["site"]) & (gap["site"] < np.maximum(a, b)))
    predictions = np.column_stack((nominal + line[:, None], predicted + line[:, None], production))
    summary = {arm: statistics(predictions[:, i], truth) for i, arm in enumerate(ARMS)}
    previous = read("validation/results/exp506/report.json")
    assert abs(summary["exp354"]["accuracy_pp"] - previous["metrics"]["accuracy_all"]) < 1e-9
    decomposition = decompose(truth, nominal, predicted, line)
    x, y = tx - sx, ty - sy
    distance = np.abs(x) + np.abs(y)
    boundary = np.minimum.reduce((sx, 119 - sx, tx, 119 - tx, sy, 549 - sy, ty, 549 - ty))
    sides = lambda a: np.where(a < 76, 0, np.where(a < 90, 1, 2))
    partitions = dict(
        source_family=query[:, 4], target_family=query[:, 6],
        role=(query[:, 4] >= 20).astype(int) * 2 + (query[:, 6] >= 20),
        direction=(x < 0).astype(int) * 2 + (y < 0),
        near_axis=((np.abs(x) < 20) | (np.abs(y) < 24)).astype(int),
        distance=np.searchsorted([24, 100, 300], distance, side="right"),
        boundary=np.searchsorted([6, 12, 24], boundary, side="right"),
        block_sides=3 * sides(sx) + sides(tx),
        row_band=2 * (sy % 100 < 50).astype(int) + (ty % 100 < 50),
        line_cost=np.searchsorted([100, 400, 800], line, side="right"))
    groups = {}
    for name, values in partitions.items():
        total_rows = 0
        for value in np.unique(values):
            selected = values == value
            total_rows += int(selected.sum())
            groups[f"{name}/{value}"] = {arm: statistics(predictions[selected, i], truth[selected])
                                        for i, arm in enumerate(ARMS)}
            groups[f"{name}/{value}"]["decomposition"] = decompose(
                truth[selected], nominal[selected], predicted[selected], line[selected])
        assert total_rows == ROWS
        for arm in ARMS:
            weighted = sum(v[arm]["rows"] * v[arm]["accuracy_pp"]
                           for k, v in groups.items() if k.startswith(name + "/")) / ROWS
            assert abs(weighted - summary[arm]["accuracy_pp"]) < 1e-9
    delta = points(predictions[:, 1], truth) - points(predictions[:, 0], truth)
    counts = np.bincount(clusters)
    sums = np.bincount(clusters, weights=delta)
    rng = np.random.default_rng(20261020535)
    draws = []
    for _ in range(2000):
        selected = rng.integers(len(counts), size=len(counts))
        draws.append(float(sums[selected].sum() / counts[selected].sum()))
    ci = np.quantile(draws, [.025, .975]).tolist()
    reduction = 1 - decomposition[1]["geometry_squared_ps"] / max(1, decomposition[0]["geometry_squared_ps"])
    hypotheses = dict(
        geometry_dominant=summary["oracle_original"]["accuracy_pp"] < 99.25 and
        decomposition[0]["geometry_squared_ps"] >= 2 * decomposition[0]["representation_squared_ps"],
        coordinate_sufficient=reduction >= .2 and float(delta.mean()) >= .05 and ci[0] > 0)
    return dict(statistics=summary, groups=groups, decomposition=decomposition, hypotheses=hypotheses,
                geometry_squared_reduction=reduction,
                paired_oracle_coordinate=dict(delta_pp=float(delta.mean()), ci95_pp=ci,
                    unit="complete source pin", clusters=len(counts), draws=2000, seed=20261020535))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp535")
    assert os.environ.get("OPENBLAS_NUM_THREADS") == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (7200, 7200))
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    started, begin = time.monotonic(), time.process_time()
    label_report = read("validation/results/exp501/report.json")
    output_report = read("validation/results/exp502/report.json")
    assert label_report["all_complete_label_checks"] and output_report["all_full_contract_checks"]
    mapping = read(BASE / "validation/results/exp532/mapping.json")
    fields = read("validation/results/exp500-preparation/fields.json")
    assert len(fields) == 208 and len(mapping["sources"]) == 208 and len(mapping["targets"]) == 288
    for side in ("source", "target"):
        assert all((coordinate[0] < 20) == port.startswith("Z")
                   for port, coordinate in zip(mapping[side + "s"], mapping[side + "_coordinates"]))
    files = [Path(__file__).resolve().relative_to(Path.cwd()),
             Path("validation/exp208_nominal_parent_tree.py"), Path("tests/exp535_real_map.cpp"), PLAN,
             BASE / "validation/results/exp532/mapping.json",
             BASE / "validation/results/exp532/construction.json",
             RECOVERY / "validation/results/exp534/report.json",
             *[Path("validation/results") / path for path in
               ("exp501/report.json", "exp502/report.json", "exp506/report.json",
                "exp500-preparation/fields.json")],
             *sorted(Path("doc/eda比赛文件/arch").glob("*.json"))]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files], rows=ROWS,
        sources=208, targets=288, pairs=59904, modes=["original", "compressed"], threads=1,
        host=socket.gethostname(), arms=ARMS, new_labels=0, new_training=0))
    (ROOT / "protocol-original.md").write_bytes(PLAN.read_bytes())
    query, indices, truth, production, cluster, input_record = inputs(mapping, label_report, output_report)
    write(ROOT / "input.json", input_record)
    nominal = oracle(query, indices, mapping, fields)
    predicted = model(query, read(RECOVERY / "validation/results/exp534/report.json"))
    result = score(query, truth, production, cluster, nominal, predicted)
    new_bytes = sum(p.stat().st_size for p in BUILD.iterdir() if p.is_file())
    assert new_bytes <= 500000000
    result.update(complete_port_validation=True, rows=ROWS, sources=208, targets=288, pairs=59904,
                  all_passed=True, host=socket.gethostname(), cpu_s=time.process_time() - begin,
                  wall_s=time.monotonic() - started,
                  rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                  new_asset_bytes=new_bytes,
                  production_cpu_validated=False, independent_holdout_validated=False,
                  dataset_status="Previously viewed complete full-port development requests.",
                  scope="Real-map mechanism diagnosis; production and hidden 1B performance remain unverified.")
    write(ROOT / "report.json", result)
    print("EXP535_COMPLETE", result["statistics"], result["hypotheses"], flush=True)


if __name__ == "__main__":
    main()
