#include <immintrin.h>
#include <fcntl.h>
namespace r4 {
static constexpr uint64_t masks[4]={0x2707000200000000ull,0x100070010000000ull,0x7001618100000ull,0x700011c000100ull};
struct Port {uint64_t word;int p;};static Port byname[4][512];
static uint16_t front[4096],back[4096];
struct Digits {char buf[7];uint8_t n;};static Digits answers[16384];
static char* decimal(char* q,int n){auto e=std::to_chars(q,q+6,n);return e.ptr;}
#ifdef KEYWORDS
#include "keywords.inc"
#endif
__attribute__((target("bmi2"))) static void makePorts(){
 for(int p=0;p<496;++p){auto s=arch.portName(p);int n=s.size();char a[8]{};a[7-n]='/';memcpy(a+8-n,s.data(),n);uint64_t v;memcpy(&v,a,8);auto &e=byname[n-4][_pext_u64(v,masks[n-4])];require(e.word==0,"port collision");e={v,p};}}
static void init(){
 if(__builtin_cpu_supports("bmi2"))makePorts();
#ifdef KEYWORDS
 if(__builtin_cpu_supports("sse4.2"))install_dict();
#endif
 for(int i=0;i<4096;++i){unsigned a=i&15,b=i>>4&15,c=i>>8;
   if(a<10){if(b==15)front[i]=a*4+1;else if(b<10){if(c==15)front[i]=(10*a+b)*4+2;else if(c<10)front[i]=(100*a+10*b+c)*4+3;}}
   if(c<10){if(b==15)back[i]=c*4+1;else if(b<10){if(a==15)back[i]=(10*b+c)*4+2;else if(a<10)back[i]=(100*a+10*b+c)*4+3;}}}
 for(int v=0;v<16384;++v){auto &a=answers[v];a.buf[0]=',';char*e=decimal(a.buf+1,v);*e++='\n';a.n=e-a.buf;}
}
#ifdef U16POS
static constexpr unsigned block=65504;using End=uint16_t;
#else
#ifndef SHIFT
#define SHIFT 17
#endif
static constexpr unsigned block=1<<SHIFT;using End=uint32_t;
#endif
alignas(64) static char buf[block+128],out[block+128];
alignas(64) static End endStorage[block+65];static End* const ends=endStorage+1;
static unsigned used;static bool prefix_ok;static FILE* fout;static uint64_t rows,bad;
static void flush(){if(used){require(fwrite(out,1,used,fout)==used,"write");used=0;}}
static inline void emit(const char*b,unsigned n,int v){
 if(used+std::max(56u,n+24)>block)flush();
 if(n>=24&&n<=45&&unsigned(v)<16384){char*d=out+used;memcpy(d,b,32);memcpy(d+n-16,b+n-16,16);
  auto a=answers[v];memcpy(d+n,&a,8);used+=n+a.n;return;}
 if(n>block-24){require(fwrite(b,1,n,fout)==n,"long line");}else{memcpy(out+used,b,n);used+=n;}
 out[used++]=',';used=std::to_chars(out+used,out+block+100,v).ptr-out;out[used++]='\n';
}
__attribute__((target("bmi2"))) static inline bool pin(const char*b,const char*end,int&x,int&y,int&p){
 // Coordinate lengths recovered independently from opposite ends. Prefix bits of the name never enter its hash.
 const int n=end-b;if(unsigned(n-12)>7)return false;
 uint64_t w;memcpy(&w,end-8,8);unsigned len=end[-1]==']' ? 6u+(end[-7]!='/') : 4u+(end[-2]=='Q');unsigned skip=7-len;
 auto &e=byname[len-4][_pext_u64(w,masks[len-4])];const char* ye=end-len-1;
 uint32_t xx,yy;memcpy(&xx,b+4,4);memcpy(&yy,ye-3,4);
 unsigned xf=front[_pext_u32(xx,0x0f0f0f)],yf=back[_pext_u32(yy,0x0f0f0f)];
 x=xf>>2;y=yf>>2;p=e.p;
 static constexpr unsigned checkx[]={0,0xf0,0xf0f0,0xf0f0f0};static constexpr unsigned checky[]={0,0xf00000,0xf0f000,0xf0f0f0};
 unsigned xn=xf&3,yn=yf&3;
 return xn&&yn&&n==int(6+len+xn+yn)&&b[4+xn]=='_'&&!memcmp(b,"SRB_",4)&&
        ((w>>(8*skip))==(e.word>>(8*skip)))&&(((xx^0x303030)&checkx[xn])|((yy^0x303030)&checky[yn]))==0;
}
static inline bool canonical(const char*b,const char*mid,const char*end,int*q){
#ifdef KEYWORDS
 if(__builtin_cpu_supports("sse4.2"))return keypin(b,mid,q[0],q[1],q[8])&&keypin(mid+1,end,q[2],q[3],q[9]);
#endif
 if(!__builtin_cpu_supports("bmi2"))return false;
 return pin(b,mid,q[0],q[1],q[8]) && pin(mid+1,end,q[2],q[3],q[9]);
}
__attribute__((target("avx512f,avx512bw,avx512vbmi2,bmi2"))) static unsigned delimit(const char*b,unsigned n){
 unsigned num=0,i=0;
#ifdef MASK_LIST
 prefix_ok=n>=4&&!memcmp(b,"SRB_",4);
 alignas(64) static const uint8_t ord[64]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63};
 for(;i+64<=n;i+=64){auto x=_mm512_loadu_si512(b+i);auto m=_mm512_cmpeq_epi8_mask(x,_mm512_set1_epi8(','))|_mm512_cmpeq_epi8_mask(x,_mm512_set1_epi8('\n'));
#ifdef CHECK_SCAN
   auto comma=_mm512_cmpeq_epi8_mask(x,_mm512_set1_epi8(','));auto expected=UINT64_C(0x5555555555555555)>>(num&1);
   auto letters=_mm512_cmpeq_epi8_mask(_mm512_loadu_si512(b+i+1),_mm512_set1_epi8('S'))&
     _mm512_cmpeq_epi8_mask(_mm512_loadu_si512(b+i+2),_mm512_set1_epi8('R'))&
     _mm512_cmpeq_epi8_mask(_mm512_loadu_si512(b+i+3),_mm512_set1_epi8('B'))&
     _mm512_cmpeq_epi8_mask(_mm512_loadu_si512(b+i+4),_mm512_set1_epi8('_'));
   uint64_t check=m;if(i+64==n)check&=~(1ull<<63);
   unsigned pc=__builtin_popcountll(m);uint64_t live=pc==64?~0ull:((1ull<<pc)-1);
   prefix_ok&=!(check&~letters)&&_pext_u64(comma,m)==(expected&live);
#endif
   unsigned cnt=__builtin_popcountll(m);if(cnt<=8){auto y=_mm512_maskz_compress_epi8(m,_mm512_load_si512(ord));auto pos=_mm256_add_epi32(_mm256_set1_epi32(i),_mm256_cvtepu8_epi32(_mm512_castsi512_si128(y)));_mm256_storeu_si256((__m256i*)(ends+num),pos);num+=cnt;}
   else while(m){ends[num++]=i+__builtin_ctzll(m);m&=m-1;}}
#endif
#ifdef CHECK_SCAN
 for(;i<n;++i)if(b[i]==','||b[i]=='\n'){prefix_ok&=(b[i]==((num&1)?'\n':','))&&(i+1==n||!memcmp(b+i+1,"SRB_",4));ends[num++]=i;}return num;
#endif
 constexpr int w=32;
 const __m512i step=_mm512_set_epi16(31,30,29,28,27,26,25,24,23,22,21,20,19,18,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1,0);
 for(;i+w<=n;i+=w){ __m256i s=_mm256_loadu_si256((const __m256i*)(b+i));auto mask=unsigned(_mm256_movemask_epi8(_mm256_or_si256(_mm256_cmpeq_epi8(s,_mm256_set1_epi8(',')),_mm256_cmpeq_epi8(s,_mm256_set1_epi8('\n')))));
#ifdef U16POS
  auto w=_mm512_add_epi16(step,_mm512_set1_epi16(uint16_t(i)));_mm512_mask_compressstoreu_epi16(ends+num,mask,w);num+=__builtin_popcount(mask);
#elif defined(STREAM_COMPRESS)
  alignas(64) uint16_t v[32];_mm512_mask_compressstoreu_epi16(v,mask,step);unsigned c=__builtin_popcount(mask);for(unsigned j=0;j<c;++j)ends[num++]=i+v[j];
#else
  (void)step;while(mask){ends[num++]=i+__builtin_ctz(mask);mask&=mask-1;}
#endif
 }
 for(;i<n;++i)if(b[i]==','||b[i]=='\n')ends[num++]=i;
 return num;
}
#ifdef VECTOR
#include "vector.inc"
#ifdef MODEL_VEC
#include "aq-modelvec.inc"
#endif
#endif
#ifdef INDEP_WRITE
static inline void emitBatch(const unsigned* d,const char* b,const int* ans,unsigned cnt){
 if(used+cnt*72>block)flush();
 unsigned local[32],k=used,sum=0;const char* origin=b;
 for(unsigned j=0;j<cnt;j++){int v=ans[j];unsigned n=d[2*j+1]-unsigned(b-buf);
   if(n<24||n>45||unsigned(v)>=16384){for(unsigned t=0;t<cnt;t++){const char*e=buf+d[2*t+1];emit(origin,unsigned(e-origin),ans[t]);origin=e+1;}return;}
   local[j]=k;k+=n+3+(v>=10)+(v>=100)+(v>=1000)+(v>=10000);b=buf+d[2*j+1]+1;
 }b=origin;
 for(unsigned j=0;j<cnt;j++){char*dst=out+local[j];const char*e=buf+d[2*j+1];unsigned l=e-b;memcpy(dst,b,32);memcpy(dst+l-16,e-16,16);auto num=answers[ans[j]];memcpy(dst+l,&num,8);b=e+1;sum+=ans[j]<0;}
 bad+=sum;used=k;
}
#endif
#ifdef HOT_BLOCK
ATTRV
#endif
static void chunk(unsigned n){
 ends[-1]=End(-1);
 unsigned num;
 if(__builtin_cpu_supports("avx512vbmi2"))num=delimit(buf,n);
 else{num=0;for(unsigned j=0;j<n;++j)if(buf[j]==','||buf[j]=='\n')ends[num++]=j;}
 require(!(num&1),"two input fields");const char*next=buf;
 constexpr unsigned batch=BATCH;for(unsigned g=0;g<num;g+=batch*2){
   const char*line[batch];unsigned length[batch];int ans[batch];unsigned count=std::min(batch,(num-g)/2);
#ifdef SURF
   surf::Row st[batch];
#endif
   int xb[batch*2],yb[batch*2],pb[batch*2];unsigned good4[batch/4]{};
#ifdef VECTOR
   if(__builtin_cpu_supports("avx512vbmi2"))for(unsigned j=0;j+4<=count;j+=4)good4[j/4]=parse4(n,ends+g+2*j,xb+2*j,yb+2*j,pb+2*j);
#else
   (void)xb;(void)yb;(void)pb;(void)good4;
#endif
#ifdef MODEL_VEC
   bool full=count==batch;
   for(unsigned j=0;j<count/4;++j)full=full && good4[j]==255;
   if(full){avm::VRegs regs[batch/8]{};for(unsigned j=0;j<count;j+=8)regs[j/8]=avm::prepare(xb+2*j,yb+2*j,pb+2*j);
#ifdef STAGE2
    for(unsigned j=0;j<count;j+=8)avm::pref2(regs[j/8]);
#endif
    for(unsigned j=0;j<count;j+=8){auto&r=regs[j/8];avm::resolve(r,ans+j
#if defined(A1RECT)||defined(AQJOIN)
     ,xb+2*j,yb+2*j
#endif
     );unsigned slow=r.exceptional;
     while(slow){unsigned k=j+__builtin_ctz(slow);slow&=slow-1;int32_t q[10]={xb[2*k],yb[2*k],xb[2*k+1],yb[2*k+1],0,0,0,0,pb[2*k],pb[2*k+1]};
#ifdef SURF
      surf::Row rr;surf::prep(q,rr);surf::stage(rr);ans[k]=surf::value(rr);
#else
      ans[k]=affine::predict(q);
#endif
     }}
#ifdef COPYBATCH
    if(used+64*count>block)flush();char* dest=out+used;
    for(unsigned j=0;j<count;j++){const char*b=next;next=buf+ends[g+2*j+1]+1;unsigned len=unsigned(next-b-1);
      memcpy(dest,b,32);memcpy(dest+len-16,b+len-16,16);dest+=len;
      if(__builtin_expect(unsigned(ans[j])<16384,true)){
        uint64_t suffix;memcpy(&suffix,answers+ans[j],8);memcpy(dest,&suffix,8);dest+=suffix>>56;
      }else{*dest++=',';dest=std::to_chars(dest,dest+16,ans[j]).ptr;*dest++='\n';bad+=ans[j]<0;}
    }used=unsigned(dest-out);
#elif defined(INDEP_WRITE)
    emitBatch(ends+g,next,ans,count);next=buf+ends[g+2*count-1]+1;
#else
    for(unsigned j=0;j<count;++j){const char* b=next;next=buf+ends[g+2*j+1]+1;emit(b,unsigned(next-b-1),ans[j]);bad+=ans[j]<0;}
#endif
    rows+=count;continue;
   }
#endif
   for(unsigned j=0;j<count;++j){const char*b=next,*m=buf+ends[g+2*j],*e=buf+ends[g+2*j+1];require(*m==','&&*e=='\n',"two fields");next=e+1;if(e>m+1&&e[-1]=='\r')--e;
    line[j]=b;length[j]=unsigned(e-b);int32_t q[10];bool good;
#ifdef VECTOR
    if(((good4[j/4]>>(2*(j%4)))&3)==3){q[0]=xb[2*j];q[1]=yb[2*j];q[2]=xb[2*j+1];q[3]=yb[2*j+1];q[8]=pb[2*j];q[9]=pb[2*j+1];good=true;}
    else
#endif
    good=canonical(b,m,e,q);
    if(!good)good=parsePin580(delayest::trimView(std::string_view(b,m-b)),q[0],q[1],q[8]) && parsePin580(delayest::trimView(std::string_view(m+1,e-m-1)),q[2],q[3],q[9]);
#ifdef SURF
    if(good)surf::prep(q,st[j]);
#else
    ans[j]=good?affine::predict(q):-1;
#endif
   }
#ifdef SURF
   for(unsigned j=0;j<count;++j)surf::stage(st[j]);
   for(unsigned j=0;j<count;++j)ans[j]=surf::value(st[j]);
#endif
   for(unsigned j=0;j<count;++j){emit(line[j],length[j],ans[j]);bad+=ans[j]<0;}rows+=count;
 }}
#ifdef HOT_BLOCK
static void genericChunk(unsigned n){const char*b=buf,*e=buf+n;while(b<e){const char*end=(const char*)memchr(b,'\n',e-b);require(end,"line");const char*m=(const char*)memchr(b,',',end-b);require(m&&!memchr(m+1,',',end-m-1),"two fields");const char*z=end;if(z>b&&z[-1]=='\r')--z;int q[10];bool yes=parsePin580(delayest::trimView(std::string_view(b,m-b)),q[0],q[1],q[8])&&parsePin580(delayest::trimView(std::string_view(m+1,z-m-1)),q[2],q[3],q[9]);int v=-1;if(yes){
#ifdef SURF
 surf::Row r;surf::prep(q,r);surf::stage(r);v=surf::value(r);
#else
 v=affine::predict(q);
#endif
 }emit(b,unsigned(z-b),v);bad+=v<0;++rows;b=end+1;}}
#endif
static void run(FILE* fin,FILE* outf){fout=outf;require(fwrite("From,To,delay\n",1,14,fout)==14,"output header");char h[32];require(fgets(h,sizeof(h),fin) &&(!strcmp(h,"From,To\n")||!strcmp(h,"From,To\r\n")),"header");
 unsigned carry=0;for(;;){size_t nr=fread(buf+carry,1,block-carry,fin);require(!ferror(fin),"read");unsigned size=carry+nr;
 if(!size)break;
 unsigned end=size;while(end&&buf[end-1]!='\n')--end;
 if(nr==0){buf[size++]='\n';end=size;}require(end>0 || size<block,"record exceeds input buffer");
 if(end){
#ifdef HOT_BLOCK
 if(__builtin_cpu_supports("avx512vbmi2") && __builtin_cpu_supports("bmi2")
#ifdef GUARD
 && __builtin_cpu_supports("avx512f") && __builtin_cpu_supports("avx512vbmi") && __builtin_cpu_supports("avx512dq") && __builtin_cpu_supports("avx512vl") && __builtin_cpu_supports("avx512bw")
#endif
 )chunk(end);else genericChunk(end);
#else
 chunk(end);
#endif
 }carry=size-end;if(carry)memmove(buf,buf+end,carry);if(!nr)break;}
 flush();require(fflush(fout)==0,"flush");fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",(unsigned long long)rows,(unsigned long long)bad,(unsigned long long)allocations);
}}
