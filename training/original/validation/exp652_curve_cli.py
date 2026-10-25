#!/usr/bin/env python3
"""Build fixed D64 distance curves with S8 and audit cached numeric paths."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path("../exp580/validation").resolve()))
import exp580_complete_speed as speed
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path("validation/results/exp652"), Path("build/exp652")
PLAN = Path("experiment/实验652-D64距离曲线补偿的完整100M联合验证.md")
MODEL = Path("../exp589/build/exp589/D64-assets")
COMPRESSED = Path("../exp646/build/exp646/D64-Z/asset.zst")
CODES = Path("../exp651/build/exp651/D64.curves")
DEPS = Path("../exp646/build/exp646/deps")
BASELINE = Path("../exp640/build/exp640/S8")
speed.ROOT = ROOT


def read(path):
    return json.loads(Path(path).read_text())


def check(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ("bytes", "sha256")), str(path)


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def freeze_check():
    frozen = read(ROOT / "build-freeze.json")
    for item in frozen["files"]:
        check(item["path"], item)
    for a, p in (("A", BASELINE), ("C", BUILD / "C")):
        check(p, frozen["binaries"][a])
    return frozen


def build():
    assert read("../exp651/validation/results/exp651/close-audit.json")["cached_gate"]
    original = read("../exp646/validation/results/exp646/D64-Z-report.json")
    check(COMPRESSED, original["compressed"])
    check(CODES, read("../exp651/validation/results/exp651/nominal-decision.json")["asset"])
    old = read("../exp640/validation/results/exp640/cli-freeze.json")
    check(BASELINE, old["binaries"]["S8"])
    check("../exp640/build/exp640/symmetric-worker.cpp", old["source"])
    check("../exp640/build/exp640/symmetric640.h", old["native"])
    dependencies = read("../exp646/validation/results/exp646/freeze.json")["dependencies"]
    for item in dependencies:
        check(DEPS / Path(item["path"]).name, item)
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    source = Path("../exp640/build/exp640/symmetric-worker.cpp").read_text()
    source = replace(source, 'extern "C" const unsigned char exp579_geometry[];\n', "")
    source = replace(source, '#include "exp596_csv_batch.h"',
                     '#include "exp652_geometry_restore.h"\n#include "exp596_csv_batch.h"')
    source = replace(source, '#include "exp619_phase_lookup.h"',
                     '#include "exp652_distance_curve_lookup.h"')
    source = replace(source, "static void initialize() {",
                     "static void initialize() {\n    restoreGeometry652();")
    (BUILD / "worker.cpp").write_text(source)
    for name in ("entry.cpp", "exp596_csv_batch.h", "exp601_port_parser.h",
                 "exp608_geometry.h", "symmetric640.h"):
        shutil.copy2(Path("../exp640/build/exp640") / name, BUILD / name)
    shutil.copy2("tests/exp652_distance_curve_lookup.h", BUILD / "exp652_distance_curve_lookup.h")
    for name in ("exp579-models.h", "exp582_int8_geometry.h"):
        shutil.copy2(MODEL / name, BUILD / name)
    restore = Path("tests/exp649_geometry_restore.h").read_text()
    restore = restore.replace("exp649", "exp652").replace("Geometry649", "Geometry652")
    (BUILD / "exp652_geometry_restore.h").write_text(restore)
    for name, asset, symbol in (("codes", CODES, "exp619_codes"),
                                ("compressed", COMPRESSED, "exp652_compressed_begin")):
        text = f'.section .rodata.exp652,"a",@progbits\n.balign 64\n.global {symbol}\n{symbol}:\n'
        text += f'.incbin "{asset.resolve()}"\n'
        if name == "compressed":
            text += ".global exp652_compressed_end\nexp652_compressed_end:\n"
        text += '.section .note.GNU-stack,"",@progbits\n'
        (BUILD / f"{name}.S").write_text(text)
        speed.measured(["g++", "-c", str(BUILD / f"{name}.S"), "-o", str(BUILD / f"{name}.o")],
                       "assemble-" + name)
    changes = {
        "../exp589/build/exp589/D64-assets": str(BUILD),
        "build/exp640": str(BUILD),
        "build/exp601": str(BUILD),
        "build/exp640/symmetric-worker.cpp": str(BUILD / "worker.cpp"),
        "build/exp640/S8.o": str(BUILD / "C.o"),
        "build/exp640/entry.cpp": str(BUILD / "entry.cpp"),
        "build/exp640/S8": str(BUILD / "C"),
        "../exp619/build/exp619/codes.o": str(BUILD / "codes.o"),
        "../exp589/build/exp589/D64-assets/geometry.o": str(BUILD / "compressed.o"),
    }
    compile_command = [changes.get(a, a) for a in read(
        "../exp640/validation/results/exp640/compile-S8.run.json")["command"]]
    compile_command += ["-I", str(DEPS)]
    link_command = [changes.get(a, a) for a in read(
        "../exp640/validation/results/exp640/link-S8.run.json")["command"]]
    link_command.insert(link_command.index("-static"), str(DEPS / "libzstd.a"))
    speed.measured(compile_command, "compile-C")
    speed.measured(link_command, "link-C")
    audit_compile = [str(BUILD / "audit.o") if a == str(BUILD / "C.o") else a for a in compile_command]
    speed.measured(audit_compile + ["-DEXP579_AUDIT"], "compile-audit")
    audit_link = [str(BUILD / "audit.o") if a == str(BUILD / "C.o") else
                  str(BUILD / "audit") if a == str(BUILD / "C") else a for a in link_command]
    speed.measured(audit_link, "link-audit")
    for name in ("compile-C", "link-C", "compile-audit", "link-audit"):
        assert not (ROOT / (name + ".stderr")).read_bytes()
    for name in ("C", "audit"):
        binary = BUILD / name
        result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
        assert "not a dynamic executable" in result.stdout + result.stderr
        assert "INTERP" not in subprocess.check_output(["readelf", "-l", str(binary)], text=True)
        assert binary.stat().st_size < 100_000_000
    files = [Path(__file__), PLAN, ROOT / "protocol-original.md", COMPRESSED, CODES,
        Path("tests/exp649_geometry_restore.h"), Path("tests/exp652_distance_curve_lookup.h"),
        Path("../exp589/build/exp589/D64-geometry.bin"),
        Path("../exp580/build/exp580/architecture-resolver.o"),
        Path("../exp579/build/exp579/arch-text.o"), *[DEPS / Path(v["path"]).name for v in dependencies],
        *[p for p in BUILD.iterdir() if p.suffix in (".h", ".cpp", ".S")],
        *Path("doc/eda比赛文件/arch").glob("*.json")]
    write(ROOT / "build-freeze.json", dict(files=[identity(p) for p in files],
        binaries={"A": identity(BASELINE), "C": identity(BUILD / "C")},
        audit_binary=identity(BUILD / "audit"), restored_expected=original["original"],
        compile_command=compile_command, link_command=link_command,
        static_linked=True, host=socket.gethostname(), disk_free_start=shutil.disk_usage(".").free))
    print("EXP652_BUILT", identity(BUILD / "C"), flush=True)


def audit():
    frozen = freeze_check()
    check(BUILD / "audit", frozen["audit_binary"])
    output = BUILD / "cached-trace.bin"
    speed.measured([str(BUILD / "audit"), "../exp579/build/exp579/queries.bin",
        "../exp579/build/exp579/folds.u8", str(output), "1"], "cached-numeric-audit")
    trace_meta = read(ROOT / "cached-numeric-audit.stdout")
    assert trace_meta["rows"] == 1_000_000 and trace_meta["trace_bytes"] == 248
    restored = identity(BUILD / "restored.bin")
    assert all(restored[k] == frozen["restored_expected"][k] for k in ("bytes", "sha256"))
    old_type = np.dtype(dict(names=["features", "response", "base", "mandatory"],
        formats=[("<f4", (53,)), "<f8", "<i4", "<i4"],
        offsets=[0, 216, 224, 228], itemsize=240))
    new_type = np.dtype(dict(names=["features", "response", "base", "mandatory", "prediction", "raw"],
        formats=[("<f4", (53,)), "<f8", "<i4", "<i4", "<i4", "<f8"],
        offsets=[0, 216, 224, 228, 232, 240], itemsize=248))
    expected_trace = read("../exp589/validation/results/exp589/audit.json")["D64"]["trace"]
    check("../exp589/build/exp589/D64-trace.bin", expected_trace)
    before = np.memmap("../exp589/build/exp589/D64-trace.bin", dtype=old_type, mode="r", shape=(1_000_000,))
    actual = np.memmap(output, dtype=new_type, mode="r", shape=(1_000_000,))
    keys_path = Path("../exp615/build/exp615/keys.bin")
    check(keys_path, read("../exp615/validation/results/exp615/freeze.json")["keys"])
    keys = np.fromfile(keys_path, "<u4", offset=12).reshape(-1, 4)
    pair, context, qx, qy = keys.T
    packed = np.fromfile(CODES, "u1", count=59904*480, offset=64).reshape(59904, 480)
    curves = np.fromfile(CODES, "<i2", offset=64+59904*480).reshape(4, 256, 542)
    far = qx+qy > 3
    correction = np.zeros(len(pair), "i4")
    before_column = np.where(qx[far] < 4, (qx[far]+1)*(8-qx[far])//2, 10)
    column = qx[far]*46+qy[far]-before_column
    correction[far] = curves[context[far]//120, packed[pair[far], context[far]], column]
    raw_path = Path("../exp640/build/exp640/S8-final.f64")
    check(raw_path, read("../exp640/validation/results/exp640/final-training.json")["raw"]["S8"])
    raw = np.fromfile(raw_path, "<f8")
    assert np.array_equal(actual["raw"].copy().view("u8"), raw.view("u8"))
    assert np.array_equal(actual["features"].copy().view("u4"), before["features"].copy().view("u4"))
    assert np.array_equal(actual["response"].copy().view("u8"), before["response"].copy().view("u8"))
    assert np.array_equal(actual["base"], before["base"].astype("i8") + correction)
    assert np.array_equal(actual["mandatory"], before["mandatory"])
    prediction = (np.maximum(0., actual["base"].astype("f8") + raw) + .5).astype("i8") + before["mandatory"]
    assert np.array_equal(actual["prediction"], prediction)
    write(ROOT / "numeric-audit.json", dict(cached_rows=len(raw), complete_estimator_runs=0,
        trace=identity(output), restored=restored, trace_fields_bitwise_equal=True,
        final_raw_bitwise_equal=True, distance_curve_base_equal=True, final_prediction_equal=True,
        header=identity(BUILD / "symmetric640.h"), production_capacity_passed=True,
        restored_rebuild_command=read(ROOT / "cached-numeric-audit.run.json")["command"]))
    print("EXP652_CACHED_NUMERIC_AUDIT_PASSED", flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp652")
    assert len(sys.argv) == 2 and sys.argv[1] in ("build", "audit")
    {"build": build, "audit": audit}[sys.argv[1]]()
