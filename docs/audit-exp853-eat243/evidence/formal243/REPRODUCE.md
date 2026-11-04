# EAT243 lossless directory release

The immutable label prepared on 2026-11-04 is
`exp853-eat243-lossless-directory-20261104`.
Main accepted source packet commit
`e0a7a86aaec8b0939974c90456eb36439a63d6e4`.
The complete compiled-source roster is the **33 entries** in
`evidence/build-report.json`, canonical SHA-256
`c799b57b0a4b88d9ea61fb8c5af0623655238236108fc34ac1bec3f2cfc4d3f8`.
The historical packet commit binds the source producer and evidence; the
compiled-source manifest independently binds all final source bytes.

The package carries those 33 files under `source/`, all five byte-exact
generated payloads under `assets/`, static `libzstd.a`, `zstd.h` and
`COPYRIGHT.libzstd`, original assembly, actual compiler argv, toolchain identity,
Main's acceptance and raw terminal summary, CPU admission, generation and
materialization evidence, and the final actual-ELF complete1M release receipt.
No Python, Julia, zstd shared library or external asset file is required at
estimator runtime. The five architecture JSONs are embedded by
`source/src/embedded_arch.cpp`.

Reconstruction uses GCC 11.4.0
`Ubuntu 11.4.0-1ubuntu1~22.04.3`, GNU ld 2.38 and matching Ubuntu 22.04 static
runtime. Run from an authorized project namespace with enough capacity:

```bash
PACKAGE=/home/lhjysyx/EDA2026/subm/versions/exp853-eat243-lossless-directory-20261104
SCRATCH=/home/lhjysyx/EDA2026_EAT/candidate/work_eat248_stage243_release/rebuild-main
python3 -B "$PACKAGE/rebuild.py" --package "$PACKAGE" --out "$SCRATCH" --plan-only
python3 -B "$PACKAGE/rebuild.py" --package "$PACKAGE" --out "$SCRATCH"
sha256sum "$SCRATCH/estimate"
```

The expected ELF is **86,937,624 B**, SHA-256
`69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02`.
The replay replaces only source/overlay/assembly/object/output paths. All
compiler switches, argument ordering, asset symbol ordering, 64-byte alignment,
static library and linker flags come from the accepted build report.
Original anonymous `/proc/<pid>/fd/` asset names in assembly are replaced by the
five packaged payload paths. No asset generation or recompression runs.
`--out` must be a new directory; failures preserve the actual result and logs.
The 243 materialization receipt already records a real reconstruction of
this exact ELF. EAT248 reuses that evidence and checks the replay's path
translation administratively; EAT248 does not execute another build.

Verify a completed package with its bundled publisher:

```bash
python3 -B "$PACKAGE/package_release.py" verify --prepared "$PACKAGE"
```

The release's formal source is the exact `source/` snapshot inside this
immutable version. Root `estimate`, `build/submission/estimate` and the latest
mirror are refreshed from this version by the existing 118 helpers. Main's
dirty ordinary source files and Git HEAD have independent identities.
An explicit rebuild through `rebuild.py` selects this snapshot; the historical
root build entry does not select it.

The final 1M release gate uses an empty environment and a clean cwd containing
only `estimate`; its output is an anonymous memfd. The filesystem namespace
remains the host namespace. Source review establishes runtime asset embedding;
this check supplies no mount-namespace isolation or official-platform evidence.

The accepted r9 CPU8 development comparison used AB warmups followed by
ABBA/BAAB/ABBA. Parent/child mean complete1B CPU was
128.60633816666666/125.208939 s. The score gain was
0.028311659722220384, with registered joint one-sided 95% lower bound
0.02069454135805846. All 14 full outputs matched. Sampled Acc stayed
98.85534283747039% over 3,833,856 exposed exact rows and 59,904 role pairs,
weighted by role-pair population with 64 observations per pair.
Repeated outputs add no exact-label observations. Timing uncertainty and the
Student-t bound condition on the registered three blocks and measured host
state. Accuracy delta is zero on the observed full outputs.

Official platform, official consecutive-five protocol, fresh hidden inputs,
all-row exact accuracy, Acc above 99% and approximately100s CPU remain open.
