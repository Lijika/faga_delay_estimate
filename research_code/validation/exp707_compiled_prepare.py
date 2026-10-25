#!/usr/bin/env python3
"""Compile fixed preparation records and measure complete, identical outputs."""
import itertools
import json
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp707"), Path("build/exp707")
PLAN = Path("experiment/实验707-固定架构准备编译与完整100M.md")
BASE = Path("../exp704")
BINS = dict(A=BASE / "build/exp704/C", M=BUILD / "M/estimate", C=BUILD / "C/estimate")
speed.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    return actual


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def worker(text, arm):
    if arm != "A":
        text = replace(text, "extern delayest::Architecture arch;",
                       'extern delayest::Architecture arch;\n#include "exp707_prepare_metadata.h"')
        text = replace(text, "    arch.loadEmbedded();", "    arch.loadEmbedded();\n    initialize707();")
        text = replace(text, "    const int source = kSourceIndex[sp], target = kTargetIndex[tp];",
                       "    const auto& sd=ports707[sp];\n    const int source=sd.source, target=ports707[tp].target;")
        start = text.index("    int ax=sx, ay=sy, ndx=0, ndy=0, fee=0;")
        end = text.index("    const int x=tx-ax", start)
        text = text[:start] + """    int ax, ay, fee, firstLine;
    if (!first707(sx,sy,sd,ax,ay,fee,firstLine)) return;
    const int ndx=sd.dx, ndy=sd.dy;
    const bool hasNet=sd.start!=65535;
""" + text[end:]
        text = replace(text, "const int mandatory=line(sx,sy,ax,ay)+line(ax,ay,tx,ty);",
                       "const int mandatory=firstLine+line707(ax,ay,tx,ty);")
        start = text.index("    bool forced=false;")
        end = text.index("    const int feature[53]", start)
        text = text[:start] + "    const bool forced=forced707(ax,ay,tx,ty);\n" + text[end:]
        text = replace(text, "state.override_cycle=dx==0 && dy==0 && sp==tp && net>=0;",
                       "state.override_cycle=dx==0 && dy==0 && sp==tp && hasNet;")
        text = replace(text, "state.cycle=kCycles[source];", "state.cycle=sd.cycle;")
        text = replace(text, """                const int s=kSourceIndex[q[8]], t=kTargetIndex[q[9]];
                if (s>=0 && t>=0) {
                    q[4]=kSourceFamily[s]; q[5]=kSourceLane[s];
                    q[6]=kTargetFamily[t]; q[7]=kTargetLane[t];""",
                       """                const auto& s=ports707[q[8]];
                const auto& t=ports707[q[9]];
                if (s.source>=0 && t.target>=0) {
                    q[4]=s.sf; q[5]=s.sl;
                    q[6]=t.tf; q[7]=t.tl;""")
    if arm == "C":
        start = text.index("struct Prepared596 {")
        end = text.index("\n\nstatic inline void prepare596", start)
        text = text[:start] + """struct Prepared596 {
    double raw=0.;
    int fee=0, mandatory=0, answer=-1;
    uint16_t pair=0, context=0, cycle=0;
    uint8_t qx=0, qy=0;
    bool dy_negative=false, override_cycle=false, ready=false;
};
static_assert(sizeof(Prepared596)==32);""" + text[end:]
        text = replace(text, "state.dy=dy;", "state.dy_negative=dy<0;")
        text = replace(text, "dy=state.dy;", "dy=state.dy_negative ? -1 : 0;")
    text += """
#ifdef EXP707_CHECK
extern "C" void init707_ARM() { initialize(); }
extern "C" size_t size707_ARM() { return sizeof(Prepared596); }
extern "C" void eval707_ARM(const int32_t* q, unsigned fold, int32_t* v, double* d) {
    Prepared596 s;
    Trace trace{};
    prepare596(q,fold,s,&trace);
    const int prediction=finish596(s,&trace);
    const int32_t fields[15]={int(s.pair),int(s.context),int(s.qx),int(s.qy),
        s.fee,s.mandatory,int(DY_NEGATIVE),int(s.cycle),s.answer,
        int(s.override_cycle),int(s.ready),trace.base,trace.mandatory,trace.prediction,prediction};
    std::memcpy(v,fields,sizeof(fields));
    std::memcpy(v+15,trace.feature,sizeof(trace.feature));
    d[0]=s.raw; d[1]=trace.response; d[2]=trace.raw;
}
#endif
""".replace("ARM", arm).replace("DY_NEGATIVE", "s.dy_negative" if arm == "C" else "s.dy<0")
    return text


def build():
    assert not BUILD.exists()
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    prior = read(BASE / "validation/results/exp704/freeze.json")
    check(BINS["A"], prior["binaries"]["C"])
    old_commands = read("../exp686/validation/results/exp686/freeze.json")["commands"]
    sources, commands = [], {}
    for arm in ("A", "M", "C"):
        directory = BUILD / arm
        directory.mkdir()
        for entry in prior["sources"]:
            original = entry["current"]
            source = BASE / original["path"]
            check(source, original)
            destination = directory / source.name
            if source.name == "worker.cpp":
                destination.write_text(worker(source.read_text(), arm))
            else:
                shutil.copyfile(source, destination)
            sources.append(dict(original=original, current=identity(destination)))
        shutil.copyfile("tests/exp707_prepare_metadata.h", directory / "exp707_prepare_metadata.h")
        compile_cmd = [x.replace("build/exp686", str(directory)) for x in old_commands["compile"]]
        link_cmd = [x.replace("build/exp686", str(directory)) for x in old_commands["link"]]
        link_cmd[-1] = str(BINS[arm]) if arm != "A" else str(directory / "unused")
        commands[arm] = dict(compile=compile_cmd, link=link_cmd)
        if arm != "A":
            speed.measured(compile_cmd, "compile-" + arm)
            speed.measured(link_cmd, "link-" + arm)
            assert BINS[arm].stat().st_size < 100_000_000
            elf = subprocess.check_output(["readelf", "-lW", str(BINS[arm])], text=True)
            assert "INTERP" not in elf
        checked = [x.replace("-Dmain=worker608_F", "-Dmain=worker707_" + arm) for x in compile_cmd]
        checked[checked.index("-o") + 1] = str(directory / "checked.o")
        speed.measured(checked + ["-DEXP707_CHECK"], "compile-check-" + arm)
    common = ["g++", "-std=c++17", "-O3", "-fno-fast-math", "-ffp-contract=off",
        "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "-I", "../exp589/src", "-I", str(BUILD / "M"), "-I", "tests"]
    objects = ["../exp580/build/exp580/architecture-resolver.o",
               "../exp579/build/exp579/arch-text.o"]
    speed.measured(common + ["-DDELAY_ESTIMATE_RESOLVER_AUDIT", "tests/exp707_prepare_metadata.cpp",
        *objects, "-static", "-o", str(BUILD / "metadata-check")], "compile-metadata-check")
    speed.measured([str(BUILD / "metadata-check")], "metadata-check")
    metadata = read(ROOT / "metadata-check.stdout")
    assert metadata["all_equal"] and metadata["net_positions"] == 10_560_000
    assert metadata["max_aligned_bx"] <= 119 and metadata["max_aligned_by"] <= 549, metadata
    speed.measured(common + ["tests/exp707_prepare_compare.cpp",
        *[str(BUILD / arm / "checked.o") for arm in ("A", "M", "C")],
        *objects, "../exp654/build/exp654/codes.o", "../exp652/build/exp652/compressed.o",
        "../exp646/build/exp646/deps/libzstd.a", "-static", "-o", str(BUILD / "compare-check")],
        "compile-compare-check")
    queries = Path("../exp705/build/exp705/queries.bin")
    speed.measured([str(BUILD / "compare-check"), str(queries)], "compare-check")
    component = read(ROOT / "compare-check.stdout")
    assert component["all_equal"] and component["queries"] == 239616
    files = [Path(__file__), PLAN, ROOT / "protocol-original.md",
             *sorted(Path("tests").glob("exp707_*"))]
    write(ROOT / "freeze.json", dict(
        binaries={arm: identity(path) for arm, path in BINS.items()},
        sources=sources, commands=commands, files=[identity(p) for p in files],
        component=component, metadata=metadata, queries=identity(queries),
        input=check(prior["input"]["path"], prior["input"]),
        reference=check(BASE / prior["reference"]["path"], prior["reference"]),
        expected_output=prior["expected_output"],
        schedule=[["A", "M", "C"], *[list(p) for p in itertools.permutations(("A", "M", "C"))]],
        compiler=subprocess.check_output(["g++", "--version"], text=True),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP707_BUILD_PASSED", metadata, component, flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for record in frozen["files"] + list(frozen["binaries"].values()) + [frozen["input"], frozen["reference"]]:
        check(record["path"], record)
    assert read("../exp706/validation/results/exp706/1b-report.json")["all_checks_passed"]
    (ROOT / "processes-before.txt").write_text(subprocess.check_output(
        ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
    timings, records = {a: [] for a in BINS}, []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            assert shutil.disk_usage(".").free > 4_500_000_000
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            assert not output.exists()
            command = ["taskset", "-c", "8", str(BINS[arm]), "-in", frozen["input"]["path"],
                       "-out", str(output)]
            measured = speed.measured(command, output.stem)
            assert measured["threads"] == 1 and measured["rss_bytes"] <= 2_000_000_000
            assert measured["cpu_s"] < 100 and measured["wall_s"] <= 3600
            assert read(measured["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            actual = check(output, frozen["expected_output"])
            record = dict(arm=arm, iteration=iteration, run=measured, output=actual)
            records.append(record)
            write(ROOT / (output.stem + "-evidence.json"), record)
            if iteration:
                timings[arm].append(measured["cpu_s"])
            cleanup = dict(file=actual, retained=frozen["reference"], rebuild_command=command)
            print("EXP707_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
            output.unlink()
            write(ROOT / (output.stem + "-cleanup.json"), dict(cleanup, deleted=True))
            print("EXP707_RUN", iteration, arm, measured["cpu_s"], flush=True)
    stats = {}
    for arm in ("M", "C"):
        diff = [a-b for a, b in zip(timings["A"], timings[arm])]
        mean = statistics.mean(diff)
        half = 3.163381449748624 * statistics.stdev(diff) / math.sqrt(6)
        stats[arm] = dict(saved_s=mean, simultaneous_ci95_s=[mean-half, mean+half],
                         qualifies=mean-half > 0, priority_goal=mean >= .5)
    eligible = [a for a in ("M", "C") if stats[a]["qualifies"]]
    selected = min(eligible, key=lambda a: statistics.mean(timings[a])) if eligible else "A"
    write(ROOT / "100m-report.json", dict(all_checks_passed=True, timings_s=timings,
        stats=stats, selected=selected, selected_binary=frozen["binaries"][selected],
        runs=records, accuracy_delta_pp=0, complete_outputs_identical=True,
        exact_sample_rows=1_916_928, input_previously_observed=True, new_exact_rows=0,
        score_reused=identity("../exp685/validation/results/exp685/score/accuracy.json"),
        contract_reused=identity("../exp685/validation/results/exp685/100m-report.json"),
        removed_bytes=sum(r["output"]["bytes"] for r in records),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP707_100M_COMPLETE", selected, stats, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp707")
    assert sys.argv[1:] in (["build"], ["run"])
    dict(build=build, run=run)[sys.argv[1]]()
