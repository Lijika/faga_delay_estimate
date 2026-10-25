
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
#include "symmetric640.h"
int main(int argc,char** argv) {
    require(argc==5,"checker FEATURES QUERIES FOLDS OUTPUT");
    FILE *features=std::fopen(argv[1],"rb"),*queries=std::fopen(argv[2],"rb"),
         *folds=std::fopen(argv[3],"rb"),*output=std::fopen(argv[4],"wb");
    require(features&&queries&&folds&&output,"files");
    char magic[8]; uint32_t count,width;
    require(std::fread(magic,1,8,features)==8&&!std::memcmp(magic,"E554F001",8)&&
        std::fread(&count,4,1,features)==1&&count==1000000&&
        std::fread(&width,4,1,features)==1&&width==53,"features header");
    require(std::fread(magic,1,8,queries)==8&&!std::memcmp(magic,"EX535Q01",8)&&
        std::fread(&count,4,1,queries)==1&&count==1000000,"queries header");
    bool seen[64]{};
    for(unsigned row=0;row<count;++row) {
        float values[53]; int f[53]; int32_t q[10]; unsigned char fold;
        require(std::fread(values,4,53,features)==53&&std::fread(q,4,10,queries)==10&&
            std::fread(&fold,1,1,folds)==1&&fold<3,"row");
        for(unsigned j=0;j<53;++j) {
            f[j]=int(values[j]); require(float(f[j])==values[j],"integer feature");
        }
        int nx=f[8]+f[6],ny=f[9]+f[7];
        unsigned route=4*(2*(nx<0)+(ny<0))+2*(std::abs(nx)>=20)+(std::abs(ny)>=24);
        for(unsigned stage=0;stage<2;++stage) {
            unsigned char leaves[16]{};
            unsigned k=stage?unsigned(fold)+1:0;
            double raw=symmetric640(q,f[28],f[29],f[6],f[7],f[8],f[9],f[50],
                f[52],route,k,leaves,f);
            require(std::fwrite(&raw,8,1,output)==1&&std::fwrite(leaves,1,16,output)==16,"write");
            seen[16*k+route]=true;
        }
    }
    for(bool s:seen) require(s,"route coverage");
    require(std::fgetc(features)==EOF&&std::fgetc(queries)==EOF&&std::fgetc(folds)==EOF,"EOF");
    require(!std::fclose(features)&&!std::fclose(queries)&&!std::fclose(folds)&&!std::fclose(output),"close");
    std::puts("{\"rows\":1000000,\"models\":64,\"active_features_equal\":true}");
}
