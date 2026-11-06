namespace stripe {
extern "C" const unsigned char stripe_bytes[];
asm(".pushsection .rodata\n.balign 4096\n.global stripe_bytes\nstripe_bytes:\n.incbin \"short-table.zst\"\n.popsection\n");
extern "C" const uint8_t stripeColumn[],stripeColumnEnd[];
asm(".pushsection .rodata\n.p2align 12\n.global stripeColumn,stripeColumnEnd\nstripeColumn:\n.incbin \"extra-column.xz\"\nstripeColumnEnd:\n.p2align 12\n.popsection");
// Logical C2 byte k resides in row k/3 at offsets {59,61,62}[k%3].
static inline uint32_t triple(unsigned row){const auto* q=aqfar::locate(row);uint64_t w;memcpy(&w,q+56,8);return uint32_t((w>>24)&255u)|uint32_t((w>>32)&0xffff00u);}
static inline uint32_t col32(unsigned b){const unsigned row=b/3,rem=b-row*3;return uint32_t((uint64_t(triple(row))|(uint64_t(triple(row+1))<<24))>>(8*rem));}
static inline uint32_t cellword(unsigned byte){return col32(byte&~3u);}
static inline unsigned u16(unsigned base,unsigned i){const unsigned b=base+2*i,row=b/3,rem=b-row*3;uint32_t v=triple(row);
 return rem<2?uint16_t(v>>(8*rem)):((v>>16)|(unsigned(aqfar::locate(row+1)[59])<<8));}
static inline unsigned u32(unsigned base,unsigned i){return col32(base+4*i);}
static inline void putbyte(unsigned at,uint8_t v){constexpr unsigned off[3]={59,61,62};const unsigned row=at/3;const_cast<uint8_t*>(aqfar::locate(row))[off[at-3*row]]=v;}
static inline void putspan(unsigned start,const uint8_t* in,unsigned n){
 unsigned j=0;while(j<n&&(start+j)%3){putbyte(start+j,in[j]);++j;}
 for(;j+3<=n;j+=3){auto*dst=const_cast<uint8_t*>(aqfar::locate((start+j)/3));dst[59]=in[j];memcpy(dst+61,in+j+1,2);}
 for(;j<n;++j)putbyte(start+j,in[j]);}
static_assert(80668760u<=208ul*138240*3,"C2 three-column capacity");
static void openColumn(){constexpr unsigned raw[]={132000,2100,11356800,30794688,38383168},start[]={0,132000,134104,11490904,42285592},types[]={1,1,1,1,2},packed[]={1200,120,975764,5454824,7108196};
 xz_crc32_init();auto dec=xz_dec_init(XZ_DYNALLOC,1u<<25);require(dec,"XZ decoder init");const auto*s=stripeColumn;alignas(64) static uint8_t temp[65536];
 for(unsigned k=0;k<5;k++){xz_dec_reset(dec);xz_buf in{};in.in=s;in.in_size=packed[k];unsigned done=0;
  for(;;){in.out=temp;in.out_pos=0;in.out_size=sizeof(temp);auto rc=xz_dec_run(dec,&in);require(rc==XZ_OK||rc==XZ_STREAM_END,"XZ physical column");
   require(done+in.out_pos<=raw[k],"XZ column overflow");
   if(types[k]==1)putspan(start[k]+done,temp,in.out_pos);
   else{const unsigned half=raw[k]/2;for(unsigned j=0;j<in.out_pos;j++){unsigned at=done+j;unsigned byte=start[k]+2*(at<half?at:at-half)+unsigned(at>=half);putbyte(byte,temp[j]);}}
   done+=in.out_pos;if(rc==XZ_STREAM_END)break;
  }require(done==raw[k]&&in.in_pos==in.in_size,"XZ decoded physical size");s+=packed[k];}
 xz_dec_end(dec);require(s==stripeColumnEnd,"XZ stream lengths");uintptr_t l=(uintptr_t(stripeColumn)+4095)&~uintptr_t(4095),u=uintptr_t(s)&~uintptr_t(4095);if(u>l)require(!munmap((void*)l,u-l),"drop XZ physical bytes");}
static unsigned char* p;static int16_t src[496],dst[496];static int8_t disp[25]={-1,-1,0,-1,-1,-1,1,2,3,-1,4,5,6,7,8,-1,9,10,11,-1,-1,-1,12,-1,-1};static int hfee[550];
static void ready(const delayest::Architecture& g){
 std::fill(src,src+496,-1);std::fill(dst,dst+496,-1);
 static const char* ss[208]={"A_AQ0","A_AQ1","A_AY","A_BQ0","A_BQ1","A_BY","A_CQ0","A_CQ1","A_CY","A_DQ0","A_DQ1","A_DY","A_EQ0","A_EQ1","A_EY","A_FQ0","A_FQ1","A_FY","A_GQ0","A_GQ1","A_GY","A_HQ0","A_HQ1","A_HY","S_AQ0","S_AQ1","S_AY","S_BQ0","S_BQ1","S_BY","S_CQ0","S_CQ1","S_CY","S_DQ0","S_DQ1","S_DY","S_EQ0","S_EQ1","S_EY","S_FQ0","S_FQ1","S_FY","S_GQ0","S_GQ1","S_GY","S_HQ0","S_HQ1","S_HY","ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]"},* tt[288]={"ZDE[0]","ZDE[1]","ZDE[2]","ZDE[3]","ZDE[4]","ZDE[5]","ZDE[6]","ZDE[7]","ZDN[0]","ZDN[1]","ZDN[2]","ZDN[3]","ZDN[4]","ZDN[5]","ZDN[6]","ZDN[7]","ZDS[0]","ZDS[1]","ZDS[2]","ZDS[3]","ZDS[4]","ZDS[5]","ZDS[6]","ZDS[7]","ZDW[0]","ZDW[1]","ZDW[2]","ZDW[3]","ZDW[4]","ZDW[5]","ZDW[6]","ZDW[7]","ZLE[0]","ZLE[1]","ZLE[2]","ZLE[3]","ZLE[4]","ZLE[5]","ZLE[6]","ZLE[7]","ZLN[0]","ZLN[1]","ZLN[2]","ZLN[3]","ZLN[4]","ZLN[5]","ZLN[6]","ZLN[7]","ZLS[0]","ZLS[1]","ZLS[2]","ZLS[3]","ZLS[4]","ZLS[5]","ZLS[6]","ZLS[7]","ZLW[0]","ZLW[1]","ZLW[2]","ZLW[3]","ZLW[4]","ZLW[5]","ZLW[6]","ZLW[7]","ZQE[0]","ZQE[1]","ZQE[2]","ZQE[3]","ZQE[4]","ZQE[5]","ZQE[6]","ZQE[7]","ZQN[0]","ZQN[1]","ZQN[2]","ZQN[3]","ZQN[4]","ZQN[5]","ZQN[6]","ZQN[7]","ZQS[0]","ZQS[1]","ZQS[2]","ZQS[3]","ZQS[4]","ZQS[5]","ZQS[6]","ZQS[7]","ZQW[0]","ZQW[1]","ZQW[2]","ZQW[3]","ZQW[4]","ZQW[5]","ZQW[6]","ZQW[7]","ZSEA[0]","ZSEA[1]","ZSEA[2]","ZSEA[3]","ZSEA[4]","ZSEA[5]","ZSEA[6]","ZSEA[7]","ZSEB[0]","ZSEB[1]","ZSEB[2]","ZSEB[3]","ZSEB[4]","ZSEB[5]","ZSEB[6]","ZSEB[7]","ZSNA[0]","ZSNA[1]","ZSNA[2]","ZSNA[3]","ZSNA[4]","ZSNA[5]","ZSNA[6]","ZSNA[7]","ZSNB[0]","ZSNB[1]","ZSNB[2]","ZSNB[3]","ZSNB[4]","ZSNB[5]","ZSNB[6]","ZSNB[7]","ZSSA[0]","ZSSA[1]","ZSSA[2]","ZSSA[3]","ZSSA[4]","ZSSA[5]","ZSSA[6]","ZSSA[7]","ZSSB[0]","ZSSB[1]","ZSSB[2]","ZSSB[3]","ZSSB[4]","ZSSB[5]","ZSSB[6]","ZSSB[7]","ZSWA[0]","ZSWA[1]","ZSWA[2]","ZSWA[3]","ZSWA[4]","ZSWA[5]","ZSWA[6]","ZSWA[7]","ZSWB[0]","ZSWB[1]","ZSWB[2]","ZSWB[3]","ZSWB[4]","ZSWB[5]","ZSWB[6]","ZSWB[7]","A_A0","A_A1","A_A2","A_A3","A_A4","A_A5","A_AD","A_AM","A_B0","A_B1","A_B2","A_B3","A_B4","A_B5","A_BD","A_BM","A_C0","A_C1","A_C2","A_C3","A_C4","A_C5","A_CD","A_CM","A_D0","A_D1","A_D2","A_D3","A_D4","A_D5","A_DD","A_DM","A_E0","A_E1","A_E2","A_E3","A_E4","A_E5","A_ED","A_EM","A_F0","A_F1","A_F2","A_F3","A_F4","A_F5","A_FD","A_FM","A_G0","A_G1","A_G2","A_G3","A_G4","A_G5","A_GD","A_GM","A_H0","A_H1","A_H2","A_H3","A_H4","A_H5","A_HD","A_HM","S_A0","S_A1","S_A2","S_A3","S_A4","S_A5","S_AD","S_AM","S_B0","S_B1","S_B2","S_B3","S_B4","S_B5","S_BD","S_BM","S_C0","S_C1","S_C2","S_C3","S_C4","S_C5","S_CD","S_CM","S_D0","S_D1","S_D2","S_D3","S_D4","S_D5","S_DD","S_DM","S_E0","S_E1","S_E2","S_E3","S_E4","S_E5","S_ED","S_EM","S_F0","S_F1","S_F2","S_F3","S_F4","S_F5","S_FD","S_FM","S_G0","S_G1","S_G2","S_G3","S_G4","S_G5","S_GD","S_GM","S_H0","S_H1","S_H2","S_H3","S_H4","S_H5","S_HD","S_HM"};
 for(int k=0;k<496;k++){auto n=g.portName(k);for(int j=0;j<208;j++)if(n==ss[j])src[k]=j;for(int j=0;j<288;j++)if(n==tt[j])dst[k]=j;}
 for(int y=0;y<550;y++)hfee[y]=g.lineDelayCrossing(delayest::Axis::Horizontal,0,y);
 p=(unsigned char*)mmap(nullptr,26853682,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(p!=MAP_FAILED,"short table allocation");
 const uint8_t*frame=stripe_bytes;const unsigned scratchBytes=12162800;auto*tmp=(uint8_t*)mmap(nullptr,scratchBytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(tmp!=MAP_FAILED,"RLE scratch");
{require(ZSTD_decompress(tmp,1557504,frame,776936)==1557504,"field block");for(unsigned i=0;i<778752;i++)for(unsigned k=0;k<2;k++)p[0+2*i+k]=tmp[k*778752+i];frame+=776936;}
{require(ZSTD_decompress(tmp,6230016,frame,1748077)==6230016,"field block");for(unsigned i=0;i<1557504;i++)for(unsigned k=0;k<4;k++)p[1557504+4*i+k]=tmp[k*1557504+i];frame+=1748077;}
{require(ZSTD_decompress(p+7787520,198864,frame,65650)==198864,"field block");frame+=65650;}
{require(ZSTD_decompress(tmp,290464,frame,130341)==290464,"field block");unsigned n=0;auto*d=(uint32_t*)(p+7986384);for(unsigned i=0;i<145232;i++){unsigned id=((uint16_t*)tmp)[i];d[2*i]=id;d[2*i+1]=n;uint64_t lo,hi;memcpy(&lo,p+7787520+16*id,8);memcpy(&hi,p+7787520+16*id+8,8);n+=1+__builtin_popcountll(lo)+__builtin_popcountll(hi);}frame+=130341;}
{require(ZSTD_decompress(tmp,12162800,frame,2110744)==12162800,"field block");for(unsigned i=0;i<6081400;i++)for(unsigned k=0;k<2;k++)p[9148240+2*i+k]=tmp[k*6081400+i];frame+=2110744;}
{require(ZSTD_decompress(p+21311040,70016,frame,12607)==70016,"field block");frame+=12607;}
{require(ZSTD_decompress(tmp,559292,frame,141677)==559292,"field block");unsigned n=0;auto*d=(uint32_t*)(p+21381056);for(unsigned i=0;i<279646;i++){unsigned id=((uint16_t*)tmp)[i];d[2*i]=id;d[2*i+1]=n;uint64_t lo,hi;memcpy(&lo,p+21311040+16*id,8);memcpy(&hi,p+21311040+16*id+8,8);n+=1+__builtin_popcountll(lo)+__builtin_popcountll(hi);}frame+=141677;}
{require(ZSTD_decompress(tmp,3235458,frame,1288085)==3235458,"field block");for(unsigned i=0;i<1617729;i++)for(unsigned k=0;k<2;k++)p[23618224+2*i+k]=tmp[k*1617729+i];frame+=1288085;}
 munmap(tmp,scratchBytes);uintptr_t l=(uintptr_t(stripe_bytes)+4095)&~uintptr_t(4095),h=(uintptr_t(stripe_bytes)+6274117)&~uintptr_t(4095);if(h>l)require(!munmap((void*)l,h-l),"release RLE");
}
template<unsigned j>static unsigned delta(unsigned h,unsigned x){constexpr unsigned di=j?21381056:7986384,ma=j?21311040:7787520,v=j?23618224:9148240;
 const auto* info=(const uint32_t*)(p+di)+2*h;const auto* mask=(const uint64_t*)(p+ma)+2*info[0];unsigned n;
 uint64_t lm=~0ULL>>(63-(x&63));if(x<64)n=__builtin_popcountll(mask[0]&lm);else n=__builtin_popcountll(mask[0])+__builtin_popcountll(mask[1]&lm);
 return ((const uint16_t*)(p+v))[info[1]+n];}
static inline int cert(int x,int y,int s,int X,int Y,int t,int old){
 if(old<0||unsigned(s)>=496||unsigned(t)>=496||unsigned(x)>=120||unsigned(X)>=120||unsigned(y)>=550||unsigned(Y)>=550)return old;
 int S=src[s],T=dst[t],dx=X-x,dy=Y-y;if(S<0||T<0||unsigned(dx+2)>=5||unsigned(dy+2)>=5)return old;int d=disp[(dx+2)*5+dy+2];if(d<0)return old;
 unsigned at=(d*208+S)*288+T;const uint32_t* ids=(const uint32_t*)(p+1557504)+2*at;const auto v0=delta<0>(ids[0],x);unsigned val=v0==65535?65535:uint16_t(((const uint16_t*)p)[at]+v0);
 unsigned w=u16(0,y*120+x),ry=u16(132000,w),rr=u32(134104,(w*13+d)*208+S);
 unsigned leaf=u32(11490904,rr*18+T/16),corr=u16(42285592,leaf*16+T%16);
 unsigned v=val;if(ry%100<50)v=uint16_t(v+delta<1>(ids[1],x));v=uint16_t(v+corr);
 if(v!=65535&&unsigned(int(ry)+dy)<550)return int(v)+std::abs(hfee[y]-hfee[Y])-std::abs(hfee[ry]-hfee[int(ry)+dy]);
 if(y%100<50)val=uint16_t(val+delta<1>(ids[1],x));return val==65535?old:int(val)+std::abs(hfee[y]-hfee[Y]);
}
static inline int small(const int* q,int a){return std::abs(q[0]-q[2])+std::abs(q[1]-q[3])<=2?cert(q[0],q[1],q[8],q[2],q[3],q[9],a):a;}
}
