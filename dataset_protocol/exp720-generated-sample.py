def prepare(case):
    rows, count, seed, budget = CASES[case]
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/'protocol-original.md')
    prior.labels.ARCH = ARCH
    sources, targets = prior.labels.roles()
    si, ti = dict(zip(sources, range(208))), dict(zip(targets, range(288)))
    if case == '100m':
        record = read('validation/results/exp720/100m-input.json')
        request = Path('build/exp720/u-role/requests.csv')
        populations = Path('build/exp720/pair-populations.json')
        old_sample = Path('../exp679/build/exp679/sample-requests.csv')
    else:
        record = read('../exp655/validation/results/exp655/1b-report.json')
        request = Path('../../build/hidden-suite-v1/role-1b/requests.csv')
        populations = Path('../exp580/build/exp580/scale-input/pair-populations-1000000000.json')
        old_sample = Path('../exp580/build/exp580/scale-exact.csv')
        assert (sources, targets) == tuple((Path('../exp580/build/exp580')/(name+'.txt')).read_text().splitlines()
                                          for name in ('sources', 'targets'))
    assert record['rows'] == record['unique_rows'] == rows and record['port_pairs'] == 59904
    check(request, record['input'])
    population = np.asarray(read(populations), dtype='<u4')
    assert population.shape == (59904,) and population.sum() == rows
    for name, ports in (('sources', sources), ('targets', targets)):
        (BUILD/name).write_text('\n'.join(ports)+'\n')
    binary = BUILD/'stratified-sample'
    (ROOT/'compiler-help.txt').write_text(subprocess.check_output(['g++', '--help'], text=True))
    command = ['g++', '-std=c++17', '-O3', '-march=x86-64', '-mtune=generic',
        '-Wall', '-Wextra', '-Werror', 'validation/exp683_stratified_sample.cpp', '-o', str(binary)]
    prior.speed.measured(command, 'compile-sampler')
    assert not (ROOT/'compile-sampler.stderr').read_bytes()
    sampler_self_check(binary)
    sampling_plan(BUILD/'sampling-plan.bin', population, count, seed)
    expected_tools = read('../exp679/validation/results/exp679/label-freeze.json')['tools']
    for tool in expected_tools:
        check(Path('../exp679')/tool['path'], tool)
    training = Path('../exp501/build/exp501/u-role/requests.csv')
    events = read('../exp679/validation/results/exp679/sample-events.json')['binary']
    event_binary = Path('../exp679')/events['path']
    check(event_binary, events)
    files = [Path(__file__), Path('validation/exp683_stratified_sample.cpp'), PLAN,
        ROOT/'protocol-original.md', binary, BUILD/'sampling-plan.bin', BUILD/'sources', BUILD/'targets',
        populations, old_sample, training, event_binary,
        Path(prior.__file__), Path(prior.labels.__file__), Path(prior.speed.__file__),
        *ARCH.glob('*.json')]
    write(ROOT/'freeze.json', dict(files=[identity(p) for p in files], input=identity(request),
        rows=rows, sample_rows=count*59904, samples_per_pair=count, seed=seed, case=case,
        cpu_label_budget_s=budget, complete_program_runs=0, untouched_scores=True,
        input_unique_evidence=record, disk_free_start_bytes=shutil.disk_usage('.').free))
    prior.speed.measured([str(binary), str(request), str(BUILD/'sampling-plan.bin'),
        str(BUILD/'sources'), str(BUILD/'targets'), str(BUILD/'sample-requests.csv'),
        str(BUILD/'positions.txt'), str(BUILD/'counts.tsv')], 'sample-input')
    assert read(ROOT/'sample-input.stdout') == dict(rows=rows, pairs=59904,
        samples=count*59904, samples_per_pair=count)
    prior.speed.measured([str(event_binary), str(BUILD/'sample-requests.csv'),
                         str(BUILD/'events.u8')], 'sample-events')
    events = np.fromfile(BUILD/'events.u8', 'u1')
    assert events.shape == (count*59904,) and np.isin(events, [0,1,2]).all()
    with old_sample.open(newline='') as stream:
        reader = csv.DictReader(stream)
        a, b = ('From', 'To') if 'From' in reader.fieldnames else ('from', 'to')
        old = {(r[a], r[b]) for r in reader}
    with training.open() as stream:
        assert stream.readline() == 'From,To\n'
        train_pairs = {line.rstrip('\n') for line in stream}
    train_pins = {line.split(',', 1)[0] for line in train_pairs}
    streams = [(BUILD/f'labels-{i}.csv').open('x', newline='') for i in range(4)]
    writers = [csv.writer(stream, lineterminator='\n') for stream in streams]
    for writer in writers:
        writer.writerow(['kind', 'from', 'to', 'label', 'span_checked'])
    counts, spans = np.zeros(59904, 'i8'), [0]*4
    bands, old_overlap, train_overlap, pin_overlap = {}, 0, 0, 0
    coverage = {name: {} for name in ('distance', 'direction', 'near_axis', 'source_tile',
        'target_tile', 'source_lane', 'target_lane', 'source_edge', 'target_edge')}
    with (BUILD/'sample-requests.csv').open(newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == ['From', 'To']
        for i, (a, b) in enumerate(reader):
            pa, pb = a.split('/', 1), b.split('/', 1)
            sx, sy = map(int, pa[0][4:].split('_'))
            tx, ty = map(int, pb[0][4:].split('_'))
            dx, dy = tx-sx, ty-sy
            distance = abs(dx)+abs(dy)
            band = next(v for v in (12, 24, 50, 100, 300, 1000) if distance <= v)
            span = bands.get(band, 0) < 2
            bands[band] = bands.get(band, 0)+1
            spans[i % 4] += span
            writers[i % 4].writerow(['exp683-random-per-pair', a, b, -2, int(span)])
            counts[si[pa[1]]*288+ti[pb[1]]] += 1
            old_overlap += (a, b) in old
            train_overlap += a+','+b in train_pairs
            pin_overlap += a in train_pins
            values = dict(distance=band, direction=2*(dx < 0)+(dy < 0),
                near_axis=int(abs(dx) < 20 or abs(dy) < 24),
                source_tile=(sx//10, sy//10), target_tile=(tx//10, ty//10),
                source_lane=pa[1].split('[')[-1].rstrip(']') if '[' in pa[1] else 'logic',
                target_lane=pb[1].split('[')[-1].rstrip(']') if '[' in pb[1] else 'logic',
                source_edge=min(sx,119-sx,sy,549-sy)//12,
                target_edge=min(tx,119-tx,ty,549-ty)//12)
            for name, value in values.items():
                key = str(value)
                coverage[name][key] = coverage[name].get(key, 0)+1
    for stream in streams:
        stream.close()
    assert i+1 == count*59904 and np.all(counts == count) and sum(spans) == 12
    if case == '100m':
        assert train_overlap == pin_overlap == 0
    left = {name: int(counts.reshape(208,288)[i].sum()) for i,name in enumerate(sources)}
    right = {name: int(counts.reshape(208,288)[:,i].sum()) for i,name in enumerate(targets)}
    complete = dict(source_ports=208, target_ports=288, from_port_counts=left, to_port_counts=right,
        port_pairs=59904, minimum_port_pair_rows=count, maximum_port_pair_rows=count,
        port_pair_counts=counts.reshape(208,288).tolist())
    write(ROOT/'input.json', dict(input=identity(BUILD/'sample-requests.csv'), rows=i+1,
        coverage=complete, diversity=coverage, training_request_overlap=train_overlap,
        training_source_pin_overlap=pin_overlap, old_sample_overlap=old_overlap,
        events=identity(BUILD/'events.u8'), event_counts=np.bincount(events,minlength=3).tolist(),
        prior_sample_rows=len(old), unique_rows_from_parent_certificate=True,
        sampling_probability='samples_per_pair / population_per_pair', score_not_read=True))
    shutil.copy2(populations, BUILD/'pair-populations.json')
    tools = [identity(Path('../exp679')/tool['path']) for tool in expected_tools]
    write(ROOT/'label-freeze.json', dict(input=identity(BUILD/'sample-requests.csv'), rows=i+1,
        positions=identity(BUILD/'positions.txt'), population=identity(BUILD/'pair-populations.json'),
        tools=tools, shards=[dict(shard=j, rows=(i+1)//4, span_checks=spans[j],
            input=identity(BUILD/f'labels-{j}.csv')) for j in range(4)]))
    print('EXP683_PREPARED', case, i+1, 'overlap', old_overlap, train_overlap, pin_overlap, flush=True)
