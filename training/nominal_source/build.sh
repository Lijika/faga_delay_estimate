#!/bin/sh
set -eu
cd "$(dirname "$0")"
g++ -O2 -std=c++17 -Wall -Wextra -Wno-unused-function \
    tests/exp499_full_residue_field.cpp src/architecture.cpp -o field
./field --help
