# exp853 EAT117 Frozen Source

This directory contains the production source for `exp853-eat117-rawzero-parser-20261102`, published on 2026-11-02.

## Source identity

- Candidate source commit: `2d7c5625ff2da531bd37d249b5540a8c4940c6a2`.
- Historical candidate commit and manifest `source_commit`: `e1c6ebdec412f4b1fe59960b198bbfded8452ce4`.
- Canonical manifest: 32 files; SHA-256 `30e34ab81535b73c84862a1622aefb972a3d74c8cde923cd7f7c5e52de8c9383`.
- Frozen static ELF: 90,411,032 bytes; SHA-256 `8b80103cecfe7425f780f4e3497994fe55312186ec4bc80ab1ac57669241ca57`.
- The frozen `build.py` and all 32 manifest files are copied byte-for-byte. The Zstandard library, header, and copyright notice are included in those 32 files. The five `arch/SRB_*.json` files are retained as contest assets, and the 210 surface frames are external to the canonical source manifest.
- Generated ELF and build reports are not tracked. Run `sha256sum build/estimate` to inspect the local output identity.

## Build

The recorded byte-reproduction environment is Ubuntu 22.04 x86-64, GCC 11.4.0, binutils 2.38, glibc 2.35, and the matching static runtime libraries. The frozen build script retains historical `exp825` help text and a `FROZEN_SHA256` self-check constant; these fields do not identify EAT117. Use the 32-file manifest and `../release/identity.json` for this version's identity.

```sh
cd source
python3 build.py --assets assets/surface779
./build/estimate -in request.csv -out result.csv
```

The build needs Python 3, `g++`, GNU `readelf`, and static link libraries. It writes `build/assets.S`, object files, `build/estimate`, and `build/build-report.json`. The generated executable is checked for a static ELF and size below 100,000,000 bytes. This repository-local `--assets` argument avoids the builder's original machine-specific default asset path.

### Surface assets

`assets/surface779/` contains the 210 compressed frames used in the frozen build: `first.zst`, `second.zst`, and `fields/000.zst` through `fields/207.zst`. The complete set totals 82,872,955 bytes. The frozen builder checks each frame against the byte size embedded in `include/surface_assets779.h`; the frame sizes and SHA-256 hashes were also compared with the EAT117 build report before publication.

The source bundle includes the exact `third_party/zstd/libzstd.a`, header, and copyright notice used by the frozen build. The frame identities are recorded in `../release/assets-manifest.json`. No model training or external dataset directory is needed for inference build.

## Implementation

The EAT117 change affects only the ordinary zero-event prediction branch in `src/worker.cpp`: its raw component is `0.0`. Nonzero events continue through `replacement679`; the forced-bias adjustment for `event == 1` remains active. The original 32-file source manifest includes the relevant prediction headers and build script.

## Evidence and limits

The frozen ELF passed 14 complete 1B development-input contracts, single-thread checks, and resource checks. There were six timed runs per arm and seven full-output consistency runs per arm. Mean CPU was 143.072572 seconds for the parent and 128.7717606667 seconds for EAT117. Same-run scoring used 3,833,856 exact-labeled sampled rows; estimated Acc was 98.8850673464% and 98.8548166161%, respectively. The paired score gain was 0.0949728435 with a one-sided 95% lower bound of 0.0726987000. Maximum observed RSS was 270,606,336 bytes.

The exported repository was also rebuilt with GCC 13.3.0. This produced a static 90,334,640-byte ELF whose SHA differs from the GCC 11.4.0 frozen artifact. The rebuild and frozen artifact produced identical complete outputs for 1,000,000 actual requests, with output-contract and single-thread checks passing. See `../release/export-verification.json`; this was a portability check, with no new accuracy or performance claim.

The Acc estimate is based on a sample, not exact labels for all 1B requests. The input is a development distribution and does not establish unknown-input generalization. Final Acc above 99%, CPU near 100 seconds, and official-platform acceptance remain unverified.
