#!/usr/bin/env python3
"""Adapt small residuals offline on l7; verify full-port predictions only on r9."""
import gc
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

ROOT, BUILD = Path('validation/results/exp587'), Path('build/exp587')
PLAN = Path('experiment/实验587-新背景与分区几何小修正的适配.md')
ROWS = 1000000
BACKGROUNDS = ('N512', 'N768')
ARMS = ('A8', 'P8', 'P16', 'W8', 'W16')
PARAMS = dict(objective='reg:absoluteerror', tree_method='hist', max_depth=4,
    max_bin=256, eta=.3, base_score=0, subsample=1., colsample_bytree=1.,
    min_child_weight=1, reg_lambda=1, seed=20261020554, nthread=16)
TRACE = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
    formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f4'],
    offsets=[0, 216, 224, 228, 232, 236], itemsize=240))


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def checked(path, expected):
    actual = identity(path)
    assert all(actual[k] == expected[k] for k in ('bytes', 'sha256')), path
    return actual


def r9():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp587')
    sys.path.insert(0, str(Path('../exp582/validation').resolve()))
    import exp582_int8_geometry as common
    common.speed.ROOT = ROOT
    common.complete.trees.BUILD = BUILD
    return common


def load_data():
    frozen = read(ROOT / 'export.json')
    checked('../exp585/build/exp585/training.npz', frozen['training'])
    checked(BUILD / 'backgrounds.npz', frozen['backgrounds'])
    with np.load('../exp585/build/exp585/training.npz') as packed:
        data = {k: packed[k] for k in packed.files}
    with np.load(BUILD / 'backgrounds.npz') as packed:
        data.update({k: packed[k] for k in packed.files})
    data['features'] = np.ascontiguousarray(data['features'][:, :53])
    assert data['features'].shape == (ROWS, 53) and np.isfinite(data['features']).all()
    assert np.unique(data['pair']).size == 59904
    assert np.isin(data['routes'], np.arange(16)).all()
    assert not np.any(data['near'] & (data['routes'] % 4 == 3))
    for fold in range(3):
        mask = data['folds'] == fold
        assert np.unique(data['pair'][mask]).size == 59904
        assert np.unique(data['pair'][~mask]).size == 59904
        assert not np.intersect1d(data['clusters'][mask], data['clusters'][~mask]).size
    return data


def export():
    r9()
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    original = read('../exp585/validation/results/exp585/export.json')
    training = checked('../exp585/build/exp585/training.npz', original['training'])
    with np.load(training['path']) as packed:
        features, mandatory, pair = (packed[k] for k in ('features', 'mandatory', 'pair'))
    keys_path = Path('../exp575/build/exp575/keys.i32')
    keys = np.fromfile(keys_path, '<i4').reshape(ROWS, 2)
    assert np.array_equal(keys[:, 0], pair)
    qx, qy = keys[:, 1] % 552 // 46, keys[:, 1] % 46
    arrays, traces = dict(near=qx + qy <= 3), {}
    freeze = read('../exp586/validation/results/exp586/candidate-freeze.json')
    audit = read('../exp586/validation/results/exp586/audit.json')
    for background in BACKGROUNDS:
        assert audit[background]['exact_integer_output']
        path = Path('../exp586/build/exp586') / (background + '-trace.bin')
        trace = np.memmap(path, dtype=TRACE, mode='r', shape=(ROWS,))
        assert np.array_equal(trace['features'].copy().view('u4'), features[:, :53].copy().view('u4'))
        assert np.array_equal(trace['mandatory'], mandatory)
        arrays[background] = trace['base'].copy()
        traces[background] = dict(trace=identity(path), binary=freeze['arms'][background]['binary'])
    np.savez_compressed(BUILD / 'backgrounds.npz', **arrays)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    write(ROOT / 'export.json', dict(training=training, backgrounds=identity(BUILD / 'backgrounds.npz'),
        traces=traces, keys=identity(keys_path), protocol=identity(ROOT / 'protocol-original.md'),
        rows=ROWS, port_pairs=59904, unique_rows=ROWS, near_rows=int(arrays['near'].sum()),
        fixed_raw=identity('../exp576/build/exp576/R8.f32'),
        fixed_record=identity('../exp576/validation/results/exp576/R8.json')))
    load_data()
    print('EXP587_EXPORTED', identity(BUILD / 'backgrounds.npz'), flush=True)


def fit(data, background, family, fold, route):
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    mask = data['routes'] == route
    if family != 'A':
        mask &= data['near']
    learn = mask & (data['folds'] != fold) if fold < 3 else mask
    rounds, floor = (8 if family == 'A' else 16), (32 if family == 'W' else 128)
    stem = f'{background}-{family}-{fold}-{route}'
    path = BUILD / (stem + '.json')
    record_path = ROOT / ('model-' + stem + '.json')
    if record_path.exists():
        record = read(record_path)
        assert record['params'] == PARAMS and record['rounds'] == rounds and record['floor'] == floor
        if record['model'] is not None:
            checked(path, record['model'])
        return
    if not learn.any():
        # Both large axes imply qx+qy>=4, outside the near domain.
        assert family != 'A' and route % 4 == 3 and not mask.any()
        write(record_path, dict(background=background, family=family, fold=fold, route=route,
            rounds=rounds, floor=floor, params=PARAMS, rows=0, port_pairs=0, model=None,
            unreachable_near_route=True, offline_only=True))
        return
    assert not path.exists(), path
    started, cpu = time.monotonic(), time.process_time()
    weights = (1000 / np.maximum(data['d0'][learn] + data['mandatory'][learn], floor)).astype('<f4')
    target = (data['d0'][learn] - data[background][learn]).astype('<f4')
    dm = xgb.DMatrix(data['features'][learn], label=target, weight=weights, nthread=16)
    booster = xgb.train(PARAMS, dm, num_boost_round=rounds)
    booster.save_model(path)
    write(record_path, dict(background=background, family=family, fold=fold, route=route,
        rounds=rounds, floor=floor, params=PARAMS, rows=int(learn.sum()),
        port_pairs=int(np.unique(data['pair'][learn]).size), model=identity(path),
        wall_s=time.monotonic() - started, cpu_s=time.process_time() - cpu, offline_only=True))
    print('EXP587_TRAINED', stem, int(learn.sum()), flush=True)
    del dm, booster
    gc.collect()


def train(final=False):
    assert socket.gethostname() == 'lhj-NF5280M5'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp587')
    data = load_data()
    if final:
        selected = read(ROOT / 'evaluation.json')['selected']
        assert selected
        work = [(selected['background'], selected['arm'][0], 3)]
    else:
        work = [(b, a, f) for b in BACKGROUNDS for a in ('A', 'P', 'W') for f in range(3)]
    for background, family, fold in work:
        for route in range(16):
            fit(data, background, family, fold, route)
    write(ROOT / ('final-training.json' if final else 'training.json'), dict(
        complete=True, export=identity(ROOT / 'export.json'), protocol=read(ROOT / 'export.json')['protocol'],
        driver=identity(__file__), models=[identity(p) for p in sorted(BUILD.glob('N*-*.json'))]))


def evaluate():
    common = r9()
    import xgboost as xgb
    data = load_data()
    with np.load('../exp585/build/exp585/evaluation.npz') as packed:
        truth = packed['truth']
        partitions = {k[10:]: packed[k] for k in packed.files if k.startswith('partition_')}
    frozen = read(ROOT / 'export.json')
    checked('../exp576/build/exp576/R8.f32', frozen['fixed_raw'])
    original_raw = np.fromfile('../exp576/build/exp576/R8.f32', '<f4')
    fixed_models = read('../exp576/validation/results/exp576/R8.json')['records']
    assert [(r['fold'], r['route']) for r in fixed_models] == [(f, r) for f in range(3) for r in range(16)]
    assert original_raw.shape == (ROWS,) and np.isfinite(original_raw).all()
    for name, target in (('features.f32', '../exp576/build/exp576/features.f32'),
                         ('folds.u8', '../exp585/build/exp585/folds.u8'),
                         ('routes.u8', '../exp585/build/exp585/routes.u8')):
        (BUILD / name).symlink_to(Path(target).resolve())
    decoder = BUILD / 'routed-predict'
    command = ['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64', '-mtune=generic',
        '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
        'tests/exp576_routed_residual.cpp', '-o', str(decoder)]
    common.speed.measured(command, 'compile-decoder')
    assert not (ROOT / 'compile-decoder.stderr').read_bytes()
    result = subprocess.run([str(decoder), '--help'], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.startswith('usage:')
    results, eligible, supports = {}, [], []
    for background in BACKGROUNDS:
        base = data[background]
        fixed = common.complete.trees.decode(original_raw, base, data['mandatory'])
        results[background] = dict(Fixed=common.paired(fixed, fixed, truth, partitions))
        for arm in ARMS:
            family, rounds = arm[0], int(arm[1:])
            raw, paths = np.empty(ROWS, dtype='<f4'), []
            for fold in range(3):
                for route in range(16):
                    stem = f'{background}-{family}-{fold}-{route}'
                    meta = read(ROOT / ('model-' + stem + '.json'))
                    path = BUILD / (stem + '.json')
                    expected = meta['model']
                    if expected is None:
                        assert meta['unreachable_near_route'] and not np.any(data['near'] & (data['routes'] == route))
                        expected = fixed_models[16 * fold + route]['assets']['json']
                        path = Path('../exp576') / expected['path']
                    checked(path, expected)
                    booster = xgb.Booster(params={'nthread': 1})
                    booster.load_model(path)
                    booster = booster[:min(rounds, booster.num_boosted_rounds())]
                    mask = (data['folds'] == fold) & (data['routes'] == route)
                    raw[mask] = booster.predict(xgb.DMatrix(data['features'][mask], nthread=1))
                    assets = common.complete.trees.export_model(booster, f'E-{background}-{arm}-{fold}-{route}')
                    paths.append(assets['binary']['path'])
                    if arm in ('A8', 'P16'):
                        test = mask & (data['near'] if family != 'A' else True)
                        supports.append(dict(background=background, arm=arm, fold=fold, route=route,
                            train_rows=meta['rows'], test_rows=int(test.sum()),
                            train_port_pairs=meta['port_pairs'], test_port_pairs=int(np.unique(data['pair'][test]).size)))
            listing = BUILD / f'{background}-{arm}-models.txt'
            listing.write_text('16\n' + ''.join(p + '\n' for p in paths))
            output = BUILD / f'{background}-{arm}-independent.f32'
            record = common.speed.measured([str(decoder), str(BUILD / 'features.f32'), str(BUILD / 'folds.u8'),
                str(BUILD / 'routes.u8'), str(listing), str(output)], f'{background}-{arm}-independent')
            independent = np.fromfile(output, '<f4')
            assert np.array_equal(independent.view('u4'), raw.view('u4'))
            counters = read(ROOT / f'{background}-{arm}-independent.stdout')
            assert counters['port_pairs'] == 59904 and counters['threads'] == 1 and counters['kernel_allocations'] == 0
            if family != 'A':
                raw[~data['near']] = original_raw[~data['near']]
            prediction = common.complete.trees.decode(raw, base, data['mandatory'])
            raw.tofile(BUILD / f'{background}-{arm}-raw.f32')
            stats = common.paired(prediction, fixed, truth, partitions)
            for group, values in (('near', data['near']), ('forced', data['features'][:, 52].astype('i4'))):
                stats[group + '_accuracy_pp'] = {str(int(k)): common.real.statistics(prediction[values == k], truth[values == k])['accuracy_pp']
                    for k in np.unique(values)}
            stats['quality_gate'] = bool(stats['paired_accuracy_pp'] >= .02 and stats['ci95_accuracy_pp'][0] > 0
                and stats['accuracy_pp'] > 98.2 and all(d >= -.03 for g in stats['groups_delta_pp'].values() for d in g.values()))
            stats.update(independent_run=record, complete_bitwise_equal=True, final_elf_verified=False,
                raw=identity(BUILD / f'{background}-{arm}-raw.f32'))
            results[background][arm] = stats
            if stats['quality_gate']:
                eligible.append(dict(background=background, arm=arm, accuracy_pp=stats['accuracy_pp']))
            write(ROOT / f'{background}-{arm}-checked.json', stats)
            print('EXP587_EVALUATED', background, arm, stats['accuracy_pp'], stats['paired_accuracy_pp'], stats['quality_gate'], flush=True)
    ordered = sorted(eligible, key=lambda x: (int(x['arm'][1:]), int(x['background'][1:]), x['arm']))
    selected = ordered[0] if ordered else None
    if selected:
        best = max(eligible, key=lambda x: x['accuracy_pp'])
        if best['accuracy_pp'] - selected['accuracy_pp'] > .02:
            selected = best
    write(ROOT / 'evaluation.json', dict(results=results, eligible=eligible, selected=selected, supports=supports,
        rows=ROWS, unique_rows=ROWS, port_pairs=59904, export=identity(ROOT / 'export.json'),
        training=identity(ROOT / 'training.json'), complete_program_verified=False))
    print('EXP587_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert sys.argv[1:] in (['export'], ['train'], ['evaluate'], ['final'])
    {'export': export, 'train': train, 'evaluate': evaluate, 'final': lambda: train(True)}[sys.argv[1]]()
