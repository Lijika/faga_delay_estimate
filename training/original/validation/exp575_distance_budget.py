#!/usr/bin/env python3
"""Fit complete-port distance groups with distinct, fixed rank budgets on l7."""
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np

import exp571_local_subspaces as previous

local = previous.local
read, write, identity, save = local.read, local.write, local.identity, local.save
ROOT, BUILD = Path("validation/results/exp575"), Path("build/exp575")
PLAN = Path("experiment/实验575-距离分组的非均匀秩预算.md")
LEFT, RIGHT, SEED = 59904, 264960, 20261021575
QSUM = ((np.arange(RIGHT) % 552) // 46 + np.arange(RIGHT) % 46)
BAND = np.select((QSUM == 0, QSUM <= 3, QSUM <= 15), (0, 1, 2), default=3)


def diagnostics(values, center, keys, left, right, name):
    totals = np.zeros((4, 2))
    energy = 0.
    for start, block in local.blocks(values, center, keys):
        energy += float(np.square(block).sum())
        residual = block - left[start:start + len(block)] @ right.T
        for band in range(4):
            part = residual[:, BAND[keys] == band]
            totals[band] += float(np.square(part).sum()), float(np.abs(part).sum())
    counts = np.bincount(BAND[keys], minlength=4) * LEFT
    assert int(counts.sum()) == LEFT * len(keys) and np.isfinite(totals).all()
    result = dict(name=name, full_port_pairs=LEFT, geometries=len(keys), values=int(counts.sum()),
                  input_energy=energy, squared=float(totals[:, 0].sum()), absolute=float(totals[:, 1].sum()),
                  by_quotient_sum=[dict(band=b, values=int(counts[b]), squared=float(totals[b, 0]),
                                         absolute=float(totals[b, 1])) for b in range(4)])
    write(ROOT / (name + "-diagnostics.json"), result)
    print("EXP575_DIAGNOSTICS", name, result["squared"], result["absolute"], flush=True)
    return result


def aggregate(parts, name):
    result = dict(name=name, full_port_pairs=LEFT, geometries=RIGHT, values=LEFT * RIGHT)
    for metric in ("input_energy", "squared", "absolute"):
        result[metric] = sum(p[metric] for p in parts)
    result["by_quotient_sum"] = [dict(band=b, **{key: sum(p["by_quotient_sum"][b][key] for p in parts)
                                               for key in ("values", "squared", "absolute")}) for b in range(4)]
    assert result["values"] == sum(b["values"] for b in result["by_quotient_sum"])
    return result


def export(name, keys, left, right, diagnostic, origin):
    rank = left.shape[1]
    assert left.shape == (LEFT, rank) and right.shape == (len(keys), rank)
    assert np.abs(left.T @ left - np.eye(rank)).max() < 1e-10
    li, le = previous.quantize(left, (0,))
    ri, re = previous.quantize(right, (0,))
    exponent = le.astype(np.int64) + re
    minimum = int(exponent.min())
    lm, rm = np.abs(li.astype(np.int32)).max(axis=0), np.abs(ri.astype(np.int32)).max(axis=0)
    bound = sum((int(a) * int(b)) << int(e - minimum) for a, b, e in zip(lm, rm, exponent))
    assert bound < 2**53 and minimum > -1022 and exponent.max() < 970
    arrays = dict(keys=keys.astype("<i4"), left=left, right=right, **{
        "left-integers": li, "right-integers": ri, "left-exponent": le, "right-exponent": re})
    assets = [save(name + "-" + suffix, np.ascontiguousarray(value)) for suffix, value in arrays.items()]
    record = dict(name=name, rank=rank, port_pairs=LEFT, geometries=len(keys), origin=origin,
                  diagnostic=diagnostic, assets=assets, integer_sum_bound=bound, common_exponent=minimum,
                  factor_bytes=li.nbytes + ri.nbytes + le.nbytes + re.nbytes)
    write(ROOT / (name + "-part.json"), record)
    return record


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp575")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    local.ROOT, local.BUILD, local.old.ROOT = ROOT, BUILD, ROOT
    shutil.copyfile(PLAN, ROOT / "protocol-original.md")
    shutil.copyfile(local.old.PREPARATION / "mapping.json", ROOT / "mapping.json")
    arrays, source_assets = previous.source_arrays()
    reference_path = Path("../exp571-recovery-01/validation/results/exp571/G-reference-diagnostics.json")
    reference = read(reference_path)
    assert reference["full_port_pairs"] == LEFT and reference["geometries"] == RIGHT
    assert abs(reference["absolute"] - 69096998.54782021) < 1e-6
    shutil.copyfile(reference_path, ROOT / "G-reference-diagnostics.json")
    source_files = [p for p in Path("validation").glob("*.py")]
    source_files += [PLAN, ROOT / "mapping.json", ROOT / "protocol-original.md", reference_path]
    (ROOT / "installed-svd-help.txt").write_text(str(inspect.signature(local.svd)) + "\n" + local.svd.__doc__)
    write(ROOT / "freeze.json", dict(files=[identity(p) for p in source_files], source_assets=source_assets,
          shape=[LEFT, RIGHT], seed=SEED, split_quotient_sum=3, near_ranks=[128, 192], far_rank=96,
          cpu_budget_s=18000, hostname=socket.gethostname(), disk_free_bytes=free))
    values = local.old.materialize(ROOT / "materialization.json")
    assert read(ROOT / "materialization.json")["matrix_sha256"] == \
        "c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86"
    center = arrays["center"]
    center_asset = save("center", center)
    gleft, gright = arrays["G-left"][0], arrays["G-right"]
    regions = (QSUM > 3).astype("u1")
    region_asset = save("regions", regions)
    assert np.bincount(regions).tolist() == [4800, 260160]
    rng, selected, candidates = np.random.default_rng(SEED), {}, []
    for group, maximum, ranks in ((0, 192, (128, 192)), (1, 96, (96,))):
        keys = np.flatnonzero(regions == group)
        left, right, fit = local.fit(values, center, keys, maximum, f"group-{group}-fit", rng)
        overlap = np.square(left.T @ gleft).sum(axis=1)
        write(ROOT / f"group-{group}-overlap.json", dict(rank=maximum, g_rank=96,
              squared_projection_of_each_new_vector=overlap.tolist(), fit=fit))
        gdiag = dict(full_port_pairs=LEFT, geometries=len(keys), values=LEFT * len(keys),
                     by_quotient_sum=[dict(b) if (b["band"] <= 1) == (group == 0) else
                                       dict(band=b["band"], values=0, squared=0., absolute=0.)
                                       for b in reference["by_quotient_sum"]])
        for metric in ("squared", "absolute"):
            gdiag[metric] = sum(b[metric] for b in gdiag["by_quotient_sum"])
        for rank in ranks:
            name = f"group-{group}-r{rank}"
            diagnostic = diagnostics(values, center, keys, left[:, :rank], right[:, :rank], name)
            fallback = diagnostic["absolute"] >= gdiag["absolute"]
            if fallback:
                chosen_left, chosen_right = gleft, gright[keys]
                chosen_diag = dict(gdiag, name=name + "-G", input_energy=diagnostic["input_energy"])
            else:
                chosen_left, chosen_right = left[:, :rank], right[:, :rank]
                chosen_diag = diagnostic
            selected[(group, rank)] = export(name, keys, chosen_left, chosen_right, chosen_diag,
                                              "G" if fallback else "conditional")
            candidates.append(dict(group=group, maximum_rank=rank, new=diagnostic,
                                   reference=gdiag, selected=selected[(group, rank)]["name"], origin="G" if fallback else "conditional"))
    models = []
    for near_rank, upper in ((128, 78403072), (192, 86685696)):
        parts = [selected[(0, near_rank)], selected[(1, 96)]]
        diagnostic = aggregate([p["diagnostic"] for p in parts], f"N{near_rank}")
        assert abs(diagnostic["input_energy"] - reference["input_energy"]) < 1e-9 * reference["input_energy"]
        reduction = 1 - diagnostic["absolute"] / reference["absolute"]
        assert reduction >= -1e-12
        size = sum(p["factor_bytes"] for p in parts) + center.nbytes + regions.nbytes
        assert size <= upper
        record = dict(name=f"N{near_rank}", parts=parts, diagnostic=diagnostic, table_bytes=size,
                      relative_l1_reduction_vs_G=reduction, fixed_l1_gate_passed=bool(reduction >= .02))
        write(ROOT / (record["name"] + "-model.json"), record)
        models.append(record)
        print("EXP575_MODEL", record["name"], reduction, record["fixed_l1_gate_passed"], size, flush=True)
    new_bytes = sum(p.stat().st_size for p in BUILD.iterdir() if p.is_file())
    assert new_bytes < 1500000000
    write(ROOT / "training.json", dict(all_training_checks=True, shape=[LEFT, RIGHT], port_pairs=LEFT,
          center=center_asset, regions=region_asset, reference=reference, candidates=candidates, models=models,
          freeze=identity(ROOT / "freeze.json"), real_request_scoring_started=False, new_asset_bytes=new_bytes,
          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP575_COMPLETE_TRAINING", flush=True)


if __name__ == "__main__":
    main()
