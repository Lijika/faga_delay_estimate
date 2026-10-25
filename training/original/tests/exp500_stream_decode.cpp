#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <omp.h>
#include <vector>

namespace {
constexpr int NL = 66560, NR = 13248, RANK = 128, NG = 552, METRICS = 688;
using Row = std::array<double, 7>;

void add(Row& a, const Row& b) {
    for (int k = 0; k < 4; ++k) a[k] += b[k];
    a[4] = std::max(a[4], b[4]);
    a[5] = std::min(a[5], b[5]);
    a[6] = std::max(a[6], b[6]);
}

void observe(Row& a, int gold, int predicted) {
    const int error = predicted - gold, absolute = std::abs(error);
    a[0] += 1;
    a[1] += error != 0;
    a[2] += gold > 0 ? 1 - std::tanh(4. * absolute / gold) : predicted == gold;
    a[3] += absolute;
    a[4] = std::max(a[4], double(absolute));
    a[5] = std::min(a[5], double(error));
    a[6] = std::max(a[6], double(error));
}

template <typename T>
int evaluate(int group, int begin, int count, const int32_t* metadata,
             const int32_t* source_ids, const int32_t* target_ids,
             const int16_t* truth, const T* left, const T* right,
             const int32_t* previous, int32_t* output, double* summary,
             double* paired) {
    std::array<std::array<Row, METRICS>, 8> totals{};
    std::array<std::array<uint64_t, 4>, 8> changes{};
    std::array<int, 8> failures{};
    // Columns are contiguous within each rank component, preserving rank-order sums.
#pragma omp parallel for num_threads(8) schedule(static)
    for (int offset = 0; offset < count; ++offset) {
        const int worker = omp_get_thread_num(), row = begin + offset;
        auto& stats = totals[worker];
        auto& changed = changes[worker];
        const auto* m = metadata + row * 8;
        const int s = m[0], t = m[1], sf = m[2], sl = m[3];
        const int tf = m[4], tl = m[5], dx = m[6], rx = m[7];
        std::array<double, NR> sum{};
        for (int k = 0; k < RANK; ++k) {
            const double a = double(left[size_t(row) * RANK + k]);
            const T* b = right + size_t(k) * NR;
            for (int column = 0; column < NR; ++column)
                sum[column] = sum[column] + a * double(b[column]);
        }
        for (int dy = 0; dy < 2; ++dy) for (int ry = 0; ry < 12; ++ry) {
            Row all{}, near{}, interior{};
            const int d = 2 * dx + dy, phase = 12 * rx + ry;
            const int base = (12 * dy + ry) * NG;
            for (int g = 0; g < NG; ++g) {
                const int column = base + g, i = g / 46, j = g % 46;
                const int trend = 125 * i + (dy ? 125 : 127) * j;
                const double value = sum[column] * (128 + 125 * i + 125 * j) + trend;
                if (!std::isfinite(value) || value >= std::numeric_limits<int32_t>::max()) {
                    failures[worker] = 1;
                    continue;
                }
                int prediction = int(std::max(0., std::round(value)));
                if (rx == 0 && ry == 0 && g == 0 && source_ids[s] == target_ids[t])
                    prediction = 0;
                output[size_t(offset) * NR + column] = prediction;
                const int old = previous ? previous[size_t(offset) * NR + column] : prediction;
                changed[0] += previous && old != prediction;
                const int x = rx + 10 * i, y = ry + 12 * j;
                if (x > 119 || y > 549 || (x == 0 && dx) || (y == 0 && dy)) continue;
                const int gold = int(truth[size_t(offset) * NR + column]) + trend;
                if (gold < 0) {
                    failures[worker] = 2;
                    continue;
                }
                observe(all, gold, prediction);
                observe((x < 20 || y < 24) ? near : interior, gold, prediction);
                if (previous) {
                    changed[1] += std::abs(prediction - gold) < std::abs(old - gold);
                    changed[2] += std::abs(prediction - gold) > std::abs(old - gold);
                }
            }
            for (int index : {0, 3 + d, 7 + phase, 127 + s, 335 + t, 623 + sf, 649 + tf})
                add(stats[index], all);
            add(stats[1], near);
            add(stats[2], interior);
            if (phase == 0 || phase == 66) {
                add(stats[685], all);
                add(stats[686], near);
                add(stats[687], interior);
            }
            // Recompute one query per source/target/context from its original port coordinates.
            const int p0 = (sl & 1) + 2 * (tl & 1);
            const int p1 = ((sl >> 1) & 1) + 2 * ((tl >> 1) & 1);
            const int p2 = ((sl >> 2) & 1) + 2 * ((tl >> 2) & 1);
            const int check_row = rx * 6656 +
                (((((sf * 4 + p0) * 4 + p1) * 4 + p2) * 2 + tf % 2) * 2 + d / 2);
            const int g = (31 * s + t + 17 * d + 7 * phase) % NG;
            const int column = ((d % 2) * 12 + ry) * NG + g;
            if (check_row != row || tf / 2 != group) failures[worker] = 3;
            double scalar = 0;
            for (int k = 0; k < RANK; ++k)
                scalar = scalar + double(left[size_t(check_row) * RANK + k]) *
                                  double(right[size_t(k) * NR + column]);
            const int trend = 125 * (g / 46) + (dy ? 125 : 127) * (g % 46);
            const double value = scalar * (128 + 125 * (g / 46) + 125 * (g % 46)) + trend;
            int prediction = int(std::max(0., std::round(value)));
            if (rx == 0 && ry == 0 && g == 0 && source_ids[s] == target_ids[t])
                prediction = 0;
            if (prediction != output[size_t(offset) * NR + column]) failures[worker] = 4;
            changed[3] += 1;
        }
    }
    std::array<Row, METRICS> merged{};
    for (int worker = 0; worker < 8; ++worker) {
        if (failures[worker]) return failures[worker];
        for (int key = 0; key < METRICS; ++key) add(merged[key], totals[worker][key]);
        for (int k = 0; k < 4; ++k) paired[k] += double(changes[worker][k]);
    }
    for (int key = 0; key < METRICS; ++key) {
        Row existing{};
        std::copy_n(summary + key * 7, 7, existing.begin());
        add(existing, merged[key]);
        std::copy(existing.begin(), existing.end(), summary + key * 7);
    }
    return 0;
}
}

extern "C" int exp500_block(int group, int begin, int count, int width,
                           const int32_t* metadata, const int32_t* source_ids,
                           const int32_t* target_ids, const int16_t* truth,
                           const void* left, const void* right, const int32_t* previous,
                           int32_t* output, double* summary, double* paired) {
    if (group < 0 || group >= 18 || begin < 0 || count <= 0 || begin + count > NL)
        return 10;
    if (width == 8)
        return evaluate(group, begin, count, metadata, source_ids, target_ids, truth,
                        static_cast<const double*>(left), static_cast<const double*>(right),
                        previous, output, summary, paired);
    if (width == 4)
        return evaluate(group, begin, count, metadata, source_ids, target_ids, truth,
                        static_cast<const float*>(left), static_cast<const float*>(right),
                        previous, output, summary, paired);
    return 11;
}
