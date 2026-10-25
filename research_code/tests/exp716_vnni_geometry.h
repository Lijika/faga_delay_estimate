#pragma once
#include <immintrin.h>

extern int16_t sums716[298560];

static void initializeSums716() {
    unsigned at=0;
    for (unsigned g=0;g<2;++g) {
        const unsigned count=g ? 260160 : 4800;
        for (unsigned local=0;local<count;++local)
            for (unsigned group=0;group<parts582[g].blocks;++group) {
                const auto* b=parts582[g].right+uint64_t(local)*parts582[g].rank+64*group;
                int sum=0;
                for (unsigned j=0;j<64;++j) sum+=b[j];
                require(sum>=-8192 && sum<=8128,"VNNI signed block sum");
                sums716[at++]=int16_t(sum);
            }
    }
    require(at==298560,"VNNI block count");
}

static inline int dot64_595(const int8_t* a, const int8_t* b, int sumB) {
#if EXP716_WIDTH == 256
    __m256i accum=_mm256_setzero_si256();
    for (unsigned j=0;j<64;j+=32) {
        const auto u=_mm256_xor_si256(_mm256_loadu_si256(
            reinterpret_cast<const __m256i*>(a+j)),_mm256_set1_epi8(char(0x80)));
        accum=_mm256_dpbusd_epi32(accum,u,_mm256_loadu_si256(
            reinterpret_cast<const __m256i*>(b+j)));
    }
    __m128i sum=_mm_add_epi32(_mm256_castsi256_si128(accum),_mm256_extracti128_si256(accum,1));
    sum=_mm_add_epi32(sum,_mm_srli_si128(sum,8));
    sum=_mm_add_epi32(sum,_mm_srli_si128(sum,4));
    return _mm_cvtsi128_si32(sum)-128*sumB;
#else
    const auto u=_mm512_xor_si512(_mm512_loadu_si512(a),_mm512_set1_epi8(char(0x80)));
    const auto accum=_mm512_dpbusd_epi32(_mm512_setzero_si512(),u,_mm512_loadu_si512(b));
    return _mm512_reduce_add_epi32(accum)-128*sumB;
#endif
}

template <unsigned Group>
static inline double geometryPart595(unsigned row, unsigned local) {
    constexpr unsigned rank=Group ? 64 : 512, blocks=rank/64;
    const auto& p=parts582[Group];
    const auto* a=p.left+uint64_t(row)*rank;
    const auto* b=p.right+uint64_t(local)*rank;
    const auto* sa=p.left_scale+uint64_t(row)*blocks;
    const auto* sb=p.right_scale+uint64_t(local)*blocks;
    double total=0.;
    for (unsigned group=0;group<blocks;++group)
        total+=double(dot64_595(a+group*64,b+group*64,
            sums716[(Group ? 38400 : 0)+local*blocks+group]))*double(sa[group])*double(sb[group]);
    return total;
}
