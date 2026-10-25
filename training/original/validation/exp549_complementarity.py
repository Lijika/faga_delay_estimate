#!/usr/bin/env python3
"""Compare frozen full-port predictions and label-only selection ceilings on r9."""
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np

import exp535_real_map as real
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp549"), Path("build/exp549")
PLAN = Path("experiment/实验549-全端口方法互补与组合成本边界.md")
SEED, DRAWS = 20261020549, 2000
MODEL_NAMES = ("M0", "M1", "M2", "M3")
read = real.read


def predictions(number, columns):
    base = Path(f"../exp{number}")
    report = read(base / f"validation/results/exp{number}/report.json")
    asset = real.check(base / report["predictions"]["path"], report["predictions"])
    assert asset["bytes"] == real.ROWS * columns * 4
    return np.fromfile(asset["path"], "<i4").reshape(real.ROWS, columns).astype(np.int64), report, asset


def fallback(base, fallback_score):
    gain = np.maximum(0., fallback_score - base)
    ordered = np.sort(gain)[::-1]
    cumulative = np.cumsum(ordered)
    result = []
    for target in (99., 99.1, 99.25):
        needed = max(0., (target - float(base.mean())) * len(base))
        feasible = bool(needed <= cumulative[-1])
        count = int(np.searchsorted(cumulative, needed, side="left") + 1) if needed else 0
        record = dict(target_pp=target, feasible=feasible, base_pp=float(base.mean()),
                      selection_ceiling_pp=float(base.mean() + gain.mean()))
        if feasible:
            assert count <= len(base)
            if count:
                threshold = ordered[count - 1]
                assert threshold > 0 and cumulative[count - 1] >= needed
                assert count == 1 or cumulative[count - 2] < needed
                above = gain > threshold
                tied_needed = needed - float(gain[above].sum())
                reconstructed = int(above.sum()) + int(np.ceil(tied_needed / threshold - 1e-7))
                assert reconstructed == count, (count, reconstructed, threshold)
            fraction = count / len(base)
            record.update(minimum_rows=count, minimum_fraction=fraction,
                          optimistic_selected_extra_ns={str(b): b / fraction if fraction else None
                                                        for b in (100, 300)})
        result.append(record)
    return result


def partition(query, event):
    sx, sy, tx, ty = query[:, :4].T
    ax, ay = event[:, :2].T
    x, y = tx - sx, ty - sy
    boundary = np.minimum.reduce((sx, 119 - sx, tx, 119 - tx, sy, 549 - sy, ty, 549 - ty))
    side = lambda a: np.where(a < 76, 0, np.where(a < 90, 1, 2))
    forced = np.zeros(real.ROWS, dtype=bool)
    for b in read("doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]["Block"]:
        forced |= (((ax < b["left"]) & (tx > b["right"])) | ((tx < b["left"]) & (ax > b["right"]))) & \
                  (ay >= b["lower"]) & (ay <= b["upper"]) & (ty >= b["lower"]) & (ty <= b["upper"])
    return dict(source_family=query[:, 4], target_family=query[:, 6],
                role=2 * (query[:, 4] >= 20) + (query[:, 6] >= 20),
                direction=2 * (x < 0) + (y < 0),
                near_axis=((np.abs(x) < 20) | (np.abs(y) < 24)).astype(int),
                distance=np.searchsorted([24, 100, 300], np.abs(x) + np.abs(y), side="right"),
                boundary=np.searchsorted([6, 12, 24], boundary, side="right"),
                block_sides=3 * side(sx) + side(tx),
                first_skip=((ax - sx != event[:, 2]) | (ay - sy != event[:, 3])).astype(int),
                forced_detour=forced.astype(int))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp549")
    assert os.environ.get("OPENBLAS_NUM_THREADS") == "1"
    resource.setrlimit(resource.RLIMIT_CPU, (1800, 1800))
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    started, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    mapping_path = Path("../exp500/validation/results/exp500-preparation/mapping.json")
    label_path = Path("../exp501/validation/results/exp501/report.json")
    output_path = Path("../exp502/validation/results/exp502/report.json")
    labels, outputs = read(label_path), read(output_path)
    assert labels["all_complete_label_checks"] and outputs["all_full_contract_checks"]
    real.BUILD = BUILD
    query, indices, truth, production, cluster, inputs = real.inputs(read(mapping_path), labels, outputs)
    assert inputs["queries"]["sha256"] == "aa0cd63f7e83be6d5a12169f0318ae0d4cfc510aa705de1f898611524a9165c1"
    write(ROOT / "input.json", inputs)
    p536, r536, a536 = predictions(536, 6)
    p537, r537, a537 = predictions(537, 2)
    p543, r543, a543 = predictions(543, 9)
    event_path = Path("../exp536/build/exp536/events.i32")
    expected = next(r for r in read("../exp543/validation/results/exp543/freeze.json")["files"]
                    if r["path"] == str(event_path))
    event_asset = real.check(event_path, expected)
    event = np.fromfile(event_path, "<i4").reshape(real.ROWS, 9)
    assert np.all(event[:, 8] == 1)
    fixed = ("mean13", "min13", "max13", "median123")
    selected = ["S_M1", "S_mean13"] + list(fixed) + ["L_" + name for name in fixed]
    files = [Path(__file__), Path("validation/exp535_real_map.py"), Path("validation/exp208_nominal_parent_tree.py"),
             ROOT / "protocol-original.md", mapping_path, label_path, output_path,
             *[Path(f"../exp{n}/validation/results/exp{n}/report.json") for n in (536, 537, 543, 534)]]
    frozen = [identity(p) for p in files] + [a536, a537, a543, event_asset] + inputs["inputs"]
    write(ROOT / "freeze.json", dict(files=frozen, prediction_columns=selected, input_domain="viewed full-port unique 1M"))
    same = np.all(query[:, :2] == query[:, 2:4], axis=1) & (query[:, 8] == query[:, 9])
    physical = p537 + event[:, 4:5] + event[:, 6:7]
    physical[same] = 0
    arms = dict(M0=p536[:, 3], M1=p536[:, 4], M2=physical[:, 0], M3=physical[:, 1],
                exp354=production, S=p543[:, 3], L=p543[:, 2])
    assert np.array_equal(p536[:, 5], production) and np.array_equal(p543[:, 6], production)
    for name, saved in (("M0", r536["statistics"]["model_original"]),
                        ("M1", r536["statistics"]["model_aligned"]),
                        ("M2", r537["statistics"]["original"]["real"]),
                        ("M3", r537["statistics"]["aligned"]["real"]),
                        ("exp354", r536["statistics"]["exp354"]),
                        ("L", r543["statistics"]["wave_lower"]),
                        ("S", r543["statistics"]["all_projected_alone"])):
        assert real.statistics(arms[name], truth) == saved, name
    assert np.all(arms["L"] <= truth) and np.all(arms["S"] <= truth)
    m1, m2, m3 = (arms[n] for n in ("M1", "M2", "M3"))
    arms.update(mean13=(m1 + m3 + 1) // 2, min13=np.minimum(m1, m3),
                max13=np.maximum(m1, m3), median123=np.sort(np.stack((m1, m2, m3)), axis=0)[1])
    for name in ("M1", "mean13"):
        arms["S_" + name] = np.maximum(arms["S"], arms[name])
        assert np.all(np.abs(arms["S_" + name] - truth) <= np.abs(arms[name] - truth))
    # Check the complete population with equivalent arithmetic and order predicates.
    assert np.array_equal(arms["mean13"], m1 + (m3 - m1 + 1) // 2)
    assert np.all((arms["mean13"] >= arms["min13"]) & (arms["mean13"] <= arms["max13"]))
    triple = np.stack((m1, m2, m3))
    assert np.all((triple <= arms["median123"]).sum(axis=0) >= 2)
    assert np.all((triple >= arms["median123"]).sum(axis=0) >= 2)
    for name in fixed:
        arms["L_" + name] = np.maximum(arms["L"], arms[name])
        assert np.all(np.abs(arms["L_" + name] - truth) <= np.abs(arms[name] - truth))
    arms["L_exp354"] = np.maximum(arms["L"], production)
    assert np.array_equal(arms["L_exp354"], p543[:, 8])
    matrix = np.stack([arms[n] for n in MODEL_NAMES])
    oracle = lambda a: a[np.argmin(np.abs(a - truth), axis=0), np.arange(real.ROWS)]
    arms["oracle_models"] = oracle(matrix)
    arms["oracle_interval"] = np.clip(truth, matrix.min(axis=0), matrix.max(axis=0))
    arms["oracle_models_exp354"] = oracle(np.vstack((matrix, production)))
    arms["oracle_models_L"] = oracle(np.vstack((matrix, arms["L"])))
    arms["oracle_models_L_exp354"] = oracle(np.vstack((matrix, arms["L"], production)))
    scores = {n: real.points(v, truth) for n, v in arms.items()}
    for name in MODEL_NAMES + fixed:
        assert np.all(scores["oracle_interval"] >= scores[name])
    for name in MODEL_NAMES:
        assert np.all(scores["oracle_models"] >= scores[name])
    statistics = {n: real.statistics(v, truth) for n, v in arms.items()}
    pairs = (("S_M1", "M1"), ("mean13", "M1"), ("L_mean13", "mean13"))
    delta = np.column_stack([scores[a] - scores[b] for a, b in pairs])
    counts = np.bincount(cluster)
    sums = np.column_stack([np.bincount(cluster, weights=delta[:, i]) for i in range(len(pairs))])
    rng, bootstrap = np.random.default_rng(SEED), np.empty((DRAWS, len(pairs)))
    for draw in range(DRAWS):
        sample = rng.integers(len(counts), size=len(counts))
        bootstrap[draw] = sums[sample].sum(axis=0) / counts[sample].sum()
    ci = np.quantile(bootstrap, [.025, .975], axis=0)
    paired = {}
    for i, (a, b) in enumerate(pairs):
        paired[f"{a}-{b}"] = dict(delta_pp=float(delta[:, i].mean()), ci95_pp=ci[:, i].tolist(),
            better_rows=int(np.sum(scores[a] > scores[b])), worse_rows=int(np.sum(scores[a] < scores[b])),
            tied_score_rows=int(np.sum(scores[a] == scores[b])), changed_rows=int(np.sum(arms[a] != arms[b])),
            unit="complete source pin", clusters=len(counts), draws=DRAWS, seed=SEED)
    pairwise = {}
    for i, a in enumerate(MODEL_NAMES):
        for b in MODEL_NAMES[i + 1:]:
            ea, eb = arms[a] - truth, arms[b] - truth
            da, db = ea.astype(float) - ea.mean(), eb.astype(float) - eb.mean()
            pairwise[f"{a}-{b}"] = dict(error_cross_ps=int(np.dot(ea, eb)),
                centered_correlation=float(np.dot(da, db) / np.sqrt(np.dot(da, da) * np.dot(db, db))),
                opposite_sign_rows=int(np.sum(((ea < 0) & (eb > 0)) | ((ea > 0) & (eb < 0)))),
                both_under_rows=int(np.sum((ea < 0) & (eb < 0))), both_over_rows=int(np.sum((ea > 0) & (eb > 0))),
                a_better_rows=int(np.sum(scores[a] > scores[b])), b_better_rows=int(np.sum(scores[b] > scores[a])),
                selection_ceiling_pp=float(np.maximum(scores[a], scores[b]).mean()))
    groups = {}
    for name, values in partition(query, event).items():
        for value in np.unique(values):
            mask = values == value
            groups[f"{name}/{value}"] = {n: real.statistics(v[mask], truth[mask]) for n, v in arms.items()}
        assert sum(g["M1"]["rows"] for k, g in groups.items() if k.startswith(name + "/")) == real.ROWS
    write(ROOT / "groups.json", groups)
    path = BUILD / "predictions.i32"
    np.column_stack([arms[n] for n in selected]).astype("<i4").tofile(path)
    for row in frozen:
        assert identity(row["path"]) == row
    main_pair = paired["S_M1-M1"]
    result = dict(statistics=statistics, paired=paired, pairwise=pairwise,
        fallback={n: fallback(scores[n], scores["exp354"]) for n in ("M1", "S_M1", "mean13")},
        hypotheses=dict(primary_quality=bool(statistics["S_M1"]["accuracy_pp"] >= 99.1 and
            main_pair["delta_pp"] >= .15 and main_pair["ci95_pp"][0] > 0),
            interval_information_sufficient=bool(statistics["oracle_interval"]["accuracy_pp"] >= 99.1)),
        cost_scope=dict(M1_static_restore_elf_bytes=read("../exp534/validation/results/exp534/report.json")["static_elf_bytes"],
            M1_restored_table_bytes=735510528, M1_inner_product_terms=128,
            M3_factor_bytes=sum(r["bytes"] for r in r537["training"][1]["factors"]), M3_inner_product_terms=96,
            mean13_inner_product_terms=224, L_additional_component_bytes=r543["component_bytes"],
            S_M1_component_static_bytes=read("../exp534/validation/results/exp534/report.json")["static_elf_bytes"] + r543["component_bytes"],
            S_M1_query_table_bytes=735510528 + r543["restored_total_bytes"],
            S_requires_full_nominal_field=False,
            L_requires_full_nominal_field=True, fixed_model_combination_capacity_validated=False,
            fallback_selected_cpu_validated=False, full_run_cpu_extrapolated=False),
        all_passed=True, source_ports=208, target_ports=288, port_pairs=59904, rows=real.ROWS,
        complete_port_validation=True, prior_statistics_replayed=True, new_labels=0, new_estimator_runs=0,
        production_cpu_validated=False, independent_holdout_validated=False, final_elf_validated=False,
        predictions=identity(path), prediction_columns=selected,
        new_asset_bytes=sum(p.stat().st_size for p in BUILD.iterdir()),
        zero_truth_rows=int(np.sum(truth == 0)), same_pin_rows=int(np.sum(same)),
        host=socket.gethostname(), cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        disk_free_bytes=shutil.disk_usage(".").free)
    assert result["new_asset_bytes"] <= 200000000
    write(ROOT / "report.json", result)
    print("EXP549_COMPLETE", result["hypotheses"], flush=True)


if __name__ == "__main__":
    main()
