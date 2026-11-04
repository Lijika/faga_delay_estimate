# Official public 1M dataset

This directory contains all 1,000,000 rows of the contest's public test data,
including the published golden delays. It is public development/test data.

| Archive | Contents | Data rows | Compressed bytes | Original bytes |
| --- | --- | ---: | ---: | ---: |
| `delay_estimate_request.csv.gz` | `From,To` | 1,000,000 | 10,420,377 | 35,394,624 |
| `delay_estimate_ans.csv.gz` | `From,To,delay` | 1,000,000 | 13,279,320 | 41,333,954 |

The golden file comes from `doc/eda比赛文件/data/delay_estimate_ans.csv` in the
research project, as distributed in the official architecture/data package.
The request file is the project's existing `delay_estimate_request.csv`,
derived from the golden file's `From,To` columns in the original row order.
Both archives preserve the respective source file's exact bytes after
decompression. Compression used `gzip -n -9 -c`.

## Verify and extract

From the repository root:

```sh
cd data/official-1m
sha256sum -c SHA256SUMS
gzip -dk delay_estimate_request.csv.gz delay_estimate_ans.csv.gz
sha256sum -c SHA256SUMS.uncompressed
cd ../..
```

The extracted CSV files are ignored by Git. Each CSV has one header row
followed by 1,000,000 data rows.

After building the estimator as described in the repository README, run:

```sh
./source/build/estimate \
  -in data/official-1m/delay_estimate_request.csv \
  -out source/build/official-1m-result.csv
```

The golden answer file supplies reference labels for evaluation.

## Upload verification

The full files were checked for row counts, CSV field counts, and exact
`From,To` agreement at every row. All golden delays are nonnegative integers;
one row has a zero golden delay. Both gzip streams were read to completion,
and their decompressed sizes and SHA-256 hashes matched the source files.

[`manifest.json`](manifest.json) records provenance, file sizes, hashes, and
these checks. This data upload did not run the estimator or measure accuracy
or CPU time.
