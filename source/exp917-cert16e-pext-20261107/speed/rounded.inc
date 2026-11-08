// For fixed geometry and deviation, all 13 rounded G4 slope corrections
// lie within three units of their minimum. One cache line holds all deviations.
namespace round60 {
alignas(64) static uint32_t tiles[18920][16];
static uint16_t geometry[8][8][36];

static inline uint16_t key(unsigned area, unsigned head, unsigned side, bool ordinary) {
    return uint16_t(geometry[area][head&7][side]+(head&56)+2*((head>>6)&3)+ordinary);
}

static void init() {
    unsigned next=0;
    for(unsigned area=0;area<8;++area)for(unsigned v=0;v<8;++v){
        for(unsigned side=0;side<36;++side){
            const int term=aqfar::bb3[area][v][side];
            unsigned first=0;
            while(first<side && aqfar::bb3[area][v][first]!=term)++first;
            if(first<side){
                geometry[area][v][side]=geometry[area][v][first];
                continue;
            }
            require(next+40<=18920,"G4 tile limit");
            geometry[area][v][side]=uint16_t(next);
            for(unsigned u=0;u<5;++u)for(unsigned d=0;d<4;++d)for(unsigned ordinary=0;ordinary<2;++ordinary){
                const unsigned uv=8*u+v;
                auto& tile=tiles[next+8*u+2*d+ordinary];
                for(unsigned dev=0;dev<13;++dev){
                    int values[13],minimum=INT_MAX;
                    for(unsigned slope=0;slope<13;++slope){
                        const int sum=aqfar::bb0[dev][area][uv]+aqfar::mid[dev][slope][uv][d][ordinary]+term;
                        values[slope]=int(uint32_t(sum+65536+16)>>5)-2048-int((unsigned(sum)&63)==16);
                        minimum=std::min(minimum,values[slope]);
                    }
                    require(minimum>=-4 && minimum<=10,"G4 tile base");
                    uint32_t word=uint32_t(minimum+4)<<26;
                    for(unsigned sl=0;sl<13;++sl){
                        const unsigned delta=unsigned(values[sl]-minimum);
                        require(delta<4,"G4 slope span");
                        word|=delta<<(2*sl);
                    }
                    tile[dev]=word;
                }
            }
            next+=40;
        }
    }
    require(next==18920,"G4 frozen geometry count");
}

static inline int get(unsigned key,unsigned dev,unsigned slope){
    const uint32_t word=tiles[key][dev];
    return int(word>>26)-4+int((word>>(2*slope))&3);
}
}
