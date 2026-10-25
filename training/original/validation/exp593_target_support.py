#!/usr/bin/env python3
"""Train six fixed residual ablations on l7; audit full-port OOF only on r9."""
import gc
from pathlib import Path
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp587/validation').resolve()))
from exp587_background_adaptation import identity, read, write, checked, PARAMS, TRACE

ROOT, BUILD = Path('validation/results/exp593'), Path('build/exp593')
PLAN = Path('experiment/实验593-方向背景残差目标与叶支持的配对消融.md')
ARMS = ('K1', 'K32', 'T1', 'T32', 'TW32', 'G32')
ROWS = 1000000


def load():
    frozen = read(ROOT / 'export.json')
    checked('../exp585/build/exp585/training.npz', frozen['training'])
    checked(BUILD / 'targets.npz', frozen['targets'])
    with np.load('../exp585/build/exp585/training.npz') as packed:
        data = {k: packed[k] for k in packed.files}
    with np.load(BUILD / 'targets.npz') as packed:
        data.update({k: packed[k] for k in packed.files})
    data['features'] = np.ascontiguousarray(data['features'][:, :53])
    assert data['features'].shape == (ROWS, 53) and np.isfinite(data['features']).all()
    assert data['truth'].shape == (ROWS,) and np.all(data['truth'] > 0)
    assert np.unique(data['pair']).size == 59904
    for fold in range(3):
        test = data['folds'] == fold
        assert np.unique(data['pair'][test]).size == 59904
        assert np.unique(data['pair'][~test]).size == 59904
        assert not np.intersect1d(data['clusters'][test], data['clusters'][~test]).size
    return data


def export():
    assert socket.gethostname() == 'lhj-R4900-G3'
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    prior = read('../exp585/validation/results/exp585/export.json')
    training = checked('../exp585/build/exp585/training.npz', prior['training'])
    audit = read('../exp589/validation/results/exp589/audit.json')['D64']
    path = '../exp589/build/exp589/D64-trace.bin'
    trace_id = checked(path, audit['trace'])
    trace = np.memmap(path, dtype=TRACE, mode='r', shape=(ROWS,))
    with np.load('../exp585/build/exp585/evaluation.npz') as packed:
        truth = packed['truth']
    np.savez_compressed(BUILD / 'targets.npz', D64=trace['base'].copy(), truth=truth)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    fixed_raw = checked('../exp576/build/exp576/R8.f32',
                        read('../exp576/validation/results/exp576/R8.json')['raw'])
    write(ROOT / 'export.json', dict(training=training, targets=identity(BUILD / 'targets.npz'),
        d64_trace=trace_id, protocol=identity(ROOT / 'protocol-original.md'),
        evaluation=identity('../exp585/build/exp585/evaluation.npz'),
        fixed_raw=fixed_raw, rows=ROWS, unique_rows=ROWS, port_pairs=59904))
    data = load()
    assert np.array_equal(trace['features'].copy().view('u4'), data['features'].view('u4'))
    assert np.array_equal(trace['mandatory'], data['mandatory'])
    print('EXP593_EXPORTED', identity(BUILD / 'targets.npz'), flush=True)


def parameters(arm):
    return dict(PARAMS, min_child_weight=1 if arm in ('K1', 'T1') else 32)


def train():
    assert socket.gethostname() == 'lhj-NF5280M5'
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    data = load()
    for arm in ARMS:
        features = data['features'].copy() if arm == 'G32' else data['features']
        if arm == 'G32':
            features[:, :26] = 0
        target = (data['d0'] if arm.startswith('K') else data['truth'] - data['mandatory']) - data['D64']
        divisor = data['truth'] if arm == 'TW32' else np.maximum(data['d0'] + data['mandatory'], 128)
        for fold in range(3):
            for route in range(16):
                stem = f'{arm}-{fold}-{route}'
                path = BUILD / (stem + '.json')
                record_path = ROOT / ('model-' + stem + '.json')
                if record_path.exists():
                    record = read(record_path)
                    assert record['params'] == parameters(arm) and record['rounds'] == 8
                    checked(path, record['model'])
                    continue
                assert not path.exists()
                learn = (data['folds'] != fold) & (data['routes'] == route)
                started, cpu = time.monotonic(), time.process_time()
                dm = xgb.DMatrix(features[learn], label=target[learn].astype('<f4'),
                    weight=(1000 / divisor[learn]).astype('<f4'), nthread=16)
                booster = xgb.train(parameters(arm), dm, num_boost_round=8)
                booster.save_model(path)
                if arm == 'G32':
                    for tree in read(path)['learner']['gradient_booster']['model']['trees']:
                        assert all(f >= 26 for f, left in zip(tree['split_indices'], tree['left_children']) if left >= 0)
                write(record_path, dict(arm=arm, fold=fold, route=route, rounds=8,
                    params=parameters(arm), rows=int(learn.sum()),
                    port_pairs=int(np.unique(data['pair'][learn]).size), model=identity(path),
                    cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
                    offline_only=True))
                del dm, booster
                gc.collect()
        print('EXP593_TRAINED', arm, flush=True)
    write(ROOT / 'training.json', dict(complete=True, export=identity(ROOT / 'export.json'),
        driver=identity(__file__), models=[identity(p) for p in sorted(BUILD.glob('*.json'))]))


def evaluate():
    assert socket.gethostname() == 'lhj-R4900-G3'
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    sys.path.insert(0, str(Path('../exp582/validation').resolve()))
    import exp582_int8_geometry as common
    sys.path.insert(0, str(Path('../exp592/validation').resolve()))
    from exp592_xgb_audit import decode, points, transition
    common.speed.ROOT = ROOT
    common.complete.trees.BUILD = BUILD
    data = load()
    with np.load('../exp585/build/exp585/evaluation.npz') as packed:
        partitions = {k[10:]: packed[k] for k in packed.files if k.startswith('partition_')}
    x = data['features'][:, 8] + data['features'][:, 6]
    y = data['features'][:, 9] + data['features'][:, 7]
    partitions.update(near_axis=((np.abs(x) < 20) | (np.abs(y) < 24)).astype('i4'),
        forced=data['features'][:, 52].astype('i4'),
        target_mismatch=(data['d0'] + data['mandatory'] != data['truth']).astype('i4'))
    assert 'distance' in partitions
    checked('../exp576/build/exp576/R8.f32', read(ROOT / 'export.json')['fixed_raw'])
    old_raw = np.fromfile('../exp576/build/exp576/R8.f32', '<f4')
    reference = decode(old_raw, data['D64'], data['mandatory'])
    for name, target in (('features.f32', '../exp576/build/exp576/features.f32'),
                         ('folds.u8', '../exp585/build/exp585/folds.u8'),
                         ('routes.u8', '../exp585/build/exp585/routes.u8')):
        (BUILD / name).symlink_to(Path(target).resolve())
    decoder = BUILD / 'routed-predict'
    common.speed.measured(['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64',
        '-mtune=generic', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
        '../exp587/tests/exp576_routed_residual.cpp', '-o', str(decoder)], 'compile-decoder')
    assert not (ROOT / 'compile-decoder.stderr').read_bytes()
    family = data['features'][:, 0].astype('i4')
    families, inverse = np.unique(family, return_inverse=True)
    assert len(families) == 26
    counts = np.bincount(inverse)
    sampled = np.random.default_rng(20261022593).integers(26, size=(9999, 26))
    alpha = .05 / len(ARMS) / 2
    results, eligible = {}, []
    for arm in ARMS:
        raw, paths = np.empty(ROWS, dtype='<f4'), []
        for fold in range(3):
            for route in range(16):
                path = BUILD / f'{arm}-{fold}-{route}.json'
                meta = read(ROOT / ('model-' + path.name))
                checked(path, meta['model'])
                booster = xgb.Booster(); booster.load_model(path)
                mask = (data['folds'] == fold) & (data['routes'] == route)
                raw[mask] = booster.predict(xgb.DMatrix(data['features'][mask], nthread=1))
                model = common.complete.trees.export_model(booster, f'native-{arm}-{fold}-{route}')
                paths.append(model['binary']['path'])
        listing = BUILD / (arm + '-models.txt')
        listing.write_text('16\n' + ''.join(p + '\n' for p in paths))
        native = BUILD / (arm + '-native.f32')
        run = common.speed.measured([str(decoder), str(BUILD / 'features.f32'), str(BUILD / 'folds.u8'),
            str(BUILD / 'routes.u8'), str(listing), str(native)], arm + '-independent')
        assert np.array_equal(np.fromfile(native, '<f4').view('u4'), raw.view('u4'))
        counters = read(ROOT / (arm + '-independent.stdout'))
        assert counters['port_pairs'] == 59904 and counters['threads'] == 1 and counters['kernel_allocations'] == 0
        prediction = decode(raw, data['D64'], data['mandatory'])
        stats = transition(prediction, reference, data['truth'], partitions)
        score = points(prediction, data['truth'])
        delta = score - points(reference, data['truth'])
        sums = np.bincount(inverse, weights=score)
        diffs = np.bincount(inverse, weights=delta)
        denominator = counts[sampled].sum(axis=1)
        stats['simultaneous_ci_accuracy_pp'] = np.quantile(sums[sampled].sum(axis=1) / denominator, [alpha, 1-alpha]).tolist()
        stats['simultaneous_ci_delta_pp'] = np.quantile(diffs[sampled].sum(axis=1) / denominator, [alpha, 1-alpha]).tolist()
        stats['quality_gate'] = bool(stats['delta_accuracy_pp'] >= .02
            and stats['simultaneous_ci_delta_pp'][0] > 0
            and stats['simultaneous_ci_accuracy_pp'][0] > 98.2
            and all(g['delta_accuracy_pp'] >= -.03 for name, group in stats['groups'].items()
                    if name in ('distance', 'near_axis') for g in group.values()))
        stats.update(raw=identity(native), native_bitwise_equal=True, independent_run=run)
        results[arm] = stats
        if stats['quality_gate']:
            eligible.append(arm)
        write(ROOT / (arm + '-report.json'), stats)
        print('EXP593_EVALUATED', arm, stats['candidate']['accuracy_pp'], stats['delta_accuracy_pp'], stats['quality_gate'], flush=True)
    selected = None
    if eligible:
        best = max(results[a]['candidate']['accuracy_pp'] for a in eligible)
        selected = next(a for a in ('G32', 'T32', 'TW32', 'K32', 'T1', 'K1')
            if a in eligible and best - results[a]['candidate']['accuracy_pp'] <= .005)
    write(ROOT / 'evaluation.json', dict(results=results, selected=selected, eligible=eligible,
        rows=ROWS, unique_rows=ROWS, port_pairs=59904, training=identity(ROOT / 'training.json'),
        complete_program_verified=False))
    print('EXP593_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp593')
    assert sys.argv[1:] in (['export'], ['train'], ['evaluate'])
    {'export': export, 'train': train, 'evaluate': evaluate}[sys.argv[1]]()
