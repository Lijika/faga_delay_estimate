
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
static void require(bool b,const char* why) {
    if(!b) { std::fprintf(stderr,"%s\n",why); std::exit(1); }
}
static inline int side(int x) { return x<76?0:x<90?1:2; }
static inline int mod(int x,int base) { int r=x%base; return r<0?r+base:r; }
#define EXP579_AUDIT
#include "replacement679.h"
#include "exp679_hv_events.h"
int main(int argc,char** argv) {
    require(argc==6,"check FEATURES QUERIES FOLDS EXTRA OUTPUT");
    FILE *features=std::fopen(argv[1],"rb"),*queries=std::fopen(argv[2],"rb"),
         *folds=std::fopen(argv[3],"rb"),*extra=std::fopen(argv[4],"rb"),
         *output=std::fopen(argv[5],"wb");
    require(features&&queries&&folds&&extra&&output,"files");
    char magic[8]; uint32_t count,width;
    require(std::fread(magic,1,8,features)==8&&!std::memcmp(magic,"E554F001",8)&&
        std::fread(&count,4,1,features)==1&&count==1000000&&
        std::fread(&width,4,1,features)==1&&width==53,"features header");
    require(std::fread(magic,1,8,queries)==8&&!std::memcmp(magic,"EX535Q01",8)&&
        std::fread(&count,4,1,queries)==1&&count==1000000,"queries header");
    unsigned events[3]{},seen[8]{};
    for(uint32_t row=0;row<count;++row) {
        float f[71]; int32_t q[10],e[18]; unsigned char fold;
        require(std::fread(f,4,53,features)==53&&std::fread(q,4,10,queries)==10&&
            std::fread(&fold,1,1,folds)==1&&fold<3&&std::fread(e,4,18,extra)==18,"row");
        for(unsigned j=0;j<18;++j) f[53+j]=float(e[j]);
        float z[16]; geometry614(f,z);
        for(unsigned j=0;j<16;++j) require(z[j]==f[53+j],"extra geometry");
        int bands,ends;
        const unsigned event=event679(int(f[28]),int(f[29]),int(f[30]),int(f[31]),
                                     bool(f[52]),bands,ends);
        require(ends==e[17],"central endpoints");
        require(event==unsigned(e[17]==2&&e[16]>0?2:0),"event");
        // Ordinary rows do not consume bands; expert rows must match all inputs.
        if(event) require(bands==e[16],"expert bands");
        ++events[event];
        if(!event) continue;
        double raw[2]; unsigned char leaves[2][8]{};
        for(unsigned stage=0;stage<2;++stage) {
            const unsigned k=stage?unsigned(fold)+1:0;
            raw[stage]=replacement679(q,int(f[28]),int(f[29]),int(f[6]),int(f[7]),
                int(f[8]),int(f[9]),int(f[50]),bool(f[52]),k,event,bands,ends,leaves[stage],f);
            ++seen[2*k+event-1];
        }
        require(std::fwrite(&row,4,1,output)==1&&std::fwrite(&event,4,1,output)==1&&
            std::fwrite(raw,8,2,output)==2&&std::fwrite(leaves,1,16,output)==16,"write");
    }
    for(unsigned i=0;i<8;++i) require(i%2 ? seen[i]>0 : seen[i]==0,"model coverage");
    for(FILE* p:{features,queries,folds,extra}) require(std::fgetc(p)==EOF,"EOF");
    for(FILE* p:{features,queries,folds,extra,output}) require(std::fclose(p)==0,"close");
    std::printf("{\"rows\":%u,\"events\":[%u,%u,%u],\"models\":8,\"all_features_equal\":true}\n",
        count,events[0],events[1],events[2]);
}
