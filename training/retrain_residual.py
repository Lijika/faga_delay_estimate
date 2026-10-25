#!/usr/bin/env python3
"""Retrain one original residual expert from the published, lossless data."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import time

import catboost as cb
import numpy as np

HERE = Path(__file__).resolve().parent


def historical_definitions(filename, names, scope):
    path = HERE / "original/validation" / filename
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


def load():
    manifest = json.loads((HERE / "data/export-manifest.json").read_text())
    for record in manifest["outputs"]:
        path = HERE / "data" / Path(record["path"]).name
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    with np.load(HERE / "data/targets_splits.npz") as packed:
        data = {k: packed[k] for k in packed.files}
    with np.load(HERE / "data/features53.npz") as packed:
        data["features"] = packed["features"].astype("<f4")
    with np.load(HERE / "data/features_extra18.npz") as packed:
        data["extra"] = packed["features"].astype("<f4")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("s8", "v8"), required=True)
    parser.add_argument("--fold", type=int, choices=(-1, 0, 1, 2), default=-1,
                        help="-1 trains the final model; 0..2 excludes that source-pin fold")
    parser.add_argument("--route", type=int, choices=range(16),
                        help="required for S8")
    parser.add_argument("--background", choices=("q4", "curve", "d64"),
                        help="defaults to the original background for the selected expert")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert cb.__version__ == "1.2.8", cb.__version__
    if (args.model == "s8") != (args.route is not None):
        parser.error("--route is required only for S8")
    args.output.mkdir(parents=True, exist_ok=False)
    data = load()
    background = args.background or ("q4" if args.model == "s8" else "curve")
    base = data["base_" + background]
    mask = data["routes"] == args.route if args.model == "s8" else data["event"] == 2
    heldout = mask & (data["folds"] == args.fold) if args.fold >= 0 else np.zeros(len(mask), bool)
    train = mask & ~heldout
    if args.fold >= 0:
        assert not np.intersect1d(data["clusters"][train], data["clusters"][heldout]).size
    features = data["features"] if args.model == "s8" else np.column_stack((data["features"], data["extra"]))
    original = HERE.parent / "validation/results" / ("exp640/prepare.json" if args.model == "s8"
                                                    else "exp678/freeze.json")
    params = json.loads(original.read_text())["params"]
    model = cb.CatBoostRegressor(**params)
    target = (data["d0"] - base).astype("<f4")
    weight = (1000 / np.maximum(data["d0"] + data["mandatory"], 128)).astype("<f4")
    started = time.monotonic()
    model.fit(features[train], target[train], sample_weight=weight[train])
    model.save_model(str(args.output / "model.json"), format="json")
    dumped = json.loads((args.output / "model.json").read_text())
    decoder = historical_definitions("exp640_symmetric_residual.py",
                                     ("json_prediction", "self_check"), dict(np=np))
    decoder["self_check"]()
    audit = features[heldout if args.fold >= 0 else train]
    decoded, leaves = decoder["json_prediction"](dumped, audit, 8)
    assert np.array_equal(leaves, model.calc_leaf_indexes(audit, ntree_end=8, thread_count=1))
    native = model.predict(audit, ntree_end=8, thread_count=1)
    assert np.allclose(decoded, native, rtol=0, atol=1e-10)
    frozen_equal = None
    if args.fold == -1 and args.background is None:
        name = f"S16-final-{args.route}.json" if args.model == "s8" else "V64-final.json"
        frozen = json.loads((HERE.parent / "source/models" / name).read_text())
        frozen_equal = all(dumped[k] == frozen[k]
                           for k in ("oblivious_trees", "features_info", "scale_and_bias"))
        assert frozen_equal, "trained model differs from frozen model; inspect toolchain/data"
    report = dict(model=args.model, route=args.route, fold=args.fold, background=background,
                  train_rows=int(train.sum()), heldout_rows=int(heldout.sum()),
                  training_trees=params["iterations"], deployment_trees=8, params=params,
                  leaf_ids_equal=True, raw_max_abs_difference=float(abs(decoded - native).max()),
                  matches_frozen_model_fields=frozen_equal, wall_s=time.monotonic() - started,
                  source_pin_overlap=0 if args.fold >= 0 else None,
                  historical_development_data=True, complete_estimator_runs=0)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
