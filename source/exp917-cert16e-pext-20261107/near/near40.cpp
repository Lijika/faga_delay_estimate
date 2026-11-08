#include <unordered_map>
#include "near40.hpp"
#include <algorithm>
#include <array>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <cstring>
#include <immintrin.h>
#include <sys/mman.h>
#include <malloc.h>
#include "zstd.h"
namespace near40 {
static void require(bool ok,const char* msg){if(!ok){std::fprintf(stderr,"near40: %s\n",msg);std::abort();}}
constexpr int X=49,Y=95,R=67,S=113,W=2*R+1,T=W*(2*S+1);
struct Edge{int to,cost;};
struct Node{int x,y;std::vector<Edge> edges;};
struct Target{int direct;std::vector<Edge> pred;};
static Node nodes[160];static Target targets[288];static std::vector<Edge> roots[208];static int local[208][288];
static SourceReady callback;static void* cookie;static bool keep;static size_t keyOffset;
extern "C" const int16_t near40graph[],near40graphend[];
static void graph(){auto p=near40graph;auto get=[&](){require(p<near40graphend,"graph read");return int(*p++);};
 auto edges=[&](std::vector<Edge>& x){int count=get();require(count>=0,"graph degree");x.reserve(count);for(int i=0;i<count;i++){int a=get(),b=get();x.push_back({a,b});}};
 for(auto& node:nodes){node.x=get();node.y=get();edges(node.edges);}
 for(auto& t:targets){t.direct=get();edges(t.pred);}
 for(int s=0;s<208;s++){edges(roots[s]);std::fill_n(local[s],288,32767);int n=get();for(int i=0;i<n;i++){int t=get(),c=get();local[s][t]=c;}}
 require(p==near40graphend,"graph length");}
constexpr int GB=8;
namespace nearpack {
static_assert(sizeof(Line)==42);static Line*tab;
constexpr unsigned Keys=208*288*480;
static Extra* pages[4096];static uint64_t marker[Keys/64];static uint32_t base[Keys/64];static unsigned nex=0;
static inline unsigned stripe(unsigned pair,unsigned ctx){unsigned s=pair/288;return (((s/8)*288+pair%288)*480+ctx)*8+(s&7);}
static inline Extra& append(unsigned z){
 if((nex&16383)==0 && !pages[nex>>14]){require(nex<(4096u<<14),"plane slots");pages[nex>>14]=(Extra*)mmap(nullptr,16384*sizeof(Extra),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(pages[nex>>14]!=MAP_FAILED,"plane allocation");}
 if(!marker[z>>6]){base[z>>6]=nex;}marker[z>>6]|=uint64_t(1)<<(z&63);
 auto& out=pages[nex>>14][nex&16383];++nex;return out;
}
static uint8_t* joined[208];static bool crossed=false;
static inline const Line& lineAt(unsigned p){if(!crossed)return tab[p-keyOffset];unsigned src=p/KeysPerSource,idx=p-src*KeysPerSource;
 return *reinterpret_cast<const Line*>(joined[src]+size_t(idx)*64);}
static inline int get(int pair,int ctx,int x,int y){
 unsigned p=unsigned(pair)*480+ctx,j=x*8+y;const auto& row=lineAt(p);int v=int(row.low&32767)-8192+row.d[j];
 if(row.low&32768){unsigned z=stripe(pair,ctx)-keyOffset,next=base[z>>6]+__builtin_popcountll(marker[z>>6]&((uint64_t(1)<<(z&63))-1));auto e=pages[next>>14]+(next&16383);
   v+=int(((e->hi[0]>>j)&1)+2*((e->hi[1]>>j)&1)+4*((e->hi[2]>>j)&1))*256;}
 return v;
}
}

static double fillSec=0,waveSec=0,tapSec=0,rowSec=0;
static inline double now(){return double(std::clock())/CLOCKS_PER_SEC;}
template<typename Word> struct Buffer {
 Word* ptr;size_t n;
 explicit Buffer(size_t count):ptr((Word*)mmap(nullptr,count*sizeof(Word),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0)),n(count){require(ptr!=MAP_FAILED,"label map");(void)madvise(ptr,n*sizeof(Word),MADV_HUGEPAGE);}
 ~Buffer(){munmap(ptr,n*sizeof(Word));}
 Word* begin(){return ptr;}Word* end(){return ptr+n;}Word* data(){return ptr;}size_t size(){return n;}
};
static void packGroup(const uint16_t* lane,int source,int stride=8){
 double cput=now();
 constexpr int K=8, CT=(2*X+1)*(2*Y+1);
 Buffer<int16_t> tmp(size_t(CT)*288*GB);
 std::vector<int> ord2(288);for(int t=0;t<288;t++)ord2[t]=targets[t].direct;
 for(int y=-Y;y<=Y;++y)for(int x=-X;x<=X;++x){int tile=(y+S)*W+x+R,ct=(y+Y)*(2*X+1)+x+X;
  alignas(16) uint16_t arrived[160][8];for(int p=0;p<160;++p){auto &n=nodes[p];int before=tile-n.x-W*n.y;
   _mm_store_si128((__m128i*)arrived[p],_mm_loadu_si128((const __m128i*)(lane+(size_t(before)*160+p)*stride)));}
  for(int t=0;t<288;++t){__m128i result;
   if(ord2[t]>=0)result=_mm_loadu_si128((const __m128i*)(lane+(size_t(tile)*160+ord2[t])*stride));
   else {result=_mm_set1_epi16(32767);for(auto e:targets[t].pred){auto v=_mm_load_si128((const __m128i*)arrived[e.to]);result=_mm_min_epi16(result,_mm_adds_epi16(v,_mm_set1_epi16(e.cost)));}}
   if(!x&&!y){alignas(16) uint16_t z[8];for(int k=0;k<8;k++)z[k]=uint16_t(std::min(32767,local[source+k][t]));result=_mm_min_epi16(result,_mm_load_si128((__m128i*)z));}
   int trend=125*(abs(x)/10)+(y<0?125:127)*(abs(y)/12);
   _mm_storeu_si128((__m128i*)(tmp.data()+((size_t(t/K)*CT+ct)*K+(t%K))*GB),_mm_sub_epi16(result,_mm_set1_epi16(trend)));
  }
 }
 tapSec+=now()-cput;cput=now();
 for(int t=0;t<288;++t)for(int c=0;c<480;++c){int rx=c%120/12,ry=c%12,sx=c>=240?-1:1,sy=c/120%2?-1:1;
  alignas(16) int16_t raw[40][8];__m128i low=_mm_set1_epi16(32767),high=_mm_set1_epi16(-32767);
  for(int u=0;u<5;++u)for(int v=0;v<8;++v){int x=sx*(rx+10*u),y=sy*(ry+12*v);
    auto val=_mm_loadu_si128((const __m128i*)(tmp.data()+((size_t(t/K)*CT+(y+Y)*(2*X+1)+x+X)*K+(t%K))*GB));
    _mm_store_si128((__m128i*)raw[u*8+v],val);low=_mm_min_epi16(low,val);high=_mm_max_epi16(high,val);}
  alignas(16) int16_t starts[8],ends[8];_mm_store_si128((__m128i*)starts,low);_mm_store_si128((__m128i*)ends,high);
  for(int k=0;k<GB;k++){unsigned pair=(source+k)*288+t,id=pair*480+c;auto& line=nearpack::tab[id-keyOffset];int mn=starts[k],range=ends[k]-mn;
    require(mn>=-8192 && mn<24576 && range<2048,"plane extent");line.low=uint16_t(mn+8192)|(range>255?32768:0);
    for(int j=0;j<40;j++)line.d[j]=uint8_t(int(raw[j][k])-mn);
    if(range>255){auto& e=nearpack::append(nearpack::stripe(pair,c)-keyOffset);uint64_t a=0,b=0,d=0;
       for(int j=0;j<40;j++){unsigned hi=(int(raw[j][k])-mn)>>8;a|=uint64_t(hi&1)<<j;b|=uint64_t((hi>>1)&1)<<j;d|=uint64_t((hi>>2)&1)<<j;}e.hi[0]=a;e.hi[1]=b;e.hi[2]=d;}
  }
 }
 rowSec+=now()-cput;
}
// Source-major rows are consumed by the final quantizer; a context tile is enough to form 40 samples per row.
static unsigned tileEnd[13];
static bool tiled=false;
void useTiledRows(){tiled=true;}
NativeView nativeRows(unsigned source){require(tiled && !nearpack::crossed,"source row lifetime");return {nearpack::tab+size_t(source)*KeysPerSource,nearpack::pages};}
static inline void transposeRows(__m128i v[8]){
 __m128i a[8],b[8];
 for(int i=0;i<4;i++){a[2*i]=_mm_unpacklo_epi16(v[2*i],v[2*i+1]);a[2*i+1]=_mm_unpackhi_epi16(v[2*i],v[2*i+1]);}
 for(int i=0;i<2;i++)for(int j=0;j<2;j++){b[4*i+2*j]=_mm_unpacklo_epi32(a[4*i+j],a[4*i+2+j]);b[4*i+2*j+1]=_mm_unpackhi_epi32(a[4*i+j],a[4*i+2+j]);}
 for(int j=0;j<4;j++){v[2*j]=_mm_unpacklo_epi64(b[j],b[4+j]);v[2*j+1]=_mm_unpackhi_epi64(b[j],b[4+j]);}
}
static inline void encodeEight(const int16_t cell[40][16],int lane,unsigned source,int target,int context){
 alignas(16) int16_t columns[8][40],lo[8],hi[8];
 __m128i low=_mm_set1_epi16(32767),high=_mm_set1_epi16(-32767);
 for(int g=0;g<5;g++){
  __m128i x[8];
  for(int j=0;j<8;j++){x[j]=_mm_load_si128(reinterpret_cast<const __m128i*>(cell[8*g+j]+lane));low=_mm_min_epi16(low,x[j]);high=_mm_max_epi16(high,x[j]);}
  transposeRows(x);
  for(int k=0;k<8;k++)_mm_store_si128(reinterpret_cast<__m128i*>(columns[k]+g*8),x[k]);
 }
 _mm_store_si128(reinterpret_cast<__m128i*>(lo),low);_mm_store_si128(reinterpret_cast<__m128i*>(hi),high);
 for(int k=0;k<8;k++){
  const int base=lo[k],range=hi[k]-base;
  require(base>=-8192&&base<24576&&range<2048,"context plane extent");
  auto& line=nearpack::tab[(source+lane+k)*KeysPerSource+target*480+context];
  line.low=uint16_t(base+8192)|(range>255?32768:0);
  alignas(16) uint16_t delta[40];const auto center=_mm_set1_epi16(lo[k]);
  for(int j=0;j<40;j+=8){
    auto d=_mm_sub_epi16(_mm_load_si128(reinterpret_cast<const __m128i*>(columns[k]+j)),center);
    auto b=_mm_and_si128(d,_mm_set1_epi16(255));
    _mm_storel_epi64(reinterpret_cast<__m128i*>(line.d+j),_mm_packus_epi16(b,b));
    _mm_store_si128(reinterpret_cast<__m128i*>(delta+j),d);
  }
  if(range>255){
    unsigned id=nearpack::nex++;
    require(id<(4096u<<14),"overflow pages");auto &page=nearpack::pages[id>>14];if(!(id&16383)){
      page=static_cast<nearpack::Extra*>(mmap(nullptr,16384*sizeof(*page),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));require(page!=MAP_FAILED,"overflow page");
    }
    auto* extra=reinterpret_cast<uint8_t*>(&page[id&16383]);
    memcpy(extra+20,line.d+36,4);memcpy(line.d+36,&id,4);
    for(int j=0;j<40;j+=2)extra[j/2]=uint8_t((delta[j]>>8)|((delta[j+1]>>8)<<4));
  }
 }
}
// One shared context tile for both packet widths. This is dead before the query phase.
alignas(64) static int16_t contextTile[8][288][40][16];
template<unsigned Stride=16> static void packContext(const uint16_t* lane,unsigned source){
 alignas(16) int16_t arrived[160][16];
 int before[160],direct[288];for(int p=0;p<160;p++)before[p]=-(nodes[p].x+W*nodes[p].y)*160+p;
 for(int t=0;t<288;t++)direct[t]=targets[t].direct;
 auto timer=now();
 for(int c0=0;c0<480;c0+=8){for(int cc=0;cc<8;cc++){const int c=c0+cc;
   const int rx=c%120/12,ry=c%12,sx=c>=240?-1:1,sy=(c/120)%2?-1:1;
   for(int u=0;u<5;u++)for(int v=0;v<8;v++){
     const int x=sx*(rx+10*u),y=sy*(ry+12*v),j=8*u+v;
     const auto* tile=lane+size_t((y+S)*W+x+R)*160*Stride;
     auto trend=_mm_set1_epi16(short(125*u+(y<0?125:127)*v));
     for(int p=0;p<160;p++)std::memcpy(arrived[p],tile+ptrdiff_t(before[p])*Stride,32);
     for(int t=0;t<288;t++){__m128i a,b;
       if(direct[t]>=0){auto loc=tile+direct[t]*Stride;a=_mm_load_si128(reinterpret_cast<const __m128i*>(loc));b=_mm_load_si128(reinterpret_cast<const __m128i*>(loc+8));}
       else{a=b=_mm_set1_epi16(32767);for(const auto e:targets[t].pred){
         const auto* q=reinterpret_cast<const __m128i*>(arrived[e.to]);auto z=_mm_set1_epi16(short(e.cost));
         a=_mm_min_epi16(a,_mm_adds_epi16(_mm_load_si128(q),z));b=_mm_min_epi16(b,_mm_adds_epi16(_mm_load_si128(q+1),z));
       }}
       if(x==0&&y==0){alignas(16) uint16_t cap[16];for(int k=0;k<16;k++)cap[k]=uint16_t(std::min(32767,local[source+k][t]));
         a=_mm_min_epi16(a,_mm_load_si128(reinterpret_cast<const __m128i*>(cap)));b=_mm_min_epi16(b,_mm_load_si128(reinterpret_cast<const __m128i*>(cap+8)));}
       auto dest=reinterpret_cast<__m128i*>(contextTile[cc][t][j]);_mm_store_si128(dest,_mm_sub_epi16(a,trend));_mm_store_si128(dest+1,_mm_sub_epi16(b,trend));
     }
   }
   }
   for(int t=0;t<288;t++)for(int cc=0;cc<8;cc++){
     encodeEight(contextTile[cc][t],0,source,t,c0+cc);
     encodeEight(contextTile[cc][t],8,source,t,c0+cc);
   }
 }
 rowSec+=now()-timer;tileEnd[source/16]=nearpack::nex;
}

static void pack16(const uint16_t* lane,int source,int stride){
 double cput=now();
 constexpr int K=8, CT=(2*X+1)*(2*Y+1);
 Buffer<int16_t> tmp(size_t(CT)*288*GB*2);
 std::vector<int> ord2(288);for(int t=0;t<288;t++)ord2[t]=targets[t].direct;
 for(int y=-Y;y<=Y;++y)for(int x=-X;x<=X;++x){int tile=(y+S)*W+x+R,ct=(y+Y)*(2*X+1)+x+X;
  alignas(16) uint16_t arrived[160][16];for(int p=0;p<160;++p){auto &n=nodes[p];int before=tile-n.x-W*n.y;
   auto input=lane+(size_t(before)*160+p)*stride;
   _mm_store_si128((__m128i*)arrived[p],_mm_loadu_si128((const __m128i*)input));
   _mm_store_si128((__m128i*)(arrived[p]+8),_mm_loadu_si128((const __m128i*)(input+8)));}
  for(int t=0;t<288;++t){__m128i lo,hi;
   if(ord2[t]>=0){auto input=lane+(size_t(tile)*160+ord2[t])*stride;
    lo=_mm_loadu_si128((const __m128i*)input);hi=_mm_loadu_si128((const __m128i*)(input+8));}
   else {lo=hi=_mm_set1_epi16(32767);for(auto e:targets[t].pred){auto cost=_mm_set1_epi16(e.cost);
    lo=_mm_min_epi16(lo,_mm_adds_epi16(_mm_load_si128((const __m128i*)arrived[e.to]),cost));
    hi=_mm_min_epi16(hi,_mm_adds_epi16(_mm_load_si128((const __m128i*)(arrived[e.to]+8)),cost));}}
   if(!x&&!y){alignas(16) uint16_t z[16];for(int k=0;k<16;k++)z[k]=uint16_t(std::min(32767,local[source+k][t]));
    lo=_mm_min_epi16(lo,_mm_load_si128((const __m128i*)z));hi=_mm_min_epi16(hi,_mm_load_si128((const __m128i*)(z+8)));}
   int trend=125*(abs(x)/10)+(y<0?125:127)*(abs(y)/12);
   auto output=tmp.data()+((size_t(t/K)*CT+ct)*K+(t%K))*GB;
   auto trendv=_mm_set1_epi16(trend);
   _mm_storeu_si128((__m128i*)output,_mm_sub_epi16(lo,trendv));_mm_storeu_si128((__m128i*)(output+size_t(CT)*288*GB),_mm_sub_epi16(hi,trendv));
  }
 }
 tapSec+=now()-cput;cput=now();for(unsigned group=0;group<2;++group,source+=8){const auto tmpBase=tmp.data()+size_t(group)*CT*288*GB;
 for(int t=0;t<288;++t)for(int c=0;c<480;++c){int rx=c%120/12,ry=c%12,sx=c>=240?-1:1,sy=c/120%2?-1:1;
  alignas(16) int16_t raw[40][8];__m128i low=_mm_set1_epi16(32767),high=_mm_set1_epi16(-32767);
  for(int u=0;u<5;++u)for(int v=0;v<8;++v){int x=sx*(rx+10*u),y=sy*(ry+12*v);
    auto val=_mm_loadu_si128((const __m128i*)(tmpBase+((size_t(t/K)*CT+(y+Y)*(2*X+1)+x+X)*K+(t%K))*GB));
    _mm_store_si128((__m128i*)raw[u*8+v],val);low=_mm_min_epi16(low,val);high=_mm_max_epi16(high,val);}
  alignas(16) int16_t starts[8],ends[8];_mm_store_si128((__m128i*)starts,low);_mm_store_si128((__m128i*)ends,high);
  for(int k=0;k<GB;k++){unsigned pair=(source+k)*288+t,id=pair*480+c;auto& line=nearpack::tab[id-keyOffset];int mn=starts[k],range=ends[k]-mn;
    require(mn>=-8192 && mn<24576 && range<2048,"plane extent");line.low=uint16_t(mn+8192)|(range>255?32768:0);
    for(int j=0;j<40;j++)line.d[j]=uint8_t(int(raw[j][k])-mn);
    if(range>255){auto& e=nearpack::append(nearpack::stripe(pair,c)-keyOffset);uint64_t a=0,b=0,d=0;
       for(int j=0;j<40;j++){unsigned hi=(int(raw[j][k])-mn)>>8;a|=uint64_t(hi&1)<<j;b|=uint64_t((hi>>1)&1)<<j;d|=uint64_t((hi>>2)&1)<<j;}e.hi[0]=a;e.hi[1]=b;e.hi[2]=d;}
  }
 }
 }rowSec+=now()-cput;
}
__attribute__((target("avx2"))) static void pack16AVX2(const uint16_t* lane,int source,int stride){
 double cput=now();
 constexpr int K=8, CT=(2*X+1)*(2*Y+1);
 Buffer<int16_t> tmp(size_t(CT)*288*GB*2);
 std::vector<int> ord2(288);for(int t=0;t<288;t++)ord2[t]=targets[t].direct;
 for(int y=-Y;y<=Y;++y)for(int x=-X;x<=X;++x){int tile=(y+S)*W+x+R,ct=(y+Y)*(2*X+1)+x+X;
  alignas(32) uint16_t arrived[160][16];for(int p=0;p<160;++p){auto &n=nodes[p];int before=tile-n.x-W*n.y;
   _mm256_store_si256((__m256i*)arrived[p],_mm256_loadu_si256((const __m256i*)(lane+(size_t(before)*160+p)*stride)));}
  for(int t=0;t<288;++t){__m256i result;
   if(ord2[t]>=0)result=_mm256_loadu_si256((const __m256i*)(lane+(size_t(tile)*160+ord2[t])*stride));
   else {result=_mm256_set1_epi16(32767);for(auto e:targets[t].pred){auto v=_mm256_load_si256((const __m256i*)arrived[e.to]);result=_mm256_min_epi16(result,_mm256_adds_epi16(v,_mm256_set1_epi16(e.cost)));}}
   if(!x&&!y){alignas(32) uint16_t z[16];for(int k=0;k<16;k++)z[k]=uint16_t(std::min(32767,local[source+k][t]));result=_mm256_min_epi16(result,_mm256_load_si256((__m256i*)z));}
   int trend=125*(abs(x)/10)+(y<0?125:127)*(abs(y)/12);
   auto output=tmp.data()+((size_t(t/K)*CT+ct)*K+(t%K))*GB;
   auto delta=_mm256_sub_epi16(result,_mm256_set1_epi16(trend));
   _mm_storeu_si128((__m128i*)output,_mm256_castsi256_si128(delta));_mm_storeu_si128((__m128i*)(output+size_t(CT)*288*GB),_mm256_extracti128_si256(delta,1));
  }
 }
 tapSec+=now()-cput;cput=now();for(unsigned group=0;group<2;++group,source+=8){const auto tmpBase=tmp.data()+size_t(group)*CT*288*GB;
 for(int t=0;t<288;++t)for(int c=0;c<480;++c){int rx=c%120/12,ry=c%12,sx=c>=240?-1:1,sy=c/120%2?-1:1;
  alignas(16) int16_t raw[40][8];__m128i low=_mm_set1_epi16(32767),high=_mm_set1_epi16(-32767);
  for(int u=0;u<5;++u)for(int v=0;v<8;++v){int x=sx*(rx+10*u),y=sy*(ry+12*v);
    auto val=_mm_loadu_si128((const __m128i*)(tmpBase+((size_t(t/K)*CT+(y+Y)*(2*X+1)+x+X)*K+(t%K))*GB));
    _mm_store_si128((__m128i*)raw[u*8+v],val);low=_mm_min_epi16(low,val);high=_mm_max_epi16(high,val);}
  alignas(16) int16_t starts[8],ends[8];_mm_store_si128((__m128i*)starts,low);_mm_store_si128((__m128i*)ends,high);
  for(int k=0;k<GB;k++){unsigned pair=(source+k)*288+t,id=pair*480+c;auto& line=nearpack::tab[id-keyOffset];int mn=starts[k],range=ends[k]-mn;
    require(mn>=-8192 && mn<24576 && range<2048,"plane extent");line.low=uint16_t(mn+8192)|(range>255?32768:0);
    for(int j=0;j<40;j++)line.d[j]=uint8_t(int(raw[j][k])-mn);
    if(range>255){auto& e=nearpack::append(nearpack::stripe(pair,c)-keyOffset);uint64_t a=0,b=0,d=0;
       for(int j=0;j<40;j++){unsigned hi=(int(raw[j][k])-mn)>>8;a|=uint64_t(hi&1)<<j;b|=uint64_t((hi>>1)&1)<<j;d|=uint64_t((hi>>2)&1)<<j;}e.hi[0]=a;e.hi[1]=b;e.hi[2]=d;}
  }
 }
 }rowSec+=now()-cput;
}
extern "C" const uint8_t zsupport[], zsupportEnd[];

struct Op{unsigned v,mask;};
static std::vector<int> arc;
static void compileDict(std::vector<Op>& ops){
 std::unordered_map<unsigned,unsigned> index[160];std::vector<int> arcs;
 for(auto& o:ops){unsigned v=o.v,p=v%160;
  auto result=index[p].emplace(o.mask,0);
  unsigned& descriptor=result.first->second;
  if(result.second){require(arcs.size()<(1u<<27),"arc array");
    descriptor=unsigned(arcs.size()<<5)+__builtin_popcount(o.mask);
    for(unsigned m=o.mask;m;m&=m-1){auto e=nodes[p].edges[__builtin_ctz(m)];int delta=160*(nodes[p].x+W*nodes[p].y)+e.to-int(p);
      require(delta>=-(1<<23)&&delta<(1<<23)&&unsigned(e.cost)<256,"arc extent");arcs.push_back(int((unsigned(delta)<<8)+e.cost));}
  }
  o.mask=descriptor;
 }
 arc=std::move(arcs);size_t n=0;for(auto& idx:index)n+=idx.size();
 std::fprintf(stderr,"instructions %zu descriptors %zu arcs %zu\n", ops.size(),n,arc.size());
}
template<unsigned L> static void packetWave(const std::vector<Op>& ops,unsigned origin,unsigned first,unsigned last){
 Buffer<uint16_t> labels(size_t(T)*160*L);
 for(unsigned s=first;s<last;s+=L){double timer=now();std::fill(labels.begin(),labels.end(),uint16_t(32767));
   for(unsigned k=0;k<L;k++)for(auto e:roots[s+k]){auto x=labels.data()+size_t(origin+e.to)*L+k;*x=std::min(*x,uint16_t(e.cost));}
   fillSec+=now()-timer;timer=now();
   for(size_t i=0;i<ops.size();i++){
     if(i+12<ops.size()){
       const auto n=ops[i+12];
       __builtin_prefetch(labels.data()+size_t(n.v)*L,0,2);
       __builtin_prefetch(arc.data()+(n.mask>>5),0,2);
     }
     if(i+4<ops.size()){
       const auto n=ops[i+4];const auto* edges=arc.data()+(n.mask>>5);
       const auto* base=labels.data()+size_t(n.v)*L;
       for(unsigned j=0;j<(n.mask&31);j++)
         __builtin_prefetch(base+ptrdiff_t(edges[j]>>8)*L,1,2);
     }
     const auto op=ops[i];
     auto ptr=labels.data()+size_t(op.v)*L;__m128i value[L/8];
     for(unsigned k=0;k<L/8;k++)value[k]=_mm_load_si128(reinterpret_cast<const __m128i*>(ptr)+k);
     auto ar=arc.data()+(op.mask>>5);unsigned deg=op.mask&31;
     for(unsigned j=0;j<deg;j++){int a=ar[j];auto to=(__m128i*)(ptr+ptrdiff_t(a>>8)*L);auto cost=_mm_set1_epi16(a&255);
       for(unsigned k=0;k<L/8;k++)_mm_store_si128(to+k,_mm_min_epi16(_mm_load_si128(to+k),_mm_adds_epi16(value[k],cost)));}

   }
   waveSec+=now()-timer;
   for(unsigned offset=0;offset<L;offset+=16){
     packContext<L>(labels.ptr+offset,s+offset);
     if(callback)for(unsigned k=0;k<16;k++)callback(s+offset+k,cookie);
   }
 }
}
static void wave16(std::vector<Op>& ops,unsigned origin) {
 constexpr unsigned L=16,V=T*160;static_assert(L==2*GB && GB==8 && 208%L==0);
 compileDict(ops);if(tiled){packetWave<32>(ops,origin,0,192);packetWave<16>(ops,origin,192,208);return;}
 Buffer<uint16_t> labels(size_t(V)*L);
 for(unsigned s=0;s<208;s+=L){double timer=now();std::fill(labels.begin(),labels.end(),uint16_t(32767));
   for(unsigned k=0;k<L;k++)for(auto e:roots[s+k]){auto x=labels.data()+size_t(origin+e.to)*L+k;*x=std::min(*x,uint16_t(e.cost));}
   fillSec+=now()-timer;timer=now();
   for(size_t i=0;i<ops.size();i++){
     if(i+12<ops.size()){
       const auto n=ops[i+12];
       __builtin_prefetch(labels.data()+size_t(n.v)*L,0,2);
       __builtin_prefetch(arc.data()+(n.mask>>5),0,2);
     }
     if(i+4<ops.size()){
       const auto n=ops[i+4];const auto* edges=arc.data()+(n.mask>>5);
       const auto* base=labels.data()+size_t(n.v)*L;
       for(unsigned j=0;j<(n.mask&31);j++)
         __builtin_prefetch(base+ptrdiff_t(edges[j]>>8)*L,1,2);
     }
     const auto op=ops[i];
     auto ptr=labels.data()+size_t(op.v)*L;auto lo=_mm_loadu_si128((const __m128i*)ptr),hi=_mm_loadu_si128((const __m128i*)(ptr+8));
     auto ar=arc.data()+(op.mask>>5);unsigned deg=op.mask&31;
     for(unsigned j=0;j<deg;j++){int a=ar[j];auto to=(__m128i*)(ptr+ptrdiff_t(a>>8)*L);auto cost=_mm_set1_epi16(a&255);
       _mm_storeu_si128(to,_mm_min_epi16(_mm_loadu_si128(to),_mm_adds_epi16(lo,cost)));
       _mm_storeu_si128(to+1,_mm_min_epi16(_mm_loadu_si128(to+1),_mm_adds_epi16(hi,cost)));}
   }
   waveSec+=now()-timer;
   if(tiled)packContext(labels.data(),s);else pack16(labels.data(),s,L);if(callback)for(unsigned k=0;k<L;k++)callback(s+k,cookie);
 }
}
__attribute__((target("avx2"))) static void wave16AVX2(std::vector<Op>& ops,unsigned origin) {
 constexpr unsigned L=16,V=T*160;static_assert(L==2*GB && GB==8 && 208%L==0);
 compileDict(ops);Buffer<uint16_t> labels(size_t(V)*L);
 for(unsigned s=0;s<208;s+=L){double timer=now();std::fill(labels.begin(),labels.end(),uint16_t(32767));
   for(unsigned k=0;k<L;k++)for(auto e:roots[s+k]){auto x=labels.data()+size_t(origin+e.to)*L+k;*x=std::min(*x,uint16_t(e.cost));}
   fillSec+=now()-timer;timer=now();
   for(auto op:ops){
     auto ptr=labels.data()+size_t(op.v)*L;auto from=_mm256_loadu_si256((const __m256i*)ptr);auto ar=arc.data()+(op.mask>>5);unsigned deg=op.mask&31;
     for(unsigned j=0;j<deg;j++){int a=ar[j];auto to=(__m256i*)(ptr+ptrdiff_t(a>>8)*L);
       auto next=_mm256_min_epi16(_mm256_loadu_si256(to),_mm256_adds_epi16(from,_mm256_set1_epi16(a&255)));_mm256_storeu_si256(to,next);}
   }
   waveSec+=now()-timer;
   if(tiled)packContext(labels.data(),s);else pack16AVX2(labels.data(),s,L);if(callback)for(unsigned k=0;k<L;k++)callback(s+k,cookie);
 }
}

static void waveAll(bool use_avx2){
 static_assert(GB==8||GB==4);
 const unsigned V=T*160;std::vector<uint32_t> support(V);constexpr unsigned BS=4,BX=34,BY=57;std::vector<uint32_t> coarse(size_t(BX)*BY*160);
 require(ZSTD_decompress(coarse.data(),coarse.size()*4,zsupport,115939)==coarse.size()*4,"coarse support");
 for(int y=0;y<=2*S;y++)for(int x=0;x<=2*R;x++)for(unsigned p=0;p<160;p++){int xx=x+nodes[p].x,yy=y+nodes[p].y;support[(y*W+x)*160+p]=(unsigned(xx)<W && unsigned(yy)<2*S+1)?coarse[((y/BS)*BX+x/BS)*160+p]:0;}
 std::vector<uint32_t>().swap(coarse);
 std::vector<unsigned> order;order.reserve(V);std::vector<uint16_t> rk(V,32767);std::vector<unsigned> bk[512];unsigned origin=(S*W+R)*160;for(unsigned i=0;i<160;++i){rk[origin+i]=0;bk[0].push_back(origin+i);}
 auto dest=[&](unsigned tile,unsigned p){return (int(tile)+nodes[p].x+W*nodes[p].y)*160;};
 size_t pend=160;for(unsigned c=0;pend;++c){auto& q=bk[c&511];for(unsigned v:q){--pend;if(rk[v]!=c)continue;order.push_back(v);unsigned p=v%160;int base=dest(v/160,p);for(unsigned m=support[v];m;m&=m-1){auto e=nodes[p].edges[__builtin_ctz(m)];unsigned z=base+e.to,nd=c+e.cost;if(nd<rk[z]){rk[z]=nd;bk[nd&511].push_back(z);++pend;}}}q.clear();}
 std::vector<uint16_t>().swap(rk); for(auto& b:bk){std::vector<unsigned>().swap(b);}
 
 std::vector<Op> program;
 const uint8_t* desc=zsupport+115939;unsigned nstage;std::memcpy(&nstage,desc,4);desc+=4;auto ptr=desc+nstage*8;
 std::vector<std::vector<Op>> parts(nstage);size_t count=0;
 for(unsigned st=0;st<nstage;++st){unsigned block,bytes;std::memcpy(&block,desc+8*st,4);std::memcpy(&bytes,desc+8*st+4,4);
   unsigned nx=(W+block-1)/block,ny=(2*S+1+block-1)/block;std::vector<unsigned> sub(size_t(nx)*ny*160);
   require(ptr+bytes<=zsupportEnd&&ZSTD_decompress(sub.data(),sub.size()*4,ptr,bytes)==sub.size()*4,"coarse stage");ptr+=bytes;
   size_t edges=0;for(unsigned v:order){unsigned p=v%160,t=v/160;unsigned m=support[v]&sub[(((t/W)/block)*nx+(t%W)/block)*160+p];if(m){parts[st].push_back({v,m});edges+=__builtin_popcount(m);}}
   count+=parts[st].size();
 }
 require(zsupportEnd-ptr==516421,"witness extent");program.reserve(count);for(auto& part:parts){program.insert(program.end(),part.begin(),part.end());std::vector<Op>().swap(part);}
 std::vector<unsigned>().swap(order);std::vector<unsigned>().swap(support);
 if(tiled){
  require(program.size()==7020712,"frozen wave schedule");std::vector<uint8_t> live((program.size()+7)/8);
  require(ZSTD_decompress(live.data(),live.size(),ptr,zsupportEnd-ptr)==live.size(),"witness bits");
  size_t end=0;for(size_t i=0;i<program.size();i++)if(live[i>>3]&(1u<<(i&7)))program[end++]=program[i];
  program.resize(end);
 }
 if(keep){if(use_avx2)wave16AVX2(program,origin);else wave16(program,origin);std::fprintf(stderr,"fill %.5f relax %.5f taps %.5f rows %.5f\n",fillSec,waveSec,tapSec,rowSec);return;}
 std::vector<uint16_t> lane(size_t(V)*GB);
 for(int src=0;src<208;src+=GB){if(!keep){keyOffset=size_t(src)*KeysPerSource;std::fill_n(nearpack::marker,GB*KeysPerSource/64,uint64_t(0));nearpack::nex=0;}
 std::fill(lane.begin(),lane.end(),uint16_t(32767));
   for(int k=0;k<GB;k++)for(auto e:roots[src+k]){auto v=origin+e.to;lane[size_t(v)*GB+k]=std::min(lane[size_t(v)*GB+k],uint16_t(e.cost));}
   for(auto op:program){unsigned v=op.v,p=v%160;int base=dest(v/160,p);auto from=_mm_loadu_si128((const __m128i*)(lane.data()+size_t(v)*GB));
     for(unsigned m=op.mask;m;m&=m-1){auto e=nodes[p].edges[__builtin_ctz(m)];auto to=(__m128i*)(lane.data()+(size_t(base)+e.to)*GB);
       auto val=_mm_min_epi16(_mm_loadu_si128(to),_mm_adds_epi16(from,_mm_set1_epi16(e.cost)));_mm_storeu_si128(to,val);}}
   packGroup(lane.data(),src);if(callback)for(unsigned k=0;k<GB;k++)callback(src+k,cookie);
 }
}


static void freePage(nearpack::Extra*& p){if(p){require(!munmap(p,16384*sizeof(nearpack::Extra)),"release plane page");p=nullptr;}}
static void freeTables(){for(auto& p:nearpack::pages)freePage(p);}
void releaseMaterialized(unsigned src){
 if(tiled){static unsigned first=0;if((src&15u)!=15u)return;
   const unsigned end=(tileEnd[src/16]+(src==207?16383:0))>>14;for(;first<end;first++)freePage(nearpack::pages[first]);return;}
 if((src&7u)!=7u)return;
 // A page shared with the next eight-source stripe stays live until that stripe is consumed.
 unsigned block=(src+1)*KeysPerSource/64;
 while(block && !nearpack::marker[block-1])--block;
 const unsigned used=block?nearpack::base[block-1]+__builtin_popcountll(nearpack::marker[block-1]):0;
 const unsigned end=src==207?(nearpack::nex+16383)>>14:used>>14;
 static unsigned released=0;
 for(;released<end;++released)freePage(nearpack::pages[released]);
}
void initialize(SourceReady on_source,void* user,bool retain,bool use_avx2){
 static bool started=false;require(!started,"initialize called twice");require(retain||on_source,"streaming needs a consumer");started=true;
 callback=on_source;cookie=user;keep=retain;graph();size_t n=(retain?208u:GB)*size_t(KeysPerSource)*sizeof(nearpack::Line);
 nearpack::tab=(nearpack::Line*)mmap(nullptr,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(nearpack::tab!=MAP_FAILED,"main table");
 (void)madvise(nearpack::tab,n,MADV_HUGEPAGE);waveAll(use_avx2);
 std::vector<int>().swap(arc);
 (void)malloc_trim(0); // Return freed wave-construction storage before final rows grow.
 if(!retain){require(!munmap(nearpack::tab,n),"unmap main table");nearpack::tab=nullptr;freeTables();}
}
int raw(unsigned key,unsigned j) noexcept {if(tiled){int16_t a[40];load40(key,a);return a[j];}return nearpack::get(key/480,key%480,j/8,j%8);}
void load40(uint32_t key,int16_t v[40]) noexcept{
 const auto& r=nearpack::lineAt(key);int center=int(r.low&32767)-8192;
 if(!(r.low&32768)){for(unsigned j=0;j<40;j++)v[j]=int16_t(center+r.d[j]);return;}
 if(tiled){unsigned id;std::memcpy(&id,r.d+36,4);const uint8_t* extra=reinterpret_cast<const uint8_t*>(nearpack::pages[id>>14]+(id&16383));
   for(unsigned j=0;j<40;j++){unsigned low=j<36?r.d[j]:extra[20+j-36];v[j]=int16_t(center+low+256*((extra[j/2]>>(4*(j&1)))&15));}return;}
 unsigned z=nearpack::stripe(key/480,key%480)-keyOffset,n=nearpack::base[z>>6]+__builtin_popcountll(nearpack::marker[z>>6]&((uint64_t(1)<<(z&63))-1));
 auto p=nearpack::pages[n>>14]+(n&16383);for(unsigned j=0;j<40;j++)v[j]=int16_t(center+r.d[j]+256*(((p->hi[0]>>j)&1)+2*((p->hi[1]>>j)&1)+4*((p->hi[2]>>j)&1)));
}
}

extern "C" const unsigned char* aq_old42(){return reinterpret_cast<const unsigned char*>(near40::nearpack::tab);}
extern "C" void aq_migrate(unsigned src,unsigned char* slab){
 using namespace near40;nearpack::joined[src]=slab;
 if(src&1u){constexpr size_t two=2ul*KeysPerSource*sizeof(nearpack::Line);static_assert(two%4096==0);
  require(!munmap(nearpack::tab+size_t(src-1)*KeysPerSource,two),"joint migration");}}
extern "C" void aq_joint_done(){near40::nearpack::crossed=true;}
