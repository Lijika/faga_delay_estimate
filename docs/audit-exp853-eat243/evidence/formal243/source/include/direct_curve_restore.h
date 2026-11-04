#pragma once

#include <zstd.h>

extern "C" const unsigned char direct_exact_begin[];
extern "C" const unsigned char direct_keys_begin[];

static constexpr unsigned kDirectCurveCount = 33280;
static constexpr unsigned kDirectCurveCells = 552;
static constexpr size_t kDirectExactBytes = 2303669;
static constexpr uint32_t kDirectCurveMarker = 0x80000000u;
alignas(64) static int16_t direct_exact[kDirectCurveCount * kDirectCurveCells];
alignas(64) static uint32_t direct_old_words[kDirectCurveCount];

static void restoreDirectCurves() {
    const size_t written = ZSTD_decompress(
        direct_exact, sizeof(direct_exact), direct_exact_begin, kDirectExactBytes);
    require(!ZSTD_isError(written), ZSTD_getErrorName(written));
    require(written == sizeof(direct_exact), "direct curve restored length");
    const auto* keys = reinterpret_cast<const uint32_t*>(direct_keys_begin);
    for (unsigned row=0;row<kDirectCurveCount;++row) {
        const unsigned key=keys[row];
        require(key<59904*480 && !(records779[key]&kDirectCurveMarker), "direct curve key");
        direct_old_words[row]=records779[key];
        records779[key]=kDirectCurveMarker|row;
    }
}
