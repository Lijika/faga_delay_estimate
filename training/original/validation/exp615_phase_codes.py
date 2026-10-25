#!/usr/bin/env python3
"""Fit bounded phase residuals of frozen D64, using certified nominal fields."""
import inspect
from pathlib import Path
import resource
import shutil
import socket
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp614/validation').resolve()))
import exp614_gemini_features as prior
from exp504_tail_rectangles import load_field

read, write, identity = prior.read, prior.write, prior.identity
ROOT, BUILD = Path('validation/results/exp615'), Path('build/exp615')
PLAN = Path('experiment/实验615-冻结方向背景的周期残量码.md')
GEOMETRY = Path('../exp589/build/exp589/D64-geometry.bin')
PREPARATION = Path('../exp500/validation/results/exp500-preparation')
QX, QY = np.array([1, 3, 7, 11]), np.array([3, 11, 23, 44])
ROWS, PAIRS = 1000000, 59904


def checked(path, frozen):
    actual = identity(path)
    assert all(actual[k] == frozen[k] for k in ('bytes', 'sha256')), str(path)
    return actual


def model():
    raw = GEOMETRY.read_bytes()
    assert raw[:8] == b'EX589Q01'
    assert struct.unpack('<6I', raw[8:32]) == (512, 64, 64, 64, 4800, 260160)
    center = np.frombuffer(raw, '<i2', count=PAIRS, offset=64)
    at = 119872 + (PAIRS + 4800) * (512 + 4 * 8)
    arrays = []
    for dtype, shape in [('i1', (4 * PAIRS, 64)), ('i1', (260160, 64)),
                         ('<f4', (4 * PAIRS,)), ('<f4', (260160,))]:
        value = np.frombuffer(raw, dtype, count=int(np.prod(shape)), offset=at).reshape(shape)
        arrays.append(value)
        at += value.nbytes
    assert at == len(raw)
    return center, *arrays


def local(context, qx, qy):
    before = np.where(qx < 4, (qx + 1) * (8 - qx) // 2, 10)
    return context * 542 + qx * 46 + qy - before


def choose(errors, weights):
    weights = np.broadcast_to(weights, errors.shape)
    order = np.argsort(errors, axis=-1, kind='stable')
    sorted_weights = np.take_along_axis(weights, order, axis=-1)
    middle = np.argmax(np.cumsum(sorted_weights, axis=-1) >=
                       .5 * np.sum(weights, axis=-1, keepdims=True), axis=-1)
    median = np.take_along_axis(np.take_along_axis(errors, order, axis=-1),
                               middle[..., None], axis=-1)[..., 0]
    choices = [np.zeros_like(median),
               np.clip(np.floor_divide(median, 2), -16, 15) * 2,
               np.clip(-np.floor_divide(-median, 2), -16, 15) * 2]
    best = np.zeros_like(median)
    initial = np.sum(weights * np.abs(errors), axis=-1)
    cost = initial.copy()
    for candidate in choices[1:]:
        loss = np.sum(weights * np.abs(errors - candidate[..., None]), axis=-1)
        tolerance = 1e-12 * np.maximum(1., cost)
        tie = np.abs(loss - cost) <= tolerance
        take = (loss < cost - tolerance) | (
            tie & ((np.abs(candidate) < np.abs(best)) |
                   ((np.abs(candidate) == np.abs(best)) & (candidate < best))))
        best = np.where(take, candidate, best)
        cost = np.where(take, loss, cost)
    assert np.all(cost <= initial + 1e-12 * np.maximum(1., initial))
    return best.astype('i1'), initial, cost


def exhaustive(errors, weights):
    best = np.zeros(errors.shape[:-1], dtype='i1')
    cost = np.sum(weights * np.abs(errors), axis=-1)
    for c in sorted(range(-32, 31, 2), key=lambda x: (abs(x), x)):
        loss = np.sum(weights * np.abs(errors - c), axis=-1)
        take = loss < cost - 1e-12 * np.maximum(1., cost)
        best, cost = np.where(take, c, best), np.where(take, loss, cost)
    return best, cost


def self_check():
    values = np.array([[0, 0, 0, 0], [-3, -3, -3, -3], [3, 3, 3, 3],
                       [-100, -80, -40, -35], [31, 50, 70, 100],
                       [-2, -2, 2, 2], [-3, -1, 4, 9]])
    for weights in (np.ones(4), np.array([1., 2., 4., 8.])):
        actual, _, loss = choose(values, weights)
        expected, direct_loss = exhaustive(values, weights)
        assert np.array_equal(actual, expected)
        assert np.allclose(loss, direct_loss, rtol=0, atol=1e-12)
    assert choose(values, np.ones(4))[0].tolist() == [0, -2, 2, -32, 30, 0, 0]


def unpack(path, count):
    raw = path.read_bytes()
    assert raw[:8] in (b'EX615B01', b'EX615P01')
    pairs, contexts = struct.unpack('<II', raw[8:16])
    assert pairs == PAIRS and pairs * contexts == count
    assert len(raw) == 16 + count * 5 // 8 + 1
    bits = np.unpackbits(np.frombuffer(raw, 'u1', offset=16), bitorder='little')[:count * 5]
    code = np.sum(bits.reshape(-1, 5) * (1 << np.arange(5)), axis=1).astype('i2')
    return (2 * (code - 16)).astype('i1').reshape(pairs, contexts)


def pack(name, value):
    assert value.dtype == np.dtype('i1') and np.all(value % 2 == 0)
    assert value.min() >= -32 and value.max() <= 30
    code = (value.reshape(-1).astype('i2') // 2 + 16).astype('u1')
    bits = ((code[:, None] >> np.arange(5)) & 1).astype('u1').reshape(-1)
    path = BUILD / (name + '.p5')
    with path.open('xb') as stream:
        stream.write(('EX615' + name + '01').encode())
        stream.write(struct.pack('<II', *value.shape))
        stream.write(np.packbits(bits, bitorder='little').tobytes() + b'\0')
    assert np.array_equal(unpack(path, value.size), value)
    return identity(path)


def prepare():
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    (ROOT / 'installed-numpy-help.txt').write_text(
        str(np.__version__) + '\n' + np.packbits.__doc__ + '\n' +
        np.unpackbits.__doc__ + '\n' + str(inspect.signature(np.argsort)) + '\n' +
        np.argsort.__doc__)
    help_run = subprocess.run(['g++', '--help'], capture_output=True, text=True, check=True)
    (ROOT / 'compiler-help.txt').write_text(help_run.stdout)
    self_check()
    frozen = read('../exp589/validation/results/exp589/candidate-freeze.json')['arms']['D64']
    checked(GEOMETRY, frozen['geometry'])
    data = prior.load()
    dx = (data['features'][:, 8] + data['features'][:, 6]).astype('i4')
    dy = (data['features'][:, 9] + data['features'][:, 7]).astype('i4')
    direction = 2 * (dx < 0) + (dy < 0)
    qx, qy = np.abs(dx) // 10, np.abs(dy) // 12
    context = (direction * 10 + np.abs(dx) % 10) * 12 + np.abs(dy) % 12
    keys = np.column_stack((data['pair'], context, qx, qy)).astype('<u4')
    old_keys = np.fromfile('../exp575/build/exp575/keys.i32', '<i4').reshape(ROWS, 2)
    assert np.array_equal(keys[:, 0], old_keys[:, 0])
    assert np.array_equal(context * 552 + qx * 46 + qy, old_keys[:, 1])
    assert np.unique(keys[:, 0]).size == PAIRS
    center, left, right, ls, rs = model()
    far = np.flatnonzero(qx + qy > 3)
    for start in range(0, len(far), 8192):
        ids = far[start:start + 8192]
        row = direction[ids] * PAIRS + data['pair'][ids]
        col = local(context[ids], qx[ids], qy[ids])
        product = np.sum(left[row].astype('i4') * right[col].astype('i4'), axis=1, dtype='i4')
        value = product.astype('f8') * ls[row].astype('f8') * rs[col].astype('f8')
        value *= 128 + 125 * qx[ids] + 125 * qy[ids]
        value += center[data['pair'][ids]]
        value += 125 * qx[ids]
        value += np.where(direction[ids] % 2, 125, 127) * qy[ids]
        restored = (np.maximum(value, 0) + .5).astype('i4') + data['features'][ids, 50].astype('i4')
        assert np.array_equal(restored, data['D64'][ids])
    with (BUILD / 'keys.bin').open('xb') as stream:
        stream.write(b'EX615K01' + struct.pack('<I', ROWS) + keys.tobytes())
    labels = read(PREPARATION / 'label-report.json')
    assert labels['evidence_passed'] and labels['certified_values'] == PAIRS * 264960
    paths = [Path(__file__), Path('tests/exp615_phase_codes.cpp'), ROOT / 'protocol-original.md',
             GEOMETRY, PREPARATION / 'mapping.json', PREPARATION / 'fields.json',
             PREPARATION / 'label-report.json', Path('validation/exp504_tail_rectangles.py'),
             Path('validation/exp208_nominal_parent_tree.py')]
    write(ROOT / 'freeze.json', dict(files=[identity(p) for p in paths],
          rows=ROWS, port_pairs=PAIRS, training_grid_qx=QX.tolist(), training_grid_qy=QY.tolist(),
          far_reconstructed_rows=len(far), bitwise_base_reconstruction=True,
          keys=identity(BUILD / 'keys.bin'), d64_geometry=frozen['geometry'],
          data=read('../exp614/validation/results/exp614/prepare.json'),
          disk_free_start=shutil.disk_usage('.').free, hostname=socket.gethostname(),
          numpy=np.__version__, synthetic_self_check=True))
    print('EXP615_PREPARED', len(far), flush=True)


def train():
    started, cpu = time.monotonic(), time.process_time()
    frozen = read(ROOT / 'freeze.json')
    for item in frozen['files']:
        checked(item['path'], item)
    mapping = read(PREPARATION / 'mapping.json')
    fields = read(PREPARATION / 'fields.json')
    assert [r['number'] for r in fields] == list(range(208))
    assert len(set(mapping['sources'])) == 208 and len(set(mapping['targets'])) == 288
    center, left, right, ls, rs = model()
    xx, yy = np.meshgrid(QX, QY, indexing='ij')
    qx, qy = xx.reshape(-1), yy.reshape(-1)
    assert np.all(qx + qy > 3)
    denom = 128 + 125 * qx + 125 * qy
    weights = 1 / denom.astype('f8')
    codes = {'B': np.empty((PAIRS, 4), dtype='i1'),
             'P': np.empty((PAIRS, 480), dtype='i1')}
    contexts = np.arange(120)[:, None]
    right_blocks = []
    for d in range(4):
        col = local(contexts + 120 * d, qx[None], qy[None]).reshape(-1)
        right_blocks.append((right[col].astype('f8'), rs[col].astype('f8')))
    records = []
    for item in fields:
        number = item['number']
        field = load_field(item, mapping)
        pair = np.arange(number * 288, (number + 1) * 288)
        losses, audited = {}, 0
        for d, (rb, scale) in enumerate(right_blocks):
            row = d * PAIRS + pair
            value = left[row].astype('f8') @ rb.T
            assert np.all(value == np.floor(value))
            value *= ls[row].astype('f8')[:, None]
            value *= scale[None]
            value = value.reshape(288, 120, 16)
            value *= denom[None, None]
            value += center[pair, None, None]
            trend = 125 * qx + (125 if d % 2 else 127) * qy
            value += trend[None, None]
            nominal = (np.maximum(value, 0) + .5).astype('i4')
            # Index after selecting direction to retain the declared field axes.
            truth = field[d][..., QX[:, None], QY[None, :]]
            assert truth.shape == (10, 12, 288, 4, 4)
            truth = truth.transpose(2, 0, 1, 3, 4).reshape(288, 120, 16).astype('i4')
            residual = truth + trend[None, None] - nominal
            cb, initial_b, loss_b = choose(residual.reshape(288, -1), np.tile(weights, 120))
            cp, initial_p, loss_p = choose(residual, weights)
            assert abs(float(initial_b.sum() - initial_p.sum())) <= 1e-9
            assert np.all(nominal + cp[..., None] >= 0)
            assert np.all(nominal + cb[:, None, None] >= 0)
            codes['B'][pair, d] = cb
            codes['P'][pair, d * 120:(d + 1) * 120] = cp
            if number == 0 and d == 0:
                for e, w, got in ((residual.reshape(288, -1)[:10], np.tile(weights, 120), cb[:10]),
                                  (residual.reshape(-1, 16)[:10], weights, cp.reshape(-1)[:10])):
                    direct, _ = exhaustive(e, w)
                    assert np.array_equal(direct, got)
                    audited += 10
            losses[str(d)] = dict(zero=float(initial_p.sum()), B=float(loss_b.sum()),
                                  P=float(loss_p.sum()), residual_min=int(residual.min()),
                                  residual_max=int(residual.max()))
        record = dict(source=number, field_sha256=item['asset']['sha256'], raw_sha256=item['raw_sha256'],
                      losses=losses, exhaustive_units=audited)
        write(ROOT / f'source-{number:03d}.json', record)
        records.append(record)
        if number % 8 == 0:
            print('EXP615_SOURCE', number, time.monotonic() - started, flush=True)
    assets = {}
    for name, code in codes.items():
        assets[name] = pack(name, code)
    totals = {key: sum(r['losses'][str(d)][key] for r in records for d in range(4))
              for key in ('zero', 'B', 'P')}
    write(ROOT / 'training.json', dict(complete=True, sources=208, targets=288, port_pairs=PAIRS,
          nominal_training_points=PAIRS * 480 * 16, assets=assets, training_l1=totals,
          counts={name: dict(nonzero=int(np.count_nonzero(c)),
                            saturated=int(np.count_nonzero((c == -32) | (c == 30))),
                            minimum=int(c.min()), maximum=int(c.max())) for name, c in codes.items()},
          full_pack_roundtrip=True, exhaustive_units=20, freeze=identity(ROOT / 'freeze.json'),
          driver=identity(__file__), cpu_s=time.process_time() - cpu, wall_s=time.monotonic() - started,
          rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
          disk_free_end=shutil.disk_usage('.').free, complete_program_verified=False))
    print('EXP615_TRAINED', totals, flush=True)


def evaluate():
    sys.path.insert(0, str(Path('../exp592/validation').resolve()))
    from exp592_xgb_audit import decode, points, transition
    frozen, trained = read(ROOT / 'freeze.json'), read(ROOT / 'training.json')
    data = prior.load()
    checked(BUILD / 'keys.bin', frozen['keys'])
    keys = np.fromfile(BUILD / 'keys.bin', '<u4', offset=12).reshape(ROWS, 4)
    pair, context, qx, qy = keys.T
    far = qx + qy > 3
    raw_path = '../exp576/build/exp576/R8.f32'
    checked(raw_path, frozen['data']['original_raw'])
    raw = np.fromfile(raw_path, '<f4')
    reference = decode(raw, data['D64'], data['mandatory'])
    command = ['g++', '-std=c++17', '-O3', '-static', '-s', '-march=x86-64', '-mtune=generic',
               '-Wall', '-Wextra', '-Werror', 'tests/exp615_phase_codes.cpp',
               '-o', str(BUILD / 'decode')]
    compile_run = subprocess.run(command, capture_output=True, text=True)
    (ROOT / 'compile.stdout').write_text(compile_run.stdout)
    (ROOT / 'compile.stderr').write_text(compile_run.stderr)
    assert compile_run.returncode == 0 and not compile_run.stderr, compile_run.stderr
    command = [str(BUILD / 'decode'), str(BUILD / 'B.p5'), str(BUILD / 'P.p5'),
               str(BUILD / 'keys.bin'), str(BUILD / 'B-query.i32'), str(BUILD / 'P-query.i32')]
    run = subprocess.run(command, capture_output=True, text=True)
    (ROOT / 'decode.stdout').write_text(run.stdout)
    (ROOT / 'decode.stderr').write_text(run.stderr)
    assert run.returncode == 0 and not run.stderr, run.stderr
    counters = read(ROOT / 'decode.stdout')
    assert counters['rows'] == ROWS and counters['port_pairs'] == PAIRS
    with np.load('../exp585/build/exp585/evaluation.npz') as packed:
        partitions = {k[10:]: packed[k] for k in packed.files if k.startswith('partition_')}
    x = data['features']
    nx, ny = x[:, 8] + x[:, 6], x[:, 9] + x[:, 7]
    partitions.update(source_family=x[:, 0].astype('i4'), forced=x[:, 52].astype('i4'),
        near_axis=((np.abs(nx) < 20) | (np.abs(ny) < 24)).astype('i4'),
        code_training_grid=(np.isin(qx, QX) & np.isin(qy, QY)).astype('i4'))
    family, inverse = np.unique(x[:, 0].astype('i4'), return_inverse=True)
    assert len(family) == 26
    counts = np.bincount(inverse)
    sampled = np.random.default_rng(20261022615).integers(26, size=(9999, 26))
    denominator = counts[sampled].sum(axis=1)
    results, eligible = {}, []
    for name, contexts in (('B', 4), ('P', 480)):
        checked(BUILD / (name + '.p5'), trained['assets'][name])
        table = unpack(BUILD / (name + '.p5'), PAIRS * contexts)
        correction = table[pair, context // 120 if name == 'B' else context].astype('i4')
        correction[~far] = 0
        assert np.array_equal(correction, np.fromfile(BUILD / (name + '-query.i32'), '<i4'))
        prediction = decode(raw, data['D64'] + correction, data['mandatory'])
        assert np.array_equal(prediction[~far], reference[~far])
        result = transition(prediction, reference, data['truth'], partitions)
        delta = points(prediction, data['truth']) - points(reference, data['truth'])
        diffs = np.bincount(inverse, weights=delta)
        result['simultaneous_ci_delta_pp'] = np.quantile(
            diffs[sampled].sum(axis=1) / denominator, [.0125, .9875]).tolist()
        result['changed_rows'] = int(np.count_nonzero(prediction != reference))
        result['quality_gate'] = bool(result['delta_accuracy_pp'] >= .02
            and result['simultaneous_ci_delta_pp'][0] > 0
            and all(g['delta_accuracy_pp'] >= -.03 for key, group in result['groups'].items()
                    if key in ('distance', 'near_axis') for g in group.values()))
        output = BUILD / (name + '-prediction.i32')
        prediction.astype('<i4').tofile(output)
        result.update(prediction=identity(output), code_table=trained['assets'][name],
                      scalar_lookup_equal=True, near_output_bitwise_unchanged=True,
                      complete_program_verified=False)
        write(ROOT / (name + '-report.json'), result)
        results[name] = result
        if result['quality_gate']:
            eligible.append(name)
        print('EXP615_EVALUATED', name, result['candidate']['accuracy_pp'],
              result['delta_accuracy_pp'], result['quality_gate'], flush=True)
    selected = None
    if eligible:
        best = max(results[a]['candidate']['accuracy_pp'] for a in eligible)
        selected = next(a for a in ('B', 'P') if a in eligible
                        and best - results[a]['candidate']['accuracy_pp'] <= .005)
    write(ROOT / 'evaluation.json', dict(results=results, selected=selected, eligible=eligible,
          rows=ROWS, port_pairs=PAIRS, query_lookup_counters=counters,
          training=identity(ROOT / 'training.json'), complete_program_verified=False))
    print('EXP615_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp615')
    resource.setrlimit(resource.RLIMIT_CPU, (7200, 7200))
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert sys.argv[1:] in (['prepare'], ['train'], ['evaluate'])
    {'prepare': prepare, 'train': train, 'evaluate': evaluate}[sys.argv[1]]()
