#include "architecture.h"
delayest::Architecture arch;
#include <cstdint>
#include <cstdlib>
#include <cstdio>
extern "C" void* __real_malloc(size_t);
extern "C" void* __real_calloc(size_t, size_t);
extern "C" void* __real_realloc(void*, size_t);
bool querying = false;
uint64_t allocations = 0;
extern "C" void* __wrap_malloc(size_t n) {
    if (querying) ++allocations;
    return __real_malloc(n);
}
extern "C" void* __wrap_calloc(size_t n, size_t m) {
    if (querying) ++allocations;
    return __real_calloc(n, m);
}
extern "C" void* __wrap_realloc(void* p, size_t n) {
    if (querying) ++allocations;
    return __real_realloc(p, n);
}


int worker608_F(int, char**);
int main(int argc, char** argv) {
    return worker608_F(argc, argv);
}
