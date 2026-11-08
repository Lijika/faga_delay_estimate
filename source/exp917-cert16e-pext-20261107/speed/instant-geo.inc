// Both halves have disjoint additive semantic fields. Bit 15 of the high half
// is the carry generated only when BOTH axes are inside the 5 by 8 near grid.
namespace instantGeo {
static uint64_t xcode[239], ycode[1099];
static void init() {
    for(int dx=-119;dx<=119;++dx) {
        const unsigned q=unsigned(std::abs(dx))/10, d=2*(dx<0);
        const unsigned u=geometry856::band(q,1,2,4,7);
        const uint32_t high=8*u+(d<<6)+(8*std::min(q,4u)<<8)+((q<5)<<14)+((d*552+46*q)<<16);
        xcode[dx+119]=(uint64_t(high)<<32)|geometry856::tables.xp[dx+119];
    }
    for(int dy=-549;dy<=549;++dy) {
        const unsigned q=unsigned(std::abs(dy))/12, d=(dy<0);
        const unsigned v=geometry856::band(q,1,2,4,7,12,21,32);
        const uint32_t high=v+(d<<6)+(std::min(q,7u)<<8)+((q<8)<<14)+((d*552+q)<<16);
        ycode[dy+549]=(uint64_t(high)<<32)|geometry856::tables.yp[dy+549];
    }
}
}
