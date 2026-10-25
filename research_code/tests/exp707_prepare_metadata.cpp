#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include "architecture.h"
#include "exp579-models.h"

static delayest::Architecture arch;
static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "%s\n", why); std::exit(1); }
}
#include "exp707_prepare_metadata.h"

int main() {
    arch.loadEmbedded();
    initialize707();
    uint64_t checked = 0, valid = 0;
    int maxBx = 0, maxBy = 0;
    for (int y = 0; y < 550; ++y) for (int x = 0; x < 120; ++x) {
        for (int n = 0; n < arch.netCount(); ++n) {
            ++checked;
            if (!arch.exists(x, y)) continue;
            const auto& net = arch.net(n);
            int ax, ay, fee, first;
            const bool ok = first707(x, y, ports707[net.from], ax, ay, fee, first);
            const auto old = arch.resolveNet(x, y, n);
            const auto walk = arch.referenceNetForAudit(x, y, n, false);
            assert(ok == old.valid && ok == walk.valid);
            if (!ok) continue;
            ++valid;
            assert(ax == old.x && ay == old.y && fee + first == old.delay);
            assert(ax == walk.x && ay == walk.y && fee + first == walk.delay);
            const int line = arch.lineDelayCrossing(delayest::Axis::Vertical, x, ax) +
                             arch.lineDelayCrossing(delayest::Axis::Horizontal, y, ay);
            assert(first == line && fee == old.delay - line);
            maxBx = std::max({maxBx, std::abs(net.dx - ax), std::abs(119 - ax + net.dx)});
            maxBy = std::max({maxBy, std::abs(net.dy - ay), std::abs(549 - ay + net.dy)});
        }
    }
    for (int x = 0; x < 120; ++x) for (int tx = 0; tx < 120; ++tx) {
        assert(line707(x, 0, tx, 0) == arch.lineDelayCrossing(delayest::Axis::Vertical, x, tx));
        const bool common = (x < blockLeft707 && tx > blockRight707) ||
                            (tx < blockLeft707 && x > blockRight707);
        for (const auto& b : arch.blocks()) {
            const bool actual = (x < b.left && tx > b.right) || (tx < b.left && x > b.right);
            assert(actual == ((b.left <= 0 || b.right >= 119) ? false : common));
        }
    }
    for (int y = 0; y < 550; ++y) for (int ty = 0; ty < 550; ++ty) {
        assert(line707(0, y, 0, ty) == arch.lineDelayCrossing(delayest::Axis::Horizontal, y, ty));
        bool expected = false;
        for (const auto& b : arch.blocks())
            if (b.left > 0 && b.right < 119)
                expected |= y >= b.lower && y <= b.upper && ty >= b.lower && ty <= b.upper;
        assert(bool(blockMask707[y] & blockMask707[ty]) == expected);
        assert(forced707(0, y, 119, ty) == expected);
    }
    for (int p = 0; p < 496; ++p) {
        const auto& d = ports707[p];
        assert(d.source == kSourceIndex[p] && d.target == kTargetIndex[p]);
        if (d.source >= 0)
            assert(d.sf == kSourceFamily[d.source] && d.sl == kSourceLane[d.source] &&
                   d.cycle == kCycles[d.source]);
        if (d.target >= 0) assert(d.tf == kTargetFamily[d.target] && d.tl == kTargetLane[d.target]);
    }
    const size_t bytes = sizeof(ports707) + sizeof(motion707) + sizeof(prefixX707) +
        sizeof(prefixY707) + sizeof(horizontal707) + sizeof(vertical707) + sizeof(blockMask707) +
        sizeof(blockLeft707) + sizeof(blockRight707);
    assert(bytes < 300000);
    std::printf("{\"all_equal\":true,\"net_positions\":%llu,\"valid_hops\":%llu,"
        "\"max_aligned_bx\":%d,\"max_aligned_by\":%d,\"metadata_bytes\":%zu,"
        "\"port_bytes\":%zu,\"motion_bytes\":%zu}\n",
        (unsigned long long)checked, (unsigned long long)valid, maxBx, maxBy,
        bytes, sizeof(Port707), sizeof(Motion707));
    return 0;
}
