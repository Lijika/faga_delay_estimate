#!/bin/bash
set -u
cd "$HOME/lhjwork/eda2026" || exit 1
export PYTHONPATH="$PWD/research/exp640/build/exp640/pydeps"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python="$PWD/research/exp491/build/venv/bin/python"
cd research/exp678 || exit 1
mkdir -p validation/results || exit 1
mkdir validation/results/exp678-launch || exit 1
"$python" -u validation/exp678_hv_replacement.py \
    >validation/results/exp678-launch/stdout \
    2>validation/results/exp678-launch/stderr
status=$?
printf '%s\n' "$status" >validation/results/exp678-launch/exit-code
exit "$status"
