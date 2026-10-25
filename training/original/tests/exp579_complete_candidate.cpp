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

extern "C" const unsigned char exp579_geometry[];
extern "C" void* __real_malloc(size_t);
extern "C" void* __real_calloc(size_t, size_t);
extern "C" void* __real_realloc(void*, size_t);
static bool querying = false;
static uint64_t allocations = 0;
extern "C" void* __wrap_malloc(size_t n) {
    if (querying) ++allocations;
    return __real_malloc(n);
}
extern "C" void* __wrap_calloc(size_t n, size_t m) {
    if (querying) ++allocations;
    return __real_calloc(n, m);
}
extern "C" void* __wrap_realloc(void* p, size_t n) {
    if (querying) ++allocations;
    return __real_realloc(p, n);
}

static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "estimate: %s\n", why); std::exit(1); }
}

struct Part {
    const int16_t* left;
    const int16_t* right;
    unsigned rank, groups = 0;
    unsigned begin[192]{}, end[192]{}, shift[192]{};
    double scale;
};
static Part parts[2];
static const int16_t* center;
static delayest::Architecture arch;

static void initialize() {
    arch.loadEmbedded();
    require(arch.portCount() == kPortCount, "architecture identity");
    const auto* at = exp579_geometry + 64;
    center = reinterpret_cast<const int16_t*>(at);
    at += 59904 * 2;
    for (unsigned g = 0; g < 2; ++g) {
        auto& p = parts[g];
        p.rank = g == 0 ? 192 : 96;
        const unsigned count = g == 0 ? 4800 : 260160;
        const auto* le = reinterpret_cast<const int32_t*>(at);
        p.left = reinterpret_cast<const int16_t*>(le + p.rank);
        const auto* re = reinterpret_cast<const int32_t*>(p.left + 59904 * p.rank);
        p.right = reinterpret_cast<const int16_t*>(re + p.rank);
        at = reinterpret_cast<const unsigned char*>(p.right + uint64_t(count) * p.rank);
        const int minimum = le[0] + re[0];
        p.scale = std::ldexp(1., minimum);
        for (unsigned k = 0; k < p.rank;) {
            const int exponent = le[k] + re[k];
            require(exponent >= minimum && exponent - minimum <= 31, "scale group");
            const unsigned group = p.groups++;
            p.begin[group] = k; p.shift[group] = unsigned(exponent - minimum);
            do { ++k; } while (k < p.rank && le[k] + re[k] == exponent);
            p.end[group] = k;
            if (k < p.rank) require(le[k] + re[k] > exponent, "scale order");
        }
    }
    require(uint64_t(at - exp579_geometry) == kGeometryBytes, "geometry length");
}

static inline double geometry(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    const unsigned g = qx + qy > 3;
    const unsigned before = qx < 4 ? (qx + 1) * (8 - qx) / 2 : 10;
    const unsigned local = g == 0 ? context * 10 + qx * (9 - qx) / 2 + qy :
                                   context * 542 + qx * 46 + qy - before;
    const auto& p = parts[g];
    const auto* a = p.left + uint64_t(pair) * p.rank;
    const auto* b = p.right + uint64_t(local) * p.rank;
    int64_t total = 0;
    for (unsigned group = 0; group < p.groups; ++group) {
        __m128i lo = _mm_setzero_si128(), hi = _mm_setzero_si128();
        unsigned k = p.begin[group];
        for (; k + 8 <= p.end[group]; k += 8) {
            const __m128i av = _mm_loadu_si128(reinterpret_cast<const __m128i*>(a + k));
            const __m128i bv = _mm_loadu_si128(reinterpret_cast<const __m128i*>(b + k));
            const __m128i product = _mm_madd_epi16(av, bv);
            const __m128i sign = _mm_srai_epi32(product, 31);
            lo = _mm_add_epi64(lo, _mm_unpacklo_epi32(product, sign));
            hi = _mm_add_epi64(hi, _mm_unpackhi_epi32(product, sign));
        }
        alignas(16) int64_t lanes[2];
        _mm_store_si128(reinterpret_cast<__m128i*>(lanes), _mm_add_epi64(lo, hi));
        int64_t sum = lanes[0] + lanes[1];
        for (; k < p.end[group]; ++k) sum += int64_t(a[k]) * int64_t(b[k]);
        total += sum * (int64_t(1) << p.shift[group]);
    }
    return double(total) * p.scale;
}

static inline float residual(const float* x, unsigned route, unsigned fold) {
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

static inline int side(int x) { return x < 76 ? 0 : x < 90 ? 1 : 2; }
static inline int mod(int x, int base) { const int r = x % base; return r < 0 ? r + base : r; }
static inline int line(int x, int y, int tx, int ty) {
    return arch.lineDelayCrossing(delayest::Axis::Vertical, x, tx) +
           arch.lineDelayCrossing(delayest::Axis::Horizontal, y, ty);
}

struct Trace {
    float feature[53];
    double response;
    int32_t base, mandatory, prediction;
    float raw;
};

static inline int predict(const int32_t* q, unsigned fold, Trace* trace = nullptr) {
    const int sx=q[0], sy=q[1], tx=q[2], ty=q[3], sp=q[8], tp=q[9];
    if (sx == tx && sy == ty && sp == tp) return 0;
    const int source = kSourceIndex[sp], target = kTargetIndex[tp];
    if (source < 0 || target < 0 || !arch.exists(sx,sy) || !arch.exists(tx,ty)) return -1;
    int ax=sx, ay=sy, ndx=0, ndy=0, fee=0;
    const int net = arch.netOfOutput(sp);
    if (net >= 0) {
        const auto& n = arch.net(net);
        const auto a = arch.resolveNet(sx, sy, net);
        if (!a.valid) return -1;
        ax=a.x; ay=a.y; ndx=n.dx; ndy=n.dy;
        fee=a.delay-line(sx,sy,ax,ay);
    }
    const int x=tx-ax, y=ty-ay, dx=x+ndx, dy=y+ndy;
    const unsigned bx=unsigned(std::abs(dx)), by=unsigned(std::abs(dy));
    require(bx<=119 && by<=549, "nominal geometry domain");
    const unsigned qx=bx/10, qy=by/12, direction=2*(dx<0)+(dy<0);
    const unsigned pair=unsigned(source*288+target), context=(direction*10+bx%10)*12+by%12;
    const double response=geometry(pair,context,qx,qy);
    const double value=response*(128+125*qx+125*qy)+center[pair]+125*qx+(dy<0?125:127)*qy;
    int nominal=int(std::max(0.,value)+.5);
    if (dx==0 && dy==0 && sp==tp && net>=0) nominal=kCycles[source];
    const int base=nominal+fee, mandatory=line(sx,sy,ax,ay)+line(ax,ay,tx,ty);
    const int sf=q[4], sl=q[5], tf=q[6], tl=q[7];
    bool forced=false;
    for (const auto& b : arch.blocks())
        forced |= ((ax<b.left && tx>b.right) || (tx<b.left && ax>b.right)) &&
                   ay>=b.lower && ay<=b.upper && ty>=b.lower && ty<=b.upper;
    float f[53];
    const int feature[53]={sf,sl,tf,tl,sf>=20,tf>=20,ndx,ndy,x,y,std::abs(x),std::abs(y),x<0,y<0,
        mod(x,10),mod(y,12),std::abs(x)%10,std::abs(y)%12,std::abs(x)/10,std::abs(y)/12,
        sl^tl,sl-tl,125*(std::abs(x)/10)+(y<0?125:127)*(std::abs(y)/12),
        (sl&1)+2*(tl&1),((sl>>1)&1)+2*((tl>>1)&1),((sl>>2)&1)+2*((tl>>2)&1),
        sx,sy,ax,ay,tx,ty,119-sx,119-ax,119-tx,549-sy,549-ay,549-ty,
        side(sx),side(ax),side(tx),sy%100,ay%100,ty%100,sy%100<50,ay%100<50,ty%100<50,
        sy/100,ay/100,ty/100,fee,(tx-14*(ty%100<50 && tx>=90))-(ax-14*(ay%100<50 && ax>=90)),forced};
    for (unsigned j=0;j<53;++j) f[j]=float(feature[j]);
    const unsigned route=4*direction+2*(bx>=20)+(by>=24);
    const float raw=residual(f,route,fold);
    const int answer=int(std::max(0.,double(base)+double(raw))+.5)+mandatory;
    if (trace) {
        std::memcpy(trace->feature,f,sizeof(f)); trace->response=response;
        trace->base=base; trace->mandatory=mandatory; trace->prediction=answer; trace->raw=raw;
    }
    return answer;
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
    delayest::LineReader reader(input); require(reader.good(),"request open");
    FILE* out=std::fopen(output,"wb"); require(out,"output open");
    static char stdioBuffer[65536]; require(std::setvbuf(out,stdioBuffer,_IOFBF,sizeof(stdioBuffer))==0,"output buffer");
    delayest::BufferedWriter writer(out);
    std::string text; text.reserve(256);
    require(reader.next(text) && text=="From,To","input header");
    require(writer.write("From,To,delay\n",14),"output header");
    uint64_t rows=0, unreachable=0;
    querying=true;
    while (reader.next(text)) {
        const size_t comma=text.find(',');
        require(comma!=std::string::npos && text.find(',',comma+1)==std::string::npos,"two input fields");
        int32_t q[10]{};
        const auto from=delayest::trimView(std::string_view(text).substr(0,comma));
        const auto to=delayest::trimView(std::string_view(text).substr(comma+1));
        int answer=-1;
        if (arch.parsePin(from,q[0],q[1],q[8]) && arch.parsePin(to,q[2],q[3],q[9])) {
            const int s=kSourceIndex[q[8]], t=kTargetIndex[q[9]];
            if (s>=0 && t>=0) {
                q[4]=kSourceFamily[s]; q[5]=kSourceLane[s];
                q[6]=kTargetFamily[t]; q[7]=kTargetLane[t];
                answer=predict(q,0);
            }
        }
        unreachable+=answer<0;
        char number[24]; number[0]=',';
        const auto end=std::to_chars(number+1,number+sizeof(number)-1,answer);
        require(end.ec==std::errc{},"integer formatting"); *end.ptr='\n';
        require(writer.write(text.data(),text.size()) && writer.write(number,size_t(end.ptr-number)+1),"output write");
        ++rows;
    }
    require(writer.flush() && std::fflush(out)==0,"output flush");
    querying=false;
    require(std::fclose(out)==0,"output close");
    require(allocations==0,"query heap allocation");
    std::fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",
        (unsigned long long)rows,(unsigned long long)unreachable,(unsigned long long)allocations);
}
#endif
