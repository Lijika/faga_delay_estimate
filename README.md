# FPGA SRB Delay Estimator

This repository contains the current formal source release
`exp917-cert16e-pext-20261107`, its complete frozen source and build assets,
and the official contest materials in [`docs/task/`](docs/task/).

The current source is in
[`source/exp917-cert16e-pext-20261107/`](source/exp917-cert16e-pext-20261107/).
Its 417 files match the immutable release byte for byte. The prior
[`exp913-packedjoin-b2442-20261106`](source/exp913-packedjoin-b2442-20261106/)
source remains as a historical release; EAT243 and earlier assets remain at
their existing paths under `source/`.

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

Cert16E retains the exp916 model, maps, prediction values and accuracy-related
changes. The exp917 integration adds BMI2 PEXT endpoint parsing and related
inlining. Xeon Gold 6242R and 6226R use that path after CPU-model and OS-enabled
instruction checks; other x86-64 processors use the SSE2 path.

The frozen source includes the model, architecture assets, static Zstandard
library, XZ decoder and licenses. `model_reproduction/` preserves historical
exp855/exp858 training material.

## Build and run

Requires Linux x86-64, Python 3, GCC/G++ with static runtime libraries, and GNU
binutils (`readelf`). The measured build used r9, Ubuntu 22.04 and GCC 11.4.0.

```sh
cd source/exp917-cert16e-pext-20261107
python3 -B build.py --variant fast --mode source --out-dir build
./build/fast/estimate -in request.csv -out result.csv
```

The builder checks the assets, embeds the runtime data and verifies a static
executable smaller than 100,000,000 bytes. Build products stay in the version's
ignored `build/` directory. Other toolchains can produce different ELF bytes.
The [release record](release/exp917-cert16e-pext-20261107/version.json),
[source manifest](release/exp917-cert16e-pext-20261107/source-manifest.json),
and [tested-source manifest](release/exp917-cert16e-pext-20261107/tested-source-manifest.json)
record the release identity and tested source files.

The [official public 1M dataset](data/official-1m/) includes published golden
answers and matching two-column requests. The
[classified-A error sample](data/exp855-classified-a-errors-2m/) contains the
representative 2M request pairs selected from exp855's errors.

## Release identity and measured evidence

- Static ELF: 99,840,088 bytes.
- ELF SHA-256: `abea3bf315e8a567d2ced6e0e2e3ff96ac22cab451cfabb68b9a59592c9b4a9f`.
- Build: Ubuntu 22.04, GCC 11.4.0, static source build, no PGO.
- The B100M candidate run and four consistency runs had identical output; the
  generic path also matched. Mean estimator CPU was 19.396891 seconds.

| Measured input | Acc | Complete-program CPU |
| --- | ---: | ---: |
| Classified A, full 100M | 99.28377634074471% | — |
| Classified B, full 100M | 99.28428301373597% | 19.396891 s mean over five runs |
| A/B combined, full 200M | 99.28402967724034% | — |
| Nonrepeating 1B, paired run | 99.29060347284297% sampled | 100.569933 s |

The 1B score uses 3,833,856 stratified exact labels across 59,904 role pairs,
64 samples per pair, weighted by population. Its within-pair sampling 95%
interval is [99.28828048856931%, 99.29292645711664%]. This interval excludes
model-selection uncertainty and dependence between source families. These
inputs have been observed during development.

The 1B CPU was measured once against the parent at 104.145960 seconds, a
3.576027-second reduction. Repeated 1B timing and long-term stability remain
to be measured.

The measured runs passed the output contract, single-thread, 2,000,000,000-byte
RSS and 3,600-second limits. The 90-second CPU target remains unmet. Official
platform results, physical 6242R hardware, all-row 1B exact accuracy and fresh
hidden-input performance remain unverified. Supplied A/B labels were used as
provided; their solver provenance has not been independently verified.

The previous frozen release record is in
[`release/exp913-packedjoin-b2442-20261106/`](release/exp913-packedjoin-b2442-20261106/).
