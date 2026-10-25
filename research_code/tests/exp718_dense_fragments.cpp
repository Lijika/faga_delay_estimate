#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <map>
#include <string>
#include <tuple>
#include <vector>
#include <time.h>
#include "exp718_records.h"

template <class T> std::vector<T> load718(const std::string& path,size_t offset=0) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);assert(f);
    const size_t bytes=size_t(f.tellg());assert(bytes>=offset && (bytes-offset)%sizeof(T)==0);
    std::vector<T> out((bytes-offset)/sizeof(T));
    f.seekg(offset);f.read(reinterpret_cast<char*>(out.data()),std::streamsize(bytes-offset));
    assert(f);return out;
}

double cpu718() {
    timespec t{};assert(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)==0);
    return double(t.tv_sec)+double(t.tv_nsec)*1e-9;
}

uint64_t pack718(const Value710& v) {
    return uint64_t(uint16_t(v.shift))|(uint64_t(v.block)<<16)|(uint64_t(v.line)<<32);
}

struct Geometry718 {
    std::vector<Map710> maps;
    std::vector<std::array<int16_t,2>> delta;
    std::vector<uint32_t> index;
    std::vector<uint64_t> values;
    explicit Geometry718(const std::string& path) {
        struct Header { uint32_t id;uint16_t bands,rows;uint32_t cells;int16_t dx,dy; };
        static_assert(sizeof(Header)==16);
        FILE* file=std::fopen(path.c_str(),"rb");assert(file);
        Header h{};
        std::map<std::array<uint64_t,120>,uint32_t> shared;
        while (std::fread(&h,sizeof(h),1,file)==1) {
            assert(h.id==maps.size() && h.bands && h.rows && h.cells);
            Map710 m;
            m.bands.resize(h.bands);m.rows.resize(h.rows);m.cells.resize(h.cells);
            assert(std::fread(m.bands.data(),sizeof(Band710),h.bands,file)==h.bands);
            assert(std::fread(m.rows.data(),sizeof(Row710),h.rows,file)==h.rows);
            assert(std::fread(m.cells.data(),sizeof(Value710),h.cells,file)==h.cells);
            assert(m.bands.back().end==550);
            std::vector<uint32_t> dense_row(h.rows);
            for (unsigned row=0;row<h.rows;++row) {
                const auto& r=m.rows[row];
                assert(r.count && r.start+r.count<=m.cells.size());
                std::array<uint64_t,120> v{};
                unsigned x=0;
                for (unsigned at=r.start;at<r.start+r.count;++at) {
                    const auto& c=m.cells[at];assert(c.end>x && c.end<=120);
                    while (x<c.end) v[x++]=pack718(c);
                }
                assert(x==120 && values.size()+120<UINT32_MAX);
                auto added=shared.emplace(v,uint32_t(values.size()));
                if (added.second) values.insert(values.end(),v.begin(),v.end());
                dense_row[row]=added.first->second;
            }
            unsigned y=0;
            for (const auto& band:m.bands) {
                assert(band.row<h.rows && band.end>y && band.end<=550);
                while (y<band.end) { index.push_back(dense_row[band.row]);++y; }
            }
            assert(y==550);maps.push_back(std::move(m));delta.push_back({h.dx,h.dy});
        }
        assert(std::feof(file) && !std::ferror(file) && std::fclose(file)==0);
        assert(maps.size()==974 && index.size()==maps.size()*550);
    }
    template <bool Direct> uint64_t at(unsigned id,unsigned x,unsigned y) const {
        if constexpr (Direct) return values[index[id*550+y]+x];
        else {
            unsigned ignored=0;
            return pack718(maps[id].at(x,y,ignored));
        }
    }
    uint64_t bytes() const { return 8*values.size()+4*index.size()+4*delta.size(); }
};

struct Programs718 {
    Geometry718 geometry;
    std::vector<Binding717> bindings;
    std::vector<uint16_t> terms;
    std::vector<std::array<int32_t,10>> queries;
    std::vector<std::array<uint32_t,6>> counts;
    std::vector<uint32_t> order;
    Programs718(const std::string& data,const std::string& query,const std::string& permutation):
        geometry(data+"/maps.bin"),bindings(load718<Binding717>(data+"/bindings.bin")),
        terms(load718<uint16_t>(data+"/terms.u16")),
        queries(load718<std::array<int32_t,10>>(query,12)),
        counts(load718<std::array<uint32_t,6>>(data+"/counts.u32")),
        order(load718<uint32_t>(permutation)) {
        assert(queries.size()==239616 && bindings.size()==queries.size() &&
               counts.size()==queries.size() && order.size()==queries.size());
        auto sorted=order;std::sort(sorted.begin(),sorted.end());
        for (unsigned i=0;i<sorted.size();++i) assert(sorted[i]==i);
    }
    template <bool Direct> int evaluate(unsigned row,const std::array<int32_t,10>& q) const {
        const auto& b=bindings[row];
        if (b.source!=q[8] || b.target!=q[9] || unsigned(q[0])>=120 ||
            unsigned(q[1])>=550 || unsigned(q[2])>=120 || unsigned(q[3])>=550) return -1;
        int x=q[0],y=q[1],cost=b.arc;
        const unsigned end=row+1<bindings.size()?bindings[row+1].start:unsigned(terms.size());
        for (unsigned at=b.start;at<end;++at) {
            const unsigned id=terms[at];
            const uint64_t v=geometry.at<Direct>(id,unsigned(x),unsigned(y));
            const unsigned encoded=unsigned(v&65535);
            if (encoded==32768) return -1;
            const int shift=encoded<32768 ? int(encoded) : int(encoded)-65536;
            x+=geometry.delta[id][0]+shift;y+=geometry.delta[id][1];
            cost+=int((v>>16)&65535)+int((v>>32)&65535);
        }
        return x==q[2] && y==q[3] ? cost : -1;
    }
    template <bool Direct> uint64_t run(unsigned rounds) const {
        uint64_t checksum=1469598103934665603ull;
        for (unsigned round=0;round<rounds;++round)
            for (unsigned at=0;at<order.size();++at) {
                const unsigned id=order[(at+round*9973u)%order.size()];
                const int value=evaluate<Direct>(id,queries[id]);
                checksum=(checksum^uint32_t(value+id*65537u))*1099511628211ull;
            }
        return checksum;
    }
    uint64_t reference(unsigned rounds) const {
        uint64_t checksum=1469598103934665603ull;
        for (unsigned round=0;round<rounds;++round)
            for (unsigned at=0;at<order.size();++at) {
                const unsigned id=order[(at+round*9973u)%order.size()];
                checksum=(checksum^uint32_t(counts[id][5]+id*65537u))*1099511628211ull;
            }
        return checksum;
    }
};

int main(int argc,char** argv) {
    assert(argc==6);
    const double begin=cpu718();
    const Programs718 programs(argv[1],argv[2],argv[3]);
    const double initialization=cpu718()-begin;
    const char mode=argv[4][0];
    const unsigned rounds=unsigned(std::stoul(argv[5]));
    if (mode=='C') {
        uint64_t points=0;
        for (unsigned id=0;id<programs.geometry.maps.size();++id)
            for (unsigned y=0;y<550;++y) for (unsigned x=0;x<120;++x) {
                assert(programs.geometry.at<true>(id,x,y)==programs.geometry.at<false>(id,x,y));++points;
            }
        for (unsigned row=0;row<programs.queries.size();++row) {
            const auto& q=programs.queries[row];
            assert(programs.evaluate<true>(row,q)==int(programs.counts[row][5]));
            assert(programs.evaluate<false>(row,q)==int(programs.counts[row][5]));
            auto changed=q;changed[2]=(q[2]+1)%120;
            assert(programs.evaluate<true>(row,changed)==-1 && programs.evaluate<false>(row,changed)==-1);
            changed=q;changed[8]=(q[8]+1)%496;
            assert(programs.evaluate<true>(row,changed)==-1 && programs.evaluate<false>(row,changed)==-1);
        }
        assert(rounds==0);
        std::printf("{\"all_equal\":true,\"grid_points\":%llu,\"queries\":%zu,\"negative_cases\":%zu,"
            "\"dense_bytes\":%llu,\"shared_rows\":%zu,\"initialization_cpu_s\":%.9f}\n",
            (unsigned long long)points,programs.queries.size(),programs.queries.size()*2,
            (unsigned long long)programs.geometry.bytes(),programs.geometry.values.size()/120,initialization);
    } else {
        assert((mode=='A' || mode=='D') && rounds==64);
        const uint64_t expected=programs.reference(rounds);
        const double start=cpu718();
        const uint64_t value=mode=='A'?programs.run<false>(rounds):programs.run<true>(rounds);
        const double elapsed=cpu718()-start;
        assert(value==expected);
        std::printf("{\"all_equal\":true,\"arm\":\"%c\",\"loop_cpu_s\":%.9f,"
            "\"initialization_cpu_s\":%.9f,\"evaluations\":%zu,\"checksum\":%llu,\"dense_bytes\":%llu}\n",
            mode,elapsed,initialization,programs.queries.size()*rounds,(unsigned long long)value,
            (unsigned long long)programs.geometry.bytes());
    }
}
