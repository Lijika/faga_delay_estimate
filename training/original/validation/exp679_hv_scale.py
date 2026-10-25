#!/usr/bin/env python3
"""Validate the fixed HV64 deployment on one fresh complete 100M."""
import csv
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

import exp679_hv_cli as cli
sys.path.insert(0, str(Path('../exp652/validation').resolve()))
import exp652_curve_scale as prior

ROOT, BUILD, PLAN = cli.ROOT, cli.BUILD, cli.PLAN
ROWS, SAMPLES, SEED = prior.ROWS, prior.SAMPLES, 20261024679
ARMS, BINARIES = prior.ARMS, {'A': cli.BASELINE, 'C': BUILD/'C'}
read, write, identity, check = cli.read, cli.write, cli.identity, cli.check
fresh, labels, speed = prior.fresh, prior.labels, prior.speed
prior.ROOT, prior.BUILD, prior.PLAN, prior.cli = ROOT, BUILD, PLAN, cli
prior.BINARIES, prior.SEED = BINARIES, SEED
fresh.ROOT, fresh.BUILD, fresh.PLAN = ROOT, BUILD, PLAN
fresh.ROWS, fresh.SEED = ROWS, SEED
labels.ROOT, labels.BUILD, labels.PLAN = ROOT, BUILD, PLAN
labels.ROWS, labels.TOOLS = SAMPLES, BUILD/'tools'
speed.ROOT = ROOT


def quality_gate(point, lower, partitions, ordinary_equal):
    return bool(point >= .01 and lower > 0 and ordinary_equal and all(
        group['delta_accuracy_pp'] >= -.03
        for key in ('distance', 'near_axis', 'direction')
        for group in partitions[key].values()) and all(
        partitions['event'][str(event)]['delta_accuracy_pp'] >= 0 for event in (1, 2)))


def self_check():
    prior.self_check()
    groups = {key: {'0': dict(delta_accuracy_pp=0.)}
              for key in ('distance', 'near_axis', 'direction')}
    groups['event'] = {str(i): dict(delta_accuracy_pp=0.) for i in range(3)}
    assert quality_gate(.01, .001, groups, True)
    assert not quality_gate(.009, .001, groups, True)
    assert not quality_gate(.01, 0., groups, True)
    assert not quality_gate(.01, .001, groups, False)
    groups['event']['2']['delta_accuracy_pp'] = -.00001
    assert not quality_gate(.01, .001, groups, True)
    groups['event']['2']['delta_accuracy_pp'] = 0.
    groups['near_axis']['0']['delta_accuracy_pp'] = -.03001
    assert not quality_gate(.01, .001, groups, True)


def prepare():
    self_check()
    frozen = cli.freeze_check()
    assert read(ROOT/'numeric-audit.json')['final_prediction_equal']
    assert not (ROOT/'freeze.json').exists()
    prepare_events()
    history = [Path(r['path']) for r in
               read('../exp652/validation/results/exp652/freeze.json')['history']]
    history += [Path('../exp652/build/exp652/sample-requests.csv'),
                Path('../exp655/build/exp655/1b-sample.csv'),
                Path('../exp663/build/exp663/sample-requests.csv')]
    assert len(history) == len(set(history))
    tools = read('../exp501/validation/results/exp501/freeze.json')['expected_tools']
    for item in tools:
        check(Path('../..')/item['path'], item)
    for tool in (prior.HIDDEN/'make_hidden_suite', prior.HIDDEN/'check_hidden_suite',
                 Path('../../build/exp203/exact_labels'), prior.CHECKER):
        result = subprocess.run([str(tool), '--help'], capture_output=True, text=True)
        text = result.stdout+result.stderr
        assert 'usage' in text.lower()
        (ROOT/(tool.name+'-help.txt')).write_text(text)
    files = [Path(__file__), Path(prior.__file__), Path(fresh.__file__), Path(labels.__file__),
        Path(speed.__file__), PLAN, ROOT/'protocol-original.md', ROOT/'build-freeze.json',
        ROOT/'numeric-audit.json', Path('../exp663/validation/exp663_sample_groups.cpp'),
        Path('tests/exp679_hv_events.h'),
        BUILD/'sample-events.cpp', BUILD/'sample-events', ROOT/'event-self-check.json',
        Path('../exp624/validation/exp624_fresh_leaf_validation.py'),
        Path('../exp575/offline/validation/results/exp575/mapping.json'),
        prior.HIDDEN/'reach.bin', prior.HIDDEN/'independent/eligibility.bin',
        *Path('doc/eda比赛文件/arch').glob('*.json')]
    assert len(list(Path('doc/eda比赛文件/arch').glob('*.json'))) == 5
    assert shutil.disk_usage('.').free > 22_000_000_000
    write(ROOT/'freeze.json', dict(files=[identity(p) for p in files],
        binaries=frozen['binaries'], checker=identity(prior.CHECKER), rows=ROWS,
        sample_rows=SAMPLES, proposal_rows=120_000_000,
        proposal_seed=20261025679, shuffle_seed=20261026679, expected_tools=tools,
        history=[identity(p) for p in history], source_ports=labels.roles()[0],
        target_ports=labels.roles()[1], required_port_pairs=59904,
        sample_rule='first four per port pair after independent shuffle and filtering',
        schedule=[ARMS, *([ARMS, ARMS[::-1]]*3)], seed=SEED, untouched_scores=True,
        cpu_label_budget_s=5000, disk_free_start_bytes=shutil.disk_usage('.').free))
    print('EXP679_FRESH_100M_FROZEN', flush=True)


def prepare_events():
    source = Path('../exp663/validation/exp663_sample_groups.cpp')
    text = cli.replace(source.read_text(), '#include "architecture.h"',
                       '#include "architecture.h"\n#include "exp679_hv_events.h"')
    text = cli.replace(text,
        'require(std::fwrite(&forced, 1, 1, output) == 1, "write flag");',
        'int bands, ends;\n'
        '        const unsigned char event = event679(ax, ay, tx, ty, forced, bands, ends);\n'
        '        require(std::fwrite(&event, 1, 1, output) == 1, "write flag");')
    path, binary = BUILD/'sample-events.cpp', BUILD/'sample-events'
    path.write_text(text)
    command = ['g++', '-std=c++17', '-O3', '-march=x86-64', '-mtune=generic',
        '-Wall', '-Wextra', '-Werror', '-DDELAY_ESTIMATE_EMBEDDED_ARCH',
        '-DDELAY_ESTIMATE_PRECOMPUTED_RESIDUE', '-I', '../exp589/src', '-I', 'tests',
        str(path), '../exp580/build/exp580/architecture-resolver.o',
        '../exp579/build/exp579/arch-text.o', '-static', '-s', '-o', str(binary)]
    speed.measured(command, 'compile-sample-events')
    assert not (ROOT/'compile-sample-events.stderr').read_bytes()
    assert 'usage:' in subprocess.check_output([str(binary), '--help'], text=True)
    mapping = read('../exp575/offline/validation/results/exp575/mapping.json')
    names = dict(zip(mapping['source_ids'], mapping['sources']))
    names.update(zip(mapping['target_ids'], mapping['targets']))
    features = np.memmap('../exp631/build/exp631/features.f32', '<f4', 'r',
                         offset=16, shape=(1_000_000, 53))
    gap = read('doc/eda比赛文件/arch/SRB_Gap.json')['Gap']
    h, v, _, _ = cli.fit.prior.events(features[:, 28:32], gap['Block'])
    expected = h.astype('u1')+2*v
    rng = np.random.default_rng(SEED)
    ids = np.concatenate([rng.choice(np.flatnonzero(expected == i), 256, replace=False)
                          for i in range(3)])
    queries = np.memmap('../exp579/build/exp579/queries.bin', '<i4', 'r',
                        offset=12, shape=(1_000_000, 10))
    toy = BUILD/'event-check.csv'
    with toy.open('x') as stream:
        stream.write('From,To\n')
        for sx, sy, tx, ty, _, _, _, _, sp, tp in queries[ids]:
            stream.write(f'SRB_{sx}_{sy}/{names[sp]},SRB_{tx}_{ty}/{names[tp]}\n')
    speed.measured([str(binary), str(toy), str(BUILD/'event-check.u8')], 'event-self-check')
    assert np.array_equal(np.fromfile(BUILD/'event-check.u8', 'u1'), expected[ids])
    write(ROOT/'event-self-check.json', dict(binary=identity(binary), source=identity(path),
        input=identity(toy), output=identity(BUILD/'event-check.u8'), cached_rows=768,
        per_event=256, first_net_resolution=True))


def dataset():
    prior.dataset()
    binary = BUILD/'sample-events'
    output = BUILD/'sample-events.u8'
    speed.measured([str(binary), str(BUILD/'sample-requests.csv'), str(output)], 'sample-events')
    assert read(ROOT/'sample-events.stdout')['rows'] == SAMPLES
    values = np.fromfile(output, 'u1')
    assert len(values) == SAMPLES and np.isin(values, [0, 1, 2]).all()
    assert np.bincount(values, minlength=3).min() >= 50
    write(ROOT/'sample-events.json', dict(asset=identity(output), binary=identity(binary),
        source=identity(BUILD/'sample-events.cpp'),
        original_source=identity('../exp663/validation/exp663_sample_groups.cpp'),
        counts=np.bincount(values, minlength=3).tolist(), cached_self_check_rows=768,
        cached_self_check_per_event=256, first_net_resolution=True))


def qualify():
    self_check()
    frozen = fresh.freeze_check()
    data = read(ROOT/'100m-input.json')
    request = BUILD/'u-role/requests.csv'
    check(request, data['input'])
    check(prior.CHECKER, frozen['checker'])
    cli.freeze_check()
    positions, requests, truth, pair, groups, population = fresh.sample_labels()
    flags = read(ROOT/'sample-events.json')
    check(flags['asset']['path'], flags['asset'])
    groups['event'] = np.fromfile(flags['asset']['path'], 'u1')
    assert len(groups['event']) == SAMPLES
    weights = population[pair]/4
    write(ROOT/'timing-freeze.json', dict(schedule=frozen['schedule'], input=data['input'],
        labels=identity(BUILD/'exact.csv'), binaries=frozen['binaries'], driver=identity(__file__),
        seed=SEED, bootstrap_count=9999, minimum_score=.005, minimum_accuracy_pp=.01,
        rows=ROWS, sample_rows=SAMPLES, no_new_candidate_selection=True))
    timing, predictions, evidence, runs, deleted = {a: [] for a in ARMS}, {}, {}, [], []
    for iteration, order in enumerate(frozen['schedule']):
        for arm in order:
            output = BUILD/f'100m-{iteration}-{arm}.csv'
            assert not output.exists()
            assert shutil.disk_usage('.').free > 5_100_000_000
            command = [str(BINARIES[arm]), '-in', str(request), '-out', str(output)]
            run = speed.measured(command, output.stem)
            actual, counters = identity(output), read(run['stderr'])
            assert run['threads'] == 1 and run['rss_bytes'] <= 2_000_000_000
            assert run['cpu_s'] < 100 and run['wall_s'] <= 3600
            assert counters == dict(rows=ROWS, unreachable=0, query_allocations=0)
            if iteration == 0:
                sample = BUILD/f'{arm}-sample.csv'
                contract_run = speed.measured([str(prior.CHECKER), 'check', str(request),
                    str(output), str(ROWS), str(BUILD/'positions.txt'), str(sample)], arm+'-contract')
                contract = read(ROOT/(arm+'-contract.stdout'))
                assert contract['contract_passed'] and contract['rows'] == ROWS
                assert contract['sample_rows'] == SAMPLES
                values = []
                with sample.open(newline='') as stream:
                    reader = csv.reader(stream)
                    assert next(reader) == ['row', 'From', 'To', 'delay']
                    for i, row in enumerate(reader):
                        assert len(row) == 4 and int(row[0]) == positions[i]
                        assert tuple(row[1:3]) == requests[i] and row[3] == str(int(row[3]))
                        values.append(int(row[3]))
                assert len(values) == SAMPLES and min(values) >= 0
                predictions[arm] = np.asarray(values)
                evidence[arm] = dict(output=actual, sample=identity(sample), run=run,
                    contract=contract, contract_run=contract_run)
            assert all(actual[k] == evidence[arm]['output'][k] for k in ('bytes', 'sha256'))
            run.update(arm=arm, iteration=iteration, output=actual, input=data['input'], counters=counters)
            write(ROOT/(output.stem+'-evidence.json'), run)
            runs.append(run)
            if iteration:
                timing[arm].append(run['cpu_s'])
                deletion = dict(file=actual, identical_to=evidence[arm]['output'], rebuild_command=command)
                write(ROOT/(output.stem+'-cleanup.json'), deletion)
                print('EXP679_REMOVE_DUPLICATE', output, actual['sha256'], flush=True)
                output.unlink()
                deleted.append(deletion)
            print('EXP679_TIMING', iteration, arm, run['cpu_s'], flush=True)
    started, cpu = time.monotonic(), time.process_time()
    scores = {a: fresh.points(predictions[a], truth) for a in ARMS}
    delta = scores['C']-scores['A']
    interval = fresh.accuracy_interval(delta, pair, groups['source_family'], population)
    comparison = prior.joint(interval['point_pp'], interval['conservative_ci975_pp'][0],
                             np.asarray(timing['A'])-timing['C'])
    partitions = {key: {str(int(v)): dict(sample_rows=int((values == v).sum()),
        source_families=len(np.unique(groups['source_family'][values == v])),
        estimated_population_rows=float(weights[values == v].sum()),
        delta_accuracy_pp=float(np.average(delta[values == v], weights=weights[values == v])),
        accuracy_pp={a: float(np.average(scores[a][values == v], weights=weights[values == v]))
                     for a in ARMS}) for v in np.unique(values)} for key, values in groups.items()}
    for event in (1, 2):
        mask = groups['event'] == event
        masses = np.bincount(groups['source_family'][mask], weights=weights[mask], minlength=26)
        totals = np.bincount(groups['source_family'][mask],
                            weights=weights[mask]*delta[mask], minlength=26)
        chosen = np.random.default_rng(SEED).integers(26, size=(9999, 26))
        assert masses[chosen].sum(axis=1).min() > 0
        partitions['event'][str(event)]['source_family_ci95_pp'] = np.quantile(
            totals[chosen].sum(axis=1)/masses[chosen].sum(axis=1), [.025, .975]).tolist()
    ordinary = groups['event'] == 0
    ordinary_equal = bool(np.array_equal(predictions['A'][ordinary], predictions['C'][ordinary]))
    quality = quality_gate(interval['point_pp'], interval['conservative_ci975_pp'][0],
                           partitions, ordinary_equal)
    errors = {a: np.abs(predictions[a]-truth) for a in ARMS}
    comparison.update(delta_accuracy_pp=interval['point_pp'], accuracy_interval=interval,
        quality_gate=quality, joint_gate=quality and comparison['score_gate'], groups=partitions,
        ordinary_sample_predictions_equal=ordinary_equal,
        changed_sample_rows=int(np.count_nonzero(predictions['A'] != predictions['C'])),
        improved_sample_rows=int(np.count_nonzero(errors['C'] < errors['A'])),
        worse_sample_rows=int(np.count_nonzero(errors['C'] > errors['A'])))
    summary = {a: dict(accuracy=fresh.accuracy_interval(scores[a], pair,
        groups['source_family'], population), mae_ps=float(np.average(errors[a], weights=weights)),
        exact_fraction=float(np.average(errors[a] == 0, weights=weights))) for a in ARMS}
    write(ROOT/'100m-report.json', dict(comparison=comparison, summary=summary, timing=timing,
        runs=runs, evidence=evidence, rows=ROWS, unique_rows=ROWS, port_pairs=59904,
        sample_rows=SAMPLES, source_pin_overlap=0, registered_history_overlap=0,
        heldout_used_for_selection=False, full_population_scored=False, cpu_1b_is_extrapolation=True,
        final_accuracy_goal_verified=False, zero_truth_sample_rows=int(np.count_nonzero(truth == 0)),
        scoring_cpu_s=time.process_time()-cpu, scoring_wall_s=time.monotonic()-started,
        deleted_duplicates=deleted, released_bytes=sum(v['file']['bytes'] for v in deleted),
        disk_free_end_bytes=shutil.disk_usage('.').free))
    print('EXP679_100M_RESULT', comparison['delta_accuracy_pp'], comparison['saved_cpu_s'],
          comparison['joint_gate'], flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp679')
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert len(sys.argv) == 2 and sys.argv[1] in ('self-check', 'prepare', 'dataset', 'labels', 'qualify')
    {'self-check': self_check, 'prepare': prepare, 'dataset': dataset,
     'labels': prior.compute_labels, 'qualify': qualify}[sys.argv[1]]()
