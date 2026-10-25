#!/bin/bash
set -u
cd "$HOME/lhjwork/eda2026" || exit 1
export PYTHONPATH="$PWD/research/exp640/build/exp640/pydeps"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python="$PWD/research/exp491/build/venv/bin/python"
cd research/exp684 || exit 1
mkdir validation/results/exp684-launch || exit 1
for arm in V8 HV8; do
    timeout 1800 "$python" -u validation/exp684_event_prefix.py "$arm" \
        >"validation/results/exp684-launch/$arm.stdout" \
        2>"validation/results/exp684-launch/$arm.stderr"
    status=$?
    printf '%s\n' "$status" >"validation/results/exp684-launch/$arm.exit-code"
    if [ "$status" -ne 0 ]; then exit "$status"; fi
done
