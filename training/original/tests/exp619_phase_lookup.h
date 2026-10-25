#pragma once

extern "C" const unsigned char exp619_codes[];
static const unsigned char* phaseCodes619;
static const int8_t* phaseLevels619;

static void initializePhaseCodes619(const unsigned char* bytes = exp619_codes) {
    require(std::memcmp(bytes, "EX619P01", 8) == 0, "phase code magic");
    const auto* shape = reinterpret_cast<const uint32_t*>(bytes + 8);
    require(shape[0] == 59904 && shape[1] == 480 && shape[2] == 16, "phase code shape");
    phaseCodes619 = bytes + 64;
    phaseLevels619 = reinterpret_cast<const int8_t*>(bytes + 32);
    require(phaseLevels619[0] == 0, "phase zero code");
}

static inline unsigned phaseByte619(unsigned pair, unsigned context) {
    return pair * 240 + (context >> 1);
}

static inline int phaseCorrection619(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    if (qx + qy <= 3) return 0;
    const unsigned packed = phaseCodes619[phaseByte619(pair, context)];
    return phaseLevels619[(packed >> (4 * (context & 1))) & 15];
}
