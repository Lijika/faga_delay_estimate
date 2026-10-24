// Complete private candidate; generated assets include the five official JSONs.
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

#include "exp652_geometry_restore.h"
#include "exp596_csv_batch.h"
#define geometry dynamicGeometry595
#define prefetchGeometry581 dynamicPrefetch595
#include "exp582_int8_geometry.h"
#undef geometry
#undef prefetchGeometry581
#include "exp608_geometry.h"
#include "exp652_distance_curve_lookup.h"
extern delayest::Architecture arch;
#ifdef EXP580_PORT_PARSER
#include "exp601_port_parser.h"
#endif

static void initialize() {
    restoreGeometry652();
    arch.loadEmbedded();
#ifdef EXP580_PORT_PARSER
    initializePorts580();
#ifdef EXP580_VERIFY_PARSER
    verifyPorts580();
#endif
#endif

    require(arch.portCount() == kPortCount, "architecture identity");
    initializeGeometry582();
    initializePhaseCodes619();
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
#include "exp679_hv_events.h"

struct Trace {
    float feature[53];
    double response;
    int32_t base, mandatory, prediction;
    double raw;
};

struct Prepared596 {
    unsigned pair=0, context=0, qx=0, qy=0;
    int fee=0, mandatory=0, dy=0, cycle=0, answer=-1;
    double raw=0.;
    bool override_cycle=false, ready=false;
};

static inline void prepare596(const int32_t* q, unsigned fold, Prepared596& state, Trace* trace = nullptr) {
    const int sx=q[0], sy=q[1], tx=q[2], ty=q[3], sp=q[8], tp=q[9];
    if (sx == tx && sy == ty && sp == tp) { state.answer=0; return; }
    const int source = kSourceIndex[sp], target = kTargetIndex[tp];
    if (source < 0 || target < 0 || !arch.exists(sx,sy) || !arch.exists(tx,ty)) return;
    int ax=sx, ay=sy, ndx=0, ndy=0, fee=0;
    const int net = arch.netOfOutput(sp);
    if (net >= 0) {
        const auto& n = arch.net(net);
        const auto a = arch.resolveNet(sx, sy, net);
        if (!a.valid) return;
        ax=a.x; ay=a.y; ndx=n.dx; ndy=n.dy;
        fee=a.delay-line(sx,sy,ax,ay);
    }
    const int x=tx-ax, y=ty-ay, dx=x+ndx, dy=y+ndy;
    const unsigned bx=unsigned(std::abs(dx)), by=unsigned(std::abs(dy));
    require(bx<=119 && by<=549, "nominal geometry domain");
    const unsigned qx=bx/10, qy=by/12, direction=2*(dx<0)+(dy<0);
    const unsigned pair=unsigned(source*288+target), context=(direction*10+bx%10)*12+by%12;
    _mm_prefetch(reinterpret_cast<const char*>(center + pair), _MM_HINT_T0);
    prefetchGeometry581(pair,context,qx,qy);
    if (qx+qy>3) _mm_prefetch(reinterpret_cast<const char*>(phaseCodes619 +
        phaseByte619(pair,context)), _MM_HINT_T0);
    const int mandatory=line(sx,sy,ax,ay)+line(ax,ay,tx,ty);
    const int sf=q[4], sl=q[5], tf=q[6], tl=q[7];
    bool forced=false;
    for (const auto& b : arch.blocks())
        forced |= ((ax<b.left && tx>b.right) || (tx<b.left && ax>b.right)) &&
                   ay>=b.lower && ay<=b.upper && ty>=b.lower && ty<=b.upper;
    const int feature[53]={sf,sl,tf,tl,sf>=20,tf>=20,ndx,ndy,x,y,std::abs(x),std::abs(y),x<0,y<0,
        mod(x,10),mod(y,12),std::abs(x)%10,std::abs(y)%12,std::abs(x)/10,std::abs(y)/12,
        sl^tl,sl-tl,125*(std::abs(x)/10)+(y<0?125:127)*(std::abs(y)/12),
        (sl&1)+2*(tl&1),((sl>>1)&1)+2*((tl>>1)&1),((sl>>2)&1)+2*((tl>>2)&1),
        sx,sy,ax,ay,tx,ty,119-sx,119-ax,119-tx,549-sy,549-ay,549-ty,
        side(sx),side(ax),side(tx),sy%100,ay%100,ty%100,sy%100<50,ay%100<50,ty%100<50,
        sy/100,ay/100,ty/100,fee,(tx-14*(ty%100<50 && tx>=90))-(ax-14*(ay%100<50 && ax>=90)),forced};
    const unsigned route=4*direction+2*(bx>=20)+(by>=24);
#if defined(EXP581_INTEGER) || defined(EXP594_PACKED)
    int bands,ends;
    const unsigned event=event679(ax,ay,tx,ty,forced,bands,ends);
    const double raw=event ? replacement679(q,ax,ay,ndx,ndy,x,y,fee,forced,fold,event,bands,ends) :
        symmetric640(q,ax,ay,ndx,ndy,x,y,fee,forced,route,fold);
#else
    float f[53];
    for (unsigned j=0;j<53;++j) f[j]=float(feature[j]);
    const float raw=residual(f,route,fold);
#endif
    state.pair=pair; state.context=context; state.qx=qx; state.qy=qy;
    state.fee=fee; state.mandatory=mandatory; state.dy=dy; state.raw=raw;
    state.override_cycle=dx==0 && dy==0 && sp==tp && net>=0;
    state.cycle=kCycles[source]; state.ready=true;
    if (trace) for (unsigned j=0;j<53;++j) trace->feature[j]=float(feature[j]);
}

static inline int finish596(const Prepared596& state, Trace* trace = nullptr) {
    if (!state.ready) return state.answer;
    const unsigned pair=state.pair, context=state.context, qx=state.qx, qy=state.qy;
    const int fee=state.fee, mandatory=state.mandatory, dy=state.dy;
    const double raw=state.raw;
    const double response=geometry(pair,context,qx,qy);
    const double value=response*(128+125*qx+125*qy)+center[pair]+125*qx+(dy<0?125:127)*qy;
    int nominal=int(std::max(0.,value)+.5);
    if (state.override_cycle) nominal=state.cycle;
    const int base=nominal+fee+phaseCorrection619(pair,context,qx,qy);
    const int answer=int(std::max(0.,double(base)+double(raw))+.5)+mandatory;
    if (trace) {
        trace->response=response;
        trace->base=base; trace->mandatory=mandatory; trace->prediction=answer; trace->raw=raw;
    }
    return answer;
}

static inline int predict(const int32_t* q, unsigned fold, Trace* trace = nullptr) {
    Prepared596 state;
    prepare596(q,fold,state,trace);
    return finish596(state,trace);
}

#ifdef EXP579_AUDIT
int main(int argc, char** argv) {
    require(argc==5,"audit QUERIES FOLDS OUTPUT MODELS");
    initialize();
    FILE* input=std::fopen(argv[1],"rb"); FILE* folds=std::fopen(argv[2],"rb");
    FILE* output=std::fopen(argv[3],"wb");
    require(input && folds && output,"audit files");
    char magic[8]; uint32_t count;
    require(std::fread(magic,1,8,input)==8 && std::memcmp(magic,"EX535Q01",8)==0 &&
            std::fread(&count,4,1,input)==1 && count==1000000,"audit queries");
    const unsigned mode=unsigned(std::atoi(argv[4])); require(mode<=1,"audit mode");
    bool seen[59904]{};
    querying=true;
    for (unsigned i=0;i<count;++i) {
        int32_t q[10]; unsigned char fold; Trace trace{};
        require(std::fread(q,4,10,input)==10 && std::fread(&fold,1,1,folds)==1 && fold<3,"audit record");
        require(kSourceIndex[q[8]]>=0 && kTargetIndex[q[9]]>=0,"audit ports");
        seen[kSourceIndex[q[8]]*288+kTargetIndex[q[9]]]=true;
        predict(q,mode ? 0 : unsigned(fold)+1,&trace);
        require(std::fwrite(&trace,sizeof(trace),1,output)==1,"audit write");
    }
    querying=false;
    require(std::fgetc(input)==EOF && std::fgetc(folds)==EOF,"audit EOF");
    require(std::fclose(input)==0 && std::fclose(folds)==0 && std::fclose(output)==0,"audit close");
    for (bool value:seen) require(value,"audit full port coverage");
    // stdio buffers are included here; production sets fixed buffers before querying.
    std::printf("{\"rows\":%u,\"port_pairs\":59904,\"trace_bytes\":%zu,\"allocations\":%llu}\n",
        count,sizeof(Trace),(unsigned long long)allocations);
    return 0;
}
#else
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
    initialize();
    CsvViewReader591 reader(input); require(reader.good(),"request open");
    FILE* out=std::fopen(output,"wb"); require(out,"output open");
    static char stdioBuffer[65536]; require(std::setvbuf(out,stdioBuffer,_IOFBF,sizeof(stdioBuffer))==0,"output buffer");
#ifdef EXP594_WRITER
    RowWriter594 writer(out);
#else
    delayest::BufferedWriter writer(out);
#endif
    std::string_view text;
    require(reader.next(text) && text=="From,To","input header");
    require(writer.write("From,To,delay\n",14),"output header");
    uint64_t rows=0, unreachable=0;
    querying=true;
    std::string_view lines[EXP596_BATCH];
    for (;;) {
        const size_t count=reader.nextBatch(lines,EXP596_BATCH);
        if (!count) break;
        Prepared596 states[EXP596_BATCH];
        for (size_t i=0;i<count;++i) {
            const auto text=lines[i];
            const size_t comma=text.find(',');
            require(comma!=std::string::npos && text.find(',',comma+1)==std::string::npos,"two input fields");
            int32_t q[10]{};
            const auto from=delayest::trimView(std::string_view(text).substr(0,comma));
            const auto to=delayest::trimView(std::string_view(text).substr(comma+1));
    #ifdef EXP580_PORT_PARSER
            if (parsePin580(from,q[0],q[1],q[8]) && parsePin580(to,q[2],q[3],q[9])) {
    #else
            if (arch.parsePin(from,q[0],q[1],q[8]) && arch.parsePin(to,q[2],q[3],q[9])) {
    #endif
                const int s=kSourceIndex[q[8]], t=kTargetIndex[q[9]];
                if (s>=0 && t>=0) {
                    q[4]=kSourceFamily[s]; q[5]=kSourceLane[s];
                    q[6]=kTargetFamily[t]; q[7]=kTargetLane[t];
                    prepare596(q,0,states[i]);
                }
            }
            }
        for (size_t i=0;i<count;++i) {
            const int answer=finish596(states[i]);
            unreachable+=answer<0;
            require(writer.row(lines[i],answer), "output write");
        }
        rows+=count;
    }
    require(writer.flush() && std::fflush(out)==0,"output flush");
    querying=false;
    require(std::fclose(out)==0,"output close");
    require(allocations==0,"query heap allocation");
    std::fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",
        (unsigned long long)rows,(unsigned long long)unreachable,(unsigned long long)allocations);
    return 0;
}
#endif
