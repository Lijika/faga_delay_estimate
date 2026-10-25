#pragma once

struct Part582 {
    const int8_t *left, *right;
    const float *left_scale, *right_scale;
    unsigned rank, block, blocks;
};
static Part582 parts582[2];
static const int16_t* center;

static void initializeGeometry582() {
    require(std::memcmp(exp579_geometry, "EX582Q01", 8) == 0, "INT8 geometry magic");
    const auto* meta = reinterpret_cast<const uint32_t*>(exp579_geometry + 8);
    const auto* at = exp579_geometry + 64;
    center = reinterpret_cast<const int16_t*>(at);
    at += 59904 * 2;
    for (unsigned g = 0; g < 2; ++g) {
        auto& p = parts582[g];
        p.rank = g == 0 ? 192 : 96;
        p.block = EXP582_BLOCK ? std::min(unsigned(EXP582_BLOCK), p.rank) : p.rank;
        p.blocks = (p.rank + p.block - 1) / p.block;
        const unsigned count = g == 0 ? 4800 : 260160;
        require(meta[g] == p.rank && meta[2 + g] == p.block && meta[4 + g] == count,
                "INT8 geometry dimensions");
        p.left = reinterpret_cast<const int8_t*>(at); at += 59904 * p.rank;
        p.right = reinterpret_cast<const int8_t*>(at); at += uint64_t(count) * p.rank;
        p.left_scale = reinterpret_cast<const float*>(at); at += 59904 * p.blocks * 4;
        p.right_scale = reinterpret_cast<const float*>(at); at += uint64_t(count) * p.blocks * 4;
    }
    require(uint64_t(at - exp579_geometry) == kGeometryBytes, "INT8 geometry length");
}

static inline unsigned local582(unsigned context, unsigned qx, unsigned qy, unsigned g) {
    const unsigned before = qx < 4 ? (qx + 1) * (8 - qx) / 2 : 10;
    return g == 0 ? context * 10 + qx * (9 - qx) / 2 + qy :
                    context * 542 + qx * 46 + qy - before;
}

static inline double geometry(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    const unsigned g = qx + qy > 3;
    const unsigned local = local582(context, qx, qy, g);
    const auto& p = parts582[g];
    const auto* a = p.left + uint64_t(pair) * p.rank;
    const auto* b = p.right + uint64_t(local) * p.rank;
    const auto* sa = p.left_scale + uint64_t(pair) * p.blocks;
    const auto* sb = p.right_scale + uint64_t(local) * p.blocks;
    double total = 0.;
    const __m128i zero = _mm_setzero_si128();
    for (unsigned group = 0; group < p.blocks; ++group) {
        __m128i lo = zero, hi = zero;
        const unsigned end = std::min((group + 1) * p.block, p.rank);
        for (unsigned k = group * p.block; k < end; k += 16) {
            const __m128i av = _mm_loadu_si128(reinterpret_cast<const __m128i*>(a + k));
            const __m128i bv = _mm_loadu_si128(reinterpret_cast<const __m128i*>(b + k));
            const __m128i as = _mm_cmpgt_epi8(zero, av), bs = _mm_cmpgt_epi8(zero, bv);
            lo = _mm_add_epi32(lo, _mm_madd_epi16(_mm_unpacklo_epi8(av, as), _mm_unpacklo_epi8(bv, bs)));
            hi = _mm_add_epi32(hi, _mm_madd_epi16(_mm_unpackhi_epi8(av, as), _mm_unpackhi_epi8(bv, bs)));
        }
        __m128i sum = _mm_add_epi32(lo, hi);
        sum = _mm_add_epi32(sum, _mm_srli_si128(sum, 8));
        sum = _mm_add_epi32(sum, _mm_srli_si128(sum, 4));
        total += double(_mm_cvtsi128_si32(sum)) * double(sa[group]) * double(sb[group]);
    }
    return total;
}

static inline void prefetchGeometry581(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    const unsigned g = qx + qy > 3;
    const unsigned local = local582(context, qx, qy, g);
    const auto& p = parts582[g];
    for (unsigned k = 0; k < p.rank; k += 64) {
        _mm_prefetch(reinterpret_cast<const char*>(p.left + uint64_t(pair) * p.rank + k), _MM_HINT_T0);
        _mm_prefetch(reinterpret_cast<const char*>(p.right + uint64_t(local) * p.rank + k), _MM_HINT_T0);
    }
    _mm_prefetch(reinterpret_cast<const char*>(p.left_scale + uint64_t(pair) * p.blocks), _MM_HINT_T0);
    _mm_prefetch(reinterpret_cast<const char*>(p.right_scale + uint64_t(local) * p.blocks), _MM_HINT_T0);
}
