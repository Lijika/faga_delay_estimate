#include <malloc.h>
#include "../libraries/xz/xz.h"
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

// Only release whole pages still exclusively owned by this live asset.
static void dropReadOnlyAsset(const void* first,size_t bytes) {
 const uintptr_t ps=uintptr_t(sysconf(_SC_PAGESIZE)),lo=uintptr_t(first);
 const uintptr_t a=((lo+ps-1)/ps)*ps,b=((lo+bytes)/ps)*ps;
 if(b>a)require(munmap(reinterpret_cast<void*>(a),b-a)==0,"release consumed readonly asset");
}
// Per-source release unmaps the maximal full-page INTERIOR of each frame group.
template<typename EndOffset> static void dropFrameBoundaries(const uint8_t* data,size_t n,EndOffset endOffset){
 constexpr uintptr_t page=4096;
 if(sysconf(_SC_PAGESIZE)!=long(page))return;
 const uintptr_t a=uintptr_t(data),lo=(a+page-1)&~(page-1),hi=(a+n)&~(page-1);
 uintptr_t prev=0;
 for(unsigned src=0;src<207;src++){
  const uintptr_t end=a+endOffset(src),p=end&~(page-1);
  if(end!=p && p>=lo && p<hi && p!=prev){
   require(!munmap(reinterpret_cast<void*>(p),page),"release live frame boundary");prev=p;
  }
 }
}
extern "C" const uint8_t zsupport[],zsupportEnd[];
extern "C" const int16_t near40graph[],near40graphend[];
static void initialize() {
    arch.loadEmbeddedFast();
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
#include "geometry.inc"
#include "packet-events.inc"
#include "cpu-path.inc"
namespace hotmotion{
struct XRec{uint16_t price,vclass;uint8_t forbidden,region;};
struct YRec{uint16_t price,hclass;uint8_t forbidden,force;};
struct Move{uint16_t coord,price,fee,line;};
static XRec X[120];static YRec Y[550];static Move move[17040+1650];static uint16_t start[496];
static void init(){
 for(unsigned x=0;x<120;x++)X[x]={uint16_t(prefixX707[x]),vertical707[x],uint8_t((x<16)+2*(x>=76&&x<90)),uint8_t(x<76?1:x>=90?2:8)};
 for(unsigned y=0;y<550;y++)Y[y]={uint16_t(prefixY707[y]),horizontal707[y],uint8_t((!arch.exists(0,y))+2*(!arch.exists(80,y))),blockMask707[y]};
 for(unsigned y=0;y<550;y++)for(unsigned x=0;x<120;x++)require(arch.exists(x,y)==!(X[x].forbidden&Y[y].forbidden),"freeze site predicate");
 for(unsigned p=0;p<496;p++){auto&s=ports707[p];start[p]=s.start==65535?17040:s.start;
 if(s.start==65535)continue;bool hor=s.dx!=0;for(unsigned i=0;i<(hor?480:1650);i++){auto z=motion707[s.start+i];move[s.start+i]={z.coordinate,uint16_t(z.coordinate==65535?0:hor?X[z.coordinate].price:Y[z.coordinate].price),z.fee,z.line};}}
 for(unsigned i=0;i<1650;++i)move[17040+i]={uint16_t(i%550),Y[i%550].price,0,0};
}
}


struct Trace {
    float feature[53];
    double response;
    int32_t base, mandatory, prediction;
    double raw;
};

struct Prepared596 {
    unsigned pair=0, context=0;
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
    if (source < 0 || target < 0 || unsigned(sx)>=120||unsigned(tx)>=120||unsigned(sy)>=550||unsigned(ty)>=550) return;
    const auto Sx=hotmotion::X[sx],Tx=hotmotion::X[tx];const auto Sy=hotmotion::Y[sy],Ty=hotmotion::Y[ty];
    if((Sx.forbidden&Sy.forbidden)|(Tx.forbidden&Ty.forbidden))return;
    int ax, ay, fee, firstLine;
    int px,py;
    {unsigned ix=hotmotion::start[sp]+(sd.dx?Sy.hclass+sx:Sx.vclass+sy);
    auto z=hotmotion::move[ix];if(z.coord==65535)return;ax=sd.dx?z.coord:sx;ay=sd.dx?sy:z.coord;
    px=sd.dx?z.price:Sx.price;py=sd.dx?Sy.price:z.price;fee=z.fee;firstLine=z.line;}
    const int ndx=sd.dx, ndy=sd.dy;
    const bool hasNet=sd.start!=65535;
    const int x=tx-ax, y=ty-ay, dx=x+ndx, dy=y+ndy;
    const unsigned bx=unsigned(std::abs(dx)), by=unsigned(std::abs(dy));
    require(bx<=119 && by<=549, "nominal geometry domain");
    const uint32_t geometry=geometry856::tables.xp[dx+119]+geometry856::tables.yp[dy+549];
    const unsigned qx=bx/10, direction=2*(dx<0)+(dy<0);
    const unsigned pair=unsigned(source*288+target), context=geometry&511;

    const int mandatory=firstLine+std::abs(px-Tx.price)+std::abs(py-Ty.price);
    const int sf=q[4], sl=q[5], tf=q[6], tl=q[7];
    const auto Ay=hotmotion::Y[ay];const auto Ax=hotmotion::X[ax];const bool forced=(Ax.region+Tx.region==3&&Ax.region!=Tx.region)&&(Ay.force&Ty.force);
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
    const double raw=ComputeTrace ? ((event ? replacement679(q,ax,ay,ndx,ndy,x,y,fee,forced,fold,event,bands,ends) :
        0.0) + (event==1 ? double(kForcedBias[context*4 + (qx>11 ? 3 : int(qx)/3)]) : 0.)) : (event ? double(eventHot::read(event,sp,tp,sy,ax,ay,tx,ty,geometry)) : 0.0);
#else
    float f[53];
    for (unsigned j=0;j<53;++j) f[j]=float(feature[j]);
    const float raw=residual(f,route,fold);
#endif
    state.pair=pair; state.context=context; state.word=geometry;
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
namespace cold913 {static inline unsigned u8(unsigned);static inline unsigned u16(unsigned);static inline uint32_t u32(unsigned);static inline uint64_t u64(unsigned);static void copy(unsigned,const uint8_t*,unsigned);constexpr unsigned c2=0,shortAt=55831560,atlas=82685248,ring=101435200;static_assert(ring+10063872<=208ul*288*480*4,"cold capacity");}
namespace atlas855 {
static constexpr int D=313,R=12;
static constexpr int16_t dispType[625]={-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,2,3,4,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,5,6,7,8,9,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,10,11,12,13,14,15,16,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,26,27,28,29,30,31,32,33,34,35,36,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,37,38,39,40,41,42,43,44,45,46,47,48,49,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,-1,-1,-1,-1,-1,-1,-1,-1,-1,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,-1,-1,-1,-1,-1,-1,-1,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,-1,-1,-1,-1,-1,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,-1,-1,-1,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,-1,145,146,147,148,149,150,151,152,153,154,155,156,0,157,158,159,160,161,162,163,164,165,166,167,168,-1,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,-1,-1,-1,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,-1,-1,-1,-1,-1,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,-1,-1,-1,-1,-1,-1,-1,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,-1,-1,-1,-1,-1,-1,-1,-1,-1,249,250,251,252,253,254,255,256,257,258,259,260,261,262,263,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,264,265,266,267,268,269,270,271,272,273,274,275,276,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,277,278,279,280,281,282,283,284,285,286,287,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,288,289,290,291,292,293,294,295,296,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,297,298,299,300,301,302,303,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,304,305,306,307,308,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,309,310,311,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,312,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};
static constexpr const char* sNames[208]={"A_AQ0","A_AQ1","A_AY","A_BQ0","A_BQ1","A_BY","A_CQ0","A_CQ1","A_CY","A_DQ0","A_DQ1","A_DY","A_EQ0","A_EQ1","A_EY","A_FQ0","A_FQ1","A_FY","A_GQ0","A_GQ1","A_GY","A_HQ0","A_HQ1","A_HY","S_AQ0","S_AQ1","S_AY","S_BQ0","S_BQ1","S_BY","S_CQ0","S_CQ1","S_CY","S_DQ0","S_DQ1","S_DY","S_EQ0","S_EQ1","S_EY","S_FQ0","S_FQ1","S_FY","S_GQ0","S_GQ1","S_GY","S_HQ0","S_HQ1","S_HY","ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]"},*tNames[288]={"ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]","A_A0","A_A1","A_A2","A_A3","A_A4","A_A5","A_AD","A_AM","A_B0","A_B1","A_B2","A_B3","A_B4","A_B5","A_BD","A_BM","A_C0","A_C1","A_C2","A_C3","A_C4","A_C5","A_CD","A_CM","A_D0","A_D1","A_D2","A_D3","A_D4","A_D5","A_DD","A_DM","A_E0","A_E1","A_E2","A_E3","A_E4","A_E5","A_ED","A_EM","A_F0","A_F1","A_F2","A_F3","A_F4","A_F5","A_FD","A_FM","A_G0","A_G1","A_G2","A_G3","A_G4","A_G5","A_GD","A_GM","A_H0","A_H1","A_H2","A_H3","A_H4","A_H5","A_HD","A_HM","S_A0","S_A1","S_A2","S_A3","S_A4","S_A5","S_AD","S_AM","S_B0","S_B1","S_B2","S_B3","S_B4","S_B5","S_BD","S_BM","S_C0","S_C1","S_C2","S_C3","S_C4","S_C5","S_CD","S_CM","S_D0","S_D1","S_D2","S_D3","S_D4","S_D5","S_DD","S_DM","S_E0","S_E1","S_E2","S_E3","S_E4","S_E5","S_ED","S_EM","S_F0","S_F1","S_F2","S_F3","S_F4","S_F5","S_FD","S_FM","S_G0","S_G1","S_G2","S_G3","S_G4","S_G5","S_GD","S_GM","S_H0","S_H1","S_H2","S_H3","S_H4","S_H5","S_HD","S_HM"};
static uint16_t sm[208],tm[288];
extern "C" const unsigned char atlas855packed[];
asm(".pushsection .rodata\n.p2align 6\n.global atlas855packed\natlas855packed:\n.incbin \"atlas.zst\"\n.popsection");
alignas(64) static uint8_t unpack[D*(2*16*120*2+208*288)];
static void init() {
 for(int p=0;p<496;p++){auto n=arch.portName(p);int s=ports707[p].source,t=ports707[p].target;
  if(s>=0){int j=0;while(j<208&&n!=sNames[j])++j;require(j<208,"atlas source");sm[s]=uint16_t(j);}
  if(t>=0){int j=0;while(j<288&&n!=tNames[j])++j;require(j<288,"atlas target");tm[t]=uint16_t(j);}}
 size_t len=ZSTD_decompress(unpack,sizeof(unpack),atlas855packed,2536603);require(len==sizeof(unpack),"atlas unpack");cold913::copy(cold913::atlas,unpack+D*7680,D*59904);uintptr_t lo=(uintptr_t(unpack+D*7680)+4095)&~uintptr_t(4095),hi=uintptr_t(unpack+sizeof(unpack))&~uintptr_t(4095);if(hi>lo)require(!madvise((void*)lo,hi-lo,MADV_DONTNEED),"atlas cold pages");
}
static inline int correction(int pair,int x,int y,int tx,int ty){
 int dx=tx-x,dy=ty-y;if(std::abs(dx)+std::abs(dy)>R)return 0;
 int i=dispType[(dx+R)*(2*R+1)+dy+R];unsigned off=(i*208u+sm[pair/288])*288u+tm[pair%288];
 unsigned code=cold913::u8(cold913::atlas+off);const auto* ptr=unpack+size_t(i)*7680;
 int16_t a,b;memcpy(&a,ptr+2*((code&15u)*120+x),2);memcpy(&b,ptr+2*((16+(code>>4))*120+x),2);
 return 2*std::max(0,int(a)+int(b));}
}

constexpr unsigned count=208*288*480u;
constexpr uint8_t lenCode[9]={0,1,2,3,4,5,6,8,10};
struct Codes {uint8_t n,idx[10];};
static_assert(sizeof(Codes)==11);
struct FarRow {uint16_t header;uint8_t v[16];};static_assert(sizeof(FarRow)==18);
extern "C" const unsigned char* aq_old42();extern "C" void aq_migrate(unsigned,unsigned char*);extern "C" void aq_joint_done();
static uint8_t* jointSlabs[208];
static constexpr uintptr_t firstVA=UINT64_C(0x20000000000);
static bool contiguous=true;
// Claim the next eight source slabs together only when the whole mapping fits.
// The individual source and noncontiguous fallback still work under ASLR and strict RLIMIT_AS.
static unsigned groupEnd=0;
static uint8_t* allocateSlab(unsigned src,size_t bytes){
 void* want=reinterpret_cast<void*>(firstVA+size_t(src)*bytes);
 if(src<groupEnd)return static_cast<uint8_t*>(want);
 if((src&7)==0){
   void* group=mmap(want,8*bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
   if(group==want){groupEnd=src+8;(void)madvise(group,8*bytes,MADV_HUGEPAGE);return static_cast<uint8_t*>(group);}
   if(group!=MAP_FAILED)munmap(group,8*bytes);
 }
 void* p=mmap(want,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p==MAP_FAILED)p=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 contiguous&=(p==want);
 if(p!=MAP_FAILED)(void)madvise(p,bytes,MADV_HUGEPAGE);
 return static_cast<uint8_t*>(p);
}
static inline const uint8_t* locate(unsigned key){
 if(__builtin_expect(contiguous,true))return reinterpret_cast<const uint8_t*>(firstVA+size_t(key)*64);
 return jointSlabs[key/138240]+size_t(key%138240)*64;
}
namespace cold913 {
static inline uint8_t* data(unsigned byte){return const_cast<uint8_t*>(locate(byte>>2))+59;}
static inline uint32_t word(unsigned byte){uint32_t v;memcpy(&v,data(byte),4);return v;}
static inline unsigned u8(unsigned byte){return data(byte)[byte&3];}
static inline unsigned u16(unsigned byte){uint16_t v;memcpy(&v,data(byte)+(byte&3),2);return v;}
static inline uint32_t u32(unsigned byte){return word(byte);}
static inline uint64_t u64(unsigned byte){return word(byte)|(uint64_t(word(byte+4))<<32);}
static inline void set8(unsigned byte,uint8_t v){data(byte)[byte&3]=v;}
static inline void set16(unsigned byte,uint16_t v){memcpy(data(byte)+(byte&3),&v,2);}
static void copy(unsigned byte,const uint8_t* in,unsigned n){
 while(n&&(byte&3)){set8(byte++,*in++);n--;}
 while(n>=4){memcpy(data(byte),in,4);byte+=4;in+=4;n-=4;}while(n--){set8(byte++,*in++);}}
}
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
alignas(16) static uint16_t selectPoint[4][9][16];
alignas(16) static float packWeight[4][10][16];
static void prepWide(){
 for(unsigned d=0;d<4;d++)for(unsigned j=0;j<16;j++){
    for(unsigned k=0;k<9;k++){selectPoint[d][k][j]=nearOrder[d][nearIdx[d][j][k]];packWeight[d][k][j]=nearWeights[d][j][k];}
    packWeight[d][9][j]=nearWeights[d][j][9];
 }}

// Four SSE2 groups preserve the former 16-lane arithmetic and round-to-even conversion.
template<unsigned D,unsigned K,unsigned G> static inline __m128 termsAQ(const float* af) {
 constexpr auto idx=[](unsigned lane){ return nearOrder[D][nearIdx[D][4*G+lane][K]]; };
 return _mm_setr_ps(af[idx(0)],af[idx(1)],af[idx(2)],af[idx(3)]);
}
template<unsigned D,unsigned G,size_t... K> static inline __m128 sumAQ(const float* af,std::index_sequence<K...>) {
 __m128 s=_mm_setzero_ps();
 ((s=_mm_add_ps(s,_mm_mul_ps(termsAQ<D,K,G>(af),_mm_load_ps(packWeight[D][K]+4*G)))),...);
 return s;
}
template<unsigned d> static inline void directFlat(const int16_t* a,const Codes& cs,uint8_t* dst,int lo){
 int hi=a[0];for(unsigned j=1;j<40;j++)hi=std::max(hi,int(a[j]));
 const unsigned cls=unsigned(hi-lo>32)+unsigned(hi-lo>80);
 // Each exact int16-to-float conversion is reused by all interpolation terms.
 alignas(16) float af[40];
 for(unsigned j=0;j<40;j+=8){
    const auto words=_mm_loadu_si128(reinterpret_cast<const __m128i*>(a+j));
    const auto sign=_mm_srai_epi16(words,15);
    _mm_store_ps(af+j,_mm_cvtepi32_ps(_mm_unpacklo_epi16(words,sign)));
    _mm_store_ps(af+j+4,_mm_cvtepi32_ps(_mm_unpackhi_epi16(words,sign)));
 }
 using Terms=std::make_index_sequence<9>;
 __m128 sum[4]={sumAQ<d,0>(af,Terms{}),sumAQ<d,1>(af,Terms{}),sumAQ<d,2>(af,Terms{}),sumAQ<d,3>(af,Terms{})},in[4]={};
 for(unsigned k=0;k<cs.n;k++){
    const float* vec=aqBooks+size_t(((d*3+cls)*10+k)*256+cs.idx[k])*16;
    for(unsigned g=0;g<4;g++)in[g]=_mm_add_ps(in[g],_mm_loadu_ps(vec+4*g));
 }
 alignas(16) int q3[56];
 for(unsigned j=0;j<40;j++)q3[j]=8*int(a[j]);
 for(unsigned g=0;g<4;g++){
    const auto raw=_mm_add_ps(_mm_add_ps(sum[g],_mm_load_ps(packWeight[d][9]+4*g)),
                             _mm_div_ps(in[g],_mm_loadu_ps(aqScale[d]+4*g)));
    _mm_store_si128(reinterpret_cast<__m128i*>(q3+40+4*g),_mm_cvtps_epi32(_mm_mul_ps(raw,_mm_set1_ps(8.f))));
 }
 int base=8*lo,top=8*hi;
 for(unsigned j=40;j<56;j++){base=std::min(base,q3[j]);top=std::max(top,q3[j]);}
 const int range=top-base;
 unsigned sh=0;while(range>(255<<sh))++sh;
 const auto vb=_mm_set1_epi32(base);const auto inv=_mm_set1_ps(1.f/float(1u<<sh));
 for(unsigned j=0;j<56;j+=8){
    const auto a0=_mm_sub_epi32(_mm_load_si128(reinterpret_cast<const __m128i*>(q3+j)),vb);
    const auto a1=_mm_sub_epi32(_mm_load_si128(reinterpret_cast<const __m128i*>(q3+j+4)),vb);
    const auto x0=_mm_cvtps_epi32(_mm_mul_ps(_mm_cvtepi32_ps(a0),inv));
    const auto x1=_mm_cvtps_epi32(_mm_mul_ps(_mm_cvtepi32_ps(a1),inv));
    const auto words=_mm_packs_epi32(x0,x1);
    _mm_storel_epi64(reinterpret_cast<__m128i*>(dst+j),_mm_packus_epi16(words,words));
 }
 const int16_t b=int16_t(base);memcpy(dst+56,&b,2);dst[58]=uint8_t(sh);
}

static bool useCore512=false;
__attribute__((target("avx512f,avx512bw,avx512dq,avx512vl")))
static void directFlatCore512(const int16_t* a,unsigned d,const Codes& cs,uint8_t* dst){
 const auto part0=_mm512_loadu_si512(a),part1=_mm512_maskz_loadu_epi16(255u,a+32);
 const auto a0=_mm512_cvtepi16_epi32(_mm512_castsi512_si256(part0));
 const auto a1=_mm512_cvtepi16_epi32(_mm512_extracti64x4_epi64(part0,1));
 const auto a2=_mm512_cvtepi16_epi32(_mm512_castsi512_si256(part1));
 int lo=std::min(_mm512_reduce_min_epi32(a0),_mm512_reduce_min_epi32(a1));
 int hi=std::max(_mm512_reduce_max_epi32(a0),_mm512_reduce_max_epi32(a1));
 for(unsigned j=32;j<40;j++){lo=std::min(lo,int(a[j]));hi=std::max(hi,int(a[j]));}
 const unsigned cls=unsigned(hi-lo>32)+unsigned(hi-lo>80);
 __m512 sum=_mm512_setzero_ps(),in=_mm512_setzero_ps();
 for(unsigned k=0;k<9;k++){
  const auto indices=_mm512_maskz_loadu_epi16(65535u,selectPoint[d][k]);
  const auto values=_mm512_permutex2var_epi16(part0,indices,part1);
  const auto x=_mm512_cvtepi32_ps(_mm512_cvtepi16_epi32(_mm512_castsi512_si256(values)));
  sum=_mm512_add_ps(sum,_mm512_mul_ps(x,_mm512_loadu_ps(packWeight[d][k])));
 }
 for(unsigned k=0;k<cs.n;k++)
  in=_mm512_add_ps(in,_mm512_loadu_ps(aqBooks+size_t(((d*3+cls)*10+k)*256+cs.idx[k])*16));
 const auto raw=_mm512_add_ps(_mm512_add_ps(sum,_mm512_loadu_ps(packWeight[d][9])),
                            _mm512_div_ps(in,_mm512_loadu_ps(aqScale[d])));
 const auto far=_mm512_cvtps_epi32(_mm512_mul_ps(raw,_mm512_set1_ps(8.f)));
 const int base=std::min(8*lo,_mm512_reduce_min_epi32(far));
 const int range=std::max(8*hi,_mm512_reduce_max_epi32(far))-base;
 unsigned sh=0;while(range>(255<<sh))++sh;
 const auto vb=_mm512_set1_epi32(base);
 const auto inv=_mm512_set1_ps(1.f/float(1u<<sh));
 #define PACK857(x) _mm512_cvtepi32_epi8(_mm512_cvtps_epi32(_mm512_mul_ps(_mm512_cvtepi32_ps(_mm512_sub_epi32((x),vb)),inv)))
 _mm_storeu_si128(reinterpret_cast<__m128i*>(dst),PACK857(_mm512_slli_epi32(a0,3)));
 _mm_storeu_si128(reinterpret_cast<__m128i*>(dst+16),PACK857(_mm512_slli_epi32(a1,3)));
 _mm_storel_epi64(reinterpret_cast<__m128i*>(dst+32),PACK857(_mm512_slli_epi32(a2,3)));
 _mm_storeu_si128(reinterpret_cast<__m128i*>(dst+40),PACK857(far));
 #undef PACK857
 const int16_t b=int16_t(base);memcpy(dst+56,&b,2);dst[58]=uint8_t(sh);
}

#include "field_source.inc"
// X2F's materializer owns a fixed source slab throughout the 138,240-row pass.
static inline int decodeNativeRow(const near40::NativeView& view,unsigned id,int16_t* value){
 const auto& row=view.rows[id];const int low=int(row.low&32767)-8192;
 const auto center=_mm_set1_epi16(short(low));
 if(!(row.low&32768)){
   for(unsigned j=0;j<40;j+=8){
     const auto bits=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(row.d+j));
     _mm_storeu_si128(reinterpret_cast<__m128i*>(value+j),_mm_add_epi16(center,_mm_unpacklo_epi8(bits,_mm_setzero_si128())));
   }
 }else{
   unsigned n;memcpy(&n,row.d+36,4);
   const auto* ex=reinterpret_cast<const uint8_t*>(&view.planes[n>>14][n&16383]);const auto mask=_mm_set1_epi8(15);
   for(unsigned j=0;j<40;j+=8){
     uint32_t code;memcpy(&code,ex+j/2,4);const auto word=_mm_cvtsi32_si128(int(code));
     const auto high=_mm_unpacklo_epi8(_mm_and_si128(word,mask),_mm_and_si128(_mm_srli_epi16(word,4),mask));
     __m128i bits;
     if(j<32)bits=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(row.d+j));
     else{uint32_t a,b;memcpy(&a,row.d+32,4);memcpy(&b,ex+20,4);bits=_mm_unpacklo_epi32(_mm_cvtsi32_si128(int(a)),_mm_cvtsi32_si128(int(b)));}
     _mm_storeu_si128(reinterpret_cast<__m128i*>(value+j),_mm_add_epi16(center,_mm_unpacklo_epi8(bits,high)));
   }
 }
 return low;
}

static void materializeSource(unsigned src){
 const auto view=near40::nativeRows(src);
 openFieldSource(src);
 constexpr unsigned per=288*480;size_t bytes=size_t(per)*64;
 auto out=allocateSlab(src,bytes);require(out!=MAP_FAILED,"AQ far row allocation");jointSlabs[src]=out;
 std::vector<uint8_t> tmp(34560*11);
 for(unsigned d=0;d<4;d++){unsigned entry=4*src+d,N=34560;
    size_t size=ZSTD_decompress(tmp.data(),tmp.size(),aqframes+offsets[entry],frameBytes[entry]);require(!ZSTD_isError(size)&&size>=17280,"AQ source frame");
    // Each column k lists the kth code of exactly the rows with length > k.
    // A cursor per column lets the consumer decode in its own natural row order.
    unsigned nibbleCounts[16]{};
    for(unsigned key=0;key<N;key+=2){
      const unsigned two=tmp[key/2];++nibbleCounts[two&15];++nibbleCounts[two>>4];
    }
    for(unsigned n=9;n<16;n++)require(!nibbleCounts[n],"AQ source count");
    const uint8_t* columns[10];
    size_t at=N/2;
    for(unsigned k=0;k<10;k++){
      columns[k]=tmp.data()+at;
      for(unsigned n=0;n<9;n++)if(lenCode[n]>k)at+=nibbleCounts[n];
      require(at<=size,"AQ source body");
    }
    require(at==size,"AQ source length");
    for(unsigned i=0;i<N;i++){unsigned id=(i/120)*480+d*120+i%120;int16_t a[40];const int low=decodeNativeRow(view,id,a);
       Codes codes;codes.n=lenCode[(tmp[i/2]>>(4*(i%2)))&15];
       for(unsigned k=0;k<codes.n;k++)codes.idx[k]=*columns[k]++;
       auto tail=out+64ul*id+60;
       const unsigned slope=geometry856::tables.slope[26+std::clamp(a[23]-a[21],-26,26)];tail[3]=sourceField(src,i/120,d,i%120);
       if(useCore512)directFlatCore512(a,d,codes,out+64ul*id);
       else switch(d){
         case 0: directFlat<0>(a,codes,out+64ul*id,low); break;
         case 1: directFlat<1>(a,codes,out+64ul*id,low); break;
         case 2: directFlat<2>(a,codes,out+64ul*id,low); break;
         default:directFlat<3>(a,codes,out+64ul*id,low); break;
       }
       auto* dst=out+64ul*id;require(dst[58]<16&&slope<16,"four-bit fields");dst[58]|=slope<<4;
    }
 }
 const uintptr_t lo=(reinterpret_cast<uintptr_t>(aqframes+offsets[4*src])+4095)&~uintptr_t(4095),hi=reinterpret_cast<uintptr_t>(aqframes+offsets[4*src+4])&~uintptr_t(4095);
 if(hi>lo){require(!munmap(reinterpret_cast<void*>(lo),hi-lo),"release packed source");}aq_migrate(src,out);
 near40::releaseMaterialized(src);
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

static int area[121][551];
static void init(){
 for(int x=0;x<120;x++)for(int y=0;y<550;y++){int z=!arch.exists(x,y);area[x+1][y+1]=area[x+1][y]+area[x][y+1]-area[x][y]+z;}
}
template<class... Args> static int band(int z, Args... edges){return (0+...+int(z>=edges));}
#include "g4.h"
struct XShape { uint16_t left,center; uint8_t side; };
struct YShape { uint16_t low,center; };
static XShape xs[120][120];
static YShape ys[551];
static int32_t mid[13][13][40][4][2],bb0[13][8][40],bb3[8][8][36];
static uint8_t areaBand[3001],ypart[550];
static void initCost(){
 for(auto v:gm3)require(v>=-4096&&v<=4095,"packed G4 geography");
 for(int i=0;i<120;i++)for(int j=0;j<120;j++){
    auto span=[&](int l,int r){return uint16_t(std::max(0,std::min(std::max(i,j)+1,r)-std::max(std::min(i,j),l)));};
    xs[i][j]={span(0,16),span(76,90),uint8_t(((i>=76)+(i>=90))*3+(j>=76)+(j>=90))};
 }
 for(int y=0;y<=550;y++)ys[y]={uint16_t(std::min(y,100)),uint16_t(y/100*50+std::min(y%100,50))};
 for(int y=0;y<550;y++)ypart[y]=y%100/50;
 for(int x=0;x<=120;x++)for(int y=0;y<=550;y++)require(area[x][y]==std::min(x,16)*ys[y].low+std::clamp(x-76,0,14)*ys[y].center,"hole prefix");
 for(int q=0;q<3001;++q)areaBand[q]=band(q,1,14,70,300,700,1500,3000);
 for(int d=0;d<13;d++)for(int s=0;s<13;s++)for(int uv=0;uv<40;uv++)for(int h=0;h<4;h++)for(int n=0;n<2;n++)
   mid[d][s][uv][h][n]=gm1[((d*13+s)*5+uv/8)*4+h]+gm2[((d*8+uv%8)*2+n)*4+h];
 for(int d=0;d<13;d++)for(int a=0;a<8;a++)for(int uv=0;uv<40;uv++)bb0[d][a][uv]=gm0[(d*8+a)*40+uv];
 for(int a=0;a<8;a++)for(int v=0;v<8;v++)for(int g=0;g<36;g++)bb3[a][v][g]=gm3[(a*8+v)*36+g];
}
static inline int physical(int recent,int sl,unsigned head,int x,int y,int tx,int ty,unsigned d,bool ordinary,int e){
 const auto a=xs[x][tx];const auto l=ys[std::min(y,ty)],h=ys[std::max(y,ty)+1];
 const unsigned ar=areaBand[std::min(3000,a.left*(h.low-l.low)+a.center*(h.center-l.center))],side=a.side*4+ypart[y]*2+ypart[ty],uv=head&63;
 const int dev=geometry856::tables.slope[std::clamp(e-recent,-26,26)+26];
 const int sum=bb0[dev][ar][uv]+mid[dev][sl][uv][d][ordinary]+bb3[ar][uv%8][side];
 return (int(uint32_t(sum+65536+16)>>5)-2048-int((unsigned(sum)&63)==16));
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
struct FlatPlan {float w[SPARSE_COUNT],bias;uint8_t ix[SPARSE_COUNT];};
static FlatPlan flat[4][552];
static void initFlat(){
 for(int d=0;d<4;d++)for(int j=0;j<552;j++){const auto& a=sparsePlan[d][j];auto& f=flat[d][j];
  for(int t=0;t<SPARSE_COUNT;t++){f.w[t]=a.weight[t];f.ix[t]=(a.mask>>t&1)?40+a.farIx[t]:a.nearIx[t];}f.bias=a.bias;}
}
static inline int baseFlat(const uint8_t* p){int16_t b;std::memcpy(&b,p+56,2);return b;}
static inline int nearFlat(const uint8_t* p,int n,int b,unsigned sh){
 return _mm_cvtss_si32(_mm_set_ss(float(b+(int(p[n])<<sh))*.125f));}


struct alignas(32) DotPlan {
 uint64_t weights;
 uint32_t indices;
 float sum,bias;
 float scale;
 uint32_t pad[2];
};static_assert(sizeof(DotPlan)==32);
static DotPlan dq[4*552];
static void initDot(){
 for(unsigned d=0;d<4;d++)for(unsigned j=0;j<552;j++){auto &x=flat[d][j];auto &q=dq[d*552+j];
  int frac=19;float mx=0;for(auto v:x.w)mx=std::max(mx,std::abs(v));
  while(frac&&mx*float(1<<frac)>32767.f)--frac;
  int16_t z[4];q.sum=0;
  for(unsigned t=0;t<4;t++){z[t]=int16_t(std::nearbyint(x.w[t]*float(1<<frac)));q.sum+=x.w[t];}
  memcpy(&q.indices,x.ix,4);memcpy(&q.weights,z,8);
  q.bias=x.bias;q.scale=1.f/float(1<<frac);
 }
}
static inline int responsePlan(const uint8_t* row,int base,unsigned sh,unsigned plan){
    const auto& p=dq[plan];const uint32_t ix=p.indices;
    const uint32_t packed=uint32_t(row[uint8_t(ix)]) |
        (uint32_t(row[uint8_t(ix>>8)])<<8) |
        (uint32_t(row[uint8_t(ix>>16)])<<16) |
        (uint32_t(row[uint8_t(ix>>24)])<<24);
    const auto bytes=_mm_unpacklo_epi8(_mm_cvtsi32_si128(packed),_mm_setzero_si128());
    const auto products=_mm_madd_epi16(bytes,_mm_cvtsi64_si128(p.weights));
    const int dot=_mm_cvtsi128_si32(_mm_add_epi32(products,_mm_srli_si128(products,4)));
    return _mm_cvtss_si32(_mm_set_ss((float(base)*p.sum+float(dot)*(p.scale*float(1u<<sh)))+p.bias));
   }
static inline int responseFlat(const uint8_t* row,int base,unsigned sh,unsigned d,unsigned j){return responsePlan(row,base,sh,d*552+j);}
#include "cut.inc"
}
#include "stripe.inc"
#include "env_margin.inc"
#include "newring.inc"
#include "bill-flow.inc"
namespace aqfar {
constexpr int minG4(){int z=0; for(auto arr:{std::pair<const int16_t*,size_t>{gm0,sizeof(gm0)/2},{gm1,sizeof(gm1)/2},{gm2,sizeof(gm2)/2},{gm3,sizeof(gm3)/2}}){int v=0;for(size_t i=0;i<arr.second;i++)v=std::min(v,int(arr.first[i]));z+=v;}return (-z+31)/32;}
static int predict(const Prepared596& st,const int32_t*q,int* ticket=nullptr){
 if(!st.ready)return newring::scalar(q,envcert::small(q,st.answer));
 unsigned c=st.context,d=c/120,j=(st.word>>9)&1023,key=st.pair*480+c;
 const unsigned head=geometry856::tables.head[d][j];
 const uint8_t* row=locate(key);unsigned nr=(head>>16)&63;bool inside=head&(1u<<23);
 int bb=baseFlat(row);unsigned sh=row[58]&15;int recent=int16_t(nearFlat(row,nr,bb,sh));
 int value=inside?recent:responseFlat(row,bb,sh,d,j);
 int trend=int(st.word>>19),nom=st.override_cycle?st.cycle:std::max(0,trend+value);
 int answer,delta,e;
 if(st.ordinary){
  delta=st.fee+st.mandatory;answer=nom+delta;e=nom-trend;
 }else{
  answer=int(std::max(0.,nom+st.fee+st.raw)+.5)+st.mandatory;
  delta=int(std::floor(st.raw+.5))+st.fee+st.mandatory;e=answer-delta-trend;
 }
 const int distance=std::abs(q[0]-q[2])+std::abs(q[1]-q[3]);
 // The finite bound means the old prior cannot be negative even before the nonnegative atlas term.
 // A replacement has no data dependency on that prior after the sign check.
 if(distance<=4 && answer>=minG4()){
  if(distance<=2){
   const int v=stripe::cert(q[0],q[1],q[8],q[2],q[3],q[9],INT_MAX);
   if(v!=INT_MAX)return envcert::refine(q[0],q[1],q[8],q[2],q[3],q[9],v);
  }else if(inside){
   int r=newring::residue(q[0],q[1],q[8],q[2],q[3],q[9]);
   if(r!=-128)return trend+value+st.fee+st.mandatory+8*r;
  }
 }
 const int pre=answer+physical(recent,row[58]>>4,head,q[0],q[1],q[2],q[3],d,st.ordinary,e);
 if(ticket && distance>=5 && distance<=55){
   bills::add(ticket,std::max(0,trend+value)+delta,q[0],q[1],q[2],q[3],key,j,row[63],distance);return pre;
 }
 const int prior=pre+atlas855::correction(st.pair,q[0],q[1],q[2],q[3]);
 if(distance<=4)return newring::scalar(q,envcert::small(q,prior));
 return distance>=5 && distance<=55 ?
  tariff::price_result(prior,std::max(0,trend+value)+delta,key,j,row[63],q[0],q[2]):prior;
}

}


#include "short-gate.inc"
#include "short-flow.inc"
#include "route-x.inc"
#include "native-query.inc"
#include "axis-route.inc"
#include "instant-geo.inc"
namespace surf {
struct Ticket{
 uint32_t key=0,word=0;
 union{uint32_t head=0;int cycle;};
 uint16_t geom=0,range=0;
 int16_t effective=0,floor=0;
 int8_t answer=-1;bool ready=false,ordinary=false;
};
struct Row{Ticket st{};int q[10]{};};
static_assert(sizeof(Ticket)==24&&sizeof(Row)==64,"bounded native lane");
static constexpr int kCertified=-2,kLegacy=-7,kUnified=-6;
static inline void start(Row&r){
 const int* q=r.q;auto& st=r.st;
 const int sx=q[0],sy=q[1],tx=q[2],ty=q[3],sp=q[8],tp=q[9];
 if(unsigned(sx)>=120||unsigned(tx)>=120||unsigned(sy)>=550||unsigned(ty)>=550)return;
 const uint32_t sw=nativeQuery::startCode[sp],tw=nativeQuery::endCode[tp];
 if((sw|tw)>>31)return;
 const int dx=tx-sx,dy=ty-sy,dist=std::abs(dx)+std::abs(dy);
 if(sp==tp&&!dist){st.answer=kLegacy;st.ready=true;return;}
 
 const auto ys=axisRoute::yBanks[(sw>>4)&15][sy];
 const auto xs0=axisRoute::xBanks[sw&15][unsigned(sy)/50%2][sx];
 const auto xt=axisRoute::targetX[tx];const auto yt=axisRoute::targetY[ty];
 if(!(ys.flags&xs0.flags&240)||!(xt.ok&yt.allowed))return;
 if(dist<=4) {
  st.ready=true;
  if(sp==tp){st.answer=kLegacy;return;}
  const unsigned pair=unsigned(stripe::src[sp])*288+stripe::dst[tp];
  if(dist<=2){
    const unsigned gd=stripe::disp[(dx+2)*5+dy+2];
    __builtin_prefetch(stripe::shortHead+gd*59904+pair,0,1);
    st.answer=kCertified;return;
  }
  const unsigned di=newring::rmap[(dx+4)*9+dy+4];
  st.key=aqfar::cold913::ring+8*(di*59904+pair);
  st.effective=int16_t(xs0.delay+(ys.flags&8)+std::abs(int(xs0.px)-xt.px)+std::abs(int(((ys.band+1)/2)*8)-yt.py));
  st.geom=unsigned(xs0.adj!=0);
  __builtin_prefetch(aqfar::cold913::data(st.key),0,1);st.answer=-5;return;
 }
 const int srcAdj=xs0.adj,srcDelay=xs0.delay+(ys.flags&8);
 const int srcPX=xs0.px,srcPY=((ys.band+1)/2)*8,srcSide=xs0.flags&3;
 const bool event=axisRoute::event(srcSide,xt.side,ys.band,yt.band);
 int nx=dx+srcAdj;
 if(sp==tp&&!nx&&!dy){st.ready=true;st.answer=kLegacy;return;}
 const int fees=srcDelay+std::abs(int(srcPX)-xt.px)+std::abs(int(srcPY)-yt.py);
 unsigned w=geometry856::tables.xp[nx+119]+geometry856::tables.yp[dy+549];
 int correction=0,floor=0;
 if(event){
  floor=fees-int(srcDelay)+std::abs(int(srcPX)-prefixX707[sx])+std::abs(int(srcPY)-prefixY707[sy]);
  const auto& sd=ports707[sp];correction=eventHot::read(srcSide==1?2u:1u,sp,tp,sy,sx+sd.dx-srcAdj,sy+sd.dy,tx,ty,w);
 }
 st.ready=true;
 st.answer=kUnified;
 const unsigned c=w&511u,d=c/120;
 st.key=(sw&~1023u)+tw+c;__builtin_prefetch(aqfar::locate(st.key),0,3);
 st.word=w;st.head=geometry856::tables.head[d][(w>>9)&1023];
 const uint32_t xs=nativeQuery::X[sx][tx],span=nativeQuery::Y[std::max(sy,ty)+1]-nativeQuery::Y[std::min(sy,ty)];
 const unsigned count=(uint64_t(xs&0x00ff00ffu)*span>>16)&65535u;
 const unsigned ar=aqfar::areaBand[std::min(3000u,count)],side=(((xs>>8)&15)*4)+aqfar::ypart[sy]*2+aqfar::ypart[ty];st.geom=uint16_t((ar<<13)+4096+aqfar::bb3[ar][st.head&7][side]);
 st.range=uint16_t((dist<<2)+d);st.effective=int16_t(fees+correction);st.floor=int16_t(floor);st.ordinary=!event;
}
static inline void prep(int *q,Row&r){
 if(ports707[q[8]].source<0||ports707[q[9]].target<0)return;
 r.q[0]=q[0];r.q[1]=q[1];r.q[2]=q[2];r.q[3]=q[3];r.q[8]=q[8];r.q[9]=q[9];start(r);
}
static __attribute__((noinline)) int reference(const Row&r){
 int q[10];memcpy(q,r.q,sizeof(q));
 const auto& sd=ports707[q[8]];const auto& td=ports707[q[9]];
 q[4]=sd.sf;q[5]=sd.sl;q[6]=td.tf;q[7]=td.tl;Prepared596 p{};prepare596Production(q,p);return aqfar::predict(p,q);
}
struct Samples{int recent,value;unsigned slope,tag;};
static inline Samples samples(const Row&r){
 const auto& st=r.st;const uint8_t* row=aqfar::locate(st.key);
 int b=aqfar::baseFlat(row);unsigned sh=row[58]&15,head=st.head;
 int n=int16_t(aqfar::nearFlat(row,(head>>16)&63,b,sh));
 return {n,head&(1u<<23)?n:aqfar::responseFlat(row,b,sh,st.range&3,(st.word>>9)&1023),unsigned(row[58]>>4),row[63]};
}
static inline int finish(const Row&r,Samples f,int* deferredOut){
 const auto& st=r.st;const int*q=r.q;unsigned uv=st.head&63,d=st.range&3,distance=st.range>>2;
 const int trend=st.word>>19,nom=std::max(0,trend+f.value),intrinsic=nom+st.effective;
 const int answer=std::max(int(st.floor),intrinsic);
 const int dev=geometry856::tables.slope[std::clamp(answer-int(st.effective)-trend-f.recent,-26,26)+26];
 const unsigned ar=st.geom>>13;const int sideTerm=int(st.geom&8191)-4096;
 const int sum=aqfar::bb0[dev][ar][uv]+aqfar::mid[dev][f.slope][uv][d][st.ordinary]+sideTerm;
 int base=answer+(int(uint32_t(sum+65536+16)>>5)-2048-int((unsigned(sum)&63)==16));
 if(distance>55)return base;
 if(deferredOut){bills::add(deferredOut,intrinsic,q[0],q[1],q[2],q[3],st.key,(st.word>>9)&1023,f.tag,distance);return base;}
 if(distance<=12)base+=aqfar::atlas855::correction(st.key/480,q[0],q[1],q[2],q[3]);
 return aqfar::tariff::price_result(base,intrinsic,st.key,(st.word>>9)&1023,f.tag,q[0],q[2]);
}
static inline int value(const Row&r,int* deferredOut=nullptr){
 if(r.st.answer==kUnified)return finish(r,samples(r),deferredOut);
 if(r.st.answer==-4)return r.st.cycle;
 if(r.st.answer==-5){auto q=r.q;int v=newring::direct(r.st.key,r.st.geom!=0,q[0],q[1]%100<50,r.st.effective);if(v!=INT_MAX)return v;return reference(r);}
 if(r.st.answer==kCertified){auto q=r.q;int v=stripe::cert(q[0],q[1],q[8],q[2],q[3],q[9],INT_MAX);
  if(v!=INT_MAX)return envcert::refine(q[0],q[1],q[8],q[2],q[3],q[9],v);}
 return r.st.ready?reference(r):-1;
}
}
#include "rounded.inc"
#include "tiny5.inc"
#include "hot-packet.inc"
#include "aq-kernel.inc"
#include "cascade-kernel.inc"
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
    const bool cascade=cpu857::selected();
    std::fprintf(stderr,"cpu_path %s\n",cascade?"cascade_cert16e":"generic_sse2");
    aqfar::useCore512=cascade;
    initialize(); hotmotion::init(); eventHot::init();auto ti=std::clock(); aqfar::prepMaterial();aqfar::prepWide();aqfar::initFlat();aqfar::initDot();near40::useTiledRows();near40::initialize(aqfar::onSource,nullptr,true,cascade);
    dropReadOnlyAsset(zsupport,uintptr_t(zsupportEnd)-uintptr_t(zsupport));
    dropReadOnlyAsset(near40graph,uintptr_t(near40graphend)-uintptr_t(near40graph));
    std::fprintf(stderr,"near_and_early %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    for(unsigned src=24;src<208;src++)aqfar::materializeSource(src);
    aqfar::aq_joint_done();
    dropFrameBoundaries(aqframes,aqfar::offsets[832],[](unsigned src){return aqfar::offsets[4*(src+1)];});
    unsigned fieldEnd=0;dropFrameBoundaries(aqfar::newField,uintptr_t(aqfar::newFieldEnd)-uintptr_t(aqfar::newField),[&](unsigned src){return fieldEnd+=aqfar::fieldFrame[src];});

    {const uintptr_t begin=(uintptr_t(aqBooks)+4095)&~uintptr_t(4095);
     const uintptr_t end=(uintptr_t(aqBooks)+1966080)&~uintptr_t(4095);
     if(end>begin)require(!munmap(reinterpret_cast<void*>(begin),end-begin),"release codebook");}
    aqfar::init();aqfar::initCost();nativeQuery::init();axisRoute::init();instantGeo::init();round60::init();tiny5::init();for(unsigned k=0;k<2;k++)for(unsigned j=0;j<8;j++)std::fprintf(stderr,"quant %u %u %u\n",k,j,aqfar::levels[k][j]); std::fprintf(stderr,"aq_init %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    std::fprintf(stderr,"contiguous %u\n",unsigned(aqfar::contiguous));r4::init();if(cascade)cascade857::init();
 aqfar::atlas855::init();dropReadOnlyAsset(aqfar::atlas855::atlas855packed,2536603);stripe::openColumn();stripe::initPlace();malloc_trim(0);envcert::ready();dropReadOnlyAsset(envcert::envFrames,uintptr_t(envcert::envEnd)-uintptr_t(envcert::envFrames));
 stripe::ready(arch);newring::init();malloc_trim(0);aqfar::tariff::init();malloc_trim(0);
 stripe::initQuick();
 FILE *fin=fopen(input,"rb"),*out=fopen(output,"wb");require(fin&&out,"open");
 require(setvbuf(fin,nullptr,_IONBF,0)==0&&setvbuf(out,nullptr,_IONBF,0)==0,"stdio mode");
 querying=true;if(cascade)r4::run<true>(fin,out);else r4::run(fin,out);querying=false;require(allocations==0,"query heap allocation");fclose(fin);require(fclose(out)==0,"close");return 0;
}
