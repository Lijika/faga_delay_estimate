#include <immintrin.h>
#include <ctime>
// Complete private candidate; generated assets include the five official JSONs.
#undef EXP596_BATCH
#define EXP596_BATCH 64

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <emmintrin.h>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <unistd.h>

#include "architecture.h"
#include "csv.h"
#include "exp579-models.h"
#include "exp594_packed_output.h"

extern bool querying;
extern uint64_t allocations;

static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "estimate: %s\n", why); std::exit(1); }
}

#include "native_representation212.h"
extern delayest::Architecture arch;
#include "exp707_prepare_metadata.h"
#ifdef EXP580_PORT_PARSER
#include "exp601_port_parser.h"
#endif
#include "exp723_fused_parse.h"
#include "exp596_csv_batch.h"

static void adviseHugePages(void* data, size_t bytes) {
    const uintptr_t page = 4096;
    const uintptr_t begin = (reinterpret_cast<uintptr_t>(data) + page - 1) & ~(page - 1);
    const uintptr_t end = (reinterpret_cast<uintptr_t>(data) + bytes) & ~(page - 1);
    if (end > begin) {
        // Failure only disables this optional layout hint; output is unchanged.
        (void)madvise(reinterpret_cast<void*>(begin), end - begin, MADV_HUGEPAGE);
    }
}

static void initialize() {
    arch.loadEmbedded();
    initialize707();
#ifdef EXP580_PORT_PARSER
    initializePorts580();
#ifdef EXP580_VERIFY_PARSER
    verifyPorts580();
#endif
#endif

    require(arch.portCount() == kPortCount, "architecture identity");

}

#ifdef EXP594_PACKED

static inline float residual(const int* x, unsigned route, unsigned fold) {
    const auto& m = kPacked594[16 * fold + route];
    unsigned path[8]{};
    for (unsigned depth = 0; depth < 4; ++depth) {
        for (unsigned t = 0; t < 8; ++t) {
            const unsigned at = ((1u << depth) - 1 + path[t]) * 8 + t;
            const uint32_t node = m.node[at];
            path[t] = 2 * path[t] + unsigned(x[node & 255] >= int16_t(node >> 16));
        }
    }
    float result = 0.f;
    for (unsigned t = 0; t < 8; ++t) result += m.value[16 * t + path[t]];
    return result;
}

#else
template <typename T>
static inline float residual(const T* x, unsigned route, unsigned fold) {
    const auto& m = kModels[16 * fold + route];
    unsigned path[8]{};
    for (unsigned depth = 0; depth < 4; ++depth) {
        for (unsigned t = 0; t < 8; ++t) {
            const unsigned at = ((1u << depth) - 1 + path[t]) * 8 + t;
            path[t] = 2 * path[t] + unsigned(x[m.feature[at]] >= m.threshold[at]);
        }
    }
    float result = 0.f;
    for (unsigned t = 0; t < 8; ++t) result += m.value[16 * t + path[t]];
    return result;
}

#endif

static inline int side(int x) { return x < 76 ? 0 : x < 90 ? 1 : 2; }
static inline int mod(int x, int base) { const int r = x % base; return r < 0 ? r + base : r; }
static inline int line(int x, int y, int tx, int ty) {
    return arch.lineDelayCrossing(delayest::Axis::Vertical, x, tx) +
           arch.lineDelayCrossing(delayest::Axis::Horizontal, y, ty);
}

#include "symmetric640.h"
#include "replacement679.h"
#include "forced_bias.h"
#include "exp679_hv_events.h"

struct Trace {
    float feature[53];
    double response;
    int32_t base, mandatory, prediction;
    double raw;
};

struct Prepared596 {
    unsigned pair=0, context=0, qx=0, qy=0;
    uint32_t word=0;
    int fee=0, mandatory=0, dy=0, cycle=0, answer=-1;
    double raw=0.;
    bool override_cycle=false, ready=false, ordinary=false;
};

template <bool ComputeTrace>
static inline void prepare596Impl(const int32_t* q, unsigned fold, Prepared596& state, Trace* trace) {
    const int sx=q[0], sy=q[1], tx=q[2], ty=q[3], sp=q[8], tp=q[9];
    if (sx == tx && sy == ty && sp == tp) { state.answer=arch.exists(sx,sy) ? 0 : -1; return; }
    const auto& sd=ports707[sp];
    const int source=sd.source, target=ports707[tp].target;
    if (source < 0 || target < 0 || !arch.exists(sx,sy) || !arch.exists(tx,ty)) return;
    int ax, ay, fee, firstLine;
    if (!first707(sx,sy,sd,ax,ay,fee,firstLine)) return;
    const int ndx=sd.dx, ndy=sd.dy;
    const bool hasNet=sd.start!=65535;
    const int x=tx-ax, y=ty-ay, dx=x+ndx, dy=y+ndy;
    const unsigned bx=unsigned(std::abs(dx)), by=unsigned(std::abs(dy));
    require(bx<=119 && by<=549, "nominal geometry domain");
    const unsigned qx=bx/10, qy=by/12, direction=2*(dx<0)+(dy<0);
    const unsigned pair=unsigned(source*288+target), context=(direction*10+bx%10)*12+by%12;

    const int mandatory=firstLine+line707(ax,ay,tx,ty);
    const int sf=q[4], sl=q[5], tf=q[6], tl=q[7];
    const bool forced=forced707(ax,ay,tx,ty);
#if defined(EXP581_INTEGER) || defined(EXP594_PACKED)
    if constexpr (ComputeTrace) {
        const int feature[53]={sf,sl,tf,tl,sf>=20,tf>=20,ndx,ndy,x,y,std::abs(x),std::abs(y),x<0,y<0,
            mod(x,10),mod(y,12),std::abs(x)%10,std::abs(y)%12,std::abs(x)/10,std::abs(y)/12,
            sl^tl,sl-tl,125*(std::abs(x)/10)+(y<0?125:127)*(std::abs(y)/12),
            (sl&1)+2*(tl&1),((sl>>1)&1)+2*((tl>>1)&1),((sl>>2)&1)+2*((tl>>2)&1),
            sx,sy,ax,ay,tx,ty,119-sx,119-ax,119-tx,549-sy,549-ay,549-ty,
            side(sx),side(ax),side(tx),sy%100,ay%100,ty%100,sy%100<50,ay%100<50,ty%100<50,
            sy/100,ay/100,ty/100,fee,(tx-14*(ty%100<50 && tx>=90))-(ax-14*(ay%100<50 && ax>=90)),forced};
        if (trace) for (unsigned j=0;j<53;++j) trace->feature[j]=float(feature[j]);
    }
#else
    const int feature[53]={sf,sl,tf,tl,sf>=20,tf>=20,ndx,ndy,x,y,std::abs(x),std::abs(y),x<0,y<0,
        mod(x,10),mod(y,12),std::abs(x)%10,std::abs(y)%12,std::abs(x)/10,std::abs(y)/12,
        sl^tl,sl-tl,125*(std::abs(x)/10)+(y<0?125:127)*(std::abs(y)/12),
        (sl&1)+2*(tl&1),((sl>>1)&1)+2*((tl>>1)&1),((sl>>2)&1)+2*((tl>>2)&1),
        sx,sy,ax,ay,tx,ty,119-sx,119-ax,119-tx,549-sy,549-ay,549-ty,
        side(sx),side(ax),side(tx),sy%100,ay%100,ty%100,sy%100<50,ay%100<50,ty%100<50,
        sy/100,ay/100,ty/100,fee,(tx-14*(ty%100<50 && tx>=90))-(ax-14*(ay%100<50 && ax>=90)),forced};
    if constexpr (ComputeTrace) {
        if (trace) for (unsigned j=0;j<53;++j) trace->feature[j]=float(feature[j]);
    }
#endif
    [[maybe_unused]] const unsigned route=4*direction+2*(bx>=20)+(by>=24);
#if defined(EXP581_INTEGER) || defined(EXP594_PACKED)
    int bands,ends;
    const unsigned event=event679(ax,ay,tx,ty,forced,bands,ends);
    const double raw=(event ? replacement679(q,ax,ay,ndx,ndy,x,y,fee,forced,fold,event,bands,ends) :
        0.0) + (event==1 ? double(kForcedBias[context*4 + (qx>11 ? 3 : int(qx)/3)]) : 0.);
#else
    float f[53];
    for (unsigned j=0;j<53;++j) f[j]=float(feature[j]);
    const float raw=residual(f,route,fold);
#endif
    state.pair=pair; state.context=context; state.qx=qx; state.qy=qy;
    state.fee=fee; state.mandatory=mandatory; state.dy=dy; state.raw=raw;
    state.override_cycle=dx==0 && dy==0 && sp==tp && hasNet;
    state.cycle=sd.cycle; state.ready=true;
    state.ordinary=(event==0 && !state.override_cycle);
}

static inline void prepare596(const int32_t* q, unsigned fold, Prepared596& state, Trace* trace = nullptr) {
    prepare596Impl<true>(q,fold,state,trace);
}

static inline void prepare596Production(const int32_t* q, Prepared596& state) {
    prepare596Impl<false>(q,0,state,nullptr);
}

#include "params.h"
// Includes the generated parameter declarations, near40(key, dst), and source geometry.
namespace aqfar {
constexpr unsigned count=208*288*480u;
constexpr uint8_t lenCode[9]={0,1,2,3,4,5,6,8,10};
struct Codes {uint8_t n,idx[10];};
static_assert(sizeof(Codes)==11);
struct FarRow {uint16_t header;uint8_t v[16];};static_assert(sizeof(FarRow)==18);
extern "C" const unsigned char* aq_old42();extern "C" void aq_migrate(unsigned,unsigned char*);extern "C" void aq_joint_done();
static uint8_t* jointSlabs[208];
static inline FarRow& farAt(unsigned s,unsigned id){return *reinterpret_cast<FarRow*>(jointSlabs[s]+64ul*id+42);}
static unsigned offsets[833],levels[2][8];
static uint8_t reference[4][16],directIndex[4][552][9];static float directWeight[4][552][9];
static void prepMaterial(){
 for(unsigned k=0;k<832;k++)offsets[k+1]=offsets[k]+frameBytes[k];
 for(unsigned d=0;d<4;d++)for(unsigned i=0;i<16;i++){
    unsigned best=0;for(unsigned k=1;k<9;k++)if(nearWeights[d][i][k]>nearWeights[d][i][best])best=k;
    reference[d][i]=nearOrder[d][nearIdx[d][i][best]];}
 for(unsigned d=0;d<4;d++)for(unsigned j=0;j<552;j++)for(unsigned k=0;k<9;k++){unsigned i=outputIdx[d][j][k];
    directIndex[d][j][k]=i<40?nearOrder[d][i]:i;directWeight[d][j][k]=i<40?outputWeights[d][j][k]:(outputWeights[d][j][k]*0.125f);}
}
alignas(64) static uint16_t selectPoint[4][10][32];
alignas(64) static float packWeight[4][10][16];
static void prepWide(){
 for(unsigned d=0;d<4;d++)for(unsigned j=0;j<16;j++){
    for(unsigned k=0;k<9;k++){selectPoint[d][k][j]=nearOrder[d][nearIdx[d][j][k]];packWeight[d][k][j]=nearWeights[d][j][k];}
    selectPoint[d][9][j]=reference[d][j];packWeight[d][9][j]=nearWeights[d][j][9];
 }}
__attribute__((target("avx512f,avx512bw,avx512vl"))) static void quantRow(const int16_t* a,unsigned d,const Codes& cs,FarRow& dest){
 auto part0=_mm512_loadu_si512(a),part1=_mm512_maskz_loadu_epi16(255u,a+32);
 int lo=std::min(int(_mm512_reduce_min_epi32(_mm512_cvtepi16_epi32(_mm512_castsi512_si256(part0)))),
                 int(_mm512_reduce_min_epi32(_mm512_cvtepi16_epi32(_mm512_extracti64x4_epi64(part0,1)))));
 int hi=std::max(int(_mm512_reduce_max_epi32(_mm512_cvtepi16_epi32(_mm512_castsi512_si256(part0)))),
                 int(_mm512_reduce_max_epi32(_mm512_cvtepi16_epi32(_mm512_extracti64x4_epi64(part0,1)))));
 for(unsigned j=32;j<40;j++){lo=std::min(lo,int(a[j]));hi=std::max(hi,int(a[j]));}
 unsigned cls=unsigned(hi-lo>32)+unsigned(hi-lo>80);
 __m512 sum=_mm512_setzero_ps(),in=_mm512_setzero_ps();
 for(unsigned k=0;k<9;k++){
    auto v=_mm512_permutex2var_epi16(part0,_mm512_load_si512(selectPoint[d][k]),part1);
    auto x=_mm512_cvtepi32_ps(_mm512_cvtepi16_epi32(_mm512_castsi512_si256(v)));
    sum=_mm512_add_ps(sum,_mm512_mul_ps(x,_mm512_load_ps(packWeight[d][k])));}
 for(unsigned k=0;k<cs.n;k++)in=_mm512_add_ps(in,_mm512_loadu_ps(aqBooks+size_t(((d*3+cls)*10+k)*256+cs.idx[k])*16));
 auto raw=_mm512_add_ps(_mm512_add_ps(sum,_mm512_load_ps(packWeight[d][9])),_mm512_div_ps(in,_mm512_loadu_ps(aqScale[d])));
 auto anchor=_mm512_permutex2var_epi16(part0,_mm512_load_si512(selectPoint[d][9]),part1);
 auto sub=_mm512_sub_ps(raw,_mm512_cvtepi32_ps(_mm512_cvtepi16_epi32(_mm512_castsi512_si256(anchor))));
 float mn0=_mm512_reduce_min_ps(raw),mx0=_mm512_reduce_max_ps(raw),mn1=_mm512_reduce_min_ps(sub),mx1=_mm512_reduce_max_ps(sub);
 int base0=int(std::floor(mn0)),base1=int(std::floor(mn1)),mode=(mx1-base1<mx0-base0)?1:0,base=mode?base1:base0;
 float range=(mode?mx1:mx0)-float(base);require(base>=-2048 && base<=2047 && range<4000,"AQ far range");
 unsigned shift=0;while(range*8.f>255.49f*float(1u<<shift))++shift;require(shift<8,"AQ far shift");
 dest.header=uint16_t(((base+2048)<<4)|(mode<<3)|shift);
 auto q=_mm512_mul_ps(_mm512_sub_ps(mode?sub:raw,_mm512_set1_ps(float(base))),_mm512_set1_ps(8.f/float(1u<<shift)));
 _mm_storeu_si128((__m128i*)dest.v,_mm512_cvtepi32_epi8(_mm512_cvtps_epi32(q)));++levels[mode][shift];
}

static void materializeSource(unsigned src){
 constexpr unsigned per=288*480;size_t bytes=size_t(per)*64;
 auto out=(uint8_t*)mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(out!=MAP_FAILED,"AQ far row allocation");jointSlabs[src]=out;const unsigned char* nearSource=aq_old42()+size_t(src)*per*42;
 (void)madvise(out,bytes,MADV_HUGEPAGE);std::vector<uint8_t> tmp(34560*11);std::vector<Codes> local(34560);
 for(unsigned d=0;d<4;d++){unsigned entry=4*src+d,N=34560;
    size_t size=ZSTD_decompress(tmp.data(),tmp.size(),aqframes+offsets[entry],frameBytes[entry]);require(!ZSTD_isError(size)&&size>=17280,"AQ source frame");
    size_t at=17280;for(unsigned key=0;key<N;key++){int n=(tmp[key>>1]>>(4*(key&1)))&15;require(n<9,"AQ source count");local[key].n=lenCode[n];}
    for(unsigned k=0;k<10;k++)for(unsigned key=0;key<N;key++)if(local[key].n>k){require(at<size,"AQ source body");local[key].idx[k]=tmp[at++];}
    require(at==size,"AQ source length");
    const bool wide=__builtin_cpu_supports("avx512bw") && __builtin_cpu_supports("avx512vl");
    for(unsigned i=0;i<N;i++){unsigned id=(i/120)*480+d*120+i%120,key=src*per+id;int16_t a[40];near40::load40(key,a);
       auto slopeBand=[](int v){return (v>=-25)+(v>=-15)+(v>=-9)+(v>=-5)+(v>=-2)+(v>=0)+(v>=1)+(v>=3)+(v>=6)+(v>=10)+(v>=16)+(v>=26);};
       auto tail=out+64ul*id+60;
       tail[0]=slopeBand(a[23]-a[21]);tail[1]=slopeBand(a[39]-a[32]);tail[2]=slopeBand(a[39]-a[7]);tail[3]=0;
       if(wide){std::memcpy(out+64ul*id,nearSource+42ul*id,42);quantRow(a,d,local[i],farAt(src,id));continue;}
       int lo=a[0],hi=a[0];for(int v:a){lo=std::min(lo,v);hi=std::max(hi,v);}unsigned cls=unsigned(hi-lo>32)+unsigned(hi-lo>80);
       int16_t sorted[40];for(unsigned k=0;k<40;k++)sorted[k]=a[nearOrder[d][k]];
       alignas(16) float in[16]={},raw[16],sub[16];const auto& cs=local[i];
       for(unsigned k=0;k<cs.n;k++){const float* vec=aqBooks+size_t(((d*3+cls)*10+k)*256+cs.idx[k])*16;
          for(int j=0;j<16;j+=4)_mm_store_ps(in+j,_mm_add_ps(_mm_load_ps(in+j),_mm_loadu_ps(vec+j)));}
       float mn0=1e9f,mx0=-1e9f,mn1=1e9f,mx1=-1e9f;
       for(unsigned j=0;j<16;j++){float sum=0;for(unsigned h=0;h<9;h++)sum+=float(sorted[nearIdx[d][j][h]])*nearWeights[d][j][h];
         float v=(sum+nearWeights[d][j][9])+in[j]/aqScale[d][j];raw[j]=v;sub[j]=v-a[reference[d][j]];
         mn0=std::min(mn0,v);mx0=std::max(mx0,v);mn1=std::min(mn1,sub[j]);mx1=std::max(mx1,sub[j]);}
       int base0=int(std::floor(mn0)),base1=int(std::floor(mn1)),mode=(mx1-base1<mx0-base0)?1:0,base=mode?base1:base0;
       float range=(mode?mx1:mx0)-float(base);require(base>=-2048 && base<=2047 && range<4000,"AQ far range");
       unsigned shift=0;while(range*8.f>255.49f*float(1u<<shift))++shift;require(shift<8,"AQ far shift");
       std::memcpy(out+64ul*id,nearSource+42ul*id,42);auto& dest=farAt(src,id);dest.header=uint16_t(((base+2048)<<4)|(mode<<3)|shift);
       float scale=8.f/float(1u<<shift);const float* v=mode?sub:raw;
       for(unsigned j=0;j<16;j++)dest.v[j]=uint8_t(std::nearbyint((v[j]-float(base))*scale));
       ++levels[mode][shift];
    }
 }
 const uintptr_t lo=(reinterpret_cast<uintptr_t>(aqframes+offsets[4*src])+4095)&~uintptr_t(4095),hi=reinterpret_cast<uintptr_t>(aqframes+offsets[4*src+4])&~uintptr_t(4095);
 if(hi>lo){require(!munmap(reinterpret_cast<void*>(lo),hi-lo),"release packed source");}aq_migrate(src,out);
}
static void onSource(unsigned src,void*){if(src<24)materializeSource(src);}
static int storedResponse(const int16_t* a,unsigned src,unsigned id,unsigned d,unsigned j){
 unsigned x=j/46,y=j%46;if(x<5&&y<8)return a[x*8+y];
 alignas(16) int16_t v[56];std::memcpy(v,a,80);const auto& row=farAt(src,id);int base=(int(row.header>>4)-2048)*8;
 unsigned shift=row.header&7,mode=(row.header>>3)&1;
 if(mode){for(unsigned i=0;i<16;i++)v[40+i]=int16_t(base+(unsigned(row.v[i])<<shift)+8*a[reference[d][i]]);}
 else{for(unsigned i=0;i<16;i++)v[40+i]=int16_t(base+(unsigned(row.v[i])<<shift));}
 float sum=0;for(unsigned k=0;k<9;k++)sum+=float(v[directIndex[d][j][k]])*directWeight[d][j][k];
 return int(std::nearbyint(sum+outputWeights[d][j][9]));
}

static uint16_t rowH[121][550],colV[120][551];
static int area[121][551];
static void init(){
 for(int x=0;x<120;x++)for(int y=0;y<550;y++){int z=!arch.exists(x,y);rowH[x+1][y]=rowH[x][y]+z;colV[x][y+1]=colV[x][y]+z;area[x+1][y+1]=area[x+1][y]+area[x][y+1]-area[x][y]+z;}
}
template<class... Args> static int band(int z, Args... edges){return (0+...+int(z>=edges));}
#include "aqgames7.h"
static inline int physical(const int16_t *a,int x,int y,int tx,int ty,int s,int t,int c,int j,int flag,int delta,int e,int,int){
 const int d=c/120,u0=j/46,v0=j%46,x0=std::min(x,tx),x1=std::max(x,tx),y0=std::min(y,ty),y1=std::max(y,ty);
 const int hole=area[x1+1][y1+1]-area[x0][y1+1]-area[x1+1][y0]+area[x0][y0];
 const int z0=int(rowH[x1+1][y])-rowH[x0][y]+colV[tx][y1+1]-colV[tx][y0];
 const int z1=int(rowH[x1+1][ty])-rowH[x0][ty]+colV[x][y1+1]-colV[x][y0];
 auto slope=[](int q){return band(q,-25,-15,-9,-5,-2,0,1,3,6,10,16,26);};
 auto bd=[](int x,int y){return band(std::min({x,119-x,y,549-y}),1,3,6,12,24,40);};
 auto edge=[](int y){return band(std::min(y%50,49-y%50),1,3,6,12,20);};
 const int nr=a[std::min(4,u0)*8+std::min(7,v0)],dev=slope(e-nr);
 const int u=band(u0,1,2,4,7),v=band(v0,1,2,4,7,12,21,32),ar=band(hole,1,14,70,300,700,1500,3000);
 const int sx=(x>=76)+(x>=90),ex=(tx>=76)+(tx>=90),side=((sx*3+ex)*2+y%100/50)*2+ty%100/50;
 const int sl=a[40],sl2=a[41],sl3=a[42];
 const int rv=band(e,0,40,80,120,160,200,270),route=band(std::min(z0,z1),1,5,14,30,60,120),sb=bd(x,y),tb=bd(tx,ty);
 const int sum=gm0[((dev*8+ar)*5+u)*8+v]+gm1[((dev*13+sl)*5+u)*4+d]+gm2[((dev*8+v)*2+(flag==3))*4+d]+gm3[(ar*8+v)*36+side]
 +gm4[(side*4+d)*5+band(abs(y/50-ty/50),1,2,4,7)]+gm5[((sb*7+tb)*4+d)*5+u]+gm6[(s/8*36+t/8)*4+d];
 return int(std::nearbyint(float(sum)*(1.f/32)));
}

#include "smallplan.inc"
template<bool direct> static inline int singleResponse(const uint8_t* bytes,int base,const int16_t* exact,const FarRow& far,unsigned d,unsigned j){
 const auto& p=sparsePlan[d][j];const int bias=(int(far.header>>4)-2048)*8;const unsigned shift=far.header&7;const bool relative=(far.header&8)!=0;
 float sum=0;
 for(int k=0;k<SPARSE_COUNT;k++){
    unsigned ix=p.nearIx[k];int v=direct?base+int(bytes[ix]):int(exact[ix]);
    if(p.mask&(1u<<k))v=bias+int(unsigned(far.v[p.farIx[k]])<<shift)+(relative?8*v:0);
    else v*=8;
    sum+=float(v)*p.weight[k];}
 return int(std::nearbyint(sum+p.bias));
}
#include "left-vbmi.inc"
static int predict(const Prepared596& st,const int32_t*q){
 if(!st.ready)return st.answer;
 unsigned s=st.pair/288,t=st.pair%288,c=st.context,d=c/120,x=st.qx,y=st.qy,j=46*x+y,id=t*480+c,key=s*138240+id;
 const uint8_t* row=jointSlabs[s]+64ul*id;uint16_t low;std::memcpy(&low,row,2);const uint8_t* b=row+2;const auto& far=*reinterpret_cast<const FarRow*>(row+42);
 int16_t near[43];near[40]=row[60];near[41]=row[61];near[42]=row[62];unsigned nr=8*std::min(x,4u)+std::min(y,7u);bool inside=x<5 && y<8;int value;
 if(!(low&32768)){int base=int(low)-8192;near[nr]=int16_t(base+b[nr]);
#if SPARSE_HEAD==23
 
#endif
    value=inside?near[nr]:singleResponse<true>(b,base,near,far,d,j);}
 else{loadNear40(key,near);value=inside?near[nr]:singleResponse<false>(b,0,near,far,d,j);}
 int trend=125*int(x)+(127-2*int(d%2))*int(y),nom=st.override_cycle?st.cycle:std::max(0,trend+value);
 int answer=int(std::max(0.,nom+st.fee+st.raw)+.5)+st.mandatory,delta=int(std::floor(st.raw+.5))+st.fee+st.mandatory;
 return answer+physical(near,q[0],q[1],q[2],q[3],s,t,c,j,1+2*int(st.ordinary),delta,answer-delta-trend,0,0);
}

}


namespace surf {
struct Row {Prepared596 st{};int q[10]{};};
static inline void prep(int *q,Row& row) {
 auto& sd=ports707[q[8]];auto& td=ports707[q[9]];
 if(sd.source<0 || td.target<0)return;
 q[4]=sd.sf;q[5]=sd.sl;q[6]=td.tf;q[7]=td.tl;
 memcpy(row.q,q,sizeof(row.q));prepare596Production(row.q,row.st);
}
static inline void stage(Row&){}
static inline int value(const Row&r){return aqfar::predict(r.st,r.q);}
}
#include "event_mask.inc"
#include "aq-kernel.inc"
int main(int argc, char** argv) {
    if (argc==2 && std::strcmp(argv[1],"--help")==0) {
        std::puts("usage: estimate -in INPUT -out OUTPUT"); return 0;
    }
    require(argc==5,"use -in INPUT -out OUTPUT");
    const char *input=nullptr,*output=nullptr;
    for (int i=1;i<5;i+=2) {
        if (std::strcmp(argv[i],"-in")==0) input=argv[i+1];
        else if (std::strcmp(argv[i],"-out")==0) output=argv[i+1];
        else require(false,"unknown argument");
    }
    require(input && output && std::strcmp(input,output)!=0,"input/output paths");
    initialize(); auto ti=std::clock(); aqfar::prepMaterial();aqfar::prepWide();near40::initialize(aqfar::onSource,nullptr,true);
    std::fprintf(stderr,"near_and_early %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    for(unsigned src=24;src<208;src++)aqfar::materializeSource(src);
    aqfar::aq_joint_done();aqfar::init();for(unsigned k=0;k<2;k++)for(unsigned j=0;j<8;j++)std::fprintf(stderr,"quant %u %u %u\n",k,j,aqfar::levels[k][j]); std::fprintf(stderr,"aq_init %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    logicalEvent::init();r4::init();r4::initVector();r4::avm::init();r4::avm::aqbatch::init();
 FILE *fin=fopen(input,"rb"),*out=fopen(output,"wb");require(fin&&out,"open");
 require(setvbuf(fin,nullptr,_IONBF,0)==0&&setvbuf(out,nullptr,_IONBF,0)==0,"stdio mode");
 auto qtime=std::clock();querying=true;r4::run(fin,out);querying=false;std::fprintf(stderr,"query_cpu %.9f\n",double(std::clock()-qtime)/CLOCKS_PER_SEC);std::fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",(unsigned long long)r4::rows,(unsigned long long)r4::bad,(unsigned long long)allocations);require(allocations==0,"query heap allocation");fclose(fin);require(fclose(out)==0,"close");return 0;
}
