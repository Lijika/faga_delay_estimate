
// Canonical endpoint fast path. The existing parser handles every noncanonical shape.
namespace pin913 {
struct Tail {uint64_t suffix;uint16_t port,size;};
static Tail tails[2048];
static uint16_t front[4096],back[4096];
static constexpr uint64_t hashMask=UINT64_C(0x27070f151c000000),mult=UINT64_C(0x70bf95954e371e59);
static inline unsigned hash(uint64_t w){return ((w&hashMask)*mult)>>53;}
template<bool Pext=false>__attribute__((always_inline)) static inline unsigned nibbles(uint32_t w){return (w&15)|((w>>4)&240)|((w>>8)&3840);}
template<>__attribute__((target("bmi2"))) inline unsigned nibbles<true>(uint32_t w){return _pext_u32(w,0x000f0f0fu);}
static void init(){
 for(unsigned i=0;i<4096;i++){
  const unsigned a=i&15,b=(i>>4)&15,c=i>>8;
  if(a<10){if(b==15)front[i]=a*4+1;else if(b<10){if(c==15)front[i]=(a*10+b)*4+2;else if(c<10)front[i]=(a*100+b*10+c)*4+3;}}
  if(c<10){if(b==15)back[i]=c*4+1;else if(b<10){if(a==15)back[i]=(b*10+c)*4+2;else if(a<10)back[i]=(a*100+b*10+c)*4+3;}}
 }
 for(int p=0;p<496;p++){if(ports707[p].source<0&&ports707[p].target<0)continue;const auto name=arch.portName(p);const unsigned n=name.size();if(n<4||n>7)continue;
  uint64_t v=0;uint8_t b[8]{};b[7-n]='/';memcpy(b+8-n,name.data(),n);memcpy(&v,b,8);
  auto& item=tails[hash(v)];if(item.size){item.size=255;continue;}item={v,uint16_t(p),uint16_t(n)};}
}
// Both coordinate tables also return the number of digits, including leading zeroes.
template<bool Pext=false>__attribute__((always_inline)) static inline bool canonical(const char*b,const char*e,int& x,int& y,int& p){
 if(unsigned(e-b-12)>7||memcmp(b,"SRB_",4))return false;
 uint64_t tail;memcpy(&tail,e-8,8);const auto z=tails[hash(tail)];
 if(unsigned(z.size-4)>3)return false;
 const uint64_t nameMask=UINT64_MAX<<((7-z.size)*8);
 if((tail&nameMask)!=z.suffix)return false;
 const char* slash=e-1-z.size;uint32_t a,bk;memcpy(&a,b+4,4);memcpy(&bk,slash-3,4);
 const unsigned f=front[nibbles<Pext>(a)],r=back[nibbles<Pext>(bk)],nx=f&3,ny=r&3;
 constexpr uint32_t hi[]={0,0xf0,0xf0f0,0xf0f0f0},rev[]={0,0xf00000,0xf0f000,0xf0f0f0};
 if(!nx||!ny||slash-b!=int(5+nx+ny)||b[4+nx]!='_'||(((a^0x303030)&hi[nx])|((bk^0x303030)&rev[ny])))return false;
 x=f>>2;y=r>>2;p=z.port;return true;
}
template<bool Pext=false>__attribute__((always_inline)) static inline bool parse(const char*b,const char*e,int&x,int&y,int&p){
 if(canonical<Pext>(b,e,x,y,p))return true;
 return parsePin580(delayest::trimView(std::string_view(b,e-b)),x,y,p);
}
}
