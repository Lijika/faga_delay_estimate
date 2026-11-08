namespace stripe {
extern "C" const unsigned char stripe_bytes[];
asm(".pushsection .rodata\n.balign 4096\n.global stripe_bytes\nstripe_bytes:\n.incbin \"short-opt.zst\"\n.popsection\n");
extern "C" const uint8_t stripeColumn[],stripeColumnEnd[];
asm(".pushsection .rodata\n.p2align 12\n.global stripeColumn,stripeColumnEnd\nstripeColumn:\n.incbin \"extra-column.xz\"\nstripeColumnEnd:\n.p2align 12\n.popsection");
static constexpr unsigned starts[]={0,90750,92064,6835164,27044178},bits[]={11,10,19,21,12};
static_assert(55831554u<=208ul*138240*2,"two columns fit");
namespace bank=aqfar::cold913;
static inline uint16_t word16(unsigned i){return bank::u16(2*i);}
static inline void put16(unsigned i,uint16_t v){bank::set16(2*i,v);}
static inline unsigned get8(unsigned at){return bank::u8(at);}
static inline void put8(unsigned at,uint8_t v){bank::set8(at,v);}
template<unsigned K> static inline unsigned getBits(unsigned i){unsigned b=i*bits[K],w=starts[K]/2+b/16,off=b&15;
 uint64_t n=word16(w)|(uint64_t(word16(w+1))<<16);if constexpr(bits[K]>16)n|=uint64_t(word16(w+2))<<32;
 return unsigned((n>>off)&((1u<<bits[K])-1));}
static inline unsigned u16(unsigned base,unsigned i){
 if(base==0)return getBits<0>(i);if(base==132000)return getBits<1>(i);
 const unsigned q=starts[4]+3*(i/2);unsigned v=get8(q+(i&1))|((get8(q+2)>>(4*(i&1))&15)<<8);return v&2048?v|61440:v;}
static inline unsigned u32(unsigned base,unsigned i){return base==134104?getBits<2>(i):getBits<3>(i);}
static inline uint32_t cellword(unsigned b){if(b<132000)return u16(0,b/2)|(u16(0,b/2+1)<<16);if(b<134100)return u16(132000,(b-132000)/2)|(u16(132000,(b-132000)/2+1)<<16);if(b<134104)return 0;
 if(b<11490904)return u32(134104,(b-134104)/4);if(b<42285592)return u32(11490904,(b-11490904)/4);
 return u16(42285592,(b-42285592)/2)|(u16(42285592,(b-42285592)/2+1)<<16);}
static void openColumn(){constexpr unsigned raw[]={132000,2100,11356800,30794688,38383168},start[]={0,132000,134104,11490904,42285592},types[]={1,1,1,1,2},packed[]={1200,120,975764,5454824,7108196};
 xz_crc32_init();auto dec=xz_dec_init(XZ_DYNALLOC,1u<<25);require(dec,"XZ decoder init");const auto*s=stripeColumn;alignas(64) static uint8_t temp[65536];
 for(unsigned k=0;k<5;k++){xz_dec_reset(dec);xz_buf in{};in.in=s;in.in_size=packed[k];unsigned done=0,partial=0,nbytes=0,used=0,at=starts[k]/2,saveNib=0;uint64_t buffer=0;
  for(;;){in.out=temp;in.out_pos=0;in.out_size=sizeof(temp);auto rc=xz_dec_run(dec,&in);require(rc==XZ_OK||rc==XZ_STREAM_END,"XZ physical column");
   require(done+in.out_pos<=raw[k],"XZ column overflow");
   if(k<4){const unsigned n=(k<2?2:4),width=bits[k];for(unsigned j=0;j<in.out_pos;j++){
     partial|=uint32_t(temp[j])<<(8*nbytes);if(++nbytes==n){require(partial<(1u<<width),"column value fits");buffer|=uint64_t(partial)<<used;used+=width;
       while(used>=16){put16(at++,uint16_t(buffer));buffer>>=16;used-=16;}nbytes=0;partial=0;}}}
   else{const unsigned half=raw[k]/2;for(unsigned j=0;j<in.out_pos;j++){unsigned v=temp[j],idx=done+j;
     if(idx<half)put8(starts[k]+3*(idx/2)+(idx&1),uint8_t(v));
     else{idx-=half;require((v>>4)==(v&8?15u:0u),"signed 12-bit field");
       if(!(idx&1))saveNib=v&15;else put8(starts[k]+3*(idx/2)+2,uint8_t(saveNib|(v<<4)));}}}
   done+=in.out_pos;if(rc==XZ_STREAM_END)break;
  }if(k<4){require(!nbytes,"column alignment");if(used)put16(at++,uint16_t(buffer));require(2*at==starts[k+1],"column plane length");}require(done==raw[k]&&in.in_pos==in.in_size,"XZ decoded physical size");s+=packed[k];}
 xz_dec_end(dec);require(s==stripeColumnEnd,"XZ stream lengths");uintptr_t l=(uintptr_t(stripeColumn)+4095)&~uintptr_t(4095),u=uintptr_t(s)&~uintptr_t(4095);if(u>l)require(!munmap((void*)l,u-l),"drop XZ physical bytes");}

static constexpr unsigned shortN=13*208*288;
alignas(64) static uint64_t shortHead[shortN];
alignas(64) static uint64_t support[1292][4];
static uint16_t zeroRoot[1050];
alignas(64) static uint64_t change0[12429][2],change1[4376][2];
// 3 exact first-curve samples per 32-bit bank word; 1023 denotes the old 65535 sentinel.
static constexpr unsigned direct0Bytes=145232u*40*4;
static_assert(bank::shortAt+direct0Bytes+2*1617729<=bank::atlas,"bounded dense short bank");
static uint32_t mdSecond[279646];
// Built only after all transient decode buffers have gone away.
static uint8_t quick0[145232][120];
static void initQuick(){
 for(unsigned h=0;h<145232;h++)for(unsigned i=0;i<40;i++){
  unsigned word=bank::u32(bank::shortAt+160*h+4*i);
  for(unsigned j=0;j<3;j++){unsigned v=(word>>(j*10))&1023;
   quick0[h][3*i+j]=uint8_t(std::min(255u,v));}
 }
}
static uint32_t offsets0[(145232+63)/64],offsets1[(279646+63)/64];
struct Place {uint16_t w, ry;};
static Place place[66000];
static unsigned char* p;static int16_t src[496],dst[496];static int8_t disp[25]={-1,-1,0,-1,-1,-1,1,2,3,-1,4,5,6,7,8,-1,9,10,11,-1,-1,-1,12,-1,-1};static int hfee[550];
static void ready(const delayest::Architecture& g){
 std::fill(src,src+496,-1);std::fill(dst,dst+496,-1);
 static const char* ss[208]={"A_AQ0","A_AQ1","A_AY","A_BQ0","A_BQ1","A_BY","A_CQ0","A_CQ1","A_CY","A_DQ0","A_DQ1","A_DY","A_EQ0","A_EQ1","A_EY","A_FQ0","A_FQ1","A_FY","A_GQ0","A_GQ1","A_GY","A_HQ0","A_HQ1","A_HY","S_AQ0","S_AQ1","S_AY","S_BQ0","S_BQ1","S_BY","S_CQ0","S_CQ1","S_CY","S_DQ0","S_DQ1","S_DY","S_EQ0","S_EQ1","S_EY","S_FQ0","S_FQ1","S_FY","S_GQ0","S_GQ1","S_GY","S_HQ0","S_HQ1","S_HY","ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]"},* tt[288]={"ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]","A_A0","A_A1","A_A2","A_A3","A_A4","A_A5","A_AD","A_AM","A_B0","A_B1","A_B2","A_B3","A_B4","A_B5","A_BD","A_BM","A_C0","A_C1","A_C2","A_C3","A_C4","A_C5","A_CD","A_CM","A_D0","A_D1","A_D2","A_D3","A_D4","A_D5","A_DD","A_DM","A_E0","A_E1","A_E2","A_E3","A_E4","A_E5","A_ED","A_EM","A_F0","A_F1","A_F2","A_F3","A_F4","A_F5","A_FD","A_FM","A_G0","A_G1","A_G2","A_G3","A_G4","A_G5","A_GD","A_GM","A_H0","A_H1","A_H2","A_H3","A_H4","A_H5","A_HD","A_HM","S_A0","S_A1","S_A2","S_A3","S_A4","S_A5","S_AD","S_AM","S_B0","S_B1","S_B2","S_B3","S_B4","S_B5","S_BD","S_BM","S_C0","S_C1","S_C2","S_C3","S_C4","S_C5","S_CD","S_CM","S_D0","S_D1","S_D2","S_D3","S_D4","S_D5","S_DD","S_DM","S_E0","S_E1","S_E2","S_E3","S_E4","S_E5","S_ED","S_EM","S_F0","S_F1","S_F2","S_F3","S_F4","S_F5","S_FD","S_FM","S_G0","S_G1","S_G2","S_G3","S_G4","S_G5","S_GD","S_GM","S_H0","S_H1","S_H2","S_H3","S_H4","S_H5","S_HD","S_HM"};
 for(int k=0;k<496;k++){auto n=g.portName(k);for(int j=0;j<208;j++)if(n==ss[j])src[k]=j;for(int j=0;j<288;j++)if(n==tt[j])dst[k]=j;}
 for(int y=0;y<550;y++)hfee[y]=g.lineDelayCrossing(delayest::Axis::Horizontal,0,y);
 const uint8_t*frame=stripe_bytes;const unsigned scratchBytes=12162800;auto*tmp=(uint8_t*)mmap(nullptr,scratchBytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(tmp!=MAP_FAILED,"RLE scratch");
{require(ZSTD_decompress(tmp,10*shortN,frame,2308822)==10*shortN,"descriptors");frame+=2308822;
 uint16_t base8[8]{};
 for(unsigned i=0;i<shortN;i++){
  const auto two=[&](unsigned at){return uint32_t(tmp[shortN*at+i])|(uint32_t(tmp[shortN*(at+1)+i])<<8);};
  const auto three=[&](unsigned at){return two(at)|(uint32_t(tmp[shortN*(at+2)+i])<<16);};
  uint16_t b=base8[i&7]=uint16_t(base8[i&7]+two(0));
  shortHead[i]=uint64_t(b)|(uint64_t(three(2))<<10)|(uint64_t(three(5))<<28)|(uint64_t(two(8))<<47);
 }}
{require(ZSTD_decompress(tmp,43444,frame,3909)==43444,"supports");frame+=3909;memcpy(support,tmp,sizeof(support));memcpy(zeroRoot,tmp+sizeof(support),sizeof(zeroRoot));}
{
 require(ZSTD_decompress(change0,sizeof(change0),frame,65650)==sizeof(change0),"change mask");frame+=65650;
 require(ZSTD_decompress(tmp,290464,frame,130341)==290464,"curve ids");frame+=130341;
 std::vector<uint16_t> curveID(145232); unsigned check=0;
 for(unsigned i=0;i<145232;i++){memcpy(&curveID[i],tmp+2*i,2);unsigned id=curveID[i];require(id<12429,"first mask");
  check+=1+__builtin_popcountll(change0[id][0])+__builtin_popcountll(change0[id][1]);}
 require(check==6081400,"first stream length");
 require(ZSTD_decompress(tmp,12162800,frame,2110744)==12162800,"first value decode");frame+=2110744;
 unsigned offset=0;
 for(unsigned h=0;h<145232;h++){
  unsigned id=curveID[h];const uint64_t* m=change0[id];unsigned pos=offset;
  for(unsigned b=0;b<40;b++){
   uint32_t word=0;
   for(unsigned k=0;k<3;k++){unsigned x=3*b+k;pos+=unsigned((m[x/64]>>(x%64))&1);
    unsigned v=tmp[pos]+256u*tmp[6081400+pos];require(v<1023||v==65535,"first lossless 10-bit encoding");
    word|=(v==65535?1023u:v)<<(10*k);}
   memcpy(bank::data(bank::shortAt+160*h+4*b),&word,4);
  }offset=pos+1;
 }
 require(offset==6081400,"first curve decode coverage");}
{
 require(ZSTD_decompress(change1,sizeof(change1),frame,12607)==sizeof(change1),"change mask");frame+=12607;
 require(ZSTD_decompress(tmp,559292,frame,141677)==559292,"curve ids");frame+=141677;
 unsigned off=0;for(unsigned i=0;i<279646;i++){unsigned id;uint16_t tmpId;memcpy(&tmpId,tmp+2*i,2);id=tmpId;
 if(!(i&63)) offsets1[i>>6]=off;unsigned delta=off-offsets1[i>>6];
 require(id<4376&&delta<65536,"curve metadata");uint32_t md=(delta<<16)|id;mdSecond[i]=md;
 off+=1+__builtin_popcountll(change1[id][0])+__builtin_popcountll(change1[id][1]);}
 require(off==1617729,"curve values");}
{require(ZSTD_decompress(tmp,3235458,frame,1288085)==3235458,"short frame decode");for(unsigned i=0;i<1617729;++i){uint32_t val=0;for(unsigned j=0;j<2;++j)val|=uint32_t(tmp[1617729*j+i])<<(8*j);bank::set16((bank::shortAt+direct0Bytes)+2*i,val);}frame+=1288085;}
 munmap(tmp,scratchBytes);uintptr_t l=(uintptr_t(stripe_bytes)+4095)&~uintptr_t(4095),h=(uintptr_t(stripe_bytes)+6061835)&~uintptr_t(4095);if(h>l)require(!munmap((void*)l,h-l),"release RLE");
}
template<unsigned j>static unsigned delta(unsigned h,unsigned x){
 if constexpr(!j){const unsigned fast=quick0[h][x];if(fast<255)return fast;unsigned w=bank::u32(bank::shortAt+160*h+4*(x/3));unsigned v=(w>>(10*(x%3)))&1023;return v==1023?65535:v;}
 constexpr unsigned value=direct0Bytes;
 uint32_t md=mdSecond[h];const auto*mask=(j?change1:change0)[md&65535];uint64_t through=~uint64_t(0)>>(63-(x&63));
 unsigned rank=x<64?__builtin_popcountll(mask[0]&through):__builtin_popcountll(mask[0])+__builtin_popcountll(mask[1]&through);
 unsigned off=(j?offsets1:offsets0)[h>>6]+(md>>16);
 return bank::u16(bank::shortAt+value+2*(off+rank));}
static void initPlace(){
 for(unsigned i=0;i<66000;++i){unsigned w=u16(0,i);place[i]={uint16_t(w),uint16_t(u16(132000,w))};}
}
static inline int cert(int x,int y,int s,int X,int Y,int t,int old){
 if(old<0||unsigned(s)>=496||unsigned(t)>=496||unsigned(x)>=120||unsigned(X)>=120||unsigned(y)>=550||unsigned(Y)>=550)return old;
 int S=src[s],T=dst[t],dx=X-x,dy=Y-y;if(S<0||T<0||unsigned(dx+2)>=5||unsigned(dy+2)>=5)return old;int d=disp[(dx+2)*5+dy+2];if(d<0)return old;
 unsigned at=(d*208+S)*288+T;uint64_t head=shortHead[at];const auto*bits=support[head>>47];
 const uint64_t bit=uint64_t(1)<<(x&63);
 unsigned v0=(bits[x>>6]&bit)?delta<0>((head>>10)&262143,x):0;
 unsigned val=v0==65535?65535:uint16_t((head&1023)+v0);
 const auto meta=place[y*120+x];unsigned w=meta.w,ry=meta.ry,corr=0;
 if(!(zeroRoot[w]&(1u<<d))){
   unsigned rr=u32(134104,(w*13+d)*208+S);
   if(rr){unsigned leaf=u32(11490904,rr*18+T/16);if(leaf)corr=u16(42285592,leaf*16+T%16);}
 }
 auto second=[&](){return(bits[2+(x>>6)] & bit) ? delta<1>((head>>28)&524287,x):0u;};
 unsigned v=val,v1=0;const bool phase=ry%100<50;
 if(phase){v1=second();v=uint16_t(v+v1);}v=uint16_t(v+corr);
 if(v!=65535&&unsigned(int(ry)+dy)<550)return int(v)+std::abs(hfee[y]-hfee[Y])-std::abs(hfee[ry]-hfee[int(ry)+dy]);
 if(y%100<50)val=uint16_t(val+(phase?v1:second()));return val==65535?old:int(val)+std::abs(hfee[y]-hfee[Y]);
}
static inline int small(const int* q,int a){return std::abs(q[0]-q[2])+std::abs(q[1]-q[3])<=2?cert(q[0],q[1],q[8],q[2],q[3],q[9],a):a;}
}
