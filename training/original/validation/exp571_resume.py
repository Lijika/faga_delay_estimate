#!/usr/bin/env python3
"""Resume exp571 from its completed I factors after the original CPU limit exits."""
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np

import exp571_local_subspaces as experiment

ORIGINAL = Path("../exp571")
ROOT, BUILD = experiment.ROOT, experiment.BUILD


def main():
    assert socket.gethostname() == "lhj-NF5280M5"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp571-recovery-01")
    assert os.environ["OPENBLAS_NUM_THREADS"] == "8"
    previous_run = experiment.read(ORIGINAL / "driver.run.json")
    assert previous_run["exit_code"] == -9 and previous_run["cpu_s"] >= 17990
    resource.setrlimit(resource.RLIMIT_CPU, (36000, 36000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage(".").free
    assert not ROOT.exists()
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    local = experiment.local
    local.ROOT, local.BUILD, local.old.ROOT = ROOT, BUILD, ROOT
    for name in ("mapping.json", "protocol-original.md", "initial-router.json", "initial-router-config.json",
                 "I-model.json", "G-reference-diagnostics.json", "I-diagnostics.json", "installed-library-help.txt"):
        shutil.copyfile(ORIGINAL / ROOT / name, ROOT / name)
    frozen = experiment.read(ORIGINAL / ROOT / "freeze.json")
    model = experiment.read(ROOT / "I-model.json")
    source_files = []
    for asset in model["assets"]:
        source = ORIGINAL / asset["path"]
        actual = experiment.identity(source)
        assert (actual["bytes"], actual["sha256"]) == (asset["bytes"], asset["sha256"])
        os.link(source, asset["path"])
        source_files.append(actual)
    for name in ("center.npy", "initial-router.json", "initial-native-leaf.npy", "initial-regions.npy"):
        source = ORIGINAL / BUILD / name
        os.link(source, BUILD / name)
        source_files.append(experiment.identity(source))
    shutil.copyfile(ORIGINAL / ROOT / "freeze.json", ROOT / "initial-freeze.json")
    frozen.update(files=[experiment.identity(Path(__file__)), experiment.identity(Path(experiment.__file__)),
                         experiment.identity(ROOT / "initial-freeze.json")],
                  initial_model_sources=source_files, cpu_budget_s=36000,
                  recovery_from=experiment.identity(ORIGINAL / "driver.run.json"),
                  algorithm_parameters_changed=False, quality_gates_changed=False)
    experiment.write(ROOT / "freeze.json", frozen)
    center = np.load(BUILD / "center.npy")
    left, right, regions = (np.load(BUILD / ("I-" + key + ".npy")) for key in ("left", "right", "regions"))
    values = local.old.materialize(ROOT / "materialization.json")
    assert experiment.read(ROOT / "materialization.json")["matrix_sha256"] == \
        "c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86"
    initial, energy = experiment.diagnostics(values, center, left, right, regions, "I-recovery-check")
    saved = experiment.read(ROOT / "I-diagnostics.json")
    for metric in ("squared", "absolute", "input_energy"):
        assert abs(initial[metric] - saved[metric]) <= 1e-9 * max(1., abs(saved[metric]))
    rng = np.random.default_rng(experiment.SEED)
    # Replay the initial range draws so both planned sweeps keep the original RNG state.
    for count in np.bincount(regions, minlength=len(left)):
        rng.standard_normal((int(count), experiment.RANK + 16))
    left, right, regions, residual = experiment.improve(
        values, center, left, right, regions, energy, model["residual_energy"], rng)
    final, restored_energy = experiment.diagnostics(values, center, left, right, regions, "K")
    assert np.allclose(restored_energy, energy, rtol=1e-12, atol=1e-8)
    assert abs(final["squared"] - residual) <= 1e-9 * final["input_energy"]
    models = [model, experiment.export_model("K", left, right, regions, residual)]
    baseline = experiment.read(ROOT / "G-reference-diagnostics.json")
    reduction = 1 - final["absolute"] / baseline["absolute"]
    new_bytes = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    assert new_bytes < 1_500_000_000
    experiment.write(ROOT / "training.json", dict(all_training_checks=True, shape=[experiment.LEFT, experiment.RIGHT],
        source_ports=208, target_ports=288, port_pairs=experiment.LEFT, models=models,
        center=experiment.identity(BUILD / "center.npy"), reference=baseline, initial=saved, final=final,
        relative_l1_reduction_vs_G=reduction, fixed_l1_gate_passed=bool(reduction >= .02),
        independent_tests=False, real_request_scoring_started=False, new_asset_bytes=new_bytes,
        freeze=experiment.identity(ROOT / "freeze.json"), cpu_s=time.process_time() - cpu,
        wall_s=time.monotonic() - started, rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        disk_free_start=free, disk_free_end=shutil.disk_usage(".").free))
    print("EXP571_COMPLETE_RECOVERED_TRAINING", reduction, bool(reduction >= .02), flush=True)


if __name__ == "__main__":
    main()
