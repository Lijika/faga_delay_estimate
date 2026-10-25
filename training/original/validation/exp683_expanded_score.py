#!/usr/bin/env python3
"""Score expanded probability samples from already timed complete outputs."""
import csv
import itertools
import math
from pathlib import Path
import socket
import sys

import numpy as np
from scipy import stats

import exp683_expanded_exact as sample

read, write, identity, check = sample.read, sample.write, sample.identity, sample.check


def design(values, pair, population):
    count = np.bincount(pair, minlength=len(population))
    assert np.all(count >= 2) and np.all(count <= population)
    centers = np.bincount(pair, weights=values, minlength=len(population))/count
    variances = np.bincount(pair, weights=(values-centers[pair])**2,
                           minlength=len(population))/(count-1)
    mass = population/population.sum()
    point = float(mass @ centers)
    variance = float(np.sum(mass**2*(1-count/population)*variances/count))
    assert variance >= 0
    return point, variance


def interval(values, pair, family, population, seed):
    point, variance = design(values, pair, population)
    count = np.bincount(pair, minlength=len(population))
    weights = population[pair]/count[pair]
    mass = np.bincount(family, weights=weights, minlength=26)
    totals = np.bincount(family, weights=weights*values, minlength=26)
    assert mass.min() > 0
    draws = np.random.default_rng(seed).integers(26, size=(9999,26))
    family_ci = np.quantile(totals[draws].sum(axis=1)/mass[draws].sum(axis=1), [.0125,.9875]).tolist()
    half = float(stats.norm.ppf(.9875))*math.sqrt(variance)
    design_ci = [point-half, point+half]
    return dict(point_pp=point, stratified_variance_pp2=variance,
        stratified_ci975_pp=design_ci, family_ci975_pp=family_ci,
        conservative_ci975_pp=[min(design_ci[0],family_ci[0]), max(design_ci[1],family_ci[1])])


def self_check():
    strata = [np.array([0.,1.,4.]), np.array([2.,3.,7.,8.])]
    population = np.array([len(v) for v in strata])
    expected = sum(v.sum() for v in strata)/population.sum()
    runs = [design(np.concatenate((a,b)), np.array([0,0,1,1]), population)
            for a,b in itertools.product(itertools.combinations(strata[0],2),
                                         itertools.combinations(strata[1],2))]
    means, variances = np.asarray(runs).T
    assert abs(means.mean()-expected) < 1e-12
    assert abs(means.var()-variances.mean()) < 1e-12
    point, variance = design(np.concatenate(strata), np.repeat([0,1],population),population)
    assert abs(point-expected) < 1e-12 and variance == 0
    zero_scores = sample.prior.fresh.points(np.array([0,1,100,125]), np.array([0,0,100,100]))
    assert np.array_equal(zero_scores[:3], [100,0,100])
    assert abs(zero_scores[3]-100*(1-math.tanh(1))) < 1e-12
    codes, weights = np.array([-1,2,-1,2]), np.array([1.,2.,3.,4.])
    values, errors = {'A': zero_scores}, {'A': np.array([0,1,0,25])}
    grouped = group_summary(codes, weights, values, errors)
    for code in np.unique(codes):
        mask = codes == code
        result = grouped[str(code)]
        assert result['sample_rows'] == int(mask.sum())
        assert result['estimated_population_rows'] == weights[mask].sum()
        assert result['accuracy_pp']['A'] == np.average(zero_scores[mask],weights=weights[mask])
        assert result['mae_ps']['A'] == np.average(errors['A'][mask],weights=weights[mask])
        assert result['exact_fraction']['A'] == np.average(errors['A'][mask] == 0,weights=weights[mask])
    return dict(passed=True, enumerated_samples=len(runs), mean=expected,
                exact_variance=float(means.var()), mean_estimated_variance=float(variances.mean()),
                zero_truth_branch=True, grouped_weighted_errors=True)


def group_summary(codes, weights, scores, errors):
    keys, inverse = np.unique(codes, return_inverse=True)
    counts = np.bincount(inverse)
    mass = np.bincount(inverse, weights=weights)
    accuracy = {a:np.bincount(inverse,weights=weights*v)/mass for a,v in scores.items()}
    mae = {a:np.bincount(inverse,weights=weights*v)/mass for a,v in errors.items()}
    exact = {a:np.bincount(inverse,weights=weights*(v == 0))/mass for a,v in errors.items()}
    return {str(int(key)): dict(sample_rows=int(counts[i]),estimated_population_rows=float(mass[i]),
        accuracy_pp={a:float(v[i]) for a,v in accuracy.items()},
        mae_ps={a:float(v[i]) for a,v in mae.items()},
        exact_fraction={a:float(v[i]) for a,v in exact.items()}) for i,key in enumerate(keys)}


def main(case, report_path, cached_evidence=None):
    base = Path('validation/results/exp683')/case
    build = Path('build/exp683')/case
    root = base/('score-'+report_path.parent.name)
    root.mkdir(exist_ok=False)
    sample.prior.speed.ROOT = root
    write(root/'self-check.json', self_check())
    frozen, labels = read(base/'freeze.json'), read(base/'report.json')
    assert labels['all_complete_label_checks'] and labels['rows'] == sample.CASES[case][1]*59904
    check(labels['exact']['path'], labels['exact'])
    manifest = read(base/'label-freeze.json')
    for item in (manifest['input'], manifest['positions'], manifest['population']):
        check(item['path'], item)
    report = read(report_path)
    complete_reports = [report_path]
    if case == '100m':
        assert report['rows'] == report['unique_rows'] == 100_000_000
        runs = {arm: dict(output=e['output'], run=e['run']) for arm,e in report['evidence'].items()}
    else:
        assert report['rows'] == report['unique_rows'] == 1_000_000_000
        arm = 'A' if report_path.parent.name == 'exp655' else 'C'
        runs = {arm: dict(output=report['output'], run=report['run'], input=report['input'])}
        if report_path.parent.name != 'exp655':
            complete_reports.append(Path('../exp655/validation/results/exp655/1b-report.json'))
            baseline = read(complete_reports[-1])
            runs['A'] = dict(output=baseline['output'], run=baseline['run'], input=baseline['input'])
    assert report['port_pairs'] == 59904
    for item in runs.values():
        run = item['run']
        assert run['exit_code'] == 0 and run['threads'] == 1
        input_id = item.get('input',run.get('input'))
        assert input_id is not None
        assert all(input_id[k] == frozen['input'][k] for k in ('bytes','sha256'))
    request = Path(frozen['input']['path'])
    check(request, frozen['input'])
    checker = Path('../exp580/build/exp580/contract-check')
    check(checker, read('../exp679/validation/results/exp679/freeze.json')['checker'])
    mapping_path = Path('../exp575/offline/validation/results/exp575/mapping.json')
    inputs = [Path(__file__), Path(sample.__file__), Path(sample.prior.fresh.__file__),
        Path(sample.prior.__file__), *complete_reports, base/'freeze.json', base/'label-freeze.json',
        base/'report.json', base/'input.json', build/'positions.txt', build/'pair-populations.json',
        build/'sources', build/'targets', mapping_path]
    write(root/'score-freeze.json', dict(files=[identity(p) for p in inputs], input=frozen['input'],
        seed=frozen['seed'], sample_rows=frozen['sample_rows'], complete_estimator_runs=0,
        cached_evidence=cached_evidence))
    positions = np.loadtxt(build/'positions.txt', dtype='i8')
    assert len(positions) == frozen['sample_rows'] and np.all(np.diff(positions) > 0)
    population = np.asarray(read(build/'pair-populations.json'), 'i8')
    sources, targets = [(build/name).read_text().splitlines() for name in ('sources','targets')]
    assert len(set(sources)) == 208 and len(set(targets)) == 288
    for name in ('sources','targets'):
        item, = [v for v in frozen['files'] if v['path'] == str(build/name)]
        check(build/name,item)
    si, ti = dict(zip(sources,range(208))), dict(zip(targets,range(288)))
    mapping = read(mapping_path)
    families = dict(zip(mapping['sources'], [v[0] for v in mapping['source_coordinates']]))
    target_families = dict(zip(mapping['targets'], [v[0] for v in mapping['target_coordinates']]))
    training_path = Path('../exp501/build/exp501/u-role/requests.csv')
    training, = [v for v in frozen['files'] if v['path'] == str(training_path)]
    check(training_path,training)
    with training_path.open(newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == ['From','To']
        training_pins = {row[0] for row in reader}
    n = len(positions)
    truth, pair, family = (np.empty(n,'i8') for _ in range(3))
    groups = {k: np.empty(n,'i4') for k in ('distance','direction','near_axis','source_tile',
        'target_tile','source_lane','target_lane','source_edge','target_edge',
        'source_port','target_port','target_family','source_pin_seen_in_training')}
    with Path(labels['exact']['path']).open(newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == ['index','from','to','exact','expanded','relaxed','cpu_s']
        for i,row in enumerate(reader):
            assert i < n and len(row) == 7 and row[0] == str(i)
            a,b = (pin.split('/',1) for pin in row[1:3])
            sx,sy = map(int,a[0][4:].split('_')); tx,ty = map(int,b[0][4:].split('_'))
            dx,dy = tx-sx,ty-sy
            truth[i],pair[i],family[i] = int(row[3]),si[a[1]]*288+ti[b[1]],families[a[1]]
            values = dict(distance=int(np.searchsorted([24,100,300],abs(dx)+abs(dy),side='right')),
                direction=2*(dx<0)+(dy<0),near_axis=int(abs(dx)<20 or abs(dy)<24),
                source_tile=(sx//10)*55+sy//10,target_tile=(tx//10)*55+ty//10,
                source_lane=int(a[1].split('[')[1][:-1]) if '[' in a[1] else -1,
                target_lane=int(b[1].split('[')[1][:-1]) if '[' in b[1] else -1,
                source_edge=min(sx,119-sx,sy,549-sy)//12,target_edge=min(tx,119-tx,ty,549-ty)//12,
                source_port=si[a[1]],target_port=ti[b[1]],target_family=target_families[b[1]],
                source_pin_seen_in_training=int(row[1] in training_pins))
            for key,value in values.items():
                groups[key][i] = value
    assert i+1 == n and truth.min() >= 0
    count = np.bincount(pair,minlength=59904)
    assert np.all(count == frozen['samples_per_pair']) and population.sum() == frozen['rows']
    input_report = read(base/'input.json')
    assert int(groups['source_pin_seen_in_training'].sum()) == input_report['training_source_pin_overlap']
    check(input_report['events']['path'],input_report['events'])
    groups.update(event=np.fromfile(input_report['events']['path'],'u1'),source_family=family)
    assert all(len(v) == n for v in groups.values())
    weights = population[pair]/count[pair]
    predictions, evidence = {}, {}
    for arm,item in runs.items():
        source_root = Path('../exp655') if arm == 'A' and case == '1b' else report_path.parents[3]
        output = source_root/item['output']['path']
        sampled = build/(root.name+'-'+arm+'.csv')
        cached = (cached_evidence or {}).get(arm)
        if cached is not None:
            assert cached['source_run'] == item['run']
            assert all(cached['source_output'][k] == item['output'][k] for k in ('bytes','sha256'))
            assert cached['contract']['contract_passed'] and cached['contract']['sample_rows'] == n
            sampled = Path(cached['sample']['path'])
            check(sampled,cached['sample'])
            run,contract = cached['contract_run'],cached['contract']
        elif case == '1b' and arm == 'A':
            assert not sampled.exists()
            import exp683_archived_sample
            baseline_report = report if report_path.parent.name == 'exp655' else baseline
            run,contract = exp683_archived_sample.extract(
                output,sampled,positions,baseline_report,root)
        else:
            assert not sampled.exists()
            check(output,item['output'])
            run = sample.prior.speed.measured([str(checker),'check',str(request),str(output),
                str(frozen['rows']),str(build/'positions.txt'),str(sampled)],arm+'-contract')
            contract = read(root/(arm+'-contract.stdout'))
        assert contract['contract_passed'] and contract['sample_rows'] == n
        values = np.empty(n,'i8')
        with sampled.open(newline='') as stream, Path(labels['exact']['path']).open(newline='') as exact:
            reader, oracle = csv.reader(stream), csv.reader(exact)
            assert next(reader) == ['row','From','To','delay']; next(oracle)
            for i,row in enumerate(reader):
                label = next(oracle)
                assert i < n and len(row) == 4 and int(row[0]) == positions[i]
                assert row[1:3] == label[1:3] and row[3] == str(int(row[3]))
                values[i] = int(row[3])
            assert i+1 == n and next(oracle,None) is None
        assert values.min() >= 0
        predictions[arm] = values
        evidence[arm] = dict(source_output=item['output'],source_run=item['run'],
            sample=identity(sampled),contract=contract,contract_run=run)
    scores = {a: sample.prior.fresh.points(v,truth) for a,v in predictions.items()}
    assert all(np.isfinite(v).all() for v in scores.values())
    errors = {a:np.abs(v-truth) for a,v in predictions.items()}
    estimates = {a: interval(v,pair,family,population,frozen['seed']) for a,v in scores.items()}
    partitions = {key:group_summary(g,weights,scores,errors) for key,g in groups.items()}
    result = dict(accuracy=estimates,groups=partitions,evidence=evidence,
        errors={a:dict(mae_ps=float(np.average(v,weights=weights)),
            exact_fraction=float(np.average(v == 0,weights=weights))) for a,v in errors.items()},
        zero_truth_sample_rows=int(np.count_nonzero(truth == 0)),
        source_ports=sources,target_ports=targets,
        sample_rows=n,samples_per_pair=frozen['samples_per_pair'],port_pairs=59904,
        full_population_scored=False,complete_estimator_runs=0,validation_input=input_report,
        source_population_rows=frozen['rows'],same_complete_run_cpu_and_accuracy=True,
        hidden_distribution_verified=False)
    if set(scores) == {'A','C'}:
        delta = scores['C']-scores['A']
        result['delta_accuracy'] = interval(delta,pair,family,population,frozen['seed'])
        result['changed_sample_rows'] = int(np.count_nonzero(predictions['A'] != predictions['C']))
        result['improved_sample_rows'] = int(np.count_nonzero(errors['C'] < errors['A']))
        result['worse_sample_rows'] = int(np.count_nonzero(errors['C'] > errors['A']))
        result['group_delta_accuracy_pp'] = {key:{v:p['accuracy_pp']['C']-p['accuracy_pp']['A']
            for v,p in group.items()} for key,group in partitions.items()}
        if case == '100m':
            result['joint'] = sample.prior.joint(result['delta_accuracy']['point_pp'],
                result['delta_accuracy']['conservative_ci975_pp'][0],
                np.asarray(report['timing']['A'])-report['timing']['C'])
    write(root/'accuracy.json',result)
    print('EXP683_EXPANDED_ACCURACY',case,{a:v['point_pp'] for a,v in estimates.items()},flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp683')
    assert len(sys.argv) == 3 and sys.argv[1] in sample.CASES
    main(sys.argv[1],Path(sys.argv[2]))
