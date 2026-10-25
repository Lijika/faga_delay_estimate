#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <omp.h>

namespace {
constexpr int NL = 59904, NR = 264960, TILE = 6624, NG = 552, METRICS = 688;
using Row = std::array<double, 7>;

void add(Row& a, const Row& b) {
    if (b[0] == 0) return;
    const bool empty = a[0] == 0;
    for (int k = 0; k < 4; ++k) a[k] += b[k];
    a[4] = std::max(a[4], b[4]);
    a[5] = empty ? b[5] : std::min(a[5], b[5]);
    a[6] = empty ? b[6] : std::max(a[6], b[6]);
}

void observe(Row& a, int gold, int predicted) {
    const int error = predicted - gold, absolute = std::abs(error);
    const bool empty = a[0] == 0;
    a[0] += 1;
    a[1] += error != 0;
    a[2] += gold > 0 ? 1 - std::tanh(4. * absolute / gold) : predicted == gold;
    a[3] += absolute;
    a[4] = std::max(a[4], double(absolute));
    a[5] = empty ? double(error) : std::min(a[5], double(error));
    a[6] = empty ? double(error) : std::max(a[6], double(error));
}

template <typename T>
int evaluate(int begin, int count, int rank, const int32_t* sc, const int32_t* tc,
             const int32_t* source_ids, const int32_t* target_ids,
             const int16_t* truth, const T* left, const T* right,
             const int32_t* previous, int32_t* output, double* summary, double* paired) {
    std::array<int, 208> source_slot;
    std::array<int, 288> target_slot;
    source_slot.fill(-1);
    target_slot.fill(-1);
    for (int s = 0; s < 208; ++s) {
        const int family = sc[2 * s], lane = sc[2 * s + 1], key = family * 8 + lane;
        if (family < 0 || family >= 26 || lane < 0 || lane >= 8 || source_slot[key] != -1) return 12;
        source_slot[key] = s;
    }
    for (int t = 0; t < 288; ++t) {
        const int family = tc[2 * t], lane = tc[2 * t + 1], key = family * 8 + lane;
        if (family < 0 || family >= 36 || lane < 0 || lane >= 8 || target_slot[key] != -1) return 13;
        target_slot[key] = t;
    }
    std::array<std::array<Row, METRICS>, 8> totals{};
    std::array<std::array<uint64_t, 4>, 8> changes{};
    std::array<int, 8> failures{};
#pragma omp parallel num_threads(8)
    {
        const int worker = omp_get_thread_num();
        auto& stats = totals[worker];
        auto& changed = changes[worker];
        // A geometry tile shares factor reads across rows without changing sum order.
        for (int tile = 0; tile < NR / TILE; ++tile) {
            const int d = tile / 10, rx = tile % 10, base = tile * TILE;
#pragma omp for schedule(static)
            for (int offset = 0; offset < count; ++offset) {
                const int row = begin + offset, s = row / 288, t = row % 288;
                const int sf = sc[2 * s], sl = sc[2 * s + 1];
                const int tf = tc[2 * t], tl = tc[2 * t + 1];
                std::array<double, TILE> sums{};
                for (int k = 0; k < rank; ++k) {
                    const double a = double(left[size_t(row) * rank + k]);
                    const T* b = right + size_t(k) * NR + base;
                    for (int c = 0; c < TILE; ++c)
                        sums[c] = sums[c] + a * double(b[c]);
                }
                for (int ry = 0; ry < 12; ++ry) {
                    Row all{}, near{}, interior{};
                    const int phase = 12 * rx + ry;
                    for (int g = 0; g < NG; ++g) {
                        const int c = ry * NG + g, i = g / 46, j = g % 46;
                        const size_t position = size_t(offset) * NR + base + c;
                        const int trend = 125 * i + (d % 2 ? 125 : 127) * j;
                        const double value = sums[c] * (128 + 125 * i + 125 * j) + trend;
                        if (!std::isfinite(value) || value >= std::numeric_limits<int32_t>::max()) {
                            failures[worker] = 1;
                            continue;
                        }
                        int prediction = int(std::max(0., std::round(value)));
                        if (rx == 0 && ry == 0 && g == 0 && source_ids[s] == target_ids[t])
                            prediction = 0;
                        output[position] = prediction;
                        const int old = previous ? previous[position] : prediction;
                        changed[0] += previous && old != prediction;
                        const int x = rx + 10 * i, y = ry + 12 * j;
                        if (y > 549 || (x == 0 && d / 2) || (y == 0 && d % 2)) continue;
                        const int gold = int(truth[position]) + trend;
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
                    for (int key : {0, 3 + d, 7 + phase, 127 + s, 335 + t, 623 + sf, 649 + tf})
                        add(stats[key], all);
                    add(stats[1], near);
                    add(stats[2], interior);
                    if (phase == 0 || phase == 66) {
                        add(stats[685], all);
                        add(stats[686], near);
                        add(stats[687], interior);
                    }
                    const int check_row = source_slot[sf * 8 + sl] * 288 + target_slot[tf * 8 + tl];
                    const int g = (31 * s + t + 17 * d + 7 * phase) % NG;
                    const int column = ((((d * 10 + rx) * 12 + ry) * 12 + g / 46) * 46 + g % 46);
                    if (check_row != row || column != base + ry * NG + g) {
                        failures[worker] = 3;
                        continue;
                    }
                    double scalar = 0;
                    for (int k = 0; k < rank; ++k)
                        scalar = scalar + double(left[size_t(check_row) * rank + k]) *
                                          double(right[size_t(k) * NR + column]);
                    const int trend = 125 * (g / 46) + (d % 2 ? 125 : 127) * (g % 46);
                    const double value = scalar * (128 + 125 * (g / 46) + 125 * (g % 46)) + trend;
                    if (!std::isfinite(value) || value >= std::numeric_limits<int32_t>::max()) {
                        failures[worker] = 5;
                        continue;
                    }
                    int prediction = int(std::max(0., std::round(value)));
                    if (rx == 0 && ry == 0 && g == 0 && source_ids[s] == target_ids[t])
                        prediction = 0;
                    if (prediction != output[size_t(offset) * NR + column]) failures[worker] = 4;
                    changed[3] += 1;
                }
            }
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

extern "C" int exp510_block(int begin, int count, int rank, int width,
                           const int32_t* sc, const int32_t* tc,
                           const int32_t* source_ids, const int32_t* target_ids,
                           const int16_t* truth, const void* left, const void* right,
                           const int32_t* previous, int32_t* output, double* summary, double* paired) {
    if (begin < 0 || count <= 0 || count > NL || begin > NL - count ||
        (rank != 64 && rank != 96)) return 10;
    if (width == 8)
        return evaluate(begin, count, rank, sc, tc, source_ids, target_ids, truth,
                        static_cast<const double*>(left), static_cast<const double*>(right),
                        previous, output, summary, paired);
    if (width == 4)
        return evaluate(begin, count, rank, sc, tc, source_ids, target_ids, truth,
                        static_cast<const float*>(left), static_cast<const float*>(right),
                        previous, output, summary, paired);
    return 11;
}
