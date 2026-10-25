#pragma once

static unsigned eventRoute631(const float* x, bool split) {
    const int nx = int(x[8]) + int(x[6]), ny = int(x[9]) + int(x[7]);
    const unsigned ax = nx < 0 ? -nx : nx, ay = ny < 0 ? -ny : ny;
    const unsigned direction = 2 * (nx < 0) + (ny < 0);
    const unsigned route = 4 * direction + 2 * (ax >= 20) + (ay >= 24);
    const bool cross = (x[28] < 76 && x[30] > 89) || (x[30] < 76 && x[28] > 89);
    return split && route % 4 == 3 && cross ? 16 + direction : route;
}

static void routeSelfCheck631() {
    for (int d = 0; d < 4; ++d) {
        float x[53]{};
        x[6] = 10;
        x[8] = (d >= 2 ? -20 : 20) - x[6];
        x[9] = d & 1 ? -24 : 24;
        x[28] = 75; x[30] = 90;
        require(eventRoute631(x, true) == unsigned(16 + d), "cross route");
        require(eventRoute631(x, false) == unsigned(4 * d + 3), "old route");
        x[28] = 76;
        require(eventRoute631(x, true) == unsigned(4 * d + 3), "left boundary");
        x[28] = 75; x[30] = 89;
        require(eventRoute631(x, true) == unsigned(4 * d + 3), "right boundary");
        x[30] = 90; x[8] = (d >= 2 ? -19 : 19) - x[6];
        require(eventRoute631(x, true) == unsigned(4 * d + 1), "near axis");
    }
}
