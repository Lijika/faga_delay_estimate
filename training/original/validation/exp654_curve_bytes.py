#!/usr/bin/env python3
"""Audit a lossless byte codebook, then time the equivalent complete 100M."""
import math
from pathlib import Path
import resource
import shutil
import socket
import statistics
import struct
import subprocess
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path("../exp652/validation").resolve()))
import exp652_curve_scale as previous

read, write, identity, check = previous.read, previous.write, previous.identity, previous.check
speed = previous.speed
ROOT, BUILD = Path("validation/results/exp654"), Path("build/exp654")
PLAN = Path("experiment/实验654-冻结距离曲线的无损字节代码本.md")
PRIOR = Path("../exp652")
CODES = Path("../exp651/build/exp651/D64.curves")
BINARIES = {"A": previous.cli.BASELINE, "C": PRIOR / "build/exp652/C", "B": BUILD / "B"}
SCHEDULE = [("A", "C", "B"), ("A", "C", "B"), ("C", "B", "A"),
            ("B", "A", "C"), ("B", "C", "A"), ("C", "A", "B"), ("A", "B", "C")]
speed.ROOT = ROOT


def prior_check():
    assert read(PRIOR / "validation/results/exp652/close-audit.json")["all_checks_passed"]
    frozen = read(PRIOR / "validation/results/exp652/build-freeze.json")
    for item in frozen["files"]:
        check(PRIOR / item["path"], item)
    for arm in ("A", "C"):
        check(BINARIES[arm], frozen["binaries"][arm])
    return frozen


def prepare():
    frozen = prior_check()
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    check(CODES, read("../exp651/validation/results/exp651/nominal-decision.json")["asset"])
    raw = CODES.read_bytes()
    assert raw[:8] == b"EX651C01" and len(raw) == 64 + 59904 * 480 + 4 * 256 * 542 * 2
    assert struct.unpack_from("<6I", raw, 8) == (59904, 4, 120, 542, 256, 2)
    values = np.frombuffer(raw, "<i2", offset=64 + 59904 * 480).astype("i4")
    origin, maximum = int(values.min()), int(values.max())
    passed = maximum - origin <= 255
    write(ROOT / "range.json", dict(input=identity(CODES), values=len(values),
        minimum=origin, maximum=maximum, span=maximum-origin, range_gate=passed,
        per_direction=[dict(minimum=int(v.min()), maximum=int(v.max()))
                       for v in values.reshape(4, -1)],
        protocol=identity(PLAN), driver=identity(__file__), disk_free_start=shutil.disk_usage(".").free))
    print("EXP654_RANGE", origin, maximum, passed, flush=True)
    if not passed:
        return
    header = bytearray(raw[:64])
    header[:8] = b"EX654C01"
    struct.pack_into("<Ii", header, 28, 1, origin)
    encoded = (values - origin).astype("u1")
    assert np.array_equal(encoded.astype("i4") + origin, values)
    asset = BUILD / "D64.curves.u8"
    asset.write_bytes(header + raw[64:64 + 59904 * 480] + encoded.tobytes())
    decoded = asset.read_bytes()
    assert decoded[64:64 + 59904 * 480] == raw[64:64 + 59904 * 480]
    assert np.array_equal(np.frombuffer(decoded, "u1", offset=64 + 59904 * 480).astype("i4") + origin, values)
    assert struct.unpack_from("<6Ii", decoded, 8) == (59904, 4, 120, 542, 256, 1, origin)
    (BUILD / "curve_origin654.h").write_text(f"static constexpr int kCurveOrigin654 = {origin};\n")
    source_build = PRIOR / "build/exp652"
    for name in ("worker.cpp", "exp652_geometry_restore.h", "exp596_csv_batch.h", "exp601_port_parser.h",
                 "exp608_geometry.h", "symmetric640.h", "exp579-models.h", "exp582_int8_geometry.h"):
        shutil.copy2(source_build / name, BUILD / name)
    shutil.copy2("tests/exp654_distance_curve_bytes.h", BUILD / "exp652_distance_curve_lookup.h")
    assembly = '.section .rodata.exp654,"a",@progbits\n.balign 64\n.global exp619_codes\nexp619_codes:\n'
    assembly += f'.incbin "{asset.resolve()}"\n.section .note.GNU-stack,"",@progbits\n'
    (BUILD / "codes.S").write_text(assembly)
    speed.measured(["g++", "-c", str(BUILD / "codes.S"), "-o", str(BUILD / "codes.o")], "assemble")
    changes = {"build/exp652": str(BUILD),
               "build/exp652/worker.cpp": str(BUILD / "worker.cpp"),
               "build/exp652/C.o": str(BUILD / "B.o"), "build/exp652/C": str(BUILD / "B"),
               "build/exp652/codes.o": str(BUILD / "codes.o")}
    def adapt(command):
        return [changes.get(a, str(PRIOR / a) if a.startswith("build/exp652/") else a)
                for a in command]
    compile_command = adapt(frozen["compile_command"])
    link_command = adapt(frozen["link_command"])
    speed.measured(compile_command, "compile-B")
    speed.measured(link_command, "link-B")
    for name in ("assemble", "compile-B", "link-B"):
        assert not (ROOT / (name + ".stderr")).read_bytes()
    binary = BINARIES["B"]
    linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
    assert "not a dynamic executable" in linked.stdout + linked.stderr
    assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(binary)], text=True)
    assert binary.stat().st_size < 100_000_000
    population = read(PRIOR / "validation/results/exp652/100m-input.json")
    request = PRIOR / population["input"]["path"]
    check(request, population["input"])
    assert population["rows"] == population["unique_rows"] == 100_000_000
    assert population["port_pairs"] == 59904
    prior = read(PRIOR / "validation/results/exp652/100m-report.json")
    for arm in ("A", "C"):
        assert prior["evidence"][arm]["contract"]["contract_passed"]
        check(PRIOR / prior["evidence"][arm]["output"]["path"], prior["evidence"][arm]["output"])
    files = [Path(__file__), PLAN, Path("tests/exp654_distance_curve_bytes.h"), asset,
             ROOT / "protocol-original.md", ROOT / "range.json",
             Path(previous.__file__), Path(previous.cli.__file__), Path(speed.__file__),
             *[p for p in BUILD.iterdir() if p.suffix in (".h", ".cpp", ".S")],
             *[PRIOR / item["path"] for item in frozen["files"]]]
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in files],
        binaries={a: identity(p) for a, p in BINARIES.items()}, input=identity(request),
        asset=identity(asset), origin=origin, full_codebook_roundtrip=True, codes_unchanged=True,
        frozen_accuracy=prior["comparison"], frozen_summary=prior["summary"],
        references={a: prior["evidence"][a] for a in ("A", "C")},
        compile_command=compile_command, link_command=link_command, schedule=SCHEDULE,
        complete_estimator_runs=0, new_exact_rows=0, disk_free=shutil.disk_usage(".").free))
    print("EXP654_PREPARED", identity(binary), flush=True)


def qualify():
    frozen = read(ROOT / "freeze.json")
    recovery = read(ROOT / "driver-recovery-freeze.json")
    for item in frozen["files"]:
        if Path(item["path"]).resolve() == Path(__file__).resolve():
            assert item == recovery["original_driver"]
            check(item["path"], recovery["updated_driver"])
        else:
            check(item["path"], item)
    for arm, path in BINARIES.items():
        check(path, frozen["binaries"][arm])
    check(frozen["input"]["path"], frozen["input"])
    assert shutil.disk_usage(".").free > 7_000_000_000
    timing, runs, deleted = {a: [] for a in BINARIES}, [], []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            command = [str(BINARIES[arm]), "-in", frozen["input"]["path"], "-out", str(output)]
            evidence_path = ROOT / (output.stem + "-evidence.json")
            resumed = evidence_path.exists()
            if resumed:
                run = read(evidence_path)
                actual, counters = run["output"], run["counters"]
                assert run["command"] == command and run["arm"] == arm and run["iteration"] == iteration
                if output.exists():
                    check(output, actual)
                else:
                    old_cleanup = read(ROOT / "duplicate-cleanup-progress.json")
                    assert any(row["file"] == actual for row in old_cleanup["files"])
            else:
                assert not output.exists()
                run = speed.measured(command, output.stem)
                actual, counters = identity(output), read(run["stderr"])
            assert run["exit_code"] == 0 and run["threads"] == 1
            assert run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] < 100 and run["wall_s"] <= 3600
            assert counters == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            reference = frozen["references"]["A" if arm == "A" else "C"]
            assert all(actual[k] == reference["output"][k] for k in ("bytes", "sha256"))
            run.update(arm=arm, iteration=iteration, output=actual, counters=counters)
            if not resumed:
                write(evidence_path, run)
            runs.append(run)
            if iteration:
                timing[arm].append(run["cpu_s"])
            entry = dict(file=actual, identical_to=reference["output"], rebuild_command=command)
            deleted.append(entry)
            write(ROOT / (output.stem + "-cleanup.json"), entry)
            if output.exists():
                print("EXP654_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
                output.unlink()
            print("EXP654_TIMING", iteration, arm, format(run["cpu_s"], ".6f"), flush=True)
    accuracy = frozen["frozen_accuracy"]
    primary = previous.joint(accuracy["delta_accuracy_pp"],
        accuracy["accuracy_interval"]["conservative_ci975_pp"][0],
        np.asarray(timing["A"]) - timing["B"])
    saved = np.asarray(timing["C"]) - timing["B"]
    mean = float(np.mean(saved))
    half = float(stats.t.ppf(.975, 5)) * statistics.stdev(saved) / math.sqrt(6)
    engineering = dict(saved_cpu_s=mean, ci95_saved_cpu_s=[mean - half, mean + half],
        gate=bool(mean >= .05 and mean - half > 0))
    write(ROOT / "100m-report.json", dict(timing=timing, runs=runs, rows=100_000_000,
        unique_rows=100_000_000, port_pairs=59904, input=frozen["input"],
        accuracy=accuracy, summary=frozen["frozen_summary"], primary=primary, engineering=engineering,
        joint_gate=bool(accuracy["quality_gate"] and primary["score_gate"] and engineering["gate"]),
        bytewise_equivalent_to_exp652=True, full_csv_contract_reused=True, full_scores_reused=True,
        source="exp652 same input and full output", new_exact_rows=0, released_bytes=sum(
            r["file"]["bytes"] for r in deleted), deleted_duplicates=deleted,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP654_100M_RESULT", primary, engineering, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp654")
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert len(sys.argv) == 2 and sys.argv[1] in ("prepare", "qualify")
    {"prepare": prepare, "qualify": qualify}[sys.argv[1]]()
