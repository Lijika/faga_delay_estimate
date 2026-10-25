#!/usr/bin/env python3
"""Fit a y-short residual and fuse its code with the frozen Q4 lookup."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp619/validation').resolve()))
import exp619_scalar_phase as scalar
sys.path.insert(0, str(Path('../exp592/validation').resolve()))
from exp592_xgb_audit import decode, points, stats, transition

prior = scalar.prior
ROOT, BUILD = Path('validation/results/exp639'), Path('build/exp639')
PLAN = Path('experiment/实验639-短轴条件残量与Q4的六位融合编码.md')
Q4 = Path('../exp619/build/exp619/Q4.p4')
PAIRS, PHASES, ROWS = 59904, 120, 1_000_000
TRAIN = [(x, y) for y in (0, 1) for x in (4, 6, 8, 11)]
VALID = [(x, y) for y in (0, 1) for x in (5, 7, 9, 10)]
read, identity, checked = prior.read, prior.identity, prior.checked


def write(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')


def pack6(codes):
    c = np.asarray(codes, dtype='u4').reshape(-1, 4)
    assert np.all(c < 64)
    word = c[:, 0] | (c[:, 1] << 6) | (c[:, 2] << 12) | (c[:, 3] << 18)
    return np.column_stack((word & 255, (word >> 8) & 255, word >> 16)).astype('u1').ravel()


def unpack6(payload, count):
    assert len(payload) == count*6//8+1
    bit = np.arange(count, dtype='u4')*6
    byte = bit//8
    word = payload[byte].astype('u2') | (payload[byte+1].astype('u2') << 8)
    return ((word >> (bit % 8)) & 63).astype('u1')


def choose_levels(errors, weights, levels):
    best = np.zeros(errors.shape[:-1], dtype='u1')
    cost = np.sum(np.abs(errors)*weights, axis=-1)
    for code, level in enumerate(levels):
        loss = np.sum(np.abs(errors-int(level))*weights, axis=-1)
        take = loss < cost-1e-12*np.maximum(1, cost)
        best[take], cost[take] = code, loss[take]
    return best, cost


def self_check():
    assert len(TRAIN) == len(VALID) == 8 and not set(TRAIN) & set(VALID)
    assert all(x >= 4 and y < 2 for x, y in TRAIN+VALID)
    scalar.self_check()
    c = np.arange(64, dtype='u1')
    payload = np.append(pack6(c), np.uint8(0))
    assert np.array_equal(unpack6(payload, len(c)), c)
    for i, expected in enumerate(c):
        at, shift = divmod(6*i, 8)
        assert ((int(payload[at]) | int(payload[at+1]) << 8) >> shift) & 63 == expected
    e = np.array([[-32, -10, 0], [3, 4, 7], [-2, 2, 0], [100, 80, 60]], dtype='i2')
    levels = np.array([0, 4, -6, 10], dtype='i1')
    code, loss = choose_levels(e, np.array([1., 2., 3.]), levels)
    for row, actual, result in zip(e, code, loss):
        options = [float(np.dot(np.abs(row-int(v)), [1., 2., 3.])) for v in levels]
        assert actual == min(range(4), key=lambda i: (options[i], abs(int(levels[i])), int(levels[i])))
        assert result == options[actual]


def fit(direction):
    begin, cpu = time.monotonic(), time.process_time()
    out = ROOT/f'direction-{direction}'
    out.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, out/'protocol-original.md')
    checked(Q4, read('../exp619/validation/results/exp619/training.json')['asset'])
    checked(prior.GEOMETRY, read('../exp589/validation/results/exp589/candidate-freeze.json')['arms']['D64']['geometry'])
    fields, mapping = read(prior.PREPARATION/'fields.json'), read(prior.PREPARATION/'mapping.json')
    assert [v['number'] for v in fields] == list(range(208))
    assert read(prior.PREPARATION/'label-report.json')['evidence_passed']
    helpers = sorted({Path(inspect.getsourcefile(m)).resolve() for n, m in list(sys.modules.items())
                      if n.startswith('exp') and inspect.getsourcefile(m)})
    inputs = [Path(__file__), out/'protocol-original.md', Q4, prior.GEOMETRY,
              prior.PREPARATION/'fields.json', prior.PREPARATION/'mapping.json',
              prior.PREPARATION/'label-report.json', *helpers]
    write(out/'freeze.json', dict(direction=direction, train=TRAIN, validation=VALID,
        inputs=[identity(p) for p in inputs], frozen_before_fit=True, independent_data=False,
        host=socket.gethostname(), numpy=np.__version__, disk_free_start_bytes=shutil.disk_usage('.').free))
    q4 = scalar.unpack(Q4)
    center, left, right, ls, rs = prior.model()
    xx, yy = np.array(TRAIN+VALID).T
    weights = 1/(128+125*xx+125*yy).astype('f8')
    trend = 125*xx+(125 if direction % 2 else 127)*yy
    col = prior.local(np.arange(PHASES)[:, None]+direction*PHASES, xx[None], yy[None]).ravel()
    rhs, scale = right[col].astype('f8'), rs[col].astype('f8')
    errors = np.empty((PAIRS, PHASES, len(xx)), dtype='i2')
    best = np.empty((PAIRS, PHASES), dtype='i1')
    records = []
    for item in fields:
        s = item['number']
        field = prior.load_field(item, mapping)[direction].reshape(10, 12, 288, 552)
        pairs = np.arange(s*288, (s+1)*288)
        rows = direction*PAIRS+pairs
        v = left[rows].astype('f8') @ rhs.T
        assert np.all(v == np.floor(v))
        v *= ls[rows].astype('f8')[:, None]
        v *= scale[None]
        v = v.reshape(288, PHASES, len(xx))
        v *= (128+125*xx+125*yy)[None, None]
        v += center[pairs, None, None]
        v += trend[None, None]
        nominal = (np.maximum(v, 0)+.5).astype('i4')
        truth = np.take(field, xx*46+yy, axis=-1).transpose(2, 0, 1, 3).reshape(288, PHASES, len(xx)).astype('i4')
        truth += trend[None, None]
        residual = truth-nominal-q4[pairs, direction*PHASES:(direction+1)*PHASES, None]
        assert np.max(np.abs(residual)) <= 32767
        errors[pairs] = residual
        best[pairs], loss = prior.exhaustive(residual[..., :8], weights[:8])
        zero = np.sum(np.abs(residual[..., :8])*weights[:8], axis=-1)
        assert np.all(loss <= zero+1e-12*np.maximum(1, zero))
        records.append(dict(source=s, raw_sha256=item['raw_sha256']))
        if s % 32 == 0:
            print('EXP639_SOURCE', direction, s, round(time.monotonic()-begin, 3), flush=True)
    counts = np.bincount(((best.astype('i2')+32)//2).ravel(), minlength=32)
    write(out/'counts.json', dict(counts=counts.tolist(), all_levels_present=bool(np.all(counts > 0))))
    assert np.all(counts > 0), 'zero count: preserve evidence and stop fixed DP protocol'
    levels, distortion = scalar.optimal(list(range(-32, 31, 2)), counts.tolist(), 4)
    levels = np.array(levels, dtype='i1')
    codes, loss = choose_levels(errors[..., :8], weights[:8], levels)
    selected = levels[codes]
    optimal_loss = np.sum(np.abs(errors[..., :8]-best[..., None])*weights[:8], axis=-1)
    zero = np.sum(np.abs(errors[..., :8])*weights[:8], axis=-1)
    assert np.all(loss <= zero+1e-12*np.maximum(1, zero))
    assert np.all(loss >= optimal_loss-1e-12*np.maximum(1, optimal_loss))
    path = BUILD/f'direction-{direction}.u8'
    with path.open('xb') as stream:
        stream.write(codes.tobytes())
    assert np.array_equal(np.fromfile(path, 'u1').reshape(codes.shape), codes)
    scores = {}
    physical = np.ones((PHASES, len(xx)), dtype=bool)
    if direction % 2:
        physical &= (12*yy[None]+np.arange(PHASES)[:, None] % 12) > 0
    for split, select in (('train', np.arange(len(xx)) < 8), ('validation', np.arange(len(xx)) >= 8)):
        scores[split] = {}
        for scope, valid in (('rectangle', np.ones_like(physical)), ('physical_domain', physical)):
            metrics = {}
            for name, mask in (('all', select), ('qy0', select & (yy == 0)), ('qy1', select & (yy == 1))):
                w = weights[mask]*valid[:, mask]
                e = errors[..., mask].astype('i4')
                baseline = float((np.abs(e)*w).sum())
                full = float((np.abs(e-best[..., None])*w).sum())
                low = float((np.abs(e-selected[..., None])*w).sum())
                metrics[name] = dict(values=PAIRS*int(np.count_nonzero(w)), baseline_l1=baseline,
                    full_l1=full, two_bit_l1=low, reduction=1-low/baseline)
            scores[split][scope] = metrics
    gate = all(scores[split][scope]['all']['reduction'] >= .10
               for split in scores for scope in scores[split])
    gate &= all(scores['validation'][scope][state]['reduction'] >= .05
                for scope in scores['validation'] for state in ('qy0', 'qy1'))
    write(out/'prototype.json', dict(all_checks_passed=True, gate=bool(gate), levels_ps=levels.tolist(),
        quantizer_distortion_ps=distortion, scores=scores, asset=identity(path), sources=records,
        cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-begin,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        disk_free_end_bytes=shutil.disk_usage('.').free))
    print('EXP639_PROTOTYPE', direction, bool(gate), scores['validation']['physical_domain'], flush=True)


def evaluate():
    begin, cpu = time.monotonic(), time.process_time()
    reports = [read(ROOT/f'direction-{d}/prototype.json') for d in range(4)]
    assert all(r['gate'] and r['all_checks_passed'] for r in reports)
    checked(Q4, read('../exp619/validation/results/exp619/training.json')['asset'])
    original = Q4.read_bytes()
    qlevels = np.frombuffer(original, 'i1', count=16, offset=32)
    p4 = np.frombuffer(original, 'u1', offset=64)
    qcodes = np.column_stack((p4 & 15, p4 >> 4)).ravel().reshape(PAIRS, 480)
    codes = qcodes.copy()
    levels = np.array([r['levels_ps'] for r in reports], dtype='i1')
    for d, report in enumerate(reports):
        path = Path(report['asset']['path'])
        checked(path, report['asset'])
        codes[:, d*120:(d+1)*120] |= np.fromfile(path, 'u1').reshape(PAIRS, 120) << 4
    lut = np.empty((4, 2, 64), dtype='i1')
    for d in range(4):
        for h in range(2):
            value = qlevels[np.arange(64) % 16].astype('i2')+h*levels[d, np.arange(64)//16]
            assert value.min() >= -128 and value.max() <= 127
            lut[d, h] = value
    header = b'EX639P01'+struct.pack('<4I', PAIRS, 480, 6, 512)+bytes(8)+qlevels.tobytes()+levels.tobytes()
    assert len(header) == 64
    asset = BUILD/'Q4Y2.p6'
    with asset.open('xb') as out:
        out.write(header); out.write(lut.tobytes()); out.write(pack6(codes).tobytes()); out.write(b'\0')
    raw = asset.read_bytes()
    assert len(raw) == 21566017 and raw[:8] == b'EX639P01'
    payload = np.frombuffer(raw, 'u1', offset=576)
    restored = unpack6(payload, PAIRS*480).reshape(PAIRS, 480)
    assert np.array_equal(restored, codes) and np.array_equal(restored & 15, qcodes)
    assert np.array_equal(np.frombuffer(raw, 'i1', count=512, offset=64).reshape(4, 2, 64), lut)
    for i in [0, 1, 2, 3, PAIRS*480-4, PAIRS*480-3, PAIRS*480-2, PAIRS*480-1]:
        at, shift = divmod(i*6, 8)
        assert ((int(payload[at]) | int(payload[at+1]) << 8) >> shift) & 63 == codes.ravel()[i]
    data_path = Path('../exp623/build/exp623/data.npz')
    keys_path = Path('../exp615/build/exp615/keys.bin')
    raw_path = Path('../exp576/build/exp576/R8.f32')
    checked(data_path, read('../exp623/validation/results/exp623/prepare.json')['data'])
    checked(keys_path, read('../exp615/validation/results/exp615/freeze.json')['keys'])
    checked(raw_path, read('../exp576/validation/results/exp576/R8.json')['raw'])
    write(ROOT/'evaluation-freeze.json', dict(inputs=[identity(p) for p in (Path(__file__), PLAN,
        data_path, keys_path, raw_path, asset)], frozen_before_predictions=True,
        seed=20261023639, bootstrap=9999, independent_requests=False))
    with np.load(data_path) as packed:
        data = {k: packed[k] for k in packed.files}
    pair, context, qx, qy = np.fromfile(keys_path, '<u4', offset=12).reshape(ROWS, 4).T
    h = (qx >= 4) & (qy < 2)
    direction = context//120
    correction = lut[direction, h.astype('u1'), restored[pair, context]].astype('i4')
    correction[qx+qy <= 3] = 0
    old = qlevels[qcodes[pair, context]].astype('i4')
    old[qx+qy <= 3] = 0
    assert np.array_equal(correction[~h], old[~h])
    # The hash-checked exp623 base already includes Q4.
    model = np.fromfile(raw_path, '<f4')
    reference = decode(model, data['base'], data['mandatory'])
    candidate = decode(model, data['base']+correction-old, data['mandatory'])
    assert stats(reference, data['truth']) == read('../exp632/validation/results/exp632/report.json')['metrics']['A']
    assert np.array_equal(reference[~h], candidate[~h])
    partitions = {k: data[k] for k in ('source_family', 'distance', 'near_axis', 'forced')}
    partitions.update(direction=direction, axis_state=np.where(h, qy, 2))
    result = transition(candidate, reference, data['truth'], partitions)
    family = data['source_family']
    counts = np.bincount(family, minlength=26)
    assert len(counts) == 26 and np.all(counts > 0)
    sums = np.bincount(family, weights=points(candidate, data['truth'])-points(reference, data['truth']), minlength=26)
    draws = np.random.default_rng(20261023639).integers(26, size=(9999, 26))
    interval = np.quantile(sums[draws].sum(axis=1)/counts[draws].sum(axis=1), [.025, .975])
    gate = result['delta_accuracy_pp'] >= .02 and interval[0] > 0 and all(
        v['delta_accuracy_pp'] >= -.03 for k in ('distance', 'near_axis', 'direction', 'forced')
        for v in result['groups'][k].values())
    result.update(ci95_acc_pp=interval.tolist(), gate=bool(gate), asset=identity(asset),
        nominal_gates_passed=True, full_code_roundtrip=True, original_q4_codes_preserved=True,
        preserved_rows=int((~h).sum()), changed_rows=int(np.count_nonzero(candidate != reference)),
        selected_domain_rows=int(h.sum()), complete_program_measured=False, independent_requests=False,
        prediction_sha256=hashlib.sha256(candidate.astype('<i4').tobytes()).hexdigest(),
        cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-begin,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        disk_free_end_bytes=shutil.disk_usage('.').free)
    write(ROOT/'evaluation.json', result)
    print('EXP639_EVALUATION', bool(gate), result['delta_accuracy_pp'], interval.tolist(), flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp639')
    assert os.environ['OPENBLAS_NUM_THREADS'] == '4'
    resource.setrlimit(resource.RLIMIT_CPU, (600 if sys.argv[1] == 'fit' else 180,)*2)
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30,)*2)
    self_check()
    if sys.argv[1:] == ['self-check']:
        print('EXP639_SELF_CHECK_OK', flush=True)
    elif sys.argv[1:] == ['evaluate']:
        evaluate()
    else:
        assert len(sys.argv) == 3 and sys.argv[1] == 'fit' and int(sys.argv[2]) in range(4)
        fit(int(sys.argv[2]))
