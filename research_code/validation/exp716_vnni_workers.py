#!/usr/bin/env python3
"""Check and time whole-query VNNI workers with one generic shared asset."""
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp716"), Path("build/exp716")
PLAN = Path("experiment/实验716-共享资产的整查询EVEX与VNNI.md")
BASE = Path("../exp707")
read, write, identity, check = execution.read, execution.write, execution.identity, execution.check
measured, replace = execution.measured, execution.replace
execution.ROOT = ROOT
ISA = ["-mavx2", "-mavx512f", "-mavx512bw", "-mavx512vl", "-mavx512vnni"]


def worker(text, arm):
    if arm != "F":
        text = replace(text, "    initializeGeometry582();",
                       "    initializeGeometry582();\n    initializeSums716();")
    text = text.replace("707_M", "716_"+arm)
    kernel = "dot64_595(a,b)" if arm == "F" else "dot64_595(a,b,sum)"
    text += f"""
#ifdef EXP716_CHECK
extern "C" int kernel716_{arm}(const int8_t* a,const int8_t* b,int {'/*sum*/' if arm == 'F' else 'sum'}) {{
    return {kernel};
}}
#endif
"""
    if arm == "F":
        text += """
#ifdef EXP716_CHECK
extern "C" void factors716_F(unsigned group,unsigned block,const int8_t** a,const int8_t** b) {
    const auto& p=parts582[group];
    const unsigned local=block/p.blocks, at=block%p.blocks;
    const unsigned row=(block*2027u+17u)%(group ? 4*59904 : 59904);
    *a=p.left+uint64_t(row)*p.rank+64*at;
    *b=p.right+uint64_t(local)*p.rank+64*at;
}
#endif
"""
    return text


def build():
    assert not ROOT.exists() and not BUILD.exists()
    assert read("../exp715/validation/results/exp715/independent-audit.json")["all_checks_passed"]
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    previous = read(BASE/"validation/results/exp707/freeze.json")
    baseline = check(BASE/"build/exp707/M/estimate", previous["binaries"]["M"])
    original = BASE/"build/exp707/M"
    source_files = [s["current"] for s in previous["sources"]
                    if s["current"]["path"].startswith("build/exp707/M/")]
    header = original/"exp707_prepare_metadata.h"
    sources, commands, objects, checked = [], {}, [], []
    for arm, width in (("F", 0), ("V", 256), ("W", 512)):
        dest = BUILD/arm
        dest.mkdir()
        for item in source_files:
            source = BASE/item["path"]
            check(source, item)
            text = source.read_text()
            if source.name == "worker.cpp":
                text = worker(text, arm)
            elif source.name == "exp652_geometry_restore.h":
                text = replace(text, "alignas(64) static unsigned char exp579_geometry[kGeometryBytes];",
                               "extern unsigned char exp579_geometry[kGeometryBytes];")
            elif source.name == "exp608_geometry.h" and arm != "F":
                tail = text[text.index("static inline double geometry("):]
                text = Path("tests/exp716_vnni_geometry.h").read_text()+"\n"+tail
            (dest/source.name).write_text(text)
            sources.append(identity(dest/source.name))
        shutil.copy2(header, dest/header.name)
        sources.append(identity(dest/header.name))
        command = [x.replace("build/exp707/M", str(dest)).replace(
            "-Dmain=worker608_F", "-Dmain=worker716_"+arm)
                   for x in previous["commands"]["M"]["compile"]]
        command += ["-fno-lto"] + (ISA+[f"-DEXP716_WIDTH={width}", f"-mprefer-vector-width={width}"]
                                  if width else [])
        measured(command, "compile-"+arm)
        obj = dest/"C.o"
        assert obj.exists()
        sections = subprocess.check_output(["readelf", "-SW", str(obj)], text=True)
        names = subprocess.check_output(["nm", "-C", str(obj)], text=True)
        assert all(x not in sections for x in (".init_array", ".ctors"))
        assert "_GLOBAL__sub_I" not in names
        (ROOT/(arm+"-sections.txt")).write_text(sections)
        (ROOT/(arm+"-symbols.txt")).write_text(names)
        objects.append(str(obj))
        audit = command.copy()
        audit[audit.index("-o")+1] = str(dest/"checked.o")
        measured(audit+["-DEXP707_CHECK", "-DEXP716_CHECK", "-DEXP579_AUDIT"],
                 "compile-check-"+arm)
        checked.append(str(dest/"checked.o"))
        commands[arm] = command
    entry = Path("../exp652/build/exp652/entry.cpp").read_text()
    entry = entry[:entry.index("int worker608_F(")] + """
alignas(64) unsigned char exp579_geometry[69303616];
alignas(64) int16_t sums716[298560];
int worker716_F(int,char**);
int worker716_V(int,char**);
int worker716_W(int,char**);
int main(int argc,char** argv) {
    __builtin_cpu_init();
    const bool vnni=__builtin_cpu_supports("avx2") && __builtin_cpu_supports("avx512f") &&
        __builtin_cpu_supports("avx512bw") && __builtin_cpu_supports("avx512vl") &&
        __builtin_cpu_supports("avx512vnni");
#if EXP716_CHOICE == 1
    if (vnni) { std::puts("{\\"worker716\\":\\"V256\\"}");return worker716_V(argc,argv); }
#elif EXP716_CHOICE == 2
    if (vnni) { std::puts("{\\"worker716\\":\\"V512\\"}");return worker716_W(argc,argv); }
#else
    (void)vnni;
#endif
    std::puts("{\\"worker716\\":\\"SSE2\\"}");return worker716_F(argc,argv);
}
"""
    (BUILD/"entry.cpp").write_text(entry)
    flags = ["-std=c++17", "-O3", "-fno-exceptions", "-fno-rtti", "-fno-fast-math",
             "-ffp-contract=off", "-fno-lto", "-march=x86-64", "-mtune=generic",
             "-Wall", "-Wextra", "-Werror", "-DDELAY_ESTIMATE_EMBEDDED_ARCH",
             "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE", "-I", "../exp589/src"]
    dependencies = ["../exp580/build/exp580/architecture-resolver.o",
        "../exp579/build/exp579/arch-text.o", "../exp654/build/exp654/codes.o",
        "../exp652/build/exp652/compressed.o", "../exp646/build/exp646/deps/libzstd.a"]
    binaries, links = {"A": baseline}, {}
    for arm, choice in (("F", 0), ("V", 1), ("W", 2)):
        program = BUILD/("estimate-"+arm)
        command = ["g++", str(BUILD/"entry.cpp"), *flags, f"-DEXP716_CHOICE={choice}", *objects,
            *dependencies, "-static", "-s", "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc",
            "-o", str(program)]
        measured(command, "link-"+arm)
        assert program.stat().st_size < 100_000_000
        assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(program)], text=True)
        assert "NEEDED" not in subprocess.check_output(["readelf", "-dW", str(program)], text=True)
        binaries[arm] = identity(program); links[arm] = command
    command = ["g++", *flags, "tests/exp716_isa_check.cpp", *checked, *dependencies,
               "-static", "-o", str(BUILD/"component-check")]
    measured(command, "link-check")
    Path("build/exp684/V8").mkdir(parents=True)
    measured([str(BUILD/"component-check"), "../exp705/build/exp705/queries.bin"], "component-check")
    component = read(ROOT/"component-check.stdout")
    assert component["all_equal"] and component["real_dots"] == 298560
    assert component["synthetic_dots"] == 165600 and component["corners"] == 99200
    schedule = [list(s) for s in ("AVW", "AVW", "WVA", "VAW", "WAV", "AWV", "VWA")]
    write(ROOT/"freeze.json", dict(binaries=binaries, commands=commands, links=links,
        sources=sources, dependencies=[identity(p) for p in dependencies],
        component=component, schedule=schedule,
        input=check(previous["input"]["path"], previous["input"]),
        reference=check("../exp703/build/exp703/warmup.csv", previous["expected_output"]),
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md",
               Path("tests/exp716_isa_check.cpp"), Path("tests/exp716_vnni_geometry.h"), BUILD/"entry.cpp")],
        cpuinfo=Path("/proc/cpuinfo").read_text().split("\n\n")[0],
        compiler=subprocess.check_output(["g++", "--version"], text=True),
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP716_BUILD_PASSED", component, flush=True)


def run():
    frozen = read(ROOT/"freeze.json")
    for item in frozen["files"] + frozen["sources"] + list(frozen["binaries"].values()) + [
            frozen["input"], frozen["reference"]]:
        check(item["path"], item)
    (ROOT/"processes-before.txt").write_text(subprocess.check_output(
        ["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"], text=True))
    timings, records = dict(A=[], V=[], W=[]), []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            assert shutil.disk_usage(".").free > 4_500_000_000
            output = BUILD/f"100m-{iteration}-{arm}.csv"
            assert not output.exists()
            command = ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                       "-in", frozen["input"]["path"], "-out", str(output)]
            result = measured(command, output.stem)
            assert result["threads"] == 1 and result["rss_bytes"] <= 300_000_000
            assert result["wall_s"] <= 3600 and result["cpu_s"] < 100
            assert read(ROOT/(output.stem+".stderr")) == dict(
                rows=100_000_000, unreachable=0, query_allocations=0)
            if arm != "A":
                assert read(ROOT/(output.stem+".stdout")) == dict(worker716="V256" if arm == "V" else "V512")
            actual = check(output, frozen["reference"])
            record = dict(iteration=iteration, arm=arm, run=result, output=actual)
            records.append(record);write(ROOT/(output.stem+"-evidence.json"), record)
            if iteration:
                timings[arm].append(result["cpu_s"])
            print("EXP716_REMOVE_DUPLICATE", output, flush=True)
            output.unlink()
            write(ROOT/(output.stem+"-cleanup.json"), dict(file=actual, retained=frozen["reference"],
                  rebuild_command=command, deleted=True))
            print("EXP716_RUN", iteration, arm, result["cpu_s"], flush=True)
    stats = {}
    for arm in ("V", "W"):
        differences = [a-b for a, b in zip(timings["A"], timings[arm])]
        mean = statistics.mean(differences)
        half = 3.163381449748624*statistics.stdev(differences)/math.sqrt(6)
        stats[arm] = dict(saved_s=mean, simultaneous_ci95_s=[mean-half, mean+half],
                          qualifies=mean >= .5 and mean-half > 0)
    eligible = [a for a in ("V", "W") if stats[a]["qualifies"]]
    selected = min(eligible, key=lambda a: statistics.mean(timings[a])) if eligible else "A"
    write(ROOT/"100m-report.json", dict(all_checks_passed=True, stats=stats, selected=selected,
        means_s={a: statistics.mean(v) for a, v in timings.items()}, timings_s=timings, runs=records,
        complete_outputs_identical=True, accuracy_delta_pp=0, new_exact_rows=0,
        exact_sample_rows=1_916_928, input_previously_observed=True,
        score_reused=identity("../exp685/validation/results/exp685/score/accuracy.json"),
        contract_reused=identity("../exp685/validation/results/exp685/100m-report.json"),
        removed_bytes=sum(r["output"]["bytes"] for r in records),
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP716_COMPLETE", selected, stats, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp716")
    assert sys.argv[1:] in (["build"], ["run"])
    dict(build=build, run=run)[sys.argv[1]]()
