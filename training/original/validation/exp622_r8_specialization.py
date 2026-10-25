#!/usr/bin/env python3
"""Specialize the unchanged R8 on the current frozen Q4 complete program."""
import csv
import math
from pathlib import Path
import re
import shutil
import socket
import statistics
import subprocess
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path("../exp620/validation").resolve()))
import exp620_frozen_q4 as prior

ROOT, BUILD = Path("validation/results/exp622"), Path("build/exp622")
PLAN = Path("experiment/实验622-当前Q4路径的固定R8专门化.md")
OLD = Path("../exp619")
ARMS = ("A", "D", "T")
read, write, identity, check = prior.read, prior.write, prior.identity, prior.check
speed = prior.speed
speed.ROOT = ROOT
BINARIES = {a: BUILD / a for a in ARMS}
BINARIES["A"] = OLD / "build/exp619/Q4"


def replace(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def feature_list(source):
    body = re.search(r"const int feature\[53\]=\{(.*?)\};", source, re.S).group(1)
    items, start, depth = [], 0, 0
    for i, char in enumerate(body):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            items.append(body[start:i].strip())
            start = i + 1
    items.append(body[start:].strip())
    assert len(items) == 53 and depth == 0
    return body, items


def model_rows():
    path = Path("../exp589/build/exp589/D64-assets/exp579-models.h")
    rows = re.findall(r"^\{\{([^\n]+?)\},\{([^\n]+?)\},\{([^\n]+?)\}\},$",
                      path.read_text(), re.M)
    assert len(rows) == 64
    result = []
    for feature, threshold, value in rows:
        f, t = list(map(int, feature.split(","))), list(map(int, threshold.split(",")))
        v = value.split(",")
        assert len(f) == len(t) == 120 and len(v) == 128
        assert all(0 <= x < 53 for x in f)
        result.append((f, t, v))
    for route, (f, t, v) in enumerate(result[:16]):
        expected = prior.complete.expanded(Path("../exp579/build/exp579") / f"R8-final-{route}.json")
        assert np.array_equal(f, expected[0]) and np.array_equal(t, expected[1])
        values = np.asarray([float.fromhex(s[:-1]) for s in v], dtype="<f4")
        assert np.array_equal(values.view("u4"), expected[2].view("u4"))
    return result, path


def emit_native(models, features):
    out = [
        "#pragma once",
        "static inline __attribute__((always_inline)) float native622(",
        "    const int32_t* q,int ax,int ay,int ndx,int ndy,int x,int y,int fee,",
        "    bool forced,unsigned route,unsigned fold,uint32_t* leaves=nullptr,",
        "    const int* expected=nullptr) {",
        "    const int sx=q[0],sy=q[1],tx=q[2],ty=q[3];",
        "    const int sf=q[4],sl=q[5],tf=q[6],tl=q[7];",
        "    switch (16*fold+route) {",
    ]
    for r, (feature, threshold, _) in enumerate(models):
        if r == 16:
            out.append("#ifdef EXP579_AUDIT")
        out += [f"    case {r}: {{", "        float result=0.f;"]
        for f in sorted(set(feature)):
            out += [f"        const int f{f}={features[f]};",
                    f'        if (expected) require(f{f}==expected[{f}],"active feature");']

        def leaf(tree, depth=0, offset=0):
            if depth == 4:
                return str(offset)
            at = ((1 << depth) - 1 + offset) * 8 + tree
            left = leaf(tree, depth + 1, 2 * offset)
            right = leaf(tree, depth + 1, 2 * offset + 1)
            return f"(f{feature[at]}<{threshold[at]}?{left}:{right})"

        for t in range(8):
            out += [f"        const unsigned p{t}={leaf(t)};",
                    f"        result+=kModels[{r}].value[{16*t}+p{t}];"]
        out += ["        if (leaves) *leaves=" + "|".join(f"(p{t}<<{4*t})" for t in range(8)) + ";",
                "        return result;", "    }"]
    out += ["#endif", '    default: require(false,"native route"); return 0.f;', "    }", "}", ""]
    path = BUILD / "native622.h"
    path.write_text("\n".join(out))
    return path


def build():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    frozen = read(OLD / "validation/results/exp619/build-freeze.json")
    check(BINARIES["A"], frozen["binaries"]["Q4"])
    for item in frozen["dependencies"]:
        check(Path(item["path"]), item)
    for key in ("source", "entry"):
        check(OLD / frozen[key]["path"], frozen[key])
    for name in ("entry.cpp", "exp608_geometry.h", "exp596_csv_batch.h", "exp601_port_parser.h"):
        shutil.copyfile(OLD / "build/exp619" / name, BUILD / name)
    models, model_path = model_rows()
    source = (OLD / frozen["source"]["path"]).read_text()
    body, features = feature_list(source)
    native = emit_native(models, features)
    used = set().union(*(set(m[0]) for m in models[:16]))
    all_used = set().union(*(set(m[0]) for m in models))
    assert len(used) == 35
    sparse = ",".join(f if i in used else f"(fold?({f}):0)" if i in all_used else "0"
                      for i, f in enumerate(features))
    sources = {"R": source, "D": replace(source, body, sparse)}
    native_source = replace(source, "struct Trace {", '#include "native622.h"\n\nstruct Trace {')
    native_source = replace(native_source, "residual(feature,route,fold)",
        "native622(q,ax,ay,ndx,ndy,x,y,fee,forced,route,fold)")
    sources["T"] = native_source
    for arm, text in sources.items():
        (BUILD / f"{arm}-worker.cpp").write_text(text)
        command = read(OLD / "validation/results/exp619/compile-Q4.run.json")["command"]
        replacements = {
            "build/exp619": str(BUILD), "tests": "../exp619/tests",
            "build/exp619/worker.cpp": str(BUILD / f"{arm}-worker.cpp"),
            "build/exp619/Q4.o": str(BUILD / f"{arm}.o"),
        }
        speed.measured([replacements.get(a, a) for a in command], "compile-" + arm)
        assert not (ROOT / f"compile-{arm}.stderr").read_bytes()
        sections = subprocess.check_output(["readelf", "-SW", str(BUILD / f"{arm}.o")], text=True)
        assert ".init_array" not in sections
        link = read(OLD / "validation/results/exp619/link-Q4.run.json")["command"]
        replacements.update({
            "build/exp619/entry.cpp": str(BUILD / "entry.cpp"),
            "build/exp619/codes.o": str(OLD / "build/exp619/codes.o"),
            "build/exp619/Q4": str(BUILD / arm),
        })
        speed.measured([replacements.get(a, a) for a in link], "link-" + arm)
        assert not (ROOT / f"link-{arm}.stderr").read_bytes()
        assert (BUILD / arm).stat().st_size < 100000000
        linked = subprocess.run(["ldd", str(BUILD / arm)], capture_output=True, text=True)
        assert "not a dynamic executable" in linked.stdout + linked.stderr
    assert identity(BUILD / "R")["sha256"] == frozen["binaries"]["Q4"]["sha256"], "rebuilt control"
    write(ROOT / "build-freeze.json", dict(
        binaries={a: identity(p) for a, p in BINARIES.items()}, rebuilt=identity(BUILD / "R"),
        baseline_rebuilt_identical=True, sources={a: identity(BUILD / f"{a}-worker.cpp") for a in sources},
        native=identity(native), models=identity(model_path), features=features,
        used=sorted(used), dead=sorted(set(range(53)) - used), audit_used=sorted(all_used),
        dependencies=frozen, protocol=identity(ROOT / "protocol-original.md"), driver=identity(__file__),
        compiler=subprocess.check_output(["g++", "--version"], text=True),
        disk_free_start=shutil.disk_usage(".").free))
    print("EXP622_BUILT", flush=True)


CHECKER = r"""
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "exp579-models.h"
static void require(bool b,const char* why) {
    if (!b) { std::fprintf(stderr,"%s\n",why); std::exit(1); }
}
static inline int side(int x) { return x<76?0:x<90?1:2; }
static inline int mod(int x,int base) { int r=x%base; return r<0?r+base:r; }
#include "native622.h"
struct Record { float feature[53]; double response; int32_t base,mandatory,prediction; float raw; };
static_assert(sizeof(Record)==240);
static uint32_t bits(float x) { uint32_t v; std::memcpy(&v,&x,4); return v; }
static float compact(const int* x,unsigned route,unsigned fold,uint32_t& leaves) {
    const auto& m=kModels[16*fold+route];
    unsigned p[8]{};
    for (unsigned d=0;d<4;++d)
        for (unsigned t=0;t<8;++t) {
            unsigned at=((1u<<d)-1+p[t])*8+t;
            p[t]=2*p[t]+unsigned(x[m.feature[at]]>=m.threshold[at]);
        }
    float raw=0.f; leaves=0;
    for (unsigned t=0;t<8;++t) { raw+=m.value[16*t+p[t]]; leaves|=p[t]<<(4*t); }
    return raw;
}
int main(int argc,char** argv) {
    require(argc==5,"checker TRACE QUERIES FOLDS OUTPUT");
    FILE *trace=std::fopen(argv[1],"rb"),*query=std::fopen(argv[2],"rb"),
         *folds=std::fopen(argv[3],"rb"),*out=std::fopen(argv[4],"wb");
    require(trace&&query&&folds&&out,"files");
    char magic[8]; uint32_t count;
    require(std::fread(magic,1,8,query)==8&&std::memcmp(magic,"EX535Q01",8)==0&&
            std::fread(&count,4,1,query)==1&&count==1000000,"queries");
    bool routes[64]{};
    for (unsigned i=0;i<count;++i) {
        Record row; int32_t q[10]; unsigned char folded; int f[53];
        require(std::fread(&row,sizeof(row),1,trace)==1&&std::fread(q,4,10,query)==10&&
                std::fread(&folded,1,1,folds)==1&&folded<3,"row");
        for (unsigned j=0;j<53;++j) { f[j]=int(row.feature[j]); require(float(f[j])==row.feature[j],"integer"); }
        int dx=f[8]+f[6],dy=f[9]+f[7];
        unsigned r=4*(2*(dx<0)+(dy<0))+2*(std::abs(dx)>=20)+(std::abs(dy)>=24);
        for (unsigned fold:{0u,unsigned(folded)+1}) {
            uint32_t a,b,c; int sparse[53]{};
            const auto& m=kModels[16*fold+r];
            for (unsigned j=0;j<120;++j) sparse[m.feature[j]]=f[m.feature[j]];
            float x=compact(f,r,fold,a), z=compact(sparse,r,fold,c);
            float y=native622(q,f[28],f[29],f[6],f[7],f[8],f[9],f[50],f[52],r,fold,&b,f);
            require(a==b&&a==c&&bits(x)==bits(y)&&bits(x)==bits(z),"leaf/raw mismatch");
            require(std::fwrite(&b,4,1,out)==1&&std::fwrite(&y,4,1,out)==1,"write");
            routes[16*fold+r]=true;
        }
    }
    for (bool r:routes) require(r,"route coverage");
    require(std::fgetc(trace)==EOF&&std::fgetc(query)==EOF&&std::fgetc(folds)==EOF,"EOF");
    require(std::fclose(trace)==0&&std::fclose(query)==0&&std::fclose(folds)==0&&std::fclose(out)==0,"close");
    std::puts("{\"rows\":1000000,\"leaf_ids\":16000000,\"raw_bitwise\":true,\"active_features_equal\":true}");
}
"""


def audit():
    freeze = read(ROOT / "build-freeze.json")
    reference = read(OLD / "validation/results/exp619/audit.json")["records"][1]["trace"]
    path = OLD / reference["path"]
    check(path, reference)
    source = BUILD / "check.cpp"
    source.write_text("#include <initializer_list>\n" + CHECKER)
    command = ["g++", "-std=c++17", "-O3", "-fno-fast-math", "-ffp-contract=off",
        "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror", "-DEXP579_AUDIT",
        "-I", str(BUILD), "-I", "../exp589/build/exp589/D64-assets", "-static",
        str(source), "-o", str(BUILD / "check")]
    speed.measured(command, "compile-check")
    assert not (ROOT / "compile-check.stderr").read_bytes()
    output = BUILD / "leaf-raw.bin"
    run = speed.measured([str(BUILD / "check"), str(path), "../exp579/build/exp579/queries.bin",
        "../exp579/build/exp579/folds.u8", str(output)], "check")
    counters = read(ROOT / "check.stdout")
    assert counters == dict(rows=1000000, leaf_ids=16000000,
        raw_bitwise=True, active_features_equal=True)
    assert output.stat().st_size == 16000000
    write(ROOT / "audit.json", dict(run=run, counters=counters, output=identity(output),
        source=identity(source), reference=reference, freeze=identity(ROOT / "build-freeze.json"),
        production_output_check_pending=True, native_header=freeze["native"]))
    print("EXP622_AUDIT_PASSED", flush=True)


def comparison(timing, arm, rows, multiplicity=1):
    saved = np.asarray(timing["A"]) - np.asarray(timing[arm])
    critical = float(stats.t.ppf(1 - .025 / multiplicity, len(saved) - 1))
    mean = float(saved.mean())
    half = critical * statistics.stdev(saved) / math.sqrt(len(saved))
    minimum = .001 * rows / 1000000
    return dict(saved_cpu_s=mean, ci_saved_s=[mean - half, mean + half],
        interval_level=1 - .05 / multiplicity, paired_rounds=len(saved), t_critical=critical,
        minimum_s=minimum, speed_gate=bool(mean >= minimum and mean - half > 0),
        delta_accuracy_pp=0., changed_rows=0, saved_cpu_1b_extrapolated_s=mean * 1e9 / rows)


def boundary():
    request = BUILD / "boundary-current.csv"
    with Path("../exp501/build/exp501/u-role/requests.csv").open(newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == ["From", "To"]
        pairs = [next(reader) for _ in range(32)]
    cases = pairs + [[a, a] for a, _ in pairs] + [["BAD", "BAD2"], ["SRB_-1_0/X", "SRB_16_0/X"]]
    mapping = read("../exp575/offline/validation/results/exp575/mapping.json")
    target_ports = set(mapping["targets"])
    same_pin_expected = ["0" if a.split("/", 1)[1] in target_ports else "-1" for a, _ in pairs]
    coordinates = [(75, 0, 90, 0), (75, 549, 90, 549), (75, 120, 90, 130),
        (90, 130, 75, 120), (9, 50, 10, 50), (9, 50, 9, 50),
        (117, 50, 118, 50), (20, 49, 20, 50), (90, 50, 75, 50)]
    for sx, sy, tx, ty in coordinates:
        for source, target in pairs[:8]:
            cases.append([f"SRB_{sx}_{sy}/" + source.split("/", 1)[1],
                          f"SRB_{tx}_{ty}/" + target.split("/", 1)[1]])
    with request.open("x", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["From", "To"])
        writer.writerows(cases)
    outputs, runs = {}, {}
    for arm in ARMS:
        output = BUILD / f"boundary-current-{arm}.csv"
        run = speed.measured([str(BINARIES[arm]), "-in", str(request), "-out", str(output)], "boundary-current-" + arm)
        with output.open(newline="") as stream:
            reader = csv.reader(stream)
            assert next(reader) == ["From", "To", "delay"]
            actual = list(reader)
        assert len(actual) == len(cases) and output.read_bytes().endswith(b"\n")
        assert all(len(p) == 3 and p[:2] == q and str(int(p[2])) == p[2] for p, q in zip(actual, cases))
        assert [p[2] for p in actual[32:64]] == same_pin_expected
        assert all(p[2] == "-1" for p in actual[64:66])
        counters = read(run["stderr"])
        assert counters == dict(rows=len(cases), unreachable=sum(int(p[2]) < 0 for p in actual), query_allocations=0)
        assert run["threads"] == 1 and run["rss_bytes"] <= 2000000000
        outputs[arm], runs[arm] = identity(output), run
        assert outputs[arm]["sha256"] == outputs["A"]["sha256"]
    write(ROOT / "boundary.json", dict(request=identity(request), rows=len(cases),
        zero_rows=same_pin_expected.count("0"), unsupported_same_pin_rows=same_pin_expected.count("-1"),
        malformed_negative_rows=2, map_coordinates=coordinates,
        outputs=outputs, runs=runs, output_equivalent=True,
        coordinate_fixture_from="../exp614/validation/exp614_gemini_features.py"))
    print("EXP622_BOUNDARY_PASSED", flush=True)


def qualify(mode):
    frozen = read(ROOT / "build-freeze.json")
    assert read(ROOT / "audit.json")["counters"]["raw_bitwise"]
    for arm, path in BINARIES.items():
        check(path, frozen["binaries"][arm])
    if mode == "1m":
        arms, rows = ARMS, 1000000
        reference = read(OLD / "validation/results/exp619/complete-report.json")["evidence"]["Q4"]
        request = Path("../exp501/build/exp501/u-role/requests.csv")
    else:
        selected = read(ROOT / "1m-report.json")["selected"]
        assert selected != "A"
        arms = ("A", selected)
        rows = {"independent": 1000000, "10m": 10000000, "100m": 100000000}[mode]
        if mode == "independent":
            reference = read("../exp620/validation/results/exp620/1m-report.json")["evidence"]["Q4"]
            request = Path("../exp588/build/exp588/u-role/requests.csv")
        else:
            assert read(ROOT / ("independent-report.json" if mode == "10m" else "10m-report.json"))["gate"]
            reference = read(f"../exp620/validation/results/exp620/{mode}-report.json")["evidence"]["Q4"]
            reference = dict(reference, input=read(f"../exp620/validation/results/exp620/{mode}-freeze.json")["input"])
            request = Path(f"../exp580/build/exp580/scale-input/requests-{mode}.csv")
    check(request, reference["input"])
    rounds = 4 if mode == "100m" else 6
    schedule = [arms, *([arms, arms[::-1]] * (rounds // 2))]
    write(ROOT / f"{mode}-timing-freeze.json", dict(schedule=schedule, rows=rows,
        input=identity(request), reference=reference, build=identity(ROOT / "build-freeze.json"),
        scipy_version=__import__("scipy").__version__, driver=identity(__file__),
        disk_free_start=shutil.disk_usage(".").free))
    timing, runs, outputs = {a: [] for a in arms}, [], {}
    deleted = []
    for iteration, order in enumerate(schedule):
        for arm in order:
            output = BUILD / f"{mode}-{iteration}-{arm}.csv"
            command = [str(BINARIES[arm]), "-in", str(request), "-out", str(output)]
            run = speed.measured(command, output.stem)
            current = identity(output)
            assert all(current[k] == reference["output"][k] for k in ("bytes", "sha256"))
            counters = read(run["stderr"])
            assert counters == dict(rows=rows, unreachable=0, query_allocations=0)
            assert run["threads"] == 1 and run["rss_bytes"] <= 2000000000 and run["cpu_s"] <= 3600
            run.update(arm=arm, iteration=iteration, input=reference["input"],
                output=current, counters=counters, contract_reused_from=reference)
            write(ROOT / (output.stem + "-evidence.json"), run)
            runs.append(run)
            if iteration:
                timing[arm].append(run["cpu_s"])
                deleted.append(dict(file=current, identical_to=outputs[arm], rebuild_command=command))
                print("EXP622_CLEANUP", current["path"], current["sha256"], flush=True)
                output.unlink()
            else:
                outputs[arm] = current
            print("EXP622_RUN", mode, iteration, arm, run["cpu_s"], flush=True)
    comparisons = {a: comparison(timing, a, rows, len(arms) - 1) for a in arms if a != "A"}
    eligible = [a for a in comparisons if comparisons[a]["speed_gate"]]
    selected = min(eligible, key=lambda a: statistics.mean(timing[a])) if eligible else "A"
    write(ROOT / f"{mode}-report.json", dict(comparisons=comparisons, selected=selected,
        gate=bool(eligible) or mode == "independent", rows=rows, timing=timing, runs=runs, outputs=outputs,
        evidence={a: dict(reference, output=outputs[a]) for a in arms},
        output_equivalent=True, accuracy_reused=True, deleted_duplicates=deleted,
        released_bytes=sum(r["file"]["bytes"] for r in deleted),
        disk_free_end=shutil.disk_usage(".").free, final_accuracy_goal_verified=False))
    print("EXP622_RESULT", mode, selected, comparisons, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp622")
    assert len(sys.argv) == 2 and sys.argv[1] in ("build", "audit", "boundary", "1m", "independent", "10m", "100m")
    if sys.argv[1] == "build":
        build()
    elif sys.argv[1] == "audit":
        audit()
    elif sys.argv[1] == "boundary":
        boundary()
    else:
        qualify(sys.argv[1])
