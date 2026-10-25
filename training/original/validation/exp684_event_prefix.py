#!/usr/bin/env python3
"""Build and audit fixed V8/HV8 prefixes with the frozen exp679 deployment."""
import importlib.util
import inspect
from pathlib import Path
import resource
import shutil
import socket
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp679/validation').resolve()))
import exp679_hv_cli as original

PLAN = Path('experiment/实验684-低频事件八树前缀的静态成本验证.md')
ROOT, BUILD = Path('validation/results/exp684'), Path('build/exp684')
read, write, identity, check = original.read, original.write, original.identity, original.check


def adapted_source(arm, source):
    changes = [
        ("ROOT, BUILD = Path('validation/results/exp679'), Path('build/exp679')",
         f"ROOT, BUILD = Path('{ROOT/arm}'), Path('{BUILD/arm}')"),
        ("PLAN = Path('experiment/实验679-HV64静态部署与新100M联合验证.md')",
         f"PLAN = Path('{PLAN}')"),
        ("for tree in model['oblivious_trees']:", "for tree in model['oblivious_trees'][:8]:"),
        ("kLeaves679[][64][16]", "kLeaves679[][8][16]"),
        ("const int32_t* q,int ax,int ay,int ndx,int ndy,",
         "const int32_t* q,int ax,int ay,[[maybe_unused]] int ndx,[[maybe_unused]] int ndy,"),
        ("unsigned char leaves[2][64]{};", "unsigned char leaves[2][8]{};"),
        ("std::fwrite(leaves,1,128,output)==128", "std::fwrite(leaves,1,16,output)==16"),
        ("('leaves', 'u1', (2, 64))", "('leaves', 'u1', (2, 8))"),
        ("predict(read(path), x[rows], 64)", "predict(read(path), x[rows], 8)"),
        ("../exp678/build/exp678/HV64-raw.f64", "../exp678/build/exp678/HV8-raw.f64"),
        ("Path('validation/exp679_run.sh')", "Path('validation/exp684_event_prefix.py')"),
        ("shutil.copy2(Path('tests')/name, BUILD/name)",
         "shutil.copy2(Path('tests')/('exp684_hv_events.h' if name == 'exp679_hv_events.h' else name), BUILD/name)"),
    ]
    if arm == 'V8':
        changes += [
            ("event = h.astype('u1')+2*v", "event = 2*v"),
            ('unsigned(f[52]?1:(e[17]==2&&e[16]>0?2:0))',
             'unsigned(e[17]==2&&e[16]>0?2:0)'),
            ('for(unsigned n:seen) require(n>0,"model coverage");',
             'for(unsigned i=0;i<8;++i) require(i%2 ? seen[i]>0 : seen[i]==0,"model coverage");'),
            ("compile_command = [changes.get(a, a) for a in frozen['compile_command']]",
             "compile_command = [changes.get(a, a) for a in frozen['compile_command']] + ['-DEXP684_V_ONLY']"),
            ("str(BUILD/'expert-check')]", "str(BUILD/'expert-check'), '-DEXP684_V_ONLY']"),
        ]
    for before, after in changes:
        source = original.replace(source, before, after)
    return source


def domain_check():
    arch = Path('../exp679/doc/eda比赛文件/arch/SRB_Gap.json')
    evidence = ROOT/'domain-prior.json'
    expected = read(evidence)
    assert identity(arch)['sha256'] == expected['map']['sha256']
    assert expected['all_checks_passed']
    blocks = read(arch)['Gap']['Block']
    assert len(blocks) == 7
    assert [(b['left'], b['right'], b['lower'], b['upper']) for b in blocks[1:]] == [
        (76, 89, 100*j, 100*j+49) for j in range(6)]
    # The independent enumeration and its map identity are frozen by exp679.
    ys = [y for y in range(550) if y % 100 >= 50]
    assert len(ys) == expected['legal_central_y_count'] == 250
    for ay in ys:
        for ty in ys:
            count = sum(min(ay, ty) < low and max(ay, ty) > low+49
                        for low in range(0, 501, 100))
            assert count == abs(ay//100-ty//100)
    for ax in range(120):
        for tx in range(120):
            assert ((76 <= ax <= 89) and (76 <= tx <= 89)) == (
                int(76 <= ax <= 89)+int(76 <= tx <= 89) == 2)
    return dict(map=identity(arch), original_evidence=identity(evidence),
        ordered_y_pairs=len(ys)**2, ordered_x_pairs=120**2, all_checks_passed=True)


def run(arm):
    assert arm in ('V8', 'HV8')
    root, build = ROOT/arm, BUILD/arm
    assert not root.exists() and not build.exists()
    frozen = read('../exp679/validation/results/exp679/build-freeze.json')
    src = Path(original.__file__)
    expected = next(v for v in frozen['files'] if Path(v['path']).resolve() == src.resolve())
    check(src, expected)
    text = adapted_source(arm, src.read_text())
    compile(text, str(build/'deployment.py'), 'exec')
    domain = domain_check()
    root.mkdir(parents=True)
    build.mkdir(parents=True)
    shutil.copyfile(PLAN, root/'protocol-original.md')
    generated = build/'deployment.py'
    generated.write_text(text)
    spec = importlib.util.spec_from_file_location('exp684_'+arm, generated)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.speed.ROOT = root
    write(root/'adaptation.json', dict(arm=arm, trees=8,
        original=identity(src), generated=identity(generated), domain=domain,
        files=[identity(p) for p in (Path(__file__), PLAN, Path('tests/exp684_hv_events.h'),
                                     Path('validation/exp684_run.sh'))],
        new_training_runs=0, complete_program_runs=0, original_models_unchanged=True))
    begin, cpu = time.monotonic(), time.process_time()
    data, x, event = cli.dataset()
    predict = cli.fit.decoder()
    records = read('../exp679/validation/results/exp679/final-training.json')['records']
    raw = np.fromfile('../exp640/build/exp640/S8-final.f64', '<f8')
    check('../exp640/build/exp640/S8-final.f64',
          read('../exp640/validation/results/exp640/final-training.json')['raw']['S8'])
    (root/'installed-catboost-help.txt').write_text(cli.fit.cb.__version__+'\n'
        + cli.fit.cb.CatBoostRegressor.load_model.__doc__+'\n'
        + str(inspect.signature(cli.fit.cb.CatBoostRegressor.predict))+'\n'
        + str(inspect.signature(cli.fit.cb.CatBoostRegressor.calc_leaf_indexes))+'\n')
    mapped = []
    for record in records:
        path = Path('../exp679')/record['model']['path']
        check(path, record['model'])
        value = 1 if record['event'] == 'H' else 2
        mask = event == value
        if mask.any():
            model = cli.fit.cb.CatBoostRegressor()
            model.load_model(str(path), format='json')
            decoded, leaves = predict(read(path), x[mask], 8)
            native = model.predict(x[mask], ntree_end=8, thread_count=1)
            assert np.array_equal(leaves, model.calc_leaf_indexes(x[mask], thread_count=1)[:, :8])
            assert np.allclose(decoded, native, rtol=0, atol=1e-10)
            assert np.array_equal(cli.fit.decode(decoded, data['base'][mask], data['mandatory'][mask]),
                                  cli.fit.decode(native, data['base'][mask], data['mandatory'][mask]))
            raw[mask] = decoded
        mapped.append(dict(record, model=identity(path), prefix_trees=8,
                           active_rows=int(mask.sum())))
    raw.tofile(build/'final.f64')
    extra = read('../exp679/validation/results/exp679/final-training.json')['extra']
    check(Path('../exp679')/extra['path'], extra)
    prep = dict(records=mapped, final_raw=identity(build/'final.f64'),
        extra=identity(Path('../exp679')/extra['path']), cpu_s=time.process_time()-cpu,
        wall_s=time.monotonic()-begin,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        native_prefix_leaf_ids_equal=True, native_prefix_integer_prediction_equal=True,
        new_training_runs=0)
    assert prep['cpu_s'] <= 600 and prep['wall_s'] <= 900 and prep['rss_bytes'] <= 2_000_000_000
    write(root/'final-training.json', prep)
    write(root/'training-freeze.json', dict(reused_models=mapped, prefix_trees=8,
        adaptation=identity(root/'adaptation.json'), new_training_runs=0))
    del data, x, event, raw
    cli.gc.collect()
    cli.build()
    cli.audit()
    numeric = read(root/'numeric-audit.json')
    assert all(numeric[k] for k in ('final_prediction_equal', 'oof_prediction_equal',
               'ordinary_predictions_equal', 'raw_bitwise_equal', 'all_leaf_ids_equal'))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    assert rss <= 2_000_000_000
    write(root/'report.json', dict(arm=arm, numeric=numeric, deployment=read(root/'build-freeze.json'),
        prefix_trees=8, new_training_runs=0, complete_program_runs=0,
        numerical_checks_passed=True, driver_rss_bytes=rss, next_stage='fresh_100m',
        final_accuracy_goal_verified=False, platform_score_verified=False))
    print('EXP684_STATIC_NUMERIC_PASSED', arm, flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp684')
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert len(sys.argv) == 2
    run(sys.argv[1])
