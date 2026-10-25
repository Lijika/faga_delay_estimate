#!/usr/bin/env python3
"""Compile four port quotients and evaluate certified projection on cached rows."""
import ast
import heapq
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp712/validation").resolve()))
sys.path.insert(0, str(Path("../exp592/validation").resolve()))
import exp712_tie_support as common
import exp592_xgb_audit as score

read, write, identity, checked = common.read, common.write, common.identity, common.check
ROOT, BUILD = Path("validation/results/exp732"), Path("build/exp732")
PLAN = Path("experiment/实验732-固定斜率端口闭包与当前模型安全投影.md")
ARCH = Path("../exp652/doc/eda比赛文件/arch")
INF, SCALE, SEED = 1 << 50, 12, 20261025732
SLOPES = np.array([(150, 127), (150, -125), (-150, 127), (-150, -125)], "i8")


def cached_data():
    # Reuse pure grouping functions without loading their training dependencies.
    scope = dict(np=np)
    for path, name in (("../exp726/validation/exp726_final_target.py", "groups"),
                       ("../exp677/validation/exp677_map_events.py", "events")):
        nodes = [n for n in ast.parse(Path(path).read_text()).body
                 if isinstance(n, ast.FunctionDef) and n.name == name]
        assert len(nodes) == 1
        exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), scope)
    with np.load("../exp585/build/exp585/training.npz") as packed:
        data = {k: packed[k] for k in ("features", "d0", "mandatory", "folds", "routes")}
    data["features"] = np.ascontiguousarray(data["features"][:, :53])
    with np.load("../exp593/build/exp593/targets.npz") as packed:
        data["truth"] = packed["truth"]
    with np.load("../exp623/build/exp623/data.npz") as packed:
        for key in ("truth", "mandatory", "folds", "routes"):
            assert np.array_equal(data[key], packed[key])
    h, v, _, _ = scope["events"](data["features"][:, 28:32],
                                 read(ARCH/"SRB_Gap.json")["Gap"]["Block"])
    assert not np.any(h & v) and int(v.sum()) == 2613
    baseline = np.fromfile("../exp719/build/exp719/T2D6-prediction.i32", "<i4").astype("i8")
    expected = read("../exp719/validation/results/exp719/report.json")["metrics"]["T2D6"]
    for key, value in score.stats(baseline, data["truth"]).items():
        assert abs(value-expected[key]) < 1e-10
    return data, scope["groups"](data, h.astype("u1")+2*v), baseline


def floyd(edges):
    result = edges.copy()
    np.fill_diagonal(result, 0)
    for k in range(len(result)):
        np.minimum(result, result[:, k, None]+result[None, k, :], out=result)
    return result


def dijkstra(edges, source):
    adjacent = [list(zip(np.flatnonzero(row < INF).tolist(), row[row < INF].tolist()))
                for row in edges]
    distance = [INF]*len(edges)
    distance[source] = 0
    queue = [(0, source)]
    while queue:
        cost, u = heapq.heappop(queue)
        if cost != distance[u]:
            continue
        for v, fee in adjacent[u]:
            if cost+fee < distance[v]:
                distance[v] = cost+fee
                heapq.heappush(queue, (cost+fee, v))
    return np.asarray(distance, "i8")


def self_check():
    edges = np.array([[INF, 2, 9, INF], [INF, INF, 3, INF],
                      [0, INF, INF, 1], [INF, INF, INF, INF]], "i8")
    closed = floyd(edges)
    assert np.array_equal(closed[0], [0, 2, 5, 6])
    for i in range(4):
        assert np.array_equal(closed[i], dijkstra(edges, i))
    for n in range(-25, 26):
        ceil = -((-n)//SCALE)
        assert (ceil-1)*SCALE < n <= ceil*SCALE
    for truth in range(1, 8):
        for lower in range(truth+1):
            for prediction in range(-2, 12):
                assert abs(max(lower, prediction)-truth) <= abs(prediction-truth)


def compile_bounds(mapping):
    names = [p["Name"] for p in read(ARCH/"SRB_Port.json")["Port"]]
    ids = {name: i for i, name in enumerate(names)}
    nets = read(ARCH/"SRB_Net.json")["Nets"]
    arcs = read(ARCH/"SRB_Arc.json")["Arcs"]
    old = read("../exp541/validation/results/exp541/potentials.json")
    assert old == read("../exp539/validation/results/exp539/potentials.json")
    old_phi = np.asarray(old["phi"], "i8")
    assert old["scale"] == 120 and np.all(old_phi % 10 == 0)
    phi = np.full((4, 496), -INF, "i8")
    phi[:, [ids[name] for name in old["ports"]]] = old_phi//10
    after, vx, vy = np.arange(496), np.zeros(496, "i8"), np.zeros(496, "i8")
    for net in nets:
        p, t = ids[net["from"]], ids[net["to"]]
        assert np.all(phi[:, t] == -INF) and np.all(phi[:, p] != -INF)
        vx[p], vy[p], after[p] = net["delta x"], net["delta y"], t
        phi[:, t] = phi[:, p]-SLOPES @ np.array([vx[p], vy[p]])
    assert np.all(phi != -INF)
    edges = np.full((4, 496, 496), INF, "i8")
    for arc in arcs:
        p, t = ids[arc["from"]], ids[arc["to"]]
        cost = SCALE*arc["delay"]+phi[:, p]-phi[:, t]
        assert np.all(cost >= 0)
        edges[:, p, t] = np.minimum(edges[:, p, t], cost)
    cells = read(ARCH/"SRB_Inst.json")["Inst"]
    x = np.array([p["x"] for p in cells], "i8")
    y = np.array([p["y"] for p in cells], "i8")
    exists = np.zeros((550, 120), bool)
    exists[y, x] = True
    assert len(cells) == int(exists.sum()) == 60200
    valid_count, skip_count = 0, 0
    for net in nets:
        p, t = ids[net["from"]], ids[net["to"]]
        compressed = x-14*((y % 100 < 50) & (x >= 90))+vx[p]
        nx = compressed+14*((y % 100 < 50) & (compressed >= 76)) if vx[p] else x
        ny = y+vy[p]
        valid = (nx >= 0) & (nx < 120) & (ny >= 0) & (ny < 550)
        valid[valid] &= exists[ny[valid], nx[valid]]
        fee = 292*(nx[valid]-x[valid] != vx[p])
        cost = SCALE*fee-SLOPES[:, 0, None]*(nx[valid]-x[valid]) - \
            SLOPES[:, 1, None]*(ny[valid]-y[valid])+phi[:, p, None]-phi[:, t, None]
        assert np.all(cost >= 0) and np.all(cost.min(1) == 0)
        edges[:, p, t] = np.minimum(edges[:, p, t], cost.min(1))
        valid_count += int(valid.sum())
        skip_count += int(np.count_nonzero(fee))
    assert valid_count == 9_417_280 and skip_count == 86_400
    sources = np.array([ids[p] for p in mapping["sources"]], "i4")
    targets = np.array([ids[p] for p in mapping["targets"]], "i4")
    consumed = after[sources]
    assert len(sources) == len(set(consumed)) == 208 and len(targets) == 288
    residual = np.empty((4, 208, 288), "i8")
    for k in range(4):
        closed = floyd(edges[k])
        for source in consumed:
            assert np.array_equal(closed[source], dijkstra(edges[k], int(source)))
        residual[k] = closed[consumed[:, None], targets[None, :]]
        assert np.all(residual[k] < INF)
    direct = phi[:, targets[:, None]].transpose(0, 2, 1)-phi[:, consumed, None]
    bias = residual+direct
    dtype = "<i2" if np.max(abs(bias)) <= 32767 else "<i4"
    packed = bias.astype(dtype)
    assert np.array_equal(packed, bias)
    packed.tofile(BUILD/"bias.bin")
    edges.tofile(BUILD/"edges.i64")
    source_index, target_index = np.full(496, -1, "i4"), np.full(496, -1, "i4")
    source_index[sources], target_index[targets] = np.arange(208), np.arange(288)
    write(ROOT/"construction.json", dict(all_checks_passed=True, scale=SCALE,
        slopes=SLOPES.tolist(), original_arcs=len(arcs), valid_nets=valid_count,
        skipped_nets=skip_count, all_four_edge_inequalities=True,
        independent_shortest_path_rows=4*208, complete_row_dijkstra_equal=True,
        table_shape=list(bias.shape), dtype=dtype, bias_range=[int(bias.min()), int(bias.max())],
        table_bytes=packed.nbytes, payload_bytes=packed.nbytes+SLOPES.nbytes+
            source_index.nbytes+target_index.nbytes, port_potential_units_exact=True,
        asset=identity(BUILD/"bias.bin")))
    return bias, direct, source_index, target_index, vx, vy


def evaluate(data, groups, baseline, compiled):
    bias, direct, si, ti, vx, vy = compiled
    q = np.fromfile("../exp535/build/exp535/queries.bin", "<i4", offset=12).reshape(-1, 10)
    x = data["features"].astype("i8")
    assert np.array_equal(q[:, :4], x[:, [26, 27, 30, 31]])
    sf, tf = si[q[:, 8]], ti[q[:, 9]]
    assert np.all(sf >= 0) and np.all(tf >= 0)
    ax, ay, tx, ty = x[:, 28], x[:, 29], q[:, 2], q[:, 3]
    compressed = q[:, 0]-14*((q[:, 1] % 100 < 50) & (q[:, 0] >= 90))+vx[q[:, 8]]
    landed = np.where(vx[q[:, 8]] != 0,
        compressed+14*((q[:, 1] % 100 < 50) & (compressed >= 76)), q[:, 0])
    assert np.array_equal(ax, landed) and np.array_equal(ay, q[:, 1]+vy[q[:, 8]])
    first_block = 292*(ax-q[:, 0] != vx[q[:, 8]])
    px, py = np.zeros(121, "i8"), np.zeros(551, "i8")
    for line in read(ARCH/"SRB_Gap.json")["Gap"]["Line"]:
        (px if line["direction"] == "vertical" else py)[line["site"]+1] += line["delay"]
    px, py = px.cumsum(), py.cumsum()
    mandatory = abs(px[ax]-px[q[:, 0]])+abs(py[ay]-py[q[:, 1]]) + \
        abs(px[tx]-px[ax])+abs(py[ty]-py[ay])
    assert np.array_equal(mandatory, data["mandatory"])
    linear = SLOPES[:, 0, None]*(tx-ax)+SLOPES[:, 1, None]*(ty-ay)
    same = np.all(q[:, :2] == q[:, 2:4], axis=1) & (q[:, 8] == q[:, 9])
    truth = data["truth"].astype("i8")
    predictions, lower = {"A": baseline}, {}
    for arm, table in (("S", direct), ("C", bias)):
        numerator = (linear+table[:, sf, tf]).max(0)
        bound = first_block+mandatory+np.maximum(0, -((-numerator)//SCALE))
        bound[same] = 0
        assert np.all(bound <= truth), arm
        lower[arm] = bound
        predictions[arm] = np.maximum(baseline, bound)
        assert np.all(abs(predictions[arm]-truth) <= abs(baseline-truth))
        bound.astype("<i4").tofile(BUILD/(arm+"-lower.i32"))
        predictions[arm].astype("<i4").tofile(BUILD/(arm+"-prediction.i32"))
    assert np.all(lower["S"] <= lower["C"])
    counts = np.bincount(groups["source_family"], minlength=26)
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    scores = {a: score.points(p, truth) for a, p in predictions.items()}
    comparisons = {}
    for arm in ("S", "C"):
        result = score.transition(predictions[arm], baseline, truth, groups)
        delta = scores[arm]-scores["A"]
        sums = np.bincount(groups["source_family"], weights=delta, minlength=26)
        ci = np.quantile(sums[draws].sum(1)/counts[draws].sum(1), [.025, .975])
        result.update(source_family_ci95_pp=ci.tolist(),
            changed_rows=int(np.count_nonzero(predictions[arm] != baseline)),
            lower_alone=score.stats(lower[arm], truth),
            lower_exact_rows=int(np.count_nonzero(lower[arm] == truth)))
        for name, vector in groups.items():
            for value in np.unique(vector):
                mask = vector == value
                row = result["groups"][name][str(int(value))]
                row["population_fraction"] = float(mask.mean())
                row["baseline_global_loss_pp"] = float((100-scores["A"][mask]).sum()/len(truth))
                row["global_delta_pp"] = float(delta[mask].sum()/len(truth))
        comparisons[arm] = result
    c = comparisons["C"]
    capacity = read(ROOT/"construction.json")["payload_bytes"]
    selected = bool(capacity <= 1_000_000 and c["delta_accuracy_pp"] >= .05 and
                    c["source_family_ci95_pp"][0] > 0)
    write(ROOT/"report.json", dict(all_checks_passed=True, selected=selected, comparisons=comparisons,
        baseline=score.stats(baseline, truth), original_lower_dominated=True,
        lower_never_over_exact=True, projected_absolute_error_never_increases=True,
        same_pin_rows=int(same.sum()), complete_program_runs=0, new_exact_rows=0,
        historical_oof_cache=True, final_model_or_unknown_input_claim=False,
        files=[identity(p) for p in BUILD.iterdir() if p.is_file()]))
    print("EXP732_COMPLETE", selected, c["delta_accuracy_pp"], flush=True)


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp732")
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    started, cpu = time.monotonic(), time.process_time()
    inputs = []
    for record in read("../exp726/validation/results/exp726/freeze.json")["inputs"]:
        inputs.append(checked(Path("../exp726")/record["path"], record))
    record = read("../exp719/validation/results/exp719/report.json")["predictions"]["T2D6"]
    inputs.append(checked(Path("../exp719")/record["path"], record))
    previous = read("../exp541/validation/results/exp541/freeze.json")
    for item in previous["files"]:
        if Path(item["path"]).name.startswith("SRB_"):
            inputs.append(checked(ARCH/Path(item["path"]).name, item))
        elif Path(item["path"]).name in ("mapping.json", "potentials.json"):
            inputs.append(checked(item["path"], item))
    paths = [Path(__file__), PLAN, Path("../exp726/validation/exp726_final_target.py"),
        Path("../exp677/validation/exp677_map_events.py"), Path(score.__file__),
        Path("../exp541/validation/results/exp541/potentials.json"),
        Path("../exp541/validation/results/exp541/real-qualification.json")]
    write(ROOT/"freeze.json", dict(inputs=inputs, files=[identity(p) for p in paths],
        seed=SEED, disk_free_start_bytes=shutil.disk_usage(".").free))
    self_check()
    mapping = read("../exp500/validation/results/exp500-preparation/mapping.json")
    compiled = compile_bounds(mapping)
    compiled_cpu = time.process_time()-cpu
    data, groups, baseline = cached_data()
    evaluate(data, groups, baseline, compiled)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    threads = next(int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines()
                   if line.startswith("Threads:"))
    assert rss <= 1_500_000_000 and threads == 1
    write(ROOT/"completion.json", dict(cpu_s=time.process_time()-cpu,
        construction_cpu_s=compiled_cpu, wall_s=time.monotonic()-started, rss_bytes=rss,
        threads=threads, disk_free_end_bytes=shutil.disk_usage(".").free,
        build_bytes=sum(p.stat().st_size for p in BUILD.iterdir()), deleted_bytes=0))


if __name__ == "__main__":
    main()
