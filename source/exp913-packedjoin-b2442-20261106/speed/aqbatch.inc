// G2 only. Frozen tables are read at the same indices as physical(). The ordinary path has zero raw event correction.
namespace aqbatch {
#ifdef AQPROBE
static int profileMode=0;
#endif
static int xpre[121],ypre[551],areaBand[3001],slope[53],head[4][552];
static int32_t b0[sizeof(aqfar::gm0)/2],b1[sizeof(aqfar::gm1)/2];
#ifdef AQFOUR
static int xside[120],yhalf[550],b2[sizeof(aqfar::gm2)/2],b3[sizeof(aqfar::gm3)/2];
#endif
static void init(){
#ifdef AQFOUR
 for(int i=0;i<120;i++)xside[i]=(i>=76)+(i>=90);for(int i=0;i<550;i++)yhalf[i]=i%100/50;
 for(size_t i=0;i<sizeof(b2)/sizeof(*b2);i++)b2[i]=aqfar::gm2[i];for(size_t i=0;i<sizeof(b3)/sizeof(*b3);i++)b3[i]=aqfar::gm3[i];
#endif
#ifdef AQPROBE
 auto env=std::getenv("AQ_PROBE");profileMode=env?std::atoi(env):0;aqfar::maskProfile=profileMode;
#endif
 for(int x=0;x<=120;x++)xpre[x]=std::min(x,16)|(std::clamp(x-76,0,14)<<16);
 for(int y=0;y<=550;y++)ypre[y]=std::min(y,100)|((y/100*50+std::min(y%100,50))<<16);
 for(int i=0;i<=3000;i++)areaBand[i]=aqfar::band(i,1,14,70,300,700,1500,3000);
 for(int i=-26;i<=26;i++)slope[26+i]=aqfar::band(i,-25,-15,-9,-5,-2,0,1,3,6,10,16,26);
 for(int d=0;d<4;d++)for(int j=0;j<552;j++){
  int q=j/46,p=j%46,u=aqfar::band(q,1,2,4,7),v=aqfar::band(p,1,2,4,7,12,21,32);
  head[d][j]=(u*8+v)|((u*4+d)<<8)|((8*std::min(q,4)+std::min(p,7))<<16)|((q<5&&p<8)<<23);
 }
 for(size_t k=0;k<sizeof(b0)/sizeof(*b0);k++)b0[k]=aqfar::gm0[k];for(size_t k=0;k<sizeof(b1)/sizeof(*b1);k++)b1[k]=aqfar::gm1[k];
}
ATTRV static inline void resolve8(const VRegs& v,int*out,const int* x,const int*y){
 V m=v.m,ctx=m&BROAD(511),cell=_mm256_srli_epi32(m,9)&BROAD(1023),d=_mm256_srli_epi32(ctx*BROAD(547),16);
#ifdef AQPROBE
 if(profileMode==1 || profileMode>=4){_mm256_storeu_si256((__m256i*)out,V(_mm256_srli_epi32(m,19))+V(v.fee));return;}
#endif
 V h=G(head,d*BROAD(552)+cell);
 alignas(32) int hd[8],key[8],cj[8],dr[8],yv[8]{},recent[8]{},slopeRaw[8]{};
 _mm256_store_si256((__m256i*)hd,h);_mm256_store_si256((__m256i*)key,v.idx);_mm256_store_si256((__m256i*)cj,cell);_mm256_store_si256((__m256i*)dr,d);
 for(int i=0;i<8;i++){
  if(v.exceptional>>i&1)continue;unsigned k=key[i],s=k/138240,id=k-s*138240,j=cj[i],di=dr[i]; 
#ifdef AQSMALL7
  const auto* p=aqfar::locate(k);
#else
  const auto* p=aqfar::jointSlabs[s]+size_t(60)*id;
#endif
  uint16_t low;memcpy(&low,p,2);
  unsigned n=(hd[i]>>16)&63;const auto* ds=p+2;
#ifdef AQPROBE
  if(profileMode==2){yv[i]=(low&32768)?near40::raw(k,n):int(low)-8192+ds[n];continue;}
#endif
#ifdef AQSMALL7
  slopeRaw[i]=p[60];int bb=aqfar::baseFlat(p);unsigned sh=p[58];recent[i]=aqfar::nearFlat(p,n,bb,sh);
  yv[i]=(hd[i]&(1<<23))?recent[i]:aqfar::responseDot(p,bb,sh,di,j);
#else
  if(__builtin_expect(!(low&32768),true)){
   int c=int(low)-8192;recent[i]=c+ds[n];slopeRaw[i]=int(ds[23])-int(ds[21]);
   if(hd[i]&(1<<23))yv[i]=recent[i];
   else{auto& f=*reinterpret_cast<const aqfar::FarRow*>(p+42);
    if(__builtin_cpu_supports("avx512vbmi"))yv[i]=aqfar::responsePermute(ds,c,f,di,j);else yv[i]=aqfar::responseSparse(ds,c,f,di,j);}
  }else{int16_t z[40];near40::load40(k,z);recent[i]=z[n];slopeRaw[i]=z[23]-z[21];yv[i]=aqfar::storedResponse(z,s,id,di,j);}
#endif
 }
#ifdef AQPROBE
 if(profileMode==2||profileMode==3){_mm256_storeu_si256((__m256i*)out,V(_mm256_max_epi32(BROAD(0),V(_mm256_srli_epi32(m,19))+V(_mm256_load_si256((__m256i*)yv))))+V(v.fee));return;}
#endif
 auto sx=even(x),tx=odd(x),sy=even(y),ty=odd(y);
 // An entire invalid group is repaired by the caller. Mask before any prefix gather for that group.
 if(v.exceptional==255){return;}
 auto DX=G(xpre,V(_mm256_max_epi32(sx,tx))+BROAD(1))-G(xpre,_mm256_min_epi32(sx,tx));
 auto DY=G(ypre,V(_mm256_max_epi32(sy,ty))+BROAD(1))-G(ypre,_mm256_min_epi32(sy,ty));
 auto ar=G(areaBand,_mm256_min_epi32(_mm256_madd_epi16(DX,DY),BROAD(3000)));
 auto tr=V(_mm256_srli_epi32(m,19));V nom=_mm256_max_epi32(BROAD(0),tr+V(_mm256_load_si256((__m256i*)yv)));
 auto delta=nom-tr-V(_mm256_load_si256((__m256i*)recent));auto dev=G(slope,_mm256_min_epi32(_mm256_max_epi32(delta,BROAD(-26)),BROAD(26))+BROAD(26));
#ifdef AQSMALL7
 V ss=_mm256_load_si256((__m256i*)slopeRaw);
#else
 auto ss=G(slope,_mm256_min_epi32(_mm256_max_epi32(_mm256_load_si256((__m256i*)slopeRaw),BROAD(-26)),BROAD(26))+BROAD(26));
#endif
 auto corr=G(b0,dev*BROAD(320)+ar*BROAD(40)+(h&BROAD(63)))+G(b1,dev*BROAD(260)+ss*BROAD(20)+(_mm256_srli_epi32(h,8)&BROAD(31)));
#ifdef AQFOUR
 V vbin=h&BROAD(7),side=(G(xside,sx)*BROAD(3)+G(xside,tx))*BROAD(4)+G(yhalf,sy)*BROAD(2)+G(yhalf,ty);
#ifdef AQEV
 V normal=_mm256_maskz_set1_epi32((~v.eventmask)&255,1);
#else
 V normal=BROAD(1);
#endif
 corr+=G(b2,((dev*BROAD(8)+vbin)*BROAD(2)+normal)*BROAD(4)+d)+G(b3,(ar*BROAD(8)+vbin)*BROAD(36)+side);
#endif
 auto round=_mm256_cvtps_epi32(_mm256_mul_ps(_mm256_cvtepi32_ps(corr),_mm256_set1_ps(1.f/32)));
 _mm256_storeu_si256((__m256i*)out,nom+V(v.fee)+round);
}
}
