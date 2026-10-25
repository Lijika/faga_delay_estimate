#!/usr/bin/env python3
"""Check the complete exp685 evidence and reconstruct its registered decision."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

ROOT = Path('validation/results/exp685')
ARMS = ('A', 'V8', 'HV8')


def read(path):
    return json.loads(Path(path).read_text())


def close(actual, expected, tolerance=1e-9):
    assert math.isfinite(actual) and math.isfinite(expected)
    assert abs(actual-expected) <= tolerance, (actual, expected)


def main():
    frozen = read(ROOT/'freeze.json')
    timing = read(ROOT/'100m-report.json')
    labels = read(ROOT/'expanded/report.json')
    inputs = read(ROOT/'expanded/input.json')
    score = read(ROOT/'score/accuracy.json')
    full = read(ROOT/'unchanged-events.json')
    assert labels['all_complete_label_checks'] and labels['span_checks'] == 12
    assert labels['rows'] == labels['unique_rows'] == score['sample_rows'] == 1_916_928
    assert inputs['training_request_overlap'] == inputs['training_source_pin_overlap'] == 0
    assert inputs['old_sample_overlap'] == 0
    assert len(labels['runs']) == 4 and all(r['exit_code'] == 0 for r in labels['runs'])
    assert sum(r['cpu_s'] for r in labels['runs']) <= 10_000
    assert max(r['rss_bytes'] for r in labels['runs']) <= 2_000_000_000
    counts = inputs['coverage']['port_pair_counts']
    assert len(counts) == 208 and all(len(row) == 288 and set(row) == {32} for row in counts)
    assert timing['rows'] == timing['unique_rows'] == full['rows'] == 100_000_000
    assert timing['port_pairs'] == score['port_pairs'] == 59904
    assert full['unchanged_event_mismatches'] == {'V8':0, 'HV8':0}
    assert sum(full['event_counts']) == 100_000_000
    schedule = [ARMS, *itertools.permutations(ARMS)]
    assert frozen['schedule'] == [list(v) for v in schedule]
    assert len(timing['runs']) == 21 and len(timing['deleted_duplicates']) == 18
    for index, run in enumerate(timing['runs']):
        iteration, slot = divmod(index, 3)
        arm = schedule[iteration][slot]
        assert run['arm'] == arm and run['iteration'] == iteration
        assert run['command'][0] == frozen['binaries'][arm]['path']
        assert run['exit_code'] == 0 and run['threads'] == 1
        assert run['rss_bytes'] <= 2_000_000_000 and run['wall_s'] <= 3600 and run['cpu_s'] < 100
        assert run['counters'] == dict(rows=100_000_000,unreachable=0,query_allocations=0)
        assert run['input'] == timing['input']
        assert run['output']['sha256'] == timing['evidence'][arm]['output']['sha256']
        if iteration:
            close(run['cpu_s'],timing['timing'][arm][iteration-1])
    for arm in ARMS:
        assert len(timing['timing'][arm]) == 6
        evidence = timing['evidence'][arm]
        assert evidence['contract']['contract_passed']
        assert evidence['contract']['rows'] == 100_000_000
        assert evidence['contract']['sample_rows'] == 1_916_928
        assert score['evidence'][arm]['source_run'] == evidence['run']
        assert score['evidence'][arm]['source_output'] == evidence['output']
    for item in timing['deleted_duplicates']:
        assert all(item['file'][k] == item['identical_to'][k] for k in ('bytes','sha256'))
    assert timing['released_bytes'] == sum(v['file']['bytes'] for v in timing['deleted_duplicates'])
    for groups in score['groups'].values():
        assert sum(v['sample_rows'] for v in groups.values()) == 1_916_928
        mass = math.fsum(v['estimated_population_rows'] for v in groups.values())
        close(mass,100_000_000,1e-6)
        for arm in ARMS:
            mean = math.fsum(v['estimated_population_rows']*v['accuracy_pp'][arm] for v in groups.values())/mass
            close(mean,score['accuracy'][arm]['point_pp'])
    passed = []
    for arm in ARMS[1:]:
        item = score['comparisons'][arm]
        delta = score['accuracy'][arm]['point_pp']-score['accuracy']['A']['point_pp']
        close(delta,item['delta_accuracy']['point_pp'])
        estimate = item['delta_accuracy']
        bounds = estimate['conservative_ci9875_pp']
        close(bounds[0],min(estimate['stratified_ci9875_pp'][0],estimate['family_ci9875_pp'][0]))
        close(bounds[1],max(estimate['stratified_ci9875_pp'][1],estimate['family_ci9875_pp'][1]))
        saved = [a-b for a,b in zip(timing['timing']['A'],timing['timing'][arm])]
        close(statistics.mean(saved),item['saved_cpu_s'])
        close(.8*delta+statistics.mean(saved)/12,item['score_extrapolated_1b'])
        close(.8*bounds[0]+item['ci9875_saved_cpu_s'][0]/12,item['conservative_ci95_score_lower'])
        events = (2,) if arm == 'V8' else (1,2)
        quality = delta >= .01 and bounds[0] > 0 and all(
            v['accuracy_pp'][arm]-v['accuracy_pp']['A'] >= -.03
            for name in ('distance','direction','near_axis') for v in score['groups'][name].values())
        quality = quality and all(score['groups']['event'][str(e)]['accuracy_pp'][arm] >=
                                  score['groups']['event'][str(e)]['accuracy_pp']['A'] for e in events)
        assert item['quality_gate'] == quality
        gate = quality and item['score_extrapolated_1b'] >= .005 and item['conservative_ci95_score_lower'] > 0
        assert item['joint_gate'] == gate
        if gate:
            passed.append(arm)
    selected = min(passed,key=lambda a:(-score['comparisons'][a]['conservative_ci95_score_lower'],
                    statistics.mean(timing['timing'][a]),a)) if passed else None
    assert score['selected'] == selected
    for name in ('exp685_event_data.py','exp685_data_run.sh','exp685_event_scale.py','exp685_scale_run.sh'):
        records = frozen['files']+read(ROOT/'timing-freeze.json')['files']
        expected, = [v for v in records if Path(v['path']).name == name]
        assert hashlib.sha256((Path('validation')/name).read_bytes()).hexdigest() == expected['sha256']
    result = dict(all_evidence_checks_passed=True,selected=selected,
        complete_100m_runs=21,distinct_binaries=3,identical_output_runs_per_arm=7,
        exact_sample_rows=1_916_928,group_partitions=len(score['groups']),
        label_cpu_s=sum(r['cpu_s'] for r in labels['runs']),
        mean_cpu_s={a:statistics.mean(timing['timing'][a]) for a in ARMS},
        accuracy_pp={a:score['accuracy'][a]['point_pp'] for a in ARMS},
        comparisons=score['comparisons'],complete_1b_runs=0,
        final_accuracy_goal_verified=False,platform_verified=False)
    with (ROOT/'close-audit-local.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print('EXP685_EVIDENCE_CHECKED',selected,result['mean_cpu_s'],result['accuracy_pp'])


if __name__ == '__main__':
    main()
