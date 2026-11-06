# FPGA SRB Delay Estimator

This repository contains the formal stage release
`exp913-packedjoin-b2442-20261106`, its complete frozen source and build assets,
and the official contest materials in [`docs/task/`](docs/task/).

The current source is in
[`source/exp913-packedjoin-b2442-20261106/`](source/exp913-packedjoin-b2442-20261106/).
Its 403 files match the immutable release byte for byte. The earlier EAT243
source and assets remain at their existing paths under `source/`.

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

PackedJoin uses its supplied prediction model and bounded physical-correction
tables. The integration retains B2442 initialization, source-by-source memory
release, batch64 parsing and output, and the existing CPU dispatch.
Other x86-64 processors use the SSE2 path; Xeon Gold 6242R and 6226R use the
Cascade Lake path after model and usable-instruction checks.

The frozen source includes the model, architecture and correction assets,
static Zstandard library, XZ decoder and licenses. `model_reproduction/`
preserves historical exp855/exp858 training material; the current model's
provenance is recorded in `manifest.json` and
[`release/exp913-packedjoin-b2442-20261106/supplied-PackedJoin.json`](release/exp913-packedjoin-b2442-20261106/supplied-PackedJoin.json).

## Build and run

Requires Linux x86-64, Python 3, GCC/G++ with static runtime libraries, and GNU
binutils (`readelf`). The measured build used r9, Ubuntu 22.04 and GCC 11.4.0.

```sh
cd source/exp913-packedjoin-b2442-20261106
python3 -B build.py --variant fast --mode source --out-dir build
./build/fast/estimate -in request.csv -out result.csv
```

The builder checks the assets, embeds the runtime data and verifies a static
executable smaller than 100,000,000 bytes. Build products stay in the version's
ignored `build/` directory. Other toolchains can produce different ELF bytes.
The [export verification](release/exp913-packedjoin-b2442-20261106/export-verification.json)
records file equality with the tested release and the reused build evidence.

The [official public 1M dataset](data/official-1m/) includes published golden
answers and matching two-column requests. The
[classified-A error sample](data/exp855-classified-a-errors-2m/) contains the
representative 2M request pairs selected from exp855's errors.

## Release identity and measured evidence

- Static ELF: 99,329,624 bytes.
- ELF SHA-256: `c17781d33c9fa1c2d3672b320a4c0d9f3d667d3dee6ddac75dfcb5d5a485a3a0`.
- Maximum measured estimator RSS: 1,965,051,904 bytes.
- Full official 1M Acc: 99.21508547390856%.
- Five automatic official-1M runs, the generic path and the supplied PackedJoin
  executable produced identical complete outputs.

| Measured input | Acc | Complete-program CPU |
| --- | ---: | ---: |
| Classified A, full 100M | 99.28377634074471% | 33.263258 s |
| Classified B, full 100M | 99.28428301373597% | 33.228675 s |
| A/B combined, full 200M | 99.28402967724034% | — |
| Nonrepeating 1B, first run | 99.29060347284297% sampled | 142.663580 s |
| Nonrepeating 1B, second run | 99.29060347284297% sampled | 142.605567 s |

The 1B score uses 3,833,856 stratified exact labels across 59,904 role pairs,
64 samples per pair, weighted by population. Its within-pair sampling 95%
interval is [99.28828048856931%, 99.29292645711664%]. This interval excludes
model-selection uncertainty and dependence between source families. These
inputs have been observed during development.

The two complete 1B outputs have identical SHA-256. Mean CPU was
142.6345735 seconds, with a 0.058013-second range. Two runs describe this
observed spread; longer-term stability remains to be measured.

All measured runs passed the output contract, single-thread, 2,000,000,000-byte
RSS and 3,600-second limits. RSS remains above the preferred 1.9 GB, and the
90-second CPU target is pending. Official-platform results, 6242R hardware,
all-row 1B exact accuracy and fresh hidden-input performance remain unverified.
Supplied A/B labels were used as provided; their solver provenance has not been
independently verified.

Frozen build and publication records are in
[`release/exp913-packedjoin-b2442-20261106/`](release/exp913-packedjoin-b2442-20261106/).
`version.json` preserves publication-time status; `summary.json`, `full1b.json`
and the classified result files contain the completed measurements.
