#!/usr/bin/env python3
"""Verify directional far spaces with frozen complete-port near assets on r9."""
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path('../exp586/validation').resolve()))
import exp586_complete_candidate as previous

quantized, complete, speed, real = previous.previous, previous.complete, previous.speed, previous.real
read, write, identity = previous.read, previous.write, previous.identity
ROOT, BUILD = Path('validation/results/exp589'), Path('build/exp589')
OFFLINE = Path('offline')
FACTOR = OFFLINE / 'build/exp589'
PLAN = Path('experiment/实验589-远域方向子空间与近域固定背景.md')
BASE = Path('../exp586/build/exp586/N512')
GEOMETRY = BASE.with_name('N512-geometry.bin')
ROWS = 1000000
speed.ROOT = ROOT


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, ROOT / 'candidate-protocol.md')
    trained = read(OFFLINE / 'validation/results/exp589/training.json')
    assert trained['all_training_checks'] and trained['port_pairs'] == 59904
    for asset in trained['factors'] + [trained['center']]:
        real.check(OFFLINE / asset['path'], asset)
    frozen = read('../exp586/validation/results/exp586/candidate-freeze.json')
    real.check(BASE, frozen['arms']['N512']['binary'])
    real.check(GEOMETRY, frozen['arms']['N512']['geometry'])
    source = Path('../exp586/build/exp586/candidate.cpp')
    real.check(source, frozen['source'])
    shutil.copyfile(source, BUILD / 'candidate.cpp')
    left, right = [np.load(FACTOR / ('far-' + side + '.npy'), mmap_mode='r') for side in ('left', 'right')]
    assert left.shape == (4, 59904, 96) and right.shape == (260160, 96)
    model = Path('../exp579/build/exp579/exp579-models.h').read_text()
    common = ['g++', '-std=c++17', '-O3', '-fno-exceptions', '-fno-rtti', '-fno-fast-math',
        '-ffp-contract=off', '-march=x86-64', '-mtune=generic', '-Wall', '-Wextra', '-Werror',
        '-DDELAY_ESTIMATE_EMBEDDED_ARCH', '-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE',
        '-DEXP580_PORT_PARSER', '-DEXP581_PREFETCH', '-DEXP582_BLOCK=64', '-I', 'src']
    records = {}
    ranks = [c['rank'] for c in trained['candidates'] if c['training_gate']]
    arms = [('D' + str(rank), 512, rank) for rank in ranks]
    if 64 in ranks:
        arms.append(('N768D64', 768, 64))
    for name, near_rank, rank in arms:
        assert rank in (64, 96)
        blocks = (rank + 63) // 64
        near_name = 'N' + str(near_rank)
        near_geometry = BASE.with_name(near_name + '-geometry.bin')
        header = BASE.with_name(near_name + '-assets') / 'exp582_int8_geometry.h'
        real.check(near_geometry, frozen['arms'][near_name]['geometry'])
        real.check(header, frozen['arms'][near_name]['header'])
        raw = near_geometry.read_bytes()
        near_end = 119872 + (59904 + 4800) * (near_rank + 4*((near_rank + 63)//64))
        assert raw[:8] == b'EX582Q01' and len(raw) == near_end + 33286656
        assert np.array_equal(np.frombuffer(raw[64:119872], '<i2'), np.load(FACTOR / 'center.npy'))
        arrays, diagnostics = [[], [], [], []], []
        for direction in range(4):
            l, r = left[direction, :, :rank], right[direction*65040:(direction+1)*65040, :rank]
            lm, rm = np.max(np.abs(l), axis=0), np.max(np.abs(r), axis=0)
            diagonal = np.ones(rank)
            active = (lm > 0) & (rm > 0)
            diagonal[active] = np.sqrt(rm[active] / lm[active])
            lq, ls, ld = quantized.quantize(l, diagonal, 64)
            rq, rs, rd = quantized.quantize(r, 1 / diagonal, 64)
            for parts, value in zip(arrays, (lq, rq, ls, rs)):
                parts.append(value)
            diagnostics.append(dict(direction=direction, left=ld, right=rd))
        path, assets = BUILD / (name + '-geometry.bin'), BUILD / (name + '-assets')
        assets.mkdir()
        with path.open('xb') as stream:
            stream.write(b'EX589Q01' + struct.pack('<6I', near_rank, rank, 64, 64, 4800, 260160) + bytes(32))
            stream.write(raw[64:near_end])
            for parts in arrays:
                stream.write(np.concatenate(parts, axis=0).tobytes(order='C'))
        assert path.stat().st_size == near_end + (4*59904 + 260160) * (rank + 4*blocks)
        new_header = header.read_text()
        changes = [('EX582Q01', 'EX589Q01', 1),
            (f'p.rank = g == 0 ? {near_rank} : 96;', f'p.rank = g == 0 ? {near_rank} : {rank};', 1),
            ('const unsigned count = g == 0 ? 4800 : 260160;',
             'const unsigned count = g == 0 ? 4800 : 260160;\n        const unsigned rows = g == 0 ? 59904 : 4 * 59904;', 1),
            ('at += 59904 * p.rank;', 'at += rows * p.rank;', 1),
            ('at += 59904 * p.blocks * 4;', 'at += rows * p.blocks * 4;', 1),
            ('const unsigned local = local582(context, qx, qy, g);',
             'const unsigned local = local582(context, qx, qy, g);\n    const unsigned row = pair + (g ? (context / 120) * 59904 : 0);', 2),
            ('uint64_t(pair)', 'uint64_t(row)', 4)]
        for old, new, count in changes:
            assert new_header.count(old) == count, old
            new_header = new_header.replace(old, new)
        (assets / header.name).write_text(new_header)
        models, count = re.subn(r'constexpr uint64_t kGeometryBytes=\d+;',
            f'constexpr uint64_t kGeometryBytes={path.stat().st_size};', model)
        assert count == 1
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
            stream.seek(64)
            assert stream.read(near_end - 64) == raw[64:near_end]
        records[name] = dict(rank=rank, near_rank=near_rank, near_source=identity(near_geometry),
            binary=identity(BUILD / name), geometry=identity(path),
            quantization=diagnostics, near_bitwise_unchanged=True, header=identity(assets / header.name))
        print('EXP589_BUILT', name, records[name]['binary'], flush=True)
    assert records
    write(ROOT / 'candidate-freeze.json', dict(arms=records, baseline=identity(BASE),
        baseline_geometry=identity(GEOMETRY), training=identity(OFFLINE / 'validation/results/exp589/training.json'),
        driver=identity(__file__), source=identity(BUILD / 'candidate.cpp'), protocol=identity(PLAN)))


def audit():
    keys = np.fromfile('../exp575/build/exp575/keys.i32', '<i4').reshape(ROWS, 2)
    pair, column = keys.T
    assert len(np.unique(pair)) == 59904
    qx, qy, context = (column % 552) // 46, column % 46, column // 552
    old = np.memmap('../exp579/build/exp579/final-trace.bin', dtype=previous.TRACE, mode='r', shape=(ROWS,))
    center = np.fromfile(GEOMETRY, '<i2', count=59904, offset=64)
    original_value = old['response'] * (128 + 125*qx + 125*qy) + center[pair] + 125*qx + np.where(context//120 % 2, 125, 127)*qy
    fee = old['features'][:, 50].astype('i4')
    override = old['base'] != (np.maximum(original_value, 0) + .5).astype('i4') + fee
    records = {}
    for name, candidate in read(ROOT / 'candidate-freeze.json')['arms'].items():
        near_rank = candidate['near_rank']
        baseline_prediction = np.fromfile(BASE.with_name(f'N{near_rank}-expected.i32'), '<i4')
        path, output = BUILD / (name + '-geometry.bin'), BUILD / (name + '-trace.bin')
        run = speed.measured([str(BUILD / (name + '-audit')), '../exp579/build/exp579/queries.bin',
            '../exp579/build/exp579/folds.u8', str(output), '1'], 'audit-' + name)
        trace = np.memmap(output, dtype=previous.TRACE, mode='r', shape=(ROWS,))
        assert np.array_equal(trace['features'].view('u4'), old['features'].view('u4'))
        assert np.array_equal(trace['raw'].view('u4'), old['raw'].view('u4'))
        reference, at = np.zeros(ROWS, dtype='f8'), 119872
        for g, rank, count, rows in ((0, near_rank, 4800, 59904), (1, candidate['rank'], 260160, 4*59904)):
            blocks = (rank + 63) // 64
            arrays = []
            for dt, shape in [('i1', (rows, rank)), ('i1', (count, rank)), ('<f4', (rows, blocks)), ('<f4', (count, blocks))]:
                array = np.memmap(path, dtype=dt, mode='r', offset=at, shape=shape)
                at += array.nbytes
                arrays.append(array)
            left, right, ls, rs = arrays
            indices = np.flatnonzero((qx + qy > 3) == bool(g))
            local = context*10 + qx*(9-qx)//2 + qy if g == 0 else context*542 + qx*46 + qy - np.where(qx < 4, (qx+1)*(8-qx)//2, 10)
            row = pair + (context//120*59904 if g else 0)
            for start in range(0, len(indices), 8192):
                ids = indices[start:start+8192]
                for k in range(blocks):
                    sl = slice(k*64, min((k+1)*64, rank))
                    product = np.sum(left[row[ids], sl].astype('i4') * right[local[ids], sl].astype('i4'), axis=1, dtype='i4')
                    reference[ids] += product.astype('f8') * ls[row[ids], k].astype('f8') * rs[local[ids], k].astype('f8')
        assert at == path.stat().st_size
        assert np.array_equal(reference.view('u8'), trace['response'].view('u8'))
        value = reference*(128 + 125*qx + 125*qy) + center[pair] + 125*qx + np.where(context//120 % 2, 125, 127)*qy
        base = (np.maximum(value, 0) + .5).astype('i4') + fee
        base[override] = old['base'][override]
        assert np.array_equal(base, trace['base'])
        prediction = (np.maximum(base + old['raw'].astype('f8'), 0) + .5).astype('i4') + old['mandatory']
        assert np.array_equal(prediction, trace['prediction'])
        near = qx+qy <= 3
        assert np.array_equal(prediction[near], baseline_prediction[near])
        expected = BUILD / (name + '-expected.i32')
        prediction.astype('<i4').tofile(expected)
        records[name] = dict(run=run, trace=identity(output), expected=identity(expected), bitwise_response=True,
            bitwise_features=True, bitwise_residual=True, exact_integer_output=True,
            port_pairs=59904, rows=ROWS, near_rows=int(near.sum()), near_rank=near_rank,
            near_output_bitwise_unchanged=True)
        print('EXP589_AUDIT', name, flush=True)
    write(ROOT / 'audit.json', records)


def qualify():
    frozen, audits = read(ROOT / 'candidate-freeze.json'), read(ROOT / 'audit.json')
    candidates, results = list(frozen['arms']), {}
    for case, exp in (('development', 'exp501'), ('robustness', 'exp562')):
        if not candidates:
            break
        request, exact = Path(f'../{exp}/build/{exp}/u-role/requests.csv'), Path(f'../{exp}/build/{exp}/exact.csv')
        old = read(f'../exp586/validation/results/exp586/{case}-report.json')['evidence']['N512']
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
                print('EXP589_RUN', case, iteration, name, run['cpu_s'], flush=True)
        stats = {}
        for name in candidates:
            result = previous.compare(predictions[name], predictions['B'], truth, partitions,
                [a-b for a, b in zip(timing[name], timing['B'])])
            result['quality_gate'] = bool(result['paired_accuracy_pp'] >= .02 and result['ci95_accuracy_pp'][0] > 0
                and all(d >= -.03 for group in result['groups_delta_pp'].values() for d in group.values()))
            matching = f"N{frozen['arms'][name]['near_rank']}"
            matched_prediction = np.fromfile(Path('../exp586/build/exp586') / f'{case}-{matching}-prediction.i32', '<i4')
            assert len(matched_prediction) == ROWS
            result['matching_near_baseline'] = matching
            result['far_only_paired_accuracy_pp'] = float((real.points(predictions[name], truth) -
                real.points(matched_prediction, truth)).mean())
            stats[name] = result
        grouped = {group: {str(int(g)): {a: real.statistics(predictions[a][values == g], truth[values == g])
            for a in arms} for g in np.unique(values)} for group, values in partitions.items()}
        write(ROOT / (case + '-groups.json'), grouped)
        results[case] = dict(evidence=evidence, timing_s=timing, runs=runs, stats=stats,
            input_role='previously_used_development', full_program_verified=True)
        write(ROOT / (case + '-report.json'), results[case])
        print('EXP589_CASE', case, json.dumps(stats), flush=True)
        candidates = [name for name in candidates if stats[name]['quality_gate']]
    selected = [name for name in candidates if all(r['stats'][name]['score_gate'] for r in results.values())]
    write(ROOT / 'report.json', dict(cases=results, quality_eligible=candidates, scale_eligible=selected,
        full_port_pairs=59904, fresh_distribution_verified=False, final_goal_achieved=False))


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp589')
    assert sys.argv[1:] in (['prepare'], ['audit'], ['qualify'])
    {'prepare': prepare, 'audit': audit, 'qualify': qualify}[sys.argv[1]]()
