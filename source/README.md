# EAT243 Frozen Source

This directory exports the compiled source of
`exp853-eat243-lossless-directory-20261104`, published on November 4, 2026.

## Identity

The 33 files listed in `../release/source-manifest.json` match the immutable
formal release byte for byte, including the Zstandard static library, header,
and copyright notice. Their canonical SHA-256 is
`c799b57b0a4b88d9ea61fb8c5af0623655238236108fc34ac1bec3f2cfc4d3f8`.
The source producer commit is `e0a7a86aaec8b0939974c90456eb36439a63d6e4`.

`build.py` is a repository-local build helper. It verifies the release
manifests and uses the accepted compiler switches, asset symbol order and
alignment. The five original `arch/SRB_*.json` files are retained as contest
materials; their contents are already embedded by `src/embedded_arch.cpp`.

## Build

```sh
cd source
python3 -B build.py
./build/estimate -in request.csv -out result.csv
```

Optional paths and compiler can be selected explicitly:

```sh
python3 -B build.py --assets assets/eat243 --build-dir build --cxx g++
```

The frozen build used Ubuntu 22.04 x86-64, GCC 11.4.0, GNU ld 2.38 and the
matching static runtime libraries. Its executable is 86,937,624 bytes with
SHA-256 `69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02`.
Other compiler/runtime versions can produce different ELF bytes.
`build/build-report.json` records the actual compiler, commands, executable
identity and `matches_frozen_eat243`.

The builder requires Python 3, `g++`, `readelf`, and static runtime libraries.
It creates the assembly, objects, executable and report under the chosen
build directory. Compiler temporary files also stay there. It checks static
linking and the strict 100,000,000-byte ELF size limit.

## Assets and runtime

`assets/eat243/` contains `direct_exact`, `direct_keys`, `directory212`,
`first212` and `second212`, totaling 79,398,908 bytes. The build verifies each
size and SHA-256 against `../release/assets-manifest.json` and embeds them
with their frozen 64-byte alignment.

The executable accepts `estimate -in INPUT -out OUTPUT` and produces integer
delay values with the exact header `From,To,delay`. All architecture, model,
directory and curve assets are inside the ELF. Python is used only for the
build.

## Verification scope

The release's measured complete-1B CPU and sampled accuracy are documented
in `../release/identity.json` and the repository README. The export's own
build and complete-1M comparison against the frozen executable are recorded
separately in `../release/export-verification.json`. Compiler parity on that
input supplies no new accuracy or comparative performance result.
