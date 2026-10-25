#!/usr/bin/env python3
"""Recompute projection scores from saved bounds and cached exact labels."""
from pathlib import Path
import numpy as np

import exp732_port_bounds as experiment

ROOT, BUILD = experiment.ROOT, experiment.BUILD
read, write, checked, identity = experiment.read, experiment.write, experiment.checked, experiment.identity


def points(prediction, truth):
    exponent = 8*np.abs(prediction-truth)/truth
    assert np.all(exponent < 700)
    return 200/(1+np.exp(exponent))


def main():
    frozen, report = read(ROOT/"freeze.json"), read(ROOT/"report.json")
    for item in frozen["files"]+frozen["inputs"]+report["files"]:
        checked(item["path"], item)
    data, groups, baseline = experiment.cached_data()
    truth = data["truth"].astype("i8")
    family = groups["source_family"]
    base_score = points(baseline, truth)
    assert abs(base_score.mean()-report["baseline"]["accuracy_pp"]) < 1e-10
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(experiment.SEED).integers(26, size=(9999, 26))
    bounds, comparisons = {}, {}
    for arm in ("S", "C"):
        lower = np.fromfile(BUILD/(arm+"-lower.i32"), "<i4").astype("i8")
        prediction = np.fromfile(BUILD/(arm+"-prediction.i32"), "<i4").astype("i8")
        assert np.array_equal(prediction, np.maximum(baseline, lower))
        assert np.all(lower <= truth) and np.all(abs(prediction-truth) <= abs(baseline-truth))
        current = points(prediction, truth)
        difference = current-base_score
        sums = np.bincount(family, weights=difference, minlength=26)
        interval = np.quantile(sums[draws].sum(1)/counts[draws].sum(1), [.025, .975])
        row = report["comparisons"][arm]
        assert abs(difference.mean()-row["delta_accuracy_pp"]) < 1e-10
        assert np.allclose(interval, row["source_family_ci95_pp"], rtol=1e-8, atol=1e-10)
        assert abs(points(lower, truth).mean()-row["lower_alone"]["accuracy_pp"]) < 1e-10
        assert int(np.count_nonzero(lower == truth)) == row["lower_exact_rows"]
        assert int(np.count_nonzero(prediction != baseline)) == row["changed_rows"]
        assert row["worse_rows"] == row["exact_lost_rows"] == 0
        for name, vector in groups.items():
            for value in np.unique(vector):
                mask = vector == value
                expected = row["groups"][name][str(int(value))]
                assert expected["rows"] == int(mask.sum())
                for key, number in dict(delta_accuracy_pp=difference[mask].mean(),
                        population_fraction=mask.mean(),
                        baseline_global_loss_pp=(100-base_score[mask]).sum()/len(truth),
                        global_delta_pp=difference[mask].sum()/len(truth)).items():
                    assert abs(expected[key]-number) < 1e-10, (name, value, key)
        bounds[arm] = lower
        comparisons[arm] = dict(delta_pp=float(difference.mean()), ci95_pp=interval.tolist())
    assert np.all(bounds["S"] <= bounds["C"])
    construction = read(ROOT/"construction.json")
    assert construction["complete_row_dijkstra_equal"] and construction["all_four_edge_inequalities"]
    c = comparisons["C"]
    selected = (construction["payload_bytes"] <= 1_000_000 and c["delta_pp"] >= .05 and c["ci95_pp"][0] > 0)
    assert selected == report["selected"]
    result = dict(all_checks_passed=True, independent_score_formula=True,
        grouped_losses_and_family_intervals_equal=True, selected=selected, comparisons=comparisons,
        rows=len(truth), report_sha256=identity(ROOT/"report.json")["sha256"],
        construction_sha256=identity(ROOT/"construction.json")["sha256"],
        source=identity(__file__))
    write(ROOT/"independent-audit.json", result)
    print("EXP732_AUDIT_PASSED", comparisons, flush=True)


if __name__ == "__main__":
    main()
