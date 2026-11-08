// The same batch runs on every x86-64 CPU; SSE2 only scans CSV delimiters.
#include "fast-pin.inc"
namespace r4 {
struct Digits { char buf[7]; uint8_t n; };
static Digits answers[16384];
static void init() {
    pin913::init();
    for (int v=0;v<16384;++v) {
        auto& a=answers[v]; a.buf[0]=',';
        char* end=std::to_chars(a.buf+1,a.buf+6,v).ptr;
        *end++='\n'; a.n=uint8_t(end-a.buf);
    }
}
static constexpr unsigned block=1u<<SHIFT;
alignas(64) static char buf[block+128],out[block+128];
static unsigned ends[block],used;
static FILE* fout;
static uint64_t rows,bad;
static void flush() {
    if (used) { require(fwrite(out,1,used,fout)==used,"write"); used=0; }
}
static inline void emit(const char* begin,unsigned n,int value) {
    if (used+std::max(56u,n+24)>block) flush();
    if (n>=24 && n<=45 && unsigned(value)<16384) {
        char* dest=out+used;
        memcpy(dest,begin,32); memcpy(dest+n-16,begin+n-16,16);
        const auto a=answers[value]; memcpy(dest+n,&a,8); used+=n+a.n;
        return;
    }
    if (n>block-24) require(fwrite(begin,1,n,fout)==n,"long line");
    else { memcpy(out+used,begin,n); used+=n; }
    out[used++]=',';
    used=unsigned(std::to_chars(out+used,out+block+100,value).ptr-out);
    out[used++]='\n';
}
struct Stop {uint32_t positions;uint16_t key,count;};
static constexpr Stop stops[32]={{0u,0u,0u},{0u,65535u,0u},{851968u,8193u,2u},{5u,32u,1u},{2u,4u,1u},{917505u,16386u,2u},{15u,32768u,1u},{6u,64u,1u},{3u,8u,1u},{13u,8192u,1u},{11u,2048u,1u},{983042u,32772u,2u},{917504u,16385u,2u},{786432u,4097u,2u},{7u,128u,1u},{983043u,32776u,2u},{0u,65535u,0u},{4u,16u,1u},{1u,2u,1u},{14u,16384u,1u},{12u,4096u,1u},{10u,1024u,1u},{0u,65535u,0u},{917506u,16388u,2u},{983041u,32770u,2u},{0u,1u,1u},{9u,512u,1u},{851969u,8194u,2u},{0u,65535u,0u},{8u,256u,1u},{0u,65535u,0u},{983040u,32769u,2u}};
static unsigned delimit(const char* begin,unsigned n,uint16_t* ends) {
    const __m128i comma=_mm_set1_epi8(','),newline=_mm_set1_epi8('\n');
    unsigned count=0,i=0;
    for (;i+16<=n;i+=16) {
        const __m128i x=_mm_loadu_si128(reinterpret_cast<const __m128i*>(begin+i));
        unsigned mask=unsigned(_mm_movemask_epi8(_mm_or_si128(
            _mm_cmpeq_epi8(x,comma),_mm_cmpeq_epi8(x,newline))));
        const auto entry=stops[(mask*3370805673u)>>27];
        if(__builtin_expect(entry.key==mask && mask!=65535u,true)){uint32_t ends2=entry.positions + i*65537u;memcpy(ends+count,&ends2,4);count+=entry.count;}
        else while(mask){ends[count++]=uint16_t(i+unsigned(__builtin_ctz(mask)));mask&=mask-1;}
    }
    for (;i<n;++i) if (begin[i]==',' || begin[i]=='\n') ends[count++]=i;
    return count;
}
template<bool Cascade>__attribute__((always_inline)) static inline void partBody(const char* text,unsigned n) {
    uint16_t ends[8192+16];
    const unsigned num=delimit(text,n,ends);
    require(!(num&1),"two input fields");
    const char* next=text;
    constexpr unsigned batch=128;
    for (unsigned g=0;g<num;g+=batch*2) {
        const unsigned count=std::min(batch,(num-g)/2);
        const char* line[batch];
        unsigned length[batch];
        static surf::Row state[batch];
        shortflow::Work shortRows[batch];unsigned shortN=0;uint16_t shortLane[batch];int answersAt[batch];
        constexpr unsigned lead=32;
        using Group=packet60::Group<lead>;Group ring[2];
        auto retire=[&](Group& jobs){
            for(unsigned k=0;k<jobs.hotN;k++){const auto& job=jobs.hot[k];answersAt[packet60::lane(job)]=packet60::result(job);}
            for(unsigned k=0;k<jobs.extraN;k++){const auto& job=jobs.aux[k];answersAt[packet60::lane(job)]=packet60::general(job,jobs.extra[k],answersAt+packet60::lane(job));}
            for(unsigned k=0;k<jobs.coldN;k++){unsigned j=jobs.cold[k];answersAt[j]=surf::value(state[j],answersAt+j);}
        };
        unsigned g0=0;
        for(;g0<count;g0+=lead){
            unsigned group=g0/lead&1;auto& jobs=ring[group];jobs.hotN=jobs.extraN=jobs.coldN=0;
            for(unsigned j=g0;j<std::min(count,g0+lead);j++){
                const char* begin=next,*mid=text+ends[g+2*j],*end=text+ends[g+2*j+1];
                require(*mid==',' && *end=='\n',"two fields");next=end+1;
                if(end>mid+1 && end[-1]=='\r')--end;line[j]=begin;length[j]=unsigned(end-begin);
                int sx,sy,sp,tx,ty,tp;
                if(!pin913::parse<Cascade>(begin,mid,sx,sy,sp)||!pin913::parse<Cascade>(mid+1,end,tx,ty,tp)){answersAt[j]=-1;continue;}
                if(packet60::enqueue<true>(sx,sy,sp,tx,ty,tp,j,jobs))continue;
                auto& r=state[j];r.st.answer=-1;r.st.ready=false;
                auto q=r.q;q[0]=sx;q[1]=sy;q[8]=sp;q[2]=tx;q[3]=ty;q[9]=tp;
                surf::start(r);
                if(!Cascade&&r.st.answer==surf::kCertified){shortLane[shortN]=j;shortRows[shortN++].q=q;}
                else jobs.cold[jobs.coldN++]=j;
            }
            if(g0)retire(ring[group^1]);
        }
        retire(ring[((g0/lead)-1)&1]);
        shortflow::resolve<0>(shortRows,shortN);
        for(unsigned k=0;k<shortN;k++){auto j=shortLane[k];auto v=shortRows[k].result;
         answersAt[j]=v==INT_MAX?surf::value(state[j],answersAt+j):v;}
        bills::finish();
        const size_t raw=size_t(next-line[0]);
        const size_t reserve=raw+12ul*count+64;
        if(reserve<=block){
         if(used+reserve>block)flush();
         char* dst=out+used;
         for(unsigned j=0;j<count;j++){const int answer=answersAt[j];
          const unsigned len=length[j];const char* row=line[j];
          if(len>=24&&len<=45&&unsigned(answer)<16384){memcpy(dst,row,32);memcpy(dst+len-16,row+len-16,16);
           const auto a=answers[answer];memcpy(dst+len,&a,8);dst+=len+a.n;
          }else{memcpy(dst,row,len);dst+=len;*dst++=',';dst=std::to_chars(dst,dst+12,answer).ptr;*dst++='\n';}
          bad+=answer<0;}
         used=unsigned(dst-out);
        }else for(unsigned j=0;j<count;j++){const int answer=answersAt[j];emit(line[j],length[j],answer);bad+=answer<0;}
        rows+=count;
    }
}
template<bool Cascade=false>static void part(const char*text,unsigned n){
 partBody<Cascade>(text,n);
}
template<>__attribute__((target("avx2,bmi,bmi2,popcnt"))) void part<true>(const char*text,unsigned n){
 partBody<true>(text,n);
}
template<bool Cascade=false>static void chunk(unsigned n){
 const char* text=buf;
 while(n){unsigned k=std::min(8192u,n);while(k&&text[k-1]!='\n')--k;
  if(k){part<Cascade>(text,k);}else{const char* nl=(const char*)memchr(text,'\n',n);require(nl,"line termination");k=unsigned(nl-text+1);
   // Large records contain exactly one comma and final LF.
   auto* m=static_cast<const char*>(memchr(text,',',k));require(m&&memchr(m+1,',',text+k-(m+1))==nullptr,"two fields");
   const char* end=text+k-1;if(end>m+1&&end[-1]=='\r')--end;
   surf::Row r{};int q[10]{};if(pin913::parse(text,m,q[0],q[1],q[8])&&pin913::parse(m+1,end,q[2],q[3],q[9]))surf::prep(q,r);
   int value=surf::value(r);emit(text,unsigned(end-text),value);bad+=value<0;++rows;
  }
  text+=k;n-=k;
 }
}
template<bool Cascade=false>static void run(FILE* fin,FILE* outf) {
    fout=outf;
    require(fwrite("From,To,delay\n",1,14,fout)==14,"output header");
    char header[32];
    require(fgets(header,sizeof(header),fin) &&
        (!strcmp(header,"From,To\n") || !strcmp(header,"From,To\r\n")),"header");
    unsigned carry=0;
    for (;;) {
        const size_t nr=fread(buf+carry,1,block-carry,fin);
        require(!ferror(fin),"read");
        unsigned size=carry+unsigned(nr);
        if (!size) break;
        unsigned end=size;
        while (end && buf[end-1]!='\n') --end;
        if (nr==0) { buf[size++]='\n'; end=size; }
        require(end>0 || size<block,"record exceeds input buffer");
        if (end) chunk<Cascade>(end);
        carry=size-end;
        if (carry) memmove(buf,buf+end,carry);
        if (!nr) break;
    }
    flush(); require(fflush(fout)==0,"flush");
    fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",
        (unsigned long long)rows,(unsigned long long)bad,(unsigned long long)allocations);
}
}
