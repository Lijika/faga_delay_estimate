// Eight endpoints share the existing short-name grammar; unusual formats use parsePin580.
namespace parser {
static uint64_t shuffleMap[256],shapeMap[256],portKey[16384],portLength[16384];
static constexpr uint64_t hm=0xa0cc82c49d6d9441ull;
static void init(){
 for(int j=0;j<256;++j){
  int a=0,b=0;while(a<4&&(j>>a&1))++a;if(a<1||a>3)continue;
  while(b<4&&(j>>(a+b+1)&1))++b;if(b<1||b>3)continue;
  unsigned char sh[8];memset(sh,128,8);
  for(int k=0;k<a;k++)sh[3-a+k]=k;
  for(int k=0;k<b;k++)sh[7-b+k]=a+1+k;
  memcpy(shuffleMap+j,sh,8);
  shapeMap[j]=unsigned((a+1+b)*8)<<8|unsigned(a*8);
 }
 for(int p=0;p<496;p++){
  const auto& s=arch.portName(p);uint64_t u=0;
  require(s.size()>=4 && s.size()<=7,"cascade short port length");
  memcpy(&u,s.data(),s.size());require(!(u>>55),"cascade port key range");
  unsigned i=(u^(u>>27))*hm>>50;
  require(portLength[i]==0,"cascade port fingerprint collision");
  portKey[i]=u|uint64_t(p)<<55;portLength[i]=s.size();
 }
}
CASCADE857_TARGET static inline unsigned parse4(const unsigned* del,int*x,int*y,int*p){
 const auto ib=_mm256_add_epi32(_mm256_loadu_si256((const __m256i*)(del-1)),_mm256_set1_epi32(1));
 const auto ie=_mm256_loadu_si256((const __m256i*)del);
 const auto span=_mm256_sub_epi32(ie,ib);
 if(_mm256_cmp_epu32_mask(span,_mm256_set1_epi32(12),_MM_CMPINT_LT))return 0;
 const auto raw=_mm512_i32gather_epi64(ib,r4::buf+4,1);
 const auto tail=_mm512_i32gather_epi64(_mm256_sub_epi32(ie,_mm256_set1_epi32(8)),r4::buf,1);
 const auto delbytes=_mm256_i32gather_epi32((const int*)r4::buf,ie,1);
 __mmask8 ok=_mm256_cmpeq_epi32_mask(_mm256_and_si256(delbytes,_mm256_set1_epi32(255)),_mm256_setr_epi32(44,10,44,10,44,10,44,10));
 ok&=_mm256_cmpeq_epi32_mask(_mm256_i32gather_epi32((const int*)r4::buf,ib,1),_mm256_set1_epi32(0x5f425253));
 const auto digits=_mm512_sub_epi8(raw,_mm512_set1_epi8('0'));
 const uint64_t dm=_mm512_cmple_epu8_mask(digits,_mm512_set1_epi8(9));
 const auto did=_mm512_cvtepu8_epi64(_mm_cvtsi64_si128(dm));
 auto sm=_mm512_i64gather_epi64(did,shuffleMap,8);
 sm=_mm512_add_epi8(sm,_mm512_setr_epi64(0,0x0808080808080808ll,0,0x0808080808080808ll,0,0x0808080808080808ll,0,0x0808080808080808ll));
 auto num=_mm512_shuffle_epi8(digits,sm);
 num=_mm512_maddubs_epi16(num,_mm512_set1_epi32(0x00010a64));
 num=_mm512_madd_epi16(num,_mm512_set1_epi16(1));
 _mm256_storeu_si256((__m256i*)x,_mm512_cvtepi64_epi32(num));
 _mm256_storeu_si256((__m256i*)y,_mm512_cvtepi64_epi32(_mm512_srli_epi64(num,32)));
 const auto byte=_mm512_set1_epi64(255);
 const auto hi=_mm512_srli_epi64(tail,56);
 const auto q=_mm512_and_si512(_mm512_srli_epi64(tail,48),byte);
 const auto z=_mm512_and_si512(_mm512_srli_epi64(tail,8),byte);
 const __mmask8 net=_mm512_cmpeq_epi64_mask(hi,_mm512_set1_epi64(']'));
 const __mmask8 longn=_mm512_cmpneq_epi64_mask(z,_mm512_set1_epi64('/'));
 const __mmask8 longq=_mm512_cmpeq_epi64_mask(q,_mm512_set1_epi64('Q'));
 auto len=_mm512_mask_add_epi64(_mm512_set1_epi64(4),net,_mm512_set1_epi64(4),_mm512_set1_epi64(2));
 len=_mm512_mask_add_epi64(len,(net&longn)|(~net&longq),len,_mm512_set1_epi64(1));
 const auto u=_mm512_srlv_epi64(tail,_mm512_slli_epi64(_mm512_sub_epi64(_mm512_set1_epi64(8),len),3));
 const auto hash=_mm512_srli_epi64(_mm512_mullo_epi64(_mm512_xor_si512(u,_mm512_srli_epi64(u,27)),_mm512_set1_epi64(hm)),50);
 const auto key=_mm512_i64gather_epi64(hash,portKey,8);
 ok&=_mm512_cmpeq_epi64_mask(u,_mm512_and_si512(key,_mm512_set1_epi64((1ull<<55)-1)));
 ok&=_mm512_cmpeq_epi64_mask(len,_mm512_i64gather_epi64(hash,portLength,8));
 _mm256_storeu_si256((__m256i*)p,_mm512_cvtepi64_epi32(_mm512_srli_epi64(key,55)));
 const auto shape=_mm512_i64gather_epi64(did,shapeMap,8);
 const auto ox=_mm512_and_si512(shape,byte),oy=_mm512_srli_epi64(shape,8);
 ok&=_mm512_cmpeq_epi64_mask(_mm512_and_si512(_mm512_srlv_epi64(raw,ox),byte),_mm512_set1_epi64('_'));
 ok&=_mm512_cmpeq_epi64_mask(_mm512_and_si512(_mm512_srlv_epi64(raw,oy),byte),_mm512_set1_epi64('/'));
 const auto expected=_mm512_add_epi64(_mm512_set1_epi64(5),_mm512_add_epi64(len,_mm512_srli_epi64(oy,3)));
 ok&=_mm256_cmpeq_epi32_mask(span,_mm512_cvtepi64_epi32(expected));
 return unsigned(ok);
}
}
