#!/usr/bin/env python3
"""Audit frozen full-port residual predictions and tree support on r9."""
import json
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp590/validation').resolve()))
from exp590_metric_diagnosis import array, identity, read

ROOT = Path('validation/results/exp592')
ROWS = 1_000_000
STATES = ['exact', '(0,.1%)', '[.1%,.5%)', '[.5%,1%)', '[1%,5%)', '>=5%']
TRACE = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
    formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f4'],
    offsets=[0, 216, 224, 228, 232, 236], itemsize=240))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def decode(raw, base, mandatory):
    return (np.maximum(0, raw.astype('f8') + base) + .5).astype('i8') + mandatory


def points(predicted, truth):
    assert np.all(truth > 0)
    return 100 * (1 - np.tanh(4 * np.abs(predicted - truth) / truth))


def stats(predicted, truth):
    error = predicted - truth
    return dict(accuracy_pp=float(points(predicted, truth).mean()),
        mae_ps=float(np.abs(error).mean()), relative_l1=float((np.abs(error) / truth).mean()),
        exact_rows=int(np.count_nonzero(error == 0)))


def quantiles(values):
    assert len(values)
    return dict(zip(['min', 'p01', 'p10', 'median', 'p90', 'max'],
                    np.quantile(values, [0, .01, .1, .5, .9, 1]).tolist()))


def state(predicted, truth):
    relative = np.abs(predicted - truth) / truth
    value = np.searchsorted([.001, .005, .01, .05], relative, side='right') + 1
    value[relative == 0] = 0
    return value


def transition(predicted, reference, truth, partitions):
    before, after = state(reference, truth), state(predicted, truth)
    delta = points(predicted, truth) - points(reference, truth)
    counts = np.bincount(6 * before + after, minlength=36).reshape(6, 6)
    contribution = np.bincount(6 * before + after, weights=delta,
                               minlength=36).reshape(6, 6) / ROWS
    assert counts.sum() == ROWS and abs(contribution.sum() - delta.mean()) < 1e-10
    ea, eb = np.abs(predicted - truth), np.abs(reference - truth)
    original = before == 0
    result = dict(reference=stats(reference, truth), candidate=stats(predicted, truth),
        states=STATES, counts=counts.tolist(), contribution_pp=contribution.tolist(),
        delta_accuracy_pp=float(delta.mean()), improved_rows=int((ea < eb).sum()),
        worse_rows=int((ea > eb).sum()), exact_lost_rows=int((original & (ea > 0)).sum()),
        exact_lost_contribution_pp=float(delta[original].sum() / ROWS),
        groups={group: {str(int(k)): dict(rows=int((values == k).sum()),
                  delta_accuracy_pp=float(delta[values == k].mean()),
                  contribution_pp=float(delta[values == k].sum() / ROWS))
                 for k in np.unique(values)} for group, values in partitions.items()})
    return result


def tree_audit(features, routes, weights, raw, names, files):
    rebuilt = np.zeros(ROWS, dtype='<f4')
    feature_count = np.zeros(53, dtype='i8')
    feature_gain = np.zeros(53)
    leaf_records, route_records = [], []
    max_hessian_relative_error = 0.
    for route in range(16):
        path = Path(f'../exp579/build/exp579/R8-final-{route}.json')
        files.append(identity(path))
        model = read(path)['learner']
        assert float(model['learner_model_param']['base_score']) == 0
        trees = model['gradient_booster']['model']['trees']
        assert len(trees) == 8
        selected = np.flatnonzero(routes == route)
        x, w = features[selected], weights[selected].astype('f8')
        output = np.zeros(len(selected), dtype='<f4')
        for t, tree in enumerate(trees):
            assert not tree['categories'] and not any(tree['split_type'])
            left, right, feature, cut = [np.asarray(tree[k]) for k in
                ('left_children', 'right_children', 'split_indices', 'split_conditions')]
            cut = cut.astype('<f4')
            internal = left >= 0
            assert np.all(cut[internal] == np.ceil(cut[internal]))
            assert np.all(np.abs(cut[internal]) <= 32767)
            feature_count += np.bincount(feature[internal], minlength=53)
            feature_gain += np.bincount(feature[internal], weights=np.asarray(tree['loss_changes'])[internal], minlength=53)
            node = np.zeros(len(selected), dtype='i4')
            for depth in range(5):
                count = np.bincount(node, minlength=len(left))
                summed = np.bincount(node, weights=w, minlength=len(left))
                reached = count > 0
                stored = np.asarray(tree['sum_hessian'])
                difference = np.abs(summed[reached] - stored[reached]) / np.maximum(1, stored[reached])
                # A leaf stays reached in later rounds; its original training support stays equal.
                max_hessian_relative_error = max(max_hessian_relative_error, float(difference.max()))
                live = left[node] >= 0
                if not live.any():
                    break
                assert depth < 4
                current = node[live]
                node[live] = np.where(x[live, feature[current]] < cut[current], left[current], right[current])
            assert np.all(left[node] < 0)
            output += cut[node]
            count = np.bincount(node, minlength=len(left))
            summed = np.bincount(node, weights=w, minlength=len(left))
            square = np.bincount(node, weights=w * w, minlength=len(left))
            for leaf in np.flatnonzero(~internal):
                assert count[leaf] > 0 and summed[leaf] > 0
                leaf_records.append(dict(route=route, tree=t, node=int(leaf), rows=int(count[leaf]),
                    weight_sum=float(summed[leaf]), effective_rows=float(summed[leaf] ** 2 / square[leaf]),
                    correction_ps=float(cut[leaf])))
        rebuilt[selected] = output
        route_records.append(dict(route=route, rows=len(selected), trees=len(trees)))
    assert np.array_equal(rebuilt.view('u4'), raw.copy().view('u4')), 'native float mismatch'
    assert max_hessian_relative_error < 3e-5, max_hessian_relative_error
    write(ROOT / 'leaf-support.json', leaf_records)
    return dict(native_bitwise_equal=True, max_hessian_relative_error=max_hessian_relative_error,
        routes=route_records, total_leaves=len(leaf_records),
        row_support=quantiles([r['rows'] for r in leaf_records]),
        weighted_support=quantiles([r['weight_sum'] for r in leaf_records]),
        effective_support=quantiles([r['effective_rows'] for r in leaf_records]),
        leaves_below_10_rows=sum(r['rows'] < 10 for r in leaf_records),
        leaves_below_100_rows=sum(r['rows'] < 100 for r in leaf_records),
        features=[dict(index=i, name=name, splits=int(feature_count[i]), gain=float(feature_gain[i]))
                  for i, name in enumerate(names)],
        relative_feature_split_fraction=float(feature_count[:26].sum() / feature_count.sum()),
        relative_feature_gain_fraction=float(feature_gain[:26].sum() / feature_gain.sum()))


def main():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp592')
    ROOT.mkdir(parents=True, exist_ok=False)
    started, cpu, disk = time.monotonic(), time.process_time(), shutil.disk_usage('.').free
    protocol = Path('experiment/实验592-XGBoost残差训练与推理的系统审计.md')
    shutil.copyfile(protocol, ROOT / 'protocol-original.md')
    files = []

    def load(path, dtype='<i4', columns=1):
        path = Path('..') / path
        files.append(identity(path))
        return array(path, dtype, columns)

    labels = load('exp554/build/exp554/labels.i32', columns=4).astype('i8')
    ports = load('exp554/build/exp554/ports.i32', columns=2)
    folds = load('exp554/build/exp554/folds.u8', 'u1')
    clusters = load('exp554/build/exp554/clusters.i32')
    query_path = Path('../exp554/build/exp554/queries.bin')
    files.append(identity(query_path))
    query = np.fromfile(query_path, '<i4', offset=12).reshape(ROWS, 10)
    trace_path = Path('../exp589/build/exp589/D64-trace.bin')
    files.append(identity(trace_path))
    trace = np.memmap(trace_path, dtype=TRACE, mode='r', shape=(ROWS,))
    features, raw = trace['features'], trace['raw']
    assert np.isfinite(features).all() and np.isfinite(raw).all()
    names = read('../exp554/validation/results/exp554/features.json')['names']
    assert len(names) == 53
    pair = ports[:, 0] * 288 + ports[:, 1]
    assert np.bincount(pair, minlength=59904).min() > 0
    input_provenance = read('../exp570/validation/results/exp570-recovery-01/input.json')
    assert input_provenance['unique_rows'] == ROWS and input_provenance['pairs'] == 59904
    _, source = np.unique(query[:, [0, 1, 4, 5]], axis=0, return_inverse=True)
    links = np.unique(np.column_stack((source, clusters)), axis=0)
    assert len(links) == len(np.unique(source)) == len(np.unique(clusters))
    fold_records = []
    for fold in range(3):
        test = folds == fold
        assert np.unique(pair[test]).size == np.unique(pair[~test]).size == 59904
        assert not np.intersect1d(source[test], source[~test]).size
        fold_records.append(dict(fold=fold, train_rows=int((~test).sum()), test_rows=int(test.sum()),
            train_port_pairs=59904, test_port_pairs=59904, source_pin_overlap=0))
    truth, d0, mandatory = labels[:, :3].T
    assert np.array_equal(trace['mandatory'], mandatory)
    base = load('exp575/build/exp575/N192-base.i32').astype('i8')
    oof = load('exp576/build/exp576/R8.f32', '<f4')
    current = trace['base'].astype('i8')
    x, y = features[:, 8] + features[:, 6], features[:, 9] + features[:, 7]
    ax, ay = np.abs(x), np.abs(y)
    partitions = dict(distance=np.searchsorted([1, 4, 16], ax // 10 + ay // 12, side='right'),
        near_axis=((ax < 20) | (ay < 24)).astype('i4'),
        target_mismatch=(d0 + mandatory != truth).astype('i4'))
    old = decode(oof, base, mandatory)
    d64_oof = decode(oof, current, mandatory)
    final = decode(raw, current, mandatory)
    assert np.array_equal(final, trace['prediction'])
    comparisons = {name: transition(p, b + mandatory, truth, partitions) for name, p, b in
        [('N192-R8-OOF', old, base), ('D64-R8-OOF', d64_oof, current),
         ('D64-R8-final-in-sample', final, current)]}
    deadzones = {}
    for background, correction, label in ((base, oof, 'N192-OOF'), (current, oof, 'D64-OOF')):
        reference = decode(correction, background, mandatory)
        deadzones[label] = {str(threshold): transition(decode(np.where(np.abs(correction) < threshold, 0, correction),
            background, mandatory), reference, truth, partitions) for threshold in (.5, 1., 2., 4.)}
    weights = (1000 / np.maximum(d0 + mandatory, 128)).astype('<f4')
    ideal = 1000 / truth
    changed = d0 + mandatory != truth
    residual_mismatch = truth - mandatory - d0
    routes = (4 * (2 * (x < 0) + (y < 0)) + 2 * (ax >= 20) + (ay >= 24)).astype('i4')
    saved_routes = load('exp576/build/exp576/routes.u8', 'u1')
    assert np.array_equal(routes, saved_routes)
    trees = tree_audit(features, routes, weights, raw, names, files)
    all_same = {name: bool(np.all(features[:, i] == features[0, i])) for i, name in enumerate(names)}
    result = dict(rows=ROWS, full_port_pairs=59904, source_pins=len(links), folds=fold_records,
        comparisons=comparisons, deadzone_development_diagnostics=deadzones, tree_audit=trees,
        target=dict(mismatched_rows=int(changed.sum()), residual_delta_ps=quantiles(residual_mismatch),
            kernel_oracle=stats(d0 + mandatory, truth),
            current_final_mismatched_group=stats(final[changed], truth[changed]),
            current_final_matched_group=stats(final[~changed], truth[~changed])),
        weights=dict(training=quantiles(weights), ideal=quantiles(ideal),
            training_over_ideal=quantiles(weights / ideal),
            floor_128_rows=int((d0 + mandatory < 128).sum()),
            weight_not_integer_count=True),
        background_migration=dict(changed_rows=int((current != base).sum()),
            difference_ps=quantiles(current - base),
            old_target=quantiles(d0 - base), new_target=quantiles(d0 - current)),
        constant_features=[name for name, same in all_same.items() if same],
        implementation=dict(no_missing_features=True, finite_raw=True, final_integer_exact=True,
            categorical_splits=False, integer_split_thresholds=True, base_score=0),
        evidence=files, script=identity(__file__), protocol=identity(protocol),
        cost=dict(cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
            rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            disk_start_bytes=disk, disk_end_bytes=shutil.disk_usage('.').free),
        scope='Existing complete development 1M. Dead-zones are descriptive, final-model predictions are in-sample. No new selected model or independent generalization claim.')
    write(ROOT / 'report.json', result)
    print('EXP592_COMPLETE', json.dumps(dict(
        accuracy={n: r['candidate']['accuracy_pp'] for n, r in comparisons.items()},
        delta={n: r['delta_accuracy_pp'] for n, r in comparisons.items()},
        deadzones={n: {t: r['delta_accuracy_pp'] for t, r in v.items()} for n, v in deadzones.items()},
        target_mismatched_rows=result['target']['mismatched_rows'],
        leaf_support=trees['row_support'], cost=result['cost'])), flush=True)


if __name__ == '__main__':
    main()
