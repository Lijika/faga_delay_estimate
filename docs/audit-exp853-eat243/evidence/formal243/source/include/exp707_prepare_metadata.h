#pragma once

struct Port707 {
    int16_t source, target;
    uint16_t start, cycle;
    int8_t dx, dy;
    uint8_t sf, sl, tf, tl;
};
struct Motion707 { uint16_t coordinate, fee, line; };
static_assert(sizeof(Port707) == 14);
static_assert(sizeof(Motion707) == 6);
static Port707 ports707[496];
static Motion707 motion707[17040];
static int prefixX707[120], prefixY707[550];
static uint16_t horizontal707[550], vertical707[120];
static uint8_t blockMask707[550];
static int blockLeft707 = -1, blockRight707 = -1;

static inline int line707(int x, int y, int tx, int ty) {
    return std::abs(prefixX707[x] - prefixX707[tx]) +
           std::abs(prefixY707[y] - prefixY707[ty]);
}

static inline bool forced707(int ax, int ay, int tx, int ty) {
    return ((ax < blockLeft707 && tx > blockRight707) ||
            (tx < blockLeft707 && ax > blockRight707)) &&
           (blockMask707[ay] & blockMask707[ty]);
}

static void initialize707() {
    using namespace delayest;
    require(arch.resolverMatchesEmbedded() && arch.portCount() == 496,
            "compiled preparation architecture");
    for (int x = 0; x < 120; ++x) {
        prefixX707[x] = arch.lineDelayCrossing(Axis::Vertical, 0, x);
        vertical707[x] = uint16_t(550 * (x < 16 ? 0 : x >= 76 && x <= 89 ? 1 : 2));
    }
    for (int y = 0; y < 550; ++y) {
        prefixY707[y] = arch.lineDelayCrossing(Axis::Horizontal, 0, y);
        horizontal707[y] = uint16_t(120 * (2 * (y < 100) + (y % 100 < 50)));
    }
    unsigned bit = 0;
    for (const auto& b : arch.blocks()) {
        if (b.left <= 0 || b.right >= 119) continue;
        if (!bit) { blockLeft707 = b.left; blockRight707 = b.right; }
        require(bit < 8 && b.left == blockLeft707 && b.right == blockRight707,
                "compiled block horizontal bounds");
        for (int y = 0; y < 550; ++y)
            if (y >= b.lower && y <= b.upper) blockMask707[y] |= uint8_t(1u << bit);
        ++bit;
    }
    require(bit > 0, "compiled block mask");
    unsigned cells = 0;
    for (const auto& type : resolver_data::kTypes) {
        const unsigned width = type.horizontal ? 120 : 550;
        const unsigned count = width * (type.horizontal ? 4 : 3);
        for (unsigned j = 0; j < count; ++j) {
            const unsigned at = type.start + j;
            require(at < 17040, "compiled motion index");
            const auto c = resolver_data::kCells[at];
            if (c.coordinate == 65535) { motion707[at] = {65535, 0, 0}; continue; }
            const int* prefix = type.horizontal ? prefixX707 : prefixY707;
            require(c.coordinate < width, "compiled motion coordinate");
            const int l = std::abs(prefix[j % width] - prefix[c.coordinate]);
            const int fee = int(c.delay) - l;
            require(l >= 0 && l <= 65535 && fee >= 0 && fee <= 65535,
                    "compiled motion fee range");
            motion707[at] = {c.coordinate, uint16_t(fee), uint16_t(l)};
        }
        cells += count;
    }
    require(cells == 17040, "compiled motion coverage");
    for (int p = 0; p < 496; ++p) {
        auto& d = ports707[p];
        const int s = kSourceIndex[p], t = kTargetIndex[p], net = arch.netOfOutput(p);
        d.source = int16_t(s); d.target = int16_t(t); d.start = 65535;
        if (s >= 0) {
            d.sf = uint8_t(kSourceFamily[s]); d.sl = uint8_t(kSourceLane[s]);
            d.cycle = uint16_t(kCycles[s]);
        }
        if (t >= 0) { d.tf = uint8_t(kTargetFamily[t]); d.tl = uint8_t(kTargetLane[t]); }
        if (net >= 0) {
            const auto& n = arch.net(net);
            require(n.dx >= -127 && n.dx <= 127 && n.dy >= -127 && n.dy <= 127,
                    "compiled motion displacement");
            d.dx = int8_t(n.dx); d.dy = int8_t(n.dy);
            d.start = resolver_data::kTypes[resolver_data::kForward[net]].start;
        }
    }
}

// The caller has checked endpoint existence, just as in prepare596.
static inline bool first707(int sx, int sy, const Port707& d,
                            int& ax, int& ay, int& fee, int& firstLine) {
    ax = sx; ay = sy; fee = 0; firstLine = 0;
    if (d.start == 65535) return true;
    const unsigned index = d.start + (d.dx ? horizontal707[sy] + sx : vertical707[sx] + sy);
    const auto c = motion707[index];
    if (c.coordinate == 65535) return false;
    if (d.dx) ax = c.coordinate; else ay = c.coordinate;
    fee = c.fee; firstLine = c.line;
    return true;
}
