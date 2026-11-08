namespace tiny5 {
struct Feature {uint16_t p,fee;uint8_t s,permit;};
static_assert(sizeof(Feature)==6);
struct FromX {uint16_t base;int8_t adj;uint8_t pad;};
struct Pair {uint16_t fee,gate;};
static FromX xx[9][2][128];static uint16_t yy[10][550];static uint8_t tx[120],ty[550];
static Pair xpair[100*32],ypair[40*16];
template<unsigned N>static unsigned intern(Feature (&items)[N],unsigned& size,Feature v){
 for(unsigned i=0;i<size;i++)if(!memcmp(items+i,&v,sizeof(v)))return i;
 require(size<N,"route feature capacity");items[size]=v;return size++;
}
static void init(){
 using namespace axisRoute;
 Feature sx[100]{},sy[40]{},ex[18]{},ey[11]{};unsigned n=0,m=0,e=0,f=0;
 for(unsigned g=0;g<9;g++)for(unsigned h=0;h<2;h++)for(int x=0;x<120;x++){const auto a=xBanks[g][h][x];
  unsigned id=intern(sx,n,{a.px,a.delay,uint8_t(a.flags&3),uint8_t(a.flags&240)});
  xx[g][h][x]={uint16_t(id*32),a.adj,0};
 }
 for(unsigned g=0;g<10;g++)for(int y=0;y<550;y++){const auto a=yBanks[g][y];unsigned p=((a.band+1)/2)*8;
   yy[g][y]=uint16_t(16*intern(sy,m,{uint16_t(p),uint16_t(a.flags&8),a.band,uint8_t(a.flags&240)}));
 }
 for(unsigned x=0;x<120;x++){auto a=targetX[x];tx[x]=intern(ex,e,{a.px,0,a.side,a.ok});}
 for(unsigned y=0;y<550;y++){auto a=targetY[y];ty[y]=intern(ey,f,{a.py,0,a.band,a.allowed});}
 for(unsigned i=0;i<n;i++)for(unsigned j=0;j<e;j++){
  auto a=sx[i],b=ex[j];unsigned d=std::abs(int(a.p)-b.p);
  xpair[32*i+j]={uint16_t(d+a.fee),uint16_t(a.permit|(b.permit<<4)|((a.s^b.s)==2)|((a.s==1&&b.s==1)?2:0))};
 }
 for(unsigned i=0;i<m;i++)for(unsigned j=0;j<f;j++){
  auto a=sy[i],b=ey[j];unsigned d=std::abs(int(a.p)-b.p);
  ypair[16*i+j]={uint16_t(d+a.fee),uint16_t(((a.permit|(b.permit<<4))^4080)|(a.s==b.s&&!(a.s&1))|(((a.s^b.s)>=2)?2:0))};
  require(d+a.fee<256,"endpoint Y width");
 }
 require(n<=100&&m<=40&&e==18&&f==11,"frozen axis classes");
}
}
