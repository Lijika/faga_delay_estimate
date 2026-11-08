// Model keys come from translated resolved graph neighborhoods and directed endpoint roles.
namespace envcert {
extern "C" const uint8_t envFrames[],envEnd[];asm(".pushsection .rodata\n.p2align 12\n.global envFrames,envEnd\nenvFrames:\n.incbin \"env.zst\"\nenvEnd:\n.p2align 12\n.popsection");
struct Filter {
 uint8_t context[66000];
 uint16_t except_target[9][208][13];
};
static Filter filter;
static_assert(sizeof(Filter)==114672);
static void ready(){
 require(ZSTD_decompress(&filter,sizeof(filter),envFrames,envEnd-envFrames)==sizeof(filter),"certificate filter size");
}
static inline int refine(int x,int y,int s,int X,int Y,int t,int prior){
 const unsigned e=filter.context[120*y+x];if(!e)return prior;
 const int sr=ports707[s].source,tr=ports707[t].target;if(sr<0||tr<0)return prior;
 const unsigned dx=unsigned(X-x+2),dy=unsigned(Y-y+2);if(dx>=5||dy>=5)return prior;
 const int d=stripe::disp[dx*5+dy];if(d<0)return prior;
 const unsigned ss=aqfar::atlas855::sm[sr],tt=aqfar::atlas855::tm[tr];
 const uint16_t except=filter.except_target[e][ss][d];
 return except!=65535&&except!=tt?std::clamp(prior,1651,65535):prior;
}
__attribute__((noinline)) static int cert(int x,int y,int s,int X,int Y,int t,int a){
 if(a<0||unsigned(x)>=120||unsigned(y)>=550||unsigned(X)>=120||unsigned(Y)>=550||unsigned(s)>=496||unsigned(t)>=496)return a;
 return refine(x,y,s,X,Y,t,stripe::cert(x,y,s,X,Y,t,a));
}
static inline int small(const int*q,int a){return a>=0&&std::abs(q[0]-q[2])+std::abs(q[1]-q[3])<=2?cert(q[0],q[1],q[8],q[2],q[3],q[9],a):a;}
}
