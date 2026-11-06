#!/usr/bin/env python3
"""Assemble three deployment assets from frozen CODEWORDS, float centroids, and raw official JSON.

This is a byte-exact *packager* of intermediate artifacts, not a trainer.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
NAMES=['SRB_Port.json','SRB_Arc.json','SRB_Net.json','SRB_Inst.json','SRB_Gap.json']
EXPECTED={
 'frames.bin':(94065657,'86d62800d87773a9c61dda998d45084930ac30cdecc6493dc0089f27829ee046'),
 'books.f32':(1966080,'7906e3e5b49d70cf796dec18acbc4c2e9fa319f4c96f90f3627a6e6afba9bb1f'),
 'arch.bin':(91246,'e0c09f3e8645a3c3718bf1f0cfda791878ddd37f364d7d68ce26b43724458b0b'),
}
def sha(b):return hashlib.sha256(b).hexdigest()
def book_bytes(path):
    with np.load(path,allow_pickle=False) as B:
      expected={f'd{d}-c{c}-n{n}' for d in range(4) for c in range(3) for n in range(10)}
      assert set(B.files)==expected,('centroid keys mismatch',len(B.files))
      mats=[]
      for d in range(4):
       for c in range(3):
        for n in range(10):
         x=B[f'd{d}-c{c}-n{n}']
         assert x.shape==(256,16) and np.isfinite(x).all()
         mats.append(x)
      return np.stack(mats).astype('<f4').tobytes(order='C')
def arch_bytes(path):
    parts=[]
    for name in NAMES:
        src=path/name
        assert src.exists(),f'missing {src}'
        proc=subprocess.run(['zstd','-19','--check','--single-thread','-q','-c',str(src)],check=True,stdout=subprocess.PIPE)
        parts.append(proc.stdout)
    return b''.join(parts)
def frame_bytes(path):
    parts=[];sizes=[]
    for s in range(208):
      for d in range(4):
        file=path/f'c{s}-{d}.zst'
        if not file.is_file():raise FileNotFoundError(file)
        b=file.read_bytes();parts.append(b);sizes.append(len(b))
    return b''.join(parts),sizes
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--wire-dir',type=Path,required=True,help='directory containing c{source}-{direction}.zst for all 832 frames')
 p.add_argument('--books',type=Path,default=ROOT/'frozen/books.npz')
 p.add_argument('--arch',type=Path,default=ROOT/'raw_arch')
 p.add_argument('--out',type=Path,required=True)
 p.add_argument('--compare-frozen',action='store_true',help='require historical SHA256 for each asset')
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 fb,sizes=frame_bytes(a.wire_dir);bb=book_bytes(a.books);ab=arch_bytes(a.arch)
 (a.out/'frames.bin').write_bytes(fb);(a.out/'books.f32').write_bytes(bb);(a.out/'arch.bin').write_bytes(ab)
 (a.out/'frameBytes.inc').write_text('static constexpr uint32_t frameBytes[832]={'+','.join(map(str,sizes))+'};\n')
 receipt={}
 for n in EXPECTED:
  b=(a.out/n).read_bytes();sz,digest=EXPECTED[n]
  matches=len(b)==sz and sha(b)==digest
  receipt[n]={'bytes':len(b),'sha256':sha(b),'historical_exact':matches}
  if a.compare_frozen and not matches:raise SystemExit(f'{n} differs from frozen identity')
 (a.out/'asset-manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
