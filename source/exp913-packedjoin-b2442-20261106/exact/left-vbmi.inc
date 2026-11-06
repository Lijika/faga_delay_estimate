// A plan's first four byte indices select its near references, the next four its far codes.
// Indices live in the low 64 bits. A zeroed upper vector is unnecessary since only 8 lanes contribute.
struct alignas(32) DecodePlan {float w[4]; uint64_t offsets; float additive; uint32_t mask;};
static_assert(sizeof(DecodePlan)==32);
static DecodePlan decPlan[4][552];
static void initDecoder(){
 for(unsigned d=0;d!=4;++d)for(unsigned j=0;j!=552;++j){
  const auto &q=sparsePlan[d][j];auto &v=decPlan[d][j];
  for(unsigned k=0;k<SPARSE_COUNT;++k){
   v.offsets|=uint64_t(q.nearIx[k]+2)<<(8*k);
   v.offsets|=uint64_t(q.farIx[k]+44)<<(8*(4+k));
   v.w[k]=q.weight[k];
  }
  v.mask=q.mask;v.additive=q.bias;
 }
}
__attribute__((target("avx512f,avx512bw,avx512vl,avx512vbmi,sse4.1")))
static inline int vbResponse(const uint8_t* row,int base,const FarRow& far,unsigned d,unsigned j){
 const auto& q=decPlan[d][j];
 auto ix=_mm512_castsi128_si512(_mm_cvtsi64_si128((long long)q.offsets));
 // A VBMI byte-permute acts as a four-way, intra-cache-line lookup with the record as dictionary.
 auto v=_mm512_castsi512_si128(_mm512_permutexvar_epi8(ix,_mm512_loadu_si512(row)));
 auto n=_mm_slli_epi32(_mm_add_epi32(_mm_set1_epi32(base),_mm_cvtepu8_epi32(v)),3);
 auto f=_mm_add_epi32(_mm_set1_epi32(((int(far.header)>>4)-2048)*8),
    _mm_sll_epi32(_mm_cvtepu8_epi32(_mm_srli_si128(v,4)),_mm_cvtsi32_si128(far.header&7)));
 auto z=_mm_mask_mov_epi32(n,q.mask,_mm_add_epi32(f,_mm_and_si128(n,_mm_set1_epi32(-int((far.header>>3)&1)))));
 auto t=_mm_mul_ps(_mm_cvtepi32_ps(z),_mm_load_ps(q.w));
 auto sum=_mm_add_ss(t,_mm_shuffle_ps(t,t,0x55));sum=_mm_add_ss(sum,_mm_shuffle_ps(t,t,0xaa));sum=_mm_add_ss(sum,_mm_shuffle_ps(t,t,0xff));
 return _mm_cvtss_si32(_mm_add_ss(sum,_mm_set_ss(q.additive)));
}
