namespace newring {
extern "C" const uint8_t rrdata[];asm(".pushsection .rodata\n.p2align 12\n.global rrdata\nrrdata:\n.incbin \"newfield.zst\"\n.p2align 12\n.popsection");
static unsigned char* rbase;static unsigned char* fbase;constexpr int8_t rmap[(2*4+1)*(2*4+1)]={-1,-1,-1,-1,0,-1,-1,-1,-1,-1,-1,-1,1,2,3,-1,-1,-1,-1,-1,4,5,-1,6,7,-1,-1,-1,8,9,-1,-1,-1,10,11,-1,12,13,-1,-1,-1,-1,-1,14,15,-1,16,17,-1,-1,-1,18,19,-1,-1,-1,20,21,-1,22,23,-1,-1,-1,-1,-1,24,25,26,-1,-1,-1,-1,-1,-1,-1,27,-1,-1,-1,-1};
#if 0
static constexpr int16_t fmap[(2*0+1)*(2*0+1)]={0};
#endif
static unsigned char* load(size_t pos,size_t n,size_t m){auto* p=(unsigned char*)mmap(nullptr,m,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);require(p!=MAP_FAILED,"ring lookup allocation");require(ZSTD_decompress(p,m,rrdata+pos,n)==m,"ring code");uintptr_t l=(uintptr_t(rrdata+pos)+4095)&~uintptr_t(4095),h=uintptr_t(rrdata+pos+n)&~uintptr_t(4095);if(h>l)require(munmap((void*)l,h-l)==0,"release ring code");return p;}
static void init(){rbase=load(0,2517356,18890596);
#if 0
 fbase=load(2519040,0,0);
#endif
}
static inline int nom(int S,int T,int dx,int dy){int d=(dx<0?2:0)+(dy<0),ax=std::abs(dx),ay=std::abs(dy),x=ax/10,y=ay/12;unsigned c=d*120+(ax%10)*12+ay%12,k=(S*288u+T)*480+c;auto p=aqfar::locate(k);return 125*x+(d%2?125:127)*y+aqfar::nearFlat(p,x*8+y,aqfar::baseFlat(p),p[58]);}
static inline unsigned bytePrice(unsigned h,int x){auto z=(const uint32_t*)(rbase+13418496)+h*2;auto m=(const uint64_t*)(rbase+14762056)+2*z[0];uint64_t bits=~0ull>>(63-(x&63));unsigned r=__builtin_popcountll(m[x>>6]&bits)+(x>=64?__builtin_popcountll(m[0]):0);return rbase[15319848+z[1]+r];}
__attribute__((noinline)) static int apply(int x,int y,int s,int X,int Y,int t,int old,int dist){
 if(old<0||unsigned(s)>=496||unsigned(t)>=496||dist<3)return old;int S=stripe::src[s],T=stripe::dst[t];if(S<0||T<0)return old;
 int xx=x,yy=y,dsx=X-x,dsy=Y-y,dx=dsx,dy=dsy,c=0,ni=arch.netOfOutput(s);
 if(ni>=0){auto a=arch.resolveNet(x,y,ni);if(!a.valid)return old;xx=a.x;yy=a.y;c=a.delay;dx-=(xx-x)-arch.net(ni).dx;dy-=(yy-y)-arch.net(ni).dy;}
 unsigned pair=S*288u+T;int dR=(dist<=4)?rmap[(dsx+4)*(2*4+1)+dsy+4]:-1;unsigned flags=0;
#if 0
 if(unsigned(dx+0)<=2*0&&unsigned(dy+0)<=2*0){int d=fmap[(dx+0)*(2*0+1)+dy+0];if(d>=0){unsigned j=pair*0+d;flags=(fbase[j>>2]>>(2*(j&3)))&3u;}}
#endif
 if(dR<0&&!flags)return old;
 int phi=c+arch.lineDelayCrossing(delayest::Axis::Vertical,xx,X)+arch.lineDelayCrossing(delayest::Axis::Horizontal,yy,Y)+nom(ports707[s].source,ports707[t].target,dx,dy);int v=old;
 if(dR>=0){
   unsigned j=(dR*59904u+pair)*2;auto* ids=(const uint32_t*)(rbase+0)+j;uint8_t price=uint8_t(bytePrice(ids[0],x));if(y%100<50)price=uint8_t(price+bytePrice(ids[1],x));if(price!=128u)v=phi+int(int8_t(price))*8;
 }
 if(flags&1)v=std::max(v,phi);
 if((flags&2)&&!(std::min(xx,X)<=15&&std::min(yy,Y)<=99)&&!(std::min(xx,X)<=89&&std::max(xx,X)>=76&&(std::min(yy,Y)%100<50||std::min(yy,Y)/100!=std::max(yy,Y)/100)))v=std::min(v,phi);
 return v;}
static inline int scalar(const int* q,int v){int d=std::abs(q[0]-q[2])+std::abs(q[1]-q[3]);return d>=3&&d<=4?apply(q[0],q[1],q[8],q[2],q[3],q[9],v,d):v;}
}