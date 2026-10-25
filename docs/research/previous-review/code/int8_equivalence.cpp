// Correctness probe, not a production worker and not a performance benchmark.
// g++ -std=c++17 -O2 -march=x86-64 -fno-fast-math -ffp-contract=off int8_equivalence.cpp -o int8_equivalence
#include <immintrin.h>
#include <algorithm>
#include <cstdlib>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
#include <stdexcept>
#include <vector>
#include <string>
#include <limits>
#include <cmath>
using Fn = int(*)(const int8_t*,const int8_t*,int);
__attribute__((noinline)) int reference(const int8_t*a,const int8_t*b,int) {
  int r=0; for(int i=0;i<64;i++) r+=int(a[i])*int(b[i]); return r;
}
__attribute__((target("sse2"),noinline)) int sse2(const int8_t*a,const int8_t*b,int) {
  __m128i acc=_mm_setzero_si128(),z=_mm_setzero_si128();
  for(int i=0;i<64;i+=16){
    auto x=_mm_loadu_si128((const __m128i*)(a+i));
    auto y=_mm_loadu_si128((const __m128i*)(b+i));
    auto xs=_mm_cmpgt_epi8(z,x),ys=_mm_cmpgt_epi8(z,y);
    acc=_mm_add_epi32(acc,_mm_madd_epi16(_mm_unpacklo_epi8(x,xs),_mm_unpacklo_epi8(y,ys)));
    acc=_mm_add_epi32(acc,_mm_madd_epi16(_mm_unpackhi_epi8(x,xs),_mm_unpackhi_epi8(y,ys)));
  }
  alignas(16) int v[4]; _mm_store_si128((__m128i*)v,acc);return v[0]+v[1]+v[2]+v[3];
}
__attribute__((target("avx2"),noinline)) int avx2(const int8_t*a,const int8_t*b,int) {
  __m256i acc=_mm256_setzero_si256();
  for(int i=0;i<64;i+=16){
    auto x=_mm256_cvtepi8_epi16(_mm_loadu_si128((const __m128i*)(a+i)));
    auto y=_mm256_cvtepi8_epi16(_mm_loadu_si128((const __m128i*)(b+i)));
    acc=_mm256_add_epi32(acc,_mm256_madd_epi16(x,y));
  }
  alignas(32) int v[8];_mm256_store_si256((__m256i*)v,acc);int r=0;for(int x:v)r+=x;return r;
}
__attribute__((target("avx2,avx512f,avx512bw,avx512vl,avx512vnni"),noinline))
int vnni256(const int8_t*a,const int8_t*b,int sb) {
  auto acc=_mm256_setzero_si256();auto flip=_mm256_set1_epi8(char(0x80));
  for(int i=0;i<64;i+=32){
    auto u=_mm256_xor_si256(_mm256_loadu_si256((const __m256i*)(a+i)),flip);
    auto y=_mm256_loadu_si256((const __m256i*)(b+i));
    acc=_mm256_dpbusd_epi32(acc,u,y);
  }
  alignas(32) int v[8];_mm256_store_si256((__m256i*)v,acc);int r=0;for(int x:v)r+=x;return r-128*sb;
}
__attribute__((target("avx2,avx512f,avx512bw,avx512vl,avx512vnni"),noinline))
int vnni512(const int8_t*a,const int8_t*b,int sb) {
  auto u=_mm512_xor_si512(_mm512_loadu_si512((const void*)a),_mm512_set1_epi8(char(0x80)));
  auto acc=_mm512_dpbusd_epi32(_mm512_setzero_si512(),u,_mm512_loadu_si512((const void*)b));
  alignas(64) int v[16];_mm512_store_si512((void*)v,acc);int r=0;for(int x:v)r+=x;return r-128*sb;
}
struct Kernel{const char* name; Fn fn;};
int main(){
  __builtin_cpu_init();std::vector<Kernel> kernels={{"SSE2",sse2}};
  if(__builtin_cpu_supports("avx2"))kernels.push_back({"AVX2",avx2});
  bool v=__builtin_cpu_supports("avx2")&&__builtin_cpu_supports("avx512f")&&__builtin_cpu_supports("avx512bw")&&__builtin_cpu_supports("avx512vl")&&__builtin_cpu_supports("avx512vnni");
  if(v){kernels.push_back({"EVEX_VNNI256",vnni256});kernels.push_back({"VNNI512",vnni512});}
  std::array<int8_t,192>a{},b{};uint64_t cases=0;int mn=0,mx=0;
  auto check=[&](int off){int sb=0;for(int i=0;i<64;i++)sb+=b[off+i];int r=reference(a.data()+off,b.data()+off,sb);mn=std::min(mn,r);mx=std::max(mx,r);for(auto k:kernels){int got=k.fn(a.data()+off,b.data()+off,sb);if(got!=r){std::fprintf(stderr,"Mismatch %s: %d != %d at %llu\n",k.name,got,r,(unsigned long long)cases);std::exit(1);}}cases++;};
  for(int x=-128;x<=127;x++)for(int y=-128;y<=127;y++){a.fill(int8_t(x));b.fill(int8_t(y));check((x+128)%64);}
  std::mt19937_64 rng(20261025);for(int k=0;k<100000;k++){for(int i=0;i<192;i++){a[i]=int8_t(int(rng()%256)-128);b[i]=int8_t(int(rng()%256)-128);}check(k%64);}
  for(int k=0;k<64;k++){for(int i=0;i<192;i++){a[i]=(i&1)?127:-128;b[i]=((i+k)&1)?127:-128;}check(k);}
  // Eight-group accumulation: scale conversion and multiplication order match the inspected source.
  uint64_t float_cases=0;std::array<float,8> sa{},sb{};std::array<int,8> dot_ref{};
  for(int trial=0;trial<4096;trial++){
    std::array<std::array<int8_t,64>,8> aa{},bb{};std::array<int,8>sumb{};
    for(int g=0;g<8;g++){for(int i=0;i<64;i++){aa[g][i]=int8_t(int(rng()%256)-128);bb[g][i]=int8_t(int(rng()%256)-128);sumb[g]+=bb[g][i];}sa[g]=std::ldexp(float(1+(rng()%10000))/10000.f,int(rng()%21)-10);sb[g]=std::ldexp(float(1+(rng()%10000))/10000.f,int(rng()%21)-10);dot_ref[g]=reference(aa[g].data(),bb[g].data(),sumb[g]);}
    double expected=0;for(int g=0;g<8;g++)expected+=double(dot_ref[g])*double(sa[g])*double(sb[g]);
    for(auto k:kernels){double got=0;for(int g=0;g<8;g++)got+=double(k.fn(aa[g].data(),bb[g].data(),sumb[g]))*double(sa[g])*double(sb[g]);if(std::memcmp(&got,&expected,8)!=0){std::fprintf(stderr,"Float sequence mismatch %s\n",k.name);return 2;}}
    float_cases++;
  }
  std::printf("{\"status\":\"pass\",\"compiler\":\"%s\",\"seed\":20261025,\"dot_cases_per_kernel\":%llu,\"eight_group_cases_per_kernel\":%llu,\"observed_dot_min\":%d,\"observed_dot_max\":%d,\"kernels\":[",__VERSION__,(unsigned long long)cases,(unsigned long long)float_cases,mn,mx);
  for(size_t i=0;i<kernels.size();i++)std::printf("%s\"%s\"",i?",":"",kernels[i].name);
  std::printf("],\"scope\":\"Synthetic arithmetic correctness only; not exp688 whole-output equivalence, GCC11.4 verification, or Xeon timing\"}\n");
}
