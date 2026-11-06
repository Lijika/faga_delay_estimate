"""Link architecture-only near-field generation, compressed adaptive far codes and a frozen physical head."""
from pathlib import Path
import argparse,json,subprocess,shutil,sys
import numpy as np
p=argparse.ArgumentParser()
for k in ('source','near_objects','model','wire','physical','out'):p.add_argument(k,type=Path)
p.add_argument('--partial',action='store_true');p.add_argument('--fast',action='store_true');p.add_argument('--compress-arch',action='store_true');a=p.parse_args();s=a.source.resolve();o=a.out.resolve();o.mkdir(exist_ok=True,parents=True);near=a.near_objects.resolve()
def arr(name,x,ctype):
 x=np.asarray(x);dims=''.join('['+str(z)+']' for z in x.shape);f=o/(name+'.inc')
 if x.dtype.kind=='f':fmt=lambda z:format(float(z),'.10g')
 else:fmt=lambda z:str(int(z))
 f.write_text('static constexpr '+ctype+' '+name+dims+'={'+','.join(fmt(z) for z in x.ravel())+'};\n')
 return '#include "'+f.name+'"\n'
hdr='';kn=[];w1=[];i1=[];w2=[];i2=[];sc=[]
for d in range(4):
 m=np.load(a.model/f'd{d}-k56-n8.npz');b=np.load(a.model/f'd{d}-k40-n8.npz');K=m['anchors'];kn.append(K[:40]//46*8+K[:40]%46);i1.append(b['idx'][K[40:]]);w1.append(b['beta'][K[40:]]);i2.append(m['idx']);w2.append(m['beta']);j=np.arange(552);w=(120-10*(j//46)-4)*(550-12*(j%46)-5)/(120+125*(j//46)+126*(j%46));S=np.zeros(56);np.add.at(S,m['idx'].ravel(),(w[:,None]*m['beta'][:,:-1]**2).ravel());sc.append(np.sqrt(np.maximum(.01,S[40:]/S[40:].mean())).astype('f4'))
for name,x,ct in [('nearOrder',kn,'uint8_t'),('nearIdx',i1,'uint8_t'),('nearWeights',w1,'float'),('outputIdx',i2,'uint8_t'),('outputWeights',w2,'float'),('aqScale',sc,'float')]:hdr+=arr(name,x,ct)
T=json.loads((a.physical/'trees.json').read_text());hdr+='struct AQNode{double value;int16_t limit;uint16_t left,right;uint8_t feature,leaf;};\n'
hdr+='static constexpr AQNode forest[]={'+','.join('{'+','.join(map(str,[v,int(np.clip(np.floor(bound),-32768,32767)),l,r,f,leaf]))+'}' for v,bound,f,l,r,leaf in T['nodes'])+'};\n'
hdr+=arr('treeRoots',T['start'],'uint16_t')+f'static constexpr double treeBase={T["base"]};static constexpr int featureCount={T["features"]};\n'
P=np.load(a.physical/'post.npz')
for k,n in enumerate(P.files):hdr+=arr('post'+str(k),P[n],'int8_t')
B=np.load(a.wire/'books.npz');books=np.stack([B[f'd{d}-c{c}-n{n}'] for d in range(4) for c in range(3) for n in range(10)]);books.astype('<f4').tofile(o/'books.f32')
frames=[];import zstandard
empty=zstandard.ZstdCompressor().compress(bytes(17280))
with (o/'frames.bin').open('wb') as dest:
 for i in range(208):
  for d in range(4):
   f=a.wire/f'c{i}-{d}.zst';data=f.read_bytes() if f.is_file() else empty if a.partial else None
   if data is None:raise ValueError(f'missing source {i}')
   dest.write(data);frames.append(len(data))
hdr+=arr('frameBytes',frames,'uint32_t')
hdr+='extern "C" const uint8_t aqframes[];extern "C" const float aqBooks[];\n#include "near40.hpp"\n#define loadNear40 near40::load40\n';(o/'params.h').write_text(hdr)
asm='.section .rodata\n'
for name,file in [('aqframes','frames.bin'),('aqBooks','books.f32')]:asm+=f'.p2align 6\n.global {name}\n{name}:\n.incbin "{o/file}"\n'
asm+='.section .note.GNU-stack,"",@progbits\n';(o/'aq.S').write_text(asm);subprocess.run(['gcc','-c',o/'aq.S','-o',o/'aq.o'],check=True)
w=(s/'src/worker.cpp').read_text();i=w.index('    adviseHugePages(records779');j=w.index('    arch.loadEmbedded();',i);w=w[:i]+w[j:]
w=w.replace('    _mm_prefetch(reinterpret_cast<const char*>(records779 + pair*480 + context), _MM_HINT_T0);','')
i=w.index('static inline void stageAndPrefetch806(');j=w.index('#ifdef EXP579_AUDIT',i);m=w.index('#else\nint main(',j)
core=Path(__file__).with_name('core.inc').read_text()
if a.fast:
 i0=core.index('static int predict(');core=core[:i0]+Path(__file__).with_name('fast.inc').read_text()+'\n'+core[i0:]
 core=core.replace('unsigned cls=int(hi-lo>32)+int(hi-lo>80);float z[56];','unsigned cls=int(hi-lo>32)+int(hi-lo>80);int yr=0;if(!quick(a,d,j,cls,allCodes[key],yr)){float z[56];')
 core=core.replace('const int trend=','yr=int(std::nearbyint(yhat));}const int trend=').replace('trend+int(std::nearbyint(yhat))','trend+yr')
w=w[:i]+'#include "params.h"\n'+core+'\n'+w[m+6:]
w=w[:w.index('#endif\n\n#ifdef EXP707_CHECK')]
w=w.replace('    initialize();\n    CsvViewReader', '    initialize(); auto ti=std::clock(); near40::initialize(); aqfar::init(); std::fprintf(stderr,"aq_init %.6f\\n",double(std::clock()-ti)/CLOCKS_PER_SEC);\n    CsvViewReader')
if a.fast:w=w.replace('aqfar::init(); std::fprintf','aqfar::init(); aqfar::initProjection(); std::fprintf')
w=w.replace('        Prepared596 states[EXP596_BATCH];','        Prepared596 states[EXP596_BATCH];int coords[EXP596_BATCH][10]{};')
w=w.replace('            int32_t q[10]{};','            auto& q=coords[count];');w=w.replace('        for (size_t index=0;index<count;++index) stageAndPrefetch806(states[index]);','')
w=w.replace('answers[index]=finish596(states[index]);','answers[index]=aqfar::predict(states[index],coords[index]);')
w='#include <ctime>\n'+w
(o/'worker.cpp').write_text(w);cmd=json.loads((s/'build/build-report.json').read_text())['commands'];cc=cmd[0].copy();ld=cmd[-1].copy();old=cc[-1];cc[cc.index('src/worker.cpp')]=str(o/'worker.cpp');cc[-1]=str(o/'worker.o');cc[1:1]=['-I'+str(near),'-Wno-unused-variable','-Wno-unused-function','-Wno-missing-braces','-Wno-misleading-indentation']
ld[ld.index(old)]=cc[-1];ld=[x for x in ld if not x.endswith('/assets.o')];ld[1:1]=[str(o/'aq.o'),str(near/'near40.o'),str(near/'near40-assets.o')];ld[-1]=str(o/'estimate')
if a.compress_arch:
 subprocess.run([sys.executable,Path(__file__).with_name('arch.py'),s,o],check=True);ld=[x for x in ld if not x.endswith('/arch-text.o')];ld[1:1]=[str(o/'arch.o'),str(o/'arch-data.o')]
for cmd in [cc,ld]:subprocess.run(cmd,cwd=s,check=True)
print('ELF', (o/'estimate').stat().st_size, 'far payload',sum(frames),flush=True)
