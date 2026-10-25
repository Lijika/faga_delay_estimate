#!/usr/bin/env python3
"""Audit regularized words using vector replay and separate design statistics."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp712/validation").resolve()))
import exp712_tie_support as prior

ROOT, BUILD = Path("validation/results/exp731"), Path("build/exp731")
read, check = prior.read, prior.check


def main():
    frozen, report = read(ROOT/"freeze.json"), read(ROOT/"report.json")
    for item in frozen["inputs"]+frozen["files"]+report["files"]:
        check(item["path"], item)
    q = np.fromfile(BUILD/"queries.bin", "<i4", offset=12).reshape(1040, 4, 10)
    gold = np.fromfile(BUILD/"gold.i32", "<i4").reshape(1040, 4)
    strata = np.fromfile(BUILD/"strata.u16", "<u2")
    population = np.asarray(frozen["population_strata"], "f8")
    _, exists, arcs, z, dx, dy, dest = prior.previous.graph()
    px, py = np.zeros(121, "i8"), np.zeros(551, "i8")
    for line in read("../exp652/doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]["Line"]:
        (px if line["direction"] == "vertical" else py)[line["site"]+1] += line["delay"]
    px, py = px.cumsum(), py.cumsum()

    def words_at(arm):
        lengths = np.fromfile(BUILD/(arm+".lengths.u32"), "<u4")
        data = np.fromfile(BUILD/(arm+".words.u8"), "u1")
        offsets = np.r_[0, np.cumsum(lengths, dtype="i8")]
        assert offsets[-1] == len(data) and len(lengths) == 4160
        return [data[a:b] for a, b in zip(offsets[:-1], offsets[1:])], lengths

    def count_changes(words):
        return np.array([sum((dx[z[a]], dy[z[a]]) != (dx[z[b]], dy[z[b]])
                            for a, b in zip(w[:-1], w[1:])) for w in words], "i8")

    def replay(word, rows):
        x, y, p = rows[:, 0].copy(), rows[:, 1].copy(), rows[:, 8].copy()
        active = np.ones(4, bool)
        arc = np.zeros(4, "i8")
        block, line, skips, jump = [arc.copy() for _ in range(4)]
        for symbol in word:
            zp = int(z[symbol])
            assert np.all(arcs[p[active], zp] >= 0)
            arc[active] += arcs[p[active], zp]
            nx, ny, fee = prior.previous.landing(x, y, dx[zp], dy[zp])
            valid = active & prior.previous.present(nx, ny, exists)
            line[valid] += abs(px[nx[valid]]-px[x[valid]]) + abs(py[ny[valid]]-py[y[valid]])
            block[valid] += fee[valid]
            skips[valid] += fee[valid] != 0
            jump[valid] += nx[valid]-x[valid]-dx[zp]
            x[valid], y[valid], p[valid] = nx[valid], ny[valid], dest[zp]
            active = valid
        active &= (x == rows[:, 2]) & (y == rows[:, 3])
        assert np.all(arcs[p[active], rows[active, 9]] >= 0)
        arc[active] += arcs[p[active], rows[active, 9]]
        values = np.where(active, arc+block, -1)
        full = np.where(active, arc+block+line, -1)
        summaries = np.column_stack((arc, np.zeros(4, "i8"), block,
            np.full(4, dx[z[word]].sum()), np.full(4, dy[z[word]].sum()),
            np.full(4, len(word)), skips, jump))
        return values, full, summaries

    def stats(data, critical=1.96):
        grouped = np.asarray(data, "f8").reshape(1040, 4).mean(1)
        observations = np.stack([grouped[strata == h] for h in range(104)])
        assert observations.shape == (104, 10)
        weights = population/population.sum()
        mean = float(weights @ observations.mean(1))
        se = float(np.sqrt(np.sum(weights**2 * (1-10/population) *
                                  observations.var(1, ddof=1)/10)))
        return dict(mean=mean, design_se=se, interval=[mean-critical*se, mean+critical*se])

    def equal(actual, expected):
        for key in actual:
            assert np.allclose(actual[key], expected[key], rtol=1e-11, atol=1e-12), key

    original, _ = words_at("O")
    original_k = count_changes(original)
    assert np.array_equal(original_k, np.fromfile(BUILD/"gold.i32.changes.u32", "<u4"))
    masks, rle_means, full_minima = {}, {}, {}
    for arm, penalty in frozen["penalties"].items():
        for stage in ("compile", "trace"):
            record = read(ROOT/(stage+"-"+arm+".run.json"))
            assert record["exit_code"] == 0
            assert not (ROOT/(stage+"-"+arm+".stderr")).read_bytes()
            if stage == "trace":
                assert record["cpu_s"] <= 1800 and record["rss_bytes"] <= 1_500_000_000
                assert record["threads"] == 1
        words, lengths = words_at(arm)
        sums = np.fromfile(BUILD/(arm+".summary.i32"), "<i4").reshape(4160, 8)
        k = count_changes(words)
        costs = sums[:, 0].astype("i8")+sums[:, 2]
        assert np.all(costs >= gold.ravel())
        assert np.all(costs+penalty*k <= gold.ravel()+penalty*original_k)
        if penalty:
            assert np.all(k <= original_k)
        eligible = costs-gold.ravel() <= 8
        accepted = [w if eligible[i] else original[i] for i, w in enumerate(words)]
        cross, full = np.full((1040, 4, 4), -1, "<i4"), np.full((1040, 4, 4), -1, "<i4")
        for i, word in enumerate(words):
            values, complete, replayed = replay(word, q[i//4])
            assert np.array_equal(replayed[i % 4], sums[i])
            assert values[i % 4] == costs[i]
            if not eligible[i]:
                values, complete, _ = replay(original[i], q[i//4])
            values[i % 4] = complete[i % 4] = -1
            cross[i//4, i % 4], full[i//4, i % 4] = values, complete
        assert np.array_equal(cross, np.fromfile(BUILD/(arm+"-cross.i32"), "<i4").reshape(1040, 4, 4))
        assert np.array_equal(full, np.fromfile(BUILD/(arm+"-full-cross.i32"), "<i4").reshape(1040, 4, 4))
        assert np.all(full[cross >= 0] >= cross[cross >= 0])
        expected = report["reports"][arm]
        masks[arm] = np.any((cross >= 0) & (cross <= gold[:, None, :]+8), axis=1)
        rle = count_changes(accepted)+np.array([len(w) > 0 for w in accepted])
        for key, value in dict(coverage=np.any(cross >= 0, axis=1),
                exact_recovery=np.any(cross == gold[:, None, :], axis=1), within8=masks[arm],
                mean_rle=rle, mean_hops=lengths, accepted_fraction=eligible,
                mean_original_excess=costs-gold.ravel()).items():
            equal(stats(value), expected[key])
        assert expected["maximum_original_excess_ps"] == int((costs-gold.ravel()).max())
        assert expected["changed_words"] == sum(not np.array_equal(a, b)
                                                for a, b in zip(accepted, original))
        rle_means[arm] = stats(rle)["mean"]
        full_minima[arm] = np.min(np.where(full >= 0, full, 2**31-1), axis=1)

    for suffix in (".words.u8", ".lengths.u32", ".summary.i32", "-cross.i32"):
        assert (BUILD/("O"+suffix)).read_bytes() == (Path("../exp712/build/exp712")/("O"+suffix)).read_bytes()
    selected = []
    for arm in ("E1", "E4"):
        expected = report["reports"][arm]
        gain = stats(masks[arm].astype(int)-masks["O"].astype(int), 2.241402728)
        ratio = rle_means[arm]/rle_means["O"]
        equal(gain, expected["within8_gain"])
        assert abs(ratio-expected["mean_rle_ratio"]) < 1e-12
        passed = (gain["mean"] >= .03 and gain["interval"][0] > 0) or (
            ratio <= .8 and gain["mean"] >= -.005)
        assert passed == expected["expand"]
        if passed:
            selected.append(arm)
        common = (full_minima[arm] != 2**31-1) & (full_minima["O"] != 2**31-1)
        delta = full_minima[arm].astype("i8")-full_minima["O"]
        fraction = stats(common)["mean"]
        equal(dict(common_fraction=fraction,
                   mean_delta_ps_on_common=stats(np.where(common, delta, 0))["mean"]/fraction,
                   lower_fraction=stats(common & (delta < 0))["mean"],
                   higher_fraction=stats(common & (delta > 0))["mean"]),
              expected["complete_line_upper_bound_comparison"])
    assert selected == report["eligible"] and report["selected"] == (selected[0] if selected else None)
    result = dict(all_checks_passed=True, rows_per_arm=4160, pair_groups=1040,
        independent_vector_replay_equal=True, original_control_bytes_equal=True,
        independent_design_statistics_equal=True, original_and_regularized_cost_bounds=True,
        full_line_costs_verified=True, own_location_excluded=True, selected=report["selected"],
        report_sha256=prior.identity(ROOT/"report.json")["sha256"],
        audit_source=prior.identity(__file__))
    prior.write(ROOT/"independent-audit.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
