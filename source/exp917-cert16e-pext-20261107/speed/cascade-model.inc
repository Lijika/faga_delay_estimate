// Compact preparation and eight ordinary responses retain the frozen scalar formulas.
namespace model {
#include "compact.inc"
static int rt[496],xpre[121],ypre[551],areaBand[3001],slope[53],xside[120],yhalf[550];
static int b0[sizeof(aqfar::gm0)/2],b1[sizeof(aqfar::gm1)/2];
static int b2[sizeof(aqfar::gm2)/2],b3[sizeof(aqfar::gm3)/2];
static void init(){
 require(blockLeft707==76 && blockRight707==89,"cascade block bounds");
 for(int x=0;x<120;x++)require(unsigned(prefixX707[x])<65536,"cascade horizontal prefix");
 for(int y=0;y<550;y++)require(unsigned(prefixY707[y])<64,"cascade vertical prefix");
 for(int p=0;p<496;p++){
  const auto& port=ports707[p];const int move=port.dx?port.dx:port.dy;
  require(move>=-16 && move<48,"cascade packed displacement");
 }
 initcompact();
 for(int p=0;p<496;p++)rt[p]=ports707[p].target;
 for(int x=0;x<=120;x++)xpre[x]=std::min(x,16)|(std::clamp(x-76,0,14)<<16);
 for(int y=0;y<=550;y++)ypre[y]=std::min(y,100)|((y/100*50+std::min(y%100,50))<<16);
 for(int x=0;x<=120;x++)for(int y=0;y<=550;y++)
  require(aqfar::area[x][y]==(xpre[x]&65535)*(ypre[y]&65535)+(xpre[x]>>16)*(ypre[y]>>16),"cascade hole prefix");
 for(int i=0;i<=3000;i++)areaBand[i]=aqfar::band(i,1,14,70,300,700,1500,3000);
 for(int i=0;i<53;i++)slope[i]=geometry856::tables.slope[i];
 for(int x=0;x<120;x++)xside[x]=(x>=76)+(x>=90);
 for(int y=0;y<550;y++)yhalf[y]=y%100/50;
 for(size_t i=0;i<sizeof(b0)/sizeof(*b0);i++)b0[i]=aqfar::gm0[i];
 for(size_t i=0;i<sizeof(b1)/sizeof(*b1);i++)b1[i]=aqfar::gm1[i];
 for(size_t i=0;i<sizeof(b2)/sizeof(*b2);i++)b2[i]=aqfar::gm2[i];
 for(size_t i=0;i<sizeof(b3)/sizeof(*b3);i++)b3[i]=aqfar::gm3[i];
}
struct VRegs {__m256i m,idx,fee;unsigned exceptional;};
CASCADE857_TARGET static inline __m256i even(const int*a){
 return _mm512_cvtepi64_epi32(_mm512_loadu_si512(a));
}
CASCADE857_TARGET static inline __m256i odd(const int*a){
 return _mm512_cvtepi64_epi32(_mm512_srli_epi64(_mm512_loadu_si512(a),32));
}
struct V {
 __m256i v;
 CASCADE857_TARGET V(__m256i a):v(a){}
 CASCADE857_TARGET operator __m256i()const{return v;}
 CASCADE857_TARGET V& operator+=(V a){v=_mm256_add_epi32(v,a.v);return *this;}
};
CASCADE857_TARGET static inline V operator+(V a,V b){return _mm256_add_epi32(a,b);}
CASCADE857_TARGET static inline V operator-(V a,V b){return _mm256_sub_epi32(a,b);}
CASCADE857_TARGET static inline V operator*(V a,V b){return _mm256_mullo_epi32(a,b);}
CASCADE857_TARGET static inline V operator&(V a,V b){return _mm256_and_si256(a,b);}
CASCADE857_TARGET static inline V operator|(V a,V b){return _mm256_or_si256(a,b);}
CASCADE857_TARGET static inline V operator^(V a,V b){return _mm256_xor_si256(a,b);}
#define CB(x) V(_mm256_set1_epi32(x))
#define CG(base,index) V(_mm256_i32gather_epi32((const int*)(base),index,4))
CASCADE857_TARGET static inline VRegs prepare(const int*x,const int*y,const int*p){
 const V sx=even(x),sy=even(y),tx=odd(x),ty=odd(y),sp=even(p),tp=odd(p);
 unsigned valid=_mm256_cmp_epu32_mask(sx,CB(120),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(tx,CB(120),_MM_CMPINT_LT)&
  _mm256_cmp_epu32_mask(sy,CB(550),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(ty,CB(550),_MM_CMPINT_LT);
 if(valid!=255)return {CB(0),CB(0),CB(0),255};
 const auto xs=CG(xmd,sx),xt=CG(xmd,tx),ys=CG(ymd,sy),yt=CG(ymd,ty),s=CG(srcmd,sp),t=CG(rt,tp);
 valid&=~_mm256_test_epi32_mask((xs&ys)|(xt&yt),CB(0x30000000));
 const auto role=s&CB(511);
 valid&=_mm256_cmpgt_epi32_mask(role,CB(0))&_mm256_cmpgt_epi32_mask(t,CB(-1));
 if(valid!=255)return {CB(0),CB(0),CB(0),255};
 const unsigned hor=_mm256_test_epi32_mask(s,CB(1<<25));
 const auto pos=V(_mm256_mask_blend_epi32(hor,(xs&CB(2047))+sy,(ys&CB(2047))+sx))+(_mm256_srli_epi32(s,9)&CB(65535));
 const auto z=CG(moveTable,pos);
 valid&=_mm256_cmpgt_epi32_mask(z,CB(-1));
 if(valid!=255)return {CB(0),CB(0),CB(0),255};
 const auto eff=(z&CB(255))-CB(128),dp=(_mm256_srli_epi32(z,8)&CB(1023))-CB(512);
 const auto dx=tx-sx-_mm256_maskz_mov_epi32(hor,eff),dy=ty-sy-_mm256_maskz_mov_epi32(~hor,eff);
 if((_mm256_cmp_epu32_mask(_mm256_abs_epi32(dx),CB(119),_MM_CMPINT_LE)&
     _mm256_cmp_epu32_mask(_mm256_abs_epi32(dy),CB(549),_MM_CMPINT_LE))!=255)
  return {CB(0),CB(0),CB(0),255};
 const auto xpmd=(_mm256_srli_epi32(xt,11)&CB(65535))-(_mm256_srli_epi32(xs,11)&CB(65535))-_mm256_maskz_mov_epi32(hor,dp);
 const auto ypmd=(_mm256_srli_epi32(yt,11)&CB(63))-(_mm256_srli_epi32(ys,11)&CB(63))-_mm256_maskz_mov_epi32(~hor,dp);
 const V cost=V(_mm256_abs_epi32(xpmd))+_mm256_abs_epi32(ypmd)+_mm256_srli_epi32(z,18);
 valid&=~(_mm256_cmpeq_epi32_mask(sp,tp)&(_mm256_cmpeq_epi32_mask(dx|dy,CB(0))|_mm256_cmpeq_epi32_mask((sx^tx)|(sy^ty),CB(0))));
 const auto move=V(_mm256_srli_epi32(s,26))-CB(16)+eff;
 const auto ax=sx+_mm256_maskz_mov_epi32(hor,move),ay=sy+_mm256_maskz_mov_epi32(~hor,move);
 const unsigned cross=(_mm256_cmpgt_epi32_mask(CB(76),ax)&_mm256_cmpgt_epi32_mask(tx,CB(89)))|
  (_mm256_cmpgt_epi32_mask(CB(76),tx)&_mm256_cmpgt_epi32_mask(ax,CB(89)));
 const unsigned center=_mm256_cmp_epu32_mask(ax-CB(76),CB(14),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(tx-CB(76),CB(14),_MM_CMPINT_LT);
 const auto actualY=CG(ymd,ay);
 valid&=~((cross&_mm256_test_epi32_mask(actualY&yt,CB(255<<20)))|(center&_mm256_test_epi32_mask(actualY^yt,CB(7<<17))));
 const auto m=CG(geometry856::tables.xp+119,dx)+CG(geometry856::tables.yp+549,dy);
 const auto key=((role-CB(1))*CB(288)+t)*CB(480)+(m&CB(511));
 const auto idx=_mm256_maskz_mov_epi32(valid,key);
 alignas(32)int keys[8];_mm256_store_si256((__m256i*)keys,idx);
 for(int j=0;j<8;j++)_mm_prefetch((const char*)aqfar::locate(keys[j]),_MM_HINT_T0);
 return {m,idx,cost,255^valid};
}
CASCADE857_TARGET static inline void resolve(const VRegs&v,int*out,const int*x,const int*y,const int*ports){
 if(v.exceptional==255)return;
 const V m=v.m,ctx=m&CB(511),cell=_mm256_srli_epi32(m,9)&CB(1023),d=_mm256_srli_epi32(ctx*CB(547),16);
 const auto h=CG(geometry856::tables.head,d*CB(552)+cell);
 alignas(32)int hd[8],key[8],cj[8],dr[8],yv[8]{},recent[8]{},slopeRaw[8]{},field[8]{};
 _mm256_store_si256((__m256i*)hd,h);_mm256_store_si256((__m256i*)key,v.idx);
 _mm256_store_si256((__m256i*)cj,cell);_mm256_store_si256((__m256i*)dr,d);
 for(int i=0;i<8;i++){
  if(v.exceptional>>i&1)continue;
  const auto* row=aqfar::locate(key[i]);const unsigned n=(hd[i]>>16)&63;
  const int base=aqfar::baseFlat(row);const unsigned sh=row[58]&15;
  slopeRaw[i]=row[58]>>4;field[i]=row[63];
  recent[i]=int16_t(aqfar::nearFlat(row,n,base,sh));
  yv[i]=(hd[i]&(1<<23))?recent[i]:aqfar::responseFlat(row,base,sh,dr[i],cj[i]);
 }
 const auto sx=even(x),tx=odd(x),sy=even(y),ty=odd(y);
 const auto DX=CG(xpre,V(_mm256_max_epi32(sx,tx))+CB(1))-CG(xpre,_mm256_min_epi32(sx,tx));
 const auto DY=CG(ypre,V(_mm256_max_epi32(sy,ty))+CB(1))-CG(ypre,_mm256_min_epi32(sy,ty));
 const auto ar=CG(areaBand,_mm256_min_epi32(_mm256_madd_epi16(DX,DY),CB(3000)));
 const auto tr=V(_mm256_srli_epi32(m,19));
 const V nom=_mm256_max_epi32(CB(0),tr+V(_mm256_load_si256((__m256i*)yv)));
 const auto delta=nom-tr-V(_mm256_load_si256((__m256i*)recent));
 const auto dev=CG(slope,_mm256_min_epi32(_mm256_max_epi32(delta,CB(-26)),CB(26))+CB(26));
 const V ss=_mm256_load_si256((__m256i*)slopeRaw);
 auto corr=CG(b0,dev*CB(320)+ar*CB(40)+(h&CB(63)))+
  CG(b1,dev*CB(260)+ss*CB(20)+(_mm256_srli_epi32(h,8)&CB(31)));
 const V vbin=h&CB(7),side=(CG(xside,sx)*CB(3)+CG(xside,tx))*CB(4)+CG(yhalf,sy)*CB(2)+CG(yhalf,ty);
 corr+=CG(b2,((dev*CB(8)+vbin)*CB(2)+CB(1))*CB(4)+d)+CG(b3,(ar*CB(8)+vbin)*CB(36)+side);
 const auto round=_mm256_cvtps_epi32(_mm256_mul_ps(_mm256_cvtepi32_ps(corr),_mm256_set1_ps(1.f/32)));
 _mm256_storeu_si256((__m256i*)out,nom+V(v.fee)+round);
 alignas(32) int rawIntrinsic[8];_mm256_store_si256((__m256i*)rawIntrinsic,tr+V(_mm256_load_si256((__m256i*)yv))+V(v.fee));
 const unsigned shortCandidates=(~v.exceptional)&_mm256_cmple_epi32_mask(tr,CB(254))&255;
 for(unsigned live=shortCandidates;live;live&=live-1){
  const unsigned i=__builtin_ctz(live);
  const int xx=x[2*i],X=x[2*i+1],yy=y[2*i],Y=y[2*i+1];
  const int distance=std::abs(xx-X)+std::abs(yy-Y);
  int value=out[i];
  if (value>=0 && distance<=4) {
   if (distance<=2) {
    int z=stripe::cert(xx,yy,ports[2*i],X,Y,ports[2*i+1],INT_MAX);
    if (z!=INT_MAX) {out[i]=envcert::refine(xx,yy,ports[2*i],X,Y,ports[2*i+1],z);continue;}
   } else if(hd[i]&(1<<23)) {
    int z=newring::residue(xx,yy,ports[2*i],X,Y,ports[2*i+1]);
    if(z!=-128){out[i]=rawIntrinsic[i]+8*z;continue;}
   }
  }
  if(distance<=12)value+=aqfar::atlas855::correction(key[i]/480,xx,yy,X,Y);
  if(distance<=2)value=envcert::cert(xx,yy,ports[2*i],X,Y,ports[2*i+1],value);
  else if(distance<=4)value=newring::apply(xx,yy,ports[2*i],X,Y,ports[2*i+1],value,distance);
  out[i]=value;
 }
 const V distance=V(_mm256_abs_epi32(_mm256_sub_epi32(sx,tx)))+
                  V(_mm256_abs_epi32(_mm256_sub_epi32(sy,ty)));
 unsigned live=(~v.exceptional)&_mm256_cmp_epu32_mask(distance-CB(5),CB(51),_MM_CMPINT_LT)&
  _mm256_cmpgt_epi32_mask(_mm256_load_si256((__m256i*)field),CB(0))&255;
 if(live){
  alignas(32) int intrinsic[8];_mm256_store_si256((__m256i*)intrinsic,nom+V(v.fee));
  for(;live;live&=live-1){const unsigned i=__builtin_ctz(live);
   out[i]=aqfar::tariff::price_result(out[i],intrinsic[i],key[i],cj[i],field[i],x[2*i],x[2*i+1]);}
 }
}
#undef CB
#undef CG
}
