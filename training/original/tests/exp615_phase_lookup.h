#pragma once

extern "C" const unsigned char exp615_codes[];
static const unsigned char* phaseCodes615;

static void initializePhaseCodes615() {
    require(std::memcmp(exp615_codes, "EX615P01", 8) == 0, "phase code magic");
    const auto* dimensions = reinterpret_cast<const uint32_t*>(exp615_codes + 8);
    require(dimensions[0] == 59904 && dimensions[1] == 480, "phase code dimensions");
    phaseCodes615 = exp615_codes + 16;
}

static inline uint64_t phaseByte615(unsigned pair, unsigned context) {
    return (5 * (uint64_t(pair) * 480 + context)) >> 3;
}

static inline int phaseCorrection615(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    if (qx + qy <= 3) return 0;
    const uint64_t bit = 5 * (uint64_t(pair) * 480 + context), byte = bit >> 3;
    const unsigned value = unsigned(phaseCodes615[byte]) |
                           (unsigned(phaseCodes615[byte + 1]) << 8);
    return 2 * (int((value >> (bit & 7)) & 31) - 16);
}
