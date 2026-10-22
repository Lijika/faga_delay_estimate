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
int worker608_S(int, char**);
int worker608_D(int, char**);

int main(int argc, char** argv) {
    __builtin_cpu_init();
#if EXP607_ARM == 5
#if EXP607_AVX_CHOICE == 1
    if (__builtin_cpu_supports("avx2")) return worker608_D(argc, argv);
#endif
#if EXP607_SSE_CHOICE == 2
    if (__builtin_cpu_supports("sse4.1")) return worker608_S(argc, argv);
#endif
    return worker608_F(argc, argv);
#elif EXP607_ARM == 1
    if (!__builtin_cpu_supports("avx2")) return 1;
    return worker608_D(argc, argv);
#elif EXP607_ARM == 2
    if (!__builtin_cpu_supports("sse4.1")) return 1;
    return worker608_S(argc, argv);
#else
    return worker608_F(argc, argv);
#endif
}
