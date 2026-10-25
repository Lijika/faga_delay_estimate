#!/usr/bin/env python3
"""Check exclusion encoding, the portable filter, and frozen sampling plans."""
import ast
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np

from export_exclusions import pin_id
from filter_fresh import filter_stream

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def definitions(filename, names, scope):
    path = ROOT / "training/original/validation" / filename
    nodes = [n for n in ast.parse(path.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_protocol.py SAMPLER_BINARY NEW_WORK_DIRECTORY")
    binary, work = (Path(x).resolve() for x in sys.argv[1:])
    work.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((HERE / "exclusions/manifest.json").read_text())
    extension = json.loads((HERE / "exclusions/exp720-extension.json").read_text())
    record = extension["output"]
    path = HERE / "exclusions" / record["path"]
    assert path.stat().st_size == record["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    with np.load(path) as packed:
        added = packed["keys"]
    assert len(added) == extension["added_pairs"] and np.all(added[1:] > added[:-1])
    names = [r["Name"] for r in json.loads((ROOT / "source/arch/SRB_Port.json").read_text())["Port"]]
    ports = dict(zip(names, range(len(names))))

    def decode(value):
        cell, port = divmod(int(value), 496)
        y, x = divmod(cell, 120)
        return f"SRB_{x}_{y}/{names[port]}"

    selected_sources, selected_pairs = set(), set()
    source_count = pair_count = 0
    last = -1
    for record in manifest["outputs"]:
        path = HERE / "exclusions" / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        with np.load(path) as packed:
            source_file = "ids" in packed.files
            a = packed["ids" if source_file else "keys"]
        assert a.ndim == 1 and np.all(a[1:] > a[:-1])
        if source_file:
            assert np.all(a < 120 * 550 * 496)
            assert not np.isin(added >> 32, a).any()
            source_count += len(a)
            selected_sources.update(map(int, a[::max(1, len(a) // 100)]))
        else:
            assert not np.intersect1d(added, a, assume_unique=True).size
            assert int(a[0]) > last
            last = int(a[-1])
            assert np.all((a >> 32) < 120 * 550 * 496)
            assert np.all((a & 0xffffffff) < 120 * 550 * 496)
            pair_count += len(a)
            selected_pairs.update(map(int, a[::max(1, len(a) // 10)]))
    assert (source_count, pair_count) == (manifest["source_pins"], manifest["history_pairs"])
    assert pair_count + len(added) == extension["combined_pairs"]
    selected_pairs.update(map(int, added[::max(1, len(added) // 20)]))
    for key in selected_pairs:
        assert pin_id(decode(key >> 32), ports) == key >> 32
        assert pin_id(decode(key & 0xffffffff), ports) == key & 0xffffffff
        assert key >> 32 not in selected_sources
    mapping = json.loads((ROOT / "path_witness/query_source/mapping.json").read_text())
    sources, targets = mapping["sources"][:2], mapping["targets"][:2]
    rejected = [(decode(s), f"SRB_20_100/{targets[0]}") for s in sorted(selected_sources)]
    rejected += [(decode(k >> 32), decode(k & 0xffffffff)) for k in sorted(selected_pairs)]
    accepted = [(f"SRB_{20+i}_{100+j}/{s}", f"SRB_40_{200+i}/{t}")
                for i in range(4) for j, s in enumerate(sources) for t in targets]
    assert all(pin_id(a, ports) not in selected_sources
               and ((pin_id(a, ports) << 32) | pin_id(b, ports)) not in selected_pairs
               for a, b in accepted)
    rows = rejected[:len(rejected)//2] + accepted[:8] + rejected[len(rejected)//2:] + accepted[8:]
    text = "From,To\n" + "".join(f"{a},{b}\n" for a, b in rows + accepted)
    old = definitions("exp642_fresh_symmetric.py", ("filter_stream",), {})
    original_out, portable_out = io.BytesIO(), io.StringIO()
    population, _, expected = old["filter_stream"](
        io.BytesIO(text.encode()), original_out,
        {decode(s).encode() for s in selected_sources},
        {f"{decode(k >> 32)},{decode(k & 0xffffffff)}".encode() for k in selected_pairs},
        sources, targets, 16)
    actual_population, actual = filter_stream(
        io.StringIO(text), portable_out, selected_sources, selected_pairs, ports,
        sources, targets, 16)
    assert original_out.getvalue() == portable_out.getvalue().encode()
    assert population == actual_population and all(actual[k] == v for k, v in expected.items())

    def write(path, value):
        Path(path).write_text(json.dumps(value, indent=2) + "\n")

    sample = definitions("exp683_expanded_exact.py", ("sampling_plan", "sampler_self_check"),
                         dict(np=np, struct=struct, subprocess=subprocess, json=json,
                              BUILD=work, ROOT=work, write=write))
    plans = {}
    for case, count, seed, frozen in (
        ("100m", 32, 20261024685, "exp685/expanded/freeze.json"),
        ("1b", 64, 20261025683, "exp683/1b/freeze.json"),
        ("exp720-100m", 32, 20261027720, "exp720/expanded/freeze.json"),
    ):
        population_path = HERE / ("exp720-pair-populations.json" if case == "exp720-100m"
                                  else f"population-{case}.json")
        population = np.asarray(json.loads(population_path.read_text()), "<u4")
        path = work / f"sampling-plan-{case}.bin"
        sample["sampling_plan"](path, population, count, seed)
        record = next(r for r in json.loads((ROOT / "validation/results" / frozen).read_text())["files"]
                      if r["path"].endswith("sampling-plan.bin"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == record["sha256"] and path.stat().st_size == record["bytes"]
        plans[case] = dict(sha256=digest, matches_historical=True)
    sample["sampler_self_check"](binary)
    report = dict(passed=True, source_pins=source_count, historical_pairs=pair_count,
                  exp720_additional_pairs=len(added), exp720_total_pairs=pair_count + len(added),
                  exp720_extension_disjoint=True,
                  exclusion_hashes_passed=True, filter_fixture=actual,
                  filter_output_matches_original=True, sampling_plans=plans,
                  sampler_self_check_passed=True, complete_request_populations_generated=0,
                  complete_estimator_runs=0)
    write(work / "report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
