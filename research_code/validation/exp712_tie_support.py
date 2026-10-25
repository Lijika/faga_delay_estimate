#!/usr/bin/env python3
"""Compare deterministic exact-path representatives at matched locations."""
import heapq
import json
from pathlib import Path
import resource
import shutil
import socket
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
sys.path.insert(0, str(Path("../exp705/validation").resolve()))
sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp709_cost_skeleton as execution
import exp705_matched_positions as previous
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp712"), Path("build/exp712")
PLAN = Path("experiment/实验712-真实最优词的平局选择与跨位置支持.md")
OLD = Path("../exp705")
execution.ROOT = ROOT
read, replace = execution.read, execution.replace
ARMS = ("O", "R", "H")


def check(path, record):
    actual = identity(path)
    assert all(actual[k] == record[k] for k in ("bytes", "sha256")), path
    return actual


def toy_check():
    # Compare primary-key reopening against an independent lexicographic heap.
    graphs = [
        [[(1, 1, 1), (3, 2, 1)], [(2, 0, 1)], [(3, 1, 1)], []],
        [[(1, 0, 1), (3, 2, 1)], [(2, 0, 1)], [(3, 1, 1)], []],
        [[(2, 1, 1), (1, 1, 0)], [(3, 1, 1)], [(3, 1, 1)], []],
        [[(1, 0, 1)], [(0, 0, 1), (2, 2, 1)], []],
    ]
    for graph in graphs:
        inf = (10**9, 10**9)
        reference = [inf] * len(graph)
        reference[0] = (0, 0)
        heap = [(0, 0, 0)]
        while heap:
            cost, hops, u = heapq.heappop(heap)
            if (cost, hops) != reference[u]:
                continue
            for v, price, step in graph[u]:
                value = cost+price, hops+step
                if value < reference[v]:
                    reference[v] = value
                    heapq.heappush(heap, (*value, v))
        labels = [inf] * len(graph)
        labels[0] = (0, 0)
        heap = [(0, 0)]
        best = inf
        while heap:
            key, u = heapq.heappop(heap)
            if key > best[0]:
                break
            cost, hops = labels[u]
            if cost != key:
                continue
            if u == len(graph)-1:
                best = min(best, (cost, hops))
                continue
            for v, price, step in graph[u]:
                value = cost+price, hops+step
                if value < labels[v]:
                    labels[v] = value
                    heapq.heappush(heap, (value[0], v))
        assert best == reference[-1]


def patch_router(text):
    text = replace(text, "  buildTransitions();", """  buildTransitions();
#ifdef EXP712_REVERSE
  for (auto& entries : arcTemplates_) std::reverse(entries.begin(), entries.end());
  for (auto& entries : successorsOfZ_) std::reverse(entries.begin(), entries.end());
#endif""")
    text = replace(text, "  traceParent_.assign(dist_.size(), -1);",
        """  traceParent_.assign(dist_.size(), -1);
#ifdef EXP712_MIN_HOPS
  hops712_.assign(dist_.size(), kInf32);
#endif""")
    text = replace(text, "  lastTrace.clear();", "  lastTrace.clear();\n  lastHopCount712 = 0;")
    begin, end = text.index("int Router::search("), text.rindex("\n}  // namespace delayest")
    prefix, body, suffix = text[:begin], text[begin:end], text[end:]
    body = replace(body, "  int traceBest = -1;", """  int traceBest = -1;
#ifdef EXP712_MIN_HOPS
  uint32_t bestHops = kInf32;
#endif""")
    body = replace(body, """    if (g >= best) return;
    const int state = stateId(x, y, zIndexOfPort_[zPort]);
    if (g < dist_[state]) {""", """#ifdef EXP712_MIN_HOPS
    if (g > best) return;
    const uint32_t hops = parent < 0 ? 0 : hops712_[parent] + 1;
#else
    if (g >= best) return;
#endif
    const int state = stateId(x, y, zIndexOfPort_[zPort]);
#ifdef EXP712_MIN_HOPS
    if (g < dist_[state] || (g == dist_[state] && hops < hops712_[state])) {
      hops712_[state] = hops;
#else
    if (g < dist_[state]) {
#endif""")
    body = replace(body, "        best = std::min<uint32_t>(best, static_cast<uint32_t>(cost));",
        """        best = std::min<uint32_t>(best, static_cast<uint32_t>(cost));
#ifdef EXP712_MIN_HOPS
        bestHops = 0;
#endif""")
    body = replace(body, "    if (f >= best) break;", """#ifdef EXP712_MIN_HOPS
    if (f > best) break;
#else
    if (f >= best) break;
#endif""")
    body = replace(body, """    if (state == goalState) {
      best = g;
      traceBest = state;
      break;
    }""", """    if (state == goalState) {
#ifdef EXP712_MIN_HOPS
      if (g < best || (g == best && hops712_[state] < bestHops)) {
        best = g; bestHops = hops712_[state]; traceBest = state;
      }
      continue;
#else
      best = g; traceBest = state; break;
#endif
    }""")
    body = replace(body, "    if (base >= best) continue;", """#ifdef EXP712_MIN_HOPS
    if (base > best) continue;
#else
    if (base >= best) continue;
#endif""")
    for value in ("base", "candidate"):
        old = f"        if ({value} < best) {{ best = {value}; traceBest = state; }}"
        new = f"""#ifdef EXP712_MIN_HOPS
        if ({value} < best || ({value} == best && hops712_[state]+1 < bestHops)) {{
          best = {value}; bestHops = hops712_[state]+1; traceBest = state;
        }}
#else
{old}
#endif"""
        body = replace(body, old, new)
    body = replace(body, "      if (candidate >= best) continue;", """#ifdef EXP712_MIN_HOPS
      if (candidate > best) continue;
#else
      if (candidate >= best) continue;
#endif""")
    body = replace(body, "  std::reverse(lastTrace.begin(), lastTrace.end());",
        """  std::reverse(lastTrace.begin(), lastTrace.end());
#ifdef EXP712_MIN_HOPS
  lastHopCount712 = bestHops;
#endif""")
    return prefix + body + suffix


def prepare():
    assert read("../exp709/validation/results/exp709/report.json")["all_checks_passed"]
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    toy_check()
    inputs = []
    for item in read(OLD / "validation/results/exp705/report.json")["files"]:
        inputs.append(check(OLD / item["path"], item))
    qpath = OLD / "build/exp705/queries.bin"
    dpath = OLD / "build/exp705/delta.i32"
    prior = read(OLD / "validation/results/exp705/freeze.json")
    for item in prior["files"]:
        if item["path"] in ("build/exp705/queries.bin", "build/exp705/delta.i32"):
            inputs.append(check(OLD / item["path"], item))
    query = np.fromfile(qpath, "<i4", offset=12).reshape(-1, 10)
    delta = np.fromfile(dpath, "<i4").reshape(-1, 2)
    strata = query[::4, 4]*4 + 2*(delta[:, 0]<0) + (delta[:, 1]<0)
    rng = np.random.default_rng(20261025712)
    pairs = np.concatenate([rng.choice(np.flatnonzero(strata == h), 10, replace=False)
                            for h in range(104)]).astype("<u4")
    selected = (pairs[:, None]*4 + np.arange(4)).ravel().astype("<u4")
    rows = query[selected]
    assert len(rows) == 4160 and len(np.unique(pairs)) == 1040
    assert len(np.unique(rows[:, 4])) == 26 and len(np.unique(rows[:, 6])) == 36
    assert set(rows[:, 5]) == set(range(8)) and set(rows[:, 7]) == set(range(8))
    with (BUILD / "queries.bin").open("xb") as out:
        out.write(b"EX535Q01" + struct.pack("<I", len(rows)) + rows.tobytes())
    selected.tofile(BUILD / "selected.u32")
    strata[pairs].astype("<u2").tofile(BUILD / "strata.u16")
    sums = np.fromfile(OLD / "build/exp705/paths.summary.i32", "<i4").reshape(-1, 8)
    (sums[selected, 0]+sums[selected, 2]).astype("<i4").tofile(BUILD / "gold.i32")
    trace_dir = Path("../exp552/build/exp552/trace")
    for item in read("../exp552/validation/results/exp552/freeze.json")["files"]:
        if item["path"].startswith("build/exp552/trace/"):
            inputs.append(check(Path("../exp552") / item["path"], item))
    private = BUILD / "trace"
    shutil.copytree(trace_dir, private)
    cpp = private / "src/router.cpp"
    cpp.write_text(patch_router(cpp.read_text()))
    header = private / "src/router.h"
    text = replace(header.read_text(), "  std::vector<int> traceParent_;",
                   "  std::vector<int> traceParent_;\n  std::vector<uint32_t> hops712_;")
    text = replace(text, "  std::vector<TraceState> lastTrace;",
                   "  std::vector<TraceState> lastTrace;\n  uint32_t lastHopCount712 = 0;")
    header.write_text(text)
    tracer = Path("../exp552/tests/exp552_real_paths.cpp")
    inputs.append(identity(tracer))
    text = replace(tracer.read_text(), '#include "../build/exp552/trace/scaffold.cpp"',
                   '#include "scaffold.cpp"')
    text = replace(text, "count < 59904", "count != 4160")
    text = replace(text, "sources.size() != 208 || targets.size() != 288 || pairs.size() != 59904",
                   "pairs.size() != 1040")
    text = replace(text, "      totalHops += hops;", """#ifdef EXP712_MIN_HOPS
      if (hops != router.lastHopCount712)
        throw std::runtime_error("minimum-hop label differs from recovered path");
#endif
      totalHops += hops;""")
    (private / "trace712.cpp").write_text(text)
    for arch in sorted(previous.ARCH.glob("*.json")):
        inputs.append(identity(arch))
    binaries = {}
    for arm in ARMS:
        command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
            "-Wno-unused-function", "-static", "-s", "-march=x86-64", "-mtune=generic",
            "-ffp-contract=off"]
        if arm != "O":
            command.append("-DEXP712_REVERSE" if arm == "R" else "-DEXP712_MIN_HOPS")
        command += [str(private / "trace712.cpp")] + [
            str(private / "src" / name) for name in ("architecture.cpp", "router.cpp", "residue_estimator.cpp")]
        command += ["-o", str(BUILD / ("trace-"+arm))]
        execution.measured(command, "compile-"+arm)
        assert not (ROOT / ("compile-"+arm+".stderr")).read_bytes()
        binaries[arm] = identity(BUILD / ("trace-"+arm))
    orbit = check(Path("../exp501/build/exp501/tools/orbit.i16"),
                  read("../exp552/validation/results/exp552/trace-freeze.json")["orbit"])
    files = [PLAN, Path(__file__), ROOT / "protocol-original.md",
        *[p for p in private.rglob("*") if p.is_file()],
        *[BUILD / n for n in ("queries.bin", "selected.u32", "strata.u16", "gold.i32")]]
    write(ROOT / "freeze.json", dict(inputs=inputs, files=[identity(p) for p in files],
        binaries=binaries, orbit=orbit, population_strata=np.bincount(strata, minlength=104).tolist(),
        sampled_pairs=pairs.tolist(), seed=20261025712, rows=4160, pair_groups=1040,
        exact_primary_labels_reused=True, toy_check_passed=True,
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP712_PREPARED", flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"]+frozen["inputs"]+list(frozen["binaries"].values())+[frozen["orbit"]]:
        check(item["path"], item)
    old_cpu, old_as = resource.getrlimit(resource.RLIMIT_CPU), resource.getrlimit(resource.RLIMIT_AS)
    for arm in ARMS:
        resource.setrlimit(resource.RLIMIT_CPU, (1800, old_cpu[1]))
        resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, old_as[1]))
        try:
            result = execution.measured([frozen["binaries"][arm]["path"], str(previous.ARCH),
                str(BUILD / "queries.bin"), str(BUILD / "gold.i32"), frozen["orbit"]["path"],
                str(BUILD / arm)], "trace-"+arm)
        finally:
            resource.setrlimit(resource.RLIMIT_CPU, old_cpu)
            resource.setrlimit(resource.RLIMIT_AS, old_as)
        assert result["threads"] == 1 and result["rss_bytes"] <= 1_500_000_000
        assert result["cpu_s"] <= 1800 and not (ROOT / ("trace-"+arm+".stderr")).read_bytes()
        report = json.loads((ROOT / ("trace-"+arm+".stdout")).read_text().splitlines()[-1])
        assert report["complete"] and report["rows"] == 4160 and report["terminal_folds"] == 0
        write(ROOT / ("trace-"+arm+".json"), report)
        print("EXP712_TRACED", arm, result["cpu_s"], flush=True)


def analyze():
    frozen = read(ROOT / "freeze.json")
    q = np.fromfile(BUILD / "queries.bin", "<i4", offset=12).reshape(-1, 10)
    gold = np.fromfile(BUILD / "gold.i32", "<i4")
    selected = np.fromfile(BUILD / "selected.u32", "<u4")
    strata = np.fromfile(BUILD / "strata.u16", "<u2")
    names, exists, arcs, z, dx, dy, dest = previous.graph()
    old_lengths = np.fromfile(OLD / "build/exp705/paths.lengths.u32", "<u4")
    old_words = np.fromfile(OLD / "build/exp705/paths.words.u8", "u1")
    old_offsets = np.r_[0, np.cumsum(old_lengths, dtype="i8")]
    outputs, words_by_arm, lengths_by_arm, run_lengths = {}, {}, {}, {}
    for arm in ARMS:
        lengths = np.fromfile(BUILD / (arm+".lengths.u32"), "<u4")
        words = np.fromfile(BUILD / (arm+".words.u8"), "u1")
        sums = np.fromfile(BUILD / (arm+".summary.i32"), "<i4").reshape(-1, 8)
        assert len(lengths) == 4160 and np.array_equal(sums[:, 0]+sums[:, 2], gold)
        offsets = np.r_[0, np.cumsum(lengths, dtype="i8")]
        assert offsets[-1] == len(words)
        full = [words[offsets[i]:offsets[i+1]] for i in range(len(q))]
        if arm == "O":
            for i, old in enumerate(selected):
                assert np.array_equal(full[i], old_words[old_offsets[old]:old_offsets[old+1]])
        values = np.full((1040, 4, 4), -1, "<i4")
        reason = np.zeros((1040, 4, 4), "u1")
        rle = []
        for i, word in enumerate(full):
            motion = list(zip(dx[z[word]].tolist(), dy[z[word]].tolist()))
            rle.append(sum(j == 0 or m != motion[j-1] for j, m in enumerate(motion)))
            for j in range(4):
                target = (i//4)*4+j
                x, y, tx, ty, sp, tp = [int(q[target, k]) for k in (0, 1, 2, 3, 8, 9)]
                p, cost, fail = sp, 0, 0
                for c in word:
                    zp = int(z[c])
                    assert arcs[p, zp] >= 0
                    nx, ny, fee = previous.landing(np.array([x]), np.array([y]),
                                                  np.array([dx[zp]]), np.array([dy[zp]]))
                    cost += int(arcs[p, zp])+int(fee[0])
                    x, y, p = int(nx[0]), int(ny[0]), int(dest[zp])
                    if not (0 <= x < 120 and 0 <= y < 550):
                        fail = 1
                        break
                    if not exists[y, x]:
                        fail = 2
                        break
                if not fail:
                    assert arcs[p, tp] >= 0
                    cost += int(arcs[p, tp])
                    if (x, y) != (tx, ty):
                        fail = 3
                    else:
                        assert cost >= int(gold[target])
                        values[i//4, i%4, j] = cost
                reason[i//4, i%4, j] = fail
                if i%4 == j:
                    assert not fail and cost == gold[i]
        for j in range(4):
            values[:, j, j] = -1
        values.tofile(BUILD / (arm+"-cross.i32"))
        reason.tofile(BUILD / (arm+"-reasons.u8"))
        outputs[arm] = values
        words_by_arm[arm], lengths_by_arm[arm], run_lengths[arm] = full, lengths, np.array(rle)
    assert np.all(lengths_by_arm["H"] <= lengths_by_arm["O"])
    assert np.all(lengths_by_arm["H"] <= lengths_by_arm["R"])
    masks = {}
    for arm, values in outputs.items():
        masks[arm] = (np.any(values >= 0, axis=1),
                      np.any(values == gold.reshape(1040, 1, 4), axis=1))
    masks["union"] = tuple(np.logical_or.reduce([masks[a][i] for a in ARMS]) for i in (0, 1))
    population = np.array(frozen["population_strata"])
    def estimate(values):
        per_pair = np.asarray(values, dtype="f8").reshape(1040, 4).mean(axis=1)
        mean, variance = 0., 0.
        for h, n in enumerate(population):
            v = per_pair[strata == h]
            assert len(v) == 10
            w = n/population.sum()
            mean += w*float(v.mean())
            variance += w*w*(1-len(v)/n)*float(v.var(ddof=1))/len(v)
        return dict(mean=mean, design_se=variance**.5,
                    normal_ci95=[mean-1.96*variance**.5, mean+1.96*variance**.5])
    metric = {a:dict(coverage=estimate(m[0]), exact_recovery=estimate(m[1]))
              for a, m in masks.items()}
    gain = estimate(masks["union"][1].astype(int)-masks["O"][1].astype(int))
    support_delta = estimate(masks["H"][0].astype(int)-masks["O"][0].astype(int))
    length_ratio = estimate(lengths_by_arm["H"])["mean"]/estimate(lengths_by_arm["O"])["mean"]
    gate = bool(gain["mean"] >= .03 or (length_ratio <= .8 and support_delta["mean"] >= -.005))
    result = dict(all_checks_passed=True, metrics=metric, union_exact_gain=gain,
        H_coverage_delta=support_delta, H_over_O_mean_hops=length_ratio,
        mean_hops={a:estimate(lengths_by_arm[a]) for a in ARMS},
        mean_motion_rle={a:estimate(run_lengths[a]) for a in ARMS},
        changed_words={a:sum(not np.array_equal(x,y) for x,y in zip(words_by_arm["O"],words_by_arm[a]))
                       for a in ARMS},
        expand_representatives=gate, O_original_words_equal=True, H_never_more_hops=True,
        candidate_own_location_excluded=True, generalization_claim=False, accuracy_claim=False,
        files=[identity(p) for p in BUILD.iterdir() if p.is_file()],
        disk_free_end_bytes=shutil.disk_usage(".").free)
    write(ROOT / "report.json", result)
    print("EXP712_COMPLETE", gain, length_ratio, gate, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp712")
    assert sys.argv[1:] in (["prepare"], ["run"], ["analyze"])
    dict(prepare=prepare, run=run, analyze=analyze)[sys.argv[1]]()
