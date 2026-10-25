#pragma once

extern "C" const unsigned char exp619_codes[];
static const unsigned char* phaseCodes619;
static const int16_t* phaseCurves652;

static void initializePhaseCodes619(const unsigned char* bytes = exp619_codes) {
    require(std::memcmp(bytes, "EX651C01", 8) == 0, "distance curve magic");
    const auto* shape = reinterpret_cast<const uint32_t*>(bytes + 8);
    require(shape[0] == 59904 && shape[1] == 4 && shape[2] == 120 &&
            shape[3] == 542 && shape[4] == 256 && shape[5] == 2,
            "distance curve shape");
    phaseCodes619 = bytes + 64;
    phaseCurves652 = reinterpret_cast<const int16_t*>(phaseCodes619 + 59904 * 480);
}

static inline unsigned phaseByte619(unsigned pair, unsigned context) {
    return pair * 480 + context;
}

static inline int phaseCorrection619(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    if (qx + qy <= 3) return 0;
    const unsigned code = phaseCodes619[phaseByte619(pair, context)];
    const unsigned local = local582(0, qx, qy, 1);
    return phaseCurves652[((context / 120) * 256 + code) * 542 + local];
}
