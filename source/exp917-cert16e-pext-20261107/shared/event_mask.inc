// Contributions occupy disjoint leaf bits. OR restores each oblivious tree's original address.
namespace logicalEvent {
#include "mask-fns.inc"
static uint64_t hX[239],hY[3*2500],hSy[550],hS[496],hT[496],vS[496],vSy[550],vTy[550],vAxis[14*14],vDelta[2][1099],hRole[256],vRole[16];
static uint16_t hYoff[550],y100[550];
static void init(){
 for(int i=-119;i<=119;i++){int cx=i+(i<0?14:-14);
  hX[119+i]=m0_8(i)|m0_10(std::abs(i))|m0_14((i%10+10)%10)|m0_16(std::abs(i)%10)
       |m0_53((cx%10+10)%10)|m0_54(std::abs(cx)%10);}
 for(int k=0;k<3;k++)for(int a=0;a<50;a++)for(int b=0;b<50;b++){
  int dif=std::abs(a-b),rk=std::min(k==0?100:std::min(a,b)+1,k==2?100:50-std::max(a,b));
  hY[k*2500+a*50+b]=m0_11(dif)|m0_17(dif%12)|m0_42(a)|m0_43(b)|m0_67(2*rk);
 }
 for(int i=0;i<550;i++){y100[i]=i%100;hYoff[i]=((i/100!=0)+(i/100==5))*2500+(i%100)*50;
  hSy[i]=m0_41(i%100);vSy[i]=m1_27(i);vTy[i]=m1_43(i%100);}
 for(int a=76;a<90;a++)for(int b=76;b<90;b++){int d=std::abs(a-b);vAxis[(a-76)*14+b-76]=
  m1_10(d)|m1_16(d%10)|m1_28(a)|m1_30(b)|m1_57(a%10)|m1_58(b%10);}
 for(int i=-549;i<=549;i++){int dy=std::abs(i);for(int x=0;x<2;x++)vDelta[x][549+i]=m1_11(dy)|m1_17(dy%12)|m1_22(125*x+(i<0?125:127)*(dy/12));}
 for(int i=0;i<496;i++){auto &z=ports707[i];hS[i]=m0_0(z.sf);hT[i]=m0_2(z.tf);
  vS[i]=m1_0(z.sf)|m1_1(z.sl)|m1_6(z.dx);}
 for(int i=0;i<256;i++)hRole[i]=m0_20(i);for(int i=0;i<16;i++)vRole[i]=m1_23(i);
}
static inline double read(bool hor,int sp,int tp,int sy,int ax,int ay,int tx,int ty,unsigned m){
 auto& s=ports707[sp];auto& t=ports707[tp];uint64_t bits;
 if(hor){bits=hX[119+tx-ax]|hY[hYoff[ay]+y100[ty]]|hSy[sy]|hS[sp]|hT[tp]|hRole[s.sl^t.tl];}
 else{bits=vAxis[(ax-76)*14+tx-76]|vDelta[std::abs(tx-ax)/10][549+ty-ay]|vSy[sy]|vTy[ty]|vS[sp]|vRole[(s.sl&1)+2*(t.tl&1)];}
 double r=0.;auto &leaf=kLeaves679[!hor];
 for(unsigned k=0;k<8;k++){r+=leaf[k][bits&63];bits>>=8;}
 if(hor){unsigned cell=(m>>9)&1023;r+=kForcedBias[(m&511)*4+std::min(3u,(cell/46)/3)];}
 return r;
}
}
