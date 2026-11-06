"""Architecture-only sensor placement by conditional covariance; freeze all coordinates before scoring labels."""
from pathlib import Path
import argparse,numpy as np
p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('fields',type=Path,nargs='+');p.add_argument("--force-near",action="store_true");a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
X=[0,1,2,3,4,6,8,11];Y=[0,1,2,3,5,8,12,19,30,45];univ=np.array(sorted({x*46+y for x in range(5) for y in range(8)}|{x*46+y for x in X for y in Y}))
j=np.arange(552);xx=j//46;yy=j%46;pop=(120-10*xx-4)*(550-12*yy-5)/(120+125*xx+126*yy)
rng=np.random.default_rng(960041);rs=[]
for d in range(4):
 raw=[]
 for f in a.fields:
  h=np.fromfile(f,'<i4',count=296);assert list(h[3:8])==[288,4,120,12,46];v=np.memmap(f,'<i2','r',offset=1184,shape=(4,34560,552))
  raw.append(v[d,rng.choice(34560,12000,replace=False)].astype('f4'))
 v=np.concatenate(raw);del raw
 # Project off a common offset; absolute scale variation must survive decoding exactly.
 base=2*46+3;v-=v[:,base,None].copy();mu=v.mean(0,dtype='f8');v-=mu.astype('f4')
 C=(v.T@v).astype('f8')/len(v);del v
 active=[base];keep=C.copy();pool=set(univ)-{base}
 if a.force_near:
  for t in [x*46+y for x in range(5) for y in range(8) if x*46+y!=base]:
   pool.remove(t);active.append(t);v=keep[:,t].copy();keep-=np.outer(v,v)/max(keep[t,t],1e-8)
 while len(active)<72:
  candidates=np.array(sorted(pool));col=keep[:,candidates];gain=pop@np.square(col)/np.maximum(keep[candidates,candidates],1e-8);t=candidates[np.argmax(gain)];pool.remove(t);active.append(t);v=keep[:,t].copy();keep-=np.outer(v,v)/max(keep[t,t],1e-8)
 # Keep runtime feature count independent of storage grid size. Each of 552 queries
 # uses at most a staged set of 4/8 coefficients and one offset.
 for K in ([40,41,42,43,44,46,48,52,56] if a.force_near else [16,32,40,48,56,72]):
  anchors=np.array(active[:K]);pos={x:i for i,x in enumerate(anchors)}
  for cnt in [4,8,16]:
   pars=np.zeros((552,cnt+2),'f4');idx=np.zeros((552,cnt+1),'u1')
   for t in range(552):
    if t in pos:idx[t,0]=pos[t];pars[t,0]=1;continue
    # Choose raw anchors sequentially by covariance with target after each partial projection.
    rem=anchors[1:];ct=C[np.ix_(rem,rem)].copy();rhs=C[t,rem].copy();chosen=[]
    for k in range(cnt):
     gain=rhs*rhs/np.maximum(np.diag(ct),1e-8);gain[chosen]=-1;jj=int(np.argmax(gain));chosen.append(jj);u=ct[:,jj].copy();den=max(ct[jj,jj],1e-8);rhs-=rhs[jj]*u/den;ct-=np.outer(u,u)/den
    use=rem[chosen];w=np.linalg.solve(C[np.ix_(use,use)]+np.eye(len(use))*.025,C[use,t]);idx[t,:]=[0,*[pos[x] for x in use]];pars[t,:]=[1-w.sum(),*w,mu[t]-w@mu[use]]
   np.savez(a.out/f'd{d}-k{K}-n{cnt}',anchors=anchors,idx=idx,beta=pars)
 print(d,active[:40],flush=True)
