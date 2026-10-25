#!/usr/bin/env python3
"""Build and verify increased near ranks on r9 using the frozen B64 far asset."""
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

sys.path.insert(0, str(Path('../exp582/validation').resolve()))
import exp582_int8_geometry as previous

complete, speed, real = previous.complete, previous.speed, previous.real
read, write, identity = previous.read, previous.write, previous.identity
ROOT, BUILD = Path('validation/results/exp586'), Path('build/exp586')
OFFLINE = Path('offline')
FACTOR = OFFLINE / 'build/exp586'
PLAN = Path('experiment/实验586-短距名义背景的INT8容量再分配.md')
BASE = Path('../exp582/build/exp582/B64')
GEOMETRY = BASE.with_name('B64-geometry.bin')
ROWS = 1000000
TRACE = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
    formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f4'],
    offsets=[0, 216, 224, 228, 232, 236], itemsize=240))
speed.ROOT = ROOT


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT / 'candidate-protocol.md')
    trained = read(OFFLINE / 'validation/results/exp586/training.json')
    assert trained['all_training_checks'] and trained['port_pairs'] == 59904
    for asset in trained['factors'] + [trained['center']]:
        real.check(OFFLINE / asset['path'], asset)
    frozen = read('../exp582/validation/results/exp582/freeze.json')
    real.check(BASE, frozen['arms']['B64']['binary'])
    real.check(GEOMETRY, frozen['arms']['B64']['geometry'])
    assert identity(BASE)['sha256'] == '816b6309d3726814c74f78905cb6d8b50be6f5849905a2338b9b5b13b2f65d05'
    source = Path('../exp582/build/exp582/candidate.cpp')
    header = Path('../exp582/tests/exp582_int8_geometry.h')
    real.check(source, frozen['source'])
    real.check(header, frozen['header'])
    shutil.copyfile(source, BUILD / 'candidate.cpp')
    raw = GEOMETRY.read_bytes()
    assert raw[:8] == b'EX582Q01' and len(raw) == 46606144
    center, far = raw[64:119872], raw[13319488:]
    assert len(far) == 33286656
    assert np.array_equal(np.frombuffer(center, '<i2'), np.load(FACTOR / 'center.npy'))
    left, right = [np.load(FACTOR / ('near-' + side + '.npy'), mmap_mode='r') for side in ('left', 'right')]
    assert left.shape == (59904, 768) and right.shape == (4800, 768)
    model = Path('../exp579/build/exp579/exp579-models.h').read_text()
    common = ['g++', '-std=c++17', '-O3', '-fno-exceptions', '-fno-rtti', '-fno-fast-math',
        '-ffp-contract=off', '-march=x86-64', '-mtune=generic', '-Wall', '-Wextra', '-Werror',
        '-DDELAY_ESTIMATE_EMBEDDED_ARCH', '-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE',
        '-DEXP580_PORT_PARSER', '-DEXP581_PREFETCH', '-DEXP582_BLOCK=64', '-I', 'src']
    records = {}
    for candidate in trained['candidates']:
        if not candidate['training_gate']:
            continue
        rank = candidate['rank']
        assert rank in (512, 768) and rank % 64 == 0
        name, blocks = 'N' + str(rank), rank // 64
        lm, rm = np.max(np.abs(left[:, :rank]), axis=0), np.max(np.abs(right[:, :rank]), axis=0)
        diagonal = np.ones(rank)
        active = (lm > 0) & (rm > 0)
        diagonal[active] = np.sqrt(rm[active] / lm[active])
        lq, ls, ld = previous.quantize(left[:, :rank], diagonal, 64)
        rq, rs, rd = previous.quantize(right[:, :rank], 1 / diagonal, 64)
        path, assets = BUILD / (name + '-geometry.bin'), BUILD / (name + '-assets')
        assets.mkdir()
        with path.open('xb') as stream:
            stream.write(b'EX582Q01' + struct.pack('<6I', rank, 96, 64, 64, 4800, 260160) + bytes(32))
            stream.write(center)
            for array in (lq, rq, ls, rs):
                stream.write(array.tobytes(order='C'))
            stream.write(far)
        assert path.stat().st_size == 119872 + 64704 * (rank + 4 * blocks) + len(far)
        new_header = header.read_text()
        marker = 'p.rank = g == 0 ? 192 : 96;'
        assert new_header.count(marker) == 1
        (assets / header.name).write_text(new_header.replace(marker, f'p.rank = g == 0 ? {rank} : 96;'))
        models, changes = re.subn(r'constexpr uint64_t kGeometryBytes=\d+;',
            f'constexpr uint64_t kGeometryBytes={path.stat().st_size};', model)
        assert changes == 1
        (assets / 'exp579-models.h').write_text(models)
        assembly = '.section .rodata.exp579,"a",@progbits\n.balign 64\n.global exp579_geometry\nexp579_geometry:\n.incbin "' + str(path.resolve()) + '"\n.section .note.GNU-stack,"",@progbits\n'
        (assets / 'geometry.S').write_text(assembly)
        speed.measured(['g++', '-c', str(assets / 'geometry.S'), '-o', str(assets / 'geometry.o')], name + '-assemble')
        for audit in (False, True):
            tag = name + ('-audit' if audit else '')
            flags = ['-I', str(assets), '-I', 'tests'] + (['-DEXP579_AUDIT'] if audit else [])
            command = common + flags + [str(BUILD / 'candidate.cpp'),
                '../exp580/build/exp580/architecture-resolver.o', '../exp579/build/exp579/arch-text.o',
                str(assets / 'geometry.o'), '-static', '-s', '-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc',
                '-o', str(BUILD / tag)]
            speed.measured(command, 'compile-' + tag)
            assert not (ROOT / ('compile-' + tag + '.stderr')).read_bytes()
            assert (BUILD / tag).stat().st_size < 100000000
        deps = subprocess.run(['ldd', str(BUILD / name)], capture_output=True, text=True)
        assert 'not a dynamic executable' in deps.stdout + deps.stderr
        with path.open('rb') as stream:
            stream.seek(119872 + 64704 * (rank + 4 * blocks))
            assert stream.read() == far
        records[name] = dict(rank=rank, binary=identity(BUILD / name), geometry=identity(path),
            left=ld, right=rd, far_bitwise_unchanged=True, header=identity(assets / header.name))
        print('EXP586_BUILT', name, records[name]['binary'], flush=True)
    write(ROOT / 'candidate-freeze.json', dict(arms=records, baseline=identity(BASE),
        baseline_geometry=identity(GEOMETRY), training=identity(OFFLINE / 'validation/results/exp586/training.json'),
        driver=identity(__file__), source=identity(BUILD / 'candidate.cpp'), protocol=identity(PLAN)))


def audit():
    keys = np.fromfile('../exp575/build/exp575/keys.i32', '<i4').reshape(ROWS, 2)
    pair, column = keys.T
    assert len(np.unique(pair)) == 59904
    qx, qy, context = (column % 552) // 46, column % 46, column // 552
    old = np.memmap('../exp579/build/exp579/final-trace.bin', dtype=TRACE, mode='r', shape=(ROWS,))
    center = np.fromfile(GEOMETRY, '<i2', count=59904, offset=64)
    original_value = old['response'] * (128 + 125*qx + 125*qy) + center[pair] + 125*qx + np.where(context//120 % 2, 125, 127)*qy
    original_nominal = (np.maximum(original_value, 0) + .5).astype('i4')
    fee = old['features'][:, 50].astype('i4')
    override = old['base'] != original_nominal + fee
    records = {}
    for name, candidate in read(ROOT / 'candidate-freeze.json')['arms'].items():
        path, output = BUILD / (name + '-geometry.bin'), BUILD / (name + '-trace.bin')
        command = [str(BUILD / (name + '-audit')), '../exp579/build/exp579/queries.bin',
            '../exp579/build/exp579/folds.u8', str(output), '1']
        saved = ROOT / ('audit-' + name + '.run.json')
        if saved.exists():
            run = read(saved)
            assert run['command'] == command and run['exit_code'] == 0
            assert output.stat().st_size == ROWS * TRACE.itemsize
        else:
            run = speed.measured(command, 'audit-' + name)
        trace = np.memmap(output, dtype=TRACE, mode='r', shape=(ROWS,))
        assert np.array_equal(trace['features'].view('u4'), old['features'].view('u4'))
        assert np.array_equal(trace['raw'].view('u4'), old['raw'].view('u4'))
        reference, at = np.zeros(ROWS, dtype='f8'), 119872
        for g, rank, count in ((0, candidate['rank'], 4800), (1, 96, 260160)):
            blocks = (rank + 63) // 64
            arrays = []
            for dt, shape in [('i1', (59904, rank)), ('i1', (count, rank)), ('<f4', (59904, blocks)), ('<f4', (count, blocks))]:
                array = np.memmap(path, dtype=dt, mode='r', offset=at, shape=shape)
                at += array.nbytes
                arrays.append(array)
            left, right, ls, rs = arrays
            indices = np.flatnonzero((qx + qy > 3) == bool(g))
            local = context*10 + qx*(9-qx)//2 + qy if g == 0 else context*542 + qx*46 + qy - np.where(qx < 4, (qx+1)*(8-qx)//2, 10)
            for start in range(0, len(indices), 8192):
                ids = indices[start:start+8192]
                for k in range(blocks):
                    sl = slice(k*64, min((k+1)*64, rank))
                    product = np.sum(left[pair[ids], sl].astype('i4') * right[local[ids], sl].astype('i4'), axis=1, dtype='i4')
                    reference[ids] += product.astype('f8') * ls[pair[ids], k].astype('f8') * rs[local[ids], k].astype('f8')
        assert at == path.stat().st_size
        assert np.array_equal(reference.view('u8'), trace['response'].view('u8'))
        value = reference*(128 + 125*qx + 125*qy) + center[pair] + 125*qx + np.where(context//120 % 2, 125, 127)*qy
        base = (np.maximum(value, 0) + .5).astype('i4') + fee
        base[override] = old['base'][override]
        assert np.array_equal(base, trace['base'])
        prediction = (np.maximum(base + old['raw'].astype('f8'), 0) + .5).astype('i4') + old['mandatory']
        assert np.array_equal(prediction, trace['prediction'])
        expected = BUILD / (name + '-expected.i32')
        prediction.astype('<i4').tofile(expected)
        records[name] = dict(run=run, trace=identity(output), expected=identity(expected), bitwise_response=True,
            bitwise_features=True, bitwise_residual=True, exact_integer_output=True,
            port_pairs=59904, rows=ROWS, near_rows=int(np.count_nonzero(qx+qy <= 3)))
        print('EXP586_AUDIT', name, flush=True)
    write(ROOT / 'audit.json', records)


def compare(prediction, baseline, truth, partitions, extra_cpu):
    delta = real.points(prediction, truth) - real.points(baseline, truth)
    counts = np.bincount(partitions['source_family'], minlength=26)
    sums = np.bincount(partitions['source_family'], weights=delta, minlength=26)
    assert len(counts) == 26 and counts.min() > 0 and len(extra_cpu) == 6
    rng = np.random.default_rng(20261022586)
    selected = rng.integers(26, size=(2000, 26))
    accuracy = sums[selected].sum(axis=1) / counts[selected].sum(axis=1)
    ci = np.quantile(accuracy, [.025, .975])
    groups = {name: {str(int(g)): float(delta[values == g].mean()) for g in np.unique(values)}
        for name, values in partitions.items() if name in ('distance', 'near_axis')}
    width = 2.570581835636314 * statistics.stdev(extra_cpu) / math.sqrt(6)
    mean_cpu = statistics.mean(extra_cpu)
    cpu_boot = np.asarray(extra_cpu)[rng.integers(6, size=(2000, 6))].mean(axis=1)
    combined = .8 * accuracy - 1000 * cpu_boot / 120
    score = .8 * float(delta.mean()) - 1000 * mean_cpu / 120
    score_ci = np.quantile(combined, [.025, .975]).tolist()
    return dict(accuracy_pp=real.statistics(prediction, truth)['accuracy_pp'], paired_accuracy_pp=float(delta.mean()),
        ci95_accuracy_pp=ci.tolist(), groups_delta_pp=groups, changed_rows=int(np.count_nonzero(prediction != baseline)),
        quality_gate=bool(delta.mean() >= .08 and ci[0] > 0 and all(d >= -.03 for g in groups.values() for d in g.values())),
        extra_cpu_s=mean_cpu, ci95_extra_cpu_s=[mean_cpu-width, mean_cpu+width], score_extrapolated_1b=score,
        ci95_score_extrapolated_1b=score_ci, score_gate=bool(score >= .01 and score_ci[0] > 0),
        bootstrap='2000 independent source-family and paired timing resamples; 26 families; 6 rounds',
        cpu_1b_is_extrapolation=True)


def qualify():
    frozen = read(ROOT / 'candidate-freeze.json')
    audits = read(ROOT / 'audit.json')
    candidates = list(frozen['arms'])
    results = {}
    for case, exp in (('development', 'exp501'), ('robustness', 'exp562')):
        if not candidates:
            break
        request, exact = Path(f'../{exp}/build/{exp}/u-role/requests.csv'), Path(f'../{exp}/build/{exp}/exact.csv')
        old_case = 'development' if case == 'development' else 'independent'
        old = read(f'../exp582/validation/results/exp582/{old_case}-report.json')['evidence']['B64']
        real.check(request, old['input'])
        arms = ['B', *candidates]
        schedule = [arms, *([arms, list(reversed(arms))] * 3)]
        write(ROOT / (case + '-timing-freeze.json'), dict(schedule=schedule, input=identity(request),
            labels=identity(exact), candidate_freeze=identity(ROOT / 'candidate-freeze.json'),
            distribution_previously_used=True))
        predictions, evidence, runs, timing = {}, {}, [], {a: [] for a in arms}
        for iteration, order in enumerate(schedule):
            for name in order:
                binary = BASE if name == 'B' else BUILD / name
                if name != 'B':
                    assert audits[name]['exact_integer_output']
                    real.check(binary, frozen['arms'][name]['binary'])
                output = BUILD / f'{case}-{iteration}-{name}.csv'
                run = speed.measured([str(binary), '-in', str(request), '-out', str(output)], output.stem)
                assert run['threads'] == 1 and run['rss_bytes'] <= 2000000000 and run['cpu_s'] <= 3600
                counters = read(run['stderr'])
                assert counters['rows'] == ROWS and counters['query_allocations'] == 0
                actual = identity(output)
                if name not in evidence:
                    expected = BUILD / (name + '-expected.i32') if case == 'development' and name != 'B' else None
                    p, truth, e, partitions = complete.check_output(request, output, exact, expected)
                    if name == 'B':
                        assert actual['sha256'] == old['output']['sha256']
                    predictions[name], evidence[name] = p, e
                    p.astype('<i4').tofile(BUILD / f'{case}-{name}-prediction.i32')
                else:
                    assert all(actual[k] == evidence[name]['output'][k] for k in ('bytes', 'sha256'))
                    write(ROOT / (output.stem + '-cleanup.json'), dict(file=actual,
                        identical_to=evidence[name]['output'], rebuild_command=run['command']))
                    output.unlink()
                run.update(arm=name, iteration=iteration, output=actual, counters=counters)
                runs.append(run)
                if iteration:
                    timing[name].append(run['cpu_s'])
                print('EXP586_RUN', case, iteration, name, run['cpu_s'], flush=True)
        stats = {name: compare(predictions[name], predictions['B'], truth, partitions,
            [a-b for a, b in zip(timing[name], timing['B'])]) for name in candidates}
        grouped = {group: {str(int(g)): {a: real.statistics(predictions[a][values == g], truth[values == g])
            for a in arms} for g in np.unique(values)} for group, values in partitions.items()}
        write(ROOT / (case + '-groups.json'), grouped)
        results[case] = dict(evidence=evidence, timing_s=timing, runs=runs, stats=stats,
            input_role='previously_used_development', full_program_verified=True)
        write(ROOT / (case + '-report.json'), results[case])
        print('EXP586_CASE', case, json.dumps(stats), flush=True)
        candidates = [name for name in candidates if stats[name]['quality_gate']]
    selected = [name for name in candidates if all(r['stats'][name]['score_gate'] for r in results.values())]
    write(ROOT / 'report.json', dict(cases=results, quality_eligible=candidates, scale_eligible=selected,
        full_port_pairs=59904, fresh_distribution_verified=False, final_goal_achieved=False))


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp586')
    assert sys.argv[1:] in (['prepare'], ['audit'], ['qualify'])
    {'prepare': prepare, 'audit': audit, 'qualify': qualify}[sys.argv[1]]()
