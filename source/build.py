#!/usr/bin/env python3
"""Rebuild the frozen exp728 submission using only this directory."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parent
EXPECTED_SHA256 = "9c05eb2ce01450f58ffa6d2adaa6793f307f44d8962a66e5d36453be32c5c68f"


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
        "-DEXP594_WRITER", "-DEXP596_BATCH=8", "-I", "third_party/zstd",
    ]
    run(["g++", *flags, "-DEXP608_SIMD=0", "-Dmain=worker608_F",
         "-c", "src/worker.cpp", "-o", "build/worker.o",
         "-DEXP640_TREES=8", "-DEXP684_V_ONLY"])
    # Architecture loading retains the frozen exception-handling settings.
    run(["g++", *arch_flags, "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
         "-c", "src/architecture.cpp", "-o", "build/architecture-resolver.o"])
    run(["g++", *arch_flags, "-c", "src/embedded_arch.cpp", "-o", "build/arch-text.o"])
    run(["g++", "-c", "assets/codes.S", "-o", "build/codes.o"])
    run(["g++", "-c", "assets/compressed.S", "-o", "build/compressed.o"])
    run(["g++", "build/codes.o", "src/entry.cpp", "build/worker.o",
         "-DEXP607_ARM=0", "-DEXP607_AVX_CHOICE=0", "-DEXP607_SSE_CHOICE=0", *flags,
         "build/architecture-resolver.o", "build/arch-text.o", "build/compressed.o",
         "third_party/zstd/libzstd.a", "-static", "-s",
         "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc", "-o", "build/estimate"])
    binary = Path("build/estimate")
    size = binary.stat().st_size
    if size >= 100_000_000:
        raise SystemExit(f"ELF exceeds the submission limit: {size} bytes")
    program_headers = subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    dynamic = subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    if "INTERP" in program_headers or "(NEEDED)" in dynamic:
        raise SystemExit("ELF requires a dynamic loader or shared library")
    originals = json.loads(Path("provenance/original-object-identities.json").read_text())
    objects = {}
    for name, original in originals.items():
        path = Path("build") / name
        digest = sha256(path)
        objects[name] = {
            "bytes": path.stat().st_size, "sha256": digest,
            "matches_frozen": digest == original["sha256"],
        }
    report = {
        "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
        "linker": subprocess.check_output(["ld", "--version"], text=True).splitlines()[0],
        "libc": subprocess.check_output(["ldd", "--version"], text=True).splitlines()[0],
        "commands": commands, "binary_bytes": size, "binary_sha256": sha256(binary),
        "static_linked": True, "under_100mb": True, "objects": objects,
        "matches_frozen_exp728": sha256(binary) == EXPECTED_SHA256,
        "algorithm_executed": False,
    }
    Path("build/build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "commands"}, indent=2))
    if not report["matches_frozen_exp728"] or not all(v["matches_frozen"] for v in objects.values()):
        raise SystemExit("Build differs from frozen exp728; check the toolchain before reusing validation")


if __name__ == "__main__":
    main()
