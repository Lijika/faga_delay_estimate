#!/bin/bash
set -u
cd "$HOME/lhjwork/eda2026" || exit 1
export PYTHONPATH="$PWD/research/exp640/build/exp640/pydeps"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python="$PWD/research/exp491/build/venv/bin/python"
cd research/exp685 || exit 1
mkdir data-launch || exit 1
for stage in prepare dataset labels; do
    timeout 7500 "$python" -u validation/exp685_event_data.py "$stage" \
        >"data-launch/$stage.stdout" 2>"data-launch/$stage.stderr"
    status=$?
    printf '%s\n' "$status" >"data-launch/$stage.exit-code"
    if [ "$status" -ne 0 ]; then exit "$status"; fi
done
