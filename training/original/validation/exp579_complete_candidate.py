#!/usr/bin/env python3
"""Build and qualify one frozen full-port standalone candidate on r9."""
import csv
import inspect
import json
import math
import os
from pathlib import Path
import resource
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import time

import numpy as np
import xgboost as xgb

import exp557_evaluate as reuse
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp579"), Path("build/exp579")
PLAN = Path("experiment/实验579-分组微型残差的完整静态程序.md")
OLD = Path("../exp576")
real, trees, read = reuse.real, reuse.trees, reuse.read
ROWS, SEED = 1000000, 20261020554


def measured(command, name):
    started = time.monotonic()
    with (ROOT / (name + ".stdout")).open("xb") as out, (ROOT / (name + ".stderr")).open("xb") as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        threads = 0
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            try:
                threads = max(threads, len(list(Path(f"/proc/{child.pid}/task").iterdir())))
            except FileNotFoundError:
                pass
            time.sleep(.001)
    record = dict(command=command, exit_code=os.waitstatus_to_exitcode(status), threads=threads,
                  cpu_s=usage.ru_utime + usage.ru_stime, wall_s=time.monotonic() - started,
                  rss_bytes=usage.ru_maxrss * 1024)
    write(ROOT / (name + ".run.json"), record)
    assert record["exit_code"] == 0, record
    return record


def geometry():
    record = read("../exp575/validation/results/exp575-evaluation/N192-geometry.json")
    path = Path("../exp575") / record["model"]["path"]
    real.check(path, record["model"])
    raw = path.read_bytes()
    assert raw[:8] == b"EX575Q01" and len(raw) == 86420800
    at = 64 + 59904 * 2
    certificates = []
    with (BUILD / "geometry.bin").open("xb") as stream:
        stream.write(raw[:at])
        for rank, count in ((192, 4800), (96, 260160)):
            le = np.frombuffer(raw, "<i4", rank, at); at += 4 * rank
            left = np.frombuffer(raw, "<i2", 59904 * rank, at).reshape(59904, rank); at += 2 * left.size
            re = np.frombuffer(raw, "<i4", rank, at); at += 4 * rank
            right = np.frombuffer(raw, "<i2", count * rank, at).reshape(count, rank); at += 2 * right.size
            exponent = le + re
            minimum = int(exponent.min())
            lm = np.max(np.abs(left.astype(np.int32)), axis=0).astype(np.int64)
            rm = np.max(np.abs(right.astype(np.int32)), axis=0).astype(np.int64)
            bound = sum(int(a) * int(b) * 2 ** (int(e) - minimum) for a, b, e in zip(lm, rm, exponent))
            assert bound <= 2**53 and lm.max() <= 32767 and rm.max() <= 32767
            assert -500 < minimum <= int(exponent.max()) < 500 and exponent.max() - minimum <= 31
            order = np.argsort(exponent, kind="stable")
            for value in (le[order], left[:, order], re[order], right[:, order]):
                stream.write(value.tobytes(order="C"))
            certificates.append(dict(rank=rank, columns=count, integer_absolute_sum_bound=bound,
                common_exponent=minimum, exponent_span=int(exponent.max()) - minimum, order=order.tolist()))
    assert at == len(raw)
    write(ROOT / "geometry-certificate.json", dict(original=record, reordered=identity(BUILD / "geometry.bin"),
          parts=certificates, complete_factor_bounds=True))


def expanded(path):
    model = read(path)["learner"]
    assert float(model["learner_model_param"]["base_score"]) == 0
    all_trees = model["gradient_booster"]["model"]["trees"]
    assert len(all_trees) == 8
    feature = np.zeros((15, 8), dtype="u1")
    threshold = np.zeros((15, 8), dtype="<i2")
    value = np.zeros((8, 16), dtype="<f4")
    for t, tree in enumerate(all_trees):
        assert not tree["categories"] and not any(tree["split_type"])
        left, right, splits, cuts = [tree[n] for n in ("left_children", "right_children", "split_indices", "split_conditions")]
        def visit(node, depth, offset):
            if depth == 4:
                assert left[node] < 0
                value[t, offset] = cuts[node]
                return
            at = (1 << depth) - 1 + offset
            if left[node] < 0:
                feature[at, t], threshold[at, t] = 0, 32767
                visit(node, depth + 1, 2 * offset)
                visit(node, depth + 1, 2 * offset + 1)
            else:
                cut = np.float32(cuts[node])
                assert float(cut).is_integer() and -32768 <= cut <= 32767 and 0 <= splits[node] < 53
                feature[at, t], threshold[at, t] = splits[node], int(cut)
                visit(left[node], depth + 1, 2 * offset)
                visit(right[node], depth + 1, 2 * offset + 1)
        visit(0, 0, 0)
    return feature.ravel(), threshold.ravel(), value.ravel()


def emit_models(mapping, ports, query, final_paths, geometry_bytes):
    count = len(read("doc/eda比赛文件/arch/SRB_Port.json")["Port"])
    out = ["#pragma once", "#include <cstdint>", f"constexpr int kPortCount={count};",
           f"constexpr uint64_t kGeometryBytes={geometry_bytes};"]
    def array(name, data, ctype="int16_t"):
        out.append(f"static constexpr {ctype} {name}[]={{" + ",".join(map(str, data)) + "};")
    for side, prefix, key in ((0, "Source", "source"), (1, "Target", "target")):
        ids = np.asarray(mapping[key + "_ids"])
        size = 208 if side == 0 else 288
        assert len(ids) == size and np.unique(ids).size == size
        index = np.full(count, -1, dtype=np.int32); index[ids] = np.arange(size)
        coordinates = np.asarray(mapping[key + "_coordinates"])
        assert np.array_equal(ids[ports[:, side]], query[:, 8 + side])
        assert np.array_equal(coordinates[ports[:, side]], query[:, 4 + side * 2:6 + side * 2])
        array("k" + prefix + "Index", index)
        array("k" + prefix + "Family", coordinates[:, 0])
        array("k" + prefix + "Lane", coordinates[:, 1])
    cycles = read("../exp536/validation/results/exp536/oracle.json")
    assert cycles["complete"] and len(cycles["sources"]) == 208
    array("kCycles", [r["cycle_ps"] for r in cycles["sources"]])
    out += ["struct TinyModel { uint8_t feature[120]; int16_t threshold[120]; float value[128]; };",
            "alignas(64) static constexpr TinyModel kModels[]={"]
    old = read(OLD / "validation/results/exp576/R8.json")
    old_paths = [OLD / row["assets"]["json"]["path"] for row in old["records"]]
    for row, path in zip(old["records"], old_paths):
        real.check(path, row["assets"]["json"])
    assert [(r["fold"], r["route"]) for r in old["records"]] == [(f, g) for f in range(3) for g in range(16)]
    for i, path in enumerate(final_paths + old_paths):
        if i == 16:
            out.append("#ifdef EXP579_AUDIT")
        feature, threshold, value = expanded(path)
        values = [",".join(map(str, feature)), ",".join(map(str, threshold)),
                  ",".join(float(v).hex() + "f" for v in value)]
        out.append("{" + ",".join("{" + v + "}" for v in values) + "},")
    out += ["#endif", "};", ""]
    (BUILD / "exp579-models.h").write_text("\n".join(out))


def build():
    helped = subprocess.check_output(["g++", "--help=optimizers"], text=True)
    assert "-ffp-contract" in helped
    (ROOT / "compiler-help.txt").write_text(helped)
    (ROOT / "installed-xgboost-help.txt").write_text(str(inspect.signature(xgb.train)) + "\n" + xgb.train.__doc__)
    reuse.previous.ROOT, trees.BUILD = ROOT, BUILD
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = reuse.previous.data()
    assert matrix.shape == (ROWS, 53) and read(ROOT / "input.json")["unique_rows"] == ROWS
    base = np.fromfile("../exp575/build/exp575/N192-base.i32", "<i4").astype(np.int64)
    assert base.shape == (ROWS,) and np.array_equal(labels[:, 2], event[:, 7] + event[:, 6])
    old_base = read("../exp575/validation/results/exp575-evaluation/N192-geometry.json")["base"]
    real.check(Path("../exp575") / old_base["path"], old_base)
    x, y = query[:, 2] - event[:, 0] + event[:, 2], query[:, 3] - event[:, 1] + event[:, 3]
    routes = (4 * (2 * (x < 0) + (y < 0)) + 2 * (np.abs(x) >= 20) + (np.abs(y) >= 24)).astype("u1")
    with (BUILD / "queries.bin").open("xb") as stream:
        stream.write(b"EX535Q01" + struct.pack("<I", ROWS)); stream.write(query.tobytes())
    folds.tofile(BUILD / "folds.u8")
    params = dict(objective="reg:absoluteerror", tree_method="hist", max_depth=4, eta=.3, max_bin=256,
                  base_score=0, subsample=1., colsample_bytree=1., seed=SEED, nthread=4)
    native = np.empty(ROWS, dtype="<f4")
    paths, records = [], []
    for route in range(16):
        mask = routes == route
        weights = (1000 / np.maximum(labels[mask, 1] + labels[mask, 2], 128)).astype("<f4")
        dm = xgb.DMatrix(matrix[mask], label=(labels[mask, 1] - base[mask]).astype("<f4"), weight=weights, nthread=4)
        booster = xgb.train(params, dm, num_boost_round=8)
        assets = trees.export_model(booster, f"R8-final-{route}")
        native[mask] = booster.predict(dm)
        paths.append(BUILD / f"R8-final-{route}.json")
        records.append(dict(route=route, rows=int(mask.sum()), assets=assets))
    native.tofile(BUILD / "final-native.f32")
    write(ROOT / "training.json", dict(params=params, rounds=8, records=records,
          native=identity(BUILD / "final-native.f32"), heldout_used_for_training=False, xgboost_version=xgb.__version__))
    geometry()
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    finish_build(mapping, ports, query, paths)


def finish_build(mapping, ports, query, paths):
    emit_models(mapping, ports, query, paths, (BUILD / "geometry.bin").stat().st_size)
    generator = ["python3", "scripts/gen_embedded_arch.py", "--out", str(BUILD)]
    measured(generator, "embed-arch")
    assembly = '.section .rodata.exp579,"a",@progbits\n.balign 64\n.global exp579_geometry\nexp579_geometry:\n.incbin "' + str((BUILD / "geometry.bin").resolve()) + '"\n.section .note.GNU-stack,"",@progbits\n'
    (BUILD / "geometry.S").write_text(assembly)
    common = ["g++", "-std=c++17", "-O3", "-fno-rtti", "-fno-fast-math", "-ffp-contract=off", "-march=x86-64",
              "-mtune=generic", "-Wall", "-Wextra", "-Werror", "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-I", "src", "-I", str(BUILD)]
    measured(common + ["-c", "src/architecture.cpp", "-o", str(BUILD / "architecture.o")], "compile-architecture")
    measured(common + ["-c", str(BUILD / "embedded_arch.cpp"), "-o", str(BUILD / "arch-text.o")], "compile-arch-text")
    measured(["g++", "-c", str(BUILD / "geometry.S"), "-o", str(BUILD / "geometry.o")], "compile-geometry")
    for name, flags in (("estimate", []), ("audit", ["-DEXP579_AUDIT"])):
        command = common + ["-fno-exceptions", *flags, "tests/exp579_complete_candidate.cpp",
            str(BUILD / "architecture.o"), str(BUILD / "arch-text.o"), str(BUILD / "geometry.o"),
            "-static", "-s", "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc", "-o", str(BUILD / name)]
        measured(command, "compile-" + name)
        assert not (ROOT / ("compile-" + name + ".stderr")).read_bytes()
        assert (BUILD / name).stat().st_size < 100000000
    static = subprocess.run(["ldd", str(BUILD / "estimate")], text=True, capture_output=True)
    assert "=>" not in static.stdout + static.stderr and "not a dynamic executable" in static.stdout + static.stderr
    (ROOT / "ldd.txt").write_text(static.stdout + static.stderr)
    write(ROOT / "candidate-freeze.json", dict(binary=identity(BUILD / "estimate"),
          audit=identity(BUILD / "audit"), model_header=identity(BUILD / "exp579-models.h"),
          geometry=identity(BUILD / "geometry.bin"), protocol=identity(ROOT / "protocol-original.md"),
          sources=[identity(p) for p in [Path(__file__), Path("tests/exp579_complete_candidate.cpp"),
                   Path("src/architecture.cpp"), Path("src/architecture.h"), Path("src/csv.h"),
                   Path("scripts/gen_embedded_arch.py"), *Path("doc/eda比赛文件/arch").glob("*.json")]],
          compiler=subprocess.check_output(["g++", "--version"], text=True), heldout_scores_seen=False,
          full_port_pairs=59904, training=identity(ROOT / "training.json")))
    print("EXP579_FROZEN_COMPLETE_ELF", identity(BUILD / "estimate"), flush=True)


def audit():
    labels, query, ports, event, matrix, folds, cluster, oracle, production, prior = reuse.previous.data()
    dtype = np.dtype(dict(names=["features", "response", "base", "mandatory", "prediction", "raw"],
        formats=[("<f4", (53,)), "<f8", "<i4", "<i4", "<i4", "<f4"], offsets=[0, 216, 224, 228, 232, 236], itemsize=240))
    results = {}
    for name, mode in (("oof", 0), ("final", 1)):
        output = BUILD / (name + "-trace.bin")
        record = measured([str(BUILD / "audit"), str(BUILD / "queries.bin"), str(BUILD / "folds.u8"),
                           str(output), str(mode)], "audit-" + name)
        trace = np.memmap(output, dtype=dtype, mode="r", shape=(ROWS,))
        assert output.stat().st_size == ROWS * dtype.itemsize
        assert np.array_equal(trace["features"].view("u4"), matrix.view("u4")), "online feature mismatch"
        base = np.fromfile("../exp575/build/exp575/N192-base.i32", "<i4")
        response = np.fromfile("../exp575/build/exp575/N192-geometry.f64", "<f8")
        assert np.array_equal(trace["response"].view("u8"), response.view("u8")), "background double mismatch"
        assert np.array_equal(trace["base"], base) and np.array_equal(trace["mandatory"], labels[:, 2])
        raw_path = OLD / "build/exp576/R8.f32" if mode == 0 else BUILD / "final-native.f32"
        raw = np.fromfile(raw_path, "<f4")
        assert np.array_equal(trace["raw"].view("u4"), raw.view("u4")), "native residual mismatch"
        expected = trees.decode(raw, base, labels[:, 2])
        assert np.array_equal(trace["prediction"], expected), "integer output mismatch"
        expected.astype("<i4").tofile(BUILD / (name + "-expected.i32"))
        results[name] = dict(run=record, trace=identity(output), exact_features=True, bitwise_background=True,
            bitwise_residual=True, exact_integer_output=True, statistics=real.statistics(expected, labels[:, 0]),
            expected=identity(BUILD / (name + "-expected.i32")))
    write(ROOT / "audit.json", results)
    print("EXP579_FULL_PORT_ONLINE_AUDIT_PASSED", flush=True)


def check_output(request, output, exact, expected=None):
    prediction, truth, pairs = np.empty(ROWS, dtype=np.int64), np.empty(ROWS, dtype=np.int64), set()
    family = np.empty(ROWS, dtype=np.int32)
    distance, near_axis, direction = [np.empty(ROWS, dtype="u1") for _ in range(3)]
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    families = dict(zip(mapping["sources"], [v[0] for v in mapping["source_coordinates"]]))
    known = set()
    with request.open(newline="") as a, output.open(newline="") as b, exact.open(newline="") as c:
        ra, rb, rc = csv.reader(a), csv.reader(b), csv.reader(c)
        assert next(ra) == ["From", "To"] and next(rb) == ["From", "To", "delay"]
        assert next(rc) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        for i, (q, p, t) in enumerate(zip(ra, rb, rc, strict=True)):
            assert i < ROWS and len(q) == 2 and len(p) == 3 and len(t) == 7
            assert p[:2] == q == t[1:3] and t[0] == str(i)
            prediction[i], truth[i] = int(p[2]), int(t[3])
            assert p[2] == str(prediction[i]) and prediction[i] >= 0
            key = tuple(q); assert key not in known; known.add(key)
            pairs.add(tuple(pin.split("/", 1)[1] for pin in q))
            family[i] = families[q[0].split("/", 1)[1]]
            cells = [tuple(map(int, pin.split("/", 1)[0][4:].split("_"))) for pin in q]
            dx, dy = cells[1][0] - cells[0][0], cells[1][1] - cells[0][1]
            distance[i] = np.searchsorted([24, 100, 300], abs(dx) + abs(dy), side="right")
            near_axis[i] = abs(dx) < 20 or abs(dy) < 24
            direction[i] = 2 * (dx < 0) + (dy < 0)
        assert i + 1 == ROWS and len(pairs) == 59904
    assert output.read_bytes().endswith(b"\n")
    if expected is not None:
        assert np.array_equal(prediction, np.fromfile(expected, "<i4"))
    return prediction, truth, dict(input=identity(request), output=identity(output), labels=identity(exact),
        rows=ROWS, unique_rows=len(known), port_pairs=len(pairs), contract_passed=True,
        statistics=real.statistics(prediction, truth)), dict(source_family=family, distance=distance,
        near_axis=near_axis, direction=direction)


def qualify():
    frozen = read(ROOT / "candidate-freeze.json")
    real.check(BUILD / "estimate", frozen["binary"])
    assert read(ROOT / "audit.json")["oof"]["exact_integer_output"]
    # Each complete output is checked once; unchanged byte-identical repeats reuse it.
    cases = [("development", Path("../exp501/build/exp501/u-role/requests.csv"), Path("../exp501/build/exp501/exact.csv")),
             ("independent", Path("../exp562/build/exp562/u-role/requests.csv"), Path("../exp562/build/exp562/exact.csv"))]
    baseline = Path("../../build/exp320/narrow/estimate")
    assert identity(baseline)["sha256"] == "14b6fea221e7158c6acab1a51768a9e83ba7e570f5744e6416490cd1ffae1b1a"
    write(ROOT / "timing-freeze.json", dict(candidate=frozen["binary"], baseline=identity(baseline),
        baseline_flags=["-cache-mb", "0", "-quiet"], schedule=["CA", "AC"] * 3,
        cases=[dict(name=n, input=identity(q), exact=identity(t)) for n, q, t in cases],
        independent_scores_seen=False, static_elf_passed=True))
    all_results = {}
    for name, request, exact in cases:
        expected = BUILD / "final-expected.i32" if name == "development" else None
        times, runs, identities, saved_predictions, deleted = {k: [] for k in "CA"}, [], {}, {}, []
        for iteration, order in enumerate(["CA", *(["CA", "AC"] * 3)]):
            for arm in order:
                output = BUILD / f"{name}-{iteration}-{arm}.csv"
                command = [str(BUILD / "estimate")] if arm == "C" else [str(baseline), "-cache-mb", "0", "-quiet"]
                command += ["-in", str(request.resolve()), "-out", str(output.resolve())]
                record = measured(command, f"{name}-{iteration}-{arm}")
                assert record["threads"] == 1 and record["rss_bytes"] <= 2000000000 and record["cpu_s"] <= 3600
                actual = identity(output)
                if arm not in identities:
                    p, truth, evidence, partitions = check_output(request, output, exact, expected if arm == "C" else None)
                    identities[arm], saved_predictions[arm] = evidence, p
                    if arm == "C":
                        counters = read(ROOT / f"{name}-{iteration}-{arm}.stderr")
                        assert counters["query_allocations"] == 0 and counters["rows"] == ROWS
                else:
                    assert actual["bytes"] == identities[arm]["output"]["bytes"]
                    assert actual["sha256"] == identities[arm]["output"]["sha256"]
                    deletion = dict(file=actual, identical_to=identities[arm]["output"], rebuild_command=command)
                    deleted.append(deletion)
                    write(ROOT / f"{name}-{iteration}-{arm}-cleanup.json", deletion)
                    output.unlink()
                record.update(arm=arm, iteration=iteration, output=actual, complete_contract_reused=iteration > 0)
                runs.append(record)
                if iteration:
                    times[arm].append(record["cpu_s"])
                print("EXP579_COMPLETE_RUN", name, iteration, arm, record["cpu_s"], flush=True)
        differences = np.asarray(times["A"]) - times["C"]
        width = 2.570581835636314 * statistics.stdev(differences) / math.sqrt(6)
        pc, pa = saved_predictions["C"], saved_predictions["A"]
        delta = real.points(pc, truth) - real.points(pa, truth)
        counts = np.bincount(partitions["source_family"], minlength=26)
        sums = np.bincount(partitions["source_family"], weights=delta, minlength=26)
        assert len(counts) == 26 and counts.min() > 0
        rng, boot = np.random.default_rng(20261021579), []
        for _ in range(2000):
            selected = rng.integers(26, size=26)
            boot.append(sums[selected].sum() / counts[selected].sum())
        grouped = {group: {str(int(v)): {arm: real.statistics(saved_predictions[arm][values == v], truth[values == v])
                   for arm in "CA"} for v in np.unique(values)} for group, values in partitions.items()}
        write(ROOT / (name + "-groups.json"), grouped)
        all_results[name] = dict(runs=runs, evidence=identities, timing_s=times,
            saved_cpu_s=float(differences.mean()), ci95_saved_s=[float(differences.mean()-width), float(differences.mean()+width)],
            paired_accuracy_pp=float(delta.mean()), changed_rows=int(np.count_nonzero(pc != pa)),
            paired_accuracy_ci95_pp=np.quantile(boot, [.025, .975]).tolist(), clusters=26,
            better_rows=int(np.count_nonzero(delta > 0)), worse_rows=int(np.count_nonzero(delta < 0)),
            deleted_duplicates=deleted, freed_duplicate_bytes=sum(r["file"]["bytes"] for r in deleted),
            quality_gate=identities["C"]["statistics"]["accuracy_pp"] >= 98.05,
            speed_gate=bool(differences.mean()-width > 0), full_program=True,
            independent=name == "independent")
        write(ROOT / (name + "-report.json"), all_results[name])
        print("EXP579_RESULT", name, identities["C"]["statistics"], flush=True)
    write(ROOT / "report.json", dict(cases=all_results, binary=frozen["binary"], full_port_pairs=59904,
        independent_consumed=True, stage100m_verified=False, stage1b_verified=False))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp579")
    assert xgb.__version__ == "3.0.5" and os.environ["OPENBLAS_NUM_THREADS"] == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (2400, 2400))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    assert len(list(Path("doc/eda比赛文件/arch").glob("*.json"))) == 5
    resume = sys.argv[1:] == ["resume-models"]
    assert resume or len(sys.argv) == 1
    if resume:
        training = read(ROOT / "training.json")
        for record in training["records"]:
            for expected in record["assets"].values():
                if isinstance(expected, dict) and "path" in expected:
                    real.check(expected["path"], expected)
        certificate = read(ROOT / "geometry-certificate.json")
        real.check(BUILD / "geometry.bin", certificate["reordered"])
        assert not (ROOT / "candidate-freeze.json").exists()
        query = np.fromfile(BUILD / "queries.bin", "<i4", offset=12).reshape(ROWS, 10)
        mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
        ports = []
        for side, key in ((0, "source"), (1, "target")):
            index = np.full(496, -1, dtype=np.int32)
            index[mapping[key + "_ids"]] = np.arange(len(mapping[key + "_ids"]))
            ports.append(index[query[:, 8 + side]])
        finish_build(mapping, np.column_stack(ports), query, [BUILD / f"R8-final-{g}.json" for g in range(16)])
    else:
        ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
        shutil.copyfile(PLAN, ROOT / "protocol-original.md")
        build()
    reuse.previous.ROOT = ROOT / "recheck-input"
    reuse.previous.ROOT.mkdir()
    audit()
    qualify()
    added = sum(p.stat().st_size for folder in (ROOT, BUILD) for p in folder.rglob("*") if p.is_file())
    assert added <= 1500000000
    write(ROOT / "cost.json", dict(cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
        driver_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024, added_bytes=added,
        disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP579_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
