namespace nativeQuery {
static uint32_t startCode[496],endCode[496],X[120][120],Y[551];
static void init(){
 int maxFee=0,maxPX=0,maxPY=0;
 for(const auto& t:route913::source){maxFee=std::max(maxFee,int(t.delay));maxPX=std::max(maxPX,int(t.priceX));maxPY=std::max(maxPY,int(t.priceY));}
 for(const auto& t:route913::target){maxPX=std::max(maxPX,int(t.priceX));maxPY=std::max(maxPY,int(t.priceY));}
 int b=0;for(auto v:kForcedBias)b=std::max(b,std::abs(int(v)));
 int h=0,v=0;for(auto a:eventHot::horizontal)h=std::max(h,std::abs(int(a)));for(auto a:eventHot::vertical)v=std::max(v,std::abs(int(a)));
 require(125*11+127*45+maxFee+maxPX+maxPY+std::max(h+b,v)<=32767,"native signed cost bounds");
 for(unsigned p=0;p<496;p++){
   const auto z=ports707[p];startCode[p]=z.source<0?UINT32_MAX:uint32_t(z.source)*138240u+uint32_t(shortgate::portClass[p]);
   endCode[p]=z.target<0?UINT32_MAX:uint32_t(z.target)*480u;
 }
 for(int sx=0;sx<120;sx++)for(int tx=0;tx<120;tx++){
   const auto a=aqfar::xs[sx][tx];X[sx][tx]=(a.left|(uint32_t(a.center)<<16))|(uint32_t(a.side)<<8);
 }
 for(int y=0;y<=550;y++){auto a=aqfar::ys[y];Y[y]=(uint32_t(a.low)<<16)|a.center;}
}
}
