#!/usr/bin/env python3
"""Measure lossless static storage while restoring the frozen INT8 query layout."""
import json
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

sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed

ROOT, BUILD = Path("validation/results/exp646"), Path("build/exp646")
PLAN = Path("experiment/实验646-压缩资产到原INT8布局的静态启动恢复.md")
SOURCE = Path("tests/exp646_asset_restore.cpp")
identity, write = speed.identity, speed.write
speed.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def checked(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    return actual


def ranges(raw, far_rank):
    assert raw[:8] == b"EX589Q01"
    assert struct.unpack("<6I", raw[8:32]) == (512, far_rank, 64, 64, 4800, 260160)
    at, factors = 64 + 59904 * 2, []
    for rank, rows in ((512, (59904, 4800)), (far_rank, (4 * 59904, 260160))):
        for count in rows:
            factors.append((at, count, rank))
            at += count * rank
        at += sum(rows) * ((rank + 63) // 64) * 4
    assert at == len(raw)
    return factors


def delta(raw, factors):
    encoded = bytearray(raw)
    for offset, rows, rank in factors:
        view = np.frombuffer(encoded, "u1", count=rows * rank, offset=offset).reshape(rows, rank)
        view[1:] = view[1:] - view[:-1]
    return encoded


def self_check():
    for rank in (64, 96):
        original = np.asarray([(i * 73 + 128) % 256 for i in range(4 * rank)], "u1")
        encoded = delta(original.tobytes(), [(0, 4, rank)])
        restored = np.add.accumulate(np.frombuffer(encoded, "u1").reshape(4, rank),
                                     axis=0, dtype=np.uint8)
        assert np.array_equal(original, restored.ravel())
    return dict(modular_wraparound=True, ranks=[64, 96])


def probe(model, arm, raw, factors, expected):
    label = f"{model}-{arm}"
    folder = BUILD / label
    folder.mkdir()
    encoded_path = Path("../exp589") / expected["path"]
    if arm == "D":
        encoded_path = folder / "delta.bin"
        encoded_path.write_bytes(delta(raw, factors))
    compressed = folder / "asset.zst"
    command = ["zstd", "--single-thread", "-9", "--check", "--no-progress", "-q", "-c",
               str(encoded_path)]
    started, before = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
    with compressed.open("xb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, check=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    assert not result.stderr
    write(ROOT / (label + "-compression.json"), dict(command=command, input=identity(encoded_path),
        compressed=identity(compressed), cpu_s=after.ru_utime + after.ru_stime -
        before.ru_utime - before.ru_stime, wall_s=time.monotonic() - started))
    rank = int(model[1:])
    (folder / "asset646.h").write_text(
        "#pragma once\n"
        f"static constexpr size_t kRawBytes646={len(raw)};\n"
        f"static constexpr unsigned kFarRank646={rank};\n"
        f"static constexpr bool kDelta646={'true' if arm == 'D' else 'false'};\n")
    assembler = folder / "asset.S"
    assembler.write_text('.section .rodata\n.balign 64\n.globl asset646_begin\nasset646_begin:\n'
        f'.incbin "{compressed}"\n.globl asset646_end\nasset646_end:\n'
        '.section .note.GNU-stack,"",@progbits\n')
    binary, output = folder / "restore", folder / "restored.bin"
    command = ["g++", "-std=c++17", "-O3", "-static", "-s", "-march=x86-64",
        "-mtune=generic", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
        "-I", str(folder), "-I", str(BUILD / "deps"), str(SOURCE), str(assembler),
        str(BUILD / "deps/libzstd.a"), "-o", str(binary)]
    speed.measured(command, label + "-compile")
    assert not (ROOT / (label + "-compile.stderr")).read_bytes()
    linked = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
    assert "not a dynamic executable" in linked.stdout + linked.stderr
    assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(binary)], text=True)
    runs = []
    for repeat in range(4):
        run = speed.measured([str(binary), str(output)], f"{label}-restore-{repeat}")
        metrics = read(run["stderr"])
        verify_start, verify_cpu = time.monotonic(), time.process_time()
        asset = checked(output, expected)
        verification = dict(cpu_s=time.process_time() - verify_cpu,
                            wall_s=time.monotonic() - verify_start)
        assert metrics["self_check_passed"] and metrics["decoder_version"] == "1.5.5"
        assert metrics["delta"] == (arm == "D") and metrics["raw_bytes"] == len(raw)
        assert metrics["compressed_bytes"] == compressed.stat().st_size
        assert run["threads"] == 1 and run["rss_bytes"] <= 512_000_000 and run["wall_s"] <= 60
        runs.append(dict(repeat=repeat, warmup=repeat == 0, run=run, metrics=metrics,
                         output=asset, sha_verification=verification))
    median = statistics.median(r["metrics"]["restore_cpu_s"] for r in runs[1:])
    projected = compressed.stat().st_size + 14_376_960 + 8_500_000
    record = dict(model=model, arm=arm, original=expected, compressed=identity(compressed),
        binary=identity(binary), source=identity(SOURCE), assembler=identity(assembler),
        generated_header=identity(folder / "asset646.h"), runs=runs, static=True,
        complete_original_bytes_restored=True, median_restore_cpu_s=median,
        projected_full_program_bytes=projected, production_cpu_measured=False,
        accuracy_measured=False, gate=binary.stat().st_size < 100_000_000 and
        projected <= 99_000_000 and median <= .5)
    write(ROOT / (label + "-report.json"), record)
    print("EXP646_RESOURCE", label, compressed.stat().st_size, median, record["gate"], flush=True)
    return record


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp646")
    resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
    resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
    ROOT.mkdir(parents=True, exist_ok=False)
    assert BUILD.is_dir() and not list(BUILD.glob("D*"))
    free, started = shutil.disk_usage(".").free, time.monotonic()
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    dependencies = read(BUILD / "deps/identities.json")
    for item in dependencies:
        checked(item["path"], item)
    models = read("../exp589/validation/results/exp589/candidate-freeze.json")["arms"]
    stage = read("../exp644/validation/results/exp644/1b-freeze.json")
    checked(Path("../exp640") / stage["binary"]["path"], stage["binary"])
    failed = read("../exp645/validation/results/exp645/decision.json")
    assert failed["all_candidate_gates_failed"]
    (ROOT / "zstd-help.txt").write_text(subprocess.check_output(["zstd", "--help"], text=True))
    (ROOT / "compiler-help.txt").write_text(subprocess.check_output(["g++", "--help"], text=True))
    (ROOT / "ldd-help.txt").write_text(subprocess.check_output(["ldd", "--help"], text=True))
    api = (BUILD / "deps/zstd.h").read_text()
    assert all(symbol in api for symbol in ("ZSTD_decompress(", "ZSTD_getFrameContentSize(",
                                            "ZSTD_findFrameCompressedSize(", "ZSTD_isError("))
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in (Path(__file__), SOURCE,
        PLAN, ROOT / "protocol-original.md", Path(speed.__file__))], dependencies=dependencies,
        models={k: models[k]["geometry"] for k in ("D64", "D96")}, self_check=self_check(),
        reference=stage["binary"], previous_decision=identity(
            "../exp645/validation/results/exp645/decision.json"),
        compressor_version=subprocess.check_output(["zstd", "--version"], text=True).strip(),
        compiler_version=subprocess.check_output(["g++", "--version"], text=True).strip(),
        disk_free_start_bytes=free, measured_queries=False))
    records = []
    for model in ("D64", "D96"):
        expected = models[model]["geometry"]
        path = Path("../exp589") / expected["path"]
        checked(path, expected)
        raw = path.read_bytes()
        factors = ranges(raw, int(model[1:]))
        for arm in ("Z", "D"):
            records.append(probe(model, arm, raw, factors, expected))
    eligible = [r for r in records if r["model"] == "D96" and r["gate"]]
    selected = None
    if eligible:
        fastest = min(r["median_restore_cpu_s"] for r in eligible)
        selected = min((r for r in eligible if r["median_restore_cpu_s"] <= fastest + .005),
                       key=lambda r: r["arm"] != "Z")["arm"]
    added = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert added <= 1_000_000_000
    write(ROOT / "report.json", dict(records=records, selected_D96_arm=selected,
        continue_to_joint_model=selected is not None, complete_original_bytes_restored=True,
        new_file_bytes=added, wall_s=time.monotonic() - started,
        disk_free_start_bytes=free, disk_free_end_bytes=shutil.disk_usage(".").free,
        production_cpu_measured=False, accuracy_measured=False, complete_program_measured=False,
        reconstruction_commands=[r["runs"][0]["run"]["command"] for r in records]))
    print("EXP646_COMPLETE", selected, flush=True)


if __name__ == "__main__":
    main()
