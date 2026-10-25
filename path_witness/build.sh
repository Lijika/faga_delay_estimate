#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
for name in trace exact_labels; do
    g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter \
        -Wno-unused-function -static -s -march=x86-64 -mtune=generic \
        -ffp-contract=off "solver/$name.cpp" solver/src/architecture.cpp \
        solver/src/router.cpp solver/src/residue_estimator.cpp -o "build/$name"
done
./build/trace --help
