#!/usr/bin/env python3
"""Measure fixed-rank row/block INT8 geometry on complete full-port requests."""
import json
import math
from pathlib import Path
import re
import shutil
import socket
import statistics
import struct
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path('../exp579/validation').resolve()))
sys.path.insert(0, str(Path('../exp580/validation').resolve()))
import exp579_complete_candidate as complete
import exp580_complete_speed as speed
from exp208_nominal_parent_tree import identity, write

ROOT, BUILD = Path('validation/results/exp582'), Path('build/exp582')
PLAN = Path('experiment/实验582-背景因子的行块INT8量化.md')
ARMS = {'R': 0, 'B64': 64, 'B32': 32}
FACTOR = Path('../exp575/offline/build/exp575')
speed.ROOT = ROOT
read, real = complete.read, complete.real


def quantize(values, diagonal, block):
    balanced = np.asarray(values, dtype=np.float64) * diagonal
    rows, rank = values.shape
    blocks = (rank + block - 1) // block
    q, scales = np.empty(values.shape, dtype='i1'), np.empty((rows, blocks), dtype='<f4')
    maximum_error = 0.
    for group in range(blocks):
        sl = slice(group * block, min((group + 1) * block, rank))
        v = balanced[:, sl]
        scale = (np.max(np.abs(v), axis=1) / 127).astype('<f4')
        scale[scale == 0] = 1
        assert np.isfinite(v).all() and np.isfinite(scale).all() and (scale > 0).all()
        integer = np.rint(v / scale[:, None])
        assert np.max(np.abs(integer)) <= 127
        q[:, sl], scales[:, group] = integer, scale
        error = np.abs(integer * scale[:, None] - v)
        assert np.all(error <= .500001 * scale[:, None])
        maximum_error = max(maximum_error, float(error.max()))
    return q, scales, dict(rows=rows, rank=rank, block=block, blocks=blocks,
                          max_abs_reconstruction_error=maximum_error)


def prepare():
    ROOT.mkdir(parents=True)
    BUILD.mkdir(parents=True)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    baseline = Path('../exp581/build/exp581/G')
    assert identity(baseline)['sha256'] == '6350c045e59b2e2ee696a1ad1696a098617c13f5d4a4b88c88755bde71c58491'
    assets, quantized = [], {}
    for g, rank in ((0, 192), (1, 96)):
        paths = [FACTOR / f'group-{g}-r{rank}-{side}.npy' for side in ('left', 'right')]
        left, right = [np.load(p, mmap_mode='r') for p in paths]
        assert left.shape == (59904, rank) and right.shape == ((4800 if g == 0 else 260160), rank)
        lm, rm = np.max(np.abs(left), axis=0).astype('f8'), np.max(np.abs(right), axis=0).astype('f8')
        d = np.ones(rank)
        active = (lm > 0) & (rm > 0)
        d[active] = np.sqrt(rm[active] / lm[active])
        assert np.isfinite(d).all() and (d > 0).all()
        assets += [identity(p) for p in paths]
        for name, limit in ARMS.items():
            block = min(limit, rank) if limit else rank
            lq, ls, ld = quantize(left, d, block)
            rq, rs, rd = quantize(right, 1 / d, block)
            quantized[g, name] = (lq, rq, ls, rs)
            write(ROOT / f'{name}-{g}-quantization.json', dict(left=ld, right=rd, diagonal=d.tolist()))
    original = Path('../exp579/build/exp579/geometry.bin')
    with original.open('rb') as f:
        assert f.read(8) == b'EX575Q01'
        f.seek(64)
        center = f.read(59904 * 2)
    source = Path('../exp581/build/exp581/candidate.cpp').read_text()
    first, last = source.index('struct Part {'), source.index('static delayest::Architecture arch;')
    source = source[:first] + '#include "exp582_int8_geometry.h"\n' + source[last:]
    first = source.index('    const auto* at = exp579_geometry + 64;')
    last = source.index('\n}', first)
    source = source[:first] + '    initializeGeometry582();' + source[last:]
    first = source.index('static inline double geometry(')
    last = source.index('template <typename T>\nstatic inline float residual', first)
    source = source[:first] + source[last:]
    (BUILD / 'candidate.cpp').write_text(source)
    model = Path('../exp579/build/exp579/exp579-models.h').read_text()
    common = ['g++', '-std=c++17', '-O3', '-fno-exceptions', '-fno-rtti', '-fno-fast-math',
              '-ffp-contract=off', '-march=x86-64', '-mtune=generic', '-Wall', '-Wextra', '-Werror',
              '-DDELAY_ESTIMATE_EMBEDDED_ARCH', '-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE',
              '-DEXP580_PORT_PARSER', '-DEXP581_PREFETCH', '-I', 'src', '-I', 'tests', '-I', str(BUILD)]
    records = {}
    for name, limit in ARMS.items():
        path = BUILD / (name + '-geometry.bin')
        with path.open('xb') as f:
            f.write(b'EX582Q01' + struct.pack('<6I', 192, 96, limit or 192, limit or 96, 4800, 260160) + bytes(32))
            f.write(center)
            for g in range(2):
                for a in quantized[g, name]:
                    f.write(a.tobytes(order='C'))
        local = BUILD / (name + '-assets')
        local.mkdir()
        header, changes = re.subn(r'constexpr uint64_t kGeometryBytes=\d+;',
                                  f'constexpr uint64_t kGeometryBytes={path.stat().st_size};', model)
        assert changes == 1
        (local / 'exp579-models.h').write_text(header)
        assembly = '.section .rodata.exp579,"a",@progbits\n.balign 64\n.global exp579_geometry\nexp579_geometry:\n.incbin "' + str(path.resolve()) + '"\n.section .note.GNU-stack,"",@progbits\n'
        (local / 'geometry.S').write_text(assembly)
        speed.measured(['g++', '-c', str(local / 'geometry.S'), '-o', str(local / 'geometry.o')], 'asset-' + name)
        for audit in (False, True):
            tag = name + ('-audit' if audit else '')
            flags = [f'-DEXP582_BLOCK={limit}', '-I', str(local)] + (['-DEXP579_AUDIT'] if audit else [])
            command = common + flags + [str(BUILD / 'candidate.cpp'),
                '../exp580/build/exp580/architecture-resolver.o', '../exp579/build/exp579/arch-text.o',
                str(local / 'geometry.o'), '-static', '-s', '-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc',
                '-o', str(BUILD / tag)]
            speed.measured(command, 'compile-' + tag)
            assert not (ROOT / ('compile-' + tag + '.stderr')).read_bytes()
            assert (BUILD / tag).stat().st_size < 100000000
        deps = subprocess.run(['ldd', str(BUILD / name)], text=True, capture_output=True)
        assert 'not a dynamic executable' in deps.stdout + deps.stderr
        records[name] = dict(binary=identity(BUILD / name), geometry=identity(path), block=limit)
    # All original column keys must map bijectively into the two local spaces.
    keys = np.arange(264960, dtype=np.int32)
    qx, qy, context = (keys % 552) // 46, keys % 46, keys // 552
    for g in range(2):
        mask = (qx + qy > 3) == bool(g)
        local = context * 10 + qx * (9 - qx) // 2 + qy if g == 0 else \
            context * 542 + qx * 46 + qy - np.where(qx < 4, (qx + 1) * (8 - qx) // 2, 10)
        assert np.array_equal(local[mask], np.arange(mask.sum()))
    write(ROOT / 'freeze.json', dict(arms=records, baseline=identity(baseline), factors=assets,
        original_geometry=identity(original), driver=identity(__file__), header=identity('tests/exp582_int8_geometry.h'),
        source=identity(BUILD / 'candidate.cpp'), protocol=identity(ROOT / 'protocol-original.md'),
        hostname=socket.gethostname(), compiler=subprocess.check_output(['g++', '--version'], text=True)))
    print('EXP582_PREPARED', flush=True)


def audit():
    keys = np.fromfile('../exp575/build/exp575/keys.i32', '<i4').reshape(1000000, 2)
    pair, column = keys.T
    qx, qy, context = (column % 552) // 46, column % 46, column // 552
    dtype = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
        formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f4'], offsets=[0,216,224,228,232,236], itemsize=240))
    old = np.memmap('../exp579/build/exp579/final-trace.bin', dtype=dtype, mode='r', shape=(1000000,))
    center = np.fromfile('../exp579/build/exp579/geometry.bin', '<i2', count=59904, offset=64)
    records = {}
    for name, limit in ARMS.items():
        output = BUILD / (name + '-trace.bin')
        record = speed.measured([str(BUILD / (name + '-audit')), '../exp579/build/exp579/queries.bin',
            '../exp579/build/exp579/folds.u8', str(output), '1'], 'audit-' + name)
        trace = np.memmap(output, dtype=dtype, mode='r', shape=(1000000,))
        assert np.array_equal(trace['features'].view('u4'), old['features'].view('u4'))
        assert np.array_equal(trace['raw'].view('u4'), old['raw'].view('u4'))
        reference = np.zeros(1000000, dtype='f8')
        at = 64 + 59904 * 2
        for g, rank, count in ((0,192,4800),(1,96,260160)):
            block = min(limit, rank) if limit else rank
            blocks = (rank + block - 1) // block
            arrays = []
            for dt, shape in [('i1',(59904,rank)), ('i1',(count,rank)), ('<f4',(59904,blocks)), ('<f4',(count,blocks))]:
                a = np.memmap(BUILD / (name + '-geometry.bin'), dtype=dt, mode='r', offset=at, shape=shape)
                at += a.nbytes
                arrays.append(a)
            left, right, ls, rs = arrays
            indices = np.flatnonzero((qx + qy > 3) == bool(g))
            local = context * 10 + qx * (9 - qx) // 2 + qy if g == 0 else \
                context * 542 + qx * 46 + qy - np.where(qx < 4, (qx + 1) * (8 - qx) // 2, 10)
            for start in range(0, len(indices), 16384):
                ids = indices[start:start+16384]
                for k in range(blocks):
                    sl = slice(k * block, min((k + 1) * block, rank))
                    product = np.sum(left[pair[ids], sl].astype('i4') * right[local[ids], sl].astype('i4'), axis=1, dtype='i4')
                    reference[ids] += product.astype('f8') * ls[pair[ids], k].astype('f8') * rs[local[ids], k].astype('f8')
        assert at == (BUILD / (name + '-geometry.bin')).stat().st_size
        assert np.array_equal(reference.view('u8'), trace['response'].view('u8')), name
        value = reference * (128 + 125*qx + 125*qy) + center[pair] + 125*qx + np.where(context//120 % 2, 125, 127)*qy
        nominal = (np.maximum(value, 0) + .5).astype('i4')
        # The unchanged source applies exact self-cycle values after the background calculation.
        original_response = old['response']
        original_value = original_response * (128+125*qx+125*qy) + center[pair] + 125*qx + np.where(context//120 % 2,125,127)*qy
        original_nominal = (np.maximum(original_value, 0)+.5).astype('i4')
        fee = old['features'][:,50].astype('i4')
        base = nominal + fee
        override = old['base'] != original_nominal + fee
        base[override] = old['base'][override]
        assert np.array_equal(base, trace['base'])
        prediction = (np.maximum(base + old['raw'].astype('f8'), 0)+.5).astype('i4') + old['mandatory']
        assert np.array_equal(prediction, trace['prediction'])
        prediction.astype('<i4').tofile(BUILD / (name + '-expected.i32'))
        records[name] = dict(run=record, trace=identity(output), bitwise_response=True,
            bitwise_residual=True, exact_integer_output=True, expected=identity(BUILD / (name + '-expected.i32')))
        print('EXP582_AUDIT', name, flush=True)
    write(ROOT / 'audit.json', records)


def paired(prediction, baseline, truth, partitions):
    delta = real.points(prediction, truth) - real.points(baseline, truth)
    counts = np.bincount(partitions['source_family'], minlength=26)
    sums = np.bincount(partitions['source_family'], weights=delta, minlength=26)
    assert len(counts) == 26 and counts.min() > 0
    rng = np.random.default_rng(20261021582)
    selected = rng.integers(26, size=(2000,26))
    ci = np.quantile(sums[selected].sum(axis=1) / counts[selected].sum(axis=1), [.025,.975])
    groups = {name: {str(int(g)): float(delta[values == g].mean()) for g in np.unique(values)}
              for name, values in partitions.items() if name in ('distance','near_axis')}
    return dict(accuracy_pp=real.statistics(prediction, truth)['accuracy_pp'], paired_accuracy_pp=float(delta.mean()),
        ci95_accuracy_pp=ci.tolist(), groups_delta_pp=groups, changed_rows=int(np.count_nonzero(prediction != baseline)),
        quality_gate=bool(ci[0] >= -.015 and all(d >= -.03 for group in groups.values() for d in group.values())))


def qualify():
    results = {}
    for case, exp in (('development','exp501'),('independent','exp562')):
        request, exact = Path(f'../{exp}/build/{exp}/u-role/requests.csv'), Path(f'../{exp}/build/{exp}/exact.csv')
        frozen = read(f'../exp579/validation/results/exp579/{case}-report.json')['evidence']['C']
        assert identity(request)['sha256'] == frozen['input']['sha256']
        arms = ['G', *ARMS]
        schedule = [arms, *([arms, list(reversed(arms))] * 3)]
        predictions, evidence, timing, runs = {}, {}, {a:[] for a in arms}, []
        for iteration, order in enumerate(schedule):
            for name in order:
                binary = Path('../exp581/build/exp581/G') if name == 'G' else BUILD / name
                output = BUILD / f'{case}-{iteration}-{name}.csv'
                record = speed.measured([str(binary), '-in', str(request), '-out', str(output)], f'{case}-{iteration}-{name}')
                assert record['threads'] == 1 and record['rss_bytes'] <= 2000000000 and record['cpu_s'] <= 3600
                counters = read(record['stderr'])
                assert counters['rows'] == 1000000 and counters['query_allocations'] == 0
                actual = identity(output)
                if name not in evidence:
                    expected = BUILD / (name + '-expected.i32') if case == 'development' and name != 'G' else None
                    p, truth, e, partitions = complete.check_output(request, output, exact, expected)
                    if name == 'G':
                        assert actual['sha256'] == frozen['output']['sha256']
                    predictions[name], evidence[name] = p, e
                    p.astype('<i4').tofile(BUILD / f'{case}-{name}-prediction.i32')
                else:
                    assert all(actual[k] == evidence[name]['output'][k] for k in ('bytes','sha256'))
                    write(ROOT / (output.stem + '-cleanup.json'), dict(file=actual,
                        identical_to=evidence[name]['output'], rebuild_command=record['command']))
                    output.unlink()
                record.update(arm=name, iteration=iteration, output=actual, counters=counters)
                runs.append(record)
                if iteration:
                    timing[name].append(record['cpu_s'])
                print('EXP582_RUN', case, iteration, name, record['cpu_s'], flush=True)
        stats = {}
        for name in ARMS:
            saved = [a-b for a,b in zip(timing['G'],timing[name])]
            mean = statistics.mean(saved)
            width = 2.570581835636314 * statistics.stdev(saved) / math.sqrt(6)
            stats[name] = dict(**paired(predictions[name],predictions['G'],truth,partitions),
                saved_cpu_s=mean, ci95_saved_s=[mean-width,mean+width], speed_gate=mean >= .01 and mean-width > 0)
        results[case] = dict(evidence=evidence, timing_s=timing, runs=runs, stats=stats, input_role='used_development')
        write(ROOT / (case + '-report.json'), results[case])
        print('EXP582_CASE', case, json.dumps(stats), flush=True)
    eligible = [a for a in ARMS if all(r['stats'][a]['quality_gate'] and r['stats'][a]['speed_gate'] for r in results.values())]
    selected = min(eligible,key=lambda a:sum(statistics.mean(r['timing_s'][a]) for r in results.values())) if eligible else None
    write(ROOT / 'report.json', dict(cases=results, selected=selected, full_port_pairs=59904,
        freeze=identity(ROOT / 'freeze.json'), final_goal_achieved=False, fresh_distribution_verified=False))
    print('EXP582_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp582')
    assert sys.argv[1:] in (['prepare'],['audit'],['qualify'])
    {'prepare':prepare,'audit':audit,'qualify':qualify}[sys.argv[1]]()
