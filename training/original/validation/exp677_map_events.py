#!/usr/bin/env python3
"""Separate horizontal same-block events from vertical corridor returns."""
import os
from pathlib import Path
import resource
import shutil
import socket
import struct
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp614/validation').resolve()))
import exp614_gemini_features as source
sys.path.insert(0, str(Path('../exp592/validation').resolve()))
from exp592_xgb_audit import decode, points, stats

ROOT = Path('validation/results/exp677')
PLAN = Path('experiment/实验677-横向同带与纵向走廊事件的当前误差诊断.md')
read, write, identity, checked = source.read, source.write, source.identity, source.checked
ROWS, SEED = 1_000_000, 20261024677
NAMES = ('remove_background', 'remove_map_residual', 'remove_line_coupling')
CURVES = Path('../exp654/build/exp654/D64.curves.u8')
Q4 = Path('../exp619/build/exp619/Q4.p4')
KEYS = Path('../exp615/build/exp615/keys.bin')
OLD_RAW = Path('../exp640/build/exp640/S8-raw.f64')


def curve_base(data):
    q4_identity = read('../exp623/validation/results/exp623/prepare.json')['data']
    checked('../exp623/build/exp623/data.npz', q4_identity)
    with np.load('../exp623/build/exp623/data.npz') as packed:
        q4 = {key: packed[key] for key in packed.files}
    for key in ('truth', 'mandatory', 'routes', 'folds'):
        assert np.array_equal(data[key], q4[key]), key
    data['base'] = q4['base']
    asset, scalar = CURVES.read_bytes(), Q4.read_bytes()
    assert asset[:8] == b'EX654C01' and len(asset) == 29_308_992
    assert struct.unpack_from('<6Ii', asset, 8) == (59904, 4, 120, 542, 256, 1, -55)
    assert scalar[:8] == b'EX619P01' and len(scalar) == 14_377_024
    assert struct.unpack_from('<3I', scalar, 8) == (59904, 480, 16)
    pair, context, qx, qy = np.fromfile(KEYS, '<u4', offset=12).reshape(-1, 4).T
    assert len(pair) == ROWS and (pair < 59904).all() and (context < 480).all()
    assert np.array_equal(pair, data['pair'])
    far = qx + qy > 3
    index = pair.astype('i8') * 480 + context
    packed = np.frombuffer(scalar, 'u1', offset=64)
    code = (packed[index // 2] >> (4 * (index % 2))) & 15
    old = np.frombuffer(scalar, 'i1', count=16, offset=32)[code].astype('i4')
    old[~far] = 0
    codes = np.frombuffer(asset, 'u1', count=59904 * 480, offset=64)
    values = np.frombuffer(asset, 'u1', offset=64 + 59904 * 480).reshape(4, 256, 542)
    gx, gy = qx[far].astype('i4'), qy[far].astype('i4')
    before = np.where(gx < 4, (gx + 1) * (8 - gx) // 2, 10)
    position = gx * 46 + gy - before
    assert ((position >= 0) & (position < 542)).all()
    correction = np.zeros(len(pair), 'i4')
    correction[far] = values[context[far] // 120, codes[index[far]], position].astype('i4') - 55
    base = data['base'].astype('i8') - old + correction
    assert np.array_equal(base[~far], data['base'][~far])
    return base


def moments(channels, error):
    assert channels.dtype == error.dtype == np.dtype('i8')
    assert np.array_equal(channels.sum(axis=1), error)
    gram = channels.T @ channels
    assert int(gram.sum()) == int(error @ error)
    return dict(rows=len(error), sums_ps=channels.sum(axis=0).tolist(),
                gram_ps2=gram.tolist(), total_squared_ps2=int(error @ error))


def events(coordinates, blocks):
    ax, ay, tx, ty = coordinates.astype('i4').T
    lowx, highx = np.minimum(ax, tx), np.maximum(ax, tx)
    lowy, highy = np.minimum(ay, ty), np.maximum(ay, ty)
    horizontal = np.zeros(len(ax), dtype=bool)
    bands = np.zeros(len(ax), dtype='i4')
    central = [b for b in blocks if b['horizontal crossable']]
    assert len(central) == 6
    for block in blocks:
        left, right, lower, upper = [block[k] for k in ('left', 'right', 'lower', 'upper')]
        horizontal |= ((lowx < left) & (highx > right) & (lowy >= lower) & (highy <= upper))
    for block in central:
        assert block['left'] == 76 and block['right'] == 89
        assert block['upper']-block['lower']+1 == 50 and not block['vertical crossable']
        bands += (lowy < block['lower']) & (highy > block['upper'])
    ends = ((ax >= 76) & (ax <= 89)).astype('i4') + ((tx >= 76) & (tx <= 89)).astype('i4')
    vertical = (ends == 2) & (bands > 0)
    assert not np.any(horizontal & vertical)
    return horizontal, vertical, bands, ends


def self_check(blocks):
    coordinates = np.array([(75, 120, 90, 130), (80, 75, 80, 175),
        (80, 75, 85, 90), (80, 175, 80, 75), (75, 75, 90, 175),
        (80, 75, 100, 175), (75, 0, 90, 0)])
    h, v, bands, ends = events(coordinates, blocks)
    assert h.tolist() == [True, False, False, False, False, False, True]
    assert v.tolist() == [False, True, False, True, False, False, False]
    assert bands.tolist() == [0, 1, 0, 1, 1, 1, 0]
    assert ends.tolist() == [0, 2, 2, 2, 0, 1, 0]
    backward = events(coordinates[:, [2, 3, 0, 1]], blocks)
    assert all(np.array_equal(a, b) for a, b in zip((h, v, bands, ends), backward))


def main():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp677')
    assert os.environ['OPENBLAS_NUM_THREADS'] == os.environ['OMP_NUM_THREADS'] == '1'
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
    start, cpu = time.monotonic(), time.process_time()
    ROOT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/'protocol-original.md')
    frozen = read('../exp657/validation/results/exp657/freeze.json')
    inputs = []
    for item in frozen['files']:
        path = Path('../exp657')/item['path']
        checked(path, item)
        inputs.append(identity(path))
    arch = Path('../exp652/doc/eda比赛文件/arch')
    original = read('../exp652/validation/results/exp652/build-freeze.json')
    for name in ('SRB_Gap.json', 'SRB_Net.json'):
        item = next(v for v in original['files'] if v['path'].endswith('/'+name))
        checked(arch/name, item)
        inputs.append(identity(arch/name))
    blocks = read(arch/'SRB_Gap.json')['Gap']['Block']
    nets = read(arch/'SRB_Net.json')['Nets']
    assert all(n['delta x'] == 0 or n['delta y'] == 0 for n in nets)
    assert max(abs(n['delta y']) for n in nets) == 12
    self_check(blocks)
    for p in (Path(__file__), PLAN, ROOT/'protocol-original.md', Path('validation/exp677_run.sh'),
              Path('../exp587/validation/exp587_background_adaptation.py'),
              Path('../exp593/validation/exp593_target_support.py'), Path(source.__file__),
              Path('../exp592/validation/exp592_xgb_audit.py'),
              Path('../exp656/validation/exp656_curve_residual.py'),
              Path('../exp657/validation/exp657_curve_error_channels.py'),
              Path('../exp657/validation/results/exp657/freeze.json'),
              Path('../exp623/validation/results/exp623/prepare.json'),
              Path('../exp623/build/exp623/data.npz'), OLD_RAW, CURVES, Q4, KEYS,
              Path('../exp657/validation/results/exp657/report.json'),
              Path('../exp657/validation/results/exp657/groups.json')):
        inputs.append(identity(p))
    write(ROOT/'freeze.json', dict(files=inputs, seed=SEED, rows=ROWS,
        new_exact_rows=0, complete_program_runs=0, training_runs=0,
        disk_free_start_bytes=shutil.disk_usage('.').free))
    data = source.load()
    data['base'] = curve_base(data)
    x = data['features']
    h, v, bands, ends = events(x[:, 28:32], blocks)
    assert np.array_equal(h, x[:, 52])
    pair = data['pair'].astype('i4')
    assert len(pair) == ROWS and len(np.unique(pair)) == 59904
    nominal_report = read('../exp536/validation/results/exp536/report.json')
    nominal_path = Path('../exp536')/nominal_report['predictions']['path']
    checked(nominal_path, nominal_report['predictions'])
    fee, base, d0, truth = [data[k].astype('i8') for k in ('mandatory', 'base', 'd0', 'truth')]
    nominal = np.fromfile(nominal_path, '<i4').reshape(ROWS, 6)[:, 2].astype('i8')-fee
    raw = np.fromfile(OLD_RAW, '<f8')
    prediction = decode(raw, base, fee)
    old = read('../exp657/validation/results/exp657/report.json')
    old_groups = read('../exp657/validation/results/exp657/groups.json')
    assert stats(prediction, truth) == old['metrics']['A']
    channels = np.column_stack((base-nominal, prediction-base-fee-(d0-nominal), d0+fee-truth))
    full = moments(channels, prediction-truth)
    assert full == old['moments']
    repairs = np.maximum(0, prediction[:, None]-channels)
    scores = points(prediction, truth)
    deltas = np.column_stack([points(repairs[:, i], truth)-scores for i in range(3)])
    for i, name in enumerate(NAMES):
        assert abs(deltas[:, i].mean()-old['repairs'][name]['delta_pp']) < 1e-10
    family = x[:, 0].astype('i4')
    nx, ny = (x[:, 8]+x[:, 6]).astype('i4'), (x[:, 9]+x[:, 7]).astype('i4')
    partitions = dict(event=h.astype('i4')+2*v, horizontal=h.astype('i4'), vertical=v.astype('i4'),
        central_ends=ends, blocking_bands=bands, source_family=family,
        direction=2*(nx < 0)+(ny < 0),
        cross=((np.minimum(x[:, 28], x[:, 30]) < 76) &
               (np.maximum(x[:, 28], x[:, 30]) > 89)).astype('i4'))
    groups = {}
    for key, values in partitions.items():
        records = {}
        for value in np.unique(values):
            mask = values == value
            row = moments(channels[mask], (prediction-truth)[mask])
            row.update(accuracy_pp=float(scores[mask].mean()), channel_mae_ps=np.abs(channels[mask]).mean(axis=0).tolist(),
                port_pairs=len(np.unique(pair[mask])), source_ports=len(np.unique(pair[mask]//288)),
                target_ports=len(np.unique(pair[mask]%288)),
                repair_delta_pp=deltas[mask].mean(axis=0).tolist(),
                repair_contribution_pp=(deltas[mask].sum(axis=0)/ROWS).tolist(),
                better_rows=np.sum(np.abs(repairs[mask]-truth[mask, None]) <
                                   np.abs(prediction[mask]-truth[mask])[:, None], axis=0).tolist(),
                worse_rows=np.sum(np.abs(repairs[mask]-truth[mask, None]) >
                                  np.abs(prediction[mask]-truth[mask])[:, None], axis=0).tolist())
            records[str(int(value))] = row
        for name in ('rows', 'sums_ps', 'gram_ps2', 'total_squared_ps2'):
            assert np.array_equal(sum(np.asarray(r[name], dtype='i8') for r in records.values()),
                                  np.asarray(full[name], dtype='i8'))
        assert np.allclose(sum(np.asarray(r['repair_contribution_pp']) for r in records.values()),
                           deltas.mean(axis=0), atol=1e-10, rtol=0)
        groups[key] = records
    for value in ('0', '1'):
        current, reference = groups['horizontal'][value], old_groups['forced'][value]
        for key in ('rows', 'sums_ps', 'gram_ps2', 'total_squared_ps2'):
            assert current[key] == reference[key]
        assert abs(current['accuracy_pp']-reference['accuracy_pp']) < 1e-10
        assert np.allclose(current['repair_contribution_pp'], reference['repair_contribution_pp'][:3],
                           atol=1e-10, rtol=0)
    draws = np.random.default_rng(SEED).integers(26, size=(9999, 26))
    counts = np.bincount(family, minlength=26)
    priorities = {}
    for name, mask in (('H', h), ('V', v)):
        change = deltas[:, 1]*mask
        totals = np.bincount(family, weights=change, minlength=26)
        sampled = totals[draws].sum(axis=1)/counts[draws].sum(axis=1)
        interval = np.quantile(sampled, [.0125, .9875]).tolist()
        point = float(change.mean())
        priorities[name] = dict(rows=int(mask.sum()), global_delta_accuracy_pp=point,
            simultaneous_ci95_pp=interval, priority=bool(point >= .02 and interval[0] > 0))
    write(ROOT/'groups.json', groups)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_s, wall_s, rss = time.process_time()-cpu, time.monotonic()-start, usage.ru_maxrss*1024
    resource_gate = cpu_s <= 90 and wall_s <= 180 and rss <= 2_000_000_000
    write(ROOT/'report.json', dict(all_checks_passed=True, self_check_passed=True,
        historical_statistics_replayed=True, full_partitions_verified=True,
        horizontal_equals_feature52=True, horizontal_vertical_disjoint=True,
        priorities=priorities, metrics=old['metrics']['A'], complete_program_runs=0,
        new_exact_rows=0, training_runs=0, independent_requests=False,
        cpu_s=cpu_s, wall_s=wall_s, rss_bytes=rss, resource_gate=resource_gate,
        released_bytes=0, disk_free_end_bytes=shutil.disk_usage('.').free))
    assert resource_gate and sum(p.stat().st_size for p in ROOT.iterdir()) < 10_000_000
    print('EXP677_COMPLETE', priorities, flush=True)


if __name__ == '__main__':
    main()
