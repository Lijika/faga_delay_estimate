#!/usr/bin/env python3
"""Test pooled H/V replacement experts without OOF stacking supervision."""
import ast
import gc
import inspect
import os
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import catboost as cb
import numpy as np

sys.path.insert(0, str(Path('../exp677/validation').resolve()))
import exp677_map_events as prior
from exp592_xgb_audit import decode, points, stats, transition

ROOT, BUILD = Path('validation/results/exp678'), Path('build/exp678')
PLAN = Path('experiment/实验678-HV事件共享替换专家与容量消融.md')
read, write, identity, checked = prior.read, prior.write, prior.identity, prior.checked
ROWS, SEED = prior.ROWS, 20261024678
ARMS = ('H8', 'V8', 'HV8', 'H64', 'V64', 'HV64')
PARAMS = dict(iterations=64, depth=4, learning_rate=.3, loss_function='MAE',
    leaf_estimation_method='Exact', leaf_estimation_iterations=1, grow_policy='SymmetricTree',
    boosting_type='Plain', bootstrap_type='No', boost_from_average=False, random_strength=0,
    border_count=256, l2_leaf_reg=1, score_function='L2', random_seed=SEED,
    task_type='CPU', thread_count=1, allow_writing_files=False, verbose=False)
DECODER = Path('../exp640/validation/exp640_symmetric_residual.py')


def decoder():
    # Reuse the audited decoder without importing its XGBoost training dependency.
    module = ast.parse(DECODER.read_text())
    nodes = [n for n in module.body if isinstance(n, ast.FunctionDef)
             and n.name in ('json_prediction', 'self_check')]
    assert [n.name for n in nodes] == ['json_prediction', 'self_check']
    scope = dict(np=np)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(DECODER), 'exec'), scope)
    scope['self_check']()
    return scope['json_prediction']


def combine(old, event, raw, arm):
    assert arm in ARMS and old.shape == event.shape == (ROWS,)
    n = 64 if arm.endswith('64') else 8
    output = old.copy()
    for label, value in (('H', 1), ('V', 2)):
        mask = event == value
        if label in arm:
            output[mask] = raw[n][mask]
    assert np.array_equal(output[event == 0], old[event == 0])
    return output


def self_check(gap):
    prior.self_check(gap['Block'])
    prior.source.self_check(gap)
    predict = decoder()
    x = np.asarray([[i >> j & 1 for j in range(4)] for i in range(16)], '<f4')
    model = dict(scale_and_bias=[1, [0]], features_info=dict(float_features=[
        dict(feature_index=j, flat_feature_index=j) for j in range(4)]),
        oblivious_trees=[dict(splits=[dict(split_type='FloatFeature',
            float_feature_index=j, border=.5) for j in range(4)],
            leaf_values=list(range(16)))] * 64)
    value, indices = predict(model, x, 64)
    assert np.array_equal(value, 64*np.arange(16))
    assert np.array_equal(indices, np.tile(np.arange(16)[:, None], (1, 64)))
    old = np.zeros(ROWS)
    event = np.zeros(ROWS, 'u1')
    event[:3] = [0, 1, 2]
    raw = {8: np.ones(ROWS), 64: np.full(ROWS, 2.)}
    for arm in ARMS:
        out = combine(old, event, raw, arm)
        n = 2 if arm.endswith('64') else 1
        assert out[:3].tolist() == [0, n if 'H' in arm else 0, n if 'V' in arm else 0]
        assert not np.any(out[3:])


def main():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp678')
    assert os.environ['OPENBLAS_NUM_THREADS'] == os.environ['OMP_NUM_THREADS'] == '1'
    assert cb.__version__ == '1.2.8'
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    start, cpu = time.monotonic(), time.process_time()
    free_start = shutil.disk_usage('.').free
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/'protocol-original.md')
    (ROOT/'installed-catboost-help.txt').write_text(cb.__version__ + '\n'
        + str(inspect.signature(cb.CatBoostRegressor)) + '\n'
        + str(inspect.signature(cb.CatBoostRegressor.fit)) + '\n'
        + str(inspect.signature(cb.CatBoostRegressor.predict)) + '\n'
        + str(inspect.signature(cb.CatBoostRegressor.calc_leaf_indexes)) + '\n'
        + cb.CatBoostRegressor.save_model.__doc__)
    inputs = []
    for item in read('../exp677/validation/results/exp677/freeze.json')['files']:
        path = Path('../exp677')/item['path']
        checked(path, item)
        inputs.append(identity(path))
    for path in (Path(__file__), Path('validation/exp678_run.sh'), PLAN,
                 ROOT/'protocol-original.md', DECODER,
                 Path(prior.__file__), Path(prior.source.__file__),
                 Path('../exp677/validation/results/exp677/report.json')):
        inputs.append(identity(path))
    gap = read('../exp652/doc/eda比赛文件/arch/SRB_Gap.json')['Gap']
    self_check(gap)
    data = prior.source.load()
    data['base'] = prior.curve_base(data)
    original = data['features']
    h, v, bands, ends = prior.events(original[:, 28:32], gap['Block'])
    assert np.array_equal(h, original[:, 52]) and not np.any(h & v)
    assert int(h.sum()) == 18064 and int(v.sum()) == 2613
    event = h.astype('u1')+2*v
    x = np.column_stack((original, prior.source.geometry(original, gap), bands, ends)).astype('<f4')
    assert x.shape == (ROWS, 71) and np.isfinite(x).all()
    assert np.array_equal(x, np.floor(x))
    folds, pair = data['folds'], data['pair'].astype('i4')
    support = []
    for fold in range(3):
        for label, value in (('H', 1), ('V', 2)):
            learn, test = (folds != fold) & (event == value), (folds == fold) & (event == value)
            assert learn.sum() >= 1000 and test.sum() >= 500
            assert not np.intersect1d(data['clusters'][learn], data['clusters'][test]).size
            support.append(dict(fold=fold, event=label, source_pin_overlap=0,
                **{name: dict(rows=int(mask.sum()), source_ports=len(np.unique(pair[mask]//288)),
                    target_ports=len(np.unique(pair[mask]%288)), port_pairs=len(np.unique(pair[mask])),
                    route_counts=np.bincount(data['routes'][mask], minlength=16).tolist())
                   for name, mask in (('train', learn), ('test', test))}))
    old = np.fromfile(prior.OLD_RAW, '<f8')
    assert old.shape == (ROWS,) and np.isfinite(old).all()
    reference = decode(old, data['base'], data['mandatory'])
    replay = stats(reference, data['truth'])
    expected = read('../exp677/validation/results/exp677/report.json')['metrics']
    assert replay['exact_rows'] == expected['exact_rows']
    assert all(abs(replay[key]-expected[key]) <= 1e-10 for key in replay if key != 'exact_rows')
    write(ROOT/'freeze.json', dict(files=inputs, params=PARAMS, arms=ARMS,
        rows=ROWS, columns=71, seed=SEED, source_pin_overlap=0, support=support,
        baseline_metrics=replay, baseline_expected=expected,
        python=sys.version, catboost=cb.__version__, numpy=np.__version__,
        independent_requests=False, complete_program_runs=0, new_exact_rows=0,
        decoder_self_check=True, geometric_self_check=True, routing_self_check=True,
        disk_free_start_bytes=free_start))
    print('EXP678_FROZEN', [(s['fold'], s['event'], s['train']['rows'], s['test']['rows'])
                            for s in support], flush=True)
    target = (data['d0']-data['base']).astype('<f4')
    weights = (1000/np.maximum(data['d0']+data['mandatory'], 128)).astype('<f4')
    raw = {n: old.copy() for n in (8, 64)}
    predict, records = decoder(), []
    for fold in range(3):
        for label, value in (('H', 1), ('V', 2)):
            learn, test = (folds != fold) & (event == value), (folds == fold) & (event == value)
            started, used_cpu = time.monotonic(), time.process_time()
            model = cb.CatBoostRegressor(**PARAMS)
            model.fit(x[learn], target[learn], sample_weight=weights[learn])
            assert model.tree_count_ == 64
            path = BUILD/f'{label}64-{fold}.json'
            model.save_model(str(path), format='json')
            dumped = read(path)
            leaf = model.calc_leaf_indexes(x[test], thread_count=1)
            differences = {}
            for n in (8, 64):
                decoded, indices = predict(dumped, x[test], n)
                native = model.predict(x[test], ntree_end=n, thread_count=1)
                assert np.array_equal(indices, leaf[:, :n])
                assert np.allclose(decoded, native, rtol=0, atol=1e-10)
                assert np.array_equal(decode(decoded, data['base'][test], data['mandatory'][test]),
                                      decode(native, data['base'][test], data['mandatory'][test]))
                raw[n][test] = decoded
                differences[str(n)] = float(np.abs(decoded-native).max())
            record = dict(event=label, fold=fold, model=identity(path), params=model.get_all_params(),
                leaf_index_equal=True, integer_prediction_equal=True, raw_max_abs_difference=differences,
                used_features=sorted({s['float_feature_index'] for tree in dumped['oblivious_trees']
                                      for s in (tree['splits'] or [])}),
                cpu_s=time.process_time()-used_cpu, wall_s=time.monotonic()-started)
            write(ROOT/f'model-{label}-{fold}.json', record)
            records.append(record)
            print('EXP678_MODEL', label, fold, record['cpu_s'], flush=True)
            del model, dumped, leaf
            gc.collect()
    for n in raw:
        raw[n].tofile(BUILD/f'HV{n}-raw.f64')
    write(ROOT/'training.json', dict(complete=True, records=records,
        raw={str(n): identity(BUILD/f'HV{n}-raw.f64') for n in raw}))
    nx, ny = original[:, 8]+original[:, 6], original[:, 9]+original[:, 7]
    family = original[:, 0].astype('i4')
    assert np.unique(family).size == 26
    partitions = dict(event=event, distance=np.searchsorted([24, 100, 300], np.abs(nx)+np.abs(ny)),
        near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype('i4'),
        direction=2*(nx < 0)+(ny < 0), source_family=family, route=data['routes'], fold=folds,
        line_mismatch=(data['d0']+data['mandatory'] != data['truth']).astype('i4'))
    counts = np.bincount(family, minlength=26)
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    reports, eligible, scores = {}, [], {}
    for arm in ARMS:
        prediction = decode(combine(old, event, raw, arm), data['base'], data['mandatory'])
        assert np.array_equal(prediction[event == 0], reference[event == 0])
        result = transition(prediction, reference, data['truth'], partitions)
        change = points(prediction, data['truth'])-points(reference, data['truth'])
        totals = np.bincount(family, weights=change, minlength=26)
        result['simultaneous_ci95_pp'] = np.quantile(totals[draws].sum(axis=1)/counts[draws].sum(axis=1),
            [.05/(2*len(ARMS)), 1-.05/(2*len(ARMS))]).tolist()
        result['changed_rows'] = int(np.count_nonzero(prediction != reference))
        result['local_accuracy_pp'] = {label: dict(reference=float(points(reference[mask], data['truth'][mask]).mean()),
            candidate=float(points(prediction[mask], data['truth'][mask]).mean()))
            for label, mask in (('H', h), ('V', v), ('ordinary', event == 0))}
        minimum = min(v['delta_accuracy_pp'] for key, group in result['groups'].items()
                      if key in ('distance', 'near_axis') for v in group.values())
        affected = [result['groups']['event'][str(i)]['delta_accuracy_pp']
                    for label, i in (('H', 1), ('V', 2)) if label in arm]
        result['minimum_primary_group_delta_pp'] = minimum
        result['quality_gate'] = bool(result['delta_accuracy_pp'] >= .01
            and result['simultaneous_ci95_pp'][0] > 0 and minimum >= -.03 and min(affected) >= 0)
        if result['quality_gate']:
            eligible.append(arm)
        reports[arm], scores[arm] = result, change
        print('EXP678_RESULT', arm, result['delta_accuracy_pp'], result['simultaneous_ci95_pp'],
              result['quality_gate'], flush=True)
    for n in (8, 64):
        assert np.allclose(scores[f'HV{n}'], scores[f'H{n}']+scores[f'V{n}'], rtol=0, atol=1e-12)
    def selection_key(arm):
        trees = 64 if arm.endswith('64') else 8
        work = trees*sum(np.count_nonzero(event == i) for label, i in (('H', 1), ('V', 2)) if label in arm)
        return (-reports[arm]['delta_accuracy_pp'], work, arm)
    selected = min(eligible, key=selection_key) if eligible else None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_s, wall_s, rss = time.process_time()-cpu, time.monotonic()-start, usage.ru_maxrss*1024
    added = sum(p.stat().st_size for directory in (ROOT, BUILD) for p in directory.rglob('*') if p.is_file())
    resource_gate = cpu_s <= 600 and wall_s <= 900 and rss <= 2_000_000_000 and added <= 50_000_000
    write(ROOT/'evaluation.json', dict(reports=reports, eligible=eligible, selected=selected,
        complete_program_runs=0, new_exact_rows=0, independent_requests=False,
        source_pin_overlap=0, background_replayed=True, all_decoder_checks_passed=True,
        combination_additivity_passed=True, ordinary_predictions_unchanged=True,
        cpu_s=cpu_s, wall_s=wall_s, rss_bytes=rss, added_bytes=added, resource_gate=resource_gate,
        released_bytes=0, disk_free_end_bytes=shutil.disk_usage('.').free,
        continue_cli=bool(selected and resource_gate), final_accuracy_goal_verified=False))
    assert resource_gate
    print('EXP678_COMPLETE', selected, cpu_s, wall_s, rss, flush=True)


if __name__ == '__main__':
    main()
