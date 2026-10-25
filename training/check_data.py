#!/usr/bin/env python3
"""Verify feature packing, source-pin folds, and the deployed curve background."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

HERE = Path(__file__).resolve().parent


def definitions(filename, names, scope):
    path = HERE / "original/validation" / filename
    nodes = [n for n in ast.parse(path.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_data.py NEW_WORK_DIRECTORY")
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((HERE / "data/export-manifest.json").read_text())
    for r in manifest["outputs"]:
        p = HERE / "data" / Path(r["path"]).name
        assert p.stat().st_size == r["bytes"] and hashlib.sha256(p.read_bytes()).hexdigest() == r["sha256"]
    with np.load(HERE / "data/targets_splits.npz") as z:
        d = {k: z[k] for k in z.files}
    with np.load(HERE / "data/features53.npz") as z:
        features = z["features"].astype("<f4")
    with np.load(HERE / "data/features_extra18.npz") as z:
        extra = z["features"].astype("<f4")
    raw = gzip.decompress((HERE.parent / "path_witness/query_source/anchors-source-queries.bin.gz").read_bytes())
    assert raw[:8] == b"EX535Q01" and struct.unpack_from("<I", raw, 8)[0] == 1_000_000
    query = np.frombuffer(raw, "<i4", offset=12).reshape(-1, 10)
    pins = ((query[:, 1] * 120 + query[:, 0]) * 496 + query[:, 8]).astype("<u4")
    target_pins = ((query[:, 3] * 120 + query[:, 2]) * 496 + query[:, 9]).astype("<u4")
    assert np.unique((pins.astype("<u8") << 32) | target_pins).size == len(query)
    unique, first, inverse = np.unique(pins, return_index=True, return_inverse=True)
    assert np.array_equal(d["folds"][first][inverse], d["folds"])
    assert np.array_equal(d["clusters"][first][inverse], d["clusters"])
    assert np.unique(d["clusters"]).size == len(unique)
    assert np.array_equal(features[:, :4], query[:, 4:8])
    assert np.array_equal(features[:, 26:28], query[:, :2])
    assert np.array_equal(features[:, 30:32], query[:, 2:4])
    frozen = json.loads((HERE.parent / "validation/results/exp631/prepare.json").read_text())
    expected = next(r for r in frozen["files"] if r["path"].endswith("/features.f32"))
    digest = hashlib.sha256(b"E554F001" + struct.pack("<II", len(query), 53)
                            + features.tobytes()).hexdigest()
    assert digest == expected["sha256"]
    gaps = json.loads((HERE.parent / "source/arch/SRB_Gap.json").read_text())["Gap"]
    scope = definitions("exp614_gemini_features.py", ("geometry",), dict(np=np))
    assert np.array_equal(scope["geometry"](features, gaps), extra[:, :16])
    scope = definitions("exp677_map_events.py", ("events",), dict(np=np))
    h, v, bands, ends = scope["events"](features[:, 28:32], gaps["Block"])
    assert np.array_equal(h.astype("u1") + 2 * v, d["event"])
    assert np.array_equal(np.column_stack((bands, ends)), extra[:, 16:])
    nx, ny = features[:, 8] + features[:, 6], features[:, 9] + features[:, 7]
    dx, dy = np.abs(nx).astype("i4"), np.abs(ny).astype("i4")
    direction = 2 * (nx < 0) + (ny < 0)
    context = (direction * 10 + dx % 10) * 12 + dy % 12
    qx, qy = dx // 10, dy // 12
    assert np.array_equal(4 * direction + 2 * (dx >= 20) + (dy >= 24), d["routes"])
    curve = (HERE.parent / "source/assets/D64.curves.u8").read_bytes()
    assert curve[:8] == b"EX654C01"
    codes = np.frombuffer(curve, "u1", count=59904 * 480, offset=64)
    values = np.frombuffer(curve, "u1", offset=64 + 59904 * 480).reshape(4, 256, 542)
    far = qx + qy > 3
    gx, gy = qx[far], qy[far]
    position = gx * 46 + gy - np.where(gx < 4, (gx + 1) * (8 - gx) // 2, 10)
    correction = np.zeros(len(query), "i4")
    index = d["pair"].astype("i8") * 480 + context
    correction[far] = values[direction[far], codes[index[far]], position].astype("i4") - 55
    assert np.array_equal(d["base_d64"] + correction, d["base_curve"])
    captured = {}
    def write(path, value):
        captured[Path(path).name] = value
    def identity(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
    scope = definitions("exp554_real_kernel_function.py", ("split",),
                        dict(np=np, SEED=20261020554, BUILD=work, ROOT=work,
                             write=write, identity=identity))
    folds = scope["split"](np.column_stack((d["pair"] // 288, d["pair"] % 288)), d["clusters"])
    assert np.array_equal(folds, d["folds"])
    report = dict(passed=True, rows=len(query), source_pins=len(unique), unique_requests=len(query),
                  frozen_features_sha256=digest, extra_features_recomputed=True,
                  event_counts=np.bincount(d["event"], minlength=3).tolist(),
                  curve_background_recomputed=True, source_pin_fold_regeneration_equal=True,
                  split=captured["split.json"], complete_estimator_runs=0)
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "split"}, indent=2))


if __name__ == "__main__":
    main()
