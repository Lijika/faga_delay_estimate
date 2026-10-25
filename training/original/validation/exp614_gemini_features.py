#!/usr/bin/env python3
"""Fixed D64 residual ablations using phase and map events, audited on r9."""
import gc
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp593/validation').resolve()))
import exp593_target_support as prior

identity, read, write, checked = prior.identity, prior.read, prior.write, prior.checked
ROOT, BUILD = Path('validation/results/exp614'), Path('build/exp614')
PLAN = Path('experiment/实验614-Gemini周期相位与地图事件特征.md')
ARMS = ('P', 'E', 'PE')
ROWS = prior.ROWS
NAMES = ('compressed_dx_mod10', 'abs_compressed_dx_mod10', 'compressed_qx',
         'compressed_dx_negative', 'ax_mod10', 'tx_mod10', 'ay_mod12', 'ty_mod12',
         'line_x_9', 'line_x_78', 'line_x_98', 'line_x_177', 'line_y_8',
         'crossed_block_count', 'block_edge_extra_rows', 'qx_compression_difference')


def load():
    prior.ROOT = Path('../exp593/validation/results/exp593')
    prior.BUILD = Path('../exp593/build/exp593')
    return prior.load()


def geometry(features, gap):
    ax, ay, tx, ty = features[:, 28:32].astype('i4').T
    cx = (tx - 14 * ((ty % 100 < 50) & (tx >= 90))) - (
          ax - 14 * ((ay % 100 < 50) & (ax >= 90)))
    assert np.array_equal(cx, features[:, 51])
    lowx, highx, lowy, highy = np.minimum(ax, tx), np.maximum(ax, tx), np.minimum(ay, ty), np.maximum(ay, ty)
    fields = [cx % 10, np.abs(cx) % 10, np.abs(cx) // 10, cx < 0,
              ax % 10, tx % 10, ay % 12, ty % 12]
    for direction, delay in (('vertical', 9), ('vertical', 78), ('vertical', 98),
                              ('vertical', 177), ('horizontal', 8)):
        low, high = (lowx, highx) if direction == 'vertical' else (lowy, highy)
        count = np.zeros(len(ax), dtype='i4')
        for line in gap['Line']:
            if line['direction'] == direction and line['delay'] == delay:
                count += (low <= line['site']) & (line['site'] < high)
        fields.append(count)
    blocks, detour, forced = np.zeros((3, len(ax)), dtype='i4')
    for block in gap['Block']:
        if not block['horizontal crossable']:
            continue
        left, right, lower, upper = (block[k] for k in ('left', 'right', 'lower', 'upper'))
        cross = (lowx < left) & (highx > right)
        blocks += cross & (lowy <= upper) & (highy >= lower)
        same = cross & (lowy >= lower) & (highy <= upper)
        steps = np.full(len(ax), 10000, dtype='i4')
        if lower > 0:
            steps = np.minimum(steps, lowy - lower + 1)
        if upper < 549:
            steps = np.minimum(steps, upper + 1 - highy)
        assert np.all(steps[same] < 10000)
        detour[same] = 2 * steps[same]
        forced += same
    assert np.array_equal(forced, features[:, 52])
    fields += [blocks, detour, np.abs(tx - ax) // 10 - np.abs(cx) // 10]
    output = np.column_stack(fields).astype('<f4')
    assert output.shape == (len(ax), 16) and np.isfinite(output).all()
    return output


def self_check(gap):
    coordinates = [(75, 0, 90, 0), (75, 549, 90, 549), (75, 120, 90, 130),
                   (90, 130, 75, 120), (9, 50, 10, 50), (9, 50, 9, 50),
                   (117, 50, 118, 50), (20, 49, 20, 50), (90, 50, 75, 50)]
    x = np.zeros((len(coordinates), 53), dtype='<f4')
    x[:, 28:32] = coordinates
    ax, ay, tx, ty = x[:, 28:32].astype('i4').T
    x[:, 51] = tx - 14 * ((ty % 100 < 50) & (tx >= 90)) - ax + 14 * ((ay % 100 < 50) & (ax >= 90))
    x[:4, 52] = 1
    z = geometry(x, gap)
    assert z[:4, 14].tolist() == [100, 100, 40, 40]
    assert z[4, 9] == 1 and np.all(z[5, 8:15] == 0)
    assert z[6, 8] == 1 and z[7, 12] == 1
    assert z[8, 0] == 5 and z[8, 3] == 1 and z[8, 14] == 0


def prepare():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    gap_path = Path('doc/eda比赛文件/arch/SRB_Gap.json')
    gap = read(gap_path)['Gap']
    self_check(gap)
    data = load()
    z = geometry(data['features'], gap)
    x = np.column_stack((data['features'], z)).astype('<f4')
    with (BUILD / 'features.f32').open('xb') as stream:
        stream.write(b'E554F001' + struct.pack('<II', ROWS, 69))
        stream.write(x.tobytes())
    for name, path in (('folds.u8', '../exp585/build/exp585/folds.u8'),
                       ('routes.u8', '../exp585/build/exp585/routes.u8')):
        (BUILD / name).symlink_to(Path(path).resolve())
    source_path = Path('../exp587/tests/exp576_routed_residual.cpp')
    source = source_path.read_text()
    old = '(columns == 53 || columns == 54)'
    assert source.count(old) == 1
    source = source.replace(old, 'columns == 69')
    source = '#include "' + str(Path('tests/exp614_geometry_features.h').resolve()) + '"\n' + source
    old = 'require(route_of(x) == routes[i], "route formula");'
    assert source.count(old) == 1
    source = source.replace(old, '''float extra[16];
            geometry614(x, extra);
            for (unsigned j = 0; j < 16; ++j)
                require(extra[j] == x[53 + j], "geometry614 feature mismatch");
            ''' + old)
    (BUILD / 'routed-predict.cpp').write_text(source)
    command = ['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64', '-mtune=generic',
               '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
               '-I' + str(source_path.parent.resolve()), str(BUILD / 'routed-predict.cpp'),
               '-o', str(BUILD / 'routed-predict')]
    run = subprocess.run(command, capture_output=True, text=True)
    (ROOT / 'compile-decoder.stdout').write_text(run.stdout)
    (ROOT / 'compile-decoder.stderr').write_text(run.stderr)
    assert run.returncode == 0 and not run.stderr, run.stderr
    help_run = subprocess.run([str(BUILD / 'routed-predict'), '--help'], capture_output=True, text=True)
    assert help_run.returncode == 0 and help_run.stdout.startswith('usage:')
    frozen = read(prior.ROOT / 'export.json')
    matched = read(prior.ROOT / 'K1-report.json')['raw']
    checked('../exp593/' + matched['path'], matched)
    write(ROOT / 'prepare.json', dict(protocol=identity(ROOT / 'protocol-original.md'),
          driver=identity(__file__), geometry_header=identity('tests/exp614_geometry_features.h'),
          gap=identity(gap_path), training=frozen['training'], targets=frozen['targets'],
          evaluation=frozen['evaluation'], original_raw=frozen['fixed_raw'], matched_raw=matched,
          features=identity(BUILD / 'features.f32'), feature_names=list(NAMES),
          columns=69, rows=ROWS, unique_rows=ROWS, port_pairs=59904, boundary_self_check=True,
          decoder=identity(BUILD / 'routed-predict'), compiler_command=command,
          folds=[dict(fold=k, train_rows=int((data['folds'] != k).sum()),
                      test_rows=int((data['folds'] == k).sum()), source_pin_overlap=0,
                      train_port_pairs=59904, test_port_pairs=59904) for k in range(3)]))
    print('EXP614_PREPARED', flush=True)


def matrix():
    frozen = read(ROOT / 'prepare.json')
    checked(BUILD / 'features.f32', frozen['features'])
    return np.fromfile(BUILD / 'features.f32', '<f4', offset=16).reshape(ROWS, 69)


def train():
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    data, x = load(), matrix()
    target = (data['d0'] - data['D64']).astype('<f4')
    weights = (1000 / np.maximum(data['d0'] + data['mandatory'], 128)).astype('<f4')
    records = []
    for arm in ARMS:
        masked = x.copy()
        disabled = list(range(61, 69)) if arm == 'P' else list(range(53, 61)) if arm == 'E' else []
        masked[:, disabled] = 0
        for fold in range(3):
            for route in range(16):
                stem = f'{arm}-{fold}-{route}'
                path = BUILD / (stem + '.json')
                record_path = ROOT / ('model-' + stem + '.json')
                if record_path.exists():
                    record = read(record_path)
                    assert record['params'] == prior.PARAMS and record['rounds'] == 8
                    checked(path, record['model'])
                    records.append(record)
                    continue
                assert not path.exists()
                learn = (data['folds'] != fold) & (data['routes'] == route)
                started, cpu = time.monotonic(), time.process_time()
                dm = xgb.DMatrix(masked[learn], label=target[learn], weight=weights[learn], nthread=16)
                booster = xgb.train(prior.PARAMS, dm, num_boost_round=8)
                booster.save_model(path)
                trees = read(path)['learner']['gradient_booster']['model']['trees']
                assert len(trees) == 8
                used = [int(f) for tree in trees for f, left in zip(tree['split_indices'], tree['left_children']) if left >= 0]
                assert not set(used).intersection(disabled)
                record = dict(arm=arm, fold=fold, route=route, rounds=8, params=prior.PARAMS,
                              rows=int(learn.sum()), used_features=sorted(set(used)),
                              model=identity(path), cpu_s=time.process_time() - cpu,
                              wall_s=time.monotonic() - started, offline_only=True)
                write(record_path, record)
                records.append(record)
                del dm, booster
                gc.collect()
            print('EXP614_TRAINED', arm, fold, flush=True)
        del masked
    write(ROOT / 'training.json', dict(complete=True, export=identity(ROOT / 'prepare.json'),
          driver=identity(__file__), models=[r['model'] for r in records]))


def evaluate():
    import xgboost as xgb
    assert xgb.__version__ == '3.0.5'
    sys.path.insert(0, str(Path('../exp554/validation').resolve()))
    import exp554_real_kernel_function as exporter
    sys.path.insert(0, str(Path('../exp592/validation').resolve()))
    from exp592_xgb_audit import decode, points, transition
    exporter.BUILD = BUILD
    data, x = load(), matrix()
    frozen = read(ROOT / 'prepare.json')
    checked('../exp576/build/exp576/R8.f32', frozen['original_raw'])
    checked('../exp593/' + frozen['matched_raw']['path'], frozen['matched_raw'])
    references = {name: decode(np.fromfile(path, '<f4'), data['D64'], data['mandatory']) for name, path in (
        ('R8', '../exp576/build/exp576/R8.f32'), ('K1', '../exp593/' + frozen['matched_raw']['path']))}
    with np.load('../exp585/build/exp585/evaluation.npz') as packed:
        partitions = {k[10:]: packed[k] for k in packed.files if k.startswith('partition_')}
    nx, ny = x[:, 8] + x[:, 6], x[:, 9] + x[:, 7]
    family, inverse = np.unique(x[:, 0].astype('i4'), return_inverse=True)
    assert len(family) == 26
    partitions.update(near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype('i4'),
          forced=x[:, 52].astype('i4'), source_family=x[:, 0].astype('i4'),
          block_count=x[:, 66].astype('i4'), compressed_phase=x[:, 53].astype('i4'),
          target_mismatch=(data['d0'] + data['mandatory'] != data['truth']).astype('i4'))
    counts = np.bincount(inverse)
    sampled = np.random.default_rng(20261022614).integers(26, size=(9999, 26))
    denominator = counts[sampled].sum(axis=1)
    alpha = .05 / 12
    results, eligible = {}, []
    for arm in ARMS:
        raw, paths, split_count = np.empty(ROWS, dtype='<f4'), [], np.zeros(69, dtype='i8')
        for fold in range(3):
            for route in range(16):
                path = BUILD / f'{arm}-{fold}-{route}.json'
                checked(path, read(ROOT / ('model-' + path.name))['model'])
                booster = xgb.Booster(params={'nthread': 1})
                booster.load_model(path)
                mask = (data['folds'] == fold) & (data['routes'] == route)
                raw[mask] = booster.predict(xgb.DMatrix(x[mask], nthread=1))
                for tree in read(path)['learner']['gradient_booster']['model']['trees']:
                    used = [int(f) for f, left in zip(tree['split_indices'], tree['left_children']) if left >= 0]
                    split_count += np.bincount(used, minlength=69)
                model = exporter.export_model(booster, f'native-{arm}-{fold}-{route}')
                paths.append(model['binary']['path'])
        listing = BUILD / (arm + '-models.txt')
        listing.write_text('16\n' + ''.join(p + '\n' for p in paths))
        native = BUILD / (arm + '-native.f32')
        command = [str(BUILD / 'routed-predict'), str(BUILD / 'features.f32'), str(BUILD / 'folds.u8'),
                   str(BUILD / 'routes.u8'), str(listing), str(native)]
        run = subprocess.run(command, capture_output=True, text=True)
        (ROOT / (arm + '-independent.stdout')).write_text(run.stdout)
        (ROOT / (arm + '-independent.stderr')).write_text(run.stderr)
        assert run.returncode == 0 and not run.stderr, run.stderr
        assert np.array_equal(np.fromfile(native, '<f4').view('u4'), raw.view('u4'))
        counters = json.loads(run.stdout)
        assert counters['threads'] == 1 and counters['kernel_allocations'] == 0 and counters['port_pairs'] == 59904
        prediction = decode(raw, data['D64'], data['mandatory'])
        score = points(prediction, data['truth'])
        comparisons = {}
        for name, reference in references.items():
            report = transition(prediction, reference, data['truth'], partitions)
            delta = score - points(reference, data['truth'])
            diffs = np.bincount(inverse, weights=delta)
            report['simultaneous_ci_delta_pp'] = np.quantile(
                diffs[sampled].sum(axis=1) / denominator, [alpha, 1 - alpha]).tolist()
            report['changed_rows'] = int(np.count_nonzero(prediction != reference))
            comparisons[name] = report
        sums = np.bincount(inverse, weights=score)
        ci = np.quantile(sums[sampled].sum(axis=1) / denominator, [alpha, 1 - alpha]).tolist()
        quality = bool(comparisons['R8']['delta_accuracy_pp'] >= .02
              and all(r['simultaneous_ci_delta_pp'][0] > 0 for r in comparisons.values())
              and all(g['delta_accuracy_pp'] >= -.03
                      for name, group in comparisons['R8']['groups'].items()
                      if name in ('distance', 'near_axis') for g in group.values()))
        result = dict(comparisons=comparisons, simultaneous_ci_accuracy_pp=ci,
                      quality_gate=quality, final_98_5_gate=bool(ci[0] > 98.5),
                      raw=identity(native), native_bitwise_equal=True, scalar_features_equal=True,
                      independent_counters=counters,
                      added_feature_splits={name: int(split_count[53 + k]) for k, name in enumerate(NAMES)},
                      complete_program_verified=False)
        results[arm] = result
        write(ROOT / (arm + '-report.json'), result)
        if quality:
            eligible.append(arm)
        print('EXP614_EVALUATED', arm, comparisons['R8']['candidate']['accuracy_pp'],
              comparisons['R8']['delta_accuracy_pp'], quality, flush=True)
    selected = None
    if eligible:
        best = max(results[a]['comparisons']['R8']['candidate']['accuracy_pp'] for a in eligible)
        selected = next(a for a in ARMS if a in eligible
                        and best - results[a]['comparisons']['R8']['candidate']['accuracy_pp'] <= .005)
    write(ROOT / 'evaluation.json', dict(results=results, selected=selected, eligible=eligible,
          rows=ROWS, unique_rows=ROWS, port_pairs=59904, training=identity(ROOT / 'training.json'),
          complete_program_verified=False))
    print('EXP614_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp614')
    assert sys.argv[1:] in (['prepare'], ['train'], ['evaluate'])
    {'prepare': prepare, 'train': train, 'evaluate': evaluate}[sys.argv[1]]()
