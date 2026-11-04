#!/usr/bin/env python3
"""Build the frozen EAT243 standalone estimator from its verified source and assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parent
FROZEN_SHA256 = "69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02"


def identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "assets/eat243")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--cxx", default=os.environ.get("CXX", "g++"))
    args = parser.parse_args()
    assets, build = args.assets.resolve(), args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((ROOT.parent / "release/source-manifest.json").read_text())
    asset_manifest = json.loads((ROOT.parent / "release/assets-manifest.json").read_text())
    for folder, entries in ((ROOT, source_manifest["source_files"]),
                            (assets, asset_manifest["files"])):
        for relative, expected in entries.items():
            if identity(folder / relative) != expected:
                raise RuntimeError(f"frozen file identity differs: {folder / relative}")
    # Symbol order and alignment match the accepted EAT243 assembly.
    symbols = ("direct_exact", "direct_keys", "directory212", "first212", "second212")
    frames = [assets / symbol for symbol in symbols]
    assembly = [".section .rodata"]
    for symbol, frame in zip(symbols, frames):
        assembly += [".balign 64", f".global {symbol}_begin", f"{symbol}_begin:",
                     ".incbin " + json.dumps(str(frame)),
                     f".global {symbol}_end", f"{symbol}_end:"]
    assembly += ['.section .note.GNU-stack,"",@progbits']
    (build / "assets.S").write_text("\n".join(assembly) + "\n")
    (build / "tmp").mkdir(exist_ok=True)
    env = dict(os.environ, TMPDIR=str(build / "tmp"))
    commands = []

    def run(command):
        print(shlex.join(command), flush=True)
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        commands.append(command)

    arch_flags = [
        "-std=c++17", "-O3", "-pipe", "-fno-rtti", "-fno-fast-math", "-ffp-contract=off",
        "-march=x86-64", "-mtune=generic", "-Wall", "-Wextra", "-Werror",
        "-DDELAY_ESTIMATE_EMBEDDED_ARCH", "-I", "include", "-I", "src", "-I", "include",
    ]
    flags = arch_flags + [
        "-fno-exceptions", "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE", "-DEXP580_PORT_PARSER",
        "-DEXP581_PREFETCH", "-DEXP582_BLOCK=64", "-DEXP594_PACKED",
        "-DEXP594_WRITER", "-DEXP596_BATCH=32", "-I", "third_party/zstd",
    ]
    run([args.cxx, *flags, "-DEXP608_SIMD=0", "-Dmain=worker608_F", "-DEXP640_TREES=8",
         "-c", "src/worker.cpp", "-o", str(build / "worker.o")])
    run([args.cxx, *arch_flags, "-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE",
         "-c", "src/architecture.cpp", "-o", str(build / "architecture-resolver.o")])
    run([args.cxx, *arch_flags, "-c", "src/embedded_arch.cpp", "-o", str(build / "arch-text.o")])
    run([args.cxx, "-c", str(build / "assets.S"), "-o", str(build / "assets.o")])
    run([args.cxx, str(build / "assets.o"), "src/entry.cpp", str(build / "worker.o"),
         "-DEXP607_ARM=0", "-DEXP607_AVX_CHOICE=0", "-DEXP607_SSE_CHOICE=0", *flags,
         str(build / "architecture-resolver.o"), str(build / "arch-text.o"),
         "third_party/zstd/libzstd.a", "-static", "-s",
         "-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc", "-o", str(build / "estimate")])
    binary = build / "estimate"
    info = identity(binary)
    program_headers = subprocess.check_output(["readelf", "-lW", str(binary)], text=True)
    dynamic = subprocess.check_output(["readelf", "-dW", str(binary)], text=True)
    if info["bytes"] >= 100_000_000 or "INTERP" in program_headers or "(NEEDED)" in dynamic:
        raise RuntimeError("candidate fails the static single-ELF size gate")
    report = {
        "binary": info, "static_linked": True, "elf_limit_bytes": 100_000_000,
        "matches_frozen_eat243": info["sha256"] == FROZEN_SHA256,
        "compiler": subprocess.check_output([args.cxx, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "sources": {str(path.relative_to(ROOT)): identity(path)
                    for folder in ("src", "include", "third_party")
                    for path in sorted((ROOT / folder).rglob("*")) if path.is_file()},
        "assets": {str(path.relative_to(assets)): identity(path) for path in frames},
    }
    (build / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("commands", "sources", "assets")}, indent=2))


if __name__ == "__main__":
    main()
