# FPGA SRB Delay Estimator

This repository contains the frozen `exp853-eat117-rawzero-parser-20261102` estimator source and the official contest materials in [`docs/task/`](docs/task/).

The program estimates directed routing delay between FPGA SRB ports. It reads request pairs from CSV and writes `From,To,delay` rows in the original request order; the architecture and prediction tables are embedded in the executable.

## Current version

The EAT117 candidate retains the EAT097/EAT112 parser and sets the ordinary `event679 == 0` raw prediction to `0.0`. Nonzero event predictions continue to use `replacement679`; the `event == 1` forced-bias correction remains active.

The published candidate source commit is `2d7c5625ff2da531bd37d249b5540a8c4940c6a2`; its historical candidate commit is `e1c6ebdec412f4b1fe59960b198bbfded8452ce4`. The source manifest also records `e1c6ebdec412f4b1fe59960b198bbfded8452ce4` in its `source_commit` field. The canonical SHA-256 manifest for the 32 frozen files is `30e34ab81535b73c84862a1622aefb972a3d74c8cde923cd7f7c5e52de8c9383`, recorded at [`release/source-manifest.json`](release/source-manifest.json). The source files are under [`source/`](source/README.md); required build assets are provided under `source/assets/surface779/`.

## Build and run

Requires Python 3, GCC/G++ with static runtime libraries, GNU binutils (`readelf`), and the frozen repository assets.

```sh
cd source
python3 build.py --assets assets/surface779
./build/estimate -in request.csv -out result.csv
```

The builder creates a statically linked standalone ELF and checks that its size is below 100,000,000 bytes. Its `exp825` help text and `FROZEN_SHA256` value are historical self-check fields, not the identity of EAT117; use the source manifest and [`release/identity.json`](release/identity.json) for the frozen version identity.

## Measured evidence

On the frozen non-repeating 1B development input, six timed runs per arm measured mean CPU of 143.072572 seconds for the parent and 128.7717606667 seconds for EAT117. Same-run exact scoring used 3,833,856 sampled rows: estimated Acc was 98.8850673464% for the parent and 98.8548166161% for EAT117. The paired score gain was 0.0949728435 points with a one-sided 95% lower bound of 0.0726987000. All 14 full runs passed the output contract; both arms were consistent across seven full outputs, single-threaded, and within the measured RSS limit.

These are development-input measurements with sampled exact labels. They do not establish performance on unknown requests, full-1B exact accuracy, or official-platform results. The final Acc goal above 99%, the approximately 100-second CPU goal, and official five-run platform acceptance remain unverified. See [`release/identity.json`](release/identity.json) for version identity and validation scope.

The exported tree passed a static rebuild with GCC 13.3.0 and a complete 1M output-parity check against the frozen executable. See [`release/export-verification.json`](release/export-verification.json) for the compiler, hashes, and check scope.

The current tree retains the official contest materials, frozen EAT117 source and build assets, and this release record. Older implementation, research, benchmark, exact-label, protocol, and validation files were removed from the current tree; existing Git history remains unchanged.
