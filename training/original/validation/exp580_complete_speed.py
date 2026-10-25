#!/usr/bin/env python3
"""Qualify fixed-model resolver/parser ablations using complete full-port inputs."""
import json
import math
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp580"), Path("build/exp580")
OLD = Path("../exp579")
ARMS = ("A", "R", "P", "RP")


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
    record = dict(command=command, exit_code=child.returncode,
                  cpu_s=usage.ru_utime + usage.ru_stime, wall_s=time.monotonic() - start,
                  rss_bytes=usage.ru_maxrss * 1024, threads=threads,
                  stderr=str(ROOT / (name + ".stderr")))
    write(ROOT / (name + ".run.json"), record)
    assert child.returncode == 0, record
    return record


def build():
    BUILD.mkdir(parents=True)
    plan = Path("experiment/实验580-完整候选的等价解析优化与规模验证.md")
    shutil.copyfile(plan, ROOT / "protocol-original.md")
    source = (OLD / "tests/exp579_complete_candidate.cpp").read_text()
    marker = "static delayest::Architecture arch;"
    assert source.count(marker) == 1
    source = source.replace(marker, marker + '\n#ifdef EXP580_PORT_PARSER\n#include "exp580_port_parser.h"\n#endif')
    marker = "    arch.loadEmbedded();"
    assert source.count(marker) == 1
    source = source.replace(marker, marker + """
#ifdef EXP580_PORT_PARSER
    initializePorts580();
#ifdef EXP580_VERIFY_PARSER
    verifyPorts580();
#endif
#endif
""")
    marker = "        if (arch.parsePin(from,q[0],q[1],q[8]) && arch.parsePin(to,q[2],q[3],q[9])) {"
    assert source.count(marker) == 1
    source = source.replace(marker, """#ifdef EXP580_PORT_PARSER
        if (parsePin580(from,q[0],q[1],q[8]) && parsePin580(to,q[2],q[3],q[9])) {
#else
""" + marker + "\n#endif")
    (BUILD / "candidate.cpp").write_text(source)
    common = ["g++", "-std=c++17", "-O3", "-fno-rtti", "-fno-fast-math", "-ffp-contract=off",
              "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
              "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-I", "src", "-I", "tests", "-I", str(OLD / "build/exp579")]
    measured(common + ["-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE", "-c", "src/architecture.cpp",
                       "-o", str(BUILD / "architecture-resolver.o")], "compile-resolver")
    for arm in ARMS[1:]:
        flags = (["-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE"] if "R" in arm else [])
        flags += (["-DEXP580_PORT_PARSER"] if "P" in arm else [])
        # The checked binary runs its parser self-check during a complete 1M run.
        variants = ((arm, []), (arm + "-checked", ["-DEXP580_VERIFY_PARSER"])) if arm == "RP" else ((arm, []),)
        for name, extra in variants:
            measured(common + ["-fno-exceptions", *flags, *extra, str(BUILD / "candidate.cpp"),
                     str(BUILD / "architecture-resolver.o") if "R" in arm else str(OLD / "build/exp579/architecture.o"),
                     str(OLD / "build/exp579/arch-text.o"), str(OLD / "build/exp579/geometry.o"),
                     "-static", "-s", "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc", "-o", str(BUILD / name)],
                     "compile-" + name)
            assert not (ROOT / ("compile-" + name + ".stderr")).read_bytes()
            assert (BUILD / name).stat().st_size < 100000000
    frozen = json.loads((OLD / "validation/results/exp579/report.json").read_text())
    assert frozen["cases"]["independent"]["quality_gate"]
    old = json.loads((OLD / "validation/results/exp579/candidate-freeze.json").read_text())
    assert identity(OLD / "build/exp579/estimate")["sha256"] == old["binary"]["sha256"]
    write(ROOT / "freeze.json", dict(protocol=identity(ROOT / "protocol-original.md"),
          model=old, binaries={a: identity(binary(a)) for a in ARMS},
          source=[identity(p) for p in (Path(__file__), BUILD / "candidate.cpp", Path("tests/exp580_port_parser.h"),
                                       Path("src/architecture.cpp"), Path("src/architecture.h"))],
          host=socket.gethostname(), compiler=subprocess.check_output(["g++", "--version"], text=True)))


def binary(arm):
    return OLD / "build/exp579/estimate" if arm == "A" else BUILD / arm


def qualify():
    results = {}
    for case, request in (("development", Path("../exp501/build/exp501/u-role/requests.csv")),
                          ("independent", Path("../exp562/build/exp562/u-role/requests.csv"))):
        prior = json.loads((OLD / f"validation/results/exp579/{case}-report.json").read_text())
        expected = prior["evidence"]["C"]["output"]
        actual_input = identity(request)
        assert actual_input["sha256"] == prior["evidence"]["C"]["input"]["sha256"]
        schedule = [ARMS, *(list((ARMS, tuple(reversed(ARMS)))) * 3)]
        runs, times = [], {a: [] for a in ARMS}
        if case == "development":
            checked = BUILD / "parser-self-check.csv"
            record = measured([str(BUILD / "RP-checked"), "-in", str(request), "-out", str(checked)], "parser-self-check")
            check_run(record, checked, expected)
        for iteration, order in enumerate(schedule):
            for arm in order:
                output = BUILD / f"{case}-{iteration}-{arm}.csv"
                record = measured([str(binary(arm)), "-in", str(request), "-out", str(output)],
                                  f"{case}-{iteration}-{arm}")
                check_run(record, output, expected)
                record.update(arm=arm, iteration=iteration, input=actual_input)
                runs.append(record)
                if iteration:
                    times[arm].append(record["cpu_s"])
                print("EXP580_COMPLETE_RUN", case, iteration, arm, record["cpu_s"], flush=True)
        stats = {}
        for arm in ARMS[1:]:
            saved = [a-b for a, b in zip(times["A"], times[arm])]
            mean = statistics.mean(saved)
            width = 2.570581835636314 * statistics.stdev(saved) / math.sqrt(6)
            stats[arm] = dict(saved_cpu_s=mean, ci95_saved_s=[mean-width, mean+width],
                              speed_gate=mean >= .01 and mean-width > 0)
        results[case] = dict(runs=runs, timing_s=times, stats=stats, exact_output_equivalence=True,
                             complete_contract_reused_from=identity(OLD / f"validation/results/exp579/{case}-report.json"))
        write(ROOT / f"{case}-report.json", results[case])
    eligible = [a for a in ARMS[1:] if all(r["stats"][a]["speed_gate"] for r in results.values())]
    selected = min(eligible, key=lambda a: sum(statistics.mean(r["timing_s"][a]) for r in results.values())) if eligible else "A"
    write(ROOT / "report.json", dict(cases=results, selected=selected, selected_binary=identity(binary(selected))))
    print("EXP580_SELECTED", selected, flush=True)


def check_run(record, output, expected):
    assert record["threads"] == 1 and record["rss_bytes"] <= 2000000000 and record["cpu_s"] <= 3600
    actual = identity(output)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), (actual, expected)
    counter = json.loads(Path(record["stderr"]).read_text())
    assert counter["query_allocations"] == 0 and counter["rows"] == 1000000
    # Equal complete SHA reuses the already checked row, endpoint, EOF and delay contract.
    record.update(output=actual, equivalent_to=expected, rebuild_command=record["command"])
    write(ROOT / (output.stem + "-equivalence.json"), record)
    output.unlink()


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp580")
    ROOT.mkdir(parents=True, exist_ok=True)
    assert sys.argv[1:] in (["build"], ["qualify"])
    (build if sys.argv[1] == "build" else qualify)()


if __name__ == "__main__":
    main()
