#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <zstd.h>
extern "C" const unsigned char aqarch[];
namespace delayest::embedded_arch {
const char* text(const char* name){
 static constexpr const char *names[]={"SRB_Port.json","SRB_Arc.json","SRB_Net.json","SRB_Inst.json","SRB_Gap.json"};
 static constexpr unsigned raw[]={31858,837145,21062,4266018,3969},wire[]={706,26692,577,62907,364};
 static std::vector<char> restored[5];if(!name)return nullptr;unsigned at=0;
 for(int k=0;k<5;k++){if(!std::strcmp(name,names[k])){auto &s=restored[k];if(s.empty()){s.resize(raw[k]+1);if(ZSTD_decompress(s.data(),raw[k],aqarch+at,wire[k])!=raw[k]){std::fputs("architecture decode failed\n",stderr);std::abort();}s[raw[k]]=0;}return s.data();}at+=wire[k];}
 return nullptr;}
}
