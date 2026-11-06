#pragma once

#include <algorithm>
#include <cstdlib>

// Fixed-map learning inputs; the detour field measures grid geometry.
static void geometry614(const float* x, float* z) {
    const int ax = int(x[28]), ay = int(x[29]);
    const int tx = int(x[30]), ty = int(x[31]);
    const int cx = (tx - 14 * (ty % 100 < 50 && tx >= 90)) -
                   (ax - 14 * (ay % 100 < 50 && ax >= 90));
    z[0] = float((cx % 10 + 10) % 10);
    z[1] = float(std::abs(cx) % 10);
    z[2] = float(std::abs(cx) / 10);
    z[3] = float(cx < 0);
    z[4] = float(ax % 10);
    z[5] = float(tx % 10);
    z[6] = float(ay % 12);
    z[7] = float(ty % 12);
    for (unsigned j = 8; j < 16; ++j) z[j] = 0;
    static constexpr int sites[] = {9, 19, 33, 39, 45, 51, 57, 63, 69,
                                    95, 99, 105, 111, 117};
    static constexpr int groups[] = {1, 1, 0, 1, 1, 1, 2, 0, 1,
                                     2, 3, 0, 1, 0};
    const int lowx = std::min(ax, tx), highx = std::max(ax, tx);
    const int lowy = std::min(ay, ty), highy = std::max(ay, ty);
    for (unsigned i = 0; i < 14; ++i)
        z[8 + groups[i]] += float(lowx <= sites[i] && sites[i] < highx);
    for (int site = 49; site < 549; site += 100)
        z[12] += float(lowy <= site && site < highy);
    if (lowx < 76 && highx > 89) {
        for (int lower = 0; lower <= 500; lower += 100) {
            const int upper = lower + 49;
            z[13] += float(lowy <= upper && highy >= lower);
            if (lowy >= lower && highy <= upper) {
                int steps = 10000;
                if (lower > 0) steps = std::min(steps, lowy - lower + 1);
                if (upper < 549) steps = std::min(steps, upper + 1 - highy);
                z[14] = float(2 * steps);
            }
        }
    }
    z[15] = float(std::abs(tx - ax) / 10 - std::abs(cx) / 10);
}
