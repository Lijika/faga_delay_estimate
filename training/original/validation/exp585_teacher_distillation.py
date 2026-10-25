#!/usr/bin/env python3
"""Freeze a full-port residual data set, train on l7, and evaluate only on r9."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np

ROOT, BUILD = Path('validation/results/exp585'), Path('build/exp585')
PLAN = Path('experiment/实验585-真实几何残差的教师与折外蒸馏.md')
ROWS, SEED = 1000000, 20261021585


def identity(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256') if hasattr(hashlib, 'file_digest') else None
        if digest is None:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1048576), b''):
                digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def r9():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp585')
    sys.path.insert(0, str(Path('../exp582/validation').resolve()))
    import exp582_int8_geometry as common
    common.speed.ROOT = ROOT
    return common


def load_data():
    expected = read(ROOT / 'export.json')['training']
    assert identity(BUILD / 'training.npz') == expected
    with np.load(BUILD / 'training.npz') as packed:
        data = {k: packed[k] for k in packed.files}
    assert data['features'].shape == (ROWS, 54)
    assert np.isfinite(data['features']).all()
    assert np.array_equal(data['features'][:, 53], data['base'])
    for fold in range(3):
        mask = data['folds'] == fold
        assert np.unique(data['pair'][mask]).size == 59904
        assert not np.intersect1d(data['clusters'][mask], data['clusters'][~mask]).size
    return data


def export():
    common = r9()
    import exp556_xgb_residual as learning
    ROOT.mkdir(parents=True, exist_ok=True); BUILD.mkdir(parents=True, exist_ok=True)
    learning.ROOT = ROOT
    labels, query, ports, event, matrix, folds, clusters, *_ = learning.data()
    dtype = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
        formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f4'],
        offsets=[0, 216, 224, 228, 232, 236], itemsize=240))
    trace_path = Path('../exp582/build/exp582/B64-trace.bin')
    trace = np.memmap(trace_path, dtype=dtype, mode='r', shape=(ROWS,))
    assert np.array_equal(matrix.view('u4'), trace['features'].copy().view('u4'))
    assert np.array_equal(labels[:, 2], trace['mandatory'])
    keys = np.fromfile('../exp575/build/exp575/keys.i32', '<i4').reshape(ROWS, 2)
    pair, column = keys.T
    assert np.array_equal(pair, ports[:, 0] * 288 + ports[:, 1])
    qx, qy, context = column % 552 // 46, column % 46, column // 552
    table = np.fromfile('../exp584/build/exp584/q0.p10', 'u1')
    assert hashlib.sha256(table).hexdigest() == '36be97a1926ad6f314a200ff337ad651d817bfaccd010e39d9fe06b8088f1225'
    bit = 10 * (pair * 480 + context)
    nominal = (((table[bit // 8].astype('u2') | table[bit // 8 + 1].astype('u2') << 8)
                >> (bit % 8)) & 1023).astype('i4') - 67
    center = np.fromfile('../exp582/build/exp582/B64-geometry.bin', '<i2', count=59904, offset=64)
    approx = trace['response'] * (128 + 125 * qx + 125 * qy) + center[pair] + 125 * qx + np.where(context // 120 % 2, 125, 127) * qy
    fee = matrix[:, 50].astype('i4')
    override = trace['base'] != (np.maximum(approx, 0) + .5).astype('i4') + fee
    base = trace['base'].copy()
    selected = (qx == 0) & (qy == 0) & ~override
    base[selected] = nominal[selected] + fee[selected]
    expected = common.complete.trees.decode(trace['raw'], base, labels[:, 2])
    assert np.array_equal(expected, np.fromfile('../exp584/build/exp584/expected.i32', '<i4'))
    _, truth, evidence, partitions = common.complete.check_output(
        Path('../exp501/build/exp501/u-role/requests.csv'),
        Path('../exp584/build/exp584/development-0-C.csv'),
        Path('../exp501/build/exp501/exact.csv'), Path('../exp584/build/exp584/expected.i32'))
    assert np.array_equal(truth, labels[:, 0])
    x, y = matrix[:, 8] + matrix[:, 6], matrix[:, 9] + matrix[:, 7]
    routes = (4 * (2 * (x < 0) + (y < 0)) + 2 * (abs(x) >= 20) + (abs(y) >= 24)).astype('u1')
    features = np.column_stack((matrix, base)).astype('<f4')
    assert np.array_equal(features[:, 53].astype('i4'), base)
    with (BUILD / 'features.f32').open('xb') as stream:
        stream.write(b'E554F001' + struct.pack('<II', ROWS, 54)); stream.write(features.tobytes())
    folds.tofile(BUILD / 'folds.u8'); routes.tofile(BUILD / 'routes.u8')
    np.savez_compressed(BUILD / 'training.npz', features=features, base=base, d0=labels[:, 1].astype('<i4'),
        mandatory=labels[:, 2].astype('<i4'), folds=folds, clusters=clusters, pair=pair, routes=routes)
    np.savez_compressed(BUILD / 'evaluation.npz', truth=truth, query=query, event=event,
                        **{'partition_' + k: v for k, v in partitions.items()})
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    write(ROOT / 'export.json', dict(training=identity(BUILD / 'training.npz'), evidence=evidence,
        trace=identity(trace_path), features=identity(BUILD / 'features.f32'), protocol=identity(PLAN),
        full_port_pairs=59904, rows=ROWS, unique_rows=ROWS, cluster_disjoint=True,
        base_exactly_reconstructed=True, q0_rows=int(selected.sum())))
    print('EXP585_EXPORTED', identity(BUILD / 'training.npz'), flush=True)


def params(teacher=False):
    return dict(objective='reg:absoluteerror', tree_method='hist', base_score=0,
        colsample_bytree=1., seed=SEED, nthread=16, max_depth=6 if teacher else 4,
        eta=.05 if teacher else .3, max_bin=1024 if teacher else 256,
        min_child_weight=20 if teacher else 1, reg_lambda=5 if teacher else 1,
        subsample=.85 if teacher else 1.)


def save_model(booster, stem, record):
    target = BUILD / (stem + '.json')
    assert not target.exists(), target
    booster.save_model(target)
    write(ROOT / ('model-' + stem + '.json'), dict(**record, model=identity(target)))
    print('EXP585_TRAINED', stem, record.get('wall_s'), flush=True)


def fit(data, stem, learn, columns, target, teacher, rounds):
    import xgboost as xgb
    record_path = ROOT / ('model-' + stem + '.json')
    parameters = params(teacher)
    if record_path.exists():
        record = read(record_path)
        assert record['params'] == parameters and record['rounds'] == rounds
        assert identity(record['model']['path']) == record['model']
        booster = xgb.Booster(); booster.load_model(record['model']['path'])
        return booster
    started, cpu = time.monotonic(), time.process_time()
    weights = (1000 / np.maximum(data['d0'][learn] + data['mandatory'][learn], 128)).astype('<f4')
    dm = xgb.DMatrix(data['features'][learn, :columns], label=target[learn], weight=weights, nthread=16)
    booster = xgb.train(parameters, dm, num_boost_round=rounds)
    save_model(booster, stem, dict(params=parameters, rounds=rounds, columns=columns,
        rows=int(learn.sum()), port_pairs=int(np.unique(data['pair'][learn]).size),
        wall_s=time.monotonic() - started, cpu_s=time.process_time() - cpu, offline_only=True))
    return booster


def train(stage):
    assert socket.gethostname() == 'lhj-NF5280M5'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp585')
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    data = load_data()
    write(ROOT / 'environment.json', dict(xgboost=xgb.__version__, build=xgb.build_info(),
        threads=16, protocol=identity(ROOT / 'protocol-original.md')))
    hard = (data['d0'] - data['base']).astype('<f4')
    if stage == 'teachers':
        for fold in range(3):
            for route in range(16):
                learn = (data['folds'] != fold) & (data['routes'] == route)
                for name, width, big, rounds in (('T128', 54, True, 128), ('C8', 53, False, 8), ('F16', 54, False, 16)):
                    booster = fit(data, f'{name}-{fold}-{route}', learn, width, hard, big, rounds)
                    if name == 'F16' and not (BUILD / f'F8-{fold}-{route}.json').exists():
                        save_model(booster[:8], f'F8-{fold}-{route}', dict(prefix_of=f'F16-{fold}-{route}', rounds=8))
        write(ROOT / 'teachers-complete.json', dict(complete=True, data=identity(BUILD / 'training.npz')))
        return
    assert stage == 'students'
    gate = read(ROOT / 'teacher-evaluation.json')
    assert gate['teacher_gate'] and gate['protocol_sha256'] == read(ROOT / 'export.json')['protocol']['sha256']
    soft = np.full((3, ROWS), np.nan, dtype='<f4')
    for fold in range(3):
        for route in range(16):
            learn = (data['folds'] == fold) & (data['routes'] == route)
            booster = fit(data, f'SingleT-{fold}-{route}', learn, 54, hard, True, 128)
            other = (data['folds'] != fold) & (data['routes'] == route)
            soft[fold, other] = booster.predict(xgb.DMatrix(data['features'][other], nthread=16))
    for fold in range(3):
        assert np.isnan(soft[fold, data['folds'] == fold]).all()
        assert np.isfinite(soft[fold, data['folds'] != fold]).all()
    np.save(BUILD / 'training-soft.npy', soft)
    for fold in range(3):
        rows = np.flatnonzero(data['folds'] != fold)
        target = np.zeros(ROWS, dtype='<f4')
        target[rows] = soft[3 - fold - data['folds'][rows], rows]
        mixed = (.5 * (target + hard)).astype('<f4')
        for route in range(16):
            learn = (data['folds'] != fold) & (data['routes'] == route)
            for name, values, rounds in (('D8', target, 8), ('M16', mixed, 16)):
                booster = fit(data, f'{name}-{fold}-{route}', learn, 54, values, False, rounds)
                if name == 'M16' and not (BUILD / f'M8-{fold}-{route}.json').exists():
                    save_model(booster[:8], f'M8-{fold}-{route}', dict(prefix_of=f'M16-{fold}-{route}', rounds=8))
    write(ROOT / 'students-complete.json', dict(complete=True, training_targets=identity(BUILD / 'training-soft.npy')))


def evaluate(stage):
    common = r9()
    import xgboost as xgb
    data = load_data()
    with np.load(BUILD / 'evaluation.npz') as packed:
        truth, query, event = (packed[k] for k in ('truth', 'query', 'event'))
        partitions = {k[len('partition_'):]: packed[k] for k in packed.files if k.startswith('partition_')}
    compiler = ['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64', '-mtune=generic',
        '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
        'tests/exp576_routed_residual.cpp', '-o', str(BUILD / 'routed-predict')]
    helped = subprocess.check_output(['g++', '--help=optimizers'], text=True)
    assert '-ffp-contract' in helped
    (ROOT / 'compiler-help.txt').write_text(helped)
    result = subprocess.run(compiler, capture_output=True, text=True)
    write(ROOT / 'compiler.json', dict(command=compiler, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
    assert result.returncode == 0 and not result.stderr
    result = subprocess.run([str(BUILD / 'routed-predict'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.startswith('usage:')
    arms = ['T128', 'C8', 'F8', 'F16'] if stage == 'teachers' else ['D8', 'M8', 'M16']
    common.complete.trees.BUILD = BUILD
    predictions, records = {}, {}
    for name in arms:
        raw, paths = np.empty(ROWS, dtype='<f4'), []
        for fold in range(3):
            for route in range(16):
                stem = f'{name}-{fold}-{route}'
                metadata = read(ROOT / ('model-' + stem + '.json'))
                assert identity(BUILD / (stem + '.json')) == metadata['model']
                booster = xgb.Booster(params={'nthread': 1}); booster.load_model(BUILD / (stem + '.json'))
                width = booster.num_features()
                mask = (data['folds'] == fold) & (data['routes'] == route)
                raw[mask] = booster.predict(xgb.DMatrix(data['features'][mask, :width], nthread=1))
                assets = common.complete.trees.export_model(booster, 'E-' + stem)
                paths.append(assets['binary']['path'])
        listing = BUILD / (name + '-models.txt')
        listing.write_text('16\n' + ''.join(p + '\n' for p in paths))
        output = BUILD / (name + '-independent.f32')
        record = common.speed.measured([str(BUILD / 'routed-predict'), str(BUILD / 'features.f32'),
            str(BUILD / 'folds.u8'), str(BUILD / 'routes.u8'), str(listing), str(output)], name + '-independent')
        restored = np.fromfile(output, '<f4')
        assert np.array_equal(restored.view('u4'), raw.view('u4'))
        counters = read(record['stderr'].replace('.stderr', '.stdout'))
        assert counters['port_pairs'] == 59904 and counters['kernel_allocations'] == 0 and counters['threads'] == 1
        prediction = common.complete.trees.decode(raw, data['base'], data['mandatory'])
        prediction.astype('<i4').tofile(BUILD / (name + '-prediction.i32'))
        raw.tofile(BUILD / (name + '-raw.f32'))
        predictions[name] = prediction
        records[name] = dict(independent_run=record, counters=counters, complete_bitwise_equal=True,
            predictions=identity(BUILD / (name + '-prediction.i32')), raw=identity(BUILD / (name + '-raw.f32')))
        write(ROOT / (name + '-checked.json'), records[name])
        print('EXP585_EVALUATED', name, common.real.statistics(prediction, truth)['accuracy_pp'], flush=True)
    summarize(stage, common, data, truth, partitions, predictions, records)


def summarize(stage, common, data, truth, partitions, predictions, records):
    if stage == 'students':
        for name in ('T128', 'C8', 'F8', 'F16'):
            predictions[name] = np.fromfile(BUILD / (name + '-prediction.i32'), '<i4')
    stats = {name: common.paired(p, predictions['C8'], truth, partitions) for name, p in predictions.items()}
    forced = data['features'][:, 52].astype('i4')
    assert np.isin(forced, [0, 1]).all()
    for name, p in predictions.items():
        stats[name]['forced_detour_accuracy_pp'] = {
            str(int(k)): common.real.statistics(p[forced == k], truth[forced == k])['accuracy_pp'] for k in np.unique(forced)}
        stats[name]['quality_gate'] = bool(stats[name]['paired_accuracy_pp'] >= .03 and stats[name]['ci95_accuracy_pp'][0] > 0
            and all(d >= -.03 for values in stats[name]['groups_delta_pp'].values() for d in values.values()))
    teacher_gate = stats['T128']['paired_accuracy_pp'] >= .05 and stats['T128']['ci95_accuracy_pp'][0] > 0
    result = dict(stats=stats, checks=records, teacher_gate=bool(teacher_gate), rows=ROWS, full_port_pairs=59904,
        protocol_sha256=read(ROOT / 'export.json')['protocol']['sha256'], complete_program_verified=False)
    if stage == 'students':
        result['distillation_delta'] = {}
        for name, baseline in (('D8', 'F8'), ('M8', 'F8'), ('M16', 'F16')):
            value = common.paired(predictions[name], predictions[baseline], truth, partitions)
            value['teacher_gain_retained'] = stats[name]['paired_accuracy_pp'] / stats['T128']['paired_accuracy_pp']
            result['distillation_delta'][name] = value
        eligible = [n for n in ('F8', 'M8', 'D8', 'F16', 'M16') if stats[n]['quality_gate']]
        small = [n for n in eligible if n.endswith('8')]
        pool = small or eligible
        best = max((stats[n]['accuracy_pp'] for n in pool), default=0)
        result['selected'] = next((n for n in pool if stats[n]['accuracy_pp'] >= best - .005), None)
    write(ROOT / ('teacher-evaluation.json' if stage == 'teachers' else 'student-evaluation.json'), result)
    print('EXP585_GATE', json.dumps(result.get('selected', bool(teacher_gate))), flush=True)


if __name__ == '__main__':
    assert sys.argv[1:] in (['export'], ['teachers'], ['students'], ['evaluate-teachers'], ['evaluate-students'])
    action = sys.argv[1]
    if action == 'export':
        export()
    elif action.startswith('evaluate-'):
        evaluate(action.split('-')[1])
    else:
        train(action)
