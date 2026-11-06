#include <cpuid.h>

namespace cpu857 {
static bool modelToken(const char* brand,const char* model) {
    const char* at=std::strstr(brand,model);
    return at && (at==brand || at[-1]==' ') && (at[5]==' ' || at[5]=='\0');
}
static bool supportedModel(const char* vendor,const char* brand) {
    return !std::strcmp(vendor,"GenuineIntel") &&
        (modelToken(brand,"6242R") || modelToken(brand,"6226R"));
}
static bool core512Supported() {
    __builtin_cpu_init();
    return __builtin_cpu_supports("avx2") && __builtin_cpu_supports("bmi") && __builtin_cpu_supports("bmi2") &&
        __builtin_cpu_supports("popcnt") && __builtin_cpu_supports("avx512f") &&
        __builtin_cpu_supports("avx512bw") && __builtin_cpu_supports("avx512dq") &&
        __builtin_cpu_supports("avx512vl");
}
static bool selected() {
    unsigned a,b,c,d;
    if(!__get_cpuid(0,&a,&b,&c,&d) ||
       __get_cpuid_max(0x80000000,nullptr)<0x80000004) return false;
    char vendor[13]{},brand[49]{};
    std::memcpy(vendor,&b,4);std::memcpy(vendor+4,&d,4);std::memcpy(vendor+8,&c,4);
    for(unsigned i=0;i<3;i++){
        __cpuid(0x80000002+i,a,b,c,d);
        std::memcpy(brand+16*i,&a,4);std::memcpy(brand+16*i+4,&b,4);
        std::memcpy(brand+16*i+8,&c,4);std::memcpy(brand+16*i+12,&d,4);
    }
    return supportedModel(vendor,brand) && core512Supported();
}
}
