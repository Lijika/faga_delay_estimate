#pragma once

static inline int dot64_595(const int8_t* a, const int8_t* b) {
    const __m128i zero = _mm_setzero_si128();
    __m128i lo = zero, hi = zero;
    for (unsigned k = 0; k < 64; k += 16) {
        const __m128i av = _mm_loadu_si128(reinterpret_cast<const __m128i*>(a + k));
        const __m128i bv = _mm_loadu_si128(reinterpret_cast<const __m128i*>(b + k));
        const __m128i as = _mm_cmpgt_epi8(zero, av), bs = _mm_cmpgt_epi8(zero, bv);
        lo = _mm_add_epi32(lo, _mm_madd_epi16(_mm_unpacklo_epi8(av, as), _mm_unpacklo_epi8(bv, bs)));
        hi = _mm_add_epi32(hi, _mm_madd_epi16(_mm_unpackhi_epi8(av, as), _mm_unpackhi_epi8(bv, bs)));
    }
    __m128i sum = _mm_add_epi32(lo, hi);
    sum = _mm_add_epi32(sum, _mm_srli_si128(sum, 8));
    sum = _mm_add_epi32(sum, _mm_srli_si128(sum, 4));
    return _mm_cvtsi128_si32(sum);
}

template <unsigned Group>
static inline double geometryPart595(unsigned row, unsigned local) {
    constexpr unsigned rank = Group ? 64 : 512;
    constexpr unsigned blocks = rank / 64;
    const auto& p = parts582[Group];
    const auto* a = p.left + uint64_t(row) * rank;
    const auto* b = p.right + uint64_t(local) * rank;
    const auto* sa = p.left_scale + uint64_t(row) * blocks;
    const auto* sb = p.right_scale + uint64_t(local) * blocks;
    double total = 0.;
    for (unsigned group = 0; group < blocks; ++group)
        total += double(dot64_595(a + group * 64, b + group * 64)) * double(sa[group]) * double(sb[group]);
    return total;
}

static inline double geometry(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    const unsigned g = qx + qy > 3;
    const unsigned local = local582(context, qx, qy, g);
    return g ? geometryPart595<1>(pair + (context / 120) * 59904, local) :
               geometryPart595<0>(pair, local);
}

template <unsigned Group>
static inline void prefetchPart595(unsigned row, unsigned local) {
    constexpr unsigned rank = Group ? 64 : 512;
    constexpr unsigned blocks = rank / 64;
    const auto& p = parts582[Group];
    for (unsigned k = 0; k < rank; k += 64) {
        _mm_prefetch(reinterpret_cast<const char*>(p.left + uint64_t(row) * rank + k), _MM_HINT_T0);
        _mm_prefetch(reinterpret_cast<const char*>(p.right + uint64_t(local) * rank + k), _MM_HINT_T0);
    }
    _mm_prefetch(reinterpret_cast<const char*>(p.left_scale + uint64_t(row) * blocks), _MM_HINT_T0);
    _mm_prefetch(reinterpret_cast<const char*>(p.right_scale + uint64_t(local) * blocks), _MM_HINT_T0);
}

static inline void prefetchGeometry581(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    const unsigned g = qx + qy > 3;
    const unsigned local = local582(context, qx, qy, g);
    if (g) prefetchPart595<1>(pair + (context / 120) * 59904, local);
    else prefetchPart595<0>(pair, local);
}
