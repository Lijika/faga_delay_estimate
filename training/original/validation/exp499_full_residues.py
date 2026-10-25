#!/usr/bin/env python3
"""Generate the complete-port 120-residue nominal label set in two offline shards."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time

from exp208_nominal_parent_tree import identity, write
from exp482_full_role_baseline import roles, ARCH

ROOT, BUILD = Path("validation/results/exp499"), Path("build/exp499")
PLAN = Path("experiment/实验499-全端口全部余类名义标签扩展.md")
HOSTS = {"lhj-NF5280M5": (0, 104), "lhj-R4900-G3": (104, 208)}
VALUES, RAW_BYTES = 4 * 120 * 288 * 552, 1184 + 2 * 4 * 120 * 288 * 552
PREPARATION = Path("validation/results/exp499-preparation")


def read(path):
    return json.loads(Path(path).read_text())


def measured(name, command):
    started = time.monotonic()
    with (ROOT / (name + ".stdout")).open("xb") as out, \
            (ROOT / (name + ".stderr")).open("xb") as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        _, status, usage = os.wait4(child.pid, 0)
        child.returncode = os.waitstatus_to_exitcode(status)
    record = dict(command=command, exit_code=child.returncode,
                  hostname=socket.gethostname(), wall_s=time.monotonic() - started,
                  cpu_s=usage.ru_utime + usage.ru_stime, rss_bytes=usage.ru_maxrss * 1024)
    write(ROOT / (name + ".run.json"), record)
    assert child.returncode == 0, (name, child.returncode)
    print(name, "complete", flush=True)


def prepare():
    assert socket.gethostname() in HOSTS
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    (BUILD / "fields").mkdir()
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    source = read(PREPARATION / "source-freeze.json")
    for row in source["files"]:
        assert identity(row["path"]) == row
    roles_source = Path("tests/exp483_role_field.cpp").read_text()
    marker = "\nint main(int argc, char** argv)"
    assert roles_source.count(marker) == 1
    (BUILD / "roles.hpp").write_text(roles_source.split(marker)[0].replace(
        '"../build/exp483/solver.hpp"', '"../exp483/solver.hpp"'))
    measured("compiler-version", ["g++", "--version"])
    measured("compiler-help", ["g++", "--help=common"])
    command = ["g++", "-O2", "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-function",
               "tests/exp499_full_residue_field.cpp", "src/architecture.cpp",
               "-o", str(BUILD / "field")]
    measured("compile", command)
    measured("field-help", [str(BUILD / "field"), "--help"])
    sources, targets = roles()
    write(ROOT / "freeze.json", dict(
        files=source["files"] + [identity(BUILD / "roles.hpp"), identity(BUILD / "field"),
                                identity(ROOT / "protocol-original.md")],
        source_freeze=identity(PREPARATION / "source-freeze.json"),
        sources=sources, targets=targets, shard=HOSTS[socket.gethostname()],
        source_ports=208, target_ports=288, contexts=480, values_per_source=VALUES,
        raw_bytes_per_source=RAW_BYTES, workers=8, compiler_command=command,
        hostname=socket.gethostname(), disk_start_bytes=shutil.disk_usage(".").free))


def self_check():
    assert socket.gethostname() == "lhj-R4900-G3"
    measured("self-check", [str(BUILD / "field"), str(ARCH), "--self-check"])
    check = read(ROOT / "self-check.stdout")
    assert check["source_ports"] == 208 and check["target_ports"] == 288
    assert check["endpoint_values"] == 208 * 288 * 3
    assert not (ROOT / "self-check.stderr").read_bytes()
    write(ROOT / "self-check.json", dict(
        result=check, frozen_source=identity(PREPARATION / "source-freeze.json"),
        executable=identity(BUILD / "field"), run=identity(ROOT / "self-check.run.json")))


def header_check(prefix, source_id, target_ids):
    assert prefix[:8] == b"EX499D01"
    assert struct.unpack("<6i", prefix[8:32]) == (source_id, 288, 4, 120, 12, 46)
    assert list(struct.unpack("<288i", prefix[32:1184])) == target_ids


def generate():
    host = socket.gethostname()
    assert host in HOSTS
    frozen = read(ROOT / "freeze.json")
    for row in frozen["files"]:
        assert identity(row["path"]) == row
    check = read(ROOT / "self-check.json")
    assert check["frozen_source"] == frozen["source_freeze"]
    assert check["result"]["endpoint_values"] == 208 * 288 * 3
    names = [p["Name"] for p in read(ARCH / "SRB_Port.json")["Port"]]
    target_ids = [names.index(name) for name in frozen["targets"]]
    begin, end = HOSTS[host]

    def one(number):
        assert shutil.disk_usage(".").free >= 2_000_000_000
        source = frozen["sources"][number]
        packed = BUILD / "fields" / f"{number:03d}.bin.xz"
        stderr = ROOT / f"field-{number:03d}.stderr"
        command = [str(BUILD / "field"), str(ARCH), source, "-"]
        started, pack_cpu = time.monotonic(), time.thread_time()
        digest, raw_bytes, prefix = hashlib.sha256(), 0, b""
        compressor = lzma.LZMACompressor(format=lzma.FORMAT_XZ, preset=6)
        with stderr.open("xb") as err, packed.open("xb") as out:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err)
            try:
                for block in iter(lambda: child.stdout.read(8 << 20), b""):
                    if not prefix:
                        prefix = block[:1184]
                    digest.update(block)
                    raw_bytes += len(block)
                    out.write(compressor.compress(block))
                out.write(compressor.flush())
            except BaseException:
                child.kill()
                child.wait()
                raise
            finally:
                child.stdout.close()
            _, status, usage = os.wait4(child.pid, 0)
            child.returncode = os.waitstatus_to_exitcode(status)
        run = dict(command=command, exit_code=child.returncode, hostname=host,
                   wall_s=time.monotonic() - started, cpu_s=usage.ru_utime + usage.ru_stime,
                   rss_bytes=usage.ru_maxrss * 1024,
                   compression_thread_cpu_s=time.thread_time() - pack_cpu)
        write(ROOT / f"field-{number:03d}.run.json", run)
        assert child.returncode == 0, (number, stderr)
        measurement = read(stderr)
        assert measurement["source"] == source and measurement["certified_values"] == VALUES
        assert measurement["source_id"] == names.index(source)
        assert measurement["target_ports"] == 288 and measurement["contexts"] == 480
        assert raw_bytes == RAW_BYTES
        header_check(prefix, names.index(source), target_ids)
        restored, restored_bytes = hashlib.sha256(), 0
        with lzma.open(packed, "rb") as stream:
            for block in iter(lambda: stream.read(8 << 20), b""):
                restored.update(block)
                restored_bytes += len(block)
        assert restored_bytes == raw_bytes and restored.digest() == digest.digest()
        row = dict(number=number, source=source, measurement=measurement, run=run,
                   asset=identity(packed), raw_bytes=raw_bytes, raw_sha256=digest.hexdigest(),
                   roundtrip_sha256=restored.hexdigest(), full_lossless_roundtrip=True,
                   reconstruction=["python3", "-c",
                       "import lzma,pathlib; p=pathlib.Path(" + repr(str(packed)) +
                       "); target=p.with_suffix(''); assert not target.exists(); "
                       "target.write_bytes(lzma.decompress(p.read_bytes()))"])
        write(ROOT / f"field-{number:03d}.json", row)
        print("EXP499_FIELD_COMPLETE", number, source, row["asset"]["bytes"], flush=True)
        return row

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(one, range(begin, end)))
    assert [r["number"] for r in rows] == list(range(begin, end))
    write(ROOT / f"shard-{begin:03d}-{end:03d}.json", dict(
        fields=rows, hostname=host, source_begin=begin, source_end=end,
        certified_values=sum(r["measurement"]["certified_values"] for r in rows),
        label_cpu_s=sum(r["run"]["cpu_s"] for r in rows),
        compression_cpu_s=sum(r["run"]["compression_thread_cpu_s"] for r in rows),
        compressed_bytes=sum(r["asset"]["bytes"] for r in rows),
        freeze=identity(ROOT / "freeze.json"), disk_free_end=shutil.disk_usage(".").free,
        scope="Offline generation shard; complete 208-source verification is pending."))


def check():
    assert socket.gethostname() == "lhj-R4900-G3"
    import numpy as np
    frozen = read(ROOT / "freeze.json")
    names = [p["Name"] for p in read(ARCH / "SRB_Port.json")["Port"]]
    target_ids = [names.index(name) for name in frozen["targets"]]
    old_path = Path("../exp491/build/exp491/truth.npy")
    expected = read(Path("../exp497/validation/results/exp497/freeze.json"))["truth"]
    actual = identity(old_path)
    assert (actual["bytes"], actual["sha256"]) == (expected["bytes"], expected["sha256"])
    old = np.load(old_path, mmap_mode="r")
    assert old.shape == (208, 4, 2, 288, 552)
    x, y = np.meshgrid(np.arange(12), np.arange(46), indexing="ij")
    checked, compared, records = 0, 0, []
    for number, source in enumerate(frozen["sources"]):
        row = read(ROOT / f"field-{number:03d}.json")
        assert row["number"] == number and row["source"] == source
        assert identity(row["asset"]["path"]) == row["asset"]
        raw = lzma.decompress(Path(row["asset"]["path"]).read_bytes())
        assert len(raw) == RAW_BYTES and hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
        header_check(raw[:1184], names.index(source), target_ids)
        residual = np.frombuffer(raw, "<i2", offset=1184).reshape(4, 120, 288, 552)
        for direction in range(4):
            trend = (125 * x + (125 if direction % 2 else 127) * y).ravel()
            values = residual[direction].astype(np.int32) + trend
            assert np.all((values >= 0) & (values < 1_000_000_000))
            assert np.array_equal(values[[0, 66]], old[number, direction])
            checked += values.size
            compared += old[number, direction].size
        assert row["measurement"]["certified_values"] == VALUES
        records.append(identity(ROOT / f"field-{number:03d}.json"))
        print("EXP499_SOURCE_VERIFIED", number, flush=True)
    assert checked == 208 * VALUES and compared == 264536064
    write(ROOT / "report.json", dict(
        evidence_passed=True, source_ports=208, target_ports=288, contexts=480,
        certified_values=checked, old_context_equal_values=compared,
        records=records, checker=identity(__file__),
        scope="Complete nominal labels, including rectangular padding; model scores, actual "
              "graph accuracy, model capacity and production CPU remain unverified."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "self-check", "generate", "check"))
    args = parser.parse_args()
    {"prepare": prepare, "self-check": self_check, "generate": generate, "check": check}[args.stage]()
