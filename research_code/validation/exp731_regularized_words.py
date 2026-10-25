#!/usr/bin/env python3
"""Select near-optimal words with fewer changes of geometric Net motion."""
import heapq
from pathlib import Path
import shutil
import socket
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp712/validation").resolve()))
import exp712_tie_support as prior

ROOT, BUILD = Path("validation/results/exp731"), Path("build/exp731")
PLAN = Path("experiment/实验731-近最优词的几何切换惩罚与支持复杂度.md")
OLD = Path("../exp712")
ARMS = dict(O=0, E1=1, E4=4)
read, write, identity, check, replace = prior.read, prior.write, prior.identity, prior.check, prior.replace
prior.ROOT, prior.BUILD, prior.ARMS, prior.execution.ROOT = ROOT, BUILD, tuple(ARMS), ROOT


def toy_check():
    # A terminal Z denotes arrival; its unused outgoing motion earns no penalty.
    graph = [[(1, 0), (2, 2)], [(3, 4)], [(3, 3)], []]
    motion = [0, 1, 0, 2]
    for penalty in (0, 1, 4):
        paths = []
        def visit(u, cost, changes, seen):
            if u == 3:
                paths.append((cost+penalty*changes, cost, changes))
                return
            for v, c in graph[u]:
                if v not in seen:
                    visit(v, cost+c, changes+int(v != 3 and motion[u] != motion[v]), seen | {v})
        visit(0, 0, 0, {0})
        distance, heap = [0, 10**9, 10**9, 10**9], [(0, 0)]
        while heap:
            d, u = heapq.heappop(heap)
            if d != distance[u]:
                continue
            for v, c in graph[u]:
                candidate = d+c+penalty*int(v != 3 and motion[u] != motion[v])
                if candidate < distance[v]:
                    distance[v] = candidate
                    heapq.heappush(heap, (candidate, v))
        assert distance[3] == min(paths)[0]
    assert min(paths)[1:] == (5, 0)


def derive_router(text):
    return replace(text, """      const uint32_t candidate = base + static_cast<uint32_t>(cost);
      if (candidate >= best) continue;""", """      const auto& current731 = arch_->net(netIndex);
      const auto& next731 = arch_->net(arch_->netOfOutput(destPort));
      const bool terminal731 = destPort == targetPort && edge.x == tx && edge.y == ty;
      const uint32_t change731 = !terminal731 &&
          (current731.dx != next731.dx || current731.dy != next731.dy);
      const uint32_t candidate = base + static_cast<uint32_t>(cost) + EXP731_LAMBDA * change731;
      if (candidate >= best) continue;""")


def derive_tracer(text):
    text = replace(text, '#include "../build/exp552/trace/scaffold.cpp"', '#include "scaffold.cpp"')
    text = replace(text, "count < 59904", "count != 4160")
    text = replace(text, "sources.size() != 208 || targets.size() != 288 || pairs.size() != 59904",
                   "pairs.size() != 1040")
    text = replace(text, "    const auto gold = readBinary<int32_t>(argv[3], count);",
        """    const auto gold = readBinary<int32_t>(argv[3], count);
    const auto originalChanges731 = readBinary<uint32_t>(
        (std::string(argv[3])+".changes.u32").c_str(), count);""")
    text = replace(text, "      if (answer != gold[i])", "      if (answer < gold[i])")
    text = replace(text, "      std::array<int32_t, 8> sums{};",
                   "      std::array<int32_t, 8> sums{};\n      uint32_t changes731 = 0;")
    text = replace(text, """          if (b.g != static_cast<uint32_t>(sums[0] + sums[1] + sums[2]))
            throw std::runtime_error("trace prefix fee differs");""",
        """          if (!(b.x == tx && b.y == ty && b.port == tp)) {
            const auto& ma731 = arch.net(arch.netOfOutput(a.port));
            const auto& mb731 = arch.net(arch.netOfOutput(b.port));
            changes731 += ma731.dx != mb731.dx || ma731.dy != mb731.dy;
          }
          if (b.g != static_cast<uint32_t>(sums[0] + sums[1] + sums[2]) +
                         EXP731_LAMBDA * changes731)
            throw std::runtime_error("regularized trace prefix fee differs");""")
    text = replace(text, "      if (sums[0] + sums[1] + sums[2] != answer ||",
        """      uint32_t recounted731 = 0;
      for (size_t j = 1; j < word.size(); ++j) {
        const auto& a731 = arch.net(arch.netOfOutput(zPorts[word[j-1]]));
        const auto& b731 = arch.net(arch.netOfOutput(zPorts[word[j]]));
        recounted731 += a731.dx != b731.dx || a731.dy != b731.dy;
      }
      if (recounted731 != changes731 ||
          sums[0] + sums[2] < gold[i] ||
          answer > gold[i] + int(EXP731_LAMBDA * originalChanges731[i]))
        throw std::runtime_error("regularized objective or original fee bound differs");
      if (sums[0] + sums[1] + sums[2] + int(EXP731_LAMBDA * changes731) != answer ||""")
    return text


def load_words(stem):
    lengths = np.fromfile(str(stem)+".lengths.u32", "<u4")
    words = np.fromfile(str(stem)+".words.u8", "u1")
    sums = np.fromfile(str(stem)+".summary.i32", "<i4").reshape(-1, 8)
    offsets = np.r_[0, np.cumsum(lengths, dtype="i8")]
    assert len(lengths) == 4160 and len(sums) == 4160 and offsets[-1] == len(words)
    assert np.array_equal(sums[:, 5], lengths)
    return [words[offsets[i]:offsets[i+1]] for i in range(4160)], lengths, sums


def changes(words, z, dx, dy):
    return np.asarray([np.count_nonzero((dx[z[w[1:]]] != dx[z[w[:-1]]]) |
                                       (dy[z[w[1:]]] != dy[z[w[:-1]]])) for w in words], "<u4")


def prepare():
    assert not ROOT.exists() and not BUILD.exists()
    assert read(OLD/"validation/results/exp712/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    toy_check()
    previous = read(OLD/"validation/results/exp712/freeze.json")
    inputs = []
    for item in previous["files"]:
        if Path(item["path"]).name in ("queries.bin", "selected.u32", "strata.u16", "gold.i32"):
            path = OLD/item["path"]
            inputs.append(check(path, item))
            shutil.copy2(path, BUILD/path.name)
    for suffix in (".lengths.u32", ".words.u8", ".summary.i32"):
        inputs.append(identity(OLD/("build/exp712/O"+suffix)))
    _, _, _, z, dx, dy, _ = prior.previous.graph()
    words, _, _ = load_words(OLD/"build/exp712/O")
    changes(words, z, dx, dy).tofile(BUILD/"gold.i32.changes.u32")
    private = BUILD/"trace"
    shutil.copytree("../exp552/build/exp552/trace", private)
    cpp = private/"src/router.cpp"
    inputs.append(identity("../exp552/build/exp552/trace/src/router.cpp"))
    cpp.write_text(derive_router(cpp.read_text()))
    tracer = Path("../exp552/tests/exp552_real_paths.cpp")
    inputs.append(identity(tracer))
    (private/"trace731.cpp").write_text(derive_tracer(tracer.read_text()))
    binaries = {}
    for arm, value in ARMS.items():
        command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
            "-Wno-unused-function", "-static", "-s", "-march=x86-64", "-mtune=generic",
            "-ffp-contract=off", f"-DEXP731_LAMBDA={value}", str(private/"trace731.cpp")]
        command += [str(private/"src"/n) for n in ("architecture.cpp", "router.cpp", "residue_estimator.cpp")]
        command += ["-o", str(BUILD/("trace-"+arm))]
        prior.execution.measured(command, "compile-"+arm)
        assert not (ROOT/("compile-"+arm+".stderr")).read_bytes()
        binaries[arm] = identity(BUILD/("trace-"+arm))
    orbit = check(previous["orbit"]["path"], previous["orbit"])
    files = [PLAN, Path(__file__), ROOT/"protocol-original.md",
        *[p for p in private.rglob("*") if p.is_file()],
        *[BUILD/n for n in ("queries.bin", "selected.u32", "strata.u16", "gold.i32", "gold.i32.changes.u32")]]
    gap = Path("../exp652/doc/eda比赛文件/arch/SRB_Gap.json")
    inputs += [identity(p) for p in (Path(prior.__file__), Path(prior.previous.__file__),
               OLD/"validation/results/exp712/independent-audit.json", gap,
               *sorted(prior.previous.ARCH.glob("*.json")))]
    write(ROOT/"freeze.json", dict(inputs=inputs, files=[identity(p) for p in files],
        binaries=binaries, orbit=orbit, population_strata=previous["population_strata"],
        rows=4160, pair_groups=1040, penalties=ARMS, excess_limit_ps=8,
        toy_check_passed=True, disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP731_PREPARED", flush=True)


def replay(words, q, gold, exists, arcs, z, dx, dy, dest, px, py):
    values = np.full((1040, 4, 4), -1, "<i4")
    full = values.copy()
    for i, word in enumerate(words):
        for j in range(4):
            target = (i//4)*4+j
            x, y, tx, ty, p, tp = [int(q[target, k]) for k in (0, 1, 2, 3, 8, 9)]
            cost = line = 0
            valid = True
            for c in word:
                zp = int(z[c])
                assert arcs[p, zp] >= 0
                cross = y % 100 < 50
                compressed = x-14*(cross and x >= 90)
                landing = compressed+int(dx[zp])
                nx = landing+14*(cross and landing >= 76) if dx[zp] else x
                ny = y+int(dy[zp])
                if not (0 <= nx < 120 and 0 <= ny < 550) or not exists[ny, nx]:
                    valid = False
                    break
                cost += int(arcs[p, zp])+292*(nx-x != dx[zp])
                line += abs(int(px[nx])-int(px[x]))+abs(int(py[ny])-int(py[y]))
                x, y, p = nx, ny, int(dest[zp])
            if valid:
                assert arcs[p, tp] >= 0
                if (x, y) == (tx, ty):
                    cost += int(arcs[p, tp])
                    assert cost >= int(gold[target])
                    values[i//4, i%4, j], full[i//4, i%4, j] = cost, cost+line
            if j == i%4:
                assert values[i//4, i%4, j] >= gold[i]
    return values, full


def analyze():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["inputs"]+frozen["files"]:
        check(item["path"], item)
    q = np.fromfile(BUILD/"queries.bin", "<i4", offset=12).reshape(-1, 10)
    gold = np.fromfile(BUILD/"gold.i32", "<i4")
    strata = np.fromfile(BUILD/"strata.u16", "<u2")
    population = np.asarray(frozen["population_strata"], "f8")
    _, exists, arcs, z, dx, dy, dest = prior.previous.graph()
    original, original_lengths, _ = load_words(OLD/"build/exp712/O")
    original_changes = changes(original, z, dx, dy)
    px, py = np.zeros(121, "i4"), np.zeros(551, "i4")
    for line in read("../exp652/doc/eda比赛文件/arch/SRB_Gap.json")["Gap"]["Line"]:
        (px if line["direction"] == "vertical" else py)[line["site"]+1] += line["delay"]
    px, py = px.cumsum(), py.cumsum()
    def estimate(values, critical=1.96):
        per_pair = np.asarray(values, "f8").reshape(1040, 4).mean(axis=1)
        means, variances = [], []
        for h, n in enumerate(population):
            v = per_pair[strata == h]
            assert len(v) == 10
            w = n/population.sum()
            means.append(w*float(v.mean()))
            variances.append(w*w*(1-10/n)*float(v.var(ddof=1))/10)
        mean, se = sum(means), sum(variances)**.5
        return dict(mean=mean, design_se=se, interval=[mean-critical*se, mean+critical*se])
    reports, masks, full_minima = {}, {}, {}
    for arm, penalty in ARMS.items():
        words, lengths, sums = load_words(BUILD/arm)
        k = changes(words, z, dx, dy)
        cost = sums[:, 0]+sums[:, 2]
        assert np.all(sums[:, 1] == 0) and np.all(cost >= gold)
        assert np.all(cost+penalty*k <= gold+penalty*original_changes)
        if penalty:
            assert np.all(k <= original_changes)
        else:
            assert all(np.array_equal(a, b) for a, b in zip(words, original))
        eligible = cost-gold <= 8
        accepted = [w if eligible[i] else original[i] for i, w in enumerate(words)]
        rle = changes(accepted, z, dx, dy)+(np.asarray([len(w) for w in accepted]) > 0)
        values, full = replay(accepted, q, gold, exists, arcs, z, dx, dy, dest, px, py)
        for i in range(4):
            rows = np.arange(1040)*4+i
            assert np.array_equal(values[:, i, i], np.where(eligible, cost, gold)[rows])
            values[:, i, i] = full[:, i, i] = -1
        values.tofile(BUILD/(arm+"-cross.i32"))
        full.tofile(BUILD/(arm+"-full-cross.i32"))
        target = gold.reshape(1040, 1, 4)
        masks[arm] = np.any((values >= 0) & (values <= target+8), axis=1)
        full_minima[arm] = np.min(np.where(full >= 0, full, np.iinfo(np.int32).max), axis=1)
        reports[arm] = dict(coverage=estimate(np.any(values >= 0, axis=1)),
            exact_recovery=estimate(np.any(values == target, axis=1)),
            within8=estimate(masks[arm]), mean_rle=estimate(rle), mean_hops=estimate(lengths),
            accepted_fraction=estimate(eligible), mean_original_excess=estimate(cost-gold),
            maximum_original_excess_ps=int((cost-gold).max()),
            changed_words=sum(not np.array_equal(a, b) for a, b in zip(accepted, original)))
    eligible = []
    for arm in ("E1", "E4"):
        gain = estimate(masks[arm].astype(int)-masks["O"].astype(int), 2.241402728)
        ratio = reports[arm]["mean_rle"]["mean"]/reports["O"]["mean_rle"]["mean"]
        passed = (gain["mean"] >= .03 and gain["interval"][0] > 0) or (ratio <= .8 and gain["mean"] >= -.005)
        reports[arm].update(within8_gain=gain, mean_rle_ratio=ratio, expand=bool(passed))
        common = ((full_minima[arm] != np.iinfo(np.int32).max) &
                  (full_minima["O"] != np.iinfo(np.int32).max))
        difference = full_minima[arm].astype("i8")-full_minima["O"]
        coverage = estimate(common)["mean"]
        reports[arm]["complete_line_upper_bound_comparison"] = dict(
            common_fraction=coverage,
            mean_delta_ps_on_common=estimate(np.where(common, difference, 0))["mean"]/coverage,
            lower_fraction=estimate(common & (difference < 0))["mean"],
            higher_fraction=estimate(common & (difference > 0))["mean"])
        if passed:
            eligible.append(arm)
    write(ROOT/"report.json", dict(all_checks_passed=True, reports=reports, eligible=eligible,
        selected=eligible[0] if eligible else None, candidate_own_location_excluded=True,
        original_control_words_equal=True, real_costs_and_objectives_verified=True,
        complete_estimator_runs=0, new_original_exact_labels=0, accuracy_claim=False,
        files=[identity(p) for p in BUILD.iterdir() if p.is_file()],
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP731_COMPLETE", eligible, {a: reports[a]["mean_rle_ratio"] for a in ("E1", "E4")}, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp731")
    assert sys.argv[1:] in (["prepare"], ["run"], ["analyze"])
    dict(prepare=prepare, run=prior.run, analyze=analyze)[sys.argv[1]]()
