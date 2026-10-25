#!/usr/bin/env python3
"""Recompute the 1B sample statistics and reconcile them with the timed output."""
import csv
import itertools
import math
from pathlib import Path
import statistics
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
from exp709_cost_skeleton import read, write, identity, check

ROOT = Path("validation/results/exp722")


def interval(values, pair, family, population, seed):
    order = np.argsort(pair, kind="stable")
    matrix = values[order].reshape(59904, 64)
    assert np.array_equal(pair[order].reshape(59904, 64), np.repeat(np.arange(59904)[:, None], 64, axis=1))
    mass = population/1_000_000_000
    point = float(np.dot(matrix.mean(axis=1), mass))
    variance = float(np.dot(matrix.var(axis=1, ddof=1)/64*(1-64/population), mass**2))
    half = statistics.NormalDist().inv_cdf(.9875)*math.sqrt(variance)
    weights = population[pair]/64
    fm = np.asarray([weights[family == i].sum() for i in range(26)])
    ft = np.asarray([np.dot(weights[family == i], values[family == i]) for i in range(26)])
    draws = np.random.default_rng(seed).integers(26, size=(9999, 26))
    bootstrap = np.quantile(ft[draws].sum(axis=1)/fm[draws].sum(axis=1), [.0125, .9875])
    return dict(point_pp=point, stratified_variance_pp2=variance,
        stratified_ci975_pp=[point-half, point+half], family_ci975_pp=bootstrap.tolist(),
        conservative_ci975_pp=[min(point-half, bootstrap[0]), max(point+half, bootstrap[1])])


def main():
    report, decision = read(ROOT/"1b-report.json"), read(ROOT/"1b-decision.json")
    score, reuse = read(ROOT/"score-1b/accuracy.json"), read(ROOT/"score-reuse-freeze.json")
    freeze = read(ROOT/"1b-freeze.json")
    check(ROOT/"1b-report.json", decision["report"])
    check(ROOT/"1b-report.json", reuse["report"])
    check(ROOT/"score-1b/accuracy.json", decision["score"])
    assert report["rows"] == report["unique_rows"] == 1_000_000_000
    assert report["port_pairs"] == 59904 and report["exact_sample_rows"] == 3_833_856
    assert all(report["binary"][k] == freeze["binary"][k] for k in ("bytes", "sha256"))
    assert report["input"] == freeze["input"]
    run, raw = report["run"], read(ROOT/"1b.run.json")
    assert all(run[k] == v for k, v in raw.items())
    assert run["threads"] == 1 and run["exit_code"] == 0 and run["rss_bytes"] <= 2_000_000_000
    assert abs(run["cpu_s"]-run["user_s"]-run["sys_s"]) < 1e-10 and run["wall_s"] <= 3600
    assert read(ROOT/"1b.stderr") == dict(rows=1_000_000_000, unreachable=0, query_allocations=0)
    assert report["contract"]["contract_passed"] and report["contract"]["rows"] == 1_000_000_000
    assert report["contract"]["sample_rows"] == 3_833_856 and report["contract_run"]["exit_code"] == 0
    assert score["evidence"]["C"]["source_run"] == run
    assert score["evidence"]["C"]["source_output"] == report["output"]
    base = Path("../exp683")
    frozen = read(base/"validation/results/exp683/1b/freeze.json")
    labels = read(base/"validation/results/exp683/1b/report.json")
    positions = np.loadtxt(base/"build/exp683/1b/positions.txt", dtype="i8")
    population = np.asarray(read(base/"build/exp683/1b/pair-populations.json"), "i8")
    assert population.sum() == 1_000_000_000 and np.all(np.diff(positions) > 0)
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    families = dict(zip(mapping["sources"], [v[0] for v in mapping["source_coordinates"]]))
    si, ti = (dict(zip(score[name], range(len(score[name])))) for name in ("source_ports", "target_ports"))
    n = 3_833_856
    truth, pair, family, a, c = (np.empty(n, "i8") for _ in range(5))
    paths = {arm: Path(e["sample"]["path"]) for arm,e in score["evidence"].items()}
    for arm, path in paths.items():
        check(path, score["evidence"][arm]["sample"])
    check(base/labels["exact"]["path"], labels["exact"])
    with (base/labels["exact"]["path"]).open(newline="") as ef, \
            paths["A"].open(newline="") as af, paths["C"].open(newline="") as cf:
        er, ar, cr = csv.reader(ef), csv.reader(af), csv.reader(cf)
        assert next(er) == ["index", "from", "to", "exact", "expanded", "relaxed", "cpu_s"]
        assert next(ar) == next(cr) == ["row", "From", "To", "delay"]
        for i, (e, aa, cc) in enumerate(itertools.zip_longest(er, ar, cr)):
            assert i < n and e is not None and aa is not None and cc is not None
            assert e[0] == str(i) and aa[:3] == cc[:3] == [str(positions[i]), *e[1:3]]
            source, target = (pin.split("/", 1)[1] for pin in e[1:3])
            truth[i], pair[i], family[i] = int(e[3]), si[source]*288+ti[target], families[source]
            a[i], c[i] = int(aa[3]), int(cc[3])
        assert i+1 == n
    assert np.all(truth >= 0) and np.all(a >= 0) and np.all(c >= 0)
    scores = {arm: np.where(truth == 0, np.where(pred == 0, 100., 0.),
        100*(1-np.tanh(4*np.abs(pred-truth)/np.maximum(truth, 1)))) for arm,pred in (("A",a),("C",c))}
    estimates = {k: interval(v, pair, family, population, frozen["seed"])
                 for k,v in {**scores, "delta": scores["C"]-scores["A"]}.items()}
    for name, estimate in estimates.items():
        expected = score["delta_accuracy"] if name == "delta" else score["accuracy"][name]
        for key, value in estimate.items():
            assert np.allclose(value, expected[key], rtol=0, atol=1e-9), (name, key)
    for groups in score["groups"].values():
        assert sum(g["sample_rows"] for g in groups.values()) == n
        assert abs(math.fsum(g["estimated_population_rows"] for g in groups.values())-1_000_000_000) < .001
        for arm in ("A", "C"):
            value = math.fsum(g["estimated_population_rows"]*g["accuracy_pp"][arm] for g in groups.values())/1_000_000_000
            assert abs(value-estimates[arm]["point_pp"]) < 1e-9
    assert score["changed_sample_rows"] == np.count_nonzero(a != c)
    assert score["improved_sample_rows"] == np.count_nonzero(np.abs(c-truth) < np.abs(a-truth))
    assert score["worse_sample_rows"] == np.count_nonzero(np.abs(c-truth) > np.abs(a-truth))
    events_id = score["validation_input"]["events"]
    check(base/events_id["path"], events_id)
    events = np.fromfile(base/events_id["path"], "u1")
    assert len(events) == n and np.array_equal(a[events == 2], c[events == 2])
    minimum = min(g["accuracy_pp"]["C"]-g["accuracy_pp"]["A"]
                  for name in ("distance", "direction", "near_axis") for g in score["groups"][name].values())
    delta = estimates["delta"]
    quality = delta["point_pp"] >= -.03 and delta["conservative_ci975_pp"][0] >= -.05 and minimum >= -.10
    assert decision["quality_gate"] == quality and abs(decision["minimum_group_delta_pp"]-minimum) < 1e-9
    write(ROOT/"close-audit.json", dict(all_checks_passed=True, quality_gate=quality,
        estimates=estimates, run_cpu_s=run["cpu_s"], exact_sample_rows=n,
        same_complete_run_cpu_and_accuracy=True, one_candidate_run=True,
        baseline_cpu_historical=True, new_estimator_runs=0,
        files=[identity(p) for p in (Path(__file__), ROOT/"1b-report.json", ROOT/"score-1b/accuracy.json")]))
    print("EXP722_CLOSE_AUDIT", quality, run["cpu_s"], estimates["C"], flush=True)


if __name__ == "__main__":
    main()
