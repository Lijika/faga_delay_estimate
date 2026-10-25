#pragma once

#include <cstdlib>

static inline unsigned event679(int ax, int ay, int tx, int ty, bool forced,
                                int& bands, int& ends) {
    ends = int(ax >= 76 && ax <= 89) + int(tx >= 76 && tx <= 89);
    // Legal central SRBs occupy y=100*j+[50,99] on the frozen map.
    bands = ends == 2 ? std::abs(ay / 100 - ty / 100) : 0;
#ifdef EXP684_V_ONLY
    (void)forced;
    return bands > 0 ? 2u : 0u;
#else
    return forced ? 1u : (bands > 0 ? 2u : 0u);
#endif
}
