"""Restore the five original architecture JSON byte strings from embedded, checksummed Zstd frames."""
from pathlib import Path
import subprocess,zstandard,sys
src,out=map(Path,sys.argv[1:]);files=['SRB_Port.json','SRB_Arc.json','SRB_Net.json','SRB_Inst.json','SRB_Gap.json'];names=[];lengths=[];sizes=[];dest=out/'arch.bin'
with dest.open('wb') as w:
 for name in files:
  raw=(src/'arch'/name).read_bytes();frame=zstandard.ZstdCompressor(level=19,write_checksum=True).compress(raw);assert zstandard.ZstdDecompressor().decompress(frame)==raw;names.append('"'+name+'"');lengths.append(str(len(raw)));sizes.append(str(len(frame)));w.write(frame)
asm=out/'arch.S';asm.write_text('.section .rodata\n.global aqarch\naqarch:\n.incbin "'+str(dest.resolve())+'"\n.section .note.GNU-stack,"",@progbits\n');subprocess.run(['gcc','-c',asm,'-o',out/'arch-data.o'],check=True)
cpp=out/'arch.cpp';cpp.write_text('''#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <zstd.h>
extern "C" const unsigned char aqarch[];
namespace delayest::embedded_arch {
const char* text(const char* name){
 static constexpr const char *names[]={'''+','.join(names)+'''};
 static constexpr unsigned raw[]={'''+','.join(lengths)+'''},wire[]={'''+','.join(sizes)+'''};
 static std::vector<char> restored[5];if(!name)return nullptr;unsigned at=0;
 for(int k=0;k<5;k++){if(!std::strcmp(name,names[k])){auto &s=restored[k];if(s.empty()){s.resize(raw[k]+1);if(ZSTD_decompress(s.data(),raw[k],aqarch+at,wire[k])!=raw[k]){std::fputs("architecture decode failed\\n",stderr);std::abort();}s[raw[k]]=0;}return s.data();}at+=wire[k];}
 return nullptr;}
}
''');subprocess.run(['g++','-O2','-std=c++17','-fno-exceptions','-I',src/'third_party/zstd','-c',cpp,'-o',out/'arch.o'],check=True);print('arch wire',dest.stat().st_size)
