// Eight endpoints (four complete requests) decoded together; an abnormal lane reuses the scalar parser.
static uint64_t shuffleMap[256],shapeMap[256],portKey[16384];
static uint32_t portId[16384];
static constexpr uint64_t hm=0xa0cc82c49d6d9441ull;
static void initVector(){
 for(int j=0;j<256;++j){int a=0,b=0;while(a<4&&(j>>a&1))++a;if(a<1||a>3)continue;while(b<4&&(j>>(a+b+1)&1))++b;if(b<1||b>3)continue;
  unsigned char sh[8];memset(sh,128,8);for(int k=0;k<a;k++)sh[3-a+k]=k;for(int k=0;k<b;k++)sh[7-b+k]=a+1+k;
#ifdef FUSEPARSE
 sh[0]|=(a<<4);sh[1]|=(a+1+b)<<4;
#endif
 memcpy(shuffleMap+j,sh,8);shapeMap[j]=unsigned((a+1+b)*8)<<8|unsigned(a*8);
 }
 for(int p=0;p<496;p++){auto s=arch.portName(p);uint64_t u=0;memcpy(&u,s.data(),s.size());unsigned i=(u^(u>>27))*hm>>50;require(portKey[i]==0,"port fingerprint collision");portKey[i]=u|uint64_t(p)<<55;portId[i]=p;}
#ifdef GUARD_LITE
 // 0 has hash 0. Fingerprint 1 hashes away from bucket 0, so it can never match here.
 if(!portKey[0])portKey[0]=1;
 static_assert((uint64_t(1)*hm>>50)!=0);
#endif
}
#define ATTRV __attribute__((target("avx512f,avx512dq,avx512bw,avx512vl,avx512vbmi2,avx512vbmi,bmi2")))
ATTRV static inline unsigned parse4(unsigned n,const End* del,int *x,int *y,int*p){
#ifdef U16POS
 const auto ib=_mm256_cvtepu16_epi32(_mm_add_epi16(_mm_loadu_si128((const __m128i*)(del-1)),_mm_set1_epi16(1)));
 const auto ie=_mm256_cvtepu16_epi32(_mm_loadu_si128((const __m128i*)del));
#else
 const auto ib=_mm256_add_epi32(_mm256_loadu_si256((__m256i*)(del-1)),_mm256_set1_epi32(1));
 const auto ie=_mm256_loadu_si256((__m256i*)del);
#endif
 (void)n;
 auto span=_mm256_sub_epi32(ie,ib);if(_mm256_cmp_epu32_mask(span,_mm256_set1_epi32(12),_MM_CMPINT_LT))return 0;
 __m512i raw=_mm512_i32gather_epi64(ib,buf+4,1),tail=_mm512_i32gather_epi64(_mm256_sub_epi32(ie,_mm256_set1_epi32(8)),buf,1);
#ifdef CHECK_SCAN
 __mmask8 ok=prefix_ok?255:0;
#else
 __m256i delbytes=_mm256_i32gather_epi32((int*)buf,ie,1);
 __mmask8 ok=_mm256_cmpeq_epi32_mask(_mm256_and_si256(delbytes,_mm256_set1_epi32(255)),_mm256_setr_epi32(44,10,44,10,44,10,44,10));
 ok&=_mm256_cmpeq_epi32_mask(_mm256_i32gather_epi32((int*)buf,ib,1),_mm256_set1_epi32(0x5f425253));
 #endif
 __m512i digits=_mm512_sub_epi8(raw,_mm512_set1_epi8('0'));
 uint64_t dm=_mm512_cmple_epu8_mask(digits,_mm512_set1_epi8(9));__m512i did=_mm512_cvtepu8_epi64(_mm_cvtsi64_si128(dm));
 __m512i sm=_mm512_i64gather_epi64(did,shuffleMap,8);sm=_mm512_add_epi8(sm,_mm512_setr_epi64(0,0x0808080808080808ll,0,0x0808080808080808ll,0,0x0808080808080808ll,0,0x0808080808080808ll));
 auto num=_mm512_shuffle_epi8(digits,sm);num=_mm512_maddubs_epi16(num,_mm512_set1_epi32(0x00010a64));num=_mm512_madd_epi16(num,_mm512_set1_epi16(1));
 _mm256_storeu_si256((__m256i*)x,_mm512_cvtepi64_epi32(num));_mm256_storeu_si256((__m256i*)y,_mm512_cvtepi64_epi32(_mm512_srli_epi64(num,32)));
 const auto byte=_mm512_set1_epi64(255);auto hi=_mm512_srli_epi64(tail,56),q= _mm512_and_si512(_mm512_srli_epi64(tail,48),byte),z=_mm512_and_si512(_mm512_srli_epi64(tail,8),byte);
 __mmask8 net=_mm512_cmpeq_epi64_mask(hi,_mm512_set1_epi64(']')),longn=_mm512_cmpneq_epi64_mask(z,_mm512_set1_epi64('/')),longq=_mm512_cmpeq_epi64_mask(q,_mm512_set1_epi64('Q'));
 __m512i len=_mm512_mask_add_epi64(_mm512_set1_epi64(4),net,_mm512_set1_epi64(4),_mm512_set1_epi64(2));len=_mm512_mask_add_epi64(len,(net&longn)|(~net&longq),len,_mm512_set1_epi64(1));
 __m512i u=_mm512_srlv_epi64(tail,_mm512_slli_epi64(_mm512_sub_epi64(_mm512_set1_epi64(8),len),3));auto hash=_mm512_srli_epi64(_mm512_mullo_epi64(_mm512_xor_si512(u,_mm512_srli_epi64(u,27)),_mm512_set1_epi64(hm)),50);

#if defined(GUARD) && !defined(GUARD_LITE)
 ok&=_mm512_cmpneq_epi64_mask(u,_mm512_setzero_si512());
#endif
 auto key=_mm512_i64gather_epi64(hash,portKey,8);ok&=_mm512_cmpeq_epi64_mask(u,_mm512_and_si512(key,_mm512_set1_epi64((1ull<<55)-1)));
 _mm256_storeu_si256((__m256i*)p,_mm512_cvtepi64_epi32(_mm512_srli_epi64(key,55)));
#ifdef FUSEPARSE
 auto ox=_mm512_and_si512(_mm512_srli_epi64(sm,1),_mm512_set1_epi64(56)),oy=_mm512_and_si512(_mm512_srli_epi64(sm,9),_mm512_set1_epi64(56));
#else
 auto shape=_mm512_i64gather_epi64(did,shapeMap,8);auto ox=_mm512_and_si512(shape,byte),oy=_mm512_srli_epi64(shape,8);
#endif
 ok&=_mm512_cmpeq_epi64_mask(_mm512_and_si512(_mm512_srlv_epi64(raw,ox),byte),_mm512_set1_epi64('_'));
 ok&=_mm512_cmpeq_epi64_mask(_mm512_and_si512(_mm512_srlv_epi64(raw,oy),byte),_mm512_set1_epi64('/'));
 auto sl=_mm256_sub_epi32(ie,ib);auto expected=_mm512_add_epi64(_mm512_set1_epi64(5),_mm512_add_epi64(len,_mm512_srli_epi64(oy,3)));
 ok&=_mm256_cmpeq_epi32_mask(sl,_mm512_cvtepi64_epi32(expected));return unsigned(ok);
}
