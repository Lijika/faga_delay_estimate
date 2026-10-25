#!/usr/bin/env python3
"""Describe the completed matched-path result without adding labels or fitting."""
import ast
from pathlib import Path
import socket

import numpy as np

import exp705_matched_positions as study


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp705")
    root, build = study.ROOT, study.BUILD
    report = study.read(root / "report.json")
    assert report["all_checks_passed"]
    for item in report["files"]:
        study.check(item["path"], item)
    query = np.fromfile(build / "queries.bin", "<i4", offset=12).reshape(-1, 10)
    sums = np.fromfile(build / "paths.summary.i32", "<i4").reshape(-1, 8)
    length = np.fromfile(build / "paths.lengths.u32", "<u4").reshape(-1, 4)
    cross = np.fromfile(build / "cross.i32", "<i4").reshape(-1, 4, 4, 7)
    _, _, _, _, dx, dy, _ = study.graph()
    ax, ay, fee = study.landing(query[:, 0], query[:, 1], dx[query[:, 8]], dy[query[:, 8]])
    source = Path("../exp677/validation/exp677_map_events.py")
    functions = [n for n in ast.parse(source.read_text()).body
                 if isinstance(n, ast.FunctionDef) and n.name in ("events", "self_check")]
    assert len(functions) == 2
    scope = dict(np=np)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), scope)
    blocks = study.read(study.ARCH / "SRB_Gap.json")["Gap"]["Block"]
    scope["self_check"](blocks)
    h, v, _, _ = scope["events"](np.column_stack((ax, ay, query[:, 2:4])), blocks)
    event = (h + 2 * v).reshape(-1, 4)
    post_block = (sums[:, 2] - fee).reshape(-1, 4)
    assert np.all(post_block >= 0) and np.all(post_block % 292 == 0)
    ordinary = (event == 0) & (post_block == 0)
    uphill = cross[:, :, :, 6].astype(bool)
    off_diagonal = ~np.eye(4, dtype=bool)[None, :, :]
    valid = np.isin(cross[:, :, :, 0], [0, 4])
    answer = (sums[:, 0] + sums[:, 2]).reshape(-1, 4)
    cost = np.where(valid & off_diagonal, cross[:, :, :, 4], 1 << 28)
    transfer = cost.min(axis=1)
    covered = transfer < (1 << 28)
    error = transfer - answer
    assert np.all(error[covered] >= 0)
    mismatch = cross[:, :, :, 0] == 3
    target = query.reshape(-1, 4, 10)
    xerror = cross[:, :, :, 2] - target[:, None, :, 2]
    yerror = cross[:, :, :, 3] - target[:, None, :, 3]
    assert np.all(yerror[mismatch] == 0) and np.all(xerror[mismatch] % 14 == 0)
    assert np.all(xerror[mismatch] != 0)
    first_invalid = np.isin(cross[:, :, :, 0], [1, 2])
    source_z = (target[:, :, 4] < 20)[:, :, None]
    assert not np.any(first_invalid & source_z & (cross[:, :, :, 1] == 0))
    groups = {}
    for name, mask in dict(all=uphill,
            both_event_zero=uphill & (event[:, :, None] == 0) & (event[:, None, :] == 0),
            both_ordinary_no_post_block=uphill & ordinary[:, :, None] & ordinary[:, None, :]).items():
        counts = np.bincount(cross[:, :, :, 0][mask], minlength=5)
        wrong = mask & mismatch
        shifts, amounts = np.unique(xerror[wrong], return_counts=True)
        fail = mask & first_invalid
        steps = cross[:, :, :, 1]
        groups[name] = dict(transfers=int(mask.sum()), reason_counts=counts.tolist(),
            changed_endpoint_x_shifts={str(int(a)): int(b) for a, b in zip(shifts, amounts)},
            invalid_transfers=int(fail.sum()),
            invalid_first_four=int((fail & (steps < 4)).sum()),
            invalid_last_four=int((fail & (steps >= length[:, :, None] - 4)).sum()))
    def transfer_stats(mask):
        have = mask & covered
        return dict(rows=int(mask.sum()), covered=int(have.sum()),
            exactly_recovered=int((have & (error == 0)).sum()),
            excess_quantiles_ps=np.quantile(error[have], [0, .5, .9, .95, .99, 1]).tolist())
    result = dict(all_checks_passed=True, descriptive_after_primary_result=True,
        changes_to_primary_gate=False, source_result=study.identity(root / "report.json"),
        full_word_transfer_excluding_own_path=True, inference_uses_oracle_words=True,
        groups=groups, held_out_position_transfer=dict(
            all=transfer_stats(np.ones_like(covered)),
            ordinary_no_post_block=transfer_stats(ordinary)),
        port_pairs=study.PAIRS, rows=study.PAIRS * 4, new_exact_rows=0, new_training_runs=0,
        complete_estimator_runs=0, files=[study.identity(p) for p in (Path(__file__), source)])
    study.write(root / "witness-groups.json", result)
    print("EXP705_WITNESSES", groups, result["held_out_position_transfer"], flush=True)


if __name__ == "__main__":
    main()
