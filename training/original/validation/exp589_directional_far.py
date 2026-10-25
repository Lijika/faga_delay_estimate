#!/usr/bin/env python3
"""Fit four complete-port far spaces offline on l7; request tests stay on r9."""
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
ROOT, BUILD = Path('validation/results/exp589'), Path('build/exp589')
PLAN = Path('experiment/实验589-远域方向子空间与近域固定背景.md')
LEFT, RIGHT, SEED = 59904, 264960, 20261022589


def main():
    assert socket.gethostname() == 'lhj-NF5280M5'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp589')
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
    near = read('../exp586/validation/results/exp586/training.json')
    center_path = Path('../exp586/build/exp586/center.npy')
    actual = identity(center_path)
    assert all(actual[k] == near['center'][k] for k in ('sha256', 'bytes'))
    center = np.load(center_path)
    assert center.shape == (LEFT,) and center.dtype.str == '<i2'
    far_paths = [Path('../exp575/build/exp575/group-1-r96-' + s + '.npy')
                 for s in ('left', 'right')]
    far = [np.load(p, mmap_mode='r') for p in far_paths]
    assert far[0].shape == (LEFT, 96) and far[1].shape == (260160, 96)
    reference = read('../exp575/validation/results/exp575/group-1-r96-diagnostics.json')
    assert reference['full_port_pairs'] == LEFT and reference['geometries'] == 260160
    source_files = list(Path('validation').glob('*.py')) + [PLAN, ROOT / 'mapping.json', *far_paths, center_path]
    write(ROOT / 'freeze.json', dict(protocol=identity(PLAN),
          files=[identity(p) for p in source_files], reference=reference,
          numpy=np.__version__, installed_svd_signature=str(inspect.signature(local.svd)),
          hostname=socket.gethostname(), seed=SEED))
    values = local.old.materialize(ROOT / 'materialization.json')
    assert values.shape == (LEFT, RIGHT)
    assert read(ROOT / 'materialization.json')['matrix_sha256'] == \
        'c3aaeca23271dbea1ff4badc8b65b4f60f6723291dc5da4a524ba8df25dd8f86'
    save('center', center)
    keys = np.flatnonzero(previous.QSUM > 3)
    assert len(keys) == 260160
    left = np.empty((4, LEFT, 96), dtype='<f8')
    right = np.empty((260160, 96), dtype='<f8')
    diagnostics = {rank: [] for rank in (64, 96)}
    fitted, references = [], []
    rng = np.random.default_rng(SEED)
    for direction in range(4):
        sl = slice(direction * 65040, (direction + 1) * 65040)
        selected = keys[sl]
        assert len(selected) == 65040 and np.all(selected // 66240 == direction)
        ref = previous.diagnostics(values, center, selected, far[0], far[1][sl],
                                   f'direction-{direction}-reference')
        references.append(ref)
        left[direction], right[sl], fit = local.fit(values, center, selected, 96,
                                                  f'direction-{direction}-r96', rng)
        fitted.append(fit)
        for rank in (64, 96):
            diagnostic = previous.diagnostics(values, center, selected,
                left[direction, :, :rank], right[sl, :rank], f'D{rank}-{direction}')
            diagnostics[rank].append(diagnostic)
        assert diagnostics[96][-1]['squared'] <= diagnostics[64][-1]['squared'] + 1e-9
    assert abs(sum(r['absolute'] for r in references) - reference['absolute']) < 1e-6
    factors = [save('far-left', left), save('far-right', right)]
    records = []
    for rank in (64, 96):
        absolute = sum(r['absolute'] for r in diagnostics[rank])
        reduction = 1 - absolute / reference['absolute']
        records.append(dict(rank=rank, absolute=absolute, groups=diagnostics[rank],
                            relative_l1_reduction=reduction, training_gate=bool(reduction >= .02)))
    write(ROOT / 'training.json', dict(all_training_checks=True, shape=[LEFT, RIGHT],
          port_pairs=LEFT, far_geometries=len(keys), factors=factors, fit=fitted,
          reference=reference, directional_reference=references, candidates=records,
          center=identity(BUILD / 'center.npy'), cpu_s=time.process_time() - cpu,
          wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_start=free, disk_free_end=shutil.disk_usage('.').free,
          real_request_scoring_started=False))
    print('EXP589_TRAINING_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
