#!/usr/bin/env python3
"""Build the frozen exp610 submission using only this directory."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parent
EXPECTED_SHA256 = "7e9ab5769e11f090fcf4c189851c09076a96580d02a9c9705996e0bead259c1d"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    os.chdir(ROOT)
    for line in Path("SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        if sha256(Path(name)) != expected:
            raise SystemExit(f"source checksum mismatch: {name}")
    print("Source checksums passed.", flush=True)
    commands = []

    def run(command):
        print(shlex.join(command), flush=True)
        subprocess.run(command, check=True)
        commands.append(command)

    run(["python3", "scripts/gen_embedded_arch.py", "--arch", "arch", "--out", "src", "--check"])
    Path("build").mkdir(exist_ok=True)
    arch_flags = [
        "-std=c++17", "-O3", "-fno-rtti", "-fno-fast-math", "-ffp-contract=off",
        "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-I", "src", "-I", "include",
    ]
    flags = arch_flags[:3] + ["-fno-exceptions"] + arch_flags[3:] + [
        "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE", "-DEXP580_PORT_PARSER",
        "-DEXP581_PREFETCH", "-DEXP582_BLOCK=64", "-DEXP594_PACKED",
        "-DEXP594_WRITER", "-DEXP596_BATCH=8",
    ]
    for arm, extra in [
        ("F", ["-DEXP608_SIMD=0"]),
        ("S", ["-DEXP608_SIMD=1", "-msse4.1"]),
        ("D", ["-DEXP608_SIMD=1", "-DEXP607_AVX2", "-mavx2"]),
    ]:
        run(["g++", *flags, *extra, f"-Dmain=worker608_{arm}",
             "-c", "src/worker.cpp", "-o", f"build/{arm}.o"])
    # Architecture loading keeps the original exception handling.
    run(["g++", *arch_flags, "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
         "-c", "src/architecture.cpp", "-o", "build/architecture-resolver.o"])
    run(["g++", *arch_flags, "-c", "src/embedded_arch.cpp", "-o", "build/arch-text.o"])
    run(["g++", "-c", "assets/geometry.S", "-o", "build/geometry.o"])
    run(["g++", "src/entry.cpp", "build/F.o", "build/S.o", "build/D.o",
         "-DEXP607_ARM=0", "-DEXP607_AVX_CHOICE=0", "-DEXP607_SSE_CHOICE=0", *flags,
         "build/architecture-resolver.o", "build/arch-text.o", "build/geometry.o",
         "-static", "-s", "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc",
         "-o", "build/estimate"])
    binary = Path("build/estimate")
    size = binary.stat().st_size
    if size >= 100_000_000:
        raise SystemExit(f"ELF exceeds the submission limit: {size} bytes")
    program_headers = subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    dynamic = subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    if "INTERP" in program_headers or "(NEEDED)" in dynamic:
        raise SystemExit("ELF requires a dynamic loader or shared library")
    digest = sha256(binary)
    report = {
        "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
        "linker": subprocess.check_output(["ld", "--version"], text=True).splitlines()[0],
        "libc": subprocess.check_output(["ldd", "--version"], text=True).splitlines()[0],
        "commands": commands, "binary_bytes": size, "binary_sha256": digest,
        "static_linked": True, "under_100mb": True,
        "matches_frozen_exp610": digest == EXPECTED_SHA256,
        "algorithm_executed": False,
    }
    Path("build/build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "commands"}, indent=2))
    if digest != EXPECTED_SHA256:
        raise SystemExit("ELF differs from frozen exp610; compare the toolchain before using prior validation")


if __name__ == "__main__":
    main()
