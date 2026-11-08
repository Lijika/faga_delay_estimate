"""Pilot true payload coding, with the decoder-known class and stage as contexts."""
import argparse,json,numpy as np,zstandard as z,lzma
from pathlib import Path
p=argparse.ArgumentParser()
for k in ['wire','cl','out']:p.add_argument(k,type=Path)
p.add_argument('--count',type=int,default=16);a=p.parse_args();a.out.mkdir(exist_ok=True,parents=True)
classes=np.memmap(a.cl,'u1','r',shape=(208,288,4,120));levels=np.array([0,1,2,3,4,5,6,8,10],'u1');rec={}
for s in np.linspace(0,207,a.count).round().astype(int):
 total=np.zeros(5,'f8');eall=0
 for d in range(4):
  f=a.wire/f'c{s}-{d}.zst';buf=np.frombuffer(z.decompress(f.read_bytes()),'u1');nib=buf[:17280];li=np.empty(34560,'u1');li[::2]=nib&15;li[1::2]=nib>>4;le=levels[li];cl=classes[s,:,d,:].reshape(-1);start=17280
  ordered=[];special=[];LN=[li[cl==i] for i in range(3)];warm=np.concatenate(LN)
  # Pack length bits again after partitioning. Predictor of length is same residue/adjacent target.
  x=warm[::2]|warm[1::2]<<4;ordered.append(x);special.append(x)
  for k in range(10):
   idx=le>k;M=idx.sum();sym=buf[start:start+M];start+=M
   cls=cl[idx];l=li[idx];order=np.argsort(cls,kind='stable');ordered.append(sym[order]);ord2=np.argsort((cls.astype('i4')*2+(le[idx]>=k+3)),kind='stable');special.append(sym[ord2])
  assert start==buf.size
  for i,raw in enumerate([buf,np.concatenate(ordered),np.concatenate(special)]):
   total[i]+=len(z.ZstdCompressor(level=17).compress(raw.tobytes()))
  total[3]+=len(lzma.compress(np.concatenate(ordered).tobytes(),format=lzma.FORMAT_XZ,preset=5));total[4]+=f.stat().st_size
 rec[int(s)]=total.astype(int).tolist();(a.out/'rate.json').write_text(json.dumps(rec));print(s,rec[int(s)],flush=True)
