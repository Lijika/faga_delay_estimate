namespace bills {
struct Job{
 int* out;int intrinsic;unsigned x,X,band,alpha,tag,priceF,priceB,ff,fb,axisSlab;
 const uint8_t* row;
};
static Job queue[1024];static unsigned n;
static inline void add(int* out,int nominal,int x,int y,int X,int Y,unsigned key,unsigned cell,unsigned tag,int distance){
 const bool atlas=distance<=12;
 if(!atlas&&!tag)return;
 auto& r=queue[n++];r.out=out;r.intrinsic=nominal;r.x=x;r.X=X;r.tag=tag;r.row=nullptr;
 unsigned pair=key/480,ctx=key%480;
 if(atlas){
  const int d=aqfar::atlas855::dispType[(X-x+12)*25+(Y-y+12)];
  r.alpha=aqfar::cold913::atlas+(d*208u+aqfar::atlas855::sm[pair/288])*288u+aqfar::atlas855::tm[pair%288];
  r.row=aqfar::atlas855::unpack+size_t(d)*7680;
  __builtin_prefetch(aqfar::cold913::data(r.alpha),0,1);
 }
 r.band=2u*(cell>=46)+(cell%46!=0);
 if(tag&15){r.ff=3*((pair/288*480+ctx)*16+(tag&15));__builtin_prefetch(aqfar::tariff::ids+r.ff,0,1);}
 if(tag>>4){r.fb=3*(((208+pair%288)*480+ctx)*16+(tag>>4));__builtin_prefetch(aqfar::tariff::ids+r.fb,0,1);}
}
static inline unsigned rowAt(unsigned a){
 uint32_t z;memcpy(&z,aqfar::tariff::ids+a,4);return z&0xffffffu;
}
static inline void finish(){
 using namespace aqfar::tariff;
 for(unsigned i=0;i<n;i++){auto&r=queue[i];
  if(r.row){unsigned code=aqfar::cold913::u8(r.alpha);r.axisSlab=code;__builtin_prefetch(r.row+2*((code&15)*120+r.x),0,1);__builtin_prefetch(r.row+2*(16+(code>>4))*120+2*r.x,0,1);}
  if(r.tag&15){r.ff=4*rowAt(r.ff)+r.band;__builtin_prefetch(words+r.ff,0,1);}
  if(r.tag>>4){r.fb=4*rowAt(r.fb)+r.band;__builtin_prefetch(words+r.fb,0,1);}
 }
 for(unsigned i=0;i<n;i++){auto&r=queue[i];
  if(r.row){int16_t a,b;unsigned z=r.axisSlab;memcpy(&a,r.row+2*((z&15)*120+r.x),2);memcpy(&b,r.row+2*((16+(z>>4))*120+r.x),2);*r.out+=2*std::max(0,int(a)+int(b));}
  if(r.tag&15){r.priceF=120*unsigned(words[r.ff])+r.x;__builtin_prefetch(price+r.priceF,0,1);}
  if(r.tag>>4){r.priceB=120*unsigned(words[r.fb])+r.X;__builtin_prefetch(price+r.priceB,0,1);}
 }
 for(unsigned i=0;i<n;i++){auto&r=queue[i];
  int delta=std::max(r.tag&15?int(price[r.priceF]):0,r.tag>>4?int(price[r.priceB]):0);
  if(delta>=8)*r.out=std::max(*r.out,r.intrinsic+delta);
 }
 n=0;
}
}
