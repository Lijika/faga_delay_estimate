#!/usr/bin/env python3
"""Compile one-variable tree decisions and reuse the frozen paired run protocol."""
import ast
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path("../exp723/validation").resolve()))
import exp723_fused_csv as timing

execution = timing.execution
read, write, identity, check = timing.read, timing.write, timing.identity, timing.check
ROOT, BUILD = Path("validation/results/exp727"), Path("build/exp727")
PLAN = Path("experiment/实验727-固定树一元判定的坐标掩码编译.md")
BASE = Path("../exp723")
DOMAINS = dict(sx=(0, 120), sy=(0, 550), ax=(0, 120), ay=(0, 550),
               tx=(0, 120), ty=(0, 550), x=(-119, 120), y=(-549, 550))
execution.ROOT = ROOT


def generate(worker, original):
    parser = Path("../exp622/validation/exp622_r8_specialization.py")
    tree = ast.parse(parser.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "feature_list")
    scope = dict(re=re)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(parser), "exec"), scope)
    _, fields = scope["feature_list"](worker)
    assert original.count("double symmetric640(") == 1
    (BUILD/"reference727.h").write_text(original.replace("double symmetric640(", "double reference727("))
    declarations, cases, checks, records = [], [], [], []
    table_bytes, table_entries, compiled_splits = 0, 0, 0
    training = read("../exp720/validation/results/exp720/final-training.json")
    for record in training["records"]:
        route = record["route"]
        path = Path("../exp720")/record["model"]["path"]
        check(path, record["model"])
        model = read(path)
        assert model["scale_and_bias"] == [1, [0]] and len(model["oblivious_trees"]) == 2
        mapping = {f["feature_index"]: f["flat_feature_index"] for f in model["features_info"]["float_features"]}
        groups, rest, active, occupied = {}, [], set(), 0
        for t, tree in enumerate(model["oblivious_trees"]):
            assert len(tree["splits"] or []) <= 6
            for j, split in enumerate(tree["splits"] or []):
                f = mapping[split["float_feature_index"]]
                cut = int(split["border"] // 1)+1
                bit = 6*t+j
                assert not occupied & (1 << bit)
                occupied |= 1 << bit
                active.add(f)
                variables = set(re.findall(r"\b(?:sx|sy|ax|ay|tx|ty|x|y|sf|sl|tf|tl|ndx|ndy|fee|forced)\b",
                                          fields[f]))
                if len(variables) == 1 and next(iter(variables)) in DOMAINS:
                    groups.setdefault(next(iter(variables)), []).append((f, cut, bit))
                else:
                    rest.append((f, cut, bit))
        terms = []
        for variable, splits in groups.items():
            low, end = DOMAINS[variable]
            name = f"kMask727_{route}_{variable}"
            values = []
            for z in range(low, end):
                mask = 0
                for f, cut, bit in splits:
                    expression = fields[f].replace("std::abs", "abs").replace("/", "//")
                    value = eval(expression, {"__builtins__": {}},
                        {variable: z, "abs": abs, "mod": lambda a, b: a % b,
                         "side": lambda a: 0 if a < 76 else 1 if a < 90 else 2})
                    assert isinstance(value, (int, bool))
                    mask |= int(value >= cut) << bit
                values.append(mask)
            declarations.append(f"static constexpr uint16_t {name}[]={{"+",".join(map(str, values))+"};")
            terms.append(f"{name}[{variable}{'+'+str(-low) if low < 0 else ''}]")
            direct = "|".join(f"(unsigned(({fields[f]})>={cut})<<{bit})" for f, cut, bit in splits)
            checks.append(f"for(int {variable}={low};{variable}<{end};++{variable}) {{"
                f"require({terms[-1]}==({direct}),\"coordinate mask\"); ++count; }}")
            table_bytes += 2*len(values)
            table_entries += len(values)
            compiled_splits += len(splits)
        terms += [f"(unsigned(({fields[f]})>={cut})<<{bit})" for f, cut, bit in rest]
        assert occupied == (1 << 12)-1
        cases.append(f"case {route}: {{")
        for f in sorted(active):
            cases.append(f'if(expected) require(({fields[f]})==expected[{f}],"mask active feature");')
        cases += ["const unsigned bits="+"|".join(terms)+";",
                  "const unsigned p0=bits&63,p1=bits>>6;",
                  f"double result=0.; result+=kLeaves720[{route}][0][p0];",
                  f"result+=kLeaves720[{route}][1][p1];",
                  "if(leaves) { leaves[0]=p0; leaves[1]=p1; }", "return result;", "}"]
        records.append(dict(route=route, groups={k: v for k, v in groups.items()},
                            scalar_splits=rest, table_loads=len(groups), model=identity(path)))
    assert table_bytes <= 128*1024 and len(records) == 16
    text = ["#pragma once", '#include "reference727.h"', *declarations,
        "static inline __attribute__((always_inline)) double symmetric640(",
        "const int32_t* q,[[maybe_unused]] int ax,[[maybe_unused]] int ay,",
        "[[maybe_unused]] int ndx,[[maybe_unused]] int ndy,int x,int y,",
        "[[maybe_unused]] int fee,[[maybe_unused]] bool forced,unsigned route,unsigned fold,",
        "unsigned char* leaves=nullptr,const int* expected=nullptr) {",
        "if(fold) return reference727(q,ax,ay,ndx,ndy,x,y,fee,forced,route,fold,leaves,expected);",
        "[[maybe_unused]] const int sx=q[0],sy=q[1],tx=q[2],ty=q[3];",
        "[[maybe_unused]] const int sf=q[4],sl=q[5],tf=q[6],tl=q[7];",
        "switch(route) {", *cases, 'default: require(false,"coordinate mask route"); return 0.;', "}", "}",
        "#ifdef EXP727_CHECK", "static uint64_t checkTables727() { uint64_t count=0;",
        *checks, "return count; }", "#endif", ""]
    (BUILD/"symmetric640.h").write_text("\n".join(text))
    write(ROOT/"tables.json", dict(table_bytes=table_bytes, table_entries=table_entries,
        compiled_splits=compiled_splits, total_splits=192, records=records,
        table_domains=DOMAINS, generator=identity(__file__)))


def build():
    assert read("../exp725/validation/results/exp725/independent-audit.json")["all_checks_passed"]
    assert not ROOT.exists() and not BUILD.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    old = read(BASE/"validation/results/exp723/freeze.json")
    check(BASE/"build/exp723/estimate", old["binaries"]["C"])
    sources = []
    for entry in old["sources"]:
        item = entry["current"]
        source, destination = BASE/item["path"], BUILD/Path(item["path"]).name
        check(source, item)
        shutil.copy2(source, destination)
        sources.append(identity(source))
    extra = BASE/"build/exp723/exp723_fused_parse.h"
    expected = next(v for v in old["files"] if v["path"] == "tests/exp723_fused_parse.h")
    check(extra, expected)
    shutil.copy2(extra, BUILD/extra.name)
    generate((BUILD/"worker.cpp").read_text(), (BUILD/"symmetric640.h").read_text())
    command = ["g++", "-std=c++17", "-O3", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
               "-ffp-contract=off", "-march=x86-64", "-mtune=generic", "-static",
               "-I", str(BUILD), "tests/exp727_coordinate_masks.cpp", "-o", str(BUILD/"component")]
    execution.measured(command, "compile-component")
    execution.measured([str(BUILD/"component")], "component")
    component, tables = read(ROOT/"component.stdout"), read(ROOT/"tables.json")
    assert component["all_equal"] and component["table_entries"] == tables["table_entries"]
    assert component["query_checks"] == 3_200_000 and component["leaf_combinations"] == 65_536
    commands = [[s.replace("build/exp723", str(BUILD)) for s in cmd] for cmd in old["commands"]]
    for name, cmd in zip(("compile", "link"), commands):
        execution.measured(cmd, name)
        assert not (ROOT/(name+".stderr")).read_bytes()
    binary = BUILD/"estimate"
    assert binary.stat().st_size < 100_000_000
    assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    assert "(NEEDED)" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    request, reference = (check(v["path"], v) for v in (old["input"], old["reference"]))
    write(ROOT/"freeze.json", dict(sources=sources, commands=commands, input=request, reference=reference,
        binaries=dict(A=identity(BASE/"build/exp723/estimate"), C=identity(binary)),
        component=component, schedule=old["schedule"], tables=tables,
        score_reused=old["score_reused"], contract_reused=old["contract_reused"],
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/"protocol-original.md",
            Path("tests/exp727_coordinate_masks.cpp"), Path(timing.__file__),
            *[p for p in BUILD.iterdir() if p.suffix in (".h", ".cpp")])],
        disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP727_BUILD_PASSED", identity(binary), component, tables["table_bytes"], flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp727")
    assert sys.argv[1:] in (["build"], ["run"])
    if sys.argv[1] == "build":
        build()
    else:
        timing.ROOT, timing.BUILD = ROOT, BUILD
        timing.run()
