#!/usr/bin/env python3
"""Freeze a new 100M population and reuse the audited 32-per-pair exact sampler."""
import inspect
import io
import itertools
from pathlib import Path
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path('../exp683/validation').resolve()))
import exp683_expanded_exact as sample

prior = sample.prior
fresh, labels, speed = prior.fresh, prior.labels, prior.speed
read, write, identity, check = sample.read, sample.write, sample.identity, sample.check
ROOT, BUILD = Path('validation/results/exp685'), Path('build/exp685')
PLAN = Path('experiment/实验685-八树事件专家的新100M三臂联合验证.md')
ARMS = ('A', 'V8', 'HV8')
BINARIES = {'A': Path('../exp654/build/exp654/B'),
            **{a: Path('../exp684/build/exp684')/a/'C' for a in ARMS[1:]}}
ROWS, COUNT, SEED = 100_000_000, 32, 20261024685
ARCH = sample.ARCH


def adaptation():
    text = inspect.getsource(prior.dataset)
    stop = '    (BUILD / "positions.txt").write_text'
    assert text.count(stop) == 1
    population = text.split(stop)[0] + '    print("EXP685_POPULATION_COMPLETE", flush=True)\n'
    assert 'write(BUILD / "pair-populations.json", population)' in population
    assert 'labels-' not in population
    text = inspect.getsource(sample.prepare)
    changes = [
        ("../exp679/validation/results/exp679/100m-input.json", str(ROOT/'100m-input.json')),
        ("../exp679/build/exp679/u-role/requests.csv", str(BUILD/'u-role/requests.csv')),
        ("../exp679/build/exp679/pair-populations.json", str(BUILD/'pair-populations.json')),
    ]
    for before, after in changes:
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    assert text.count("old_sample = Path('../exp679/build/exp679/sample-requests.csv')") == 1
    for name, source in (('population.py', population), ('sample.py', text)):
        compile(source, name, 'exec')
    return population, text


def configure(expanded=False):
    root, build = (ROOT/'expanded', BUILD/'expanded') if expanded else (ROOT, BUILD)
    prior.ROOT, prior.BUILD, prior.PLAN, prior.ROWS = ROOT, BUILD, PLAN, ROWS
    fresh.ROOT, fresh.BUILD, fresh.PLAN, fresh.ROWS = ROOT, BUILD, PLAN, ROWS
    fresh.ARCH = labels.ARCH = ARCH
    labels.roles.__globals__['ARCH'] = ARCH
    labels.ROOT, labels.BUILD, labels.PLAN, labels.ROWS = root, build, PLAN, COUNT*59904
    sample.ROOT, sample.BUILD, sample.PLAN = root, build, PLAN
    sample.CASES = {'100m': (ROWS, COUNT, SEED, 10_000)}
    speed.ROOT = root


def freeze_check():
    frozen = fresh.freeze_check()
    for item in frozen['binaries'].values():
        check(item['path'], item)
    for item in frozen['expected_tools']:
        check(Path('../..')/item['path'], item)
    return frozen


def self_check():
    configure()
    rows = [f'SRB_0_{i}/S,SRB_1_{i}/T\n'.encode() for i in range(10)]
    output = io.BytesIO()
    populations, selected, rejected = fresh.filter_stream(
        io.BytesIO(b'From,To\n'+b''.join(rows)), output, {b'SRB_0_0/S'},
        {rows[1][:-1]}, ['S'], ['T'], 8)
    assert populations == [8] and [p for p,_,_ in selected] == list(range(4))
    assert output.getvalue() == b'From,To\n'+b''.join(rows[2:])
    assert rejected == dict(visited_proposal_rows=10, rejected_source_rows=1, rejected_history_rows=1)
    population, expanded = adaptation()
    assert "str(ROOT/'100m-input.json')" not in expanded
    assert str(ROOT/'100m-input.json') in expanded
    assert 'EXP685_POPULATION_COMPLETE' in population
    schedule = [ARMS, *itertools.permutations(ARMS)]
    assert len(schedule) == 7 and len(set(schedule[1:])) == 6
    assert all([order.index(a) for order in schedule[1:]].count(i) == 2
               for a in ARMS for i in range(3))
    print('EXP685_DATA_SELF_CHECK_PASSED', flush=True)


def prepare():
    self_check()
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/'protocol-original.md')
    population, expanded = adaptation()
    (BUILD/'population.py').write_text(population)
    (BUILD/'sample.py').write_text(expanded)
    old = read('../exp679/validation/results/exp679/freeze.json')
    history = [Path(r['path']) for r in old['history']]
    history += [Path('../exp679/build/exp679/sample-requests.csv'),
                Path('../exp683/build/exp683/100m/sample-requests.csv'),
                Path('../exp683/build/exp683/1b/sample-requests.csv')]
    assert len(history) == len(set(history))
    provenance = []
    for arm in ARMS[1:]:
        base = Path('../exp684/validation/results/exp684')/arm
        record = read(base/'build-freeze.json')
        check(BINARIES[arm], record['binaries']['C'])
        check(BINARIES['A'], record['binaries']['A'])
        assert record['static_linked']
        numeric = read(base/'numeric-audit.json')
        assert all(numeric[k] for k in ('final_prediction_equal', 'oof_prediction_equal',
                   'ordinary_predictions_equal', 'raw_bitwise_equal', 'all_leaf_ids_equal'))
        provenance.extend([base/'build-freeze.json', base/'numeric-audit.json'])
    for item in old['expected_tools']:
        check(Path('../..')/item['path'], item)
    check(prior.CHECKER, old['checker'])
    sampler = Path('validation/exp683_stratified_sample.cpp')
    assert sampler.read_bytes() == Path('../exp683/validation/exp683_stratified_sample.cpp').read_bytes()
    for tool in (prior.HIDDEN/'make_hidden_suite', prior.HIDDEN/'check_hidden_suite',
                 Path('../../build/exp203/exact_labels'), prior.CHECKER):
        result = subprocess.run([str(tool), '--help'], capture_output=True, text=True)
        text = result.stdout + result.stderr
        assert 'usage' in text.lower(), str(tool)
        (ROOT/(tool.name+'-help.txt')).write_text(text)
    files = [Path(__file__), Path('validation/exp685_data_run.sh'), PLAN,
        ROOT/'protocol-original.md', BUILD/'population.py',
        BUILD/'sample.py', sampler, Path(sample.__file__), Path(prior.__file__),
        Path(fresh.__file__), Path(labels.__file__), Path(speed.__file__),
        Path('../exp624/validation/exp624_fresh_leaf_validation.py'),
        Path('../exp575/offline/validation/results/exp575/mapping.json'),
        prior.HIDDEN/'reach.bin', prior.HIDDEN/'independent/eligibility.bin',
        *provenance, *ARCH.glob('*.json')]
    assert len(list(ARCH.glob('*.json'))) == 5
    assert shutil.disk_usage('.').free > 28_000_000_000
    write(ROOT/'freeze.json', dict(files=[identity(p) for p in files],
        binaries={a: identity(p) for a,p in BINARIES.items()}, checker=identity(prior.CHECKER),
        rows=ROWS, sample_rows=COUNT*59904, samples_per_pair=COUNT,
        proposal_rows=120_000_000, proposal_seed=20261025685, shuffle_seed=20261026685,
        expected_tools=old['expected_tools'], history=[identity(p) for p in history],
        source_ports=labels.roles()[0], target_ports=labels.roles()[1], required_port_pairs=59904,
        schedule=[ARMS, *itertools.permutations(ARMS)], seed=SEED, untouched_scores=True,
        sample_rule='32 without-replacement positions per port pair with exp683 sampler',
        cpu_label_budget_s=10_000, disk_free_start_bytes=shutil.disk_usage('.').free,
        complete_estimator_runs=0))
    print('EXP685_NEW_100M_FROZEN', flush=True)


def dataset():
    configure()
    freeze_check()
    namespace = dict(vars(prior))
    exec(compile((BUILD/'population.py').read_text(), str(BUILD/'population.py'), 'exec'), namespace)
    namespace['dataset']()
    configure(expanded=True)
    namespace = dict(vars(sample))
    exec(compile((BUILD/'sample.py').read_text(), str(BUILD/'sample.py'), 'exec'), namespace)
    namespace['prepare']('100m')
    report = read(ROOT/'expanded/input.json')
    assert report['training_request_overlap'] == report['training_source_pin_overlap'] == 0
    assert report['old_sample_overlap'] == 0
    print('EXP685_RANDOM_EXACT_INPUT_READY', report['rows'], flush=True)


def compute_labels():
    configure()
    freeze_check()
    configure(expanded=True)
    sample.labels('100m')


if __name__ == '__main__':
    assert len(sys.argv) == 2
    stage = sys.argv[1]
    if stage != 'self-check':
        assert socket.gethostname() == 'lhj-R4900-G3'
        assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp685')
    {'self-check': self_check, 'prepare': prepare, 'dataset': dataset,
     'labels': compute_labels}[stage]()
