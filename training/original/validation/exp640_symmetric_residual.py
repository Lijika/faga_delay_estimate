#!/usr/bin/env python3
"""Fit two fixed symmetric-tree budgets on the frozen Q4 residual on r9."""
import gc
import inspect
import json
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import catboost as cb
import numpy as np

sys.path.insert(0, str(Path('../exp631/validation').resolve()))
import exp631_event_experts as prior

ROOT, BUILD = Path('validation/results/exp640'), Path('build/exp640')
PLAN = Path('experiment/实验640-Q4残差的对称树预算与独立解码.md')
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked
ROWS, SEED = 1_000_000, 20261023640
PARAMS = dict(iterations=16, depth=4, learning_rate=.3, loss_function='MAE',
    leaf_estimation_method='Exact', leaf_estimation_iterations=1, grow_policy='SymmetricTree',
    boosting_type='Plain', bootstrap_type='No', boost_from_average=False, random_strength=0,
    border_count=256, l2_leaf_reg=1, score_function='L2', random_seed=SEED,
    task_type='CPU', thread_count=16, allow_writing_files=False, verbose=False)


def json_prediction(model, x, rounds):
    assert np.isfinite(x).all() and np.array_equal(x, np.floor(x))
    assert model['scale_and_bias'] == [1, [0]]
    assert not model['features_info'].get('categorical_features')
    mapping = {f['feature_index']: f['flat_feature_index']
               for f in model['features_info']['float_features']}
    value = np.zeros(len(x), '<f8')
    indices = np.empty((len(x), rounds), '<u4')
    for t, tree in enumerate(model['oblivious_trees'][:rounds]):
        splits = tree['splits'] or []
        assert len(splits) <= 4 and len(tree['leaf_values']) == 1 << len(splits)
        index = np.zeros(len(x), '<u4')
        for level, split in enumerate(splits):
            assert split['split_type'] == 'FloatFeature'
            feature = mapping[split['float_feature_index']]
            border = split['border']
            # Integer deployment thresholds preserve CatBoost's strict comparison.
            assert np.array_equal(x[:, feature] > border,
                                  x[:, feature] >= np.floor(border) + 1)
            index |= (x[:, feature] > border).astype('<u4') << level
        indices[:, t] = index
        value += np.asarray(tree['leaf_values'], '<f8')[index]
    return value, indices


def self_check():
    x = np.asarray([[i >> j & 1 for j in range(4)] for i in range(16)], '<f4')
    tree = dict(splits=[dict(split_type='FloatFeature', float_feature_index=j,
                            border=.5) for j in range(4)], leaf_values=list(range(16)))
    model = dict(scale_and_bias=[1, [0]], features_info=dict(float_features=[
        dict(feature_index=j, flat_feature_index=j) for j in range(4)]),
        oblivious_trees=[tree, dict(tree, leaf_values=[2 * i for i in range(16)])])
    value, indices = json_prediction(model, x, 2)
    assert np.array_equal(indices, np.column_stack((np.arange(16), np.arange(16))))
    assert np.array_equal(value, 3 * np.arange(16))


def prepare():
    assert cb.__version__ == '1.2.8'
    self_check()
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    (ROOT / 'installed-catboost-help.txt').write_text(
        cb.__version__ + '\n' + str(inspect.signature(cb.CatBoostRegressor))
        + '\n' + cb.CatBoostRegressor.__doc__ + '\n'
        + str(inspect.signature(cb.CatBoostRegressor.save_model))
        + '\n' + cb.CatBoostRegressor.save_model.__doc__)
    data = prior.load()
    assert data['features'].shape == (ROWS, 53)
    assert np.isfinite(data['features']).all()
    assert np.array_equal(data['features'], np.floor(data['features']))
    freeze = read('../exp622/validation/results/exp622/build-freeze.json')
    t = freeze['binaries']['T']
    checked('../exp622/' + t['path'], t)
    sources = [Path(__file__), PLAN, Path(prior.__file__),
        Path('../exp623/build/exp623/data.npz'),
        Path('../exp585/build/exp585/training.npz'),
        Path('../exp593/build/exp593/targets.npz'),
        Path('../exp576/build/exp576/R8.f32'), Path('../exp631/build/exp631/M-raw.f32'),
        Path('../exp631/validation/results/exp631/training.json'),
        Path('../exp622/validation/results/exp622/build-freeze.json')]
    write(ROOT / 'prepare.json', dict(rows=ROWS, port_pairs=59904, params=PARAMS,
        python=sys.version, catboost=cb.__version__, numpy=np.__version__,
        protocol=identity(ROOT / 'protocol-original.md'), files=[identity(p) for p in sources],
        binary=t, source_pin_overlap=0, json_self_check=True,
        folds=[dict(fold=f, train_rows=int((data['folds'] != f).sum()),
                    test_rows=int((data['folds'] == f).sum()),
                    train_pairs=59904, test_pairs=59904) for f in range(3)],
        disk_free_start_bytes=shutil.disk_usage('.').free))
    print('EXP640_PREPARED', flush=True)


def train():
    assert cb.__version__ == '1.2.8'
    frozen = read(ROOT / 'prepare.json')
    assert frozen['params'] == PARAMS
    for item in frozen['files']:
        checked(item['path'], item)
    self_check()
    data = prior.load()
    target = (data['d0'] - data['base']).astype('<f4')
    weights = (1000 / np.maximum(data['d0'] + data['mandatory'], 128)).astype('<f4')
    raw = {n: np.empty(ROWS, '<f8') for n in (8, 16)}
    records = []
    for fold in range(3):
        for route in range(16):
            learn = (data['folds'] != fold) & (data['routes'] == route)
            test = (data['folds'] == fold) & (data['routes'] == route)
            assert learn.any() and test.any()
            started, cpu = time.monotonic(), time.process_time()
            model = cb.CatBoostRegressor(**PARAMS)
            model.fit(data['features'][learn], target[learn], sample_weight=weights[learn])
            assert model.tree_count_ == 16
            path = BUILD / f'S16-{fold}-{route}.json'
            model.save_model(str(path), format='json')
            dumped = read(path)
            x = data['features'][test]
            leaf = model.calc_leaf_indexes(x, thread_count=1)
            max_difference = {}
            for n in (8, 16):
                decoded, indices = json_prediction(dumped, x, n)
                assert np.array_equal(indices, leaf[:, :n])
                native = model.predict(x, ntree_end=n, thread_count=1)
                assert np.allclose(decoded, native, rtol=0, atol=1e-12)
                assert np.array_equal(prior.decode(decoded, data['base'][test], data['mandatory'][test]),
                                      prior.decode(native, data['base'][test], data['mandatory'][test]))
                raw[n][test] = decoded
                max_difference[str(n)] = float(np.abs(decoded - native).max())
            record = dict(fold=fold, route=route, model=identity(path),
                train_rows=int(learn.sum()), test_rows=int(test.sum()),
                params=model.get_all_params(), leaf_index_equal=True, integer_prediction_equal=True,
                raw_max_abs_difference=max_difference, cpu_s=time.process_time()-cpu,
                wall_s=time.monotonic()-started)
            records.append(record)
            write(ROOT / f'model-{fold}-{route}.json', record)
            del model, dumped, x, leaf
            gc.collect()
            print('EXP640_MODEL', fold, route, flush=True)
    for n in raw:
        raw[n].tofile(BUILD / f'S{n}-raw.f64')
    write(ROOT / 'training.json', dict(complete=True, records=records,
        raw={f'S{n}': identity(BUILD / f'S{n}-raw.f64') for n in raw}))


def evaluate():
    data, training = prior.load(), read(ROOT / 'training.json')
    old = read('../exp576/validation/results/exp576/R8.json')
    checked('../exp576/build/exp576/R8.f32', old['raw'])
    matched = read('../exp631/validation/results/exp631/training.json')['raw']['M']
    checked('../exp631/' + matched['path'], matched)
    predictions = {}
    for name, path, dtype in [('A', '../exp576/build/exp576/R8.f32', '<f4'),
            ('M', '../exp631/build/exp631/M-raw.f32', '<f4'),
            ('S8', str(BUILD / 'S8-raw.f64'), '<f8'),
            ('S16', str(BUILD / 'S16-raw.f64'), '<f8')]:
        if name.startswith('S'):
            checked(path, training['raw'][name])
        raw = np.fromfile(path, dtype)
        assert raw.shape == (ROWS,) and np.isfinite(raw).all()
        predictions[name] = prior.decode(raw, data['base'], data['mandatory'])
    x = data['features']
    nx, ny = x[:, 8] + x[:, 6], x[:, 9] + x[:, 7]
    partitions = dict(distance=np.searchsorted([24, 100, 300], np.abs(nx)+np.abs(ny)),
        near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype('i4'),
        source_family=x[:, 0].astype('i4'), direction=2*(nx < 0)+(ny < 0),
        forced=x[:, 52].astype('i4'))
    family = partitions['source_family']
    assert np.unique(family).size == 26
    counts = np.bincount(family, minlength=26)
    sampled = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    denominator = counts[sampled].sum(axis=1)
    reports, eligible = {}, {}
    for name in ('S8', 'S16'):
        for reference in ('A', 'M'):
            result = prior.transition(predictions[name], predictions[reference],
                                      data['truth'], partitions)
            delta = prior.points(predictions[name], data['truth']) - prior.points(
                predictions[reference], data['truth'])
            totals = np.bincount(family, weights=delta, minlength=26)
            result['simultaneous_ci_delta_pp'] = np.quantile(
                totals[sampled].sum(axis=1) / denominator, [.05/8, 1-.05/8]).tolist()
            result['changed_rows'] = int(np.count_nonzero(predictions[name] != predictions[reference]))
            reports[name + '-' + reference] = result
            print('EXP640_COMPARISON', name, reference, result['delta_accuracy_pp'],
                  result['simultaneous_ci_delta_pp'], flush=True)
        result = reports[name + '-A']
        groups = [v['delta_accuracy_pp'] for key, group in result['groups'].items()
                  if key in ('distance', 'near_axis') for v in group.values()]
        accuracy = (result['delta_accuracy_pp'] >= .02
            and result['simultaneous_ci_delta_pp'][0] > 0 and min(groups) >= -.03)
        speed = (result['delta_accuracy_pp'] >= -.05
            and result['simultaneous_ci_delta_pp'][0] >= -.08 and min(groups) >= -.15)
        eligible[name] = dict(accuracy=bool(accuracy), speed=bool(speed),
                              continue_cli=bool(accuracy or speed))
    write(ROOT / 'evaluation.json', dict(reports=reports, eligible=eligible,
        training=identity(ROOT / 'training.json'), complete_program_measured=False,
        independent_requests=False, json_all_leaves_equal=True,
        raw_precision='float64, original tree order; no leaf quantization or fusion'))
    print('EXP640_ELIGIBLE', eligible, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp640')
    assert len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'train', 'evaluate')
    resource.setrlimit(resource.RLIMIT_CPU, (1200, 1200))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    start, cpu = time.monotonic(), time.process_time()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate}[sys.argv[1]]()
    write(ROOT / (sys.argv[1] + '-resources.json'), dict(cpu_s=time.process_time()-cpu,
        wall_s=time.monotonic()-start, rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        disk_free_end_bytes=shutil.disk_usage('.').free))
