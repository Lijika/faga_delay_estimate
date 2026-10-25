#!/usr/bin/env python3
"""Independently recompute the frozen 100M decision from exact and output rows."""
import csv
import itertools
import math
from pathlib import Path
import statistics

import numpy as np

from exp720_leaf_cli import identity, write, read, check

ROOT, BUILD = Path("validation/results/exp720"), Path("build/exp720")


def close(a, b, tolerance=1e-9):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance, (a, b)


def interval(values, pair, family, population, seed):
    order = np.argsort(pair, kind="stable")
    matrix = values[order].reshape(59904, 32)
    assert np.array_equal(pair[order].reshape(59904, 32), np.repeat(np.arange(59904)[:, None], 32, axis=1))
    mass = population/100_000_000
    point = float(np.dot(matrix.mean(axis=1), mass))
    variance = float(np.dot(matrix.var(axis=1, ddof=1)/32*(1-32/population), mass**2))
    half = statistics.NormalDist().inv_cdf(.9875)*math.sqrt(variance)
    weights = population[pair]/32
    fm = np.asarray([weights[family == i].sum() for i in range(26)])
    ft = np.asarray([np.dot(weights[family == i], values[family == i]) for i in range(26)])
    draws = np.random.default_rng(seed).integers(26, size=(9999, 26))
    bootstrap = np.quantile(ft[draws].sum(axis=1)/fm[draws].sum(axis=1), [.0125, .9875])
    return dict(point_pp=point, stratified_variance_pp2=variance,
        stratified_ci975_pp=[point-half, point+half], family_ci975_pp=bootstrap.tolist(),
        conservative_ci975_pp=[min(point-half, bootstrap[0]), max(point+half, bootstrap[1])])


def main():
    frozen, timing = read(ROOT/"freeze.json"), read(ROOT/"100m-report.json")
    labels, inputs = read(ROOT/"expanded/report.json"), read(ROOT/"expanded/input.json")
    score, decision = read(ROOT/"score/accuracy.json"), read(ROOT/"decision.json")
    assert labels["all_complete_label_checks"] and labels["span_checks"] == 12
    assert labels["rows"] == labels["unique_rows"] == score["sample_rows"] == 1_916_928
    assert inputs["training_request_overlap"] == inputs["training_source_pin_overlap"] == inputs["old_sample_overlap"] == 0
    assert len(labels["runs"]) == 4 and all(r["exit_code"] == 0 for r in labels["runs"])
    assert sum(r["cpu_s"] for r in labels["runs"]) <= 10_000
    assert max(r["rss_bytes"] for r in labels["runs"]) <= 2_000_000_000
    assert timing["rows"] == timing["unique_rows"] == 100_000_000
    assert timing["port_pairs"] == score["port_pairs"] == 59904
    schedule = [list(v) for v in ("AC", "AC", "CA", "AC", "CA", "AC", "CA")]
    assert frozen["schedule"] == schedule and len(timing["runs"]) == 14
    assert len(timing["deleted_duplicates"]) == 12
    for index, run in enumerate(timing["runs"]):
        iteration, slot = divmod(index, 2)
        arm = schedule[iteration][slot]
        raw = read(ROOT/f"100m-{iteration}-{arm}.run.json")
        assert all(run[k] == v for k, v in raw.items())
        assert run["arm"] == arm and run["iteration"] == iteration
        assert run["command"][:4] == ["taskset", "-c", "8", frozen["binaries"][arm]["path"]]
        assert run["command"][4:6] == ["-in", timing["input"]["path"]]
        assert run["exit_code"] == 0 and run["threads"] == 1
        assert run["rss_bytes"] <= 2_000_000_000 and run["cpu_s"] < 100 and run["wall_s"] <= 3600
        assert run["counters"] == read(run["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
        assert run["input"] == timing["input"]
        assert all(run["output"][k] == timing["evidence"][arm]["output"][k] for k in ("bytes", "sha256"))
        if iteration:
            close(run["cpu_s"], timing["timing"][arm][iteration-1])
    for arm in ("A", "C"):
        e = timing["evidence"][arm]
        assert len(timing["timing"][arm]) == 6 and e["contract"]["contract_passed"]
        assert e["contract"]["rows"] == 100_000_000 and e["contract"]["sample_rows"] == 1_916_928
        assert score["evidence"][arm]["source_run"] == e["run"]
        assert score["evidence"][arm]["source_output"] == e["output"]
        check(e["sample"]["path"], e["sample"])
    for item in timing["deleted_duplicates"]:
        assert all(item["file"][k] == item["identical_to"][k] for k in ("bytes", "sha256"))
    assert timing["released_bytes"] == sum(d["file"]["bytes"] for d in timing["deleted_duplicates"])
    check(labels["exact"]["path"], labels["exact"])
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    families = dict(zip(mapping["sources"], [v[0] for v in mapping["source_coordinates"]]))
    si, ti = (dict(zip(score[name], range(len(score[name])))) for name in ("source_ports", "target_ports"))
    population = np.asarray(read(BUILD/"expanded/pair-populations.json"), "i8")
    positions = np.loadtxt(BUILD/"expanded/positions.txt", dtype="i8")
    n = 1_916_928
    assert population.sum() == 100_000_000 and len(positions) == n and np.all(np.diff(positions) > 0)
    truth, pair, family, a, c = (np.empty(n, "i8") for _ in range(5))
    with Path(labels["exact"]["path"]).open(newline="") as ef, \
            Path(timing["evidence"]["A"]["sample"]["path"]).open(newline="") as af, \
            Path(timing["evidence"]["C"]["sample"]["path"]).open(newline="") as cf:
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
    assert np.all(np.bincount(pair, minlength=59904) == 32)
    scores = {}
    for arm, prediction in (("A", a), ("C", c)):
        values = np.where(truth == 0, np.where(prediction == 0, 100., 0.),
                          100*(1-np.tanh(4*np.abs(prediction-truth)/np.maximum(truth, 1))))
        scores[arm] = values
    estimates = {k: interval(v, pair, family, population, frozen["seed"])
                 for k, v in {**scores, "delta": scores["C"]-scores["A"]}.items()}
    for name, estimate in estimates.items():
        expected = score["delta_accuracy"] if name == "delta" else score["accuracy"][name]
        for key, value in estimate.items():
            assert np.allclose(value, expected[key], rtol=0, atol=1e-9), (name, key, value, expected[key])
    weights = population[pair]/32
    for groups in score["groups"].values():
        assert sum(g["sample_rows"] for g in groups.values()) == n
        close(math.fsum(g["estimated_population_rows"] for g in groups.values()), 100_000_000, 1e-6)
        for arm in ("A", "C"):
            close(math.fsum(g["estimated_population_rows"]*g["accuracy_pp"][arm]
                           for g in groups.values())/100_000_000, estimates[arm]["point_pp"])
    assert score["changed_sample_rows"] == np.count_nonzero(a != c)
    assert score["improved_sample_rows"] == np.count_nonzero(np.abs(c-truth) < np.abs(a-truth))
    assert score["worse_sample_rows"] == np.count_nonzero(np.abs(c-truth) > np.abs(a-truth))
    for arm, pred in (("A", a), ("C", c)):
        close(score["errors"][arm]["mae_ps"], float(np.average(np.abs(pred-truth), weights=weights)))
    check(inputs["events"]["path"], inputs["events"])
    events = np.fromfile(inputs["events"]["path"], "u1")
    v_equal = bool(np.array_equal(a[events == 2], c[events == 2]))
    assert score["V_predictions_unchanged"] == v_equal
    delta = estimates["delta"]
    saved = [x-y for x, y in zip(timing["timing"]["A"], timing["timing"]["C"])]
    mean = statistics.mean(saved)
    half = 3.163381449748624*statistics.stdev(saved)/math.sqrt(6)
    joint = score["joint"]
    close(joint["saved_cpu_s"], mean)
    assert np.allclose(joint["ci975_saved_cpu_s"], [mean-half, mean+half], rtol=0, atol=1e-9)
    point = .8*delta["point_pp"]+mean/12
    lower = .8*delta["conservative_ci975_pp"][0]+(mean-half)/12
    close(joint["score_extrapolated_1b"], point)
    close(joint["conservative_ci95_score_lower"], lower)
    minimum = min(g["accuracy_pp"]["C"]-g["accuracy_pp"]["A"]
                  for name in ("distance", "direction", "near_axis") for g in score["groups"][name].values())
    gates = dict(quality=delta["point_pp"] >= -.03 and delta["conservative_ci975_pp"][0] >= -.05 and minimum >= -.10,
                 V_unchanged=v_equal, cpu=mean >= .5 and mean-half > 0, combined=bool(point >= .005 and lower > 0))
    assert gates == decision["gates"] and decision["selected"] == all(gates.values())
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True, selected=all(gates.values()), gates=gates,
        original_rows_recomputed=n, complete_runs=14, same_output_runs_per_arm=7, estimates=estimates,
        mean_cpu_s={a: statistics.mean(v) for a, v in timing["timing"].items()},
        label_cpu_s=sum(r["cpu_s"] for r in labels["runs"]),
        cpu_components_recorded=False,
        protocol_deviations=["The reused timer saved user+sys total only; separate user/sys values were not retained."],
        same_complete_run_cpu_and_accuracy=True, decision=identity(ROOT/"decision.json"),
        files=[identity(p) for p in (Path(__file__), ROOT/"100m-report.json", ROOT/"score/accuracy.json")]))
    print("EXP720_INDEPENDENT_AUDIT", gates, estimates["delta"], flush=True)


if __name__ == "__main__":
    main()
