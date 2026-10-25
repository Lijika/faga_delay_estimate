#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void require(bool value, const char* message) {
    if (!value) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}
[[maybe_unused]] static int side(int x) { return x<76 ? 0 : x<90 ? 1 : 2; }
[[maybe_unused]] static int mod(int x, int n) { const int r=x%n; return r<0 ? r+n : r; }
#define EXP727_CHECK
#include "symmetric640.h"

static uint32_t state=20261025727ULL & 0xffffffffu;
static unsigned draw(unsigned limit) {
    state^=state<<13; state^=state>>17; state^=state<<5;
    return state%limit;
}

int main() {
    const auto entries=checkTables727();
    uint64_t checks=0, combinations=0;
    for(unsigned i=0;i<200000;++i) {
        int32_t q[10]={int(draw(120)),int(draw(550)),int(draw(120)),int(draw(550)),
                       int(draw(26)),int(draw(8)),int(draw(36)),int(draw(8)),0,0};
        const int ax=draw(120),ay=draw(550),ndx=int(draw(25))-12,ndy=int(draw(25))-12;
        const int x=q[2]-ax,y=q[3]-ay,fee=draw(1024);
        const bool forced=draw(2);
        for(unsigned route=0;route<16;++route) {
            unsigned char a[2]{},b[2]{};
            const double expected=reference727(q,ax,ay,ndx,ndy,x,y,fee,forced,route,0,a);
            const double actual=symmetric640(q,ax,ay,ndx,ndy,x,y,fee,forced,route,0,b);
            require(std::memcmp(a,b,2)==0,"combined leaf indices");
            require(std::memcmp(&actual,&expected,sizeof(double))==0,"combined raw bits");
            ++checks;
        }
    }
    for(unsigned r=0;r<16;++r) for(unsigned a=0;a<64;++a) for(unsigned b=0;b<64;++b) {
        const unsigned bits=a|(b<<6);
        double reference=0.,actual=0.;
        reference+=kLeaves720[r][0][a]; reference+=kLeaves720[r][1][b];
        actual+=kLeaves720[r][0][bits&63]; actual+=kLeaves720[r][1][bits>>6];
        require(std::memcmp(&actual,&reference,sizeof(double))==0,"leaf arithmetic order");
        ++combinations;
    }
    std::printf("{\"all_equal\":true,\"table_entries\":%llu,\"query_checks\":%llu,"
                "\"leaf_combinations\":%llu}\n",
                static_cast<unsigned long long>(entries),static_cast<unsigned long long>(checks),
                static_cast<unsigned long long>(combinations));
}
