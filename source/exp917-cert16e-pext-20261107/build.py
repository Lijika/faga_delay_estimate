#!/usr/bin/env python3
"""Build fast/exact Linux x86-64 static ELF using ONLY bundled data and files.

Examples:
  python3 build.py --variant both --mode source
  python3 build.py --variant fast --mode frozen
  python3 build.py --variant exact --mode source --out-dir /tmp/mybin

A donor executable, network connection, pip dependency, or external model file
is not needed. Frozen mode uses bundled historic .o files; source mode compiles
all project C++ from source. The bundled libzstd.a is a static third-party link
asset, and is accompanied by the license.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
META = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
ALIAS = {'fast': 'speed', 'exact': 'exact'}
SIZE_LIMIT = 100_000_000

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):
            h.update(part)
    return h.hexdigest()

def exec_cmd(args, cwd, quiet=False):
    cmd=list(map(str,args))
    if not quiet:
        print('+', ' '.join(cmd), flush=True)
    subprocess.run(cmd,cwd=cwd,check=True)

def check_assets():
    info=META['variants']['speed']['assets']
    for filename,meta in info.items():
        p=ROOT/'model'/filename
        if not p.is_file():
            raise RuntimeError(f'Missing model file {p}')
        if p.stat().st_size!=meta['bytes'] or sha256(p)!=meta['sha256']:
            raise RuntimeError(f'Incorrect model file: {p}')
    for required in ('near/mask.zst','near/topology.dat','libraries/libzstd.a',
                     'libraries/zstd.h','libraries/COPYRIGHT.libzstd',
                     'shared/entry.cpp','shared/architecture.cpp',
                     'shared/arch.cpp','near/near40.cpp',
                     'speed/worker.cpp','exact/worker.cpp'):
        if not (ROOT/required).is_file():
            raise RuntimeError(f'Missing required build dependency: {required}')

def build(variant, mode, outdir, cxx, cc, quiet):
    src=ALIAS[variant]
    outpath=outdir/variant/'estimate'
    outpath.parent.mkdir(parents=True, exist_ok=True)
    includes=['-I',ROOT/src,'-I',ROOT/'shared','-I',ROOT/'near','-I',ROOT/'libraries']
    with tempfile.TemporaryDirectory(prefix='.build-estimate-',dir=outpath.parent) as temp:
        work=Path(temp)
        for name in META['variants']['speed']['assets']:
            os.symlink(ROOT/'model'/name,work/name)
        (work/'aq.S').write_text('''\
.section .rodata
.p2align 6
.global aqframes
aqframes:
.incbin "frames.bin"
.p2align 6
.global aqBooks
aqBooks:
.incbin "books.f32"
.section .note.GNU-stack,"",@progbits
''')
        (work/'arch.S').write_text('''\
.section .rodata
.global aqarch
aqarch:
.incbin "arch.bin"
.section .note.GNU-stack,"",@progbits
''')
        exec_cmd([cc,'-c','aq.S','-o','aq.o'],work,quiet)
        exec_cmd([cc,'-c','arch.S','-o','arch-data.o'],work,quiet)
        if mode=='source':
            worker=work/'worker.o'
            exec_cmd([cxx,*META['cc'][src],*includes,'-c',ROOT/src/'worker.cpp','-o',worker],work,quiet)
            near,graph,arch,resolver=(work/x for x in ('near.o','graph.o','arch.o','resolver.o'))
            exec_cmd([cxx,'-std=c++17','-O3','-march=x86-64','-mtune=generic',
                      '-fno-rtti','-fno-exceptions','-Wall','-Wextra','-Werror',
                      *includes,'-c',ROOT/'near/near40.cpp','-o',near],work,quiet)
            for name in ('mask.zst','topology.dat'):
                os.symlink(ROOT/'near'/name,work/name)
            (work/'near-assets.S').write_text('''\
.section .rodata
.p2align 6
.global zsupport,zsupportEnd,near40graph,near40graphend
zsupport:
.incbin "mask.zst"
zsupportEnd:
.p2align 1
near40graph:
.incbin "topology.dat"
near40graphend:
.section .note.GNU-stack,"",@progbits
''')
            exec_cmd([cc,'-c','near-assets.S','-o',graph],work,quiet)
            exec_cmd([cxx,'-O2','-std=c++17','-march=x86-64','-mtune=generic','-fno-exceptions',*includes,
                      '-c',ROOT/'shared/arch.cpp','-o',arch],work,quiet)
            resolver_flags=[x for x in META['link'] if x!='-fno-exceptions']
            exec_cmd([cxx,*resolver_flags,*includes,'-c',
                      ROOT/'shared/architecture.cpp','-o',resolver],work,quiet)
        else:
            worker=ROOT/src/'worker.o'
            near=ROOT/'near/near40.o'
            graph=ROOT/'near/near40-assets.o'
            arch=ROOT/'objects/arch.o'
            resolver=ROOT/'objects/architecture-resolver.o'
            for p in (worker,near,graph,arch,resolver):
                if not p.exists():
                    raise RuntimeError(f'Missing optional frozen object: {p}')
        xroot=ROOT/'libraries/xz'
        xobjs=[]
        for unit in ('xz_crc32','xz_dec_lzma2','xz_dec_stream'):
            obj=work/(unit+'.o')
            exec_cmd([cc,'-Os','-std=c11','-I',xroot,'-c',xroot/(unit+'.c'),'-o',obj],work,quiet)
            xobjs.append(obj)
        objs=['aq.o',near,graph,arch,'arch-data.o',ROOT/'shared/entry.cpp',worker,*xobjs]
        exec_cmd([cxx,*objs,*META['link'],*includes,resolver,
                  ROOT/'libraries/libzstd.a','-static','-s',
                  '-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc',
                  '-o','estimate'],work,quiet)
        target=work/'estimate'
        size=target.stat().st_size
        if size>=SIZE_LIMIT:
            raise RuntimeError(f'ELF bytes={size} exceed strict upper bound {SIZE_LIMIT}')
        digest=sha256(target)
        target.replace(outpath)
        outpath.chmod(0o755)
    receipt={'variant':variant,'mode':mode,'path':str(outpath),'bytes':size,'sha256':digest,
             'matches_historical_release_sha256':digest==META['variants'][src]['sha256'],
             'compiler':subprocess.check_output([cxx,'--version'],text=True).splitlines()[0]}
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant',choices=('both','fast','exact'),default='both')
    p.add_argument('--mode',choices=('source','frozen'),default='source',
                   help='source compiles project C++; frozen relinks packaged original objects')
    p.add_argument('--out-dir',type=Path,default=ROOT/'bin')
    p.add_argument('--cxx',default='g++')
    p.add_argument('--cc',default='gcc')
    p.add_argument('--quiet',action='store_true')
    args=p.parse_args()
    for tool in (args.cxx,args.cc):
        if not shutil.which(tool):
            p.error(f'compiler unavailable: {tool}')
    check_assets()
    receipts=[]
    for variant in (['fast','exact'] if args.variant=='both' else [args.variant]):
        receipts.append(build(variant,args.mode,args.out_dir.resolve(),args.cxx,args.cc,args.quiet))
    rpath=args.out_dir.resolve()/'build-receipts.json'
    rpath.parent.mkdir(parents=True,exist_ok=True)
    rpath.write_text(json.dumps(receipts,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

if __name__=='__main__':
    try:
        main()
    except (RuntimeError,subprocess.CalledProcessError) as e:
        print(f'Build FAILED: {e}',file=sys.stderr)
        sys.exit(1)
