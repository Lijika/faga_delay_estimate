#!/usr/bin/env python3
"""Test a stable batch8 directory-to-curve stage against frozen exp708."""
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp714"), Path("build/exp714")
PLAN = Path("experiment/实验714-批内曲线目录与正文的三阶段求值.md")
BASE = Path("../exp707")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
measured, replace = execution.measured, execution.replace
execution.ROOT = ROOT


def worker(text):
    text = replace(text, "static inline int finish596(", """static inline void stageCurve714(Prepared596& state) {
    if (!state.ready || state.qx+state.qy<=3) return;
    const unsigned code=phaseCodes619[phaseByte619(state.pair,state.context)];
    const unsigned local=local582(0,state.qx,state.qy,1);
    state.answer=int(((state.context/120)*256+code)*542+local);
    _mm_prefetch(reinterpret_cast<const char*>(phaseCurves654+state.answer),_MM_HINT_T0);
}

static inline int finish596(""")
    text = replace(text, "phaseCorrection619(pair,context,qx,qy)",
        "(qx+qy<=3 ? 0 : int(phaseCurves654[state.answer])+kCurveOrigin654)")
    text = replace(text, "    return finish596(state,trace);",
        "    stageCurve714(state);\n    return finish596(state,trace);")
    text = replace(text, "        for (size_t i=0;i<count;++i) {\n            const int answer=finish596(states[i]);",
        "        for (size_t i=0;i<count;++i) stageCurve714(states[i]);\n"
        "        for (size_t i=0;i<count;++i) {\n            const int answer=finish596(states[i]);")
    text = replace(text, "    const int prediction=finish596(s,&trace);",
        "    const int savedAnswer=s.answer;\n"
        "    stageCurve714(s);\n"
        "    require(!s.ready || s.qx+s.qy<=3 || (s.answer>=0 && s.answer<4*256*542),\"curve stage index\");\n"
        "    const int prediction=finish596(s,&trace);")
    text = replace(text, "int(s.cycle),s.answer,", "int(s.cycle),savedAnswer,")
    return text.replace("707_M", "714_C")


def build():
    assert not ROOT.exists() and not BUILD.exists()
    assert read("../exp713/validation/results/exp713/independent-audit.json")["all_checks_passed"]
    assert read("../exp708/validation/results/exp708/1b-report.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    directory = BUILD / "C"
    directory.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    previous = read(BASE / "validation/results/exp707/freeze.json")
    baseline = check(BASE / "build/exp707/M/estimate", previous["binaries"]["M"])
    sources = []
    for item in previous["sources"]:
        original = item["current"]
        if not original["path"].startswith("build/exp707/M/"):
            continue
        source = BASE / original["path"]
        check(source, original)
        dest = directory / source.name
        if dest.name == "worker.cpp":
            dest.write_text(worker(source.read_text()))
        else:
            shutil.copy2(source, dest)
        sources.append(identity(dest))
    header = BASE / "build/exp707/M/exp707_prepare_metadata.h"
    shutil.copy2(header, directory / header.name)
    sources.append(identity(directory / header.name))
    commands = {kind: [x.replace("build/exp707/M", str(directory)) for x in cmd]
                for kind, cmd in previous["commands"]["M"].items()}
    for kind in ("compile", "link"):
        measured(commands[kind], kind)
    binary = directory / "estimate"
    assert binary.stat().st_size < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "NEEDED" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    checked = [x.replace("-Dmain=worker608_F", "-Dmain=worker714_C") for x in commands["compile"]]
    checked[checked.index("-o") + 1] = str(directory / "checked.o")
    measured(checked + ["-DEXP707_CHECK", "-DEXP579_AUDIT"], "compile-check")
    baseline_check = [x.replace("build/exp707/M", str(BASE / "build/exp707/M"))
                      .replace("-Dmain=worker608_F", "-Dmain=worker714_A")
                      for x in previous["commands"]["M"]["compile"]]
    baseline_check[baseline_check.index("-o") + 1] = str(BUILD / "baseline-checked.o")
    measured(baseline_check + ["-DEXP707_CHECK", "-DEXP579_AUDIT"], "compile-baseline-check")
    dependencies = ["../exp580/build/exp580/architecture-resolver.o",
                    "../exp579/build/exp579/arch-text.o", "../exp654/build/exp654/codes.o",
                    "../exp652/build/exp652/compressed.o", "../exp646/build/exp646/deps/libzstd.a"]
    measured(["g++", "-std=c++17", "-O2", "-I", "../exp589/src",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "tests/exp714_curve_check.cpp", str(BUILD / "baseline-checked.o"),
        str(directory / "checked.o"), *dependencies, "-static", "-o", str(BUILD / "component-check")],
        "link-check")
    queries = "../exp705/build/exp705/queries.bin"
    Path("build/exp684/V8").mkdir(parents=True)
    measured([str(BUILD / "component-check"), queries], "component-check")
    assert read(ROOT / "component-check.stdout")["all_equal"]
    reference = check("../exp703/build/exp703/warmup.csv", previous["expected_output"])
    write(ROOT / "freeze.json", dict(binaries=dict(A=baseline, C=identity(binary)),
        commands=commands, sources=sources, dependencies=[identity(p) for p in dependencies],
        queries=identity(queries), component=read(ROOT / "component-check.stdout"),
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md",
                                    Path("tests/exp714_curve_check.cpp"))],
        input=check(previous["input"]["path"], previous["input"]), reference=reference,
        schedule=[["A", "C"], *[list("AC" if j % 2 == 0 else "CA") for j in range(6)]],
        compiler=subprocess.check_output(["g++", "--version"], text=True),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP714_BUILD_PASSED", flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"] + list(frozen["binaries"].values()) + [frozen["input"], frozen["reference"]]:
        check(item["path"], item)
    (ROOT / "processes-before.txt").write_text(subprocess.check_output(
        ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
    timings, runs = dict(A=[], C=[]), []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            assert shutil.disk_usage(".").free > 4_500_000_000
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            assert not output.exists()
            command = ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                       "-in", frozen["input"]["path"], "-out", str(output)]
            result = measured(command, output.stem)
            assert result["threads"] == 1 and result["rss_bytes"] <= 300_000_000
            assert result["wall_s"] <= 3600 and result["cpu_s"] < 100
            assert read(ROOT / (output.stem + ".stderr")) == dict(
                rows=100_000_000, unreachable=0, query_allocations=0)
            actual = check(output, frozen["reference"])
            record = dict(iteration=iteration, arm=arm, run=result, output=actual)
            runs.append(record)
            write(ROOT / (output.stem + "-evidence.json"), record)
            if iteration:
                timings[arm].append(result["cpu_s"])
            print("EXP714_REMOVE_DUPLICATE", output, flush=True)
            output.unlink()
            write(ROOT / (output.stem + "-cleanup.json"), dict(file=actual,
                retained=frozen["reference"], rebuild_command=command, deleted=True))
            print("EXP714_RUN", iteration, arm, result["cpu_s"], flush=True)
    delta = [a-c for a, c in zip(timings["A"], timings["C"])]
    mean = statistics.mean(delta)
    half = 2.570581835636314 * statistics.stdev(delta) / math.sqrt(6)
    passed = mean >= .5 and mean-half > 0
    write(ROOT / "100m-report.json", dict(all_checks_passed=True, runs=runs, timings_s=timings,
        means_s={a: statistics.mean(v) for a, v in timings.items()}, saved_s=mean,
        paired_ci95_s=[mean-half, mean+half], selected="C" if passed else "A",
        quality_delta_pp=0, complete_outputs_identical=True, new_exact_rows=0,
        score_reused=identity("../exp685/validation/results/exp685/score/accuracy.json"),
        exact_sample_rows=1_916_928, input_previously_observed=True,
        contract_reused=identity("../exp685/validation/results/exp685/100m-report.json"),
        removed_bytes=sum(r["output"]["bytes"] for r in runs),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP714_COMPLETE", mean, [mean-half, mean+half], passed, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp714")
    assert sys.argv[1:] in (["build"], ["run"])
    dict(build=build, run=run)[sys.argv[1]]()
