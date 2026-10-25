#!/usr/bin/env python3
"""Compile the complete fixed port language into one checked table access."""
import itertools
import os
from pathlib import Path
import shutil
import signal
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp686/validation").resolve()))
import exp686_event_boundary as prior

read, write, identity, check, speed = prior.read, prior.write, prior.identity, prior.check, prior.speed
ROOT, BUILD = Path("validation/results/exp704"), Path("build/exp704")
PLAN = Path("experiment/实验704-固定端口语言的直接解码与完整100M.md")
BASE = Path("../exp686")
BINS = dict(A=BASE / "build/exp686/N", C=BUILD / "C")
speed.ROOT = ROOT


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def parser(text):
    text = replace(text, "static PortSlot580 portSlots580[2048];",
                   "static PortSlot580 portSlots580[688];")
    start, end = text.index("static inline unsigned portHash580("), text.index("static void initializePorts580()")
    text = text[:start] + """static inline unsigned portIndex704(std::string_view name) {
    static constexpr uint8_t kind[16]={0,1,0,3,0,0,0,0,0,0,0,0,2,0,0,0};
    static constexpr uint8_t direction[8]={0,0,0,2,0,0,1,3};
    static constexpr auto suffix=[] {
        std::array<uint8_t,64> a{};
        for (unsigned i=0;i<6;++i) a['0'+i]=uint8_t(i);
        a['D'&63]=6; a['M'&63]=7; a['Y'&63]=10;
        return a;
    }();
    if (name.size()>=6) {
        const unsigned role=name[0]=='I', k=kind[uint8_t(name[1])&15];
        const unsigned d=direction[uint8_t(name[2])&7];
        const unsigned v=name.size()==7 && name[3]=='B';
        return (((role*4+k)*4+d)*2+v)*8+(uint8_t(name[name.size()-2])&7);
    }
    const unsigned role=name[0]=='S', group=(unsigned(uint8_t(name[2]))-'A')&7;
    const unsigned sub=name.size()==5 ? 8+(uint8_t(name[4])&1) : suffix[uint8_t(name[3])&63];
    return 512+(role*8+group)*11+sub;
}

""" + text[end:]
    text = replace(text, "unsigned slot = portHash580(key);\n        while (portSlots580[slot].port >= 0) slot = (slot + 1) & 2047;",
                   'const unsigned slot = portIndex704(name);\n        require(portSlots580[slot].port < 0, "direct port collision");')
    start = text.index("    unsigned slot = portHash580(key);", text.index("static inline bool parsePin601"))
    end = text.index("\n    return false;", start)
    text = text[:start] + """    const auto& entry = portSlots580[portIndex704(name)];
    if (entry.port >= 0 && entry.key == key && entry.length == name.size()) {
        x = xx; y = yy; port = entry.port;
        return true;
    }""" + text[end:]
    assert "portHash580" not in text
    return text


def build():
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    old = read(BASE / "validation/results/exp686/freeze.json")
    check(BINS["A"], old["binaries"]["N"])
    sources = []
    for entry in old["sources"]:
        item = entry["current"]
        source = BASE / item["path"]
        check(source, item)
        destination = BUILD / source.name
        if source.name == "exp601_port_parser.h":
            shutil.copyfile(source, BUILD / "original_parser.h")
            destination.write_text(parser(source.read_text()))
        else:
            shutil.copyfile(source, destination)
        sources.append(dict(original=identity(source), current=identity(destination)))
    assert (BUILD / "original_parser.h").exists()
    for stage in ("compile", "link"):
        command = [x.replace("build/exp686", str(BUILD)) for x in old["commands"][stage]]
        if stage == "link":
            command[-1] = str(BINS["C"])
        speed.measured(command, stage)
        assert not (ROOT / f"{stage}.stderr").read_bytes()
    assert BINS["C"].stat().st_size < 100_000_000
    result = subprocess.run(["ldd", str(BINS["C"])], capture_output=True, text=True)
    assert "not a dynamic executable" in result.stdout + result.stderr
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
        "-march=x86-64", "-mtune=generic", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "-I", "../exp589/src", "-I", str(BUILD), "tests/exp704_port_decoder.cpp",
        "../exp580/build/exp580/architecture-resolver.o",
        "../exp579/build/exp579/arch-text.o", "-o", str(BUILD / "parser-test")]
    speed.measured(command, "compile-test")
    speed.measured([str(BUILD / "parser-test"), "../exp652/doc/eda比赛文件/arch"], "parser-test")
    tests = read(ROOT / "parser-test.stdout")
    assert tests["all_equal"] and tests["ports"] == 496
    source = read("../exp703/validation/results/exp703/freeze.json")
    request = check(source["input"]["path"], source["input"])
    reference = Path("../exp703/build/exp703/warmup.csv")
    expected = source["expected_output"]
    check(reference, expected)
    write(ROOT / "freeze.json", dict(sources=sources, input=request, reference=identity(reference),
        binaries={a: identity(p) for a, p in BINS.items()}, expected_output=expected,
        schedule=[["A", "C"], *[list(order) for order in itertools.islice(
            itertools.cycle((("A", "C"), ("C", "A"))), 6)]], component_check=tests,
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md",
                                     Path("tests/exp704_port_decoder.cpp"))],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP704_BUILT", identity(BINS["C"]), tests, flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for record in frozen["files"] + list(frozen["binaries"].values()) + [frozen["input"], frozen["reference"]]:
        check(record["path"], record)
    timings, runs, paused = dict(A=[], C=[]), [], []
    try:
        for p in Path("/proc").iterdir():
            if not p.name.isdigit():
                continue
            try:
                args = (p / "cmdline").read_bytes().split(b"\0")
                if args and args[0] == b"zstd" and b"research/exp688/build/exp688/1b.csv" in args:
                    assert (p / "cwd").resolve() == Path("/home/lhj/lhjwork/eda2026")
                    pid = int(p.name)
                    os.kill(pid, signal.SIGSTOP)
                    paused.append(pid)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        write(ROOT / "archive-paused.json", dict(pids=paused))
        (ROOT / "processes-before.txt").write_text(subprocess.check_output(
            ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
        for iteration, order in enumerate(frozen["schedule"]):
            for arm in order:
                assert shutil.disk_usage(".").free > 4_500_000_000
                output = BUILD / f"100m-{iteration}-{arm}.csv"
                command = ["taskset", "-c", "8", str(BINS[arm]), "-in",
                           frozen["input"]["path"], "-out", str(output)]
                measured = speed.measured(command, output.stem)
                assert measured["threads"] == 1 and measured["rss_bytes"] <= 2_000_000_000
                assert measured["cpu_s"] < 100 and measured["wall_s"] <= 3600
                assert read(measured["stderr"]) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
                actual = check(output, frozen["expected_output"])
                record = dict(arm=arm, iteration=iteration, run=measured, output=actual)
                write(ROOT / f"{output.stem}-evidence.json", record)
                runs.append(record)
                if iteration:
                    timings[arm].append(measured["cpu_s"])
                write(ROOT / f"{output.stem}-cleanup.json", dict(file=actual,
                    retained=frozen["reference"], rebuild_command=command, deleted=True))
                output.unlink()
                print("EXP704_RUN", iteration, arm, measured["cpu_s"], flush=True)
    finally:
        for pid in paused:
            try:
                os.kill(pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        write(ROOT / "archive-resumed.json", dict(pids=paused))
    saved = [a - c for a, c in zip(timings["A"], timings["C"])]
    mean = statistics.mean(saved)
    width = 2.570581835636314 * statistics.stdev(saved) / len(saved) ** .5
    write(ROOT / "100m-report.json", dict(all_checks_passed=True, timings_s=timings,
        saved_s=mean, ci95_saved_s=[mean - width, mean + width],
        qualifies=bool(mean > 0 and mean - width > 0), practical_priority_target_s=.5,
        same_output_all_runs=True, accuracy_delta_pp=0, runs=runs,
        score_reused=identity("../exp685/validation/results/exp685/score/accuracy.json"),
        contract_reused=identity("../exp685/validation/results/exp685/100m-report.json"),
        complete_program_runs=len(runs), new_exact_rows=0, training_runs=0,
        removed_bytes=sum(r["output"]["bytes"] for r in runs),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP704_100M_COMPLETE", mean, [mean - width, mean + width], flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp704")
    assert sys.argv[1:] in (["build"], ["run"])
    dict(build=build, run=run)[sys.argv[1]]()
