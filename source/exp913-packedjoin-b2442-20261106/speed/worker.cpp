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
#include "geometry.inc"
#include "cpu-path.inc"

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
    if (source < 0 || target < 0 || !arch.exists(sx,sy) || !arch.exists(tx,ty)) return;
    int ax, ay, fee, firstLine;
    if (!first707(sx,sy,sd,ax,ay,fee,firstLine)) return;
    const int ndx=sd.dx, ndy=sd.dy;
    const bool hasNet=sd.start!=65535;
    const int x=tx-ax, y=ty-ay, dx=x+ndx, dy=y+ndy;
    const unsigned bx=unsigned(std::abs(dx)), by=unsigned(std::abs(dy));
    require(bx<=119 && by<=549, "nominal geometry domain");
    const uint32_t geometry=geometry856::tables.xp[dx+119]+geometry856::tables.yp[dy+549];
    const unsigned qx=bx/10, direction=2*(dx<0)+(dy<0);
    const unsigned pair=unsigned(source*288+target), context=geometry&511;

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
 size_t len=ZSTD_decompress(unpack,sizeof(unpack),atlas855packed,2536603);require(len==sizeof(unpack),"atlas unpack");
}
static inline int correction(int pair,int x,int y,int tx,int ty){
 int dx=tx-x,dy=ty-y;if(std::abs(dx)+std::abs(dy)>R)return 0;
 int i=dispType[(dx+R)*(2*R+1)+dy+R];unsigned off=(i*208u+sm[pair/288])*288u+tm[pair%288];
 unsigned code=unpack[D*7680u+off];const auto* ptr=unpack+size_t(i)*7680;
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
static uint8_t* allocateSlab(unsigned src,size_t bytes){
 void* want=reinterpret_cast<void*>(firstVA+size_t(src)*bytes);
 void* p=mmap(want,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p==MAP_FAILED)p=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 contiguous&=(p==want);
 return static_cast<uint8_t*>(p);
}
static inline const uint8_t* locate(unsigned key){
 if(__builtin_expect(contiguous,true))return reinterpret_cast<const uint8_t*>(firstVA+size_t(key)*64);
 return jointSlabs[key/138240]+size_t(key%138240)*64;
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
static void directFlat(const int16_t* a,unsigned d,const Codes& cs,uint8_t* dst){
 int lo=a[0],hi=a[0];for(unsigned j=1;j<40;j++){lo=std::min(lo,int(a[j]));hi=std::max(hi,int(a[j]));}
 const unsigned cls=unsigned(hi-lo>32)+unsigned(hi-lo>80);
 // Each exact int16-to-float conversion is reused by all interpolation terms.
 alignas(16) float af[40];
 for(unsigned j=0;j<40;j+=8){
    const auto words=_mm_loadu_si128(reinterpret_cast<const __m128i*>(a+j));
    const auto sign=_mm_srai_epi16(words,15);
    _mm_store_ps(af+j,_mm_cvtepi32_ps(_mm_unpacklo_epi16(words,sign)));
    _mm_store_ps(af+j+4,_mm_cvtepi32_ps(_mm_unpackhi_epi16(words,sign)));
 }
 __m128 sum[4]={},in[4]={};
 for(unsigned k=0;k<9;k++)for(unsigned g=0;g<4;g++){
    const auto* ix=selectPoint[d][k]+4*g;
    const auto x=_mm_setr_ps(af[ix[0]],af[ix[1]],af[ix[2]],af[ix[3]]);
    sum[g]=_mm_add_ps(sum[g],_mm_mul_ps(x,_mm_load_ps(packWeight[d][k]+4*g)));
 }
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
static void materializeSource(unsigned src){
 openFieldSource(src);
 constexpr unsigned per=288*480;size_t bytes=size_t(per)*64;
 auto out=allocateSlab(src,bytes);require(out!=MAP_FAILED,"AQ far row allocation");jointSlabs[src]=out;
 (void)madvise(out,bytes,MADV_HUGEPAGE);std::vector<uint8_t> tmp(34560*11);std::vector<Codes> local(34560);
 for(unsigned d=0;d<4;d++){unsigned entry=4*src+d,N=34560;
    size_t size=ZSTD_decompress(tmp.data(),tmp.size(),aqframes+offsets[entry],frameBytes[entry]);require(!ZSTD_isError(size)&&size>=17280,"AQ source frame");
    size_t at=17280;for(unsigned key=0;key<N;key++){int n=(tmp[key>>1]>>(4*(key&1)))&15;require(n<9,"AQ source count");local[key].n=lenCode[n];}
    for(unsigned k=0;k<10;k++)for(unsigned key=0;key<N;key++)if(local[key].n>k){require(at<size,"AQ source body");local[key].idx[k]=tmp[at++];}
    require(at==size,"AQ source length");
    for(unsigned i=0;i<N;i++){unsigned id=(i/120)*480+d*120+i%120,key=src*per+id;int16_t a[40];near40::load40(key,a);
       auto slopeBand=[](int v){return (v>=-25)+(v>=-15)+(v>=-9)+(v>=-5)+(v>=-2)+(v>=0)+(v>=1)+(v>=3)+(v>=6)+(v>=10)+(v>=16)+(v>=26);};
       auto tail=out+64ul*id+60;
       tail[0]=slopeBand(a[23]-a[21]);tail[1]=slopeBand(a[39]-a[32]);tail[2]=slopeBand(a[39]-a[7]);tail[3]=sourceField(src,i/120,d,i%120);
       if(useCore512)directFlatCore512(a,d,local[i],out+64ul*id);
       else directFlat(a,d,local[i],out+64ul*id);
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

static uint16_t rowH[121][550],colV[120][551];
static int area[121][551];
static void init(){
 for(int x=0;x<120;x++)for(int y=0;y<550;y++){int z=!arch.exists(x,y);rowH[x+1][y]=rowH[x][y]+z;colV[x][y+1]=colV[x][y]+z;area[x+1][y+1]=area[x+1][y]+area[x][y+1]-area[x][y]+z;}
}
template<class... Args> static int band(int z, Args... edges){return (0+...+int(z>=edges));}
#include "g4.h"
static inline int physical(const int16_t *a,int x,int y,int tx,int ty,int s,int t,int c,int j,int flag,int delta,int e,int,int){
 const int d=c/120,x0=std::min(x,tx),x1=std::max(x,tx),y0=std::min(y,ty),y1=std::max(y,ty);
 const unsigned head=geometry856::tables.head[d][j];
 const int hole=area[x1+1][y1+1]-area[x0][y1+1]-area[x1+1][y0]+area[x0][y0];
 const int z0=int(rowH[x1+1][y])-rowH[x0][y]+colV[tx][y1+1]-colV[tx][y0];
 const int z1=int(rowH[x1+1][ty])-rowH[x0][ty]+colV[x][y1+1]-colV[x][y0];
 auto bd=[](int x,int y){return band(std::min({x,119-x,y,549-y}),1,3,6,12,24,40);};
 auto edge=[](int y){return band(std::min(y%50,49-y%50),1,3,6,12,20);};
 const int nr=a[(head>>16)&63],dev=geometry856::tables.slope[std::clamp(e-nr,-26,26)+26];
 const int v=head&7,ar=band(hole,1,14,70,300,700,1500,3000);
 const int sx=(x>=76)+(x>=90),ex=(tx>=76)+(tx>=90),side=((sx*3+ex)*2+y%100/50)*2+ty%100/50;
 const int sl=a[40],sl2=a[41],sl3=a[42];
 const int rv=band(e,0,40,80,120,160,200,270),route=band(std::min(z0,z1),1,5,14,30,60,120),sb=bd(x,y),tb=bd(tx,ty);
 const int sum=gm0[dev*320+ar*40+(head&63)]+gm1[dev*260+sl*20+((head>>8)&31)]+gm2[((dev*8+v)*2+(flag==3))*4+d]+gm3[(ar*8+v)*36+side];
 return _mm_cvtss_si32(_mm_set_ss(float(sum)*(1.f/32)));
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
static DotPlan dq[4][552];
static void initDot(){
 for(unsigned d=0;d<4;d++)for(unsigned j=0;j<552;j++){auto &x=flat[d][j];auto &q=dq[d][j];
  int frac=19;float mx=0;for(auto v:x.w)mx=std::max(mx,std::abs(v));
  while(frac&&mx*float(1<<frac)>32767.f)--frac;
  int16_t z[4];q.sum=0;
  for(unsigned t=0;t<4;t++){z[t]=int16_t(std::nearbyint(x.w[t]*float(1<<frac)));q.sum+=x.w[t];}
  memcpy(&q.indices,x.ix,4);memcpy(&q.weights,z,8);
  q.bias=x.bias;q.scale=1.f/float(1<<frac);
 }
}
static inline int responseFlat(const uint8_t* row,int base,unsigned sh,unsigned d,unsigned j){
    const auto& p=dq[d][j];const uint32_t ix=p.indices;
    const uint32_t packed=uint32_t(row[uint8_t(ix)]) |
        (uint32_t(row[uint8_t(ix>>8)])<<8) |
        (uint32_t(row[uint8_t(ix>>16)])<<16) |
        (uint32_t(row[uint8_t(ix>>24)])<<24);
    const auto bytes=_mm_unpacklo_epi8(_mm_cvtsi32_si128(packed),_mm_setzero_si128());
    const auto products=_mm_madd_epi16(bytes,_mm_cvtsi64_si128(p.weights));
    const int dot=_mm_cvtsi128_si32(_mm_add_epi32(products,_mm_srli_si128(products,4)));
    return _mm_cvtss_si32(_mm_set_ss((float(base)*p.sum+float(dot)*(p.scale*float(1u<<sh)))+p.bias));
   }
#include "cut.inc"
static int predict(const Prepared596& st,const int32_t*q){
 if(!st.ready)return st.answer;
 unsigned s=st.pair/288,t=st.pair%288,c=st.context,d=c/120,j=(st.word>>9)&1023,id=t*480+c,key=s*138240+id;
 const unsigned head=geometry856::tables.head[d][j];
 const uint8_t* row=locate(key);uint16_t low;std::memcpy(&low,row,2);const uint8_t* b=row+2;const auto& far=*reinterpret_cast<const FarRow*>(row+42);
 int16_t near[43];near[40]=row[60];near[41]=row[61];near[42]=row[62];unsigned nr=(head>>16)&63;bool inside=head&(1u<<23);int value;
 int bb=baseFlat(row);unsigned sh=row[58];near[nr]=nearFlat(row,nr,bb,sh);
 value=inside?near[nr]:responseFlat(row,bb,sh,d,j);
 int trend=int(st.word>>19),nom=st.override_cycle?st.cycle:std::max(0,trend+value);
 int answer,delta,e;
 if(st.ordinary){
  delta=st.fee+st.mandatory;answer=nom+delta;e=nom-trend;
 }else{
  answer=int(std::max(0.,nom+st.fee+st.raw)+.5)+st.mandatory;
  delta=int(std::floor(st.raw+.5))+st.fee+st.mandatory;e=answer-delta-trend;
 }
 const int prior=atlas855::correction(st.pair,q[0],q[1],q[2],q[3])+answer+
  physical(near,q[0],q[1],q[2],q[3],s,t,c,j,1+2*int(st.ordinary),delta,e,0,0);
 const int distance=std::abs(q[0]-q[2])+std::abs(q[1]-q[3]);
 return distance>=5 && distance<=55 ?
  tariff::price_result(prior,std::max(0,trend+value)+delta,key,j,row[63],q[0],q[2]):prior;
}

}


namespace surf {
struct Row {Prepared596 st{};int q[10]{};};
static inline void prep(int *q,Row& row) {
 auto& sd=ports707[q[8]];auto& td=ports707[q[9]];
 if(sd.source<0 || td.target<0)return;
 q[4]=sd.sf;q[5]=sd.sl;q[6]=td.tf;q[7]=td.tl;
 memcpy(row.q,q,sizeof(row.q));prepare596Production(row.q,row.st);
 if(row.st.ready)_mm_prefetch(reinterpret_cast<const char*>(aqfar::locate(row.st.pair*480+row.st.context)),_MM_HINT_T0);
}
static inline void stage(Row& row){
 if(row.st.ready)_mm_prefetch(reinterpret_cast<const char*>(aqfar::locate(row.st.pair*480+row.st.context)),_MM_HINT_T0);
}
static inline int value(const Row&r){return aqfar::predict(r.st,r.q);}
}
#include "stripe.inc"
#include "env_margin.inc"
#include "newring.inc"
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
    std::fprintf(stderr,"cpu_path %s\n",cascade?"cascade6226r6242r":"generic_sse2");
    aqfar::useCore512=cascade;
    initialize(); auto ti=std::clock(); aqfar::prepMaterial();aqfar::prepWide();aqfar::initFlat();aqfar::initDot();near40::initialize(aqfar::onSource,nullptr,true,cascade);
    std::fprintf(stderr,"near_and_early %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    for(unsigned src=24;src<208;src++)aqfar::materializeSource(src);
    aqfar::aq_joint_done();
    {const uintptr_t begin=(uintptr_t(aqBooks)+4095)&~uintptr_t(4095);
     const uintptr_t end=(uintptr_t(aqBooks)+1966080)&~uintptr_t(4095);
     if(end>begin)require(!munmap(reinterpret_cast<void*>(begin),end-begin),"release codebook");}
    aqfar::init();for(unsigned k=0;k<2;k++)for(unsigned j=0;j<8;j++)std::fprintf(stderr,"quant %u %u %u\n",k,j,aqfar::levels[k][j]); std::fprintf(stderr,"aq_init %.6f\n",double(std::clock()-ti)/CLOCKS_PER_SEC);
    std::fprintf(stderr,"contiguous %u\n",unsigned(aqfar::contiguous));r4::init();if(cascade)cascade857::init();
 aqfar::atlas855::init();stripe::openColumn();envcert::ready();
 stripe::ready(arch);newring::init();aqfar::tariff::init();
 FILE *fin=fopen(input,"rb"),*out=fopen(output,"wb");require(fin&&out,"open");
 require(setvbuf(fin,nullptr,_IONBF,0)==0&&setvbuf(out,nullptr,_IONBF,0)==0,"stdio mode");
 querying=true;if(cascade)cascade857::run(fin,out);else r4::run(fin,out);querying=false;require(allocations==0,"query heap allocation");fclose(fin);require(fclose(out)==0,"close");return 0;
}
