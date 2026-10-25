#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <vector>

namespace {
constexpr int NL = 66560, NR = 13248, RANK = 128;
using Query = std::array<std::int32_t, 10>;
double cpu() { return double(std::clock()) / CLOCKS_PER_SEC; }
int compressed(int x, int y) { return x - 14 * (y % 100 < 50 && x >= 90); }

int predict(const Query& query, const float* tables, bool transform) {
    const int sx = transform ? compressed(query[0], query[1]) : query[0];
    const int tx = transform ? compressed(query[2], query[3]) : query[2];
    const int x = tx - sx, y = query[3] - query[1];
    const int dx = x < 0, dy = y < 0, ax = std::abs(x), ay = std::abs(y);
    assert(ax <= 119 && ay <= 549);
    const int sf = query[4], sl = query[5], tf = query[6], tl = query[7];
    assert(0 <= sf && sf < 26 && 0 <= sl && sl < 8);
    assert(0 <= tf && tf < 36 && 0 <= tl && tl < 8);
    const int p0 = (sl & 1) + 2 * (tl & 1);
    const int p1 = ((sl >> 1) & 1) + 2 * ((tl >> 1) & 1);
    const int p2 = ((sl >> 2) & 1) + 2 * ((tl >> 2) & 1);
    const int row = (ax % 10) * 6656 +
        (((((sf * 4 + p0) * 4 + p1) * 4 + p2) * 2 + tf % 2) * 2 + dx);
    const int column = (12 * dy + ay % 12) * 552 + (ax / 10) * 46 + ay / 12;
    assert(0 <= row && row < NL && 0 <= column && column < NR);
    const float* left = tables + std::size_t(tf / 2) * (NL + NR) * RANK + row * RANK;
    const float* right = tables + std::size_t(tf / 2) * (NL + NR) * RANK +
                         std::size_t(NL) * RANK + column * RANK;
    double sum = 0;
    for (int k = 0; k < RANK; ++k) sum += double(left[k]) * double(right[k]);
    const int i = ax / 10, j = ay / 12;
    const double value = sum * (128 + 125 * i + 125 * j) + 125 * i + (dy ? 125 : 127) * j;
    assert(std::isfinite(value) && value < INT32_MAX);
    if (sx == tx && query[1] == query[3] && query[8] == query[9]) return 0;
    return int(std::max(0., std::round(value)));
}
}

int main(int argc, char** argv) {
    static_assert(sizeof(float) == 4 && sizeof(Query) == 40);
    assert(argc == 4);
    const double begin = cpu();
    std::vector<float> tables(std::size_t(18) * (NL + NR) * RANK);
    std::ifstream model(argv[1], std::ios::binary);
    assert(model);
    model.read(reinterpret_cast<char*>(tables.data()), std::streamsize(tables.size() * sizeof(float)));
    assert(model && model.peek() == std::char_traits<char>::eof());
    std::ifstream input(argv[2], std::ios::binary);
    std::array<char, 8> magic{};
    std::uint32_t count = 0;
    input.read(magic.data(), magic.size());
    assert((magic == std::array<char, 8>{'E','X','5','3','5','Q','0','1'}));
    input.read(reinterpret_cast<char*>(&count), sizeof(count));
    assert(input && count == 1000000);
    std::vector<Query> queries(count);
    input.read(reinterpret_cast<char*>(queries.data()), std::streamsize(count * sizeof(Query)));
    assert(input && input.peek() == std::char_traits<char>::eof());
    std::vector<std::array<std::int32_t, 2>> predictions(count);
    const double loaded = cpu();
    for (std::uint32_t i = 0; i < count; ++i)
        for (int mode = 0; mode < 2; ++mode)
            predictions[i][mode] = predict(queries[i], tables.data(), mode != 0);
    const double queried = cpu();
    std::ofstream output(argv[3], std::ios::binary);
    assert(output);
    output.write(reinterpret_cast<const char*>(predictions.data()), std::streamsize(count * 8));
    output.close();
    assert(output);
    std::fprintf(stderr,
        "{\"rows\":%u,\"predictions\":%u,\"table_bytes\":%zu,"
        "\"load_cpu_s\":%.9f,\"query_cpu_s\":%.9f,\"write_cpu_s\":%.9f,"
        "\"total_cpu_s\":%.9f}\n",
        count, count * 2, tables.size() * sizeof(float), loaded - begin,
        queried - loaded, cpu() - queried, cpu() - begin);
}
