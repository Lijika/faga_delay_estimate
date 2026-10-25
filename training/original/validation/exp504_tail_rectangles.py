#!/usr/bin/env python3
"""Compile exact constant rectangles from the full certified nominal domain."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import resource
import shutil
import socket
import struct
import time

import numpy as np

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp504"), Path("build/exp504")
PREPARATION = Path("../exp500/validation/results/exp500-preparation")
PLAN = Path("experiment/实验504-全端口有限尾矩形的常数编译.md")
DTYPE = np.dtype([("constant", "<i2"), ("a", "u1"), ("b", "u1")])
SHAPE = (4, 10, 12, 288)
SLICES = 4 * 120 * 288


def read(path):
    return json.loads(Path(path).read_text())


def load_field(row, mapping):
    path = Path("../exp499") / row["asset"]["path"]
    packed = path.read_bytes()
    assert len(packed) == row["asset"]["bytes"]
    assert hashlib.sha256(packed).hexdigest() == row["asset"]["sha256"]
    raw = lzma.decompress(packed)
    assert len(raw) == row["raw_bytes"] and hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
    assert raw[:8] == b"EX499D01"
    assert struct.unpack("<6i", raw[8:32]) == (mapping["source_ids"][row["number"]], 288, 4, 120, 12, 46)
    assert np.array_equal(np.frombuffer(raw, "<i4", count=288, offset=32), mapping["target_ids"])
    return np.frombuffer(raw, "<i2", offset=1184).reshape(*SHAPE, 12, 46)


def prepare():
    assert socket.gethostname() == "lhj-NF5280M5"
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    (BUILD / "fields").mkdir()
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    mapping = read(PREPARATION / "mapping.json")
    assert len(mapping["sources"]) == 208 and len(mapping["targets"]) == 288
    shutil.copyfile(PREPARATION / "mapping.json", ROOT / "mapping.json")
    report = read(PREPARATION / "label-report.json")
    assert report["evidence_passed"] and report["certified_values"] == 208 * SLICES * 552
    fields = read(PREPARATION / "fields.json")
    assert [r["number"] for r in fields] == list(range(208))
    files = [Path(__file__).resolve().relative_to(Path.cwd()),
             Path("validation/exp208_nominal_parent_tree.py"),
             ROOT / "protocol-original.md", ROOT / "mapping.json",
             PREPARATION / "fields.json", PREPARATION / "label-report.json"]
    for row in fields:
        found = identity(Path("../exp499") / row["asset"]["path"])
        assert (found["bytes"], found["sha256"]) == (row["asset"]["bytes"], row["asset"]["sha256"])
    write(ROOT / "freeze.json", dict(
        files=[identity(p) for p in files], sources=208, targets=288, contexts=480,
        values=208 * SLICES * 552, numpy_version=np.__version__,
        bytes_per_slice=DTYPE.itemsize, host=socket.gethostname(),
        scope="Offline fitting only; complete model verification runs on r9."))


def compile_model():
    assert socket.gethostname() == "lhj-NF5280M5"
    frozen = read(ROOT / "freeze.json")
    assert frozen["numpy_version"] == np.__version__
    for row in frozen["files"]:
        assert identity(row["path"]) == row
    mapping = read(ROOT / "mapping.json")
    started, cpu = time.monotonic(), time.process_time()
    direction = np.arange(4)[:, None, None, None, None]
    rx = np.arange(10)[None, :, None, None, None]
    ry = np.arange(12)[None, None, :, None, None]
    a_values = np.arange(12, dtype=np.int16)
    xmin = ((direction // 2 == 1) & (rx == 0)).astype(np.int16)
    ymin = ((direction % 2 == 1) & (ry == 0)).astype(np.int16)
    ymax = np.where(ry <= 9, 46, 45)
    widths = 12 - np.maximum(a_values, xmin)
    column_ends = np.arange(1, 47, dtype=np.uint8)
    records = []
    for row in read(PREPARATION / "fields.json"):
        values = load_field(row, mapping)
        constant = values[..., -1, -1]
        bad = values != constant[..., None, None]
        row_start = np.max(np.where(bad, column_ends, np.uint8(0)), axis=-1)
        b_values = np.maximum.accumulate(row_start[..., ::-1], axis=-1)[..., ::-1]
        areas = widths * np.maximum(0, ymax - np.maximum(b_values, ymin))
        chosen = np.argmax(areas, axis=-1)
        data = np.empty(SHAPE, dtype=DTYPE)
        data["constant"] = constant
        data["a"] = chosen
        data["b"] = np.take_along_axis(b_values, chosen[..., None], axis=-1)[..., 0]
        assert data.dtype.itemsize == 4 and np.isfinite(areas).all()
        header = b"EX504R01" + struct.pack("<6i", row["number"], 288, 4, 10, 12, 4)
        raw = header + data.tobytes()
        path = BUILD / "fields" / f"{row['number']:03d}.bin.xz"
        with path.open("xb") as stream:
            stream.write(lzma.compress(raw, preset=6))
        record = dict(number=row["number"], asset=identity(path), raw_bytes=len(raw),
                      raw_sha256=hashlib.sha256(raw).hexdigest(), slices=SLICES)
        write(ROOT / f"field-{row['number']:03d}.json", record)
        records.append(record)
        print("EXP504_FIELD_COMPILED", row["number"], flush=True)
    write(ROOT / "compilation.json", dict(
        fields=records, sources=208, targets=288, contexts=480,
        slices=208 * SLICES, body_bytes=208 * SLICES * 4,
        asset_bytes=sum(r["asset"]["bytes"] for r in records),
        cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        host=socket.gethostname(), freeze=identity(ROOT / "freeze.json"),
        scope="Compiled fixed rectangles only; coverage, optimality and capacity checked on r9."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "compile"))
    args = parser.parse_args()
    {"prepare": prepare, "compile": compile_model}[args.stage]()
