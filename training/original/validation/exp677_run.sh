#!/bin/sh
set -u
test "$(pwd)" = /home/lhj/lhjwork/eda2026/research/exp677 || exit 2
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
limit=$(( $(date +%s) + 15000 ))
while :; do
    if test -f ../exp676/scale-exit-code.txt; then
        test "$(cat ../exp676/scale-exit-code.txt)" -eq 0 || exit 3
        if test -f ../exp676/validation/results/exp676/skip.json; then break; fi
        if test -f ../exp676/audit-exit-code.txt; then
            test "$(cat ../exp676/audit-exit-code.txt)" -eq 0 || exit 4
            break
        fi
    fi
    kill -0 "$(cat ../exp676/pipeline.pid)" 2>/dev/null || exit 5
    test "$(date +%s)" -lt "$limit" || exit 6
    sleep 60
done
printf 'EXP677_START %s\n' "$(date -Is)"
timeout 190 ../exp491/build/venv/bin/python -u validation/exp677_map_events.py >diagnostic.stdout 2>diagnostic.stderr
code=$?
printf '%s\n' "$code" >diagnostic-exit-code.txt
test "$code" -eq 0 || exit "$code"
printf 'EXP677_PIPELINE_COMPLETE %s\n' "$(date -Is)"
