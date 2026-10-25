#!/usr/bin/env python3
"""Screen the frozen symmetric budgets using paired complete-program CPU."""
import math
from pathlib import Path
import shutil
import socket
import statistics
import sys

import numpy as np
from scipy import stats

import exp640_symmetric_cli as cli

ROOT, BUILD = cli.ROOT, cli.BUILD
read, write, identity, checked = cli.read, cli.write, cli.identity, cli.checked
ARMS = ('A', 'S8', 'S16')


def joint(delta, accuracy_lower, saved):
    assert len(saved) == 12 and np.isfinite(saved).all()
    mean = float(np.mean(saved))
    critical = float(stats.t.ppf(1 - .05 / 8, 11))
    half = critical * statistics.stdev(saved) / math.sqrt(12)
    point = .8 * delta + mean * 1000 / 120
    lower = .8 * accuracy_lower + (mean - half) * 1000 / 120
    return dict(saved_cpu_s=mean, simultaneous_ci_saved_s=[mean-half, mean+half],
        delta_accuracy_oof_pp=delta, oof_accuracy_lower_pp=accuracy_lower,
        score_screen_extrapolated_1b=point, conservative_score_lower=lower,
        screen_gate=bool(point >= .005 and lower > 0),
        cpu_scale_assumption='1M complete CPU difference times 1000, including initialization',
        independent_joint_confirmation_pending=True)


def main():
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp640')
    assert not (ROOT / 'timing-screen-freeze.json').exists()
    assert joint(0., 0., np.full(12, .002))['screen_gate']
    assert not joint(0., 0., np.zeros(12))['screen_gate']
    freeze = read(ROOT / 'cli-freeze.json')
    evaluation = read(ROOT / 'evaluation.json')
    binaries = {a: Path(freeze['binaries'][a]['path']) for a in ARMS}
    for a in ARMS:
        checked(binaries[a], freeze['binaries'][a])
    request = Path('../exp501/build/exp501/u-role/requests.csv')
    exact = Path('../exp501/build/exp501/exact.csv')
    previous = read('../exp622/validation/results/exp622/1m-report.json')['evidence']['T']
    checked(request, previous['input'])
    expected = {'A': previous['output']}
    expected.update({a: freeze['audits'][a]['development'] for a in ARMS[1:]})
    schedule = [ARMS] + [ARMS if i % 2 == 0 else ARMS[::-1] for i in range(12)]
    write(ROOT / 'timing-screen-freeze.json', dict(schedule=schedule,
        binaries=freeze['binaries'], input=identity(request), labels=identity(exact),
        development_training_outputs=True, model_selection_uses_oof=True,
        accuracy_evidence=identity(ROOT / 'evaluation.json'),
        protocol=identity(ROOT / 'cli-timing-protocol.md'), driver=identity(__file__),
        interval='Bonferroni: two arms and two components; t CPU, frozen OOF family bootstrap',
        selection='highest eligible OOF+CPU score point, tie S8; fresh source-pin confirmation',
        minimum_score=.005, disk_free_start=shutil.disk_usage('.').free))
    timing, runs, evidence, removed = {a: [] for a in ARMS}, [], {}, []
    predictions, truth, partitions = {}, None, None
    for iteration, order in enumerate(schedule):
        for a in order:
            output = BUILD / f'timing-screen-{iteration}-{a}.csv'
            command = [str(binaries[a]), '-in', str(request), '-out', str(output)]
            run = cli.speed.measured(command, output.stem)
            current = identity(output)
            assert all(current[k] == expected[a][k] for k in ('bytes', 'sha256'))
            assert read(run['stderr']) == dict(rows=1_000_000, unreachable=0, query_allocations=0)
            assert run['threads'] == 1 and run['rss_bytes'] <= 2_000_000_000 and run['cpu_s'] <= 3600
            run.update(arm=a, iteration=iteration, output=current)
            if iteration == 0:
                p, t, contract, groups = cli.old.prior.complete.check_output(request, output, exact)
                if truth is not None:
                    assert np.array_equal(t, truth)
                predictions[a], truth, partitions = p, t, groups
                evidence[a] = dict(run=run, contract=contract,
                    accuracy_scope='same-run development training output; no generalization claim')
            else:
                timing[a].append(run['cpu_s'])
                removed.append(dict(file=current, identical_to=evidence[a]['run']['output'],
                                    rebuild_command=command))
                print('EXP640_REMOVE_DUPLICATE', current['path'], current['sha256'], flush=True)
                output.unlink()
            write(ROOT / (output.stem + '-evidence.json'), run)
            runs.append(run)
            print('EXP640_TIMING', iteration, a, run['cpu_s'], flush=True)
    comparisons = {}
    for a in ARMS[1:]:
        quality = evaluation['reports'][a + '-A']
        result = joint(quality['delta_accuracy_pp'], quality['simultaneous_ci_delta_pp'][0],
                       np.asarray(timing['A']) - timing[a])
        result['same_run_training_transition'] = cli.fit.prior.transition(
            predictions[a], predictions['A'], truth, partitions)
        comparisons[a] = result
    eligible = [a for a in ARMS[1:] if comparisons[a]['screen_gate']]
    selected = max(eligible, key=lambda a: comparisons[a]['score_screen_extrapolated_1b']) if eligible else 'A'
    write(ROOT / 'timing-screen-report.json', dict(selected=selected, comparisons=comparisons,
        timing=timing, runs=runs, evidence=evidence, removed_duplicates=removed,
        released_bytes=sum(v['file']['bytes'] for v in removed),
        disk_free_end=shutil.disk_usage('.').free, final_accuracy_goal_verified=False,
        independent_joint_confirmation_pending=bool(eligible)))
    print('EXP640_SCREEN_RESULT', selected, comparisons, flush=True)


if __name__ == '__main__':
    main()
