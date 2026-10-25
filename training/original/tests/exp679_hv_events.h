#pragma once

#include <algorithm>

static inline unsigned event679(int ax, int ay, int tx, int ty, bool forced,
                                int& bands, int& ends) {
    ends = int(ax >= 76 && ax <= 89) + int(tx >= 76 && tx <= 89);
    bands = 0;
    const int low = std::min(ay, ty), high = std::max(ay, ty);
    // Both central endpoints are the only production users of the band count.
    if (ends == 2)
        for (int lower = 0; lower <= 500; lower += 100)
            bands += low < lower && high > lower + 49;
    return forced ? 1u : (bands > 0 ? 2u : 0u);
}
