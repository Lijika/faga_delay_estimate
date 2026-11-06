// Included after aq-kernel.inc. Initialization follows initialize707(), aqfar::init(), r4::init().
#define CASCADE857_TARGET __attribute__((target("avx512f,avx512bw,avx512dq,avx512vl,avx2,bmi2,bmi,popcnt")))
namespace cascade857 {
#include "cascade-parser.inc"
#include "cascade-model.inc"
static unsigned endStorage[r4::block+1];
static unsigned*const ends=endStorage+1;
static void init(){
 ends[-1]=unsigned(-1);parser::init();model::init();
}
CASCADE857_TARGET static unsigned delimit(unsigned n){
 const auto comma=_mm512_set1_epi8(','),newline=_mm512_set1_epi8('\n');
 unsigned count=0,i=0;
 for(;i+64<=n;i+=64){
  const auto x=_mm512_loadu_si512(r4::buf+i);
  uint64_t mask=_mm512_cmpeq_epi8_mask(x,comma)|_mm512_cmpeq_epi8_mask(x,newline);
  while(mask){ends[count++]=i+unsigned(__builtin_ctzll(mask));mask&=mask-1;}
 }
 for(;i<n;++i)if(r4::buf[i]==','||r4::buf[i]=='\n')ends[count++]=i;
 return count;
}
CASCADE857_TARGET static void chunk(unsigned n){
 constexpr unsigned batch=BATCH;
 static_assert(batch==64,"cascade preserves batch64");
 const unsigned num=delimit(n);require(!(num&1),"two input fields");
 const char* next=r4::buf;
 for(unsigned g=0;g<num;g+=batch*2){
  const unsigned count=std::min(batch,(num-g)/2);
  alignas(64)int xb[2*batch],yb[2*batch],pb[2*batch],answer[batch];
  unsigned good4[batch/4]{};
  model::VRegs regs[batch/8];
  static surf::Row fallback[batch];
  const char* line[batch];unsigned length[batch];
  for(unsigned j=0;j+4<=count;j+=4)
   good4[j/4]=parser::parse4(ends+g+2*j,xb+2*j,yb+2*j,pb+2*j);
  for(unsigned j=0;j<batch;j+=8){
   regs[j/8].exceptional=255;
   if(j+8<=count&&good4[j/4]==255&&good4[j/4+1]==255)
    regs[j/8]=model::prepare(xb+2*j,yb+2*j,pb+2*j);
  }
  for(unsigned j=0;j<count;++j){
   const char* begin=next,*mid=r4::buf+ends[g+2*j],*end=r4::buf+ends[g+2*j+1];
   require(*mid==','&&*end=='\n',"two fields");next=end+1;
   if(end>mid+1&&end[-1]=='\r')--end;
   line[j]=begin;length[j]=unsigned(end-begin);
   if(regs[j/8].exceptional>>(j%8)&1){
    fallback[j]=surf::Row{};
    int32_t q[10]{};
    const bool parsed=((good4[j/4]>>(2*(j%4)))&3)==3;
    bool valid=parsed;
    if(parsed){q[0]=xb[2*j];q[1]=yb[2*j];q[2]=xb[2*j+1];q[3]=yb[2*j+1];q[8]=pb[2*j];q[9]=pb[2*j+1];}
    else valid=parsePin580(delayest::trimView(std::string_view(begin,mid-begin)),q[0],q[1],q[8])&&
     parsePin580(delayest::trimView(std::string_view(mid+1,end-mid-1)),q[2],q[3],q[9]);
    if(valid)surf::prep(q,fallback[j]);
   }
  }
  for(unsigned j=0;j+8<=count;j+=8)model::resolve(regs[j/8],answer+j,xb+2*j,yb+2*j,pb+2*j);
  for(unsigned j=0;j<count;++j){
   if(regs[j/8].exceptional>>(j%8)&1)answer[j]=surf::value(fallback[j]);
   if(regs[j/8].exceptional>>(j%8)&1){
    const auto* q=fallback[j].q;
    answer[j]=newring::scalar(q,envcert::small(q,answer[j]));
   }
   r4::emit(line[j],length[j],answer[j]);r4::bad+=answer[j]<0;
  }
  r4::rows+=count;
 }
}
static void run(FILE*fin,FILE*outf){
 r4::fout=outf;
 require(fwrite("From,To,delay\n",1,14,r4::fout)==14,"output header");
 char header[32];
 require(fgets(header,sizeof(header),fin)&&(!strcmp(header,"From,To\n")||!strcmp(header,"From,To\r\n")),"header");
 unsigned carry=0;
 for(;;){
  const size_t nr=fread(r4::buf+carry,1,r4::block-carry,fin);require(!ferror(fin),"read");
  unsigned size=carry+unsigned(nr);if(!size)break;
  unsigned end=size;while(end&&r4::buf[end-1]!='\n')--end;
  if(nr==0){r4::buf[size++]='\n';end=size;}
  require(end>0||size<r4::block,"record exceeds input buffer");
  if(end)chunk(end);
  carry=size-end;if(carry)memmove(r4::buf,r4::buf+end,carry);
  if(!nr)break;
 }
 r4::flush();require(fflush(r4::fout)==0,"flush");
 fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",
  (unsigned long long)r4::rows,(unsigned long long)r4::bad,(unsigned long long)allocations);
}
}
#undef CASCADE857_TARGET
