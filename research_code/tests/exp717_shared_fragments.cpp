#include "exp710_functions.h"
#include "exp715_functions.h"

struct Trie717 {
    std::array<int,16> next;
    bool terminal=false;
    Trie717() { next.fill(-1); }
};
struct Binding717 {
    uint32_t start;
    int32_t arc;
    int16_t dx,dy;
    uint16_t source,target;
};
static_assert(sizeof(Binding717)==16);

std::vector<unsigned> partition717(const Word& word, const Word& motion,
                                   const std::vector<Trie717>& trie) {
    const unsigned n=unsigned(word.size());
    std::vector<unsigned> cost(n+1), spans(n,1);
    for (unsigned at=n; at--;) {
        cost[at]=1+cost[at+1];
        const auto offer=[&](unsigned span) {
            const unsigned value=1+cost[at+span];
            if (value<cost[at] || (value==cost[at] && span>spans[at])) {
                cost[at]=value;spans[at]=span;
            }
        };
        for (unsigned width=1;width<=4 && at+2*width<=n;++width)
            for (unsigned span=2*width;at+span<=n;span+=width) {
                if (!std::equal(word.begin()+at,word.begin()+at+width,
                                word.begin()+at+span-width)) break;
                offer(span);
            }
        int node=0;
        for (unsigned k=at;k<n && k<at+12;++k) {
            node=trie[node].next[motion[k]];
            if (node<0) break;
            if (trie[node].terminal) offer(k-at+1);
        }
    }
    return spans;
}

void save_words717(const std::string& prefix,const std::vector<Word>& words) {
    std::vector<uint32_t> lengths;
    std::vector<uint8_t> text;
    for (const auto& w:words) {
        lengths.push_back(uint32_t(w.size()));
        text.insert(text.end(),w.begin(),w.end());
    }
    save715(prefix+".lengths.u32",lengths);
    save715(prefix+".words.u8",text);
}

int main(int argc,char** argv) {
    assert(argc==5);
    const std::string data=argv[1],output=argv[2];
    Architecture arch;arch.load(argv[3]);
    const auto queries=load715<std::array<int32_t,10>>(data+"/queries.bin",12);
    const auto lengths=load715<uint32_t>(data+"/paths.lengths.u32");
    const auto raw=load715<uint8_t>(data+"/paths.words.u8");
    const auto sums=load715<std::array<int32_t,8>>(data+"/paths.summary.i32");
    const auto baseline=load715<std::array<uint32_t,3>>(argv[4]);
    assert(queries.size()==239616 && lengths.size()==queries.size() &&
           sums.size()==queries.size() && baseline.size()==queries.size());
    auto ports=arch.netSources();std::sort(ports.begin(),ports.end());
    assert(ports.size()==160);
    std::map<std::pair<int,int>,uint8_t> motion_ids;
    std::vector<int> representatives;
    std::array<int,160> nets;
    std::array<uint8_t,160> types;
    for (unsigned code=0;code<160;++code) {
        nets[code]=arch.netOfOutput(ports[code]);
        const auto& n=arch.net(nets[code]);
        auto added=motion_ids.emplace(std::make_pair(n.dx,n.dy),uint8_t(motion_ids.size()));
        types[code]=added.first->second;
        if (added.second) representatives.push_back(nets[code]);
    }
    assert(representatives.size()==16);
    save715(output+"/types.u8",std::vector<uint8_t>(types.begin(),types.end()));
    std::vector<std::array<int16_t,2>> deltas;
    for (int net:representatives) {
        const auto& n=arch.net(net);deltas.push_back({int16_t(n.dx),int16_t(n.dy)});
    }
    save715(output+"/motions.i16",deltas);
    std::vector<Word> words,motions;
    std::map<Word,uint32_t> frequency;
    size_t begin=0;
    for (unsigned row=0;row<queries.size();++row) {
        assert(begin+lengths[row]<=raw.size());
        words.emplace_back(raw.begin()+begin,raw.begin()+begin+lengths[row]);
        begin+=lengths[row];
        Word m;
        for (unsigned code:words.back()) { assert(code<160);m.push_back(types[code]); }
        motions.push_back(std::move(m));
        const auto choice=partition715(words.back(),4);
        unsigned calls=0;
        for (unsigned at=0;at<choice.size();at+=choice[at].span) ++calls;
        assert(calls==baseline[row][2] && baseline[row][0]==lengths[row]);
        assert(queries[row][5]>=0 && queries[row][5]<8);
        if (queries[row][5]%4==3) continue;
        for (unsigned at=0;at<choice.size();) {
            if (choice[at].span!=1) { at+=choice[at].span;continue; }
            const unsigned start=at;
            while (at<choice.size() && choice[at].span==1) ++at;
            for (unsigned i=start;i<at;++i)
                for (unsigned size=2;size<=12 && i+size<=at;++size)
                    ++frequency[Word(motions.back().begin()+i,motions.back().begin()+i+size)];
        }
    }
    assert(begin==raw.size());
    std::vector<std::pair<Word,uint32_t>> ranked;
    for (const auto& item:frequency) if (item.second>=2) ranked.push_back(item);
    std::sort(ranked.begin(),ranked.end(),[](const auto& a,const auto& b) {
        const uint64_t av=uint64_t(a.second)*(a.first.size()-1);
        const uint64_t bv=uint64_t(b.second)*(b.first.size()-1);
        return av!=bv ? av>bv : a.first<b.first;
    });
    if (ranked.size()>512) ranked.resize(512);
    std::vector<Word> selected;
    std::vector<Trie717> trie(1);
    std::vector<uint32_t> selected_counts;
    for (const auto& item:ranked) {
        selected.push_back(item.first);selected_counts.push_back(item.second);
        int node=0;
        for (unsigned code:item.first) {
            int next=trie[node].next[code];
            if (next<0) {
                next=int(trie.size());trie[node].next[code]=next;trie.emplace_back();
            }
            node=next;
        }
        trie[node].terminal=true;
    }
    save_words717(output+"/selected",selected);save715(output+"/selected.counts.u32",selected_counts);
    std::map<Word,uint16_t> geometry_ids;
    std::vector<Word> geometry;
    std::vector<uint16_t> terms;
    std::vector<Binding717> bindings;
    std::vector<std::array<uint32_t,6>> counts;
    for (unsigned row=0;row<words.size();++row) {
        const auto& w=words[row];const auto& m=motions[row];const auto& q=queries[row];
        const auto spans=partition717(w,m,trie);
        int x=q[0],y=q[1],port=q[8],arc=0,block=0,line=0,dx=0,dy=0;
        const unsigned start=unsigned(terms.size());
        for (unsigned at=0;at<w.size();) {
            const unsigned span=spans[at];assert(span && at+span<=w.size());
            Word fragment(m.begin()+at,m.begin()+at+span);
            assert(geometry.size()<65535);
            auto added=geometry_ids.emplace(fragment,uint16_t(geometry.size()));
            if (added.second) geometry.push_back(fragment);
            terms.push_back(added.first->second);
            at+=span;
        }
        assert(arch.exists(x,y));
        for (unsigned code:w) {
            arc+=arc715(arch,port,ports[code]);
            const auto& n=arch.net(nets[code]);
            const auto e=arch.resolveNet(x,y,nets[code]);assert(e.valid);
            const int l=arch.lineDelayCrossing(delayest::Axis::Vertical,x,e.x)+
                        arch.lineDelayCrossing(delayest::Axis::Horizontal,y,e.y);
            block+=e.delay-l;line+=l;dx+=n.dx;dy+=n.dy;x=e.x;y=e.y;port=n.to;
        }
        arc+=arc715(arch,port,q[9]);
        assert(x==q[2] && y==q[3] && arc==sums[row][0] && block==sums[row][2] &&
               dx==sums[row][3] && dy==sums[row][4]);
        assert(dx>=INT16_MIN && dx<=INT16_MAX && dy>=INT16_MIN && dy<=INT16_MAX);
        const unsigned calls=unsigned(terms.size())-start;
        assert(calls<=baseline[row][2]);
        bindings.push_back({start,arc,int16_t(dx),int16_t(dy),uint16_t(q[8]),uint16_t(q[9])});
        counts.push_back({unsigned(w.size()),baseline[row][2],calls,0,0,unsigned(arc+block+line)});
    }
    save_words717(output+"/geometry",geometry);
    save715(output+"/terms.u16",terms);save715(output+"/bindings.bin",bindings);
    std::vector<Map710> maps;
    std::vector<std::array<int16_t,2>> gdeltas;
    std::ofstream table(output+"/maps.csv");
    table<<"geometry_id,hops,bytes,max_comparisons,valid_positions\n";
    FILE* binary=std::fopen((output+"/maps.bin").c_str(),"wb");assert(binary && table);
    uint64_t points=0,hops=0,map_bytes=0;
    for (unsigned id=0;id<geometry.size();++id) {
        int dx=0,dy=0;
        for (unsigned code:geometry[id]) { dx+=deltas[code][0];dy+=deltas[code][1]; }
        assert(dx>=INT16_MIN && dx<=INT16_MAX && dy>=INT16_MIN && dy<=INT16_MAX);
        std::vector<Value710> grid(66000);
        unsigned valid=0;
        for (int sy=0;sy<550;++sy) for (int sx=0;sx<120;++sx) {
            int x=sx,y=sy,fee=0,block=0,line=0;
            bool ok=arch.exists(x,y);
            for (unsigned code:geometry[id]) {
                if (!ok) break;
                const auto e=arch.resolveNet(x,y,representatives[code]);
                const auto a=analytic(arch,x,y,representatives[code]);
                ++hops;assert(e.valid==a.valid);
                ok=e.valid;
                if (!ok) break;
                assert(e.x==a.x && e.y==a.y && e.delay==a.delay);
                const int l=arch.lineDelayCrossing(delayest::Axis::Vertical,x,e.x)+
                            arch.lineDelayCrossing(delayest::Axis::Horizontal,y,e.y);
                block+=e.delay-l;line+=l;fee+=e.delay;x=e.x;y=e.y;
            }
            Value710 value{0,INT16_MIN,0,0};
            if (ok) {
                assert(y-sy==dy && x-sx-dx>INT16_MIN && x-sx-dx<=INT16_MAX);
                assert(block>=0 && block<=UINT16_MAX && line>=0 && line<=UINT16_MAX && fee==block+line);
                value={0,int16_t(x-sx-dx),uint16_t(block),uint16_t(line)};++valid;
            }
            grid[sy*120+sx]=value;++points;
        }
        maps.push_back(compile710(grid,true));gdeltas.push_back({int16_t(dx),int16_t(dy)});
        const auto bytes=save710(binary,maps.back(),id,int16_t(dx),int16_t(dy),true);
        map_bytes+=bytes;
        table<<id<<","<<geometry[id].size()<<","<<bytes<<","<<maps.back().maxComparisons<<","<<valid<<"\n";
    }
    assert(std::fclose(binary)==0);table.close();assert(table);
    for (unsigned row=0;row<queries.size();++row) {
        const auto& q=queries[row];const auto& binding=bindings[row];
        unsigned comparisons=0,worst=0;
        int x=q[0],y=q[1],block=0,line=0;
        const unsigned end=row+1<bindings.size()?bindings[row+1].start:unsigned(terms.size());
        for (unsigned at=binding.start;at<end;++at) {
            const unsigned id=terms[at];
            const auto v=maps[id].at(unsigned(x),unsigned(y),comparisons);
            assert(v.shift!=INT16_MIN);
            x+=gdeltas[id][0]+v.shift;y+=gdeltas[id][1];
            block+=v.block;line+=v.line;worst+=maps[id].maxComparisons;
            assert(arch.exists(x,y));
        }
        assert(x==q[2] && y==q[3] && block==sums[row][2] &&
               binding.arc+block+line==int(counts[row][5]));
        counts[row][3]=comparisons;counts[row][4]=worst;
    }
    save715(output+"/counts.u32",counts);
    std::printf("{\"all_checks_passed\":true,\"rows\":%zu,\"selected_fragments\":%zu,"
        "\"geometry_fragments\":%zu,\"checked_grid_points\":%llu,\"replayed_fragment_hops\":%llu,"
        "\"map_bytes\":%llu,\"terms\":%zu,\"binding_bytes\":%zu}\n",
        queries.size(),selected.size(),geometry.size(),(unsigned long long)points,
        (unsigned long long)hops,(unsigned long long)map_bytes,terms.size(),bindings.size()*sizeof(Binding717));
}
