#!/usr/bin/env python3
"""Separate final-delay supervision from its relative-error weighting."""
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

sys.path.insert(0, str(Path("../exp719/validation").resolve()))
import exp719_leaf_budget as prior

fit = prior.fit
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked
ROOT, BUILD = Path("validation/results/exp726"), Path("build/exp726")
PLAN = Path("experiment/实验726-完整延迟监督与评分分母的四格对照.md")
ROWS, SEED = 1_000_000, 20261025726
ARMS = ("W", "Y", "J")
PARAMS = dict(prior.prior.PARAMS, iterations=2, depth=6, learning_rate=.7599)


def data_and_baseline():
    data, event, replacement, _ = prior.data_and_references()
    assert np.all(data["truth"] > 0)
    record = read("../exp719/validation/results/exp719/T2D6-training.json")
    assert record["params"] == PARAMS
    path = Path("../exp719")/record["raw"]["path"]
    checked(path, record["raw"])
    raw = np.fromfile(path, "<f8")
    assert raw.shape == (ROWS,) and np.isfinite(raw).all()
    raw[event == 2] = replacement[event == 2]
    predictions = fit.decode(raw, data["base"], data["mandatory"])
    expected = read("../exp719/validation/results/exp719/report.json")["metrics"]["T2D6"]
    for key, value in fit.stats(predictions, data["truth"]).items():
        assert abs(value-expected[key]) < 1e-10
    return data, event, replacement, raw


def targets(data):
    g, d0, b, f = (data[k].astype("i8") for k in ("truth", "d0", "base", "mandatory"))
    old, final = (d0-b).astype("<f4"), (g-b-f).astype("<f4")
    assert np.array_equal(final-old, g-d0-f)
    legacy = (1000/np.maximum(d0+f, 128)).astype("<f4")
    relative = (1000/g).astype("<f4")
    assert np.isfinite(relative).all() and np.all(relative > 0)
    residual = np.asarray([-4., 0., 3., 9.])
    bg, fee, truth = np.array([10., 20., 30., 40.]), 5., np.array([12., 28., 39., 42.])
    assert np.array_equal(np.abs(bg+fee+residual-truth)/truth,
                          np.abs(residual-(truth-bg-fee))/truth)
    return {"W": (old, relative), "Y": (final, legacy), "J": (final, relative)}, dict(
        changed_targets=int(np.count_nonzero(final != old)),
        target_delta_range=[int((g-d0-f).min()), int((g-d0-f).max())],
        truth_range=[int(g.min()), int(g.max())],
        relative_weight_range=[float(relative.min()), float(relative.max())],
        weight_ratio_range=[float((relative/legacy).min()), float((relative/legacy).max())])


def train(data, arm, target, weight):
    raw, records = np.full(ROWS, np.nan, "<f8"), []
    for fold in range(3):
        for route in range(16):
            learn = (data["folds"] != fold) & (data["routes"] == route)
            test = (data["folds"] == fold) & (data["routes"] == route)
            assert learn.any() and test.any()
            assert not np.intersect1d(data["clusters"][learn], data["clusters"][test]).size
            model = fit.cb.CatBoostRegressor(**PARAMS)
            model.fit(data["features"][learn], target[learn], sample_weight=weight[learn])
            path = BUILD/f"{arm}-{fold}-{route}.json"
            model.save_model(str(path), format="json")
            values, leaves = prior.predict(read(path), data["features"][test], 2, 6)
            native = model.predict(data["features"][test], thread_count=1)
            assert np.array_equal(leaves, model.calc_leaf_indexes(data["features"][test], thread_count=1))
            assert np.allclose(values, native, rtol=0, atol=1e-10)
            assert np.array_equal(fit.decode(values, data["base"][test], data["mandatory"][test]),
                                  fit.decode(native, data["base"][test], data["mandatory"][test]))
            raw[test] = values
            records.append(dict(fold=fold, route=route, train_rows=int(learn.sum()),
                test_rows=int(test.sum()), model=identity(path), source_pin_overlap=0,
                params=model.get_all_params(), native_leaf_ids_equal=True,
                integer_predictions_equal=True, raw_max_abs_difference=float(np.abs(values-native).max())))
            del model, native, leaves
            gc.collect()
        print("EXP726_TRAINED", arm, fold, flush=True)
    assert np.isfinite(raw).all()
    raw.tofile(BUILD/(arm+"-raw.f64"))
    write(ROOT/(arm+"-training.json"), dict(params=PARAMS, records=records,
        raw=identity(BUILD/(arm+"-raw.f64"))))
    return raw


def groups(data, event):
    x = data["features"]
    dx, dy = x[:, 8]+x[:, 6], x[:, 9]+x[:, 7]
    return dict(source_family=x[:, 0].astype("i4"), target_family=x[:, 2].astype("i4"),
        source_lane=x[:, 1].astype("i4"), target_lane=x[:, 3].astype("i4"),
        distance=np.searchsorted([24, 100, 300], np.abs(dx)+np.abs(dy)),
        near_axis=((np.abs(dx) < 20) | (np.abs(dy) < 24)).astype("i4"),
        direction=2*(dx < 0)+(dy < 0), event=event, fold=data["folds"],
        exact_delay=np.searchsorted([128, 512, 2048], data["truth"]),
        line_remainder=(data["truth"] != data["d0"]+data["mandatory"]).astype("i4"))


def evaluate(data, event, raws):
    grouped = groups(data, event)
    pred = {a: fit.decode(v, data["base"], data["mandatory"]) for a, v in raws.items()}
    scores = {a: fit.points(p, data["truth"]) for a, p in pred.items()}
    family = grouped["source_family"]
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    comparisons, eligible = {}, []
    for arm in ARMS:
        assert np.array_equal(pred[arm][event == 2], pred["A"][event == 2])
        result = fit.transition(pred[arm], pred["A"], data["truth"], grouped)
        diff = scores[arm]-scores["A"]
        totals = np.bincount(family, weights=diff, minlength=26)
        interval = np.quantile(totals[draws].sum(axis=1)/counts[draws].sum(axis=1), [.05/6, 1-.05/6])
        minimum = min(v["delta_accuracy_pp"] for key, group in result["groups"].items()
                      if key in ("distance", "near_axis", "direction") for v in group.values())
        passed = bool(result["delta_accuracy_pp"] >= .05 and interval[0] > 0 and minimum >= -.03)
        result.update(simultaneous_family_ci95_pp=interval.tolist(), minimum_group_delta_pp=minimum,
                      changed_rows=int(np.count_nonzero(pred[arm] != pred["A"])), quality_gate=passed)
        for key, values in grouped.items():
            for value in np.unique(values):
                mask = values == value
                item = result["groups"][key][str(int(value))]
                item["population_fraction"] = float(mask.mean())
                item["baseline_global_loss_pp"] = float(np.sum(100-scores["A"][mask])/ROWS)
                item["global_delta_pp"] = float(diff[mask].sum()/ROWS)
        comparisons[arm] = result
        if passed:
            eligible.append(arm)
    selected = max(eligible, key=lambda a: (comparisons[a]["delta_accuracy_pp"],
                                            {"W": 0, "Y": 1, "J": 2}[a])) if eligible else None
    for arm, p in pred.items():
        p.astype("<i4").tofile(BUILD/(arm+"-prediction.i32"))
    return dict(all_checks_passed=True, selected=selected, eligible=eligible,
        comparisons=comparisons, metrics={a: fit.stats(p, data["truth"]) for a, p in pred.items()},
        interaction_pp=float((scores["J"]-scores["Y"]-scores["W"]+scores["A"]).mean()),
        predictions={a: identity(BUILD/(a+"-prediction.i32")) for a in pred},
        new_exact_rows=0, complete_program_runs=0, independent_requests=False,
        source_pin_overlap=0, V_predictions_unchanged=True, static_elf_and_cpu_verified=False)


def run():
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    start, cpu = time.monotonic(), time.process_time()
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    (ROOT/"installed-catboost-help.txt").write_text(fit.cb.__version__+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor.fit))+"\n"+
        str(inspect.signature(fit.cb.CatBoostRegressor.calc_leaf_indexes))+"\n"+
        fit.cb.CatBoostRegressor.save_model.__doc__)
    inputs = []
    for item in read("../exp719/validation/results/exp719/freeze.json")["inputs"]:
        path = Path("../exp719")/item["path"]
        checked(path, item)
        inputs.append(identity(path))
    for path in (Path(__file__), PLAN, ROOT/"protocol-original.md", Path(prior.__file__),
                 Path("../exp719/validation/results/exp719/T2D6-training.json"),
                 Path("../exp719/validation/results/exp719/independent-audit.json")):
        inputs.append(identity(path))
    assert read("../exp719/validation/results/exp719/independent-audit.json")["all_checks_passed"]
    prior.self_check()
    data, event, replacement, raw = data_and_baseline()
    tasks, diagnostic = targets(data)
    write(ROOT/"freeze.json", dict(inputs=inputs, params=PARAMS, seed=SEED,
        numpy=np.__version__, catboost=fit.cb.__version__, python=sys.version,
        target_check=diagnostic, baseline_raw=identity("../exp719/build/exp719/T2D6-raw.f64"),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    write(ROOT/"target-groups.json", {name: {str(int(value)): dict(
        rows=int((values == value).sum()),
        mean_target_delta=float((data["truth"]-data["d0"]-data["mandatory"])[values == value].mean()))
        for value in np.unique(values)} for name, values in groups(data, event).items()
        if name in ("source_family", "distance")})
    raws = {"A": raw}
    for arm, (target, weight) in tasks.items():
        candidate = train(data, arm, target, weight)
        candidate[event == 2] = replacement[event == 2]
        raws[arm] = candidate
    report = evaluate(data, event, raws)
    report["resources"] = dict(cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-start,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        asset_bytes=sum(p.stat().st_size for p in BUILD.iterdir()),
        disk_free_end_bytes=shutil.disk_usage(".").free)
    assert report["resources"]["cpu_s"] <= 1800 and report["resources"]["wall_s"] <= 1800
    assert report["resources"]["rss_bytes"] <= 2_000_000_000
    assert report["resources"]["asset_bytes"] <= 100_000_000
    write(ROOT/"report.json", report)
    print("EXP726_COMPLETE", report["selected"],
          {a: r["delta_accuracy_pp"] for a, r in report["comparisons"].items()}, flush=True)


def audit():
    frozen, report = read(ROOT/"freeze.json"), read(ROOT/"report.json")
    for item in frozen["inputs"]:
        checked(item["path"], item)
    checked(frozen["baseline_raw"]["path"], frozen["baseline_raw"])
    data, event, replacement, baseline = data_and_baseline()
    _, diagnostic = targets(data)
    assert diagnostic == frozen["target_check"]
    raws, decoded = {"A": baseline}, 0
    for arm in ARMS:
        training = read(ROOT/(arm+"-training.json"))
        assert len(training["records"]) == 48 and training["params"] == PARAMS
        raw = np.zeros(ROWS, "<f8")
        coverage = np.zeros(ROWS, "u1")
        for item in training["records"]:
            checked(item["model"]["path"], item["model"])
            model = read(item["model"]["path"])
            mask = (data["folds"] == item["fold"]) & (data["routes"] == item["route"])
            learn = (data["folds"] != item["fold"]) & (data["routes"] == item["route"])
            assert not np.intersect1d(data["clusters"][mask], data["clusters"][learn]).size
            assert int(mask.sum()) == item["test_rows"] and int(learn.sum()) == item["train_rows"]
            assert model["scale_and_bias"] == [1, [0]] and len(model["oblivious_trees"]) == 2
            mapping = {v["feature_index"]: v["flat_feature_index"]
                       for v in model["features_info"]["float_features"]}
            value = np.zeros(int(mask.sum()), "<f8")
            for tree in model["oblivious_trees"]:
                leaf = np.zeros(len(value), "i4")
                assert len(tree["splits"] or []) <= 6
                for split in reversed(tree["splits"] or []):
                    assert split["split_type"] == "FloatFeature"
                    leaf = 2*leaf+(data["features"][mask, mapping[split["float_feature_index"]]] >
                                   split["border"]).astype("i4")
                value += np.asarray(tree["leaf_values"])[leaf]
            raw[mask] = value
            coverage[mask] += 1
            decoded += 1
        assert np.all(coverage == 1)
        checked(training["raw"]["path"], training["raw"])
        assert np.array_equal(raw, np.fromfile(training["raw"]["path"], "<f8"))
        raw[event == 2] = replacement[event == 2]
        raws[arm] = raw
    predictions, scores = {}, {}
    for arm, raw in raws.items():
        checked(report["predictions"][arm]["path"], report["predictions"][arm])
        p = np.floor(np.maximum(0, data["base"]+raw)+.5).astype("i8")+data["mandatory"]
        assert np.array_equal(p, np.fromfile(report["predictions"][arm]["path"], "<i4"))
        score = 100-100*np.tanh(4*np.abs(p-data["truth"])/data["truth"])
        assert abs(float(score.mean())-report["metrics"][arm]["accuracy_pp"]) < 1e-10
        predictions[arm], scores[arm] = p, score
    family = data["features"][:, 0].astype("i4")
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    partition = groups(data, event)
    eligible = []
    for arm in ARMS:
        item = report["comparisons"][arm]
        diff = scores[arm]-scores["A"]
        assert np.array_equal(predictions[arm][event == 2], predictions["A"][event == 2])
        assert int(np.count_nonzero(predictions[arm] != predictions["A"])) == item["changed_rows"]
        totals = np.bincount(family, weights=diff, minlength=26)
        interval = np.quantile(totals[draws].sum(axis=1)/counts[draws].sum(axis=1), [.05/6, 1-.05/6])
        assert np.allclose(interval, item["simultaneous_family_ci95_pp"], rtol=0, atol=1e-10)
        minimum = min(float(diff[values == value].mean()) for key, values in partition.items()
                      if key in ("distance", "near_axis", "direction") for value in np.unique(values))
        assert abs(minimum-item["minimum_group_delta_pp"]) < 1e-10
        assert abs(float(diff.mean())-item["delta_accuracy_pp"]) < 1e-10
        for key, values in partition.items():
            for value in np.unique(values):
                mask = values == value
                group = item["groups"][key][str(int(value))]
                assert int(mask.sum()) == group["rows"]
                assert abs(float(diff[mask].mean())-group["delta_accuracy_pp"]) < 1e-10
                assert abs(float(diff[mask].sum()/ROWS)-group["global_delta_pp"]) < 1e-10
                assert abs(float((100-scores["A"][mask]).sum()/ROWS)-
                           group["baseline_global_loss_pp"]) < 1e-10
        passed = bool(diff.mean() >= .05 and interval[0] > 0 and minimum >= -.03)
        assert passed == item["quality_gate"]
        if passed:
            eligible.append(arm)
    selected = max(eligible, key=lambda a: (report["comparisons"][a]["delta_accuracy_pp"],
                                            {"W": 0, "Y": 1, "J": 2}[a])) if eligible else None
    assert selected == report["selected"] and eligible == report["eligible"]
    assert abs(float((scores["J"]-scores["Y"]-scores["W"]+scores["A"]).mean())-
               report["interaction_pp"]) < 1e-10
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True,
        independently_decoded_models=decoded, loader_reused=True, groups_reused=True,
        leaf_decoding_and_scoring_independent=True, paired_statistics_recomputed=True,
        selected=selected, new_exact_rows=0, complete_program_runs=0,
        report=identity(ROOT/"report.json"), auditor=identity(Path(__file__))))
    print("EXP726_AUDIT", selected, decoded, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp726")
    assert os.environ["OPENBLAS_NUM_THREADS"] == os.environ["OMP_NUM_THREADS"] == "1"
    assert fit.cb.__version__ == "1.2.8"
    assert sys.argv[1:] in (["run"], ["audit"])
    resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    dict(run=run, audit=audit)[sys.argv[1]]()
