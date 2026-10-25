#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "architecture.h"

delayest::Architecture arch;
bool querying = false;
uint64_t allocations = 0;
extern "C" void init707_A();
extern "C" void init707_M();
extern "C" void init707_C();
extern "C" void eval707_A(const int32_t*, unsigned, int32_t*, double*);
extern "C" void eval707_M(const int32_t*, unsigned, int32_t*, double*);
extern "C" void eval707_C(const int32_t*, unsigned, int32_t*, double*);
extern "C" size_t size707_A();
extern "C" size_t size707_M();
extern "C" size_t size707_C();

static void compare(const int32_t* q, unsigned fold, unsigned row) {
    int32_t reference[68]{}, actual[68]{};
    double ref[3]{}, out[3]{};
    eval707_A(q, fold, reference, ref);
    for (auto eval : {eval707_M, eval707_C}) {
        eval(q, fold, actual, out);
        for (unsigned j = 0; j < 68; ++j) {
            if (reference[j] != actual[j])
                std::fprintf(stderr, "row=%u fold=%u field=%u reference=%d actual=%d\n",
                             row, fold, j, reference[j], actual[j]);
            assert(reference[j] == actual[j]);
        }
        assert(std::memcmp(ref, out, sizeof(ref)) == 0);
    }
}

int main(int argc, char** argv) {
    assert(argc == 2);
    init707_A(); init707_M(); init707_C();
    FILE* f = std::fopen(argv[1], "rb");
    assert(f);
    char magic[8]; uint32_t n;
    assert(std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "EX535Q01", 8) == 0);
    assert(std::fread(&n, 4, 1, f) == 1 && n == 239616);
    for (unsigned i = 0; i < n; ++i) {
        int32_t q[10];
        assert(std::fread(q, 4, 10, f) == 10);
        for (unsigned fold = 0; fold < 4; ++fold) compare(q, fold, i);
    }
    assert(std::fgetc(f) == EOF && std::fclose(f) == 0);
    unsigned corners = 0;
    for (int p = 0; p < 496; ++p) {
        for (int x : {-1, 0, 15, 16, 75, 76, 89, 90, 119, 120})
            for (int y : {-1, 0, 49, 50, 99, 100, 499, 500, 549, 550}) {
                int32_t q[10] = {x, y, x, y, 0, 0, 0, 0, p, p};
                compare(q, 0, n + corners++);
            }
    }
    assert(size707_A() == size707_M() && size707_C() == 32);
    std::printf("{\"all_equal\":true,\"queries\":%u,\"folds\":4,\"corner_cases\":%u,"
        "\"prepared_A_bytes\":%zu,\"prepared_M_bytes\":%zu,\"prepared_C_bytes\":%zu}\n",
        n, corners, size707_A(), size707_M(), size707_C());
}
