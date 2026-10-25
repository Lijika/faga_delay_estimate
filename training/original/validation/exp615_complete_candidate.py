#!/usr/bin/env python3
"""Integrate only the qualified P table in the frozen generic exp610 worker."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import numpy as np

import exp615_phase_codes as codes

sys.path.insert(0, str(Path('../exp603/validation').resolve()))
import exp603_rank_cost as prior

ROOT, BUILD = codes.ROOT, codes.BUILD
BASE = Path('../exp609/build/exp609/F')
read, write, identity, checked = codes.read, codes.write, codes.identity, codes.checked
speed = prior.speed
speed.ROOT = ROOT


def build():
    selected = read(ROOT / 'evaluation.json')['selected']
    assert selected == 'P'
    frozen = read('../exp609/validation/results/exp609/build-freeze.json')
    checked(BASE, frozen['binaries']['F'])
    dependencies = []
    for item in frozen['dependencies']:
        path = Path(item['path'])
        if path.parts[0] != '..':
            path = Path('../exp609') / path
        checked(path, item)
        dependencies.append(identity(path))
    for key in ('source', 'entry', 'header'):
        checked(Path('../exp609') / frozen[key]['path'], frozen[key])
    table = BUILD / 'P.p5'
    checked(table, read(ROOT / 'training.json')['assets']['P'])
    source = (Path('../exp609') / frozen['source']['path']).read_text()
    source = prior.replace(source, '#include "exp608_geometry.h"',
                           '#include "exp608_geometry.h"\n#include "exp615_phase_lookup.h"')
    source = prior.replace(source, '    initializeGeometry582();',
                           '    initializeGeometry582();\n    initializePhaseCodes615();')
    source = prior.replace(source, '    prefetchGeometry581(pair,context,qx,qy);',
        '    prefetchGeometry581(pair,context,qx,qy);\n'
        '    if (qx+qy>3) _mm_prefetch(reinterpret_cast<const char*>(phaseCodes615 +\n'
        '        phaseByte615(pair,context)), _MM_HINT_T0);')
    source = prior.replace(source, '    const int base=nominal+fee;',
                           '    const int base=nominal+fee+phaseCorrection615(pair,context,qx,qy);')
    (BUILD / 'worker.cpp').write_text(source)
    for name in ('entry.cpp', 'exp608_geometry.h', 'exp596_csv_batch.h', 'exp601_port_parser.h'):
        shutil.copyfile(Path('../exp609/build/exp609') / name, BUILD / name)
    assembly = BUILD / 'codes.S'
    assembly.write_text('.section .rodata.exp615,"a",@progbits\n.balign 64\n'
        '.global exp615_codes\nexp615_codes:\n.incbin "' + str(table.resolve()) +
        '"\n.section .note.GNU-stack,"",@progbits\n')
    speed.measured(['g++', '-c', str(assembly), '-o', str(BUILD / 'codes.o')], 'embed-codes')
    binaries = {'A': identity(BASE)}
    for suffix in ('', '-audit'):
        tag = 'P' + suffix
        command = read('../exp609/validation/results/exp609/compile-F' + suffix + '.run.json')['command']
        substitutions = {'build/exp609': str(BUILD), 'build/exp609/worker.cpp': str(BUILD / 'worker.cpp'),
                         'build/exp609/F' + suffix + '.o': str(BUILD / (tag + '.o'))}
        command = [substitutions.get(arg, arg) for arg in command]
        command[1:1] = ['-I', 'tests']
        speed.measured(command, 'compile-' + tag)
        assert not (ROOT / ('compile-' + tag + '.stderr')).read_bytes()
        sections = subprocess.check_output(['readelf', '-SW', str(BUILD / (tag + '.o'))], text=True)
        assert '.init_array' not in sections
        link = read('../exp609/validation/results/exp609/link-F' + suffix + '.run.json')['command']
        link = [arg for arg in link if arg not in ('build/exp609/S' + suffix + '.o',
                                                  'build/exp609/D' + suffix + '.o')]
        substitutions.update({'build/exp609/entry.cpp': str(BUILD / 'entry.cpp'),
                              'build/exp609/F' + suffix: str(BUILD / tag)})
        link = [substitutions.get(arg, arg) for arg in link]
        link.insert(1, str(BUILD / 'codes.o'))
        speed.measured(link, 'link-' + tag)
        assert not (ROOT / ('link-' + tag + '.stderr')).read_bytes()
        assert (BUILD / tag).stat().st_size < 100000000
        deps = subprocess.run(['ldd', str(BUILD / tag)], capture_output=True, text=True)
        assert 'not a dynamic executable' in deps.stdout + deps.stderr
        binaries[tag] = identity(BUILD / tag)
    write(ROOT / 'build-freeze.json', dict(binaries=binaries, table=identity(table),
          source=identity(BUILD / 'worker.cpp'), entry=identity(BUILD / 'entry.cpp'),
          header=identity('tests/exp615_phase_lookup.h'), driver=identity(__file__),
          dependencies=dependencies, source_baseline=identity('../exp609/validation/results/exp609/build-freeze.json'),
          original_protocol=identity(ROOT / 'protocol-original.md')))
    print('EXP615_COMPLETE_BUILT', binaries['P'], flush=True)


def audit():
    frozen = read(ROOT / 'build-freeze.json')
    checked(BUILD / 'P-audit', frozen['binaries']['P-audit'])
    data = codes.prior.load()
    dtype = prior.old.previous.TRACE
    reference_path = Path('../exp589/build/exp589/D64-trace.bin')
    checked(reference_path, read('../exp589/validation/results/exp589/audit.json')['D64']['trace'])
    reference = np.memmap(reference_path, dtype=dtype, mode='r', shape=(1000000,))
    keys = np.fromfile(BUILD / 'keys.bin', '<u4', offset=12).reshape(1000000, 4)
    pair, context, qx, qy = keys.T
    correction = codes.unpack(BUILD / 'P.p5', 59904 * 480)[pair, context].astype('i4')
    correction[qx + qy <= 3] = 0
    records = []
    for mode in (0, 1):
        path = BUILD / f'audit-{mode}-trace.bin'
        command = [str(BUILD / 'P-audit'), '../exp579/build/exp579/queries.bin',
                   '../exp579/build/exp579/folds.u8', str(path), str(mode)]
        run = speed.measured(command, 'audit-' + str(mode))
        actual = np.memmap(path, dtype=dtype, mode='r', shape=(1000000,))
        assert np.array_equal(actual['feature' if 'feature' in dtype.names else 'features'].copy().view('u4'),
                              data['features'].view('u4'))
        assert np.array_equal(actual['response'].copy().view('u8'), reference['response'].copy().view('u8'))
        assert np.array_equal(actual['mandatory'], data['mandatory'])
        assert np.array_equal(actual['base'], data['D64'] + correction)
        raw = reference['raw'] if mode else np.fromfile('../exp576/build/exp576/R8.f32', '<f4')
        assert np.array_equal(actual['raw'].copy().view('u4'), np.ascontiguousarray(raw).view('u4'))
        expected = prior.old.complete.trees.decode(raw, data['D64'] + correction, data['mandatory'])
        assert np.array_equal(actual['prediction'], expected)
        expected_path = BUILD / ('final-expected.i32' if mode else 'P-prediction.i32')
        if mode:
            expected.astype('<i4').tofile(expected_path)
        else:
            assert np.array_equal(np.fromfile(expected_path, '<i4'), expected)
        records.append(dict(mode=mode, run=run, trace=identity(path), expected=identity(expected_path),
                            all_fields_verified=True, rebuild_command=command))
        del actual
        path.unlink()
    write(ROOT / 'audit.json', dict(records=records, rows=1000000, port_pairs=59904,
          oof_prediction_bitwise=True, final_prediction_bitwise=True, near_bitwise_unchanged=True))
    print('EXP615_COMPLETE_AUDIT_PASSED', flush=True)


def qualify():
    assert read(ROOT / 'audit.json')['final_prediction_bitwise']
    frozen = read(ROOT / 'build-freeze.json')
    for name in ('A', 'P'):
        checked(BASE if name == 'A' else BUILD / name, frozen['binaries'][name])
    reference = read('../exp589/validation/results/exp589/development-report.json')['evidence']['D64']
    request = Path('../exp501/build/exp501/u-role/requests.csv')
    exact = Path('../exp501/build/exp501/exact.csv')
    checked(request, reference['input'])
    checked(exact, reference['labels'])
    schedule = [('A', 'P'), *([('A', 'P'), ('P', 'A')] * 3)]
    write(ROOT / 'development-timing-freeze.json', dict(schedule=schedule, input=reference['input'],
          labels=reference['labels'], candidate=identity(ROOT / 'build-freeze.json'),
          comparison_seed=20261022615, bootstrap_count=9999, ci_quantiles=[.025, .975],
          quality_delta_pp=.02, joint_point_min=.01, joint_lower_min=0))
    predictions, timing, evidence, runs = {}, {'A': [], 'P': []}, {}, []
    for iteration, order in enumerate(schedule):
        for name in order:
            output = BUILD / f'development-{iteration}-{name}.csv'
            run = speed.measured([str(BASE if name == 'A' else BUILD / name),
                                  '-in', str(request), '-out', str(output)], output.stem)
            counters = read(run['stderr'])
            assert run['threads'] == 1 and run['rss_bytes'] <= 2000000000 and run['cpu_s'] <= 3600
            assert counters['rows'] == 1000000 and counters['query_allocations'] == 0
            current = identity(output)
            if name not in evidence:
                expected = BUILD / 'final-expected.i32' if name == 'P' else None
                prediction, truth, record, partitions = prior.old.complete.check_output(request, output, exact, expected)
                predictions[name], evidence[name] = prediction, dict(record, output=current)
                if name == 'A':
                    assert all(current[k] == reference['output'][k] for k in ('bytes', 'sha256'))
            assert all(current[k] == evidence[name]['output'][k] for k in ('bytes', 'sha256'))
            run.update(arm=name, iteration=iteration, output=current, counters=counters)
            write(ROOT / (output.stem + '-evidence.json'), run)
            runs.append(run)
            if iteration:
                timing[name].append(run['cpu_s'])
            if iteration:
                output.unlink()
            print('EXP615_COMPLETE_RUN', iteration, name, run['cpu_s'], flush=True)
    sys.path.insert(0, str(Path('../exp592/validation').resolve()))
    from exp592_xgb_audit import transition, points
    result = transition(predictions['P'], predictions['A'], truth, partitions)
    family = partitions['source_family']
    counts = np.bincount(family, minlength=26)
    delta = points(predictions['P'], truth) - points(predictions['A'], truth)
    sums = np.bincount(family, weights=delta, minlength=26)
    rng = np.random.default_rng(20261022615)
    chosen = rng.integers(26, size=(9999, 26))
    accuracy = sums[chosen].sum(axis=1) / counts[chosen].sum(axis=1)
    extra = np.asarray(timing['P']) - np.asarray(timing['A'])
    cpu = extra[rng.integers(6, size=(9999, 6))].mean(axis=1)
    joint = .8 * accuracy - 1000 * cpu / 120
    point = .8 * result['delta_accuracy_pp'] - 1000 * extra.mean() / 120
    result.update(extra_cpu_s=float(extra.mean()), ci95_extra_cpu_s=np.quantile(cpu, [.025, .975]).tolist(),
          ci95_delta_accuracy_pp=np.quantile(accuracy, [.025, .975]).tolist(),
          score_extrapolated_1b=float(point), ci95_score_extrapolated_1b=np.quantile(joint, [.025, .975]).tolist(),
          joint_gate=bool(point >= .01 and np.quantile(joint, .025) > 0),
          cpu_1b_is_extrapolation=True, complete_program_verified=True)
    write(ROOT / 'complete-report.json', dict(comparison=result, timing=timing, evidence=evidence,
          runs=runs, rows=1000000, unique_rows=1000000, port_pairs=59904,
          unchanged_repeated_outputs=True, build=identity(ROOT / 'build-freeze.json'),
          independent_new_requests_verified=False, disk_free_end=shutil.disk_usage('.').free))
    print('EXP615_COMPLETE_QUALIFIED', result['candidate']['accuracy_pp'], result['extra_cpu_s'],
          result['score_extrapolated_1b'], result['joint_gate'], flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp615')
    assert sys.argv[1:] in (['build'], ['audit'], ['qualify'])
    {'build': build, 'audit': audit, 'qualify': qualify}[sys.argv[1]]()
