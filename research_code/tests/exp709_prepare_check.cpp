#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "architecture.h"

delayest::Architecture arch;
bool querying = false;
uint64_t allocations = 0;
extern "C" void init707_M();
extern "C" void init707_G();
extern "C" void eval707_M(const int32_t*, unsigned, int32_t*, double*);
extern "C" void eval707_G(const int32_t*, unsigned, int32_t*, double*);

int main(int argc, char** argv) {
    assert(argc == 2);
    FILE* f = std::fopen(argv[1], "rb");
    assert(f);
    char magic[8];
    uint32_t rows;
    assert(std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "EX535Q01", 8) == 0);
    assert(std::fread(&rows, 4, 1, f) == 1 && rows == 239616);
    init707_M();
    arch = delayest::Architecture{};
    init707_G();
    for (unsigned i = 0; i < rows; ++i) {
        int32_t q[10], expected[68]{}, value[68]{};
        double original_raw[3]{}, raw[3]{};
        assert(std::fread(q, 4, 10, f) == 10);
        eval707_M(q, 0, expected, original_raw);
        eval707_G(q, 0, value, raw);
        for (unsigned j = 0; j < 11; ++j) assert(value[j] == expected[j]);
        for (unsigned j = 15; j < 68; ++j) assert(value[j] == expected[j]);
        float forced;
        std::memcpy(&forced, value+67, sizeof(forced));
        assert(raw[0] == double(forced));
        assert(value[14] == 1234);
    }
    assert(std::fgetc(f) == EOF && std::fclose(f) == 0);
    std::printf("{\"all_equal\":true,\"queries\":%u,\"geometry_and_features\":true}\n", rows);
}
