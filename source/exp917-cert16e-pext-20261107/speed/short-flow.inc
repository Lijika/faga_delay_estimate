// Each work item was admitted by X2F's frozen short-domain certificate.
namespace shortflow{
using namespace stripe;
struct Work {
 const int *q;
 unsigned d,S,T,ry,w,h0,h1,firstPos,secondPos,rr,leaf,base;
 bool phase,need0,need1;
 int result;
};
template<unsigned K>static inline void touchIndex(unsigned index){
 const unsigned start=(starts[K]/2+index*bits[K]/16)*2;
 __builtin_prefetch(bank::data(start),0,1);__builtin_prefetch(bank::data(start+4),0,1);
}
template<bool second>static inline unsigned address(unsigned h,unsigned x){
 if constexpr(!second)return bank::shortAt+160*h+4*(x/3);
 unsigned md=mdSecond[h];const auto* m=(second?change1:change0)[md&65535];
 uint64_t bits=~uint64_t(0)>>(63-(x&63));
 unsigned rank=x<64?__builtin_popcountll(m[0]&bits):__builtin_popcountll(m[0])+__builtin_popcountll(m[1]&bits);
 return bank::shortAt+direct0Bytes+2*((second?offsets1:offsets0)[h>>6]+(md>>16)+rank);
}
template<unsigned mode>static void resolve(Work *a,unsigned n){
 for(unsigned i=0;i<n;i++){
   auto& r=a[i];const int*q=r.q;int x=q[0],y=q[1];r.S=src[q[8]];r.T=dst[q[9]];
   r.d=disp[(q[2]-x+2)*5+q[3]-y+2];auto h=shortHead[(r.d*208+r.S)*288+r.T];
   const auto meta=place[120*y+x];r.w=meta.w;r.ry=meta.ry;r.phase=r.ry%100<50;
   const uint64_t bit=uint64_t(1)<<(x&63);const auto*b=support[h>>47];r.base=h&1023;
   r.need0=(b[x>>6]&bit)!=0;r.need1=(r.phase||y%100<50)&&(b[2+(x>>6)]&bit)!=0;
   r.h0=(h>>10)&262143;r.h1=(h>>28)&524287;
   if(r.need0)__builtin_prefetch(&quick0[r.h0][x],0,1);
   if(r.need1)__builtin_prefetch(mdSecond+r.h1,0,1);
   if(!(zeroRoot[r.w]&(1u<<r.d)))touchIndex<2>((r.w*13+r.d)*208+r.S);
 }
 for(unsigned i=0;i<n;i++){
   auto&r=a[i];r.rr=zeroRoot[r.w]&(1u<<r.d)?0:u32(134104,(r.w*13+r.d)*208+r.S);
   if(r.rr)touchIndex<3>(r.rr*18+r.T/16);
   if(r.need0){r.firstPos=quick0[r.h0][r.q[0]];if(r.firstPos==255)__builtin_prefetch(bank::data(address<false>(r.h0,r.q[0])),0,1);}
   if(r.need1){r.secondPos=address<true>(r.h1,r.q[0]);__builtin_prefetch(bank::data(r.secondPos),0,1);}
 }
 for(unsigned i=0;i<n;i++){
   auto&r=a[i];r.leaf=r.rr?u32(11490904,r.rr*18+r.T/16):0;
   if(r.leaf){unsigned at=starts[4]+3*((r.leaf*16+r.T%16)/2);__builtin_prefetch(bank::data(at),0,1);__builtin_prefetch(bank::data(at+2),0,1);}
 }
 for(unsigned i=0;i<n;i++){
   auto&r=a[i];auto q=r.q;unsigned v0=r.need0?(r.firstPos==255?stripe::delta<0>(r.h0,q[0]):r.firstPos):0, v1=r.need1?bank::u16(r.secondPos):0;
   unsigned val=v0==65535?65535:uint16_t(r.base+v0);unsigned v=r.phase?uint16_t(val+v1):val;
   if(r.leaf)v=uint16_t(v+u16(42285592,r.leaf*16+r.T%16));
   int dy=q[3]-q[1],fee=std::abs(hfee[q[1]]-hfee[q[3]]);int z;
   if(v!=65535&&unsigned(int(r.ry)+dy)<550)z=int(v)+fee-std::abs(hfee[r.ry]-hfee[int(r.ry)+dy]);
   else{if(q[1]%100<50)val=uint16_t(val+v1);z=val==65535?INT_MAX:int(val)+fee;}
   r.result=z==INT_MAX?INT_MAX:envcert::refine(q[0],q[1],q[8],q[2],q[3],q[9],z);
 }
}
}
