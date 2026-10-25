#!/usr/bin/env python3
"""Fuse canonical row framing with pin parsing; retain the frozen slow reader."""
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
ROOT, BUILD = Path("validation/results/exp723"), Path("build/exp723")
PLAN = Path("experiment/实验723-规范请求行扫描与双端点解析融合.md")
BASE = Path("../exp720")
execution.ROOT = ROOT
replace = execution.replace


def reader(text):
    start = text.index("    size_t nextBatch(")
    end = text.index("\n private:", start)
    return text[:start]+"""    bool nextParsed(std::string_view& line, int32_t* q, bool first, bool& parsed) {
        parsed=false;
        const char* begin=buffer_.data()+pos_;
        const char* end=buffer_.data()+filled_;
        size_t consumed=0;
        if (row723(begin,end,q,consumed)) {
            line=std::string_view(begin,consumed-1);
            pos_+=consumed;
            parsed=true;
        } else if (first) {
            return next(line);
        } else {
            const char* nl=static_cast<const char*>(std::memchr(begin,'\\n',size_t(end-begin)));
            if (!nl) return false;
            line=std::string_view(begin,size_t(nl-begin));
            pos_=size_t(nl-buffer_.data())+1;
            if (!line.empty() && line.back()=='\\r') line.remove_suffix(1);
        }
#ifdef EXP591_VERIFY_READER
        require(reference_.next(reference_line_) && line==reference_line_, "parsed reader mismatch");
#endif
        return true;
    }
""" + text[end:]


def worker(text):
    text = replace(text, '#include "exp596_csv_batch.h"\n', "")
    text = replace(text, '#include "exp601_port_parser.h"\n#endif',
                   '#include "exp601_port_parser.h"\n#endif\n'
                   '#include "exp723_fused_parse.h"\n#include "exp596_csv_batch.h"')
    start = text.index("    for (;;) {\n        const size_t count=reader.nextBatch")
    end = text.index("                const auto& s=ports707", start)
    text = text[:start]+"""    for (;;) {
        Prepared596 states[EXP596_BATCH];
        size_t count=0;
        for (;count<EXP596_BATCH;++count) {
            int32_t q[10]{};
            bool parsed;
            if (!reader.nextParsed(lines[count],q,count==0,parsed)) break;
            if (!parsed) {
                const auto text=lines[count];
                const size_t comma=text.find(',');
                require(comma!=std::string::npos && text.find(',',comma+1)==std::string::npos,"two input fields");
                const auto from=delayest::trimView(text.substr(0,comma));
                const auto to=delayest::trimView(text.substr(comma+1));
                parsed=parsePin580(from,q[0],q[1],q[8]) && parsePin580(to,q[2],q[3],q[9]);
            }
            if (parsed) {
""" + text[end:]
    text = replace(text, "        for (size_t i=0;i<count;++i) {\n            const int answer=",
                   "        if (!count) break;\n        for (size_t i=0;i<count;++i) {\n            const int answer=")
    text = replace(text, "prepare596(q,0,states[i]);", "prepare596(q,0,states[count]);")
    return text


def local_component():
    assert Path.cwd() == Path("/home/lhjysyx/EDA2026")
    folder = BUILD/"local"
    assert not folder.exists()
    folder.mkdir(parents=True)
    source = Path("/home/lhjysyx/faga_delay_estimate_exp688/source")
    original = source/"include/exp596_csv_batch.h"
    (folder/"reader723.h").write_text(reader(original.read_text()))
    shutil.copy2(original, folder/"original_reader.h")
    shutil.copy2("build/exp707/local/M/exp601_port_parser.h", folder/"exp601_port_parser.h")
    ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", str(source/"src"), "-I", str(folder), "-I", "tests",
        "tests/exp723_fused_csv.cpp", str(source/"src/architecture.cpp"),
        "-o", str(folder/"component")]
    execution.measured(command, "local-compile")
    execution.measured([str(folder/"component"), str(source/"arch"), str(folder)], "local-component")
    result = read(ROOT/"local-component.stdout")
    assert result["all_equal"] and result["guard_pages_passed"]
    write(ROOT/"local-check.json", dict(result=result, command=command,
        files=[identity(p) for p in (Path(__file__), PLAN, Path("tests/exp723_fused_parse.h"),
                                     Path("tests/exp723_fused_csv.cpp"), original)],
        algorithm_runs=0, performance_claim=False))
    print("EXP723_LOCAL_COMPONENT", result, flush=True)


def build():
    assert read("../exp722/validation/results/exp722/1b-decision.json")["quality_gate"]
    assert not BUILD.exists()
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    old = read(BASE/"validation/results/exp720/build-freeze.json")
    check(BASE/"build/exp720/estimate", old["binaries"]["C"])
    sources = []
    for item in old["files"]:
        path = Path(item["path"])
        if path.parent != Path("build/exp720") or path.suffix not in (".h", ".cpp"):
            continue
        source, destination = BASE/path, BUILD/path.name
        check(source, item)
        if path.name == "worker.cpp":
            destination.write_text(worker(source.read_text()))
        elif path.name == "exp596_csv_batch.h":
            shutil.copy2(source, BUILD/"original_reader.h")
            destination.write_text(reader(source.read_text()))
            shutil.copy2(destination, BUILD/"reader723.h")
        else:
            shutil.copy2(source, destination)
        sources.append(dict(original=identity(source), current=identity(destination)))
    shutil.copy2("tests/exp723_fused_parse.h", BUILD/"exp723_fused_parse.h")
    commands = []
    for stage in ("compile", "link"):
        command = [v.replace("build/exp720", str(BUILD)) for v in old[stage+"_command"]]
        commands.append(command)
        execution.measured(command, stage)
        assert not (ROOT/(stage+".stderr")).read_bytes()
    binary = BUILD/"estimate"
    assert binary.stat().st_size < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
        "-march=x86-64", "-mtune=generic", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "-I", "../exp589/src", "-I", str(BUILD), "-I", "tests", "tests/exp723_fused_csv.cpp",
        "../exp580/build/exp580/architecture-resolver.o", "../exp579/build/exp579/arch-text.o",
        "-o", str(BUILD/"component")]
    execution.measured(command, "compile-component")
    execution.measured([str(BUILD/"component"), "../exp652/doc/eda比赛文件/arch", str(BUILD)], "component")
    component = read(ROOT/"component.stdout")
    assert component["all_equal"] and component["guard_pages_passed"]
    prior = read(BASE/"validation/results/exp720/100m-report.json")
    request = check(BASE/prior["input"]["path"], prior["input"])
    reference = prior["evidence"]["C"]
    retained = check(BASE/reference["output"]["path"], reference["output"])
    write(ROOT/"freeze.json", dict(
        sources=sources, commands=commands, input=request, reference=retained,
        binaries=dict(A=identity(BASE/"build/exp720/estimate"), C=identity(binary)),
        component=component, schedule=[list(s) for s in ("AC", "AC", "CA", "AC", "CA", "AC", "CA")],
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md",
            Path("tests/exp723_fused_parse.h"), Path("tests/exp723_fused_csv.cpp"))],
        score_reused=identity(BASE/"validation/results/exp720/score/accuracy.json"),
        contract_reused=reference["contract"], disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP723_BUILD_PASSED", identity(binary), component, flush=True)


def run():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["files"]+list(frozen["binaries"].values())+[frozen["input"], frozen["reference"]]:
        check(item["path"], item)
    write(ROOT/"timing-freeze.json", dict(freeze=identity(ROOT/"freeze.json"), cpu=8,
        minimum_saved_s=.5, confidence=.95, input_previously_observed=True,
        process_snapshot=subprocess.check_output(["ps", "-eo", "pid,etimes,pcpu,stat,args",
                                                 "--sort=-pcpu"], text=True)))
    timing, runs = dict(A=[], C=[]), []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            assert shutil.disk_usage(".").free > 4_500_000_000
            output = BUILD/f"100m-{iteration}-{arm}.csv"
            assert not output.exists()
            command = ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                       "-in", frozen["input"]["path"], "-out", str(output)]
            run = execution.measured(command, output.stem)
            assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
            assert run["cpu_s"] < 100 and run["wall_s"] <= 3600
            assert read(ROOT/(output.stem+".stderr")) == dict(rows=100_000_000, unreachable=0, query_allocations=0)
            actual = check(output, frozen["reference"])
            record = dict(arm=arm, iteration=iteration, run=run, output=actual)
            write(ROOT/(output.stem+"-evidence.json"), record)
            runs.append(record)
            if iteration:
                timing[arm].append(run["cpu_s"])
            write(ROOT/(output.stem+"-cleanup.json"), dict(file=actual,
                retained=frozen["reference"], rebuild_command=command))
            print("EXP723_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
            output.unlink()
            print("EXP723_TIMING", iteration, arm, run["cpu_s"], flush=True)
    saved = [a-c for a, c in zip(timing["A"], timing["C"])]
    mean = statistics.mean(saved)
    half = 2.570581835636314*statistics.stdev(saved)/len(saved)**.5
    write(ROOT/"100m-report.json", dict(all_checks_passed=True, timing=timing,
        saved_s=mean, ci95_saved_s=[mean-half, mean+half], selected=mean >= .5 and mean-half > 0,
        runs=runs, accuracy_delta_pp=0, complete_outputs_identical=True, exact_sample_rows=1_916_928,
        new_exact_rows=0, score_reused=frozen["score_reused"], contract_reused=frozen["contract_reused"],
        released_duplicate_bytes=sum(r["output"]["bytes"] for r in runs),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP723_COMPLETE", mean, [mean-half, mean+half], flush=True)


if __name__ == "__main__":
    assert sys.argv[1:] in (["local"], ["build"], ["run"])
    if sys.argv[1] == "local":
        local_component()
    else:
        assert socket.gethostname() == "lhj-R4900-G3"
        assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp723")
        dict(build=build, run=run)[sys.argv[1]]()
