#pragma once

#include "curve_origin654.h"
extern "C" const unsigned char exp619_codes[];
static const unsigned char* phaseCodes619;
static const unsigned char* phaseCurves654;

static void initializePhaseCodes619(const unsigned char* bytes = exp619_codes) {
    require(std::memcmp(bytes, "EX654C01", 8) == 0, "byte distance curve magic");
    const auto* shape = reinterpret_cast<const uint32_t*>(bytes + 8);
    require(shape[0] == 59904 && shape[1] == 4 && shape[2] == 120 &&
            shape[3] == 542 && shape[4] == 256 && shape[5] == 1 &&
            static_cast<int32_t>(shape[6]) == kCurveOrigin654, "byte distance curve shape");
    phaseCodes619 = bytes + 64;
    phaseCurves654 = phaseCodes619 + 59904 * 480;
}

static inline unsigned phaseByte619(unsigned pair, unsigned context) {
    return pair * 480 + context;
}

static inline int phaseCorrection619(unsigned pair, unsigned context, unsigned qx, unsigned qy) {
    if (qx + qy <= 3) return 0;
    const unsigned code = phaseCodes619[phaseByte619(pair, context)];
    const unsigned local = local582(0, qx, qy, 1);
    return int(phaseCurves654[((context / 120) * 256 + code) * 542 + local]) + kCurveOrigin654;
}
