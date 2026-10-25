#!/bin/sh
# Run from the project root after the documented 1M/10M and reachability gates.
set -eu
root=build/hidden-suite-v1
for kind in output role; do
  case "$kind" in
    output) profile=U-output; proposal=2026101201; shuffle=2026101301 ;;
    role) profile=U-role; proposal=2026101202; shuffle=2026101302 ;;
  esac
  dataset="$root/$kind-1b"
  /usr/bin/time -v -o "$root/$kind-1b.time" \
    "$root/make_hidden_suite" "$root/arch" "$root/reach.bin" \
    "$profile" 1000000000 "$proposal" "$shuffle" "$dataset" \
    >"$root/$kind-1b.log" 2>&1
  /usr/bin/time -v -o "$root/$kind-1b-check.time" \
    "$root/check_hidden_suite" "$root/arch" "$root/reach.bin" \
    "$root/independent/eligibility.bin" "$profile" 1000000000 \
    "$dataset/requests.csv" "$dataset/check" >"$root/$kind-1b-check.log" 2>&1
  python3 "$root/validation/hidden_suite_manifest.py" --root "$root" --dataset "$kind-1b" \
    >"$root/$kind-1b-manifest.log" 2>&1
  ln "$dataset/requests.csv" "$root/u-$kind-1b.csv"
  cp "$dataset/manifest.json" "$root/u-$kind-1b.json"
done
printf 'Both 1B datasets generated, checked and frozen.\n'
