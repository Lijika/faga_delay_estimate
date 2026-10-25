#!/usr/bin/env python3
"""Screen two fixed symmetric-tree shapes on the historical residual cache."""
import gc
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp713/validation").resolve()))
import exp713_local_support as prior

fit = prior.fit
read, write, identity, checked = fit.read, fit.write, fit.identity, fit.checked
ROOT, BUILD = Path("validation/results/exp719"), Path("build/exp719")
PLAN = Path("experiment/实验719-同叶值预算的少树深层残差.md")
ROWS, SEED = 1_000_000, 20261025719
ARMS = {"T2D6": (2, 6, .7599), "T4D5": (4, 5, .51)}


def predict(model, x, trees, depth):
    assert np.isfinite(x).all() and np.array_equal(x, np.floor(x))
    assert model["scale_and_bias"] == [1, [0]]
    assert not model["features_info"].get("categorical_features")
    assert len(model["oblivious_trees"]) == trees
    mapping = {f["feature_index"]: f["flat_feature_index"]
               for f in model["features_info"]["float_features"]}
    raw, ids = np.zeros(len(x), "<f8"), np.empty((len(x), trees), "<u4")
    for t, tree in enumerate(model["oblivious_trees"]):
        splits = tree["splits"] or []
        assert len(splits) <= depth <= 6 and len(tree["leaf_values"]) == 1 << len(splits)
        leaf = np.zeros(len(x), "<u4")
        for j, s in enumerate(splits):
            assert s["split_type"] == "FloatFeature"
            f, cut = mapping[s["float_feature_index"]], s["border"]
            selected = x[:, f] > cut
            assert np.array_equal(selected, x[:, f] >= np.floor(cut)+1)
            leaf |= selected.astype("<u4") << j
        ids[:, t] = leaf
        raw += np.asarray(tree["leaf_values"], "<f8")[leaf]
    return raw, ids


def self_check():
    for depth in range(7):
        x = np.array([[((i >> j) & 1)-2 for j in range(depth)]
                      for i in range(1 << depth)], "<f4").reshape(1 << depth, depth)
        splits = [dict(split_type="FloatFeature", float_feature_index=j, border=-1.5)
                  for j in range(depth)]
        model = dict(scale_and_bias=[1, [0]], features_info=dict(float_features=[
            dict(feature_index=j, flat_feature_index=j) for j in range(depth)]),
            oblivious_trees=[dict(splits=splits, leaf_values=list(range(1 << depth))),
                             dict(splits=splits, leaf_values=[-i*.25 for i in range(1 << depth)])])
        value, leaf = predict(model, x, 2, depth)
        assert np.array_equal(value, .75*np.arange(1 << depth))
        assert np.array_equal(leaf, np.tile(np.arange(1 << depth)[:, None], (1, 2)))
    for trees, depth, eta in ARMS.values():
        assert trees*(1 << depth) == 128 and abs((1-eta)**trees-.7**8) < 1e-15


def data_and_references():
    data = fit.prior.source.load()
    data["base"] = fit.prior.curve_base(data)
    x = data["features"]
    assert x.shape == (ROWS, 53) and np.isfinite(x).all()
    gap = read("../exp652/doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]
    h, v, _, _ = fit.prior.events(x[:, 28:32], gap["Block"])
    assert not np.any(h & v) and int(v.sum()) == 2613
    event = h.astype("u1")+2*v
    replacement = np.fromfile("../exp678/build/exp678/HV8-raw.f64", "<f8")
    raws = dict(A=np.fromfile(fit.prior.OLD_RAW, "<f8"),
                C=np.fromfile("../exp656/build/exp656/S8-raw.f64", "<f8"))
    for raw in raws.values():
        assert raw.shape == (ROWS,) and np.isfinite(raw).all()
        raw[v] = replacement[v]
    return data, event, replacement, raws


def train(data, arm):
    trees, depth, eta = ARMS[arm]
    params = dict(prior.PARAMS, iterations=trees, depth=depth, learning_rate=eta)
    target = (data["d0"]-data["base"]).astype("<f4")
    weights = (1000/np.maximum(data["d0"]+data["mandatory"], 128)).astype("<f4")
    raw, records = np.full(ROWS, np.nan, "<f8"), []
    for fold in range(3):
        for route in range(16):
            learn = (data["folds"] != fold) & (data["routes"] == route)
            test = (data["folds"] == fold) & (data["routes"] == route)
            assert learn.any() and test.any()
            assert not np.intersect1d(data["clusters"][learn], data["clusters"][test]).size
            model = fit.cb.CatBoostRegressor(**params)
            model.fit(data["features"][learn], target[learn], sample_weight=weights[learn])
            path = BUILD/f"{arm}-{fold}-{route}.json"
            model.save_model(str(path), format="json")
            dumped, x = read(path), data["features"][test]
            values, leaves = predict(dumped, x, trees, depth)
            native = model.predict(x, thread_count=1)
            assert np.array_equal(leaves, model.calc_leaf_indexes(x, thread_count=1))
            assert np.allclose(values, native, rtol=0, atol=1e-10)
            assert np.array_equal(fit.decode(values, data["base"][test], data["mandatory"][test]),
                                  fit.decode(native, data["base"][test], data["mandatory"][test]))
            raw[test] = values
            records.append(dict(fold=fold, route=route, source_pin_overlap=0,
                train_rows=int(learn.sum()), test_rows=int(test.sum()), model=identity(path),
                params=model.get_all_params(), leaf_indices_equal=True, integer_prediction_equal=True,
                raw_max_abs_difference=float(np.abs(values-native).max()),
                depths=[len(t["splits"] or []) for t in dumped["oblivious_trees"]],
                nonempty_leaves=[sum(w > 0 for w in t["leaf_weights"]) for t in dumped["oblivious_trees"]],
                active_features=sorted({s["float_feature_index"] for t in dumped["oblivious_trees"]
                                        for s in (t["splits"] or [])})))
            del model, dumped, x, leaves
            gc.collect()
        print("EXP719_TRAINED", arm, fold, flush=True)
    assert np.isfinite(raw).all()
    raw.tofile(BUILD/(arm+"-raw.f64"))
    write(ROOT/(arm+"-training.json"), dict(complete=True, records=records, params=params,
        raw=identity(BUILD/(arm+"-raw.f64"))))
    return raw


def evaluate(data, event, raws):
    x, truth = data["features"], data["truth"]
    dx, dy = x[:, 8]+x[:, 6], x[:, 9]+x[:, 7]
    family = x[:, 0].astype("i4")
    groups = dict(source_family=family, target_family=x[:, 2].astype("i4"),
        source_lane=x[:, 1].astype("i4"), target_lane=x[:, 3].astype("i4"),
        distance=np.searchsorted([24, 100, 300], np.abs(dx)+np.abs(dy)),
        near_axis=((np.abs(dx) < 20) | (np.abs(dy) < 24)).astype("i4"),
        direction=2*(dx < 0)+(dy < 0), event=event, fold=data["folds"], route=data["routes"],
        exact_delay=np.searchsorted([128, 512, 2048], truth))
    pred = {a: fit.decode(raw, data["base"], data["mandatory"]) for a, raw in raws.items()}
    scores = {a: fit.points(p, truth) for a, p in pred.items()}
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    counts = np.bincount(family, minlength=26)
    results, eligible = {}, []
    for arm in ARMS:
        assert np.array_equal(pred[arm][event == 2], pred["A"][event == 2])
        passed = True
        for reference in ("A", "C"):
            result = fit.transition(pred[arm], pred[reference], truth, groups)
            diff = scores[arm]-scores[reference]
            totals = np.bincount(family, weights=diff, minlength=26)
            interval = np.quantile(totals[draws].sum(axis=1)/counts[draws].sum(axis=1),
                                   [.00625, .99375])
            minimum = min(v["delta_accuracy_pp"] for key, group in result["groups"].items()
                          if key in ("distance", "near_axis", "direction") for v in group.values())
            result.update(simultaneous_family_ci95_pp=interval.tolist(),
                changed_rows=int(np.count_nonzero(pred[arm] != pred[reference])),
                minimum_primary_group_delta_pp=minimum,
                quality_gate=bool(result["delta_accuracy_pp"] >= -.03 and interval[0] >= -.05
                                  and minimum >= -.10))
            passed &= result["quality_gate"]
            results[arm+"-"+reference] = result
        if passed:
            eligible.append(arm)
    for arm, p in pred.items():
        p.astype("<i4").tofile(BUILD/(arm+"-prediction.i32"))
    return dict(all_checks_passed=True, comparisons=results, eligible=eligible,
        selected=eligible[0] if eligible else None,
        metrics={a: fit.stats(p, truth) for a, p in pred.items()},
        predictions={a: identity(BUILD/(a+"-prediction.i32")) for a in pred},
        new_exact_rows=0, full_estimator_runs=0, independent_requests=False,
        V_predictions_unchanged=True, source_pin_overlap=0, static_elf_and_cpu_verified=False)


def run():
    assert not ROOT.exists() and not BUILD.exists()
    resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    start, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    (ROOT/"installed-catboost-help.txt").write_text(fit.cb.__version__+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor))+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor.fit))+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor.calc_leaf_indexes))+"\n"+
        fit.cb.CatBoostRegressor.save_model.__doc__)
    sources = []
    for record in read("../exp713/validation/results/exp713/freeze.json")["inputs"]:
        path = Path("../exp713")/record["path"]
        checked(path, record)
        sources.append(identity(path))
    for path in (fit.prior.KEYS, fit.prior.Q4, Path(__file__), PLAN, ROOT/"protocol-original.md",
                 Path(prior.__file__), Path(fit.__file__), Path(fit.prior.__file__)):
        sources.append(identity(path))
    self_check()
    data, event, replacement, raws = data_and_references()
    metrics = {a: fit.stats(fit.decode(raw, data["base"], data["mandatory"]), data["truth"])
               for a, raw in raws.items()}
    expected = read("../exp713/validation/results/exp713/report.json")["metrics"]
    assert all(abs(metrics[a][k]-expected[a][k]) < 1e-10 for a in ("A", "C") for k in metrics[a])
    write(ROOT/"freeze.json", dict(inputs=sources, params=prior.PARAMS, arms=ARMS,
        baseline_metrics=metrics, seed=SEED, decoder_self_check=True, catboost=fit.cb.__version__,
        numpy=np.__version__, python=sys.version, disk_free_start_bytes=shutil.disk_usage(".").free))
    for arm in ARMS:
        raw = train(data, arm)
        raw[event == 2] = replacement[event == 2]
        raws[arm] = raw
    report = evaluate(data, event, raws)
    report["resources"] = dict(cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-start,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        asset_bytes=sum(p.stat().st_size for p in BUILD.iterdir()),
        disk_free_end_bytes=shutil.disk_usage(".").free)
    assert report["resources"]["cpu_s"] <= 1800 and report["resources"]["wall_s"] <= 1800
    assert report["resources"]["rss_bytes"] <= 2_000_000_000
    assert report["resources"]["asset_bytes"] <= 100_000_000
    write(ROOT/"report.json", report)
    print("EXP719_COMPLETE", report["selected"],
          {k: v["delta_accuracy_pp"] for k, v in report["comparisons"].items()}, flush=True)


def audit():
    frozen, report = read(ROOT/"freeze.json"), read(ROOT/"report.json")
    for item in frozen["inputs"]:
        checked(item["path"], item)
    data, event, replacement, raws = data_and_references()
    for arm, (trees, depth, _) in ARMS.items():
        record = read(ROOT/(arm+"-training.json"))
        assert len(record["records"]) == 48
        raw = np.zeros(ROWS, "<f8")
        for r in record["records"]:
            checked(r["model"]["path"], r["model"])
            model = read(r["model"]["path"])
            test = (data["folds"] == r["fold"]) & (data["routes"] == r["route"])
            assert int(test.sum()) == r["test_rows"]
            mapping = {f["feature_index"]: f["flat_feature_index"]
                       for f in model["features_info"]["float_features"]}
            values = np.zeros(int(test.sum()), "<f8")
            assert len(model["oblivious_trees"]) == trees
            for t in model["oblivious_trees"]:
                leaf = np.zeros(len(values), "i4")
                assert len(t["splits"] or []) <= depth
                for s in reversed(t["splits"] or []):
                    leaf = 2*leaf+(data["features"][test, mapping[s["float_feature_index"]]] >
                                   s["border"]).astype("i4")
                values += np.asarray(t["leaf_values"])[leaf]
            raw[test] = values
        checked(record["raw"]["path"], record["raw"])
        assert np.array_equal(raw, np.fromfile(record["raw"]["path"], "<f8"))
        raw[event == 2] = replacement[event == 2]
        raws[arm] = raw
    predictions, scores = {}, {}
    for arm, raw in raws.items():
        checked(report["predictions"][arm]["path"], report["predictions"][arm])
        p = np.floor(np.maximum(0, data["base"]+raw)+.5).astype("i8")+data["mandatory"]
        assert np.array_equal(p, np.fromfile(report["predictions"][arm]["path"], "<i4"))
        assert np.all(data["truth"] > 0)
        scores[arm] = 100*(1-np.tanh(4*np.abs(p-data["truth"])/data["truth"]))
        assert abs(float(scores[arm].mean())-report["metrics"][arm]["accuracy_pp"]) < 1e-11
        predictions[arm] = p
        assert np.array_equal(p[event == 2], predictions["A"][event == 2])
    family = data["features"][:, 0].astype("i4")
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(20261025719).integers(26, size=(9999, 26))
    eligible = []
    for arm in ARMS:
        gates = []
        for ref in ("A", "C"):
            entry = report["comparisons"][arm+"-"+ref]
            diff = scores[arm]-scores[ref]
            totals = np.bincount(family, weights=diff, minlength=26)
            interval = np.quantile(totals[draws].sum(axis=1)/counts[draws].sum(axis=1),
                                   [.00625, .99375])
            assert abs(float(diff.mean())-entry["delta_accuracy_pp"]) < 1e-12
            assert np.array_equal(interval, entry["simultaneous_family_ci95_pp"])
            assert np.count_nonzero(predictions[arm] != predictions[ref]) == entry["changed_rows"]
            dx, dy = data["features"][:, 8]+data["features"][:, 6], data["features"][:, 9]+data["features"][:, 7]
            groups = [np.searchsorted([24, 100, 300], np.abs(dx)+np.abs(dy)),
                      ((np.abs(dx) < 20) | (np.abs(dy) < 24)).astype("i4"), 2*(dx < 0)+(dy < 0)]
            minimum = min(float(diff[g == k].mean()) for g in groups for k in np.unique(g))
            assert minimum == entry["minimum_primary_group_delta_pp"]
            gate = bool(diff.mean() >= -.03 and interval[0] >= -.05 and minimum >= -.10)
            assert gate == entry["quality_gate"]
            gates.append(gate)
        if all(gates):
            eligible.append(arm)
    assert eligible == report["eligible"] and report["selected"] == (eligible[0] if eligible else None)
    result = dict(all_checks_passed=True, independently_decoded_models=96,
        original_data_loader_reused=True, predictions_and_statistics_recomputed=True,
        new_exact_rows=0, full_estimator_runs=0, selected=report["selected"],
        report=identity(ROOT/"report.json"))
    write(ROOT/"independent-audit.json", result)
    print("EXP719_AUDIT", result, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp719")
    assert os.environ["OPENBLAS_NUM_THREADS"] == os.environ["OMP_NUM_THREADS"] == "1"
    assert fit.cb.__version__ == "1.2.8"
    assert sys.argv[1:] in (["run"], ["audit"])
    dict(run=run, audit=audit)[sys.argv[1]]()
