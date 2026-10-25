#!/usr/bin/env python3
"""Recreate the exp683/exp685 stratified sample plan and extract its request rows."""
import argparse
import ast
import json
from pathlib import Path
import struct
import subprocess

import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("100m", "1b"))
    parser.add_argument("requests", type=Path)
    parser.add_argument("population_json", type=Path)
    parser.add_argument("sampler_binary", type=Path)
    parser.add_argument("new_output_directory", type=Path)
    args = parser.parse_args()
    original = HERE.parent / "training/original/validation/exp683_expanded_exact.py"
    node = next(n for n in ast.parse(original.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "sampling_plan")
    scope = dict(np=np, struct=struct)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(original), "exec"), scope)
    population = np.asarray(json.loads(args.population_json.read_text()), "<u4")
    rows, count, seed = (100_000_000, 32, 20261024685) if args.case == "100m" \
                       else (1_000_000_000, 64, 20261025683)
    assert population.shape == (59904,) and population.sum() == rows
    out = args.new_output_directory.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scope["sampling_plan"](out / "sampling-plan.bin", population, count, seed)
    mapping = json.loads((HERE.parent / "path_witness/query_source/mapping.json").read_text())
    for name in ("sources", "targets"):
        (out / name).write_text("\n".join(mapping[name]) + "\n")
    command = [str(args.sampler_binary.resolve()), str(args.requests.resolve()),
               str(out / "sampling-plan.bin"), str(out / "sources"), str(out / "targets"),
               str(out / "sample-requests.csv"), str(out / "positions.txt"), str(out / "counts.tsv")]
    subprocess.run(command, check=True)
    report = dict(case=args.case, rows=rows, samples=count * 59904, seed=seed,
                  per_pair=count, inclusion_probability="count / N_pair", index_base=0)
    (out / "sampling.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
