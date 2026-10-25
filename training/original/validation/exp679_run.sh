#!/bin/bash
set -u
cd "$HOME/lhjwork/eda2026" || exit 1
export PYTHONPATH="$PWD/research/exp640/build/exp640/pydeps"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python="$PWD/research/exp491/build/venv/bin/python"
cd research/exp679 || exit 1
mkdir -p validation/results || exit 1
mkdir validation/results/exp679-launch || exit 1
for phase in train build audit; do
    "$python" -u validation/exp679_hv_cli.py "$phase" \
        >"validation/results/exp679-launch/$phase.stdout" \
        2>"validation/results/exp679-launch/$phase.stderr"
    status=$?
    printf '%s\n' "$status" >"validation/results/exp679-launch/$phase.exit-code"
    if [ "$status" -ne 0 ]; then exit "$status"; fi
done
