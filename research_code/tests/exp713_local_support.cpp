#include "architecture.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <vector>

template <class T> void save713(const std::string& path, const std::vector<T>& values) {
    std::ofstream out(path, std::ios::binary);
    out.write(reinterpret_cast<const char*>(values.data()), values.size()*sizeof(T));
    out.close();
    assert(out);
}

int main(int argc, char** argv) {
    assert(argc==3);
    delayest::Architecture arch;
    arch.loadEmbedded();
    const std::string output=argv[2];
    std::set<std::pair<int,int>> distinct;
    for (int n=0; n<arch.netCount(); ++n) distinct.emplace(arch.net(n).dx,arch.net(n).dy);
    assert(distinct.size()==16 && arch.portCount()==496 && arch.netCount()==160);
    std::vector<std::array<int16_t,2>> motions;
    std::map<std::pair<int,int>,unsigned> ids;
    for (auto m:distinct) {
        ids[m]=unsigned(motions.size());
        motions.push_back({int16_t(m.first),int16_t(m.second)});
    }
    std::vector<unsigned> kinds(160);
    std::vector<int> representatives(16,-1);
    for (int n=0; n<160; ++n) {
        kinds[n]=ids.at({arch.net(n).dx,arch.net(n).dy});
        representatives[kinds[n]]=n;
    }
    std::vector<std::array<uint16_t,2>> cells(66000), ports(496);
    uint64_t legal=0;
    for (int y=0; y<550; ++y) for (int x=0; x<120; ++x) {
        if (!arch.exists(x,y)) continue;
        for (unsigned m=0; m<16; ++m) {
            const auto e=arch.resolveNet(x,y,representatives[m]);
            if (!e.valid) continue;
            assert(arch.exists(e.x,e.y));
            cells[y*120+x][0]|=uint16_t(1u<<m);
            cells[e.y*120+e.x][1]|=uint16_t(1u<<m);
            ++legal;
        }
    }
    for (int p=0; p<496; ++p) {
        for (const auto& a:arch.outgoingArcs(p)) {
            const int n=arch.netOfOutput(a.to);
            if (n>=0) ports[p][0]|=uint16_t(1u<<kinds[n]);
        }
    }
    for (int n=0; n<160; ++n) {
        const int input=arch.net(n).to;
        ports[input][1]|=uint16_t(1u<<kinds[n]);
        for (const auto& a:arch.outgoingArcs(input)) ports[a.to][1]|=uint16_t(1u<<kinds[n]);
    }
    save713(output+"/motions.i16",motions);
    save713(output+"/cells.u16",cells);
    save713(output+"/ports.u16",ports);
    std::ifstream query(argv[1],std::ios::binary);
    char magic[8];
    uint32_t count;
    query.read(magic,8);
    query.read(reinterpret_cast<char*>(&count),4);
    assert(query && std::memcmp(magic,"EX535Q01",8)==0 && count==1000000);
    std::vector<std::array<uint16_t,4>> features(count);
    for (unsigned i=0; i<count; ++i) {
        std::array<int32_t,10> q;
        query.read(reinterpret_cast<char*>(q.data()),sizeof(q));
        assert(query && arch.exists(q[0],q[1]) && arch.exists(q[2],q[3]));
        int x=q[0],y=q[1],p=q[8];
        assert(p>=0 && p<496 && q[9]>=0 && q[9]<496);
        const int n=arch.netOfOutput(p);
        if (n>=0) {
            const auto e=arch.resolveNet(x,y,n);
            assert(e.valid);
            x=e.x; y=e.y; p=arch.net(n).to;
        }
        features[i]={uint16_t(x),uint16_t(y),uint16_t(cells[y*120+x][0]&ports[p][0]),
            uint16_t(cells[q[3]*120+q[2]][1]&ports[q[9]][1])};
    }
    assert(query.peek()==std::char_traits<char>::eof());
    save713(output+"/features.u16",features);
    std::printf("{\"rows\":%u,\"motions\":16,\"ports\":496,\"positions\":66000,"
        "\"legal_motion_edges\":%llu}\n",count,(unsigned long long)legal);
}
