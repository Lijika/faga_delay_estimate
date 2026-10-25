#include "architecture.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <vector>

using delayest::Architecture;
using delayest::ResolvedEdge;
#include "exp193_analytic.h"

template <class T> std::vector<T> load(const std::string& path, size_t offset = 0) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    assert(f);
    const size_t bytes = size_t(f.tellg());
    assert(bytes >= offset && (bytes-offset) % sizeof(T) == 0);
    std::vector<T> out((bytes-offset)/sizeof(T));
    f.seekg(offset);
    f.read(reinterpret_cast<char*>(out.data()), std::streamsize(bytes-offset));
    assert(f);
    return out;
}

struct Value710 {
    uint16_t end;
    int16_t shift;
    uint16_t block, line;
    bool same(const Value710& b) const {
        return shift == b.shift && block == b.block && line == b.line;
    }
    bool operator==(const Value710& b) const { return end == b.end && same(b); }
    bool operator<(const Value710& b) const {
        return std::tie(end,shift,block,line) < std::tie(b.end,b.shift,b.block,b.line);
    }
};
struct Band710 { uint16_t end, row; };
struct Row710 { uint32_t start; uint16_t count, reserved=0; };
static_assert(sizeof(Value710)==8 && sizeof(Band710)==4 && sizeof(Row710)==8);

struct Map710 {
    std::vector<Band710> bands;
    std::vector<Row710> rows;
    std::vector<Value710> cells;
    unsigned maxComparisons=0;

    Value710 at(unsigned x, unsigned y, unsigned& comparisons) const {
        size_t lo=0, hi=bands.size();
        while (lo<hi) {
            ++comparisons;
            const size_t mid=(lo+hi)/2;
            if (bands[mid].end<=y) lo=mid+1; else hi=mid;
        }
        assert(lo<bands.size());
        const auto& row=rows[bands[lo].row];
        lo=row.start; hi=lo+row.count;
        while (lo<hi) {
            ++comparisons;
            const size_t mid=(lo+hi)/2;
            if (cells[mid].end<=x) lo=mid+1; else hi=mid;
        }
        assert(lo<row.start+row.count);
        return cells[lo];
    }
};

Map710 compile710(const std::vector<Value710>& grid, bool full) {
    Map710 result;
    std::map<std::vector<Value710>,uint16_t> dictionary;
    for (unsigned y=0; y<550; ++y) {
        std::vector<Value710> row;
        for (unsigned x=0; x<120; ++x) {
            auto value=grid[y*120+x];
            value.end=uint16_t(x+1);
            if (!full) value.line=0;
            if (!row.empty() && row.back().same(value)) row.back().end=value.end;
            else row.push_back(value);
        }
        assert(dictionary.size()<65536);
        auto added=dictionary.emplace(row,uint16_t(dictionary.size()));
        const uint16_t id=added.first->second;
        if (added.second) {
            result.rows.push_back({uint32_t(result.cells.size()),uint16_t(row.size()),0});
            result.cells.insert(result.cells.end(),row.begin(),row.end());
        }
        if (!result.bands.empty() && result.bands.back().row==id)
            result.bands.back().end=uint16_t(y+1);
        else result.bands.push_back({uint16_t(y+1),id});
    }
    for (unsigned y=0; y<550; ++y) for (unsigned x=0; x<120; ++x) {
        unsigned comparisons=0;
        auto value=result.at(x,y,comparisons), expected=grid[y*120+x];
        if (!full) expected.line=0;
        assert(value.same(expected));
        result.maxComparisons=std::max(result.maxComparisons,comparisons);
    }
    return result;
}

uint64_t save710(FILE* f, const Map710& map, uint32_t id, int16_t dx, int16_t dy, bool full) {
    const uint16_t bands=uint16_t(map.bands.size()), rows=uint16_t(map.rows.size());
    const uint32_t cells=uint32_t(map.cells.size());
    assert(std::fwrite(&id,4,1,f)==1 && std::fwrite(&bands,2,1,f)==1 &&
           std::fwrite(&rows,2,1,f)==1 && std::fwrite(&cells,4,1,f)==1 &&
           std::fwrite(&dx,2,1,f)==1 && std::fwrite(&dy,2,1,f)==1);
    assert(std::fwrite(map.bands.data(),4,bands,f)==bands &&
           std::fwrite(map.rows.data(),8,rows,f)==rows);
    for (const auto& c:map.cells) assert(std::fwrite(&c,full?8:6,1,f)==1);
    return 16+4*uint64_t(bands)+8*uint64_t(rows)+(full?8:6)*uint64_t(cells);
}

int arc710(const Architecture& arch, int from, int to) {
    if (from==to) return 0;
    int cost=INT_MAX;
    for (const auto& a:arch.outgoingArcs(from)) if (a.to==to) cost=std::min(cost,a.delay);
    assert(cost<INT_MAX);
    return cost;
}

int main(int argc, char** argv) {
    assert(argc==5);
    const std::string data=argv[1], samples=argv[2], output=argv[3], archPath=argv[4];
    Architecture arch;
    arch.load(archPath);
    assert(arch.portCount()==496 && arch.netCount()==160);
    const auto q=load<std::array<int32_t,10>>(data+"/queries.bin",12);
    const auto lengths=load<uint32_t>(data+"/paths.lengths.u32");
    const auto words=load<uint8_t>(data+"/paths.words.u8");
    const auto sums=load<std::array<int32_t,8>>(data+"/paths.summary.i32");
    const auto sample=load<uint32_t>(samples);
    assert(q.size()==239616 && q.size()==lengths.size() && q.size()==sums.size() && sample.size()==1040);
    std::vector<int> ports=arch.netSources();
    std::sort(ports.begin(),ports.end());
    std::vector<size_t> offsets(q.size()+1,0);
    std::map<std::pair<int,int>,uint8_t> motions;
    std::array<int,160> nets{};
    std::array<uint8_t,160> types{};
    std::vector<int> representatives;
    for (int j=0; j<160; ++j) {
        nets[j]=arch.netOfOutput(ports[j]);
        const auto& n=arch.net(nets[j]);
        auto added=motions.emplace(std::make_pair(n.dx,n.dy),uint8_t(motions.size()));
        types[j]=added.first->second;
        if (added.second) representatives.push_back(nets[j]);
    }
    assert(motions.size()==16);
    std::map<std::vector<uint8_t>,uint32_t> geometry;
    std::set<std::vector<uint16_t>> complete;
    std::vector<std::vector<uint8_t>> sequences;
    std::vector<uint32_t> group(q.size());
    std::vector<int> firstPair, sharedPair;
    FILE* catalogue=std::fopen((output+"/catalogue.i32").c_str(),"wb");
    assert(catalogue);
    uint64_t originHops=0;
    for (size_t i=0; i<q.size(); ++i) {
        offsets[i+1]=offsets[i]+lengths[i];
        assert(offsets[i+1]<=words.size());
        std::vector<uint8_t> sequence;
        std::vector<uint16_t> full={uint16_t(q[i][8]),uint16_t(q[i][9])};
        int x=q[i][0],y=q[i][1],p=q[i][8],arc=0,block=0,line=0,dx=0,dy=0,runs=0;
        assert(arch.exists(x,y));
        for (size_t at=offsets[i]; at<offsets[i+1]; ++at) {
            const unsigned c=words[at];
            assert(c<160);
            if (sequence.empty() || sequence.back()!=types[c]) ++runs;
            sequence.push_back(types[c]); full.push_back(uint16_t(c));
            arc+=arc710(arch,p,ports[c]);
            const auto e=arch.resolveNet(x,y,nets[c]);
            const auto a=analytic(arch,x,y,nets[c]);
            assert(e.valid && a.valid && e.x==a.x && e.y==a.y && e.delay==a.delay);
            const int l=arch.lineDelayCrossing(delayest::Axis::Vertical,x,e.x)+
                        arch.lineDelayCrossing(delayest::Axis::Horizontal,y,e.y);
            line+=l; block+=e.delay-l;
            const auto& n=arch.net(nets[c]);
            dx+=n.dx; dy+=n.dy; x=e.x; y=e.y; p=n.to;
            ++originHops;
        }
        arc+=arc710(arch,p,q[i][9]);
        assert(x==q[i][2] && y==q[i][3] && arc==sums[i][0] &&
               block==sums[i][2] && dx==sums[i][3] && dy==sums[i][4]);
        auto added=geometry.emplace(sequence,uint32_t(geometry.size()));
        group[i]=added.first->second;
        if (added.second) { sequences.push_back(sequence); firstPair.push_back(int(i/4)); sharedPair.push_back(0); }
        else if (firstPair[group[i]]!=int(i/4)) sharedPair[group[i]]=1;
        complete.insert(std::move(full));
        const int32_t record[6]={int32_t(group[i]),arc,dx,dy,line,runs};
        assert(std::fwrite(record,4,6,catalogue)==6);
    }
    assert(offsets.back()==words.size() && std::fclose(catalogue)==0);
    std::ofstream table(output+"/maps.csv");
    table<<"sample_row,geometry_id,hops,kind,y_segments,unique_rows,x_segments,bytes,max_ordered_comparisons,valid_positions\n";
    FILE* binary[2]={std::fopen((output+"/support.bin").c_str(),"wb"),
                     std::fopen((output+"/full.bin").c_str(),"wb")};
    assert(table && binary[0] && binary[1]);
    std::set<uint32_t> seen;
    uint64_t referenceHops=0, points=0;
    for (unsigned i:sample) {
        assert(i<q.size());
        const uint32_t id=group[i];
        if (!seen.insert(id).second) continue;
        int dx=0,dy=0;
        for (unsigned c:sequences[id]) { dx+=arch.net(representatives[c]).dx; dy+=arch.net(representatives[c]).dy; }
        assert(dx>=INT16_MIN && dx<=INT16_MAX && dy>=INT16_MIN && dy<=INT16_MAX);
        std::vector<Value710> grid(66000);
        unsigned valid=0;
        for (int sy=0; sy<550; ++sy) {
            int last=-1;
            for (int sx=0; sx<120; ++sx) {
                int x=sx,y=sy,block=0,line=0;
                bool ok=arch.exists(x,y);
                for (unsigned c:sequences[id]) {
                    if (!ok) break;
                    const auto e=analytic(arch,x,y,representatives[c]);
                    ok=e.valid;
                    if (!ok) break;
                    const int l=arch.lineDelayCrossing(delayest::Axis::Vertical,x,e.x)+
                                arch.lineDelayCrossing(delayest::Axis::Horizontal,y,e.y);
                    block+=e.delay-l; line+=l; x=e.x; y=e.y;
                }
                int rx=sx,ry=sy,fee=0;
                bool rok=arch.exists(rx,ry);
                for (size_t at=offsets[i]; rok && at<offsets[i+1]; ++at) {
                    const auto e=arch.resolveNet(rx,ry,nets[words[at]]);
                    ++referenceHops; rok=e.valid;
                    if (rok) { rx=e.x; ry=e.y; fee+=e.delay; }
                }
                assert(ok==rok && (!ok || (x==rx && y==ry && block+line==fee)));
                Value710 value{0,INT16_MIN,0,0};
                if (ok) {
                    assert(y-sy==dy && x>last && block>=0 && block<=65535 && line>=0 && line<=65535);
                    assert(x-sx-dx>INT16_MIN && x-sx-dx<=INT16_MAX);
                    value={0,int16_t(x-sx-dx),uint16_t(block),uint16_t(line)};
                    last=x; ++valid;
                }
                grid[sy*120+sx]=value;
                ++points;
            }
        }
        for (unsigned full=0; full<2; ++full) {
            const auto map=compile710(grid,full);
            const auto bytes=save710(binary[full],map,id,int16_t(dx),int16_t(dy),full);
            table<<i<<','<<id<<','<<lengths[i]<<','<<(full?'F':'S')<<','<<map.bands.size()
                 <<','<<map.rows.size()<<','<<map.cells.size()<<','<<bytes<<','<<map.maxComparisons
                 <<','<<valid<<'\n';
        }
        if (seen.size()%64==0) std::fprintf(stderr,"EXP710_COMPILED %zu\n",seen.size());
    }
    table.close();
    assert(table && std::fclose(binary[0])==0 && std::fclose(binary[1])==0);
    unsigned shared=0;
    for (int x:sharedPair) shared+=x;
    std::printf("{\"all_equal\":true,\"rows\":%zu,\"full_words\":%zu,\"motion_words\":%zu,"
        "\"cross_pair_motion_words\":%u,\"sampled_motion_words\":%zu,\"certified_positions\":%llu,"
        "\"origin_hops\":%llu,\"reference_hops\":%llu}\n",q.size(),complete.size(),geometry.size(),
        shared,seen.size(),(unsigned long long)points,(unsigned long long)originHops,
        (unsigned long long)referenceHops);
}
