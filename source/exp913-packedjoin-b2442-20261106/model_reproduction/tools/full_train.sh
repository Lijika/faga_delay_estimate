#!/usr/bin/env bash
# From-scratch generation of the THREE binary assets from original architecture, nominal graph solver,
# and public training source frequency. Computationally costly and dependent on numerical toolchain versions.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: bash tools/full_train.sh /path/to/faga_delay_estimate/source /absolute/workdir /path/to/public-cohort.csv.gz' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$(realpath "$1")";WORK="$(mkdir -p "$2" && cd "$2" && pwd)";COHORT="$(realpath "$3")"
NOMINAL="$ROOT/sources/repro/nominal_source"
mkdir -p "$WORK/fields" "$WORK/public" "$WORK/tracer" "$WORK/trace-run" "$WORK/knots" "$WORK/wire" "$WORK/model"
for name in SRB_Port.json SRB_Arc.json SRB_Net.json SRB_Inst.json SRB_Gap.json; do
  test -f "$SRC/arch/$name" || { echo "MISSING official architecture: $name" >&2; exit 1; }
  cmp "$SRC/arch/$name" "$ROOT/raw_arch/$name" || { echo "Different architecture JSON: $name" >&2; exit 1; }
done
python3 - <<'PY'
import importlib
for name in ['numpy','pandas','scipy','sklearn','zstandard']:
  importlib.import_module(name)
print('Training Python dependencies available')
PY
# Build release source first: trace.py extracts the frozen builder commands from build/build-report.json.
(cd "$SRC" && python3 build.py --assets assets/surface779)
(cd "$NOMINAL" && bash build.sh)
"$NOMINAL/field" "$SRC/arch" --self-check
# Produces four files, each 152,618,144 bytes. This may require substantial CPU time.
for entry in '0 ZSNB[4]' '1 A_DY' '2 ZDN[2]' '3 S_DQ0'; do
  i="${entry%% *}";name="${entry#* }";dst="$WORK/fields/$i.bin"
  if [[ -e "$dst" ]]; then
    [[ $(stat -c '%s' "$dst") -eq 152618144 ]] || { echo "Incomplete $dst. Delete it and rerun" >&2; exit 1; }
  else
    "$NOMINAL/field" "$SRC/arch" "$name" "$dst"
    [[ $(stat -c '%s' "$dst") -eq 152618144 ]]
  fi
done
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 "$ROOT/sources/knots/fit.py" "$WORK/knots" \
  "$WORK/fields/0.bin" "$WORK/fields/1.bin" "$WORK/fields/2.bin" "$WORK/fields/3.bin" --force-near

g++ -O3 -std=c++17 -I "$NOMINAL" "$ROOT/sources/knots/export.cpp" "$NOMINAL/src/architecture.cpp" -o "$WORK/knots-export"
# Only 'From' is used for role frequencies. The public cohort preserves request order.
gzip -dc "$COHORT" > "$WORK/public/gold.csv"
python3 "$ROOT/sources/repro/inputs/trace.py" "$SRC" "$WORK/tracer"
(cd "$WORK/trace-run" && "$WORK/tracer/estimate" -in "$WORK/public/gold.csv" -out "$WORK/trace-run/output.csv")
mv "$WORK/trace-run/nomtrace.bin" "$WORK/pub.raw"

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 "$ROOT/sources/knots/encode_rates.py" \
  "$WORK/knots" "$WORK/knots-export" "$SRC/arch" \
  "$ROOT/sources/repro/inputs/sources.ids" "$ROOT/sources/repro/inputs/targets.oldidx" \
  "$WORK/public/gold.csv" "$WORK/pub.raw" "$WORK/wire" \
  --fields "$WORK/fields/0.bin" "$WORK/fields/1.bin" "$WORK/fields/2.bin" "$WORK/fields/3.bin" \
  --count 208 --jobs 2 --maxrate 10 --adaptive-price 0.5683326721191406 \
  --adaptive-lambda 2.0 --save adaptive

python3 "$ROOT/tools/pack_assets.py" --wire-dir "$WORK/wire" --books "$WORK/wire/books.npz" \
  --arch "$SRC/arch" --out "$WORK/model"
python3 "$ROOT/tools/split_frames.py" --frames "$WORK/model/frames.bin" \
  --lengths "$WORK/model/frameBytes.inc" --out "$WORK/verified-frames"
echo "Newly generated training assets: $WORK/model"
echo 'Compare manifest against the historic checksums; numerical package/version changes can change bytes.'
