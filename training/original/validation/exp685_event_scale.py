#!/usr/bin/env python3
"""Time the three frozen estimators, then score the same complete outputs."""
import inspect
import io
import math
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

import numpy as np
from scipy import stats

import exp685_event_data as data
import exp683_expanded_score as scoring

ROOT, BUILD, ARMS = data.ROOT, data.BUILD, data.ARMS
read, write, identity, check = data.read, data.write, data.identity, data.check


def interval(values, pair, family, population, seed):
    point, variance = scoring.design(values, pair, population)
    count = np.bincount(pair, minlength=len(population))
    weights = population[pair]/count[pair]
    mass = np.bincount(family, weights=weights, minlength=26)
    totals = np.bincount(family, weights=weights*values, minlength=26)
    assert mass.min() > 0
    draws = np.random.default_rng(seed).integers(26, size=(9999,26))
    family_ci = np.quantile(totals[draws].sum(axis=1)/mass[draws].sum(axis=1),
                            [.00625,.99375]).tolist()
    half = float(stats.norm.ppf(.99375))*math.sqrt(variance)
    design_ci = [point-half, point+half]
    return dict(point_pp=point, stratified_variance_pp2=variance,
        stratified_ci9875_pp=design_ci, family_ci9875_pp=family_ci,
        conservative_ci9875_pp=[min(design_ci[0],family_ci[0]), max(design_ci[1],family_ci[1])])


def joint(delta, lower, saved):
    assert len(saved) == 6 and np.isfinite(saved).all()
    mean = float(np.mean(saved))
    half = float(stats.t.ppf(.99375,5))*statistics.stdev(saved)/math.sqrt(6)
    point, bound = .8*delta+mean/12, .8*lower+(mean-half)/12
    return dict(saved_cpu_s=mean, ci9875_saved_cpu_s=[mean-half,mean+half],
        score_extrapolated_1b=point, conservative_ci95_score_lower=bound,
        score_gate=bool(point >= .005 and bound > 0))


def quality(arm, delta, lower, partitions, equal):
    events = (2,) if arm == 'V8' else (1,2)
    return bool(delta >= .01 and lower > 0 and equal and all(
        row['accuracy_pp'][arm]-row['accuracy_pp']['A'] >= -.03
        for key in ('distance','near_axis','direction') for row in partitions[key].values())
        and all(partitions['event'][str(e)]['accuracy_pp'][arm] >=
                partitions['event'][str(e)]['accuracy_pp']['A'] for e in events))


def selection(comparisons, timing):
    passed = [a for a in ARMS[1:] if comparisons[a]['joint_gate']]
    return min(passed, key=lambda a: (-comparisons[a]['conservative_ci95_score_lower'],
               float(np.mean(timing[a])), a)) if passed else None


def comparisons(scores, predictions, errors, pair, family, population, groups, partitions, timing):
    full = read(ROOT/'unchanged-events.json')
    result = {}
    for arm in ARMS[1:]:
        estimate = interval(scores[arm]-scores['A'],pair,family,population,data.SEED)
        lower = estimate['conservative_ci9875_pp'][0]
        outside = groups['event'] != 2 if arm == 'V8' else groups['event'] == 0
        equal = bool(np.array_equal(predictions[arm][outside],predictions['A'][outside]))
        equal = equal and full['unchanged_event_mismatches'][arm] == 0
        gate = quality(arm,estimate['point_pp'],lower,partitions,equal)
        value = joint(estimate['point_pp'],lower,np.asarray(timing['A'])-timing[arm])
        value.update(delta_accuracy=estimate,quality_gate=gate,joint_gate=gate and value['score_gate'],
            unchanged_event_outputs_equal=equal,
            changed_sample_rows=int(np.count_nonzero(predictions[arm] != predictions['A'])),
            improved_sample_rows=int(np.count_nonzero(errors[arm] < errors['A'])),
            worse_sample_rows=int(np.count_nonzero(errors[arm] > errors['A'])),
            group_delta_accuracy_pp={key:{v:r['accuracy_pp'][arm]-r['accuracy_pp']['A']
                for v,r in entries.items()} for key,entries in partitions.items()})
        result[arm] = value
    return result


def adapted_score():
    text = inspect.getsource(scoring.main)
    start = text.index("    if set(scores) == {'A','C'}:")
    stop = text.index("    write(root/'accuracy.json',result)",start)
    text = text[:start]+text[stop:]
    changes = [
        ("base = Path('validation/results/exp683')/case", f"base = Path('{ROOT/'expanded'}')"),
        ("build = Path('build/exp683')/case", f"build = Path('{BUILD/'expanded'}')"),
        ("root = base/('score-'+report_path.parent.name)", f"root = Path('{ROOT/'score'}')"),
        ("EXP683_EXPANDED_ACCURACY", "EXP685_EXPANDED_ACCURACY"),
        ("write(root/'accuracy.json',result)",
         "result['comparisons'] = comparisons(scores,predictions,errors,pair,family,population,\n"
         "        groups,partitions,report['timing'])\n"
         "    result['selected'] = selection(result['comparisons'],report['timing'])\n"
         "    result['heldout_used_for_selection'] = True\n"
         "    write(root/'accuracy.json',result)"),
    ]
    for before, after in changes:
        assert text.count(before) == 1, before
        text = text.replace(before,after)
    compile(text,'exp685-score.py','exec')
    return text


def compare_events(event_stream, streams, wanted):
    counts, changes = [0]*3, {a:[0]*3 for a in ARMS[1:]}
    assert all(f.readline() == b'From,To,delay\n' for f in streams)
    i = 0
    for block in iter(lambda:event_stream.read(1<<20),b''):
        for event in block:
            assert 0 <= event <= 2
            rows = [f.readline() for f in streams]
            assert all(rows)
            counts[event] += 1
            for arm,row in zip(ARMS[1:],rows[1:]):
                changes[arm][event] += row != rows[0]
            i += 1
    assert i == wanted and all(f.read(1) == b'' for f in streams)
    return dict(rows=i,event_counts=counts,changed_rows=changes,
        unchanged_event_mismatches=dict(V8=sum(changes['V8'][:2]),HV8=changes['HV8'][0]))


def self_check():
    scoring.self_check()
    assert joint(.02,.015,np.zeros(6))['score_gate']
    assert not joint(.02,.015,np.full(6,-.5))['score_gate']
    partitions = {k:{'0':dict(accuracy_pp=dict(A=99.,V8=99.,HV8=99.))}
                  for k in ('distance','near_axis','direction')}
    partitions['event'] = {str(i):dict(accuracy_pp=dict(A=99.,V8=99.,HV8=99.)) for i in range(3)}
    assert quality('V8',.01,.001,partitions,True)
    assert not quality('V8',.01,.001,partitions,False)
    partitions['event']['1']['accuracy_pp']['HV8'] = 98.999
    assert not quality('HV8',.01,.001,partitions,True)
    assert quality('V8',.01,.001,partitions,True)
    family = pair = np.repeat(np.arange(26),2)
    estimate = interval(np.full(52,.25),pair,family,np.full(26,10),1)
    assert all(abs(v-.25) < 1e-14 for v in estimate['conservative_ci9875_pp'])
    choices = {a:dict(joint_gate=True,conservative_ci95_score_lower=.1) for a in ARMS[1:]}
    assert selection(choices,dict(V8=[2.]*6,HV8=[1.]*6)) == 'HV8'
    assert selection(choices,dict(V8=[1.]*6,HV8=[1.]*6)) == 'HV8'
    for value in choices.values():
        value['joint_gate'] = False
    assert selection(choices,{}) is None
    output = b'From,To,delay\na,b,1\nc,d,2\ne,f,3\n'
    streams = [io.BytesIO(v) for v in
        (output,output.replace(b'e,f,3',b'e,f,4'),
         output.replace(b'c,d,2',b'c,d,3').replace(b'e,f,3',b'e,f,4'))]
    result = compare_events(io.BytesIO(bytes([0,1,2])),streams,3)
    assert result['changed_rows'] == dict(V8=[0,0,1],HV8=[0,1,1])
    assert not any(result['unchanged_event_mismatches'].values())
    streams = [io.BytesIO(v) for v in (output,output.replace(b'a,b,1',b'a,b,2'),output)]
    assert compare_events(io.BytesIO(bytes([0,1,2])),streams,3)['unchanged_event_mismatches']['V8'] == 1
    adapted_score()
    print('EXP685_SCALE_SELF_CHECK_PASSED',flush=True)


def run():
    self_check()
    data.configure()
    frozen = data.freeze_check()
    labels = read(ROOT/'expanded/report.json')
    assert labels['all_complete_label_checks'] and labels['span_checks'] == 12
    assert labels['rows'] == data.COUNT*59904
    assert all(r['exit_code'] == 0 and r['rss_bytes'] <= 2_000_000_000 for r in labels['runs'])
    assert sum(r['cpu_s'] for r in labels['runs']) <= 10_000
    check(labels['exact']['path'],labels['exact'])
    assert Path('../exp683/exit-expanded-score-1b-archive.txt').read_text().strip() == '0'
    assert Path('data-launch/labels.exit-code').read_text().strip() == '0'
    source = BUILD/'score.py'
    source.write_text(adapted_score())
    population = read(ROOT/'100m-input.json')
    request = Path(population['input']['path'])
    check(request,population['input'])
    check(data.prior.CHECKER,frozen['checker'])
    write(ROOT/'timing-freeze.json',dict(files=[identity(p) for p in
        (Path(__file__),Path('validation/exp685_scale_run.sh'),Path(scoring.__file__),source,ROOT/'freeze.json',
         ROOT/'expanded/report.json',ROOT/'expanded/freeze.json')],
        input=population['input'],binaries=frozen['binaries'],schedule=frozen['schedule'],
        labels=labels['exact'],host=socket.gethostname(),
        process_snapshot=subprocess.check_output(['ps','-eo','pid,pcpu,comm,args'],text=True),
        confidence_per_component=.9875,simultaneous_components=4,
        minimum_delta_pp=.01,minimum_score=.005,seed=data.SEED,bootstrap_count=9999))
    timing, evidence, runs, deleted = {a:[] for a in ARMS},{},[],[]
    for iteration,order in enumerate(frozen['schedule']):
        for arm in order:
            output = BUILD/f'100m-{iteration}-{arm}.csv'
            assert not output.exists() and shutil.disk_usage('.').free > 5_100_000_000
            command = [str(data.BINARIES[arm]),'-in',str(request),'-out',str(output)]
            record = data.speed.measured(command,output.stem)
            counters = read(record['stderr'])
            assert record['threads'] == 1 and record['rss_bytes'] <= 2_000_000_000
            assert record['cpu_s'] < 100 and record['wall_s'] <= 3600
            assert counters == dict(rows=data.ROWS,unreachable=0,query_allocations=0)
            actual = identity(output)
            record.update(arm=arm,iteration=iteration,input=population['input'],output=actual,counters=counters)
            write(ROOT/(output.stem+'-evidence.json'),record)
            if iteration == 0:
                sample = BUILD/f'{arm}-sample.csv'
                contract_run = data.speed.measured([str(data.prior.CHECKER),'check',str(request),
                    str(output),str(data.ROWS),str(BUILD/'expanded/positions.txt'),str(sample)],
                    arm+'-contract')
                contract = read(ROOT/(arm+'-contract.stdout'))
                assert contract['contract_passed'] and contract['rows'] == data.ROWS
                assert contract['sample_rows'] == data.COUNT*59904
                evidence[arm] = dict(output=actual,run=record,contract=contract,contract_run=contract_run,
                                     sample=identity(sample))
            else:
                assert all(actual[k] == evidence[arm]['output'][k] for k in ('bytes','sha256'))
                timing[arm].append(record['cpu_s'])
                deletion = dict(file=actual,identical_to=evidence[arm]['output'],rebuild_command=command)
                write(ROOT/(output.stem+'-cleanup.json'),deletion)
                print('EXP685_REMOVE_DUPLICATE',output,actual['sha256'],flush=True)
                output.unlink()
                deleted.append(deletion)
            runs.append(record)
            print('EXP685_TIMING',iteration,arm,record['cpu_s'],flush=True)
    write(ROOT/'100m-report.json',dict(rows=data.ROWS,unique_rows=data.ROWS,port_pairs=59904,
        input=population['input'],timing=timing,evidence=evidence,runs=runs,deleted_duplicates=deleted,
        released_bytes=sum(v['file']['bytes'] for v in deleted),accuracy_not_read=True,
        same_complete_run_cpu_and_accuracy=True,disk_free_end_bytes=shutil.disk_usage('.').free))
    print('EXP685_COMPLETE_TIMING_READY',flush=True)


def unchanged():
    data.configure()
    data.freeze_check()
    record = read(ROOT/'100m-report.json')
    event = read('../exp679/validation/results/exp679/sample-events.json')['binary']
    binary = Path('../exp679')/event['path']
    check(binary,event)
    events = BUILD/'full-events.u8'
    assert not events.exists()
    data.speed.measured([str(binary),record['input']['path'],str(events)],'full-events')
    assert read(ROOT/'full-events.stdout')['rows'] == data.ROWS
    assert events.stat().st_size == data.ROWS
    streams = [Path(record['evidence'][a]['output']['path']).open('rb') for a in ARMS]
    try:
        with events.open('rb') as stream:
            result = compare_events(stream,streams,data.ROWS)
    finally:
        for stream in streams:
            stream.close()
    write(ROOT/'unchanged-events.json',dict(**result,event_asset=identity(events),
        event_binary=identity(binary),full_outputs=record['evidence']))
    assert not any(result['unchanged_event_mismatches'].values()),result
    print('EXP685_UNCHANGED_EVENTS_VERIFIED',result,flush=True)


def score():
    self_check()
    data.configure()
    data.freeze_check()
    frozen = read(ROOT/'timing-freeze.json')
    for item in frozen['files']:
        check(item['path'],item)
    data.configure(expanded=True)
    namespace = dict(vars(scoring),interval=interval,comparisons=comparisons,selection=selection)
    exec(compile((BUILD/'score.py').read_text(),str(BUILD/'score.py'),'exec'),namespace)
    namespace['main']('100m',ROOT/'100m-report.json')


if __name__ == '__main__':
    assert len(sys.argv) == 2
    if sys.argv[1] != 'self-check':
        assert socket.gethostname() == 'lhj-R4900-G3'
        assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp685')
    started, cpu = time.monotonic(), time.process_time()
    stage = sys.argv[1]
    {'self-check':self_check,'run':run,'unchanged':unchanged,'score':score}[stage]()
    if stage != 'self-check':
        write(ROOT/(stage+'-driver-cost.json'),
              dict(cpu_s=time.process_time()-cpu,wall_s=time.monotonic()-started))
