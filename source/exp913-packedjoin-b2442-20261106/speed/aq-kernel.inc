// The same batch runs on every x86-64 CPU; SSE2 only scans CSV delimiters.
namespace r4 {
struct Digits { char buf[7]; uint8_t n; };
static Digits answers[16384];
static void init() {
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
static unsigned delimit(const char* begin,unsigned n) {
    const __m128i comma=_mm_set1_epi8(','),newline=_mm_set1_epi8('\n');
    unsigned count=0,i=0;
    for (;i+16<=n;i+=16) {
        const __m128i x=_mm_loadu_si128(reinterpret_cast<const __m128i*>(begin+i));
        unsigned mask=unsigned(_mm_movemask_epi8(_mm_or_si128(
            _mm_cmpeq_epi8(x,comma),_mm_cmpeq_epi8(x,newline))));
        while (mask) {
            ends[count++]=i+unsigned(__builtin_ctz(mask));
            mask&=mask-1;
        }
    }
    for (;i<n;++i) if (begin[i]==',' || begin[i]=='\n') ends[count++]=i;
    return count;
}
static void chunk(unsigned n) {
    const unsigned num=delimit(buf,n);
    require(!(num&1),"two input fields");
    const char* next=buf;
    constexpr unsigned batch=BATCH;
    for (unsigned g=0;g<num;g+=batch*2) {
        const unsigned count=std::min(batch,(num-g)/2);
        const char* line[batch];
        unsigned length[batch];
        surf::Row state[batch];
        for (unsigned j=0;j<count;++j) {
            const char* begin=next,*mid=buf+ends[g+2*j],*end=buf+ends[g+2*j+1];
            require(*mid==',' && *end=='\n',"two fields");
            next=end+1;
            if (end>mid+1 && end[-1]=='\r') --end;
            line[j]=begin; length[j]=unsigned(end-begin);
            int32_t q[10]{};
            const bool valid=parsePin580(delayest::trimView(std::string_view(begin,mid-begin)),q[0],q[1],q[8]) &&
                parsePin580(delayest::trimView(std::string_view(mid+1,end-mid-1)),q[2],q[3],q[9]);
            if (valid) surf::prep(q,state[j]);
        }
        for (unsigned j=0;j<count;++j) {
            const auto* q=state[j].q;
            const int answer=newring::scalar(q,envcert::small(q,surf::value(state[j])));
            emit(line[j],length[j],answer); bad+=answer<0;
        }
        rows+=count;
    }
}
static void run(FILE* fin,FILE* outf) {
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
        if (end) chunk(end);
        carry=size-end;
        if (carry) memmove(buf,buf+end,carry);
        if (!nr) break;
    }
    flush(); require(fflush(fout)==0,"flush");
    fprintf(stderr,"{\"rows\":%llu,\"unreachable\":%llu,\"query_allocations\":%llu}\n",
        (unsigned long long)rows,(unsigned long long)bad,(unsigned long long)allocations);
}
}
