// Every frozen threshold contributes to a disjoint bit in eight oblivious leaf addresses.
namespace eventHot {
#include "mask-fns.inc"
template<unsigned N> struct Axis {
    uint64_t masks[N]{};
    unsigned n=0;
    uint8_t intern(uint64_t v) {
        for(unsigned i=0;i<n;i++)if(masks[i]==v)return uint8_t(i);
        require(n<N,"event equivalence class capacity");masks[n]=v;return uint8_t(n++);
    }
};
static Axis<38> hx;static Axis<242> hy;static Axis<3> hs;static Axis<2> hp,ht,hr;
static Axis<113> vx;static Axis<9> vd;static Axis<2> vs,vt;static Axis<8> vp;static Axis<2> vr;
static int16_t horizontal[38*242*24],vertical[113*36*16];
static uint32_t hdx[239],hdy[3*50*50],vxx[14*14];
static uint16_t off[550],ym[550],vdy[2][1099];
static uint8_t hsrc[496],htgt[496],vsrc[496],hrid[256],vrid[4],hsy[550],vsy[550],vty[550];
static double leaves(unsigned model,uint64_t bits){double sum=0.;for(unsigned k=0;k<8;k++){sum+=kLeaves679[model][k][bits&63];bits>>=8;}return sum;}
// Anything within a half-ULP of a rounded threshold needs the double evaluator.
static int16_t rounded(double v){
  const double gap=std::abs(v-std::floor(v)-.5);
  require(std::abs(v)<32767 && (gap==0. || gap>0x1p-19),"safe event quantization");
  return int16_t(std::floor(v+.5));
}
static void init(){
 for(int i=-119;i<=119;i++){int cx=i+(i<0?14:-14);
  hdx[119+i]=242*24*hx.intern(m0_8(i)|m0_10(std::abs(i))|m0_14((i%10+10)%10)|m0_16(std::abs(i)%10)|m0_53((cx%10+10)%10)|m0_54(std::abs(cx)%10));}
 for(int k=0;k<3;k++)for(int a=0;a<50;a++)for(int b=0;b<50;b++){
  int dif=std::abs(a-b),rk=std::min(k==0?100:std::min(a,b)+1,k==2?100:50-std::max(a,b));
  hdy[k*2500+a*50+b]=24*hy.intern(m0_11(dif)|m0_17(dif%12)|m0_42(a)|m0_43(b)|m0_67(2*rk));}
 for(int i=0;i<550;i++){ym[i]=i%100;off[i]=((i/100!=0)+(i/100==5))*2500+(i%100)*50;
  hsy[i]=8*hs.intern(m0_41(i%100));vsy[i]=32*vs.intern(m1_27(i));vty[i]=16*vt.intern(m1_43(i%100));}
 for(int a=76;a<90;a++)for(int b=76;b<90;b++){int d=std::abs(a-b);
   vxx[(a-76)*14+b-76]=36*16*vx.intern(m1_10(d)|m1_16(d%10)|m1_28(a)|m1_30(b)|m1_57(a%10)|m1_58(b%10));}
 for(int i=-549;i<=549;i++)for(int x=0;x<2;x++){int dy=std::abs(i);vdy[x][549+i]=64*vd.intern(m1_11(dy)|m1_17(dy%12)|m1_22(125*x+(i<0?125:127)*(dy/12)));}
 for(int i=0;i<496;i++){auto &z=ports707[i];hsrc[i]=4*hp.intern(m0_0(z.sf));htgt[i]=2*ht.intern(m0_2(z.tf));vsrc[i]=2*vp.intern(m1_0(z.sf)|m1_1(z.sl)|m1_6(z.dx));}
 for(int i=0;i<256;i++)hrid[i]=hr.intern(m0_20(i));for(int i=0;i<4;i++)vrid[i]=vr.intern(m1_23(i));
 for(unsigned i=0;i<hx.n;i++)for(unsigned j=0;j<hy.n;j++)for(unsigned y=0;y<hs.n;y++)
  for(unsigned s=0;s<hp.n;s++)for(unsigned t=0;t<ht.n;t++)for(unsigned r=0;r<hr.n;r++)
   horizontal[i*242*24+j*24+y*8+s*4+t*2+r]=rounded(leaves(0,hx.masks[i]|hy.masks[j]|hs.masks[y]|hp.masks[s]|ht.masks[t]|hr.masks[r]));
 for(unsigned i=0;i<vx.n;i++)for(unsigned j=0;j<vd.n;j++)for(unsigned y=0;y<vs.n;y++)for(unsigned t=0;t<vt.n;t++)
  for(unsigned s=0;s<vp.n;s++)for(unsigned r=0;r<vr.n;r++)
   vertical[i*36*16+j*64+y*32+t*16+s*2+r]=rounded(leaves(1,vx.masks[i]|vd.masks[j]|vs.masks[y]|vt.masks[t]|vp.masks[s]|vr.masks[r]));
}
static inline int read(unsigned event,int sp,int tp,int sy,int ax,int ay,int tx,int ty,unsigned m){
 const unsigned sl=ports707[sp].sl,tl=ports707[tp].tl;
 if(event==1){unsigned id=hdx[119+tx-ax]+hdy[off[ay]+ym[ty]]+hsy[sy]+hsrc[sp]+htgt[tp]+hrid[sl^tl];unsigned qx=((m>>9)&1023)/46;return horizontal[id]+kForcedBias[(m&511)*4+std::min(qx/3,3u)];}
 unsigned id=vxx[(ax-76)*14+tx-76]+vdy[std::abs(tx-ax)/10][549+ty-ay]+vsy[sy]+vty[ty]+vsrc[sp]+vrid[(sl&1)+2*(tl&1)];return vertical[id];
}
}
