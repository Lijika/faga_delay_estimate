#!/usr/bin/env python3
"""Decompose saved full-port losses on r9 without rerunning estimators."""
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import time

import numpy as np

ROOT = Path('validation/results/exp590')
BASE = Path('..')
ROWS, PORTS = 1_000_000, 59_904


def read(path):
    return json.loads(Path(path).read_text())


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=digest.hexdigest())


def array(path, dtype, columns=1):
    value = np.fromfile(path, dtype).reshape(ROWS, columns)
    return value[:, 0] if columns == 1 else value


def metrics(prediction, truth, scale):
    error = prediction.astype(np.float64) - truth
    positive = truth > 0
    relative = np.divide(np.abs(error), truth, out=np.zeros(ROWS), where=positive)
    loss = np.where(positive, np.tanh(4 * relative), prediction != 0)
    return dict(accuracy_pp=float(100 * (1 - loss.mean())),
                mae_ps=float(np.abs(error).mean()), squared_ps=float(np.square(error).sum()),
                mean_normalized_l1=float((np.abs(error) / scale).mean()),
                mean_relative_l1=float(relative[positive].mean()),
                exact_rows=int(np.count_nonzero(error == 0)),
                zero_truth_rows=int(np.count_nonzero(~positive)))


def compare(candidate, reference, truth, scale, band, grid_weight, request_weight):
    assert np.all(truth > 0)
    ea, eb = candidate - truth, reference - truth
    aa, ab = np.abs(ea), np.abs(eb)
    ra, rb = aa / truth, ab / truth
    na, nb = aa / scale, ab / scale
    score_delta = 100 * (np.tanh(4 * rb) - np.tanh(4 * ra))
    delta_relative, delta_normalized = float((ra - rb).mean()), float((na - nb).mean())
    ratio = scale / truth
    denominator_mean = float(ratio.mean()) * delta_normalized
    denominator_covariance = float(((ratio - ratio.mean()) * (na - nb)).mean())
    assert abs(delta_relative - denominator_mean - denominator_covariance) < 1e-12
    linear = -400 * delta_relative
    saturation = float(100 * ((4 * ra - np.tanh(4 * ra)) -
                             (4 * rb - np.tanh(4 * rb))).mean())
    assert abs(float(score_delta.mean()) - linear - saturation) < 1e-9
    groups = []
    for k in range(4):
        mask = band == k
        conditional = float(score_delta[mask].mean())
        groups.append(dict(band=k, rows=int(mask.sum()),
            delta_accuracy_pp=conditional, contribution_pp=conditional * request_weight[k],
            delta_mae_ps=float((aa[mask] - ab[mask]).mean()),
            delta_mean_relative_l1=float((ra[mask] - rb[mask]).mean()),
            delta_mean_normalized_l1=float((na[mask] - nb[mask]).mean())))
    standardized = float(sum(grid_weight[k] * groups[k]['delta_accuracy_pp'] for k in range(4)))
    assert abs(sum(g['contribution_pp'] for g in groups) - score_delta.mean()) < 1e-9
    exact_lost, exact_gained = (eb == 0) & (ea != 0), (eb != 0) & (ea == 0)
    tails = []
    # Freeze bins before examining the new diagnostic; all rows remain included.
    labels = np.searchsorted([.001, .005, .01, .05, .1, .25], rb, side='right')
    for k in range(7):
        mask = labels == k
        tails.append(dict(reference_relative_error_band=k, rows=int(mask.sum()),
                          delta_sse_ps2=float((np.square(ea[mask]) - np.square(eb[mask])).sum()),
                          contribution_pp=float(score_delta[mask].sum() / ROWS)))
    return dict(delta_accuracy_pp=float(score_delta.mean()),
        delta_sse_ps2=float((np.square(ea) - np.square(eb)).sum()),
        delta_mae_ps=float((aa - ab).mean()), delta_mean_normalized_l1=delta_normalized,
        delta_mean_relative_l1=delta_relative, relative_l1_linear_pp=linear,
        saturation_pp=saturation, normalized_change_mean_term=denominator_mean,
        normalized_change_covariance_term=denominator_covariance,
        uniform_band_standardized_delta_pp=standardized,
        request_band_weight_shift_pp=float(score_delta.mean()) - standardized,
        groups=groups, reference_error_bands=tails,
        exact_lost_rows=int(exact_lost.sum()), exact_gained_rows=int(exact_gained.sum()),
        exact_lost_contribution_pp=float(score_delta[exact_lost].sum() / ROWS),
        exact_gained_contribution_pp=float(score_delta[exact_gained].sum() / ROWS),
        improved_rows=int(np.count_nonzero(aa < ab)), worsened_rows=int(np.count_nonzero(aa > ab)))


def main():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp590')
    assert os.environ['OPENBLAS_NUM_THREADS'] == os.environ['OMP_NUM_THREADS'] == '1'
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
    started, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True, exist_ok=True)
    files = []

    def load(path, dtype='<i4', columns=1):
        path = BASE / path
        files.append(identity(path))
        return array(path, dtype, columns).astype(np.float64 if dtype == '<f4' else np.int64)

    labels = load('exp554/build/exp554/labels.i32', columns=4)
    ports = load('exp554/build/exp554/ports.i32', columns=2)
    folds = load('exp554/build/exp554/folds.u8', 'u1')
    events = load('exp536/build/exp536/events.i32', columns=9)
    query_path = BASE / 'exp554/build/exp554/queries.bin'
    files.append(identity(query_path))
    query = np.fromfile(query_path, '<i4', offset=12).reshape(ROWS, 10).astype(np.int64)
    truth, d0, mandatory = labels[:, :3].T
    pair = ports[:, 0] * 288 + ports[:, 1]
    assert np.bincount(pair, minlength=PORTS).min() > 0
    for k in range(3):
        for mask in (folds == k, folds != k):
            assert np.bincount(pair[mask], minlength=PORTS).min() > 0
    provenance = read(BASE / 'exp570/validation/results/exp570-recovery-01/input.json')
    assert provenance['unique_rows'] == ROWS and provenance['pairs'] == PORTS
    x, y = query[:, 2] - events[:, 0] + events[:, 2], query[:, 3] - events[:, 1] + events[:, 3]
    ax, ay = np.abs(x), np.abs(y)
    column = (((((2 * (x < 0) + (y < 0)) * 10 + ax % 10) * 12 + ay % 12) * 12 + ax // 10) * 46 + ay // 12)
    keys = load('exp570/build/exp570-recovery-01/keys.i32', columns=2)
    assert np.array_equal(keys, np.column_stack((pair, column)))
    scale = 128 + 125 * (ax // 10 + ay // 12)
    band = np.searchsorted([1, 4, 16], ax // 10 + ay // 12, side='right')
    grid = np.arange(264960)
    grid_band = np.searchsorted([1, 4, 16], grid % 46 + grid // 46 % 12, side='right')
    grid_weight, request_weight = np.bincount(grid_band) / 264960., np.bincount(band) / ROWS
    old = read(BASE / 'exp554/validation/results/exp554/report.json')
    old_prediction = load('exp554/build/exp554/predictions.i32', columns=len(old['prediction_names']))
    predictions = {'exp354': old_prediction[:, old['prediction_names'].index('exp354')],
                   'Q-base': old_prediction[:, old['prediction_names'].index('O')],
                   'D0-plus-mandatory': d0 + mandatory}
    for name in ('G', 'F', 'T'):
        predictions[name + '-base'] = load('exp557/build/exp557/' + name + '-base.i32') + mandatory
        predictions[name + '32'] = load('exp557/build/exp557/' + name + '32.i32')
    predictions['C-base'] = load('exp564/build/exp564/C64-base.i32') + mandatory
    predictions['C32'] = load('exp564/build/exp564/C32.i32')
    for name, filename in [('E-base', 'base.i32'), ('Ef-base', 'float-base.i32'), ('E32', 'E32.i32')]:
        predictions[name] = load('exp570/build/exp570-recovery-01/' + filename)
        if name != 'E32':
            predictions[name] += mandatory
    statistics = {n: metrics(p, truth, scale) for n, p in predictions.items()}
    checks = [('exp557/validation/results/exp557/report.json', {}),
              ('exp564/validation/results/exp564/report.json', {'C-base': 'C-base'}),
              ('exp570/validation/results/exp570-recovery-01/report.json',
               {'L-base': 'E-base', 'Lf-base': 'Ef-base'})]
    for path, rename in checks:
        report = read(BASE / path)
        for name, previous in report['statistics'].items():
            name = rename.get(name, name)
            if name not in statistics:
                continue
            current = statistics[name]
            assert abs(current['accuracy_pp'] - previous['accuracy_pp']) < 1e-9
            assert abs(current['mae_ps'] - previous['mae_ps']) < 1e-9
            assert current['squared_ps'] == previous['squared_ps']
    comparisons = {}
    for name, reference in [('E32', 'exp354'), ('E32', 'G32'), ('C32', 'F32'),
                             ('T32', 'F32'), ('Q-base', 'exp354')]:
        comparisons[name + '-' + reference] = compare(predictions[name], predictions[reference],
            truth, scale, band, grid_weight, request_weight)
    # Existing full-port results must reproduce the reported inverse ordering.
    assert statistics['E32']['squared_ps'] < statistics['exp354']['squared_ps']
    assert statistics['E32']['accuracy_pp'] < statistics['exp354']['accuracy_pp']
    assert statistics['E32']['mae_ps'] < statistics['G32']['mae_ps']
    assert statistics['E32']['accuracy_pp'] < statistics['G32']['accuracy_pp']
    stages = {}
    for name, background in [('G32', 'G-base'), ('F32', 'F-base'), ('T32', 'T-base'),
                              ('C32', 'C-base'), ('E32', 'E-base')]:
        nominal_error = predictions[background] - predictions['Q-base']
        correction = predictions[name] - predictions[background]
        actual_correction = truth - predictions['Q-base']
        correction_error = correction - actual_correction
        assert np.array_equal(nominal_error + correction_error, predictions[name] - truth)
        raw_name = name if name != 'E32' else 'E32'
        folder = 'exp557/build/exp557' if name[0] in 'GFT' else (
                 'exp564/build/exp564' if name == 'C32' else 'exp570/build/exp570-recovery-01')
        raw = load(folder + '/' + raw_name + '.f32', '<f4')
        continuous = np.maximum(0, raw + predictions[background] - mandatory) + mandatory
        stages[name] = dict(nominal_mae_ps=float(np.abs(nominal_error).mean()),
            correction_error_mae_ps=float(np.abs(correction_error).mean()),
            opposite_error_sign_rows=int(np.count_nonzero(nominal_error * correction_error < 0)),
            nominal_correction_error_correlation=float(np.corrcoef(nominal_error, correction_error)[0, 1]),
            continuous=metrics(continuous, truth, scale),
            rounding_delta_accuracy_pp=statistics[name]['accuracy_pp'] - metrics(continuous, truth, scale)['accuracy_pp'])
    result = dict(rows=ROWS, port_pairs=PORTS, all_folds_and_complements_full_port=True,
        provenance=identity(BASE / 'exp570/validation/results/exp570-recovery-01/input.json'),
        files=files, sources=[identity(Path(__file__)), identity(Path('experiment/实验590-归一化损失与官方评分的逐行分解.md'))],
        statistics=statistics, comparisons=comparisons, stages=stages,
        grid_band_weight=grid_weight.tolist(), request_band_weight=request_weight.tolist(),
        request_to_grid_band_weight=(request_weight / grid_weight).tolist(),
        verified_saved_reports=True, decomposition_checks_passed=True, model_reruns=0,
        development_only=True, independent_requests_used=0,
        wall_s=time.monotonic() - started, cpu_s=time.process_time() - cpu,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    with (ROOT / 'report.json').open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print('EXP590_COMPLETE_FULL_PORT_DECOMPOSITION', flush=True)


if __name__ == '__main__':
    main()
