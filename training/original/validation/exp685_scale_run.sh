#!/bin/bash
set -u
cd "$HOME/lhjwork/eda2026" || exit 1
export PYTHONPATH="$PWD/research/exp640/build/exp640/pydeps"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python="$PWD/research/exp491/build/venv/bin/python"
cd research/exp685 || exit 1
mkdir scale-launch || exit 1
printf '%s\n' 'EXP685_WAITING_FOR_LABELS'
scale_deadline=$((SECONDS + 7500))
while [ ! -f data-launch/labels.exit-code ]; do
    if [ "$SECONDS" -ge "$scale_deadline" ]; then exit 1; fi
    sleep 5
done
test "$(cat data-launch/labels.exit-code)" = 0 || exit 1
test "$(cat ../exp683/exit-expanded-score-1b-archive.txt)" = 0 || exit 1
for stage in run unchanged score; do
    timeout 3600 "$python" -u validation/exp685_event_scale.py "$stage" \
        >"scale-launch/$stage.stdout" 2>"scale-launch/$stage.stderr"
    status=$?
    printf '%s\n' "$status" >"scale-launch/$stage.exit-code"
    if [ "$status" -ne 0 ]; then exit "$status"; fi
done
