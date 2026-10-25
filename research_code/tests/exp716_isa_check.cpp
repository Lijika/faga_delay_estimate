#include "architecture.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>

delayest::Architecture arch;
bool querying=false;
uint64_t allocations=0;
alignas(64) unsigned char exp579_geometry[69303616];
alignas(64) int16_t sums716[298560];

extern "C" void init716_F();
extern "C" void init716_V();
extern "C" void init716_W();
extern "C" void eval716_F(const int32_t*,unsigned,int32_t*,double*);
extern "C" void eval716_V(const int32_t*,unsigned,int32_t*,double*);
extern "C" void eval716_W(const int32_t*,unsigned,int32_t*,double*);
extern "C" int kernel716_F(const int8_t*,const int8_t*,int);
extern "C" int kernel716_V(const int8_t*,const int8_t*,int);
extern "C" int kernel716_W(const int8_t*,const int8_t*,int);
extern "C" void factors716_F(unsigned,unsigned,const int8_t**,const int8_t**);

static void compare716(const int32_t* q,unsigned fold) {
    int32_t a[68]{},b[68]{};
    double x[3]{},y[3]{};
    eval716_F(q,fold,a,x);
    for (const auto fn:{eval716_V,eval716_W}) {
        fn(q,fold,b,y);
        assert(std::memcmp(a,b,sizeof(a))==0 && std::memcmp(x,y,sizeof(x))==0);
    }
}

static void dot716(const int8_t* a,const int8_t* b) {
    int expected=0,sum=0;
    for (unsigned j=0;j<64;++j) { expected+=int(a[j])*int(b[j]);sum+=b[j]; }
    assert(kernel716_F(a,b,sum)==expected && kernel716_V(a,b,sum)==expected &&
           kernel716_W(a,b,sum)==expected);
}

int main(int argc,char** argv) {
    assert(argc==2);
    __builtin_cpu_init();
    assert(__builtin_cpu_supports("avx2") && __builtin_cpu_supports("avx512f") &&
           __builtin_cpu_supports("avx512bw") && __builtin_cpu_supports("avx512vl") &&
           __builtin_cpu_supports("avx512vnni"));
    init716_F();arch=delayest::Architecture{};
    init716_V();arch=delayest::Architecture{};
    init716_W();
    std::array<int8_t,192>a{},b{};
    uint32_t synthetic=0,real=0;
    for (int x=-128;x<=127;++x) for (int y=-128;y<=127;++y) {
        a.fill(int8_t(x));b.fill(int8_t(y));dot716(a.data()+(x+128)%64,b.data()+(x+128)%64);++synthetic;
    }
    std::mt19937_64 rng(20261025716);
    for (unsigned trial=0;trial<100000;++trial) {
        for (unsigned j=0;j<a.size();++j) {
            a[j]=int8_t(int(rng()%256)-128);b[j]=int8_t(int(rng()%256)-128);
        }
        dot716(a.data()+trial%64,b.data()+trial%64);++synthetic;
    }
    for (unsigned trial=0;trial<64;++trial) {
        for (unsigned j=0;j<a.size();++j) {
            a[j]=(j&1) ? 127 : -128;b[j]=((j+trial)&1) ? 127 : -128;
        }
        dot716(a.data()+trial,b.data()+trial);++synthetic;
    }
    for (unsigned group=0;group<2;++group)
        for (unsigned block=0;block<(group ? 260160 : 38400);++block) {
            const int8_t *left,*right;
            factors716_F(group,block,&left,&right);
            dot716(left,right);++real;
        }
    FILE* input=std::fopen(argv[1],"rb");
    assert(input);
    char magic[8];uint32_t rows;
    assert(std::fread(magic,1,8,input)==8 && std::memcmp(magic,"EX535Q01",8)==0);
    assert(std::fread(&rows,4,1,input)==1 && rows==239616);
    for (unsigned row=0;row<rows;++row) {
        int32_t q[10];
        assert(std::fread(q,4,10,input)==10);
        for (unsigned fold=0;fold<4;++fold) compare716(q,fold);
    }
    assert(std::fgetc(input)==EOF && std::fclose(input)==0);
    unsigned corners=0;
    for (int p=0;p<496;++p)
        for (int x:{-1,0,15,16,75,76,89,90,119,120})
            for (int y:{-1,0,49,50,99,100,499,500,549,550}) {
                int32_t q[10]={x,y,x,y,0,0,0,0,p,p};
                compare716(q,0);++corners;
                q[2]=120;q[3]=550;compare716(q,0);++corners;
            }
    std::printf("{\"all_equal\":true,\"synthetic_dots\":%u,\"real_dots\":%u,"
                "\"queries\":%u,\"folds\":4,\"corners\":%u,\"shared_geometry_bytes\":69303616,"
                "\"shared_sum_bytes\":597120}\n",synthetic,real,rows,corners);
}
