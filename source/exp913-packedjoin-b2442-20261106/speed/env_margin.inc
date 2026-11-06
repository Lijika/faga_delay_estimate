// Model keys come from translated resolved graph neighborhoods and directed endpoint roles.
namespace envcert {
extern "C" const uint8_t envFrames[],envEnd[];asm(".pushsection .rodata\n.p2align 12\n.global envFrames,envEnd\nenvFrames:\n.incbin \"env.zst\"\nenvEnd:\n.p2align 12\n.popsection");
static constexpr unsigned E=192,V=82,W=18;
static uint16_t ctx[66000];static uint32_t rows[E*208*13],wordrows[V*18],words[W*16];
static void ready(){const auto* p=envFrames;void* bufs[]={ctx,rows,wordrows,words};const size_t size[]={sizeof(ctx),sizeof(rows),sizeof(wordrows),sizeof(words)},z[]={457,623,108,33};
 for(int k=0;k<4;k++){require(ZSTD_decompress(bufs[k],size[k],p,z[k])==size[k],"specialized bounds");p+=z[k];}require(p==envEnd,"specialized lengths");}
__attribute__((noinline)) static int cert(int x,int y,int s,int X,int Y,int t,int a){
 if(a<0||unsigned(x)>=120||unsigned(y)>=550||unsigned(X)>=120||unsigned(Y)>=550||unsigned(s)>=496||unsigned(t)>=496)return a;
 int prior=stripe::cert(x,y,s,X,Y,t,a);unsigned e=ctx[y*120+x];if(e==65535)return prior;
 int sr=ports707[s].source,tr=ports707[t].target;if(sr<0||tr<0)return prior;unsigned dx=unsigned(X-x+2),dy=unsigned(Y-y+2);
 static constexpr int8_t dm[25]={-1,-1,0,-1,-1,-1,1,2,3,-1,4,5,6,7,8,-1,9,10,11,-1,-1,-1,12,-1,-1};if(dx>4||dy>4)return prior;int d=dm[dx*5+dy];if(d<0)return prior;
 unsigned ss=aqfar::atlas855::sm[sr],tt=aqfar::atlas855::tm[tr];unsigned r=rows[(e*208+ss)*13+d],b=wordrows[r*18+tt/16],v=words[16*b+tt%16];
 if(!v)return prior;return std::clamp(prior,int(v&65535)-1,int(v>>16));}
static inline int small(const int*q,int a){return a>=0&&std::abs(q[0]-q[2])+std::abs(q[1]-q[3])<=2?cert(q[0],q[1],q[8],q[2],q[3],q[9],a):a;}
}
