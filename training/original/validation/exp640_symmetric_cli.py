#!/usr/bin/env python3
"""Deploy the two preregistered symmetric-tree budgets on the frozen Q4 path."""
import csv
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

import exp640_symmetric_residual as fit

sys.path.insert(0, str(Path('../exp622/validation').resolve()))
import exp622_r8_specialization as old

ROOT, BUILD = fit.ROOT, fit.BUILD
read, write, identity, checked = fit.read, fit.write, fit.identity, fit.checked
speed = old.speed
speed.ROOT = ROOT


def final():
    assert all(v['continue_cli'] for v in read(ROOT / 'evaluation.json')['eligible'].values())
    assert not (ROOT / 'final-training.json').exists()
    frozen = read(ROOT / 'prepare.json')
    assert frozen['params'] == fit.PARAMS
    for item in frozen['files']:
        checked(item['path'], item)
    data = fit.prior.load()
    target = (data['d0'] - data['base']).astype('<f4')
    weight = (1000 / np.maximum(data['d0'] + data['mandatory'], 128)).astype('<f4')
    raw = {n: np.empty(fit.ROWS, '<f8') for n in (8, 16)}
    records = []
    for route in range(16):
        members = data['routes'] == route
        model = fit.cb.CatBoostRegressor(**fit.PARAMS)
        model.fit(data['features'][members], target[members], sample_weight=weight[members])
        path = BUILD / f'S16-final-{route}.json'
        model.save_model(str(path), format='json')
        dumped, x = read(path), data['features'][members]
        leaf = model.calc_leaf_indexes(x, thread_count=1)
        difference = {}
        for n in raw:
            decoded, indices = fit.json_prediction(dumped, x, n)
            native = model.predict(x, ntree_end=n, thread_count=1)
            assert np.array_equal(indices, leaf[:, :n])
            assert np.allclose(decoded, native, rtol=0, atol=1e-12)
            assert np.array_equal(fit.prior.decode(decoded, data['base'][members], data['mandatory'][members]),
                                  fit.prior.decode(native, data['base'][members], data['mandatory'][members]))
            raw[n][members] = decoded
            difference[str(n)] = float(np.abs(decoded - native).max())
        records.append(dict(route=route, model=identity(path), train_rows=int(members.sum()),
            params=model.get_all_params(), leaf_index_equal=True, raw_max_abs_difference=difference))
        print('EXP640_FINAL_MODEL', route, flush=True)
    for n, values in raw.items():
        values.tofile(BUILD / f'S{n}-final.f64')
    write(ROOT / 'final-training.json', dict(records=records,
        raw={f'S{n}': identity(BUILD / f'S{n}-final.f64') for n in raw},
        driver=identity(__file__), selection_uses_oof_only=True))


def emit():
    records = read(ROOT / 'final-training.json')['records'] + read(ROOT / 'training.json')['records']
    assert len(records) == 64
    models = []
    for record in records:
        checked(record['model']['path'], record['model'])
        model = read(record['model']['path'])
        assert model['scale_and_bias'] == [1, [0]]
        mapping = {f['feature_index']: f['flat_feature_index']
                   for f in model['features_info']['float_features']}
        trees = model['oblivious_trees']
        assert len(trees) == 16
        splits = [[(mapping[s['float_feature_index']], int(np.floor(s['border'])) + 1)
                   for s in (tree['splits'] or [])] for tree in trees]
        assert all(len(s) <= 4 for s in splits)
        assert all(s['split_type'] == 'FloatFeature' for t in trees for s in (t['splits'] or []))
        values = [t['leaf_values'] + [0.] * (16 - len(t['leaf_values'])) for t in trees]
        assert all(len(t['leaf_values']) == 1 << len(s) for t, s in zip(trees, splits))
        models.append((splits, values))
    source = Path('../exp622/build/exp622/T-worker.cpp').read_text()
    _, features = old.feature_list(source)
    text = ['#pragma once', 'static constexpr double kSymmetric640[][16][16]={']
    for route, (_, values) in enumerate(models):
        if route == 16:
            text.append('#ifdef EXP579_AUDIT')
        text.append('{' + ','.join('{' + ','.join(float(v).hex() for v in t) + '}' for t in values) + '},')
    text += ['#endif', '};', 'static inline __attribute__((always_inline)) double symmetric640(',
        'const int32_t* q,int ax,int ay,int ndx,int ndy,int x,int y,int fee,bool forced,',
        'unsigned route,unsigned fold,unsigned char* leaves=nullptr,const int* expected=nullptr) {',
        'const int sx=q[0],sy=q[1],tx=q[2],ty=q[3];',
        'const int sf=q[4],sl=q[5],tf=q[6],tl=q[7];', 'switch(16*fold+route) {']
    for route, (splits, _) in enumerate(models):
        if route == 16:
            text.append('#ifdef EXP579_AUDIT')
        text += [f'case {route}: {{', 'double result=0.;']
        for f in sorted({f for tree in splits for f, _ in tree}):
            text += [f'const int f{f}={features[f]};',
                     f'if(expected) require(f{f}==expected[{f}],"symmetric active feature");']
        for tree, conditions in enumerate(splits):
            text += [f'#if EXP640_TREES > {tree}',
                     f'const unsigned p{tree}=' + ('|'.join(
                         f'(unsigned(f{f}>={cut})<<{j})' for j, (f, cut) in enumerate(conditions)) or '0') + ';',
                     f'result+=kSymmetric640[{route}][{tree}][p{tree}];',
                     f'if(leaves) leaves[{tree}]=p{tree};', '#endif']
        text += ['return result;', '}']
    text += ['#endif', 'default: require(false,"symmetric route"); return 0.;', '}', '}', '']
    (BUILD / 'symmetric640.h').write_text('\n'.join(text))
    return source


CHECKER = r"""
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
#include "symmetric640.h"
int main(int argc,char** argv) {
    require(argc==5,"checker FEATURES QUERIES FOLDS OUTPUT");
    FILE *features=std::fopen(argv[1],"rb"),*queries=std::fopen(argv[2],"rb"),
         *folds=std::fopen(argv[3],"rb"),*output=std::fopen(argv[4],"wb");
    require(features&&queries&&folds&&output,"files");
    char magic[8]; uint32_t count,width;
    require(std::fread(magic,1,8,features)==8&&!std::memcmp(magic,"E554F001",8)&&
        std::fread(&count,4,1,features)==1&&count==1000000&&
        std::fread(&width,4,1,features)==1&&width==53,"features header");
    require(std::fread(magic,1,8,queries)==8&&!std::memcmp(magic,"EX535Q01",8)&&
        std::fread(&count,4,1,queries)==1&&count==1000000,"queries header");
    bool seen[64]{};
    for(unsigned row=0;row<count;++row) {
        float values[53]; int f[53]; int32_t q[10]; unsigned char fold;
        require(std::fread(values,4,53,features)==53&&std::fread(q,4,10,queries)==10&&
            std::fread(&fold,1,1,folds)==1&&fold<3,"row");
        for(unsigned j=0;j<53;++j) {
            f[j]=int(values[j]); require(float(f[j])==values[j],"integer feature");
        }
        int nx=f[8]+f[6],ny=f[9]+f[7];
        unsigned route=4*(2*(nx<0)+(ny<0))+2*(std::abs(nx)>=20)+(std::abs(ny)>=24);
        for(unsigned stage=0;stage<2;++stage) {
            unsigned char leaves[16]{};
            unsigned k=stage?unsigned(fold)+1:0;
            double raw=symmetric640(q,f[28],f[29],f[6],f[7],f[8],f[9],f[50],
                f[52],route,k,leaves,f);
            require(std::fwrite(&raw,8,1,output)==1&&std::fwrite(leaves,1,16,output)==16,"write");
            seen[16*k+route]=true;
        }
    }
    for(bool s:seen) require(s,"route coverage");
    require(std::fgetc(features)==EOF&&std::fgetc(queries)==EOF&&std::fgetc(folds)==EOF,"EOF");
    require(!std::fclose(features)&&!std::fclose(queries)&&!std::fclose(folds)&&!std::fclose(output),"close");
    std::puts("{\"rows\":1000000,\"models\":64,\"active_features_equal\":true}");
}
"""


def build():
    assert not (ROOT / 'cli-freeze.json').exists()
    frozen = read('../exp622/validation/results/exp622/build-freeze.json')
    checked('../exp622/build/exp622/T', frozen['binaries']['T'])
    source = emit()
    source = old.replace(source, '#include "native622.h"', '#include "symmetric640.h"')
    source = old.replace(source, 'const float raw=native622(', 'const double raw=symmetric640(')
    source = old.replace(source, 'float raw=0.f;', 'double raw=0.;')
    source = old.replace(source, 'const float raw=state.raw;', 'const double raw=state.raw;')
    source = old.replace(source, '    float raw;', '    double raw;')
    (BUILD / 'symmetric-worker.cpp').write_text(source)
    for name in ('entry.cpp', 'exp608_geometry.h', 'exp596_csv_batch.h', 'exp601_port_parser.h'):
        shutil.copyfile(Path('../exp622/build/exp622') / name, BUILD / name)
    (BUILD / 'symmetric-check.cpp').write_text(CHECKER)
    data, audits, binaries = fit.prior.load(), {}, {'A': identity('../exp622/build/exp622/T')}
    request = Path('../exp501/build/exp501/u-role/requests.csv')
    labels = Path('../exp501/build/exp501/exact.csv')
    for n in (8, 16):
        arm = f'S{n}'
        command = ['g++', '-std=c++17', '-O3', '-static', '-march=x86-64', '-mtune=generic',
            '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
            '-DEXP579_AUDIT', f'-DEXP640_TREES={n}', '-I', str(BUILD),
            str(BUILD / 'symmetric-check.cpp'), '-o', str(BUILD / (arm + '-check'))]
        speed.measured(command, 'compile-' + arm + '-check')
        assert not (ROOT / ('compile-' + arm + '-check.stderr')).read_bytes()
        output = BUILD / (arm + '-audit.bin')
        speed.measured([str(BUILD / (arm + '-check')), '../exp631/build/exp631/features.f32',
            '../exp579/build/exp579/queries.bin', '../exp579/build/exp579/folds.u8', str(output)],
            arm + '-audit')
        actual = np.memmap(output, dtype=[('raw', '<f8'), ('leaf', 'u1', (16,))],
                           mode='r', shape=(fit.ROWS, 2))
        for stage, suffix in enumerate(('final', 'raw')):
            expected = np.fromfile(BUILD / f'{arm}-{suffix}.f64', '<f8')
            assert np.array_equal(actual['raw'][:, stage].copy().view('u8'), expected.view('u8'))
            for fold in ([0] if stage == 0 else [1, 2, 3]):
                for route in range(16):
                    members = data['routes'] == route
                    if fold:
                        members &= data['folds'] == fold - 1
                    tag = 'final' if not fold else str(fold - 1)
                    _, leaf = fit.json_prediction(read(BUILD / f'S16-{tag}-{route}.json'),
                                                  data['features'][members], n)
                    assert np.array_equal(actual['leaf'][members, stage, :n], leaf)
        changes = {'build/exp622': str(BUILD),
            'build/exp622/T-worker.cpp': str(BUILD / 'symmetric-worker.cpp'),
            'build/exp622/T.o': str(BUILD / (arm + '.o'))}
        command = read('../exp622/validation/results/exp622/compile-T.run.json')['command']
        speed.measured([changes.get(a, a) for a in command] + [f'-DEXP640_TREES={n}'], 'compile-' + arm)
        assert not (ROOT / ('compile-' + arm + '.stderr')).read_bytes()
        changes.update({'build/exp622/entry.cpp': str(BUILD / 'entry.cpp'),
                        'build/exp622/T': str(BUILD / arm)})
        command = read('../exp622/validation/results/exp622/link-T.run.json')['command']
        speed.measured([changes.get(a, a) for a in command], 'link-' + arm)
        assert not (ROOT / ('link-' + arm + '.stderr')).read_bytes()
        binary = BUILD / arm
        linked = subprocess.run(['ldd', str(binary)], capture_output=True, text=True)
        assert 'not a dynamic executable' in linked.stdout + linked.stderr
        assert binary.stat().st_size < 100000000
        assert 'INTERP' not in subprocess.check_output(['readelf', '-l', str(binary)], text=True)
        raw = np.fromfile(BUILD / f'{arm}-final.f64', '<f8')
        expected = fit.prior.decode(raw, data['base'], data['mandatory'])
        expected.astype('<i4').tofile(BUILD / (arm + '-expected.i32'))
        result = BUILD / (arm + '-development.csv')
        run = speed.measured([str(binary), '-in', str(request), '-out', str(result)], arm + '-development')
        prediction, truth, contract, _ = old.prior.complete.check_output(
            request, result, labels, BUILD / (arm + '-expected.i32'))
        assert np.array_equal(prediction, expected) and np.array_equal(truth, data['truth'])
        assert read(run['stderr']) == dict(rows=fit.ROWS, unreachable=0, query_allocations=0)
        assert run['threads'] == 1 and run['rss_bytes'] <= 2000000000 and run['cpu_s'] <= 3600
        boundary = Path('../exp622/build/exp622/boundary-current.csv')
        boundary_output = BUILD / (arm + '-boundary.csv')
        edge_run = speed.measured([str(binary), '-in', str(boundary), '-out', str(boundary_output)],
                                  arm + '-boundary')
        with boundary.open(newline='') as stream:
            queries = list(csv.reader(stream))[1:]
        with boundary_output.open(newline='') as stream:
            rows = csv.reader(stream)
            assert next(rows) == ['From', 'To', 'delay']
            edges = list(rows)
        with Path('../exp622/build/exp622/boundary-current-A.csv').open(newline='') as stream:
            reference_edges = list(csv.reader(stream))[1:]
        assert len(edges) == len(queries) and boundary_output.read_bytes().endswith(b'\n')
        assert all(len(r) == 3 and r[:2] == q and r[2] == str(int(r[2])) for q, r in zip(queries, edges))
        assert edges[32:66] == reference_edges[32:66]
        assert read(edge_run['stderr']) == dict(rows=len(edges),
            unreachable=sum(int(r[2]) < 0 for r in edges), query_allocations=0)
        assert edge_run['threads'] == 1 and edge_run['rss_bytes'] <= 2000000000
        binaries[arm] = identity(binary)
        audits[arm] = dict(raw_bitwise_equal=True, leaf_ids_equal=True, active_features_equal=True,
            audit=identity(output), run=run, contract=contract, development=identity(result),
            boundary=identity(boundary_output), boundary_run=edge_run,
            zero_and_unsupported_equal=True)
        print('EXP640_CLI_BUILT', arm, binaries[arm]['bytes'], flush=True)
    write(ROOT / 'cli-freeze.json', dict(binaries=binaries, audits=audits,
        native=identity(BUILD / 'symmetric640.h'), source=identity(BUILD / 'symmetric-worker.cpp'),
        final_training=identity(ROOT / 'final-training.json'), driver=identity(__file__),
        raw_precision='double, original order, original leaves', performance_comparison_pending=True))


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp640')
    assert len(sys.argv) == 2 and sys.argv[1] in ('final', 'build')
    start, cpu = time.monotonic(), time.process_time()
    {'final': final, 'build': build}[sys.argv[1]]()
    write(ROOT / ('cli-' + sys.argv[1] + '-resources.json'), dict(
        cpu_s=time.process_time()-cpu, wall_s=time.monotonic()-start,
        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        disk_free_end_bytes=shutil.disk_usage('.').free))
