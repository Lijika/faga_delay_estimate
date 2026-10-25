#!/usr/bin/env python3
"""Train full-port near nominal factors on l7; evaluate requests only on r9."""
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import time

import numpy as np

import exp575_distance_budget as previous

local = previous.local
read, write, identity, save = local.read, local.write, local.identity, local.save
ROOT, BUILD = Path('validation/results/exp586'), Path('build/exp586')
PLAN = Path('experiment/实验586-短距名义背景的INT8容量再分配.md')
LEFT, RIGHT, SEED = 59904, 264960, 20261022586


def main():
    assert socket.gethostname() == 'lhj-NF5280M5'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp586')
    assert os.environ['OPENBLAS_NUM_THREADS'] == '8'
    resource.setrlimit(resource.RLIMIT_CPU, (18000, 18000))
    resource.setrlimit(resource.RLIMIT_AS, (96 << 30, 96 << 30))
    started, cpu, free = time.monotonic(), time.process_time(), shutil.disk_usage('.').free
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    previous.ROOT, previous.BUILD = ROOT, BUILD
    local.ROOT, local.BUILD, local.old.ROOT = ROOT, BUILD, ROOT
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    shutil.copyfile(local.old.PREPARATION / 'mapping.json', ROOT / 'mapping.json')
    arrays, source_assets = previous.previous.source_arrays()
    reference = read('../exp575/validation/results/exp575/group-0-r192-diagnostics.json')
    assert reference['full_port_pairs'] == LEFT and reference['geometries'] == 4800
    far = [Path('../exp575/build/exp575/group-1-r96-' + s + '.npy') for s in ('left', 'right')]
    source_files = list(Path('validation').glob('*.py')) + [PLAN, ROOT / 'mapping.json', *far]
    write(ROOT / 'freeze.json', dict(protocol=identity(PLAN), source_assets=source_assets,
          files=[identity(p) for p in source_files], near_reference=reference,
          numpy=np.__version__, installed_svd_signature=str(inspect.signature(local.svd)),
          hostname=socket.gethostname(), seed=SEED))
    values = local.old.materialize(ROOT / 'materialization.json')
    assert values.shape == (LEFT, RIGHT)
    assert read(ROOT / 'materialization.json')['matrix_sha256'] == \
        'c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86'
    center = arrays['center']
    save('center', center)
    keys = np.flatnonzero(previous.QSUM <= 3)
    assert len(keys) == 4800
    save('near-keys', keys.astype('<i4'))
    left, right, fitted = local.fit(values, center, keys, 768, 'near-r768', np.random.default_rng(SEED))
    assert left.shape == (LEFT, 768) and right.shape == (4800, 768)
    factors = [save('near-left', left), save('near-right', right)]
    records = []
    for rank in (512, 768):
        diagnostic = previous.diagnostics(values, center, keys, left[:, :rank], right[:, :rank], 'N' + str(rank))
        reduction = 1 - diagnostic['absolute'] / reference['absolute']
        records.append(dict(rank=rank, diagnostic=diagnostic, relative_l1_reduction=reduction,
                            training_gate=bool(reduction >= .20)))
    assert records[1]['diagnostic']['squared'] <= records[0]['diagnostic']['squared'] + 1e-9
    write(ROOT / 'training.json', dict(all_training_checks=True, shape=[LEFT, RIGHT], port_pairs=LEFT,
          near_geometries=len(keys), factors=factors, fit=fitted, candidates=records,
          center=identity(BUILD / 'center.npy'), far_factors=[identity(p) for p in far],
          cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage('.').free,
          real_request_scoring_started=False))
    print('EXP586_TRAINING_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
