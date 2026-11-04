# FPGA SRB Delay Estimator

This repository contains the formal stage release
`exp853-eat243-lossless-directory-20261104`, its complete build inputs, and the
official contest materials in [`docs/task/`](docs/task/).

The [development-history audit](docs/audit-exp853-eat243/00-阅读入口与结论.md)
covers the project through EAT243 with seven reports, all 1,018 experiment
logs, selected raw evidence, resource calculations, and a SHA-256 delivery
manifest. The reports distinguish measurements, derivations, and unverified
claims.

The estimator predicts directed routing delays between FPGA SRB ports. It
reads CSV requests and writes `From,To,delay` rows in the original request
order. Architecture data and prediction tables are embedded in one static
executable.

## Current algorithm

EAT243 uses a lossless full-domain directory representation, building on
EAT176's direct access to 33,280 nominal curves and EAT117's zero raw term for
ordinary `event679 == 0` requests. Ordinary requests covered by the direct
curves read one curve; other requests retain the A/B surface representation.
Event, cycle, forced-bias and final integer-composition logic remain in the
frozen source.

The EAT243 release preserves EAT176's complete output on the measured 1B
input and reduces CPU cost. Its 33 compiled source/library files and five
generated assets are checked against their release SHA-256 manifests before
building. The five original architecture JSON files remain in `source/arch/`.

## Build and run

Requires Linux x86-64, Python 3, GCC/G++ with static runtime libraries, and GNU
binutils (`readelf`). All prediction assets and the static Zstandard library
are included.

```sh
cd source
python3 -B build.py
./build/estimate -in request.csv -out result.csv
```

The builder checks the frozen inputs, embeds all five assets, and verifies a
static executable smaller than 100,000,000 bytes. Intermediate files stay in
`source/build/`, which is ignored by Git. See
[`source/README.md`](source/README.md) for source identity and build details.

The [official public 1M dataset](data/official-1m/) includes the published golden
answers and matching two-column requests as lossless gzip files, with
decompression commands and SHA-256 checksums.

## Release identity and measured evidence

- Source producer commit: `e0a7a86aaec8b0939974c90456eb36439a63d6e4`.
- Canonical 33-file source SHA-256: `c799b57b0a4b88d9ea61fb8c5af0623655238236108fc34ac1bec3f2cfc4d3f8`.
- Frozen executable: 86,937,624 bytes, SHA-256 `69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02`.
- Build assets: five files, 79,398,908 bytes.

The registered r9 CPU8 comparison used one exposed, non-repeating 1B
development input, with AB warmups and ABBA/BAAB/ABBA timed blocks. Six timed
runs per arm measured mean CPU of 128.6063381667 seconds for EAT176 and
125.208939 seconds for EAT243. All 14 full outputs matched. Same-output
scoring of 3,833,856 exact-labeled samples across 59,904 role pairs gave
unchanged Acc of 98.8553428375%. The paired score gain was 0.0283116597 points,
with a registered joint one-sided 95% lower bound of 0.0206945414.

These records describe the frozen development distribution and its sampled
exact labels. Unknown-input generalization, all-row 1B exact accuracy,
official-platform results, Acc above 99%, approximately 100-second CPU, and
the official consecutive-five protocol remain unverified. Source and asset
identities are recorded in [`release/`](release/); export build and complete
1M parity checks are recorded in
[`release/export-verification.json`](release/export-verification.json).

The current tree contains the latest formal source and required assets.
Earlier algorithm versions remain available through Git history.
