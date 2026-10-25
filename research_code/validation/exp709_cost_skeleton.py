#!/usr/bin/env python3
"""Measure complete CSV skeletons without treating fixed output as accuracy."""
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(Path("../exp580/validation").resolve()))
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp709"), Path("build/exp709")
PLAN = Path("experiment/实验709-完整100M公共处理骨架与预测成本.md")
BASE = Path("../exp707")
ARMS = ("I", "P", "G", "F")


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    return actual


def measured(command, name):
    start = time.monotonic()
    with (ROOT / (name + ".stdout")).open("xb") as out, (ROOT / (name + ".stderr")).open("xb") as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        threads = 0
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            try:
                threads = max(threads, len(list(Path(f"/proc/{child.pid}/task").iterdir())))
            except FileNotFoundError:
                pass
            time.sleep(.001)
        child.returncode = os.waitstatus_to_exitcode(status)
    result = dict(command=command, exit_code=child.returncode, user_s=usage.ru_utime,
        sys_s=usage.ru_stime, cpu_s=usage.ru_utime + usage.ru_stime,
        wall_s=time.monotonic() - start, rss_bytes=usage.ru_maxrss * 1024, threads=threads)
    write(ROOT / (name + ".run.json"), result)
    assert child.returncode == 0, result
    return result


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def worker(text, arm):
    # All skeletons retain the same asset recovery and output implementation.
    for name in ("symmetric640.h", "replacement679.h", "exp679_hv_events.h"):
        text = replace(text, '#include "' + name + '"\n', "")
    text = replace(text, "const int32_t* q, unsigned fold, Prepared596& state",
                   "const int32_t* q, unsigned, Prepared596& state")
    text = replace(text, "    const unsigned route=4*direction+2*(bx>=20)+(by>=24);\n", "")
    begin = text.index("    _mm_prefetch(reinterpret_cast<const char*>(center + pair)")
    end = text.index("    const int mandatory=", begin)
    text = text[:begin] + text[end:]
    begin = text.index("#if defined(EXP581_INTEGER) || defined(EXP594_PACKED)",
                       text.index("static inline void prepare596"))
    end = text.index("    state.pair=", begin)
    text = text[:begin] + "    const double raw=forced;\n" + text[end:]
    begin = text.index("static inline int finish596(")
    end = text.index("\nstatic inline int predict(", begin)
    text = text[:begin] + """static inline int finish596(const Prepared596&, Trace* = nullptr) {
    return 1234;
}
""" + text[end:]
    text = replace(text, "uint64_t rows=0, unreachable=0;", "uint64_t rows=0, unreachable=0, checksum709=0;")
    if arm == "I":
        begin = text.index("            int32_t q[10]{};", text.index('require(reader.next(text)'))
        end = text.index("        for (size_t i=0;i<count;++i) {\n            const int answer=", begin)
        text = text[:begin] + "            }\n" + text[end:]
        text = replace(text, "        Prepared596 states[EXP596_BATCH];", "")
        text = replace(text, "const int answer=finish596(states[i]);", "const int answer=1234;")
    elif arm == "P":
        text = replace(text, "                    prepare596(q,0,states[i]);", """
                    require(arch.exists(q[0],q[1]) && arch.exists(q[2],q[3]),"skeleton endpoint");
                    checksum709+=uint64_t(q[0]+q[1]+q[2]+q[3]+q[8]+q[9]);
""")
    elif arm == "G":
        text = replace(text, "                    prepare596(q,0,states[i]);", """
                    prepare596(q,0,states[i]);
                    const auto& s709=states[i];
                    checksum709+=uint64_t(s709.pair+s709.context+s709.qx+s709.qy+
                        s709.fee+s709.mandatory+s709.cycle+(s709.dy<0)+
                        s709.override_cycle+s709.ready+int(s709.raw));
""")
    else:
        raise AssertionError(arm)
    text = replace(text, '    require(allocations==0,"query heap allocation");',
        '    require(allocations==0,"query heap allocation");\n'
        '    std::printf("{\\"checksum\\":%llu}\\n",(unsigned long long)checksum709);')
    return text.replace("707_M", "707_G")


def build():
    assert not BUILD.exists() and not ROOT.exists()
    assert read("../exp708/validation/results/exp708/1b-report.json")["all_checks_passed"]
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT / "protocol-original.md")
    previous = read(BASE / "validation/results/exp707/freeze.json")
    assert read(BASE / "validation/results/exp707/100m-report.json")["selected"] == "M"
    inputs, commands, binaries = [], {}, {"F": check(BASE / "build/exp707/M/estimate", previous["binaries"]["M"])}
    sources = [s["current"] for s in previous["sources"] if s["current"]["path"].startswith("build/exp707/M/")]
    for arm in ARMS[:3]:
        directory = BUILD / arm
        directory.mkdir()
        for item in sources:
            original = BASE / item["path"]
            check(original, item)
            dest = directory / original.name
            if original.name == "worker.cpp":
                dest.write_text(worker(original.read_text(), arm))
            else:
                shutil.copy2(original, dest)
            inputs.append(identity(dest))
        header = BASE / "build/exp707/M/exp707_prepare_metadata.h"
        shutil.copy2(header, directory / header.name)
        inputs.append(identity(directory / header.name))
        commands[arm] = {kind: [x.replace("build/exp707/M", str(directory)) for x in cmd]
                         for kind, cmd in previous["commands"]["M"].items()}
        measured(commands[arm]["compile"], "compile-" + arm)
        measured(commands[arm]["link"], "link-" + arm)
        program = directory / "estimate"
        assert program.stat().st_size < 100_000_000
        assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(program)], text=True)
        binaries[arm] = identity(program)
    checked = [x.replace("-Dmain=worker608_F", "-Dmain=worker709_G")
               for x in commands["G"]["compile"]]
    checked[checked.index("-o") + 1] = str(BUILD / "checked.o")
    measured(checked + ["-DEXP707_CHECK"], "compile-check")
    command = ["g++", "-std=c++17", "-O2", "-I", "../exp589/src",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
        "tests/exp709_prepare_check.cpp", str(BASE / "build/exp707/M/checked.o"),
        str(BUILD / "checked.o"),
        "../exp580/build/exp580/architecture-resolver.o", "../exp579/build/exp579/arch-text.o",
        "../exp654/build/exp654/codes.o", "../exp652/build/exp652/compressed.o",
        "../exp646/build/exp646/deps/libzstd.a", "-static", "-o", str(BUILD / "component-check")]
    measured(command, "link-check")
    measured([str(BUILD / "component-check"), "../exp705/build/exp705/queries.bin"], "component-check")
    assert read(ROOT / "component-check.stdout")["all_equal"]
    write(ROOT / "freeze.json", dict(binaries=binaries, commands=commands,
        input=check(previous["input"]["path"], previous["input"]), expected_full=previous["expected_output"],
        schedule=[list(ARMS), *[list(ARMS[i:] + ARMS[:i]) for i in range(4)]],
        sources=inputs, files=[identity(p) for p in (Path(__file__), PLAN, ROOT / "protocol-original.md",
            Path("tests/exp709_prepare_check.cpp"))], disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP709_BUILD_PASSED", flush=True)


def run():
    frozen = read(ROOT / "freeze.json")
    for item in frozen["files"] + list(frozen["binaries"].values()) + [frozen["input"]]:
        check(item["path"], item)
    checker = (Path("../exp685") / read("../exp685/validation/results/exp685/A-contract.run.json")["command"][0]).resolve()
    check(checker, read("../exp685/validation/results/exp685/freeze.json")["checker"])
    positions = BUILD / "contract-positions.txt"
    positions.write_text("0\n99999999\n")
    runs, times, checksums, reference = [], {a: [] for a in ARMS}, {}, None
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            assert shutil.disk_usage(".").free > 4_500_000_000
            output = BUILD / f"100m-{iteration}-{arm}.csv"
            assert not output.exists()
            command = ["taskset", "-c", "8", frozen["binaries"][arm]["path"],
                       "-in", frozen["input"]["path"], "-out", str(output)]
            result = measured(command, output.stem)
            assert result["threads"] == 1 and result["rss_bytes"] <= 2_000_000_000 and result["wall_s"] <= 3600
            assert read(ROOT / (output.stem + ".stderr")) == dict(
                rows=100_000_000, unreachable=0, query_allocations=0)
            actual = identity(output)
            if arm != "F":
                checksum = read(ROOT / (output.stem + ".stdout"))["checksum"]
                if arm in checksums:
                    assert checksums[arm] == checksum
                checksums[arm] = checksum
                if reference is None:
                    measured([str(checker), "check", frozen["input"]["path"], str(output),
                              "100000000", str(positions), str(BUILD / "sample.csv")], "contract")
                    contract = read(ROOT / "contract.stdout")
                    assert contract["contract_passed"] and contract["rows"] == 100_000_000
                    reference = actual
                else:
                    check(output, reference)
            else:
                check(output, frozen["expected_full"])
            record = dict(arm=arm, iteration=iteration, run=result, output=actual)
            runs.append(record)
            write(ROOT / (output.stem + "-evidence.json"), record)
            if iteration:
                times[arm].append(result["cpu_s"])
            retained = (BASE / "../exp703/build/exp703/warmup.csv") if arm == "F" else Path(reference["path"])
            if output != retained:
                expected = frozen["expected_full"] if arm == "F" else reference
                check(retained, expected)
                print("EXP709_REMOVE_DUPLICATE", output, flush=True)
                output.unlink()
                write(ROOT / (output.stem + "-cleanup.json"), dict(file=actual,
                    retained=identity(retained), rebuild_command=command, deleted=True))
            print("EXP709_RUN", iteration, arm, result["cpu_s"], flush=True)
    write(ROOT / "report.json", dict(all_checks_passed=True, diagnostic_only=True, runs=runs,
        times_s=times, means_s={a: statistics.mean(v) for a, v in times.items()},
        stdev_s={a: statistics.stdev(v) for a, v in times.items()},
        paired_deltas_s={b+"-"+a: [y-x for x, y in zip(times[a], times[b])]
                         for a, b in zip(ARMS[:-1], ARMS[1:])},
        checksums=checksums, diagnostic_reference=reference, contract=contract,
        score_claim=False, input_previously_observed=True,
        disk_free_end_bytes=shutil.disk_usage(".").free))
    print("EXP709_COMPLETE", {a: statistics.mean(v) for a, v in times.items()}, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp709")
    assert sys.argv[1:] in (["build"], ["run"])
    dict(build=build, run=run)[sys.argv[1]]()
