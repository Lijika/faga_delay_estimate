#!/usr/bin/env python3
"""Compare matched Q4 retraining with nested map-event experts on r9."""
import gc
import inspect
import json
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np
import xgboost as xgb

sys.path.insert(0, str(Path('../exp614/validation').resolve()))
import exp614_gemini_features as prior
sys.path.insert(0, str(Path('../exp554/validation').resolve()))
import exp554_real_kernel_function as exporter
sys.path.insert(0, str(Path('../exp592/validation').resolve()))
from exp592_xgb_audit import decode, points, transition

ROOT, BUILD = Path('validation/results/exp631'), Path('build/exp631')
PLAN = Path('experiment/实验631-Q4背景的嵌套地图事件专家.md')
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked
ROWS, SEED = 1000000, 20261023631
PARAMS = prior.prior.PARAMS


def routes(features, split):
    nx, ny = features[:, 8] + features[:, 6], features[:, 9] + features[:, 7]
    direction = 2 * (nx < 0) + (ny < 0)
    route = 4 * direction + 2 * (np.abs(nx) >= 20) + (np.abs(ny) >= 24)
    ax, tx = features[:, 28], features[:, 30]
    cross = (np.minimum(ax, tx) < 76) & (np.maximum(ax, tx) > 89)
    return np.where(split & (route % 4 == 3) & cross, 16 + direction, route).astype('u1')


def load():
    data = prior.load()
    frozen = read('../exp623/validation/results/exp623/prepare.json')
    checked('../exp623/build/exp623/data.npz', frozen['data'])
    with np.load('../exp623/build/exp623/data.npz') as packed:
        q4 = {k: packed[k] for k in packed.files}
    for key in ('truth', 'mandatory', 'routes', 'folds'):
        assert np.array_equal(data[key], q4[key]), key
    data['base'] = q4['base']
    assert np.array_equal(routes(data['features'], False), data['routes'])
    return data


def prepare():
    assert xgb.__version__ == '3.0.5'
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    (ROOT / 'installed-xgboost-help.txt').write_text(
        xgb.__version__ + '\n' + str(inspect.signature(xgb.train)) + '\n' + xgb.train.__doc__
        + '\n' + str(inspect.signature(xgb.DMatrix)))
    gap_path = Path('../exp614/doc/eda比赛文件/arch/SRB_Gap.json')
    gap = read(gap_path)['Gap']
    bands = {(b['left'], b['right']) for b in gap['Block'] if b['horizontal crossable']}
    assert bands == {(76, 89)}
    fixtures = np.zeros((24, 53), '<f4')
    expected = []
    for d in range(4):
        for j, (a, t, nx) in enumerate(((75, 90, 20), (76, 90, 20), (75, 89, 20),
                                       (90, 75, 20), (75, 90, 19), (90, 90, 20))):
            i = d * 6 + j
            fixtures[i, 6] = 10
            fixtures[i, 8] = (-nx if d >= 2 else nx) - 10
            fixtures[i, 9] = -24 if d & 1 else 24
            fixtures[i, 28], fixtures[i, 30] = a, t
            expected.append(16 + d if j in (0, 3) else 4 * d + (1 if j == 4 else 3))
    assert routes(fixtures, True).tolist() == expected
    data = load()
    with (BUILD / 'features.f32').open('xb') as stream:
        stream.write(b'E554F001' + struct.pack('<II', ROWS, 53))
        stream.write(data['features'].astype('<f4').tobytes())
    data['folds'].astype('u1').tofile(BUILD / 'folds.u8')
    for arm in ('M', 'E'):
        routes(data['features'], arm == 'E').tofile(BUILD / (arm + '-routes.u8'))
    source_path = Path('../exp587/tests/exp576_routed_residual.cpp')
    source = source_path.read_text()
    first, last = source.index('static unsigned route_of('), source.index('\nint main(')
    source = source[:first] + '#include "exp631_event_route.h"\n' + (
        'static unsigned route_of(const float* x) { return eventRoute631(x, EXP631_EVENT); }\n') + source[last:]
    source = source.replace('(groups == 1 || groups == 16)', '(groups == (EXP631_EVENT ? 20 : 16))')
    source = source.replace('routes[i] < 16', 'routes[i] < 20')
    source = source.replace('require(argc == 6, "arguments");',
        'require(argc == 6, "arguments");\n        routeSelfCheck631();')
    (BUILD / 'predict.cpp').write_text(source)
    (ROOT / 'compiler-help.txt').write_text(subprocess.check_output(['g++', '--help'], text=True))
    compile_records = []
    for arm in ('M', 'E'):
        command = ['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64',
            '-mtune=generic', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
            '-DEXP631_EVENT=' + str(int(arm == 'E')), '-Itests',
            '-I' + str(source_path.parent.resolve()), str(BUILD / 'predict.cpp'),
            '-o', str(BUILD / (arm + '-predict'))]
        run = subprocess.run(command, capture_output=True, text=True)
        (ROOT / ('compile-' + arm + '.stderr')).write_text(run.stderr)
        assert run.returncode == 0 and not run.stderr, run.stderr
        usage = subprocess.run([str(BUILD / (arm + '-predict')), '--help'], capture_output=True, text=True)
        assert usage.returncode == 0 and usage.stdout.startswith('usage:')
        compile_records.append(dict(command=command, binary=identity(BUILD / (arm + '-predict')),
                                    usage=usage.stdout))
    write(ROOT / 'prepare.json', dict(rows=ROWS, groups=dict(M=16, E=20),
        files=[identity(p) for p in (Path(__file__), PLAN, Path('tests/exp631_event_route.h'),
               Path('validation/event-experts-theory.md'), gap_path, source_path, Path(exporter.__file__),
               Path('../exp623/build/exp623/data.npz'), BUILD / 'features.f32', BUILD / 'folds.u8',
               BUILD / 'M-routes.u8', BUILD / 'E-routes.u8')],
        folds=[dict(fold=k, source_pin_overlap=0, train_port_pairs=59904, test_port_pairs=59904)
               for k in range(3)], params=PARAMS, rounds=8,
        compile_records=compile_records, fixture_route_equal=True,
        disk_free_start_bytes=shutil.disk_usage('.').free))
    print('EXP631_PREPARED', flush=True)


def train():
    assert xgb.__version__ == '3.0.5'
    for item in read(ROOT / 'prepare.json')['files']:
        checked(item['path'], item)
    data = load()
    exporter.BUILD = BUILD
    old = read('../exp576/validation/results/exp576/R8.json')
    frozen = {(r['fold'], r['route']): r['assets']['json'] for r in old['records']}
    target = (data['d0'] - data['base']).astype('<f4')
    weights = (1000 / np.maximum(data['d0'] + data['mandatory'], 128)).astype('<f4')
    records = []
    for arm, groups in (('M', 16), ('E', 20)):
        group = routes(data['features'], arm == 'E')
        raw = np.empty(ROWS, '<f4')
        paths = []
        for fold in range(3):
            for route in range(groups):
                learn = (data['folds'] != fold) & (group == route)
                test = (data['folds'] == fold) & (group == route)
                assert learn.any() and test.any()
                changed = route >= 16 or route % 4 == 3
                start = time.process_time()
                source = None
                if changed:
                    dm = xgb.DMatrix(data['features'][learn], label=target[learn],
                                     weight=weights[learn], nthread=16)
                    booster = xgb.train(PARAMS, dm, num_boost_round=8)
                    del dm
                else:
                    source = frozen[fold, route]
                    path = Path('../exp576') / source['path']
                    checked(path, source)
                    booster = xgb.Booster(params={'nthread': 1})
                    booster.load_model(path)
                booster.set_param({'nthread': 1})
                dm = xgb.DMatrix(data['features'][test], nthread=1)
                raw[test] = booster.predict(dm)
                del dm
                asset = exporter.export_model(booster, f'{arm}-{fold}-{route}')
                assert asset['trees'] == 8
                paths.append(asset['binary']['path'])
                record = dict(arm=arm, fold=fold, route=route, trained=changed,
                    source=source, train_rows=int(learn.sum()), test_rows=int(test.sum()),
                    train_pairs=int(np.unique(data['pair'][learn]).size),
                    test_pairs=int(np.unique(data['pair'][test]).size), assets=asset,
                    cpu_s=time.process_time()-start)
                records.append(record)
                write(ROOT / f'model-{arm}-{fold}-{route}.json', record)
                del booster
                gc.collect()
            print('EXP631_TRAINED', arm, fold, flush=True)
        raw.tofile(BUILD / (arm + '-raw.f32'))
        (BUILD / (arm + '-models.txt')).write_text(str(groups) + '\n' + ''.join(p + '\n' for p in paths))
    write(ROOT / 'training.json', dict(complete=True, records=records,
        raw={arm: identity(BUILD / (arm + '-raw.f32')) for arm in ('M', 'E')}))


def evaluate():
    data = load()
    training = read(ROOT / 'training.json')
    old = read('../exp576/validation/results/exp576/R8.json')
    checked('../exp576/build/exp576/R8.f32', old['raw'])
    raw_a = np.fromfile('../exp576/build/exp576/R8.f32', '<f4')
    prediction = {'A': decode(raw_a, data['base'], data['mandatory'])}
    audits = {}
    for arm in ('M', 'E'):
        for item in training['records']:
            if item['arm'] == arm:
                checked(item['assets']['binary']['path'], item['assets']['binary'])
        checked(BUILD / (arm + '-raw.f32'), training['raw'][arm])
        command = [str(BUILD / (arm + '-predict')), str(BUILD / 'features.f32'),
            str(BUILD / 'folds.u8'), str(BUILD / (arm + '-routes.u8')),
            str(BUILD / (arm + '-models.txt')), str(BUILD / (arm + '-native.f32'))]
        run = subprocess.run(command, capture_output=True, text=True)
        (ROOT / (arm + '-independent.stdout')).write_text(run.stdout)
        (ROOT / (arm + '-independent.stderr')).write_text(run.stderr)
        assert run.returncode == 0 and not run.stderr, run.stderr
        raw = np.fromfile(BUILD / (arm + '-raw.f32'), '<f4')
        native = np.fromfile(BUILD / (arm + '-native.f32'), '<f4')
        assert np.array_equal(raw.view('u4'), native.view('u4'))
        untouched = data['routes'] % 4 != 3
        assert np.array_equal(raw[untouched].view('u4'), raw_a[untouched].view('u4'))
        prediction[arm] = decode(raw, data['base'], data['mandatory'])
        assert np.array_equal(prediction[arm][untouched], prediction['A'][untouched])
        counters = json.loads(run.stdout)
        assert counters['threads'] == 1 and counters['kernel_allocations'] == 0
        audits[arm] = dict(raw_bitwise_equal=True, unchanged_rows=int(untouched.sum()),
            command=command, counters=counters, native=identity(BUILD / (arm + '-native.f32')))
    x = data['features']
    nx, ny = x[:, 8] + x[:, 6], x[:, 9] + x[:, 7]
    partitions = dict(distance=np.searchsorted([24, 100, 300], np.abs(nx)+np.abs(ny)),
        near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype('i4'),
        source_family=x[:, 0].astype('i4'), direction=2*(nx < 0)+(ny < 0),
        cross=((np.minimum(x[:, 28], x[:, 30]) < 76) &
               (np.maximum(x[:, 28], x[:, 30]) > 89)).astype('i4'), forced=x[:, 52].astype('i4'))
    family = partitions['source_family']
    counts = np.bincount(family, minlength=26)
    sampled = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    denominator = counts[sampled].sum(axis=1)
    reports = {}
    for a, b in (('E', 'A'), ('E', 'M'), ('M', 'A')):
        result = transition(prediction[a], prediction[b], data['truth'], partitions)
        delta = points(prediction[a], data['truth']) - points(prediction[b], data['truth'])
        totals = np.bincount(family, weights=delta, minlength=26)
        result['simultaneous_ci_delta_pp'] = np.quantile(
            totals[sampled].sum(axis=1)/denominator, [.05/6, 1-.05/6]).tolist()
        result['changed_rows'] = int(np.count_nonzero(prediction[a] != prediction[b]))
        reports[a + '-' + b] = result
    def quality(name):
        item = reports[name + '-A']
        return bool(item['delta_accuracy_pp'] >= .02 and item['simultaneous_ci_delta_pp'][0] > 0
            and all(v['delta_accuracy_pp'] >= -.03 for key, group in item['groups'].items()
                    if key in ('distance', 'near_axis') for v in group.values()))
    eligible = dict(E=quality('E') and reports['E-M']['simultaneous_ci_delta_pp'][0] > 0,
                    M=quality('M'))
    selected = 'E' if eligible['E'] else 'M' if eligible['M'] else None
    write(ROOT / 'evaluation.json', dict(reports=reports, audits=audits, eligible=eligible,
        selected=selected, training=identity(ROOT / 'training.json'), independent_requests=False,
        complete_program_measured=False, hypothesis='nested map-event partition under frozen Q4'))
    for name, item in reports.items():
        print('EXP631_COMPARISON', name, item['delta_accuracy_pp'], item['simultaneous_ci_delta_pp'], flush=True)
    print('EXP631_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp631')
    assert len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'train', 'evaluate')
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    start, cpu = time.monotonic(), time.process_time()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate}[sys.argv[1]]()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    write(ROOT / (sys.argv[1] + '-resources.json'), dict(cpu_s=time.process_time()-cpu+
          children.ru_utime+children.ru_stime, wall_s=time.monotonic()-start,
          own_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
          children_rss_bytes=children.ru_maxrss*1024, disk_free_end_bytes=shutil.disk_usage('.').free))
