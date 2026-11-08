namespace axisRoute {
// The two X values describe movement on either side of the port's exceptional
// vertical band. Each holds exactly the fields consumed by the fast predictor.
// Twelve motion-field bits fit in two bytes; remaining fields stay decoded.
struct X {int8_t adj;uint8_t flags;uint16_t px,delay;};
struct Y {uint8_t band,flags;};
struct SourceY {uint8_t py,delay,band,flags;};
struct TargetX {uint16_t px;uint8_t side,ok;};
struct TargetY {uint8_t py,band,allowed;};
static_assert(sizeof(X)==6&&sizeof(Y)==2,"axis record width");
static X xBanks[9][2][120];static Y yBanks[10][550];
static TargetX targetX[120];static TargetY targetY[550];

static inline bool event(unsigned sx,unsigned tx,unsigned sy,unsigned ty){
 return ((sx^tx)==2&&sy==ty&&!(sy&1))||(sx==1&&tx==1&&(sy^ty)>=2);
}
static inline unsigned xWord(const route913::Source& s,unsigned dy){
 require(s.priceX<1024&&s.delay>=dy&&s.delay-dy<512&&(s.adj==0||s.adj==14||s.adj==-14),"axis range");
 return s.priceX|((s.delay-dy)<<10)|(unsigned(uint8_t(s.adj))<<19)|(unsigned(s.code%3)<<27);
}
static void init(){
 for(unsigned sc=0;sc<33;sc++)for(unsigned tc=0;tc<33;tc++)
  require(event(sc%3,tc%3,sc/3,tc/3)==bool(route913::eventMask[sc]&(uint64_t(1)<<tc)),"axis events");
 unsigned nx=0,ny=0;uint8_t groupCode[17]{};
 for(unsigned g=0;g<17;g++){
   uint64_t sourceX[120]{};SourceY sourceY[550]{};
   auto at=[&](int x,int y)->const route913::Source&{
     return route913::source[route913::rows[route913::srcY[g][y]/120][x]];
   };
   for(int y=0;y<550;y++){
     unsigned dy=65535,py=0,band=0;
     for(int x=0;x<120;x++){const auto& s=at(x,y);if(s.code==63)continue;
       if(dy!=65535)require(py==s.priceY&&band==s.code/3,"source Y not separable");
       dy=std::min(dy,unsigned(s.delay));py=s.priceY;band=s.code/3;
     }
     if(dy==65535)dy=0;
     require(dy<=255&&py<=255&&band<11,"source Y width");
     sourceY[y]={uint8_t(py),uint8_t(dy),uint8_t(band),0};
   }
   uint8_t permits[4][550]{};int npermit=0;
   for(int x=0;x<120;x++){
     uint32_t w[2]{};unsigned counts[2]{};uint8_t good[550]{};
     for(int y=0;y<550;y++){const auto& s=at(x,y);if(s.code==63)continue;
       good[y]=1;unsigned v=xWord(s,sourceY[y].delay);
       unsigned h=counts[0]&&w[0]!=v;require(!counts[h]||w[h]==v,"third source X");w[h]=v;++counts[h];
     }
     if(counts[1]>counts[0]){std::swap(w[0],w[1]);std::swap(counts[0],counts[1]);}
     if(!counts[1])w[1]=w[0];
     int id=0;while(id<npermit&&memcmp(permits[id],good,550))id++;
     if(id==npermit){require(npermit<4,"axis validity width");memcpy(permits[npermit++],good,550);}
     for(int y=0;y<550;y++)if(good[y]){
       auto& meta=sourceY[y];meta.flags|=uint8_t(1u<<id);
       if(xWord(at(x,y),meta.delay)!=w[0])meta.flags|=32;
     }
     const uint32_t test=uint32_t(id)<<29;
     sourceX[x]=(w[0]|test)|(uint64_t(w[1]|test)<<32);
   }
   X gx[2][120];Y gy[550];
   for(unsigned half=0;half<2;half++)for(unsigned x=0;x<120;x++){
    const uint32_t w=uint32_t(sourceX[x]>>(32*half));
    gx[half][x]={int8_t((int((w>>19)&255)-int((w>>18)&256))),
      uint8_t((16u<<(w>>29))|((w>>27)&3)),uint16_t(w&1023),uint16_t((w>>10)&511)};
   }
   for(unsigned y=0;y<550;y++){
    const auto a=sourceY[y];require(a.py==((a.band+1)/2)*8 && (a.delay==0||a.delay==8),"compact Y");
    gy[y]={a.band,uint8_t((a.flags<<4&240)|a.delay)};
   }
   unsigned xb=0,yb=0;while(xb<nx&&memcmp(xBanks[xb],gx,sizeof(gx)))xb++;
   if(xb==nx){require(nx<9,"x row banks");memcpy(xBanks[nx++],gx,sizeof(gx));}
   while(yb<ny&&memcmp(yBanks[yb],gy,sizeof(gy)))yb++;
   if(yb==ny){require(ny<10,"y row banks");memcpy(yBanks[ny++],gy,sizeof(gy));}
   groupCode[g]=uint8_t(xb|(yb<<4));
   for(int y=0;y<550;y++)for(int x=0;x<120;x++){
     const auto& s=at(x,y);const auto a=yBanks[yb][y];const auto b=xBanks[xb][(y/50)&1][x];
     require(bool(a.flags&b.flags&240)==(s.code!=63),"compact axis legality");
     if(s.code!=63)require(b.px==s.priceX&&((a.band+1)/2)*8==s.priceY&&
      b.delay+(a.flags&8)==s.delay&&b.adj==s.adj&&3*a.band+(b.flags&3)==s.code&&
      unsigned(x-b.adj)<120,"compact source projection");
   }
 }
 require(nx==9&&ny==10,"bank cardinality");
 for(unsigned p=0;p<496;p++)if(ports707[p].source>=0){
  unsigned g=shortgate::portClass[p];require(g<17,"source action");
  nativeQuery::startCode[p]=(nativeQuery::startCode[p]&~1023u)|groupCode[g];
 }
 const unsigned xc=groupCode[16]&15,yc=groupCode[16]>>4;
 for(unsigned x=0;x<120;x++){const auto u=xBanks[xc][0][x];targetX[x]={u.px,uint8_t(u.flags&3),uint8_t(u.flags&240)};}
 for(unsigned y=0;y<550;y++) {
   const auto a=yBanks[yc][y];targetY[y]={uint8_t(((a.band+1)/2)*8),a.band,uint8_t(a.flags&240)};
   for(unsigned x=0;x<120;x++){
     const auto t=route913::target[route913::drows[route913::dstY[y]/120][x]];const auto u=targetX[x];
     require(bool(a.flags&u.ok)==(t.code!=63),"target axis legality");
     if(t.code!=63)require(u.px==t.priceX&&targetY[y].py==t.priceY&&3*a.band+u.side==t.code,"target axis values");
   }
 }
}
}
