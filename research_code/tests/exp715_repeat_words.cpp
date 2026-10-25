#include "architecture.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <string>
#include <vector>

using Word = std::vector<uint8_t>;
struct Term715 { uint32_t unit, repeats; };
struct Choice715 { unsigned span=1, width=1; };

template <class T> std::vector<T> load715(const std::string& path, size_t offset=0) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    assert(input);
    const size_t bytes=size_t(input.tellg());
    assert(bytes>=offset && (bytes-offset)%sizeof(T)==0);
    std::vector<T> values((bytes-offset)/sizeof(T));
    input.seekg(offset);
    input.read(reinterpret_cast<char*>(values.data()), std::streamsize(bytes-offset));
    assert(input);
    return values;
}

template <class T> void save715(const std::string& path, const std::vector<T>& values) {
    FILE* output=std::fopen(path.c_str(),"wb");
    assert(output && std::fwrite(values.data(),sizeof(T),values.size(),output)==values.size());
    assert(std::fclose(output)==0);
}

std::vector<Choice715> partition715(const Word& word, unsigned maximum) {
    const unsigned size=unsigned(word.size());
    std::vector<unsigned> best(size+1,0);
    std::vector<Choice715> choice(size);
    for (unsigned at=size; at--;) {
        best[at]=1+best[at+1];
        for (unsigned width=1; width<=maximum && at+2*width<=size; ++width)
            for (unsigned span=2*width; at+span<=size; span+=width) {
                if (!std::equal(word.begin()+at,word.begin()+at+width,
                                word.begin()+at+span-width)) break;
                const unsigned cost=1+best[at+span];
                const auto old=choice[at];
                if (cost<best[at] || (cost==best[at] &&
                    (width<old.width || (width==old.width && span>old.span)))) {
                    best[at]=cost;
                    choice[at]={span,width};
                }
            }
    }
    return choice;
}

struct Program715 {
    std::map<Word,uint32_t> lookup;
    std::vector<Word> dictionary;
    std::vector<Term715> terms;
    std::vector<uint32_t> offsets{0};

    unsigned append(const Word& word, unsigned maximum) {
        const auto choice=partition715(word,maximum);
        const size_t start=terms.size();
        Word recovered;
        for (unsigned at=0; at<word.size();) {
            const auto step=choice[at];
            assert(step.width && step.span%step.width==0 && at+step.span<=word.size());
            Word unit(word.begin()+at,word.begin()+at+step.width);
            const auto found=lookup.emplace(unit,uint32_t(dictionary.size()));
            if (found.second) dictionary.push_back(unit);
            const unsigned count=step.span/step.width;
            terms.push_back({found.first->second,count});
            for (unsigned j=0;j<count;++j) recovered.insert(recovered.end(),unit.begin(),unit.end());
            at+=step.span;
        }
        assert(word==recovered && terms.size()<UINT32_MAX);
        offsets.push_back(uint32_t(terms.size()));
        return unsigned(terms.size()-start);
    }

    void save(const std::string& prefix) const {
        std::vector<std::array<uint8_t,5>> records;
        for (const auto& unit:dictionary) {
            std::array<uint8_t,5> record={uint8_t(unit.size()),255,255,255,255};
            std::copy(unit.begin(),unit.end(),record.begin()+1);
            records.push_back(record);
        }
        save715(prefix+".dictionary.u8",records);
        save715(prefix+".terms.u32",terms);
        save715(prefix+".offsets.u32",offsets);
    }
};

int arc715(const delayest::Architecture& arch, int source, int target) {
    if (source==target) return 0;
    int price=INT32_MAX;
    for (const auto& edge:arch.outgoingArcs(source))
        if (edge.to==target) price=std::min(price,edge.delay);
    assert(price!=INT32_MAX);
    return price;
}

int main(int argc, char** argv) {
    assert(argc==4);
    const std::string data=argv[1], output=argv[2];
    delayest::Architecture arch;
    arch.load(argv[3]);
    auto ports=arch.netSources();
    std::sort(ports.begin(),ports.end());
    assert(ports.size()==160);
    const auto queries=load715<std::array<int32_t,10>>(data+"/queries.bin",12);
    const auto lengths=load715<uint32_t>(data+"/paths.lengths.u32");
    const auto words=load715<uint8_t>(data+"/paths.words.u8");
    const auto sums=load715<std::array<int32_t,8>>(data+"/paths.summary.i32");
    assert(queries.size()==239616 && lengths.size()==queries.size() && sums.size()==queries.size());
    Program715 self, multi;
    std::vector<std::array<uint32_t,3>> counts;
    size_t start=0;
    uint64_t replayed=0;
    for (unsigned row=0;row<queries.size();++row) {
        const auto& q=queries[row];
        assert(start+lengths[row]<=words.size());
        Word word(words.begin()+start,words.begin()+start+lengths[row]);
        start+=lengths[row];
        int x=q[0],y=q[1],port=q[8],arc=0,block=0,line=0,dx=0,dy=0;
        assert(arch.exists(x,y));
        for (unsigned code:word) {
            assert(code<160);
            arc+=arc715(arch,port,ports[code]);
            const int net=arch.netOfOutput(ports[code]);
            const auto& description=arch.net(net);
            const auto edge=arch.resolveNet(x,y,net);
            assert(edge.valid);
            const int crossing=arch.lineDelayCrossing(delayest::Axis::Vertical,x,edge.x)+
                arch.lineDelayCrossing(delayest::Axis::Horizontal,y,edge.y);
            block+=edge.delay-crossing; line+=crossing;
            dx+=description.dx;dy+=description.dy;
            x=edge.x;y=edge.y;port=description.to;
            ++replayed;
        }
        arc+=arc715(arch,port,q[9]);
        assert(x==q[2] && y==q[3] && arc==sums[row][0] && block==sums[row][2]);
        assert(dx==sums[row][3] && dy==sums[row][4] && int(word.size())==sums[row][5]);
        const unsigned a=self.append(word,1), b=multi.append(word,4);
        assert(b<=a && a<=word.size() && line>=0);
        counts.push_back({unsigned(word.size()),a,b});
    }
    assert(start==words.size());
    self.save(output+"/S");multi.save(output+"/M");save715(output+"/counts.u32",counts);
    std::printf("{\"all_checks_passed\":true,\"rows\":%zu,\"replayed_net_hops\":%llu,"
                "\"self_units\":%zu,\"multi_units\":%zu,\"self_calls\":%zu,\"multi_calls\":%zu}\n",
        queries.size(),(unsigned long long)replayed,self.dictionary.size(),multi.dictionary.size(),
        self.terms.size(),multi.terms.size());
}
