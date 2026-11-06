import argparse,re,subprocess,concurrent.futures
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
for key in ['source','solver','out']:p.add_argument(key,type=Path)
p.add_argument('traces',type=Path,nargs='+');p.add_argument('--workers',type=int,default=4)
a=p.parse_args();o=a.out.resolve();o.mkdir(parents=True,exist_ok=True);s=a.source.resolve()
roles=(s/'include/exp579-models.h').read_text();ids=lambda k:np.fromstring(re.search(k+r'\[\]=\{([^}]+)\}',roles)[1],sep=',',dtype=int)
si=ids('kSourceIndex');ti=ids('kTargetIndex');src=np.flatnonzero(si>=0);target=np.flatnonzero(ti>=0);assert (np.sort(si[src])==np.arange(208)).all()
src=src[np.argsort(si[src])];tmap=np.argsort(np.argsort(ti[target]))
# solver targets are ascending original port IDs, TI is EAT role number.
told=np.argsort(ti[target])
allq=np.concatenate([np.fromfile(f,'<i4').reshape(-1,6) for f in a.traces]);n=len(allq)
k,j,fl=allq[:,:3].T;role=k//(288*480);tg=k//480%288;ctx=k%480;d=ctx//120
dx=(ctx%120//12+10*(j//46))*np.where(d>=2,-1,1);dy=(ctx%12+12*(j%46))*np.where(d%2,-1,1)
gold=np.full(n,-1,'i4')
def one(i):
 sel=np.flatnonzero((role==i)&(fl&1!=0));req=o/(str(i)+'.req');v=o/(str(i)+'.res')
 np.stack([dx[sel],dy[sel],told[tg[sel]],sel],axis=1).astype('<i4').tofile(req)
 subprocess.run([str(a.solver.resolve()),str(s/'arch'),str(src[i]),str(req),str(v)],check=True)
 z=np.fromfile(v,'<i4').reshape(-1,2);assert np.array_equal(z[:,0],sel);return z
with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
 for c,z in enumerate(ex.map(one,range(208))):
  gold[z[:,0]]=z[:,1]
  if c%16==15:print(c+1,flush=True)
assert np.all(gold[fl&1!=0]>=0)
at=0
for f in a.traces:
 n=f.stat().st_size//24;gold[at:at+n].tofile(o/(f.stem+'.nom'));at+=n
