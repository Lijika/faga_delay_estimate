#!/usr/bin/env python3
"""Deploy the preregistered two-tree residual using exp708/M's frozen worker."""
import ast
import gc
from pathlib import Path
import re
import resource
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path("../exp719/validation").resolve()))
import exp719_leaf_budget as fit
sys.path.insert(0, str(Path("../exp709/validation").resolve()))
import exp709_cost_skeleton as execution

ROOT, BUILD = Path("validation/results/exp720"), Path("build/exp720")
PLAN = Path("experiment/实验720-T2D6静态部署与新100M联合验证.md")
BASE = Path("../exp707/build/exp707/M")
read, write, identity, check = fit.read, fit.write, fit.identity, fit.checked
execution.ROOT = ROOT


def final():
    assert read("../exp719/validation/results/exp719/independent-audit.json")["selected"] == "T2D6"
    assert not ROOT.exists() and not BUILD.exists()
    started, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True); BUILD.mkdir(parents=True)
    shutil.copy2(PLAN, ROOT/"protocol-original.md")
    frozen = read("../exp719/validation/results/exp719/freeze.json")
    for item in frozen["inputs"]:
        check(Path("../exp719")/item["path"], item)
    params = read("../exp719/validation/results/exp719/T2D6-training.json")["params"]
    assert params["depth"] == 6 and params["iterations"] == 2 and params["learning_rate"] == .7599
    data, event, _, _ = fit.data_and_references()
    target = (data["d0"]-data["base"]).astype("<f4")
    weight = (1000/np.maximum(data["d0"]+data["mandatory"], 128)).astype("<f4")
    raw, records = np.zeros(fit.ROWS, "<f8"), []
    for route in range(16):
        mask = data["routes"] == route
        model = fit.fit.cb.CatBoostRegressor(**params)
        model.fit(data["features"][mask], target[mask], sample_weight=weight[mask])
        path = BUILD/f"T2D6-final-{route}.json"
        model.save_model(str(path), format="json")
        values, leaf = fit.predict(read(path), data["features"][mask], 2, 6)
        native = model.predict(data["features"][mask], thread_count=1)
        assert np.array_equal(leaf, model.calc_leaf_indexes(data["features"][mask], thread_count=1))
        assert np.allclose(values, native, rtol=0, atol=1e-10)
        assert np.array_equal(fit.fit.decode(values, data["base"][mask], data["mandatory"][mask]),
                              fit.fit.decode(native, data["base"][mask], data["mandatory"][mask]))
        raw[mask] = values
        records.append(dict(route=route, model=identity(path), train_rows=int(mask.sum()),
            leaf_indices_equal=True, integer_prediction_equal=True,
            raw_max_abs_difference=float(np.abs(values-native).max())))
        del model
        gc.collect()
    raw.tofile(BUILD/"T2D6-final.f64")
    v = Path("../exp684/build/exp684/V8/final.f64")
    check(v, read("../exp684/validation/results/exp684/V8/final-training.json")["final_raw"])
    raw[event == 2] = np.fromfile(v, "<f8")[event == 2]
    raw.tofile(BUILD/"combined-final.f64")
    write(ROOT/"final-training.json", dict(records=records, params=params,
        raw=identity(BUILD/"T2D6-final.f64"), combined=identity(BUILD/"combined-final.f64"),
        V_reference=identity(v), source=identity(__file__), protocol=identity(ROOT/"protocol-original.md"),
        cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-started,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
    print("EXP720_FINAL_TRAINED", flush=True)


def emit():
    module = ast.parse(Path("../exp622/validation/exp622_r8_specialization.py").read_text())
    node = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "feature_list")
    scope = dict(re=re)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "exp622-feature-list", "exec"), scope)
    _, fields = scope["feature_list"]((BASE/"worker.cpp").read_text())
    records = read(ROOT/"final-training.json")["records"]
    oof = read("../exp719/validation/results/exp719/T2D6-training.json")["records"]
    records += [dict(r, model=dict(r["model"], path=str(Path("../exp719")/r["model"]["path"])))
                for r in oof]
    assert len(records) == 64
    models = []
    for r in records:
        check(r["model"]["path"], r["model"])
        m = read(r["model"]["path"])
        assert m["scale_and_bias"] == [1, [0]] and len(m["oblivious_trees"]) == 2
        mapping = {f["feature_index"]: f["flat_feature_index"] for f in m["features_info"]["float_features"]}
        splits = [[(mapping[s["float_feature_index"]], int(np.floor(s["border"]))+1)
                   for s in (t["splits"] or [])] for t in m["oblivious_trees"]]
        assert all(len(s) <= 6 for s in splits)
        values = [t["leaf_values"]+[0.]*(64-len(t["leaf_values"])) for t in m["oblivious_trees"]]
        models.append((splits, values))
    text = ["#pragma once", "static constexpr double kLeaves720[][2][64]={"]
    for k, (_, rows) in enumerate(models):
        if k == 16:
            text.append("#ifdef EXP579_AUDIT")
        text.append("{"+",".join("{"+",".join(float(v).hex() for v in row)+"}" for row in rows)+"},")
    text += ["#endif", "};",
        "static inline __attribute__((always_inline)) double symmetric640(",
        "const int32_t* q,[[maybe_unused]] int ax,[[maybe_unused]] int ay,",
        "[[maybe_unused]] int ndx,[[maybe_unused]] int ndy,int x,int y,",
        "[[maybe_unused]] int fee,[[maybe_unused]] bool forced,unsigned route,unsigned fold,",
        "unsigned char* leaves=nullptr,const int* expected=nullptr) {",
        "[[maybe_unused]] const int sx=q[0],sy=q[1],tx=q[2],ty=q[3];",
        "[[maybe_unused]] const int sf=q[4],sl=q[5],tf=q[6],tl=q[7];", "switch(16*fold+route) {"]
    for k, (splits, _) in enumerate(models):
        if k == 16:
            text.append("#ifdef EXP579_AUDIT")
        text += [f"case {k}: {{", "double result=0.;"]
        for f in sorted({f for tree in splits for f, _ in tree}):
            text += [f"const int f{f}={fields[f]};",
                     f'if(expected) require(f{f}==expected[{f}],"T2D6 active feature");']
        for t, conditions in enumerate(splits):
            expression = "|".join(f"(unsigned(f{f}>={cut})<<{j})"
                                  for j, (f, cut) in enumerate(conditions)) or "0"
            text += [f"const unsigned p{t}={expression};",
                     f"result+=kLeaves720[{k}][{t}][p{t}];", f"if(leaves) leaves[{t}]=p{t};"]
        text += ["return result;", "}"]
    text += ["#endif", 'default: require(false,"T2D6 route"); return 0.;', "}", "}", ""]
    (BUILD/"symmetric640.h").write_text("\n".join(text))


def build():
    assert not (ROOT/"build-freeze.json").exists()
    old = read("../exp707/validation/results/exp707/freeze.json")
    check(BASE/"estimate", old["binaries"]["M"])
    copied = []
    for r in old["sources"]:
        item = r["current"]
        if "/M/" not in item["path"]:
            continue
        source = Path("../exp707")/item["path"]
        check(source, item)
        if source.name != "symmetric640.h":
            if source.name == "exp652_geometry_restore.h":
                text = source.read_text()
                old_path = "build/exp684/V8/restored.bin"
                assert text.count(old_path) == 1
                (BUILD/source.name).write_text(text.replace(old_path, str(BUILD/"restored.bin")))
            else:
                shutil.copy2(source, BUILD/source.name)
            copied.append(identity(BUILD/source.name))
    meta = BASE/"exp707_prepare_metadata.h"
    expected = next(r for r in old["files"] if r["path"] == "tests/exp707_prepare_metadata.h")
    check(meta, expected)
    shutil.copy2(meta, BUILD/meta.name)
    emit()
    c, l = [[v.replace("build/exp707/M", str(BUILD)) for v in old["commands"]["M"][key]]
            for key in ("compile", "link")]
    ac = [str(BUILD/"audit.o") if v == str(BUILD/"C.o") else v for v in c]+["-DEXP579_AUDIT"]
    al = [str(BUILD/"audit.o") if v == str(BUILD/"C.o") else
          str(BUILD/"audit") if v == str(BUILD/"estimate") else v for v in l]
    old_cli = ast.parse(Path("../exp640/validation/exp640_symmetric_cli.py").read_text())
    checker = next(ast.literal_eval(n.value) for n in old_cli.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "CHECKER" for t in n.targets))
    (BUILD/"model-check.cpp").write_text(checker)
    cc = ["g++", "-std=c++17", "-O3", "-fno-fast-math", "-ffp-contract=off",
          "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
          "-DEXP579_AUDIT", "-I", str(BUILD), str(BUILD/"model-check.cpp"),
          "-static", "-s", "-o", str(BUILD/"model-check")]
    for name, command in (("compile", c), ("link", l), ("compile-audit", ac),
                          ("link-audit", al), ("compile-model-check", cc)):
        execution.measured(command, name)
        assert not (ROOT/(name+".stderr")).read_bytes()
    for name in ("estimate", "audit", "model-check"):
        binary = BUILD/name
        assert binary.stat().st_size < 100_000_000
        assert "INTERP" not in subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
        assert "NEEDED" not in subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    files = [Path(__file__), PLAN, ROOT/"protocol-original.md", ROOT/"final-training.json",
             *[p for p in BUILD.iterdir() if p.suffix in (".h", ".cpp", ".json")],
             *[Path(v) for v in l if v.endswith((".o", ".a", ".cpp")) and v != str(BUILD/"C.o")]]
    write(ROOT/"build-freeze.json", dict(files=[identity(p) for p in files], copied=copied,
        binaries=dict(A=identity(BASE/"estimate"), C=identity(BUILD/"estimate")),
        audit=identity(BUILD/"audit"), checker=identity(BUILD/"model-check"),
        compile_command=c, link_command=l, static_linked=True, full_estimator_runs=0))
    print("EXP720_STATIC_BUILT", identity(BUILD/"estimate"), flush=True)


def numeric():
    frozen = read(ROOT/"build-freeze.json")
    for item in frozen["files"]+list(frozen["binaries"].values())+[frozen["audit"], frozen["checker"]]:
        check(item["path"], item)
    data, event, replacement, _ = fit.data_and_references()
    execution.measured([str(BUILD/"model-check"), "../exp631/build/exp631/features.f32",
        "../exp579/build/exp579/queries.bin", "../exp579/build/exp579/folds.u8",
        str(BUILD/"model-check.bin")], "model-check")
    actual = np.memmap(BUILD/"model-check.bin", dtype=[("raw", "<f8"), ("leaf", "u1", (16,))],
                       mode="r", shape=(fit.ROWS, 2))
    records = read(ROOT/"final-training.json")["records"]
    oof = read("../exp719/validation/results/exp719/T2D6-training.json")["records"]
    for stage, models in enumerate((records, oof)):
        for r in models:
            mask = data["routes"] == r["route"]
            if stage:
                mask &= data["folds"] == r["fold"]
            path = Path("../exp719")/r["model"]["path"] if stage else Path(r["model"]["path"])
            raw, leaf = fit.predict(read(path), data["features"][mask], 2, 6)
            assert np.array_equal(actual["raw"][mask, stage].copy().view("u8"), raw.view("u8"))
            assert np.array_equal(actual["leaf"][mask, stage, :2], leaf)
            assert not np.any(actual["leaf"][mask, stage, 2:])
    expected = {0: np.fromfile("../exp719/build/exp719/T2D6-raw.f64", "<f8"),
                1: np.fromfile(BUILD/"combined-final.f64", "<f8")}
    expected[0][event == 2] = replacement[event == 2]
    dtype = np.dtype(dict(names=["features", "response", "base", "mandatory", "prediction", "raw"],
        formats=[("<f4", (53,)), "<f8", "<i4", "<i4", "<i4", "<f8"],
        offsets=[0, 216, 224, 228, 232, 240], itemsize=248))
    traces = []
    for mode in (0, 1):
        path = BUILD/f"cached-trace-{mode}.bin"
        execution.measured([str(BUILD/"audit"), "../exp579/build/exp579/queries.bin",
            "../exp579/build/exp579/folds.u8", str(path), str(mode)], f"cached-worker-{mode}")
        assert read(ROOT/f"cached-worker-{mode}.stdout")["trace_bytes"] == 248
        trace = np.memmap(path, dtype=dtype, mode="r", shape=(fit.ROWS,))
        for key in ("features", "base", "mandatory"):
            assert np.array_equal(trace[key], data[key]), key
        assert np.array_equal(trace["raw"].copy().view("u8"), expected[mode].view("u8"))
        assert np.array_equal(trace["prediction"], fit.fit.decode(expected[mode], data["base"], data["mandatory"]))
        traces.append(identity(path))
    check(BUILD/"restored.bin", read("../exp652/validation/results/exp652/build-freeze.json")["restored_expected"])
    write(ROOT/"numeric-audit.json", dict(all_checks_passed=True, models=64,
        cached_rows=fit.ROWS, all_leaf_ids_equal=True, all_features_equal=True, base_equal=True,
        mandatory_equal=True, raw_bitwise_equal=True, final_prediction_equal=True,
        oof_prediction_equal=True, V_predictions_unchanged=True, complete_estimator_runs=0,
        traces=traces, model_check=identity(BUILD/"model-check.bin")))
    print("EXP720_NUMERIC_AUDIT_PASSED", flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp720")
    assert sys.argv[1:] in (["final"], ["build"], ["numeric"])
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    dict(final=final, build=build, numeric=numeric)[sys.argv[1]]()
