#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "architecture.h"

delayest::Architecture arch;
bool querying = false;
uint64_t allocations = 0;
extern "C" void init707_M();
extern "C" void init714_C();
extern "C" size_t size707_M();
extern "C" size_t size714_C();
extern "C" void eval707_M(const int32_t*, unsigned, int32_t*, double*);
extern "C" void eval714_C(const int32_t*, unsigned, int32_t*, double*);

static void compare(const int32_t* q, unsigned fold) {
    int32_t reference[68]{}, actual[68]{};
    double expected[3]{}, value[3]{};
    eval707_M(q, fold, reference, expected);
    eval714_C(q, fold, actual, value);
    assert(std::memcmp(reference, actual, sizeof(reference)) == 0);
    assert(std::memcmp(expected, value, sizeof(expected)) == 0);
}

int main(int argc, char** argv) {
    assert(argc == 2);
    init707_M();
    arch = delayest::Architecture{};
    init714_C();
    assert(size707_M() == 56 && size714_C() == 56);
    FILE* f = std::fopen(argv[1], "rb");
    assert(f);
    char magic[8];
    uint32_t rows;
    assert(std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "EX535Q01", 8) == 0);
    assert(std::fread(&rows, 4, 1, f) == 1 && rows == 239616);
    for (unsigned i = 0; i < rows; ++i) {
        int32_t q[10];
        assert(std::fread(q, 4, 10, f) == 10);
        for (unsigned fold = 0; fold < 4; ++fold) compare(q, fold);
    }
    assert(std::fgetc(f) == EOF && std::fclose(f) == 0);
    unsigned corners = 0;
    for (int p = 0; p < 496; ++p)
        for (int x : {-1, 0, 15, 16, 75, 76, 89, 90, 119, 120})
            for (int y : {-1, 0, 49, 50, 99, 100, 499, 500, 549, 550}) {
                int32_t q[10] = {x, y, x, y, 0, 0, 0, 0, p, p};
                compare(q, 0);
                ++corners;
                q[2] = 120;
                q[3] = 550;
                compare(q, 0);
                ++corners;
            }
    std::printf("{\"all_equal\":true,\"queries\":%u,\"folds\":4,\"corners\":%u,"
                "\"prepared_bytes\":56}\n", rows, corners);
}
