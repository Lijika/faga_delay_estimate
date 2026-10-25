#!/usr/bin/env python3
"""Measure frozen near/far capacity choices with the exp601 execution path."""
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path('../exp589/validation').resolve()))
import exp589_complete_candidate as old

ROOT, BUILD = Path('validation/results/exp603'), Path('build/exp603')
PLAN = Path('experiment/实验603-固定模型容量分配与尾块推理成本.md')
BASE = Path('../exp601/build/exp601/PQ')
ARMS = ('A', 'D96', 'N768D64')
read, write, identity, check = old.read, old.write, old.identity, old.real.check
speed = old.speed
speed.ROOT = ROOT


def replace(text, before, after, count=1):
    assert text.count(before) == count, (before, text.count(before), count)
    return text.replace(before, after)


def binary(arm):
    return BASE if arm == 'A' else BUILD / arm


def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True)
    frozen = read('../exp601/validation/results/exp601/freeze.json')
    check(BASE, frozen['binary'])
    assert frozen['binary']['sha256'] == 'f3d96c4b06162812778015628d1978c6753dfba03fbad7adc7ac9d886c082196'
    dependencies = []
    for item in frozen['dependencies']:
        path = Path(item['path'])
        if path.parts[0] != '..':
            path = Path('../exp601') / path
        check(path, item)
        dependencies.append(identity(path))
    source = Path('../exp601') / frozen['source']['path']
    check(source, frozen['source'])
    text = replace(source.read_text(), '#include "exp595_static_geometry.h"',
        '#include "exp603_geometry.h"')
    (BUILD / 'candidate.cpp').write_text(text)
    reader = Path('../exp601') / frozen['generated_reader']['path']
    check(reader, frozen['generated_reader'])
    for path in (reader, Path('../exp601/build/exp601/exp601_port_parser.h')):
        shutil.copyfile(path, BUILD / path.name)
    header_path = Path('../exp595/tests/exp595_static_geometry.h')
    text = header_path.read_text()
    text = replace(text, 'static inline int dot64_595(', 'template <unsigned Width>\nstatic inline int dot595(')
    text = replace(text, '    const __m128i zero',
        '    static_assert(Width == 32 || Width == 64);\n    const __m128i zero')
    text = replace(text, 'k < 64;', 'k < Width;')
    text = replace(text, 'Group ? 64 : 512', 'Group ? EXP603_FAR_RANK : EXP603_NEAR_RANK', 2)
    text = replace(text, 'blocks = rank / 64', 'blocks = (rank + 63) / 64', 2)
    text = replace(text,
        '    for (unsigned group = 0; group < blocks; ++group)\n'
        '        total += double(dot64_595(a + group * 64, b + group * 64)) * double(sa[group]) * double(sb[group]);',
        '    for (unsigned group = 0; group < rank / 64; ++group)\n'
        '        total += double(dot595<64>(a + group * 64, b + group * 64)) * double(sa[group]) * double(sb[group]);\n'
        '    if constexpr (rank % 64 == 32)\n'
        '        total += double(dot595<32>(a + rank - 32, b + rank - 32)) * double(sa[blocks-1]) * double(sb[blocks-1]);')
    (BUILD / 'exp603_geometry.h').write_text(text)
    dependencies.append(identity(header_path))
    models = read('../exp589/validation/results/exp589/candidate-freeze.json')
    template = read('../exp601/validation/results/exp601/compile-PQ.run.json')['command']
    records = {'A': identity(BASE)}
    for arm in ARMS[1:]:
        model = models['arms'][arm]
        assets = Path('../exp589/build/exp589') / (arm + '-assets')
        check(Path('../exp589') / model['geometry']['path'], model['geometry'])
        check(assets / 'exp582_int8_geometry.h', model['header'])
        dependencies.extend(identity(assets / name) for name in
            ('exp582_int8_geometry.h', 'exp579-models.h', 'geometry.o'))
        for suffix in ('', '-audit'):
            name = arm + suffix
            substitution = {'build/exp601': str(BUILD), 'build/exp601/PQ.cpp': str(BUILD / 'candidate.cpp'),
                'build/exp601/PQ': str(BUILD / name),
                '../exp589/build/exp589/D64-assets': str(assets),
                '../exp589/build/exp589/D64-assets/geometry.o': str(assets / 'geometry.o')}
            command = [substitution.get(arg, arg) for arg in template]
            command[1:1] = [f'-DEXP603_NEAR_RANK={model["near_rank"]}', f'-DEXP603_FAR_RANK={model["rank"]}']
            if suffix:
                command.insert(1, '-DEXP579_AUDIT')
            speed.measured(command, 'compile-' + name)
            assert not (ROOT / ('compile-' + name + '.stderr')).read_bytes()
            assert (BUILD / name).stat().st_size < 100000000
            linked = subprocess.run(['ldd', str(BUILD / name)], capture_output=True, text=True)
            assert 'not a dynamic executable' in linked.stdout + linked.stderr
            records[name] = identity(BUILD / name)
    shutil.copyfile(PLAN, ROOT / 'protocol-original.md')
    write(ROOT / 'build-freeze.json', dict(binaries=records, source=identity(BUILD / 'candidate.cpp'),
        header=identity(BUILD / 'exp603_geometry.h'), reader=identity(BUILD / reader.name),
        parser=identity(BUILD / 'exp601_port_parser.h'), dependencies=dependencies,
        models=models, driver=identity(__file__), protocol=identity(ROOT / 'protocol-original.md'),
        disk_start_bytes=shutil.disk_usage('.').free))


def audit():
    frozen = read(ROOT / 'build-freeze.json')
    references = read('../exp589/validation/results/exp589/audit.json')
    dtype = old.previous.TRACE
    reports = {}
    for arm in ARMS[1:]:
        reference = references[arm]
        assert reference['rows'] == 1000000 and reference['port_pairs'] == 59904
        expected = Path('../exp589') / reference['trace']['path']
        check(expected, reference['trace'])
        check(BUILD / (arm + '-audit'), frozen['binaries'][arm + '-audit'])
        trace = BUILD / (arm + '-trace.bin')
        command = [str(BUILD / (arm + '-audit')), '../exp579/build/exp579/queries.bin',
            '../exp579/build/exp579/folds.u8', str(trace), '1']
        run = speed.measured(command, 'audit-' + arm)
        a, b = [np.memmap(p, mode='r', dtype=dtype, shape=(1000000,)) for p in (trace, expected)]
        for name in dtype.names:
            assert np.array_equal(np.ascontiguousarray(a[name]).view('u1'),
                np.ascontiguousarray(b[name]).view('u1')), (arm, name)
        reports[arm] = dict(run=run, output=identity(trace), reference=reference['trace'],
            matched_fields=list(dtype.names), rows=1000000, port_pairs=59904,
            rebuild_command=command)
        write(ROOT / ('audit-' + arm + '-evidence.json'), reports[arm])
        del a, b
        trace.unlink()
    write(ROOT / 'audit.json', reports)


def compare(prediction, baseline, truth, partitions, extra_cpu):
    result = old.previous.compare(prediction, baseline, truth, partitions, extra_cpu)
    delta = old.real.points(prediction, truth) - old.real.points(baseline, truth)
    family = partitions['source_family']
    counts, sums = np.bincount(family, minlength=26), np.bincount(family, weights=delta, minlength=26)
    rng = np.random.default_rng(20261022603)
    selected = rng.integers(26, size=(10000, 26))
    accuracy = sums[selected].sum(axis=1) / counts[selected].sum(axis=1)
    cpu = np.asarray(extra_cpu)[rng.integers(6, size=(10000, 6))].mean(axis=1)
    ci = np.quantile(accuracy, [.0125, .9875]).tolist()
    joint = np.quantile(.8 * accuracy - 1000 * cpu / 120, [.0125, .9875]).tolist()
    result.update(simultaneous_ci_accuracy_pp=ci, simultaneous_ci_score_extrapolated_1b=joint,
        quality_gate=bool(delta.mean() >= .02 and ci[0] > 0 and all(
            d >= -.03 for group in result['groups_delta_pp'].values() for d in group.values())),
        score_gate=bool(result['score_extrapolated_1b'] >= .01 and joint[0] > 0),
        bootstrap='10000 source-family and paired timing resamples; two-candidate Bonferroni 97.5% intervals')
    return result


def qualify():
    frozen = read(ROOT / 'build-freeze.json')
    assert set(read(ROOT / 'audit.json')) == set(ARMS[1:])
    for arm in ARMS:
        check(binary(arm), frozen['binaries'][arm])
    results = {}
    for case, exp in (('development', 'exp501'), ('robustness', 'exp562')):
        reference = read(f'../exp589/validation/results/exp589/{case}-report.json')['evidence']
        request = Path(f'../{exp}/build/{exp}/u-role/requests.csv')
        exact = Path(f'../{exp}/build/{exp}/exact.csv')
        check(request, reference['D64']['input'])
        check(exact, reference['D64']['labels'])
        baseline_csv = Path('../exp589') / reference['D64']['output']['path']
        check(baseline_csv, reference['D64']['output'])
        baseline, truth, _, partitions = old.complete.check_output(request, baseline_csv, exact)
        predictions = {'A': baseline}
        for arm in ARMS[1:]:
            prior_csv = Path('../exp589') / reference[arm]['output']['path']
            check(prior_csv, reference[arm]['output'])
            predictions[arm], other_truth, _, _ = old.complete.check_output(request, prior_csv, exact,
                Path(f'../exp589/build/exp589/{case}-{arm}-prediction.i32'))
            assert np.array_equal(other_truth, truth)
        schedule = [ARMS, *([ARMS, ARMS[::-1]] * 3)]
        write(ROOT / (case + '-timing-freeze.json'), dict(schedule=schedule,
            input=reference['D64']['input'], labels=reference['D64']['labels'],
            reference=reference, candidate_freeze=identity(ROOT / 'build-freeze.json')))
        timing, runs = {arm: [] for arm in ARMS}, []
        for iteration, order in enumerate(schedule):
            for arm in order:
                output = BUILD / f'{case}-{iteration}-{arm}.csv'
                run = speed.measured([str(binary(arm)), '-in', str(request), '-out', str(output)], output.stem)
                actual, counters = identity(output), read(run['stderr'])
                expected = reference['D64' if arm == 'A' else arm]['output']
                assert all(actual[k] == expected[k] for k in ('bytes', 'sha256'))
                assert run['threads'] == 1 and run['rss_bytes'] <= 2000000000 and run['cpu_s'] <= 3600
                assert counters['rows'] == 1000000 and counters['query_allocations'] == 0
                run.update(arm=arm, iteration=iteration, output=actual, identical_to=expected, counters=counters)
                write(ROOT / (output.stem + '-evidence.json'), run)
                output.unlink()
                runs.append(run)
                if iteration:
                    timing[arm].append(run['cpu_s'])
                print('EXP603_RUN', case, iteration, arm, run['cpu_s'], flush=True)
        comparisons = {arm: compare(predictions[arm], baseline, truth, partitions,
            [a-b for a, b in zip(timing[arm], timing['A'])]) for arm in ARMS[1:]}
        results[case] = dict(timing=timing, runs=runs, comparisons=comparisons, rows=1000000,
            unique_rows=1000000, port_pairs=59904, reused_accuracy_evidence=reference)
        write(ROOT / (case + '-report.json'), results[case])
    eligible = [a for a in ARMS[1:] if all(r['comparisons'][a]['quality_gate'] and
        r['comparisons'][a]['score_gate'] for r in results.values())]
    selected = None
    if eligible:
        scores = {a: min(r['comparisons'][a]['score_extrapolated_1b'] for r in results.values()) for a in eligible}
        tied = [a for a in eligible if scores[a] >= max(scores.values()) - .005]
        selected = min(tied, key=lambda a: sum(statistics.mean(r['timing'][a]) for r in results.values()))
    write(ROOT / 'report.json', dict(cases=results, eligible=eligible, selected=selected,
        all_outputs_identical_to_frozen_models=True, fresh_distribution_verified=False,
        disk_end_bytes=shutil.disk_usage('.').free))
    print('EXP603_SELECTED', selected, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp603')
    assert sys.argv[1:] in (['build'], ['audit'], ['qualify'])
    {'build': build, 'audit': audit, 'qualify': qualify}[sys.argv[1]]()
