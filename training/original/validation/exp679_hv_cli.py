#!/usr/bin/env python3
"""Deploy the fixed pooled HV64 experts on the frozen exp655 path."""
import ast
import gc
import inspect
from pathlib import Path
import re
import resource
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path('../exp678/validation').resolve()))
import exp678_hv_replacement as fit
sys.path.insert(0, str(Path('../exp580/validation').resolve()))
import exp580_complete_speed as speed

ROOT, BUILD = Path('validation/results/exp679'), Path('build/exp679')
PLAN = Path('experiment/实验679-HV64静态部署与新100M联合验证.md')
OLD = Path('../exp654')
BASELINE = OLD/'build/exp654/B'
read, write, identity = fit.read, fit.write, fit.identity
speed.ROOT = ROOT


def check(path, expected):
    return fit.checked(path, expected)


def replace(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after)


def freeze_check():
    frozen = read(ROOT/'build-freeze.json')
    for item in frozen['files']:
        check(item['path'], item)
    for arm, path in (('A', BASELINE), ('C', BUILD/'C')):
        check(path, frozen['binaries'][arm])
    return frozen


def dataset():
    data = fit.prior.source.load()
    data['base'] = fit.prior.curve_base(data)
    gap = read('../exp652/doc/eda比赛文件/arch/SRB_Gap.json')['Gap']
    h, v, bands, ends = fit.prior.events(data['features'][:, 28:32], gap['Block'])
    assert np.array_equal(h, data['features'][:, 52]) and not np.any(h & v)
    event = h.astype('u1')+2*v
    x = np.column_stack((data['features'], fit.prior.source.geometry(data['features'], gap),
                         bands, ends)).astype('<f4')
    assert x.shape == (fit.ROWS, 71) and np.array_equal(x, np.floor(x))
    return data, x, event


def train():
    start, cpu = time.monotonic(), time.process_time()
    selected = read('../exp678/validation/results/exp678/evaluation.json')
    assert selected['selected'] == 'HV64' and selected['continue_cli']
    original = read('../exp678/validation/results/exp678/freeze.json')
    assert original['params'] == fit.PARAMS
    for item in original['files']:
        check(Path('../exp678')/item['path'], item)
    ROOT.mkdir(parents=True, exist_ok=False)
    BUILD.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(PLAN, ROOT/'protocol-original.md')
    (ROOT/'installed-catboost-help.txt').write_text(fit.cb.__version__+'\n'
        + str(inspect.signature(fit.cb.CatBoostRegressor.fit))+'\n'
        + str(inspect.signature(fit.cb.CatBoostRegressor.calc_leaf_indexes))+'\n'
        + fit.cb.CatBoostRegressor.save_model.__doc__)
    write(ROOT/'training-freeze.json', dict(params=fit.PARAMS,
        development_selection=identity('../exp678/validation/results/exp678/evaluation.json'),
        files=[identity(p) for p in (Path(__file__), PLAN, ROOT/'protocol-original.md',
            Path(fit.__file__), Path(fit.prior.__file__), Path(fit.prior.source.__file__))],
        deployment_selection='HV64', complete_program_runs=0))
    data, x, event = dataset()
    target = (data['d0']-data['base']).astype('<f4')
    weight = (1000/np.maximum(data['d0']+data['mandatory'], 128)).astype('<f4')
    records, predict = [], fit.decoder()
    raw = np.fromfile('../exp640/build/exp640/S8-final.f64', '<f8')
    check('../exp640/build/exp640/S8-final.f64',
          read('../exp640/validation/results/exp640/final-training.json')['raw']['S8'])
    for label, value in (('H', 1), ('V', 2)):
        members = event == value
        model = fit.cb.CatBoostRegressor(**fit.PARAMS)
        model.fit(x[members], target[members], sample_weight=weight[members])
        assert model.tree_count_ == 64
        path = BUILD/f'{label}64-final.json'
        model.save_model(str(path), format='json')
        decoded, indices = predict(read(path), x[members], 64)
        native = model.predict(x[members], thread_count=1)
        assert np.array_equal(indices, model.calc_leaf_indexes(x[members], thread_count=1))
        assert np.allclose(decoded, native, rtol=0, atol=1e-10)
        assert np.array_equal(fit.decode(decoded, data['base'][members], data['mandatory'][members]),
                              fit.decode(native, data['base'][members], data['mandatory'][members]))
        raw[members] = decoded
        records.append(dict(event=label, model=identity(path), train_rows=int(members.sum()),
            params=model.get_all_params(), native_leaf_ids_equal=True,
            integer_prediction_equal=True, raw_max_abs_difference=float(np.abs(decoded-native).max())))
        print('EXP679_FINAL_TRAINED', label, int(members.sum()), flush=True)
        del model
        gc.collect()
    raw.tofile(BUILD/'final.f64')
    x[:, 53:].astype('<i4').tofile(BUILD/'expected-extra.i4')
    report = dict(records=records, final_raw=identity(BUILD/'final.f64'),
        extra=identity(BUILD/'expected-extra.i4'), cpu_s=time.process_time()-cpu,
        wall_s=time.monotonic()-start, rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    assert report['cpu_s'] <= 600 and report['wall_s'] <= 900
    assert report['rss_bytes'] <= 2_000_000_000
    write(ROOT/'final-training.json', report)


def emit():
    # Reuse the established expression parser without importing old training modules.
    path = Path('../exp622/validation/exp622_r8_specialization.py')
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'feature_list')
    scope = dict(re=re)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    _, fields = scope['feature_list']((OLD/'build/exp654/worker.cpp').read_text())
    fields += [f'int(z[{j}])' for j in range(16)]+['bands', 'ends']
    final = read(ROOT/'final-training.json')['records']
    oof = read('../exp678/validation/results/exp678/training.json')['records']
    records = final + [next(r for r in oof if r['fold'] == k and r['event'] == label)
                       for k in range(3) for label in ('H', 'V')]
    models = []
    for index, record in enumerate(records):
        path = Path(record['model']['path'])
        if index >= 2:
            path = Path('../exp678')/path
        check(path, record['model'])
        model = read(path)
        assert model['scale_and_bias'] == [1, [0]]
        mapping = {f['feature_index']: f['flat_feature_index']
                   for f in model['features_info']['float_features']}
        assert len(model['oblivious_trees']) == 64
        splits, values = [], []
        for tree in model['oblivious_trees']:
            conditions = []
            for split in tree['splits'] or []:
                assert split['split_type'] == 'FloatFeature'
                conditions.append((mapping[split['float_feature_index']],
                                   int(np.floor(split['border']))+1))
            assert len(conditions) <= 4 and len(tree['leaf_values']) == 1 << len(conditions)
            splits.append(conditions)
            values.append(tree['leaf_values']+[0.]*(16-len(tree['leaf_values'])))
        models.append((splits, values))
    text = ['#pragma once', '#include "exp614_geometry_features.h"',
            'static constexpr double kLeaves679[][64][16]={']
    for index, (_, values) in enumerate(models):
        if index == 2:
            text.append('#ifdef EXP579_AUDIT')
        text.append('{'+','.join('{'+','.join(float(v).hex() for v in row)+'}'
                                for row in values)+'},')
    text += ['#endif', '};',
        'static inline double replacement679(const int32_t* q,int ax,int ay,int ndx,int ndy,',
        'int x,int y,[[maybe_unused]] int fee,[[maybe_unused]] bool forced,',
        'unsigned fold,unsigned event,[[maybe_unused]] int bands,[[maybe_unused]] int ends,',
        'unsigned char* leaves=nullptr,const float* expected=nullptr) {',
        '[[maybe_unused]] const int sx=q[0],sy=q[1],tx=q[2],ty=q[3];',
        '[[maybe_unused]] const int sf=q[4],sl=q[5],tf=q[6],tl=q[7];',
        'float g[53]{}; g[28]=float(ax); g[29]=float(ay); g[30]=float(tx); g[31]=float(ty);',
        'float z[16]; geometry614(g,z);',
        'switch(2*fold+event-1) {']
    for index, (splits, _) in enumerate(models):
        if index == 2:
            text.append('#ifdef EXP579_AUDIT')
        text += [f'case {index}: {{', 'double result=0.;']
        for f in sorted({f for tree in splits for f, _ in tree}):
            text += [f'const int f{f}={fields[f]};',
                     f'if(expected) require(f{f}==expected[{f}],"expert active feature");']
        for t, conditions in enumerate(splits):
            expression = '|'.join(f'(unsigned(f{f}>={cut})<<{j})'
                                  for j, (f, cut) in enumerate(conditions)) or '0'
            text += [f'const unsigned p{t}={expression};',
                     f'result+=kLeaves679[{index}][{t}][p{t}];',
                     f'if(leaves) leaves[{t}]=p{t};']
        text += ['return result;', '}']
    text += ['#endif', 'default: require(false,"expert route"); return 0.;', '}', '}', '']
    (BUILD/'replacement679.h').write_text('\n'.join(text))


CHECKER = r'''
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
static void require(bool b,const char* why) {
    if(!b) { std::fprintf(stderr,"%s\n",why); std::exit(1); }
}
static inline int side(int x) { return x<76?0:x<90?1:2; }
static inline int mod(int x,int base) { int r=x%base; return r<0?r+base:r; }
#define EXP579_AUDIT
#include "replacement679.h"
#include "exp679_hv_events.h"
int main(int argc,char** argv) {
    require(argc==6,"check FEATURES QUERIES FOLDS EXTRA OUTPUT");
    FILE *features=std::fopen(argv[1],"rb"),*queries=std::fopen(argv[2],"rb"),
         *folds=std::fopen(argv[3],"rb"),*extra=std::fopen(argv[4],"rb"),
         *output=std::fopen(argv[5],"wb");
    require(features&&queries&&folds&&extra&&output,"files");
    char magic[8]; uint32_t count,width;
    require(std::fread(magic,1,8,features)==8&&!std::memcmp(magic,"E554F001",8)&&
        std::fread(&count,4,1,features)==1&&count==1000000&&
        std::fread(&width,4,1,features)==1&&width==53,"features header");
    require(std::fread(magic,1,8,queries)==8&&!std::memcmp(magic,"EX535Q01",8)&&
        std::fread(&count,4,1,queries)==1&&count==1000000,"queries header");
    unsigned events[3]{},seen[8]{};
    for(uint32_t row=0;row<count;++row) {
        float f[71]; int32_t q[10],e[18]; unsigned char fold;
        require(std::fread(f,4,53,features)==53&&std::fread(q,4,10,queries)==10&&
            std::fread(&fold,1,1,folds)==1&&fold<3&&std::fread(e,4,18,extra)==18,"row");
        for(unsigned j=0;j<18;++j) f[53+j]=float(e[j]);
        float z[16]; geometry614(f,z);
        for(unsigned j=0;j<16;++j) require(z[j]==f[53+j],"extra geometry");
        int bands,ends;
        const unsigned event=event679(int(f[28]),int(f[29]),int(f[30]),int(f[31]),
                                     bool(f[52]),bands,ends);
        require(ends==e[17],"central endpoints");
        require(event==unsigned(f[52]?1:(e[17]==2&&e[16]>0?2:0)),"event");
        // Ordinary rows do not consume bands; expert rows must match all inputs.
        if(event) require(bands==e[16],"expert bands");
        ++events[event];
        if(!event) continue;
        double raw[2]; unsigned char leaves[2][64]{};
        for(unsigned stage=0;stage<2;++stage) {
            const unsigned k=stage?unsigned(fold)+1:0;
            raw[stage]=replacement679(q,int(f[28]),int(f[29]),int(f[6]),int(f[7]),
                int(f[8]),int(f[9]),int(f[50]),bool(f[52]),k,event,bands,ends,leaves[stage],f);
            ++seen[2*k+event-1];
        }
        require(std::fwrite(&row,4,1,output)==1&&std::fwrite(&event,4,1,output)==1&&
            std::fwrite(raw,8,2,output)==2&&std::fwrite(leaves,1,128,output)==128,"write");
    }
    for(unsigned n:seen) require(n>0,"model coverage");
    for(FILE* p:{features,queries,folds,extra}) require(std::fgetc(p)==EOF,"EOF");
    for(FILE* p:{features,queries,folds,extra,output}) require(std::fclose(p)==0,"close");
    std::printf("{\"rows\":%u,\"events\":[%u,%u,%u],\"models\":8,\"all_features_equal\":true}\n",
        count,events[0],events[1],events[2]);
}
'''


def build():
    frozen = read(OLD/'validation/results/exp654/freeze.json')
    recovery = read(OLD/'validation/results/exp654/driver-recovery-freeze.json')
    assert not recovery['models_changed'] and not recovery['compiled_assets_changed']
    for item in frozen['files']:
        expected = recovery['updated_driver'] if item == recovery['original_driver'] else item
        check(OLD/item['path'], expected)
    check(BASELINE, frozen['binaries']['B'])
    assert identity(BASELINE)['sha256'] == 'd9a8194584b644ffa331d31a8713a39f559b881a1fe40e8f0dce4d4ad8ff58dd'
    for path in sorted((OLD/'build/exp654').iterdir()):
        if path.suffix in ('.h', '.cpp'):
            shutil.copy2(path, BUILD/path.name)
    restore = BUILD/'exp652_geometry_restore.h'
    restore.write_text(replace(restore.read_text(), '"build/exp652/restored.bin"',
                               f'"{BUILD}/restored.bin"'))
    for name in ('exp614_geometry_features.h', 'exp679_hv_events.h'):
        shutil.copy2(Path('tests')/name, BUILD/name)
    emit()
    worker = (BUILD/'worker.cpp').read_text()
    worker = replace(worker, '#include "symmetric640.h"',
                     '#include "symmetric640.h"\n#include "replacement679.h"\n#include "exp679_hv_events.h"')
    before = 'const double raw=symmetric640(q,ax,ay,ndx,ndy,x,y,fee,forced,route,fold);'
    after = '''int bands,ends;
    const unsigned event=event679(ax,ay,tx,ty,forced,bands,ends);
    const double raw=event ? replacement679(q,ax,ay,ndx,ndy,x,y,fee,forced,fold,event,bands,ends) :
        symmetric640(q,ax,ay,ndx,ndy,x,y,fee,forced,route,fold);'''
    (BUILD/'worker.cpp').write_text(replace(worker, before, after))
    changes = {'build/exp654/codes.o': str(OLD/'build/exp654/codes.o'),
               'build/exp654': str(BUILD), 'build/exp654/worker.cpp': str(BUILD/'worker.cpp'),
               'build/exp654/B.o': str(BUILD/'C.o'), 'build/exp654/B': str(BUILD/'C')}
    compile_command = [changes.get(a, a) for a in frozen['compile_command']]
    link_command = [changes.get(a, a) for a in frozen['link_command']]
    audit_compile = [str(BUILD/'audit.o') if a == str(BUILD/'C.o') else a for a in compile_command]
    audit_link = [str(BUILD/'audit.o') if a == str(BUILD/'C.o') else
                  str(BUILD/'audit') if a == str(BUILD/'C') else a for a in link_command]
    (BUILD/'expert-check.cpp').write_text(CHECKER)
    checker_command = ['g++', '-std=c++17', '-O3', '-fno-fast-math', '-ffp-contract=off',
        '-march=x86-64', '-mtune=generic', '-Wall', '-Wextra', '-Werror', '-I', str(BUILD),
        str(BUILD/'expert-check.cpp'), '-static', '-s', '-o', str(BUILD/'expert-check')]
    for name, command in (('compile-C', compile_command), ('link-C', link_command),
        ('compile-audit', audit_compile+['-DEXP579_AUDIT']), ('link-audit', audit_link),
        ('compile-expert-check', checker_command)):
        speed.measured(command, name)
        assert not (ROOT/(name+'.stderr')).read_bytes()
    for name in ('C', 'audit', 'expert-check'):
        binary = BUILD/name
        linked = subprocess.run(['ldd', str(binary)], capture_output=True, text=True)
        assert 'not a dynamic executable' in linked.stdout+linked.stderr
        assert 'INTERP' not in subprocess.check_output(['readelf', '-l', str(binary)], text=True)
        assert binary.stat().st_size < 100_000_000
    files = [Path(__file__), PLAN, ROOT/'protocol-original.md', Path('validation/exp679_run.sh'),
        ROOT/'final-training.json', ROOT/'training-freeze.json',
        *[p for p in BUILD.iterdir() if p.suffix in ('.h', '.cpp', '.json')],
        *[Path(a) for a in link_command if a.endswith(('.o', '.a', '.cpp')) and a != str(BUILD/'C.o')]]
    write(ROOT/'build-freeze.json', dict(files=[identity(p) for p in files],
        binaries=dict(A=identity(BASELINE), C=identity(BUILD/'C')),
        audit_binary=identity(BUILD/'audit'), expert_checker=identity(BUILD/'expert-check'),
        compile_command=compile_command, link_command=link_command, static_linked=True,
        host=socket.gethostname(), complete_program_runs=0))
    print('EXP679_STATIC_BUILT', identity(BUILD/'C'), flush=True)


def audit():
    frozen = freeze_check()
    data, x, event = dataset()
    extra = read(ROOT/'final-training.json')['extra']
    check(extra['path'], extra)
    check(BUILD/'expert-check', frozen['expert_checker'])
    leaf_path = BUILD/'expert-check.bin'
    speed.measured([str(BUILD/'expert-check'), '../exp631/build/exp631/features.f32',
        '../exp579/build/exp579/queries.bin', '../exp579/build/exp579/folds.u8',
        str(extra['path']), str(leaf_path)], 'cached-expert-check')
    meta = read(ROOT/'cached-expert-check.stdout')
    assert meta['events'] == np.bincount(event, minlength=3).tolist()
    dtype = np.dtype([('row', '<u4'), ('event', '<u4'), ('raw', '<f8', (2,)),
                      ('leaves', 'u1', (2, 64))])
    out = np.fromfile(leaf_path, dtype)
    assert np.array_equal(out['row'], np.flatnonzero(event))
    assert np.array_equal(out['event'], event[out['row']])
    predict = fit.decoder()
    records = read(ROOT/'final-training.json')['records']
    oof = read('../exp678/validation/results/exp678/training.json')['records']
    for stage in range(2):
        for label, value in (('H', 1), ('V', 2)):
            for fold in (range(3) if stage else [-1]):
                mask = (out['event'] == value)
                if stage:
                    mask &= data['folds'][out['row']] == fold
                record = next(r for r in (oof if stage else records)
                              if r['event'] == label and (not stage or r['fold'] == fold))
                path = Path('../exp678')/record['model']['path'] if stage else Path(record['model']['path'])
                rows = out['row'][mask]
                raw, leaves = predict(read(path), x[rows], 64)
                assert np.array_equal(out['leaves'][mask, stage], leaves)
                assert np.array_equal(out['raw'][mask, stage].view('u8'), raw.view('u8'))
    old_final = np.fromfile('../exp640/build/exp640/S8-final.f64', '<f8')
    old_oof = np.fromfile(fit.prior.OLD_RAW, '<f8')
    expected = {1: np.fromfile(BUILD/'final.f64', '<f8'), 0: old_oof.copy()}
    replacement = np.fromfile('../exp678/build/exp678/HV64-raw.f64', '<f8')
    expected[0][event != 0] = replacement[event != 0]
    trace_type = np.dtype(dict(names=['features', 'response', 'base', 'mandatory', 'prediction', 'raw'],
        formats=[('<f4', (53,)), '<f8', '<i4', '<i4', '<i4', '<f8'],
        offsets=[0, 216, 224, 228, 232, 240], itemsize=248))
    traces = []
    for mode in (0, 1):
        path = BUILD/f'cached-trace-{mode}.bin'
        speed.measured([str(BUILD/'audit'), '../exp579/build/exp579/queries.bin',
            '../exp579/build/exp579/folds.u8', str(path), str(mode)], f'cached-worker-{mode}')
        assert read(ROOT/f'cached-worker-{mode}.stdout')['trace_bytes'] == 248
        trace = np.memmap(path, dtype=trace_type, mode='r', shape=(fit.ROWS,))
        assert np.array_equal(trace['features'], data['features'])
        assert np.array_equal(trace['base'], data['base'])
        assert np.array_equal(trace['mandatory'], data['mandatory'])
        assert np.array_equal(trace['raw'].copy().view('u8'), expected[mode].view('u8'))
        assert np.array_equal(trace['prediction'], fit.decode(expected[mode], data['base'], data['mandatory']))
        ordinary = event == 0
        old = old_final if mode else old_oof
        assert np.array_equal(trace['prediction'][ordinary],
            fit.decode(old[ordinary], data['base'][ordinary], data['mandatory'][ordinary]))
        traces.append(identity(path))
    restored = BUILD/'restored.bin'
    check(restored, read('../exp652/validation/results/exp652/build-freeze.json')['restored_expected'])
    write(ROOT/'numeric-audit.json', dict(cached_rows=fit.ROWS, complete_estimator_runs=0,
        final_prediction_equal=True, oof_prediction_equal=True, ordinary_predictions_equal=True,
        base_equal=True, mandatory_equal=True, raw_bitwise_equal=True, all_leaf_ids_equal=True,
        all_features_equal=True, event_counts=meta['events'], traces=traces,
        expert_check=identity(leaf_path), restored_geometry=identity(restored),
        final_accuracy_goal_verified=False))
    print('EXP679_CACHED_NUMERICAL_AUDIT_PASSED', flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp679')
    resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
    assert len(sys.argv) == 2 and sys.argv[1] in ('train', 'build', 'audit')
    {'train': train, 'build': build, 'audit': audit}[sys.argv[1]]()
