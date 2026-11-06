// Scalar tables retain aq-modelvec.inc/aqbatch.inc field and bucket definitions.
namespace geometry856 {
template<class... Args> static constexpr unsigned band(int z, Args... edges) {
    return (0u + ... + unsigned(z >= edges));
}
struct Tables {
    uint32_t xp[239]{}, yp[1099]{}, head[4][552]{};
    uint8_t slope[53]{};
    constexpr Tables() {
        for (int x=-119; x<=119; ++x) {
            const unsigned a=x<0 ? -x : x;
            xp[x+119]=(125u*(a/10)<<19)|((a/10)*46<<9)|(240u*(x<0)+12u*(a%10));
        }
        for (int y=-549; y<=549; ++y) {
            const unsigned a=y<0 ? -y : y;
            yp[y+549]=((y<0?125u:127u)*(a/12)<<19)|(a/12<<9)|(120u*(y<0)+a%12);
        }
        for (int d=0; d<4; ++d) for (int j=0; j<552; ++j) {
            const int q=j/46, p=j%46;
            const unsigned u=band(q,1,2,4,7), v=band(p,1,2,4,7,12,21,32);
            head[d][j]=(u*8+v)|((u*4+d)<<8)|
                       ((8*std::min(q,4)+std::min(p,7))<<16)|((q<5&&p<8)<<23);
        }
        for (int i=-26; i<=26; ++i)
            slope[i+26]=uint8_t(band(i,-25,-15,-9,-5,-2,0,1,3,6,10,16,26));
    }
};
static constexpr Tables tables{};
}
