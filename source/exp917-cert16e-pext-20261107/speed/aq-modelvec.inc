namespace avm {
alignas(64) static int rp[496],rt[496],cls[496],ox[496],oy[496],exists[66000],lineX[120*120],lineY[550*550];
#ifdef FLAT_GEO
static int ctl[496],fee0[496];static uint32_t normal[66000],usable[66000];
#endif
static std::vector<uint32_t> geo;static uint32_t xp[239],yp[1099];
#ifdef COMPACT
#include "compact.inc"
#endif
static void init(){
#ifdef COMPACT
 initcompact();
#endif
 for(int i=0;i<496;i++)rt[i]=ports707[i].target;
 for(int x=-119;x<=119;++x){unsigned a=std::abs(x);xp[x+119]=(125u*(a/10)<<19)|((a/10)*46<<9)|(240u*(x<0)+12u*(a%10));}
 for(int y=-549;y<=549;++y){unsigned a=std::abs(y);yp[y+549]=((y<0?125u:127u)*(a/12)<<19)|(a/12<<9)|(120u*(y<0)+a%12);}

}
struct VRegs{__m256i m,idx,fee;unsigned exceptional;unsigned eventmask{};
#ifdef STAGE2
 __m256i word{},ai{},bi{};
#endif
};
#define AVT __attribute__((target("avx512f,avx512dq,avx512bw,avx512vl,avx512vbmi2,avx512vbmi,bmi2")))
AVT static inline __m256i even(const int*a){const auto v=_mm512_loadu_si512(a);return _mm512_cvtepi64_epi32(v);}
AVT static inline __m256i odd(const int*a){const auto v=_mm512_loadu_si512(a);return _mm512_cvtepi64_epi32(_mm512_srli_epi64(v,32));}
#define BROAD(x) _mm256_set1_epi32(x)
#define G(base,index) _mm256_i32gather_epi32((const int*)(base),index,4)
struct V {__m256i v;AVT V(__m256i a):v(a){} AVT operator __m256i() const{return v;} AVT V& operator+=(V o){v=_mm256_add_epi32(v,o.v);return *this;} AVT V& operator-=(V o){v=_mm256_sub_epi32(v,o.v);return *this;}};
AVT static inline V operator+(V a,V b){return _mm256_add_epi32(a,b);}
AVT static inline V operator-(V a,V b){return _mm256_sub_epi32(a,b);}
AVT static inline V operator*(V a,V b){return _mm256_mullo_epi32(a,b);}
AVT static inline V operator&(V a,V b){return _mm256_and_si256(a,b);}
AVT static inline V operator|(V a,V b){return _mm256_or_si256(a,b);}
AVT static inline V operator^(V a,V b){return _mm256_xor_si256(a,b);}
#undef BROAD
#undef G
#define BROAD(x) V(_mm256_set1_epi32(x))
#define G(base,index) V(_mm256_i32gather_epi32((const int*)(base),index,4))
AVT static inline VRegs prepare(const int*x,const int*y,const int*p){
 V sx=even(x),sy=even(y),tx=odd(x),ty=odd(y),sp=even(p),tp=odd(p);[[maybe_unused]] auto site=sy*BROAD(120)+sx,tsite=ty*BROAD(120)+tx;
#ifdef COMPACT
 unsigned valid=_mm256_cmp_epu32_mask(sx,BROAD(120),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(tx,BROAD(120),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(sy,BROAD(550),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(ty,BROAD(550),_MM_CMPINT_LT);

#ifdef FASTVALID
 if(valid!=255)return {BROAD(0),BROAD(0),BROAD(0),255};
#else
 sx=_mm256_maskz_mov_epi32(valid,sx);tx=_mm256_maskz_mov_epi32(valid,tx);sy=_mm256_maskz_mov_epi32(valid,sy);ty=_mm256_maskz_mov_epi32(valid,ty);
#endif
 auto xs=G(xmd,sx),xt=G(xmd,tx),ys=G(ymd,sy),yt=G(ymd,ty),s=G(srcmd,sp),t=G(rt,tp);
 valid&=~_mm256_test_epi32_mask((xs&ys)|(xt&yt),BROAD(0x30000000));
 auto role=s&BROAD(511);valid&=_mm256_cmpgt_epi32_mask(role,BROAD(0))&_mm256_cmpgt_epi32_mask(t,BROAD(-1));
 unsigned hor=_mm256_test_epi32_mask(s,BROAD(1<<25));
 auto pos=V(_mm256_mask_blend_epi32(hor,(xs&BROAD(2047))+sy,(ys&BROAD(2047))+sx))+(_mm256_srli_epi32(s,9)&BROAD(65535));auto z=G(moveTable,pos);
 valid&=_mm256_cmpgt_epi32_mask(z,BROAD(-1));
#ifdef FASTVALID
 if(valid!=255)return {BROAD(0),BROAD(0),BROAD(0),255};
#else
 z=_mm256_mask_mov_epi32(BROAD(128+(512<<8)),valid,z);
#endif
 auto eff=(z&BROAD(255))-BROAD(128),dp=(_mm256_srli_epi32(z,8)&BROAD(1023))-BROAD(512);
 auto dx=tx-sx-_mm256_maskz_mov_epi32(hor,eff),dy=ty-sy-_mm256_maskz_mov_epi32(~hor,eff);
 auto xpmd=(_mm256_srli_epi32(xt,11)&BROAD(0xffff))-(_mm256_srli_epi32(xs,11)&BROAD(0xffff))-_mm256_maskz_mov_epi32(hor,dp),ypmd=(_mm256_srli_epi32(yt,11)&BROAD(63))-(_mm256_srli_epi32(ys,11)&BROAD(63))-_mm256_maskz_mov_epi32(~hor,dp);
 V cost=V(_mm256_abs_epi32(xpmd))+_mm256_abs_epi32(ypmd)+_mm256_srli_epi32(z,18);
 valid&=~(_mm256_cmpeq_epi32_mask(sp,tp)&(_mm256_cmpeq_epi32_mask(dx|dy,BROAD(0))|_mm256_cmpeq_epi32_mask((sx^tx)|(sy^ty),BROAD(0))));
#ifdef SURF
#ifndef PLAIN
 auto nom=V(_mm256_srli_epi32(s,26))-BROAD(16);auto move=nom+eff;auto ax=sx+_mm256_maskz_mov_epi32(hor,move),ay=sy+_mm256_maskz_mov_epi32(~hor,move);
#ifndef FASTVALID
 ay=_mm256_maskz_mov_epi32(valid,ay);
#endif
 unsigned cross=(_mm256_cmpgt_epi32_mask(BROAD(76),ax)&_mm256_cmpgt_epi32_mask(tx,BROAD(89)))|(_mm256_cmpgt_epi32_mask(BROAD(76),tx)&_mm256_cmpgt_epi32_mask(ax,BROAD(89)));
 unsigned center=_mm256_cmp_epu32_mask(ax-BROAD(76),BROAD(14),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(tx-BROAD(76),BROAD(14),_MM_CMPINT_LT);
 auto actualY=G(ymd,ay);
#ifdef FAST_EVENT

#else
 valid&=~((cross&_mm256_test_epi32_mask(actualY&yt,BROAD(255<<20)))|(center&_mm256_test_epi32_mask(actualY^yt,BROAD(7<<17))));
#endif
#endif
#ifndef FASTVALID
 dx=_mm256_maskz_mov_epi32(valid,dx);dy=_mm256_maskz_mov_epi32(valid,dy);
#endif
 auto m=G(xp+119,dx)+G(yp+549,dy);
 #ifdef FAST_EVENT
 unsigned horEvent=cross&_mm256_test_epi32_mask(actualY&yt,BROAD(255<<20)),verEvent=center&_mm256_test_epi32_mask(actualY^yt,BROAD(7<<17));
 unsigned events=horEvent|verEvent;
 if(__builtin_expect(events!=0,false)){
  alignas(32) int axs[8],ays[8],ms[8],fees[8]{};
  _mm256_store_si256((__m256i*)axs,ax);_mm256_store_si256((__m256i*)ays,ay);_mm256_store_si256((__m256i*)ms,m);
  for(unsigned todo=events&valid;todo;todo&=todo-1){
   unsigned i=__builtin_ctz(todo);double raw=logicalEvent::read(horEvent>>i&1,p[2*i],p[2*i+1],y[2*i],axs[i],ays[i],x[2*i+1],y[2*i+1],ms[i]);
   // Charged cost can only be folded when rounding commutes with adding the nonnegative integer base.
   double r=std::floor(raw+.5); if(raw<0 || std::abs(raw+.5-std::nearbyint(raw+.5))<1e-9){valid&=~(1u<<i);continue;}
   fees[i]=int(r);
  }
  cost+=_mm256_load_si256((__m256i*)fees);
 }

#endif
 auto key=((role-BROAD(1))*BROAD(288)+t)*BROAD(480)+(m&BROAD(511));auto idx=_mm256_maskz_mov_epi32(valid,key);
 alignas(32)int keys[8];_mm256_store_si256((__m256i*)keys,idx);for(int j=0;j<8;j++)
_mm_prefetch((const char*)(aqfar::locate(keys[j])),_MM_HINT_T0);
 return {m,idx,cost,255^valid,horEvent|verEvent};
#else
 auto packed=G(vqX+119,dx)+G(vqY+549,dy);auto res=packed&BROAD(127),band=_mm256_srli_epi32(packed,7)&BROAD(63);auto idx=(((role-BROAD(1))*BROAD(288)+t)*BROAD(36)+band)*BROAD(NPART);
 if constexpr(NPART>1){V group=(__m256i)((__v8si)res.v/(120/NPART));idx+=group;res-=group*BROAD(120/NPART);}
 return {V(_mm256_slli_epi32(_mm256_srli_epi32(packed,14),19))|res,_mm256_maskz_mov_epi32(valid,idx),cost,255^valid};
#endif
#else
 unsigned valid=_mm256_cmp_epu32_mask(sx,BROAD(120),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(tx,BROAD(120),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(sy,BROAD(550),_MM_CMPINT_LT)&_mm256_cmp_epu32_mask(ty,BROAD(550),_MM_CMPINT_LT);
 site=_mm256_maskz_mov_epi32(valid,site);tsite=_mm256_maskz_mov_epi32(valid,tsite);sx=_mm256_maskz_mov_epi32(valid,sx);tx=_mm256_maskz_mov_epi32(valid,tx);sy=_mm256_maskz_mov_epi32(valid,sy);ty=_mm256_maskz_mov_epi32(valid,ty);
#ifdef FLAT_GEO
 auto src=G(rp,sp),tgt=G(rt,tp);
#ifdef APPROX_GEO
 auto type=G(usable,site);
#else
 auto type=G(normal,site);
#endif
 valid&=_mm256_test_epi32_mask(type,G(ctl,sp))&_mm256_cmpgt_epi32_mask(G(exists,tsite),BROAD(0))&_mm256_cmpgt_epi32_mask(src,BROAD(-1))&_mm256_cmpgt_epi32_mask(tgt,BROAD(-1));
 V ax=sx,ay=sy,dx=tx-sx,dy=ty-sy,charge=G(fee0,sp);
#else
 auto pos=G(geo.data(),G(cls,sp)+site);auto src=G(rp,sp),tgt=G(rt,tp);
 valid&=_mm256_cmpneq_epi32_mask(pos,BROAD(-1))&_mm256_cmpgt_epi32_mask(G(exists,tsite),BROAD(0))&_mm256_cmpgt_epi32_mask(src,BROAD(-1))&_mm256_cmpgt_epi32_mask(tgt,BROAD(-1));
 pos=_mm256_maskz_mov_epi32(valid,pos);auto ax=pos&BROAD(127),ay=_mm256_srli_epi32(pos,7)&BROAD(1023);auto dx=tx-ax+G(ox,sp),dy=ty-ay+G(oy,sp);
 V charge=_mm256_srli_epi32(pos,17);
#endif
 dx=_mm256_maskz_mov_epi32(valid,dx);dy=_mm256_maskz_mov_epi32(valid,dy);
 auto m=G(xp+119,dx)+G(yp+549,dy);auto lx=G(lineX,ax*BROAD(120)+tx),ly=G(lineY,ay*BROAD(550)+ty);
 unsigned same=_mm256_cmpeq_epi32_mask(sp,tp)&(_mm256_cmpeq_epi32_mask(dx|dy,BROAD(0))|_mm256_cmpeq_epi32_mask((sx^tx)|(sy^ty),BROAD(0)));
 auto pair=src+tgt;auto ctx=m&BROAD(511);V idx=BROAD(0);
#ifdef SURF
 idx=pair*BROAD(480)+ctx;valid&=~_mm256_test_epi32_mask(lx&ly,BROAD(49152));
#else
 auto sign=_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(BROAD(0),dx),2)|_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(BROAD(0),dy),1);
 auto xx=_mm256_abs_epi32(dx),yy=_mm256_abs_epi32(dy);V bx=V(_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(xx,BROAD(19)),1))+_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(xx,BROAD(59)),1);
 V by=V(_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(yy,BROAD(47)),1))+_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(yy,BROAD(167)),1);idx=((pair*BROAD(4)+sign)*BROAD(9)+bx*BROAD(3)+by)*BROAD(NPART);
 auto res=ctx-sign*BROAD(120); if constexpr(NPART>1){auto groups=V((__m256i)((__v8si)res.v/(120/NPART)));idx+=groups;res-=groups*BROAD(120/NPART);}
 m=(m&BROAD(~511u))|res;
#endif
#ifdef PLANE
 alignas(32) int hints[8];_mm256_store_si256((__m256i*)hints,_mm256_maskz_mov_epi32(valid,idx));for(int k=0;k<8;++k)_mm_prefetch((const char*)(plane::data+hints[k]),_MM_HINT_T0);
#endif
 valid&=~same;
 return {m,_mm256_maskz_mov_epi32(valid,idx),(charge+((lx+ly)&BROAD(16383))),255^valid};
#endif
}
#ifdef STAGE2
AVT static inline void pref2(VRegs&v){
 V w=G(records779,v.idx),ctx=V(v.m)&BROAD(511),cell=_mm256_srli_epi32(v.m,9)&BROAD(1023);
#ifdef FASTVALID
 V d=_mm256_srli_epi32(ctx*BROAD(547),16);
#else
 V d=V(_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(ctx,BROAD(119)),1))+_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(ctx,BROAD(239)),1)+_mm256_maskz_set1_epi32(_mm256_cmpgt_epi32_mask(ctx,BROAD(359)),1);
#endif
 auto a=(d*BROAD(2048)+(_mm256_srli_epi32(w,10)&BROAD(2047)))*BROAD(552)+cell;
 auto id=d*BROAD(256)+(_mm256_srli_epi32(w,22)&BROAD(255));
#ifdef SUBCURVE
 id=id*BROAD(4)+(V(_mm256_srli_epi32(w,21)&BROAD(1))|(_mm256_srli_epi32(w,29)&BROAD(2)));
 const int16_t* bt=subcurve::curves;
#else
 const int16_t* bt=second779;
#endif
 auto b=id*BROAD(552)+cell;v.word=w.v;v.ai=a.v;v.bi=b.v;
 alignas(32) int ai[8],bi[8];_mm256_store_si256((__m256i*)ai,a);_mm256_store_si256((__m256i*)bi,b);
 for(int i=0;i<8;i++){_mm_prefetch((const char*)(first779+ai[i]),_MM_HINT_T0);_mm_prefetch((const char*)(bt+bi[i]),_MM_HINT_T0);}
}
#endif

#include "aqbatch.inc"
AVT static inline void resolve(const VRegs&v,int*out,const int*x,const int*y){aqbatch::resolve8(v,out,x,y); }
#undef BROAD
#undef G
}
