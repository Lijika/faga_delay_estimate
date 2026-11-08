#include "build/exp499/roles.hpp"
#include <cstdio>
#include <cstdlib>
struct Tail{int h,x,y,w;};struct Output{int direct=kInf;std::vector<Tail> arcs;};
int main(int argc,char**argv){
 if(argc!=6)return 2;Architecture a;a.load(argv[1]);int source=std::atoi(argv[2]);Graph g(a);int sid=sourceGraph(g,a,source);auto f=solve(g,sid,162,612);std::vector<uint8_t> seen((f.d.size()+7)/8);
 std::ifstream ord(argv[3]),kn(argv[4]);std::vector<int> order,cells;int v;while(ord>>v)order.push_back(v);while(kn>>v)cells.push_back(v);int nk=cells.size()/4;if(order.size()!=288||nk<=40||nk>64||cells.size()%4)return 3;
 auto tgt=roleTargets(a);std::vector<int> idx(a.portCount(),-1);for(int i=0;i<160;i++)idx[g.ports[i]]=i;std::vector<Output> list;
 for(auto t:order){int p=tgt[t];Output out;if(idx[p]>=0)out.arcs.push_back({idx[p],0,0,0});else for(auto e:a.incomingArcs(p)){int net=a.netOfInput(e.to);if(net>=0){auto n=a.net(net);out.arcs.push_back({idx[n.from],n.dx,n.dy,e.delay});}else if(e.to==source)out.direct=std::min(out.direct,e.delay);}list.push_back(out);}
 FILE* out=fopen(argv[5],"wb");if(!out)return 4;uint16_t row[288];
 for(int c=0;c<480;c++){int d=c/120;for(int k=0;k<nk;k++){int j=cells[d*nk+k],qx=j/46,qy=j%46,x=(10*qx+c%120/12)*(d>=2?-1:1),y=(12*qy+c%12)*(d%2?-1:1);for(int t=0;t<288;t++){auto& out=list[t];int best=(!x&&!y)?out.direct:kInf;
   for(auto q:out.arcs){int u=x-q.x,w=y-q.y,id=f.id(u,w,q.h);auto &b=seen[id>>3];int m=1<<(id&7);if(!(b&m)){if(!f.certified(g,u,w,q.h))return 5;b|=m;}best=std::min(best,f.d[id]+q.w);}
   if(best>=32767)return 6;row[t]=uint16_t(int16_t(best-125*qx-(d%2?125:127)*qy));
  }if(fwrite(row,2,288,out)!=288)return 7;
 }}return fclose(out);
}
