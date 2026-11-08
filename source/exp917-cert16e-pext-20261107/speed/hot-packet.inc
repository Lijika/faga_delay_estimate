namespace packet60 {
// Long queries need no coordinates after their route and model key are known.
struct Work {
    const uint8_t* row;
    uint32_t selector;
    uint16_t geom;
    int16_t trendFee;
};
static_assert(sizeof(Work)==16,"packet extent");
struct Extra {unsigned key;uint16_t sy,ty,cell;uint8_t sx,tx,dist;};
template<unsigned N>struct Group {
    Work hot[N],aux[N];Extra extra[N];uint16_t cold[N];unsigned hotN,extraN,coldN;
};
template<bool Events,unsigned N>
static inline bool enqueue(int sx,int sy,int sp,int tx,int ty,int tp,unsigned lane,Group<N>& group) {
    if(unsigned(sx)>=120||unsigned(tx)>=120||unsigned(sy)>=550||unsigned(ty)>=550)return false;
    const int dx=tx-sx,dy=ty-sy,dist=std::abs(dx)+std::abs(dy);
    if(dist<=4)return false;
    const uint32_t sw=nativeQuery::startCode[sp],tw=nativeQuery::endCode[tp];
    if((sw|tw)>>31)return false;
    uint32_t word,head,key;const uint8_t* row;int effective;bool event;
    const auto sourceX=tiny5::xx[sw&15][unsigned(sy)/50%2][sx];
    int nx=dx+sourceX.adj;
    if(!dy&&!nx&&sp==tp)return false;
    auto xp=tiny5::xpair[sourceX.base+tiny5::tx[tx]];
    auto yp=tiny5::ypair[tiny5::yy[(sw>>4)&15][sy]+tiny5::ty[ty]];
    unsigned gate=xp.gate&yp.gate;
    if(gate>=4)return false;
    event=gate!=0;
    const uint64_t g=instantGeo::xcode[nx+119]+instantGeo::ycode[dy+549];
    word=uint32_t(g);head=g>>32;key=(sw&~1023u)+tw+(word&511u);
    row=aqfar::locate(key);__builtin_prefetch(row,0,3);
    effective=xp.fee+yp.fee;
    if(event){auto sd=ports707[sp];effective+=eventHot::read(gate,sp,tp,sy,sx+sd.dx-sourceX.adj,sy+sd.dy,tx,ty,word);}
    const unsigned x=nativeQuery::X[sx][tx],span=nativeQuery::Y[std::max(sy,ty)+1]-nativeQuery::Y[std::min(sy,ty)];
    const unsigned missing=(uint64_t(x&0x00ff00ffu)*span>>16)&65535u;
    const unsigned area=aqfar::areaBand[std::min(3000u,missing)],side=((x>>8)&15)*4+aqfar::ypart[sy]*2+aqfar::ypart[ty];
    const bool simple=dist>55;
    if(!simple)group.extra[group.extraN]={key,uint16_t(sy),uint16_t(ty),uint16_t((word>>9)&1023),uint8_t(sx),uint8_t(tx),uint8_t(dist)};
    auto &job=simple?group.hot[group.hotN++]:group.aux[group.extraN++];
    job.row=row;job.selector=(head&~255u)|lane;
    job.trendFee=int16_t(int(word>>19)+effective);
    job.geom=round60::key(area,head,side,!event);
    __builtin_prefetch(round60::tiles[job.geom],0,1);
    return true;
}
// The frozen-model bounds and the self-route guard make both clamps redundant
// for every admitted key. Billing receives the same nominal value as in G4.
static inline int evaluate(const Work& job,const Extra* extra,int* out) {
    const unsigned head=job.selector;
    const auto row=job.row;
    const int base=aqfar::baseFlat(row);
    const unsigned shift=row[58]&15,slope=row[58]>>4;
    const int near=int16_t(aqfar::nearFlat(row,(head>>8)&63,base,shift));

    int value=near;unsigned dev=6;
    if(!(head&(1u<<15))){
        value=aqfar::responsePlan(row,base,shift,head>>16);
        dev=geometry856::tables.slope[std::clamp(value-near,-26,26)+26];
    }
    const int intrinsic=job.trendFee+value;
    if(extra)bills::add(out,intrinsic,extra->sx,extra->sy,extra->tx,extra->ty,extra->key,extra->cell,row[63],extra->dist);
    return intrinsic+round60::get(job.geom,dev,slope);
}
static inline unsigned lane(const Work& job){return job.selector&255u;}
static inline int result(const Work& job){return evaluate(job,nullptr,nullptr);}
static inline int general(const Work& job,const Extra& extra,int* out){return evaluate(job,&extra,out);}
}
