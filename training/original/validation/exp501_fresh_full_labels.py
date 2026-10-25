#!/usr/bin/env python3
"""Prepare a complete fresh 1M and compute exact labels offline on l7."""
import argparse
import collections
import concurrent.futures
import csv
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from exp208_nominal_parent_tree import identity, write
from exp462_unique_1b import prior_pairs
from exp482_full_role_baseline import ARCH, coverage, roles

ROOT = Path("validation/results/exp501")
BUILD = Path("build/exp501")
PLAN = Path("experiment/实验501-全端口新1M请求与独立exact标签.md")
ROWS = 1_000_000
TOOLS = BUILD / "tools"
REFERENCE = Path("../..")


def read(path):
    return json.loads(Path(path).read_text())


def freeze_check():
    frozen = read(ROOT / "freeze.json")
    for row in frozen["files"]:
        assert identity(row["path"]) == row, row["path"]
    return frozen


def prepare():
    ROOT.mkdir()
    BUILD.mkdir()
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    known, history = prior_pairs()
    with gzip.open(BUILD / "known-local.csv.gz", "wt", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("From", "To"))
        writer.writerows(sorted(known))
    history["requests"] = identity(BUILD / "known-local.csv.gz")
    write(ROOT / "history-local.json", history)
    files = [Path(__file__).resolve().relative_to(Path.cwd()),
             Path("validation/exp208_nominal_parent_tree.py"),
             Path("validation/exp462_unique_1b.py"),
             Path("validation/exp482_full_role_baseline.py"),
             ROOT / "protocol-original.md", ROOT / "history-local.json",
             BUILD / "known-local.csv.gz", *ARCH.glob("*.json")]
    write(ROOT / "freeze.json", dict(
        files=[identity(p) for p in files], rows=ROWS, proposal_seed=20261019501,
        shuffle_seed=20261020501, source_ports=roles()[0], target_ports=roles()[1],
        required_port_pairs=208 * 288, expected_tools=read(
            "validation/results/exp482/remote-freeze.json")["files"],
        base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        protected=[identity(p) for p in ("estimate", "src/residue_estimator.cpp",
                                       "src/residue_estimator.h", "src/xgb_residual_base47_fast.h")],
        disk_start_bytes=shutil.disk_usage(".").free))
    print("EXP501_DATA_PROTOCOL_FROZEN", len(known), flush=True)


def measured(name, command):
    command = list(map(str, command))
    started = time.monotonic()
    with (ROOT / (name + ".stdout")).open("xb") as out, \
            (ROOT / (name + ".stderr")).open("xb") as err:
        result = subprocess.run(
            ["/usr/bin/time", "-f", "user=%U sys=%S wall=%e rss_kib=%M exit=%x",
             "-o", str(ROOT / (name + ".time")), *command], stdout=out, stderr=err)
    record = dict(command=command, exit_code=result.returncode,
                  wall_s=time.monotonic() - started, host=socket.gethostname(),
                  measured=(ROOT / (name + ".time")).read_text())
    write(ROOT / (name + ".run.json"), record)
    assert result.returncode == 0, (name, result.returncode)
    return record


def full_coverage(pairs):
    report = coverage(pairs)
    sources, targets = roles()
    counts = collections.Counter((a.split("/", 1)[1], b.split("/", 1)[1])
                                 for a, b in pairs)
    assert len(counts) == len(sources) * len(targets)
    assert set(counts) == {(a, b) for a in sources for b in targets}
    report.update(port_pairs=len(counts), minimum_port_pair_rows=min(counts.values()),
                  maximum_port_pair_rows=max(counts.values()),
                  port_pair_counts=[[counts[a, b] for b in targets] for a in sources])
    assert sum(map(sum, report["port_pair_counts"])) == len(pairs)
    return report


def dataset():
    assert socket.gethostname() == "lhj-R4900-G3"
    frozen = freeze_check()
    actual_tools = []
    for expected in frozen["expected_tools"]:
        actual = identity(REFERENCE / expected["path"])
        assert (actual["bytes"], actual["sha256"]) == (expected["bytes"], expected["sha256"])
        actual_tools.append(actual)
    write(ROOT / "tool-freeze.json", dict(files=actual_tools, host=socket.gethostname(),
                                         disk_start_bytes=shutil.disk_usage(".").free))
    hidden = REFERENCE / "build/hidden-suite-v1"
    generated = BUILD / "u-role"
    measured("generate", [hidden / "make_hidden_suite", ARCH, hidden / "reach.bin",
                         "U-role", ROWS, frozen["proposal_seed"], frozen["shuffle_seed"], generated])
    measured("input-check", [hidden / "check_hidden_suite", ARCH, hidden / "reach.bin",
                            hidden / "independent/eligibility.bin", "U-role", ROWS,
                            generated / "requests.csv", generated / "check"])
    check = read(generated / "check/check.json")
    assert check["status"] == "passed" and check["unique_rows"] == ROWS
    with (generated / "requests.csv").open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        pairs = [tuple(row) for row in reader]
    assert len(pairs) == len(set(pairs)) == ROWS
    complete = full_coverage(pairs)
    with gzip.open(BUILD / "known-local.csv.gz", "rt", newline="") as stream:
        reader = csv.DictReader(stream)
        known = {(r["From"], r["To"]) for r in reader}
    original = Path.cwd()
    try:
        os.chdir(REFERENCE)
        remote_known, history = prior_pairs()
    finally:
        os.chdir(original)
    history["reference_root"] = str((original / REFERENCE).resolve())
    known.update(remote_known)
    overlap = [[i, *p] for i, p in enumerate(pairs) if p in known]
    write(ROOT / "history-check.json", dict(remote=history, local=identity(
        ROOT / "history-local.json"), combined_known_pairs=len(known), overlap=overlap))
    assert not overlap, overlap[:10]
    write(ROOT / "input.json", dict(
        input=identity(generated / "requests.csv"), rows=ROWS, unique_rows=ROWS,
        coverage=complete, independent_checker=identity(generated / "check/check.json"),
        prior_exact_overlap=0, scope="Fresh in the recorded local and r9 exact CSV history."))
    checks = collections.Counter()
    flags = []
    for a, b in pairs:
        xy = lambda pin: tuple(map(int, pin.split("/")[0][4:].split("_")))
        distance = sum(abs(x - y) for x, y in zip(xy(a), xy(b)))
        band = next(v for v in (0, 12, 24, 50, 100, 1000) if distance <= v)
        flags.append(int(checks[band] < 2))
        checks[band] += 1
    assert len(checks) == 6 and sum(flags) == 12
    shards = []
    for shard in range(4):
        selected = pairs[shard::4]
        with (BUILD / f"labels-{shard}.csv").open("x", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("kind", "from", "to", "label", "span_checked"))
            for i in range(shard, ROWS, 4):
                writer.writerow(("fresh-full-role", *pairs[i], -2, flags[i]))
        shards.append(dict(shard=shard, rows=len(selected), coverage=coverage(selected),
                           span_checks=sum(flags[shard::4]),
                           input=identity(BUILD / f"labels-{shard}.csv")))
    TOOLS.mkdir()
    for name, source in (("exact_labels", "build/exp203/exact_labels"),
                         ("orbit.i16", "build/exp155/orbit.i16")):
        shutil.copy2(REFERENCE / source, TOOLS / name)
    write(ROOT / "label-freeze.json", dict(
        shards=shards, rows=ROWS, input=identity(generated / "requests.csv"),
        tools=[identity(TOOLS / name) for name in ("exact_labels", "orbit.i16")],
        source_freeze=identity(ROOT / "freeze.json"),
        scope="Four offline exact computations; all scoring awaits the complete 1M on r9."))
    print("EXP501_FULL_1M_AND_ALL_PORT_PAIRS_CHECKED", flush=True)


def labels():
    assert socket.gethostname() != "lhj-R4900-G3"
    freeze_check()
    frozen = read(ROOT / "label-freeze.json")
    for row in frozen["tools"] + [r["input"] for r in frozen["shards"]]:
        assert identity(row["path"]) == row, row["path"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for shard in range(4):
            command = [TOOLS / "exact_labels", ARCH, BUILD / f"labels-{shard}.csv",
                       TOOLS / "orbit.i16", BUILD / f"exact-{shard}.csv"]
            futures.append(executor.submit(measured, f"labels-{shard}", command))
        results = [future.result() for future in futures]
    write(ROOT / "label-computation.json", dict(
        all_exited_zero=True, runs=results, host=socket.gethostname(),
        outputs=[identity(BUILD / f"exact-{i}.csv") for i in range(4)]))
    print("EXP501_OFFLINE_LABELS_COMPLETE", flush=True)


def verify():
    assert socket.gethostname() == "lhj-R4900-G3"
    freeze_check()
    frozen = read(ROOT / "label-freeze.json")
    computed = read(ROOT / "label-computation.json")
    assert computed["all_exited_zero"] and len(computed["runs"]) == 4
    for row in computed["outputs"] + [frozen["input"]]:
        assert identity(row["path"]) == row, row["path"]
    streams = [(BUILD / f"exact-{i}.csv").open(newline="") for i in range(4)]
    readers = [csv.reader(stream) for stream in streams]
    try:
        for reader in readers:
            assert next(reader) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        counts = [0] * 4
        with Path(frozen["input"]["path"]).open(newline="") as requests, \
                (BUILD / "exact.csv").open("x", newline="") as output:
            input_rows = csv.reader(requests)
            assert next(input_rows) == ["From", "To"]
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(("index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"))
            merged_pairs = []
            for position, pair in enumerate(input_rows):
                shard = position % 4
                row = next(readers[shard])
                assert len(row) == 7 and int(row[0]) == position // 4
                assert row[1:3] == pair
                assert str(int(row[3])) == row[3] and int(row[3]) >= 0
                assert int(row[4]) >= 0 and int(row[5]) >= 0 and float(row[6]) >= 0
                writer.writerow((position, *row[1:]))
                merged_pairs.append(tuple(pair))
                counts[shard] += 1
            assert len(merged_pairs) == ROWS and len(set(merged_pairs)) == ROWS
            complete = full_coverage(merged_pairs)
        for shard, reader in enumerate(readers):
            assert next(reader, None) is None
            assert counts[shard] == frozen["shards"][shard]["rows"]
            text = (ROOT / f"labels-{shard}.stdout").read_text()
            expected = (f"labels_done rows={counts[shard]} known_checks=0 "
                        f"span_checks={frozen['shards'][shard]['span_checks']} threads=1")
            assert text.splitlines()[-1] == expected
            assert not (ROOT / f"labels-{shard}.stderr").read_bytes()
            with (BUILD / f"exact-{shard}.csv").open("rb") as stream:
                stream.seek(-1, 2)
                assert stream.read() == b"\n"
    finally:
        for stream in streams:
            stream.close()
    assert complete == read(ROOT / "input.json")["coverage"]
    write(ROOT / "report.json", dict(
        all_complete_label_checks=True, rows=ROWS, unique_rows=ROWS,
        source_ports=208, target_ports=288, port_pairs=208 * 288, span_checks=12,
        exact=identity(BUILD / "exact.csv"), input=frozen["input"],
        input_check=identity(ROOT / "input.json"), runs=computed["runs"],
        host=socket.gethostname(), disk_end_bytes=shutil.disk_usage(".").free,
        scope="Complete fresh real-graph labels. Candidate accuracy and CPU remain unverified."))
    print("EXP501_COMPLETE_1M_EXACT_VERIFIED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "dataset", "labels", "verify"))
    globals()[parser.parse_args().stage]()
