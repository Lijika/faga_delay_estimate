#!/usr/bin/env python3
"""Verify exported direction/anchor/regressor tables against frozen NPZ intermediates."""
import numpy as np
from pathlib import Path
import argparse,hashlib,json
R=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--frozen',type=Path,default=R/'frozen')
 p.add_argument('--inc-dir',type=Path,default=R/'frozen')
 a=p.parse_args()
 out={'nearOrder':[],'nearIdx':[],'nearWeights':[],'outputIdx':[],'outputWeights':[],'aqScale':[]}
 for d in range(4):
  m=np.load(a.frozen/f'd{d}-k56-n8.npz');b=np.load(a.frozen/f'd{d}-k40-n8.npz');K=m['anchors']
  out['nearOrder'].append(K[:40]//46*8+K[:40]%46)
  out['nearIdx'].append(b['idx'][K[40:]])
  out['nearWeights'].append(b['beta'][K[40:]])
  out['outputIdx'].append(m['idx'])
  out['outputWeights'].append(m['beta'])
  j=np.arange(552)
  w=(120-10*(j//46)-4)*(550-12*(j%46)-5)/(120+125*(j//46)+126*(j%46))
  S=np.zeros(56)
  np.add.at(S,m['idx'].ravel(),(w[:,None]*m['beta'][:,:-1]**2).ravel())
  out['aqScale'].append(np.sqrt(np.maximum(.01,S[40:]/S[40:].mean())).astype('f4'))
 typ={'nearOrder':'uint8_t','nearIdx':'uint8_t','nearWeights':'float','outputIdx':'uint8_t','outputWeights':'float','aqScale':'float'}
 result={}
 for name,raw in out.items():
  z=np.asarray(raw);fmt=(lambda x: format(float(x),'.10g')) if z.dtype.kind=='f' else (lambda x:str(int(x)))
  text='static constexpr '+typ[name]+' '+name+''.join('['+str(n)+']' for n in z.shape)+'={'+','.join(map(fmt,z.ravel()))+'};\n'
  historical=(a.inc_dir/(name+'.inc')).read_text()
  result[name]={'identical':text==historical,'items':int(z.size),'sha256':hashlib.sha256(text.encode()).hexdigest()}
  if text!=historical:raise RuntimeError(f'{name} differs')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
