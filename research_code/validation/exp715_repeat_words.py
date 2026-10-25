#!/usr/bin/env python3
"""Measure an exact bounded-repeat grammar on the frozen real D0 witnesses."""
import itertools
from pathlib import Path
import resource
import shutil
import socket
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp715"), Path("build/exp715")
PLAN = Path("experiment/实验715-完整端口多Net重复片段的执行复杂度.md")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
execution.ROOT = ROOT


def possibilities(word, at, maximum):
    yield 1, 1
    for width in range(1, maximum+1):
        count = 2
        while at+width*count <= len(word):
            if word[at+(count-1)*width:at+count*width] != word[at:at+width]:
                break
            yield width*count, width
            count += 1


def minimum(word, maximum):
    costs = [0]*(len(word)+1)
    for at in range(len(word)-1, -1, -1):
        costs[at] = 1+min(costs[at+span] for span, _ in possibilities(word, at, maximum))
    return costs[0]


def self_check():
    def brute(word):
        if not word:
            return 0
        return 1+min(brute(word[span:]) for span, _ in possibilities(word, 0, 4))
    cases = 0
    for length in range(9):
        for word in itertools.product((0, 1), repeat=length):
            assert minimum(word, 4) == brute(word)
            cases += 1
    assert minimum((0, 1)*6, 1) == 12 and minimum((0, 1)*6, 4) == 1
    return cases


def prepare():
    assert not ROOT.exists() and not BUILD.exists()
    assert read("../exp714/validation/results/exp714/100m-report.json")["selected"] == "A"
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    source = Path("../exp705/build/exp705")
    previous = read("../exp705/validation/results/exp705/freeze.json")["files"] + \
        read("../exp705/validation/results/exp705/report.json")["files"]
    required = {"queries.bin", "delta.i32", "paths.lengths.u32", "paths.words.u8", "paths.summary.i32"}
    records = {Path(item["path"]).name: item for item in previous}
    inputs = [check(source/name, records[name]) for name in sorted(required)]
    # The frozen witness solver includes this same architecture implementation.
    include = Path("../exp589/src")
    objects = [Path("../exp580/build/exp580/architecture-resolver.o"),
               Path("../exp579/build/exp579/arch-text.o")]
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror",
               "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
               "-I", str(include), "tests/exp715_repeat_words.cpp", *map(str, objects),
               "-static", "-o", str(BUILD/"repeat-words")]
    execution.measured(command, "compile")
    assert not (ROOT/"compile.stderr").read_bytes()
    write(ROOT/"freeze.json", dict(inputs=inputs, source=str(source),
        files=[identity(p) for p in (Path(__file__), Path("tests/exp715_repeat_words.cpp"),
               PLAN, ROOT/"protocol-original.md", include/"architecture.h", *objects,
               *sorted(Path("../../doc/eda比赛文件/arch").glob("*.json")))],
        compile_command=command, binary=identity(BUILD/"repeat-words"), maximum_unit=4,
        tiny_exhaustive_cases=self_check(),
        disk_free_start_bytes=shutil.disk_usage(".").free))


def analyze(frozen):
    data = Path(frozen["source"])
    queries = np.fromfile(data/"queries.bin", "<i4", offset=12).reshape(-1, 10)
    delta = np.fromfile(data/"delta.i32", "<i4").reshape(-1, 2)
    summaries = np.fromfile(data/"paths.summary.i32", "<i4").reshape(-1, 8)
    counts = np.fromfile(BUILD/"counts.u32", "<u4").reshape(-1, 3)
    assert counts.shape == (239616, 3)
    def metrics(mask):
        v = counts[mask].astype("f8")
        return dict(rows=len(v), mean_hops=float(v[:, 0].mean()),
            self_mean_calls=float(v[:, 1].mean()), multi_mean_calls=float(v[:, 2].mean()),
            mean_call_reduction_fraction=float(1-v[:, 2].sum()/v[:, 1].sum()),
            self_call_quantiles=np.quantile(v[:, 1], [.5, .9, .99, 1]).tolist(),
            multi_call_quantiles=np.quantile(v[:, 2], [.5, .9, .99, 1]).tolist(),
            at_most_four_calls_fraction=float((v[:, 2] <= 4).mean()))
    all_metrics = metrics(np.ones(len(queries), bool))
    direction = np.repeat(2*(delta[:, 0] < 0)+(delta[:, 1] < 0), 4)
    role = 2*(queries[:, 4] >= 20)+(queries[:, 6] >= 20)
    total = np.repeat(np.abs(delta[:, 0])//10+np.abs(delta[:, 1])//12, 4)
    groups = {}
    for name, labels in (("direction", direction), ("role", role),
                         ("near", total <= 3), ("net_jump", summaries[:, 7] != 0)):
        for value in np.unique(labels):
            groups[f"{name}-{int(value)}"] = metrics(labels == value)
    selected = (all_metrics["mean_call_reduction_fraction"] >= .2 and
                all_metrics["multi_call_quantiles"][1] <= 4 and
                all_metrics["multi_call_quantiles"][2] <= 8)
    files = [identity(p) for p in sorted(BUILD.iterdir()) if p.suffix in (".u8", ".u32")]
    write(ROOT/"report.json", dict(all_checks_passed=True, selected=bool(selected),
        overall=all_metrics, groups=groups, component=read("validation/results/exp715/component.stdout"),
        files=files, serialized_query_bytes=sum(p["bytes"] for p in files if Path(p["path"]).name.startswith("M.")),
        source_roles=len(np.unique(queries[:, 8])), target_roles=len(np.unique(queries[:, 9])),
        port_pairs=len(np.unique(queries[:, 8:10], axis=0)),
        dictionary_selection_uses_observed_paths=True, unknown_displacement_selector_available=False,
        full_estimator_runs=0, new_exact_rows=0, accuracy_claim=False,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP715_COMPLETE", all_metrics, bool(selected), flush=True)


def run():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["inputs"]+frozen["files"]+[frozen["binary"]]:
        check(item["path"], item)
    cpu, memory = resource.getrlimit(resource.RLIMIT_CPU), resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_CPU, (600, cpu[1]))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, memory[1]))
    try:
        result = execution.measured([str(BUILD/"repeat-words"), frozen["source"], str(BUILD),
                                     "../../doc/eda比赛文件/arch"], "component")
    finally:
        resource.setrlimit(resource.RLIMIT_CPU, cpu); resource.setrlimit(resource.RLIMIT_AS, memory)
    assert result["threads"] == 1 and result["rss_bytes"] < 512 << 20
    assert read(ROOT/"component.stdout")["all_checks_passed"]
    analyze(frozen)


def audit(data):
    report = read(ROOT/"report.json")
    for item in report["files"]:
        check(item["path"], item)
    lengths = np.fromfile(data/"paths.lengths.u32", "<u4")
    raw = (data/"paths.words.u8").read_bytes()
    offsets = np.r_[0, np.cumsum(lengths)].astype("i8")
    counts = np.fromfile(BUILD/"counts.u32", "<u4").reshape(-1, 3)
    for column, arm, maximum in ((1, "S", 1), (2, "M", 4)):
        dictionary = np.fromfile(BUILD/(arm+".dictionary.u8"), "u1").reshape(-1, 5)
        terms = np.fromfile(BUILD/(arm+".terms.u32"), "<u4").reshape(-1, 2)
        index = np.fromfile(BUILD/(arm+".offsets.u32"), "<u4")
        assert len(index) == len(lengths)+1 and index[0] == 0 and index[-1] == len(terms)
        assert np.array_equal(np.diff(index), counts[:, column])
        units = []
        for record in dictionary:
            size = int(record[0])
            assert 1 <= size <= maximum and (record[1+size:] == 255).all()
            units.append(bytes(record[1:1+size]))
        for row in range(len(lengths)):
            word = raw[offsets[row]:offsets[row+1]]
            pieces = []
            for unit, repeat in terms[index[row]:index[row+1]]:
                assert 1 <= repeat <= len(word)
                assert repeat >= 2 or len(units[unit]) == 1
                pieces.append(units[unit]*int(repeat))
            assert b"".join(pieces) == word
            assert minimum(word, maximum) == counts[row, column]
    assert not report["selected"] or report["overall"]["mean_call_reduction_fraction"] >= .2
    write(ROOT/"independent-audit.json", dict(all_checks_passed=True, restored_rows=2*len(lengths),
        independent_optimal_call_checks=2*len(lengths), tiny_exhaustive_cases=self_check(),
        report=identity(ROOT/"report.json"), selected=report["selected"]))
    print("EXP715_AUDIT_PASSED", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "audit":
        audit(Path(sys.argv[2]))
    else:
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp715")
        dict(prepare=prepare, run=run)[sys.argv[1]]()
