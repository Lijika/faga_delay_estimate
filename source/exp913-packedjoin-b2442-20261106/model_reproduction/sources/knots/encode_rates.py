"""Actual entropy rate of variable-depth additive codes. Builds frozen centroids and encodes certified source frames."""
from pathlib import Path
import argparse,numpy as np,json,subprocess,concurrent.futures as cf,zstandard as zs,pandas as pd,zlib
from scipy.spatial import cKDTree
from sklearn.cluster import MiniBatchKMeans
p=argparse.ArgumentParser()
for k in ['model','solver','arch','sourceids','targets','public','trace','out']:p.add_argument(k,type=Path)
p.add_argument('--fields',nargs='+',type=Path,required=True);p.add_argument('--count',type=int,default=208);p.add_argument('--save',type=str);p.add_argument('--adaptive-price',type=float,default=0.);p.add_argument('--adaptive-lambda',type=float,default=2.0);p.add_argument('--trial-prices',type=float,nargs='*',default=[]);p.add_argument('--jobs',type=int,default=2);p.add_argument('--maxrate',type=int,default=8);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(842769);K=56;C=[];keys=[];wirebook={}
for d in range(4):
 m=np.load(a.model/f'd{d}-k56-n8.npz');base=np.load(a.model/f'd{d}-k40-n8.npz');kn=m['anchors'];keys.append(kn);far=kn[40:];ix=base['idx'][far];coef=base['beta'][far];train=[]
 for f in a.fields:
  v=np.memmap(f,'i2','r',offset=1184,shape=(4,34560,552));train.append(v[d,rng.choice(34560,30000,replace=False)][:,kn].astype('f4'))
 Z=np.concatenate(train);local=Z[:,:40];D=Z[:,40:]-(np.einsum('nsk,sk->ns',local[:,ix],coef[:,:-1],optimize=True)+coef[:,-1]);cl=np.searchsorted([32,80],local.max(1)-local.min(1));j=np.arange(552);w=(120-10*(j//46)-4)*(550-12*(j%46)-5)/(120+125*(j//46)+126*(j%46));S=np.zeros(K);np.add.at(S,m['idx'].ravel(),(w[:,None]*m['beta'][:,:-1]**2).ravel());scale=np.sqrt(np.maximum(.01,S[40:]/S[40:].mean())).astype('f4');groups=[]
 for c in range(3):
  x=(D[cl==c]*scale).copy();st=[]
  for n in range(a.maxrate):
   km=MiniBatchKMeans(n_clusters=256,batch_size=2048,n_init=1,max_iter=55,random_state=849+n).fit(x);cent=km.cluster_centers_.copy();tree=cKDTree(cent);x-=cent[tree.query(x)[1]];st.append((tree,cent));wirebook[f'd{d}-c{c}-n{n}']=cent
  groups.append(st)
 C.append((ix,coef,scale,groups))
np.savetxt(a.out/'knots',np.concatenate(keys),fmt='%d');np.savez(a.out/'books.npz',**wirebook)
src=np.loadtxt(a.sourceids,dtype=int)
# Public-role frequency only; deliberately test explicit rate tiers rather than file-size extrapolation.
df=pd.read_csv(a.public,usecols=['From']);k=np.fromfile(a.trace,'i4').reshape(-1,6)[:,0]//480;f=np.fromiter((zlib.crc32(z.encode())%10<7 for z in df.From),bool,len(df));freq=np.bincount(k[f],minlength=59904);order=np.argsort(-freq,kind='stable');ranks=np.empty(59904,'i4');ranks[order]=np.arange(59904)
spec={n:np.full(59904,n,'u1') for n in [3,4,5]};spec['var']=np.select([ranks<59904*.10,ranks<59904*.33,ranks<59904*.40],[8,6,4],2).astype('u1');spec['var2']=np.select([ranks<59904*.10,ranks<59904*.33,ranks<59904*.40],[8,6,4],3).astype('u1')
def one(s):
 Afile=a.out/f'{s}.tmp';subprocess.run([a.solver.resolve(),a.arch.resolve(),str(src[s]),a.targets.resolve(),a.out/'knots',Afile],check=True)
 A=np.memmap(Afile,'<i2','r',shape=(4,120,K,288));ans={str(t):0 for t in spec};ans['adaptive']=0
 for d,(ix,coef,scale,groups) in enumerate(C):
  Z=A[d].transpose(2,0,1).reshape(-1,K).astype('f4');near=Z[:,:40];Y=(Z[:,40:]-(np.einsum('nsk,sk->ns',near[:,ix],coef[:,:-1],optimize=True)+coef[:,-1]))*scale;cl=np.searchsorted([32,80],near.max(1)-near.min(1));code=np.zeros((len(Y),a.maxrate),'u1')
  levels=np.array([l for l in [0,1,2,3,4,5,6,8,10] if l<=a.maxrate]);risk=np.empty((len(Y),len(levels)),'f4');risk[:,0]=np.mean(abs(Y)*scale,axis=1)
  for g,st in enumerate(groups):
   mm=cl==g;x=Y[mm]
   if not len(x):continue
   temp=np.empty((len(x),a.maxrate),'u1')
   for n,(tr,ct) in enumerate(st):
    id=tr.query(x)[1];temp[:,n]=id;x-=ct[id]
    if n+1 in levels:risk[mm,int(np.where(levels==n+1)[0][0])]=np.mean(abs(x)*scale,axis=1)
   code[mm]=temp
  for pri in ([a.adaptive_price] if a.adaptive_price else [])+a.trial_prices:
   fr=np.repeat(freq[s*288:(s+1)*288],120)/freq.mean();li=(risk*(1+a.adaptive_lambda*fr[:,None])**.70+pri*levels).argmin(1).astype('u1');rate=levels[li]
   packed=li[::2]|(li[1::2]<<4);wire=packed.tobytes()+b''.join(code[rate>n,n].tobytes() for n in range(a.maxrate));frame=zs.ZstdCompressor(level=8).compress(wire);tag='adaptive' if pri==a.adaptive_price else 'p'+str(pri);ans[tag]=ans.get(tag,0)+len(frame)+4
   if a.save==tag:(a.out/f'c{s}-{d}.zst').write_bytes(frame)
  for t,bits in spec.items():
   rate=bits[s*288:(s+1)*288];rect=code.reshape(288,120,-1);wire=b''.join(rect[rate>n,:,n].tobytes() for n in range(a.maxrate));frame=zs.ZstdCompressor(level=8).compress(wire);ans[str(t)]+=len(frame)+4
   if str(t)==a.save:(a.out/f'c{s}-{d}.zst').write_bytes(frame)
 del A;Afile.unlink();return s,ans
stat={};samples=np.linspace(0,207,a.count).round().astype('i4')
with cf.ThreadPoolExecutor(a.jobs) as ex:
 for s,r in ex.map(one,samples):
  stat[int(s)]=r;(a.out/'rates.json').write_text(json.dumps(stat,indent=2)+'\n');print(int(s),r,flush=True)
