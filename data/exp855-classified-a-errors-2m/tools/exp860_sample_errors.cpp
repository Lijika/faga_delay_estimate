// Reuse the independently checked CSV, endpoint and score functions.
#define main distribution_main
#include "exp860_accuracy_distribution.cpp"
#undef main

struct SampleRow {
    uint64_t row;
    std::string endpoints;
    int exact,prediction,stratum;
};
static uint64_t random64(uint64_t& state) {
    uint64_t z=(state+=0x9e3779b97f4a7c15ULL);
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
    z=(z^(z>>27))*0x94d049bb133111ebULL;
    return z^(z>>31);
}
static uint64_t below(uint64_t& state,uint64_t bound) {
    const uint64_t threshold=-bound%bound;
    uint64_t x;
    do { x=random64(state); } while (x<threshold);
    return x%bound;
}
static std::vector<uint64_t> allocate(const std::vector<uint64_t>& counts,uint64_t wanted) {
    const uint64_t total=std::accumulate(counts.begin(),counts.end(),uint64_t(0));
    const uint64_t active=std::count_if(counts.begin(),counts.end(),[](uint64_t n){return n>0;});
    need(wanted>=active && wanted<=total,"sample budget incompatible with occupied strata");
    if (wanted==total) return counts;
    std::vector<uint64_t> quota(counts.size()),remainder(counts.size());
    uint64_t assigned=active,remaining=wanted-active,available=total-active;
    need(available>0,"empty allocation denominator");
    for (size_t i=0;i<counts.size();++i) if (counts[i]) {
        const uint64_t product=remaining*(counts[i]-1);
        quota[i]=1+product/available; remainder[i]=product%available;
        assigned+=quota[i]-1;
    }
    std::vector<size_t> order(counts.size()); std::iota(order.begin(),order.end(),0);
    std::sort(order.begin(),order.end(),[&](size_t a,size_t b){
        return remainder[a]!=remainder[b]?remainder[a]>remainder[b]:a<b;});
    for (size_t i:order) {
        if (assigned==wanted) break;
        if (quota[i]<counts[i]) { ++quota[i]; ++assigned; }
    }
    need(assigned==wanted,"allocation total differs");
    return quota;
}
static void sampling_self_check() {
    self_check();
    auto q=allocate({0,1,2,100,1000},100);
    assert(std::accumulate(q.begin(),q.end(),uint64_t(0))==100);
    assert(q[0]==0 && q[1]==1 && q[2]>=1 && q[3]<=100 && q[4]<=1000);
    assert(allocate({0,1,2},3)==std::vector<uint64_t>({0,1,2}));
    uint64_t a=85520261105ULL,b=a;
    for (int i=0;i<10000;++i) { auto x=below(a,17); assert(x<17 && x==below(b,17)); }
    // Exhaust the two replacement draws for a reservoir of two among four.
    std::map<std::pair<int,int>,int> combinations;
    for (int j3=0;j3<3;++j3) for (int j4=0;j4<4;++j4) {
        std::array<int,2> r{{0,1}};
        if (j3<2) r[j3]=2;
        if (j4<2) r[j4]=3;
        std::sort(r.begin(),r.end()); ++combinations[{r[0],r[1]}];
    }
    assert(combinations.size()==6);
    for (auto [pair,n]:combinations) { (void)pair; assert(n==2); }
}
int main(int argc,char** argv) {
    sampling_self_check();
    if (argc==2 && std::string_view(argv[1])=="--self-check") return 0;
    need(argc==8,"usage: sample-errors EXACT PREDICTION ROWS SAMPLE_ROWS SEED OUTPUT.csv SUMMARY.json");
    const uint64_t expected=std::stoull(argv[3]),wanted=std::stoull(argv[4]),seed=std::stoull(argv[5]);
    std::ifstream metadata(std::filesystem::path(argv[0]).parent_path()/"port-metadata.tsv");
    need(bool(metadata),"cannot read metadata");
    std::unordered_map<std::string,Port> ports;
    std::string name,family; int seen_s,seen_t;
    while (metadata>>name>>family>>seen_s>>seen_t) {
        auto f=std::find(families.begin(),families.end(),family);
        need(f!=families.end(),"family differs");
        need(ports.emplace(name,Port{int(ports.size()),int(f-families.begin()),seen_s,seen_t}).second,
             "duplicate port");
    }
    need(metadata.eof() && ports.size()==336,"metadata count differs");
    const size_t strata=7*36*2*9;
    std::vector<uint64_t> counts(strata),seen(strata),pair_population(336*336),pair_sample(336*336);
    std::vector<Stats> population_stats(strata),sample_stats(strata);
    std::vector<std::vector<SampleRow>> reservoirs(strata);
    std::vector<uint64_t> quota;
    Stats population_total,sample_total;
    uint64_t random_state=seed;
    for (int pass=0;pass<2;++pass) {
        FILE* gold=std::fopen(argv[1],"rb"),*pred=std::fopen(argv[2],"rb");
        need(gold && pred,"cannot open inputs");
        char *gl=nullptr,*pl=nullptr; size_t gc=0,pc=0; uint64_t n=0;
        auto header=[](FILE* f,char** p,size_t* c) {
            const auto len=getline(p,c,f);
            need(len>0 && std::string_view(*p,len)=="From,To,delay\n","header differs");
        };
        header(gold,&gl,&gc); header(pred,&pl,&pc);
        for (ssize_t gn;(gn=getline(&gl,&gc,gold))>=0;) {
            const auto pn=getline(&pl,&pc,pred);
            need(pn>0 && n<expected,"row count differs");
            auto g=row({gl,size_t(gn)}),p=row({pl,size_t(pn)});
            need(g.first==p.first && g.second>0 && p.second>=0,"endpoint/delay mismatch");
            ++n;
            if (p.second==g.second) continue;
            const auto comma=g.first.find(',');
            const auto s=pin(g.first.substr(0,comma),ports,true),t=pin(g.first.substr(comma+1),ports,false);
            const int d=distance_bin(std::abs(t.x-s.x)+std::abs(t.y-s.y));
            const int rb=relative_bin(std::abs(int64_t(p.second)-g.second),g.second)-1;
            const int stratum=((d*36+s.family*6+t.family)*2+(p.second>g.second))*9+rb;
            if (!pass) {
                ++counts[stratum]; ++pair_population[s.id*336+t.id];
                const double loss=1-point(p.second,g.second);
                population_stats[stratum].add(p.second,g.second,loss);
                population_total.add(p.second,g.second,loss);
            } else {
                const uint64_t k=quota[stratum],visited=++seen[stratum];
                const uint64_t slot=visited<=k?visited-1:below(random_state,visited);
                if (slot<k) {
                    SampleRow r{n,std::string(g.first),g.second,p.second,stratum};
                    if (visited<=k) reservoirs[stratum].push_back(std::move(r));
                    else reservoirs[stratum][slot]=std::move(r);
                }
            }
        }
        need(n==expected && getline(&pl,&pc,pred)<0 && !ferror(gold) && !ferror(pred),"input EOF differs");
        std::fclose(gold); std::fclose(pred); std::free(gl); std::free(pl);
        std::fprintf(stderr,"pass %d complete, %llu rows\n",pass+1,(unsigned long long)n);
        if (!pass) {
            quota=allocate(counts,wanted);
            for (size_t i=0;i<strata;++i) reservoirs[i].reserve(quota[i]);
        }
    }
    need(counts==seen,"pass populations differ");
    std::vector<SampleRow> selected; selected.reserve(wanted);
    for (size_t i=0;i<strata;++i) {
        need(reservoirs[i].size()==quota[i],"reservoir quota differs");
        for (auto& r:reservoirs[i]) selected.push_back(std::move(r));
        reservoirs[i].clear(); reservoirs[i].shrink_to_fit();
    }
    need(selected.size()==wanted,"selected count differs");
    std::sort(selected.begin(),selected.end(),[](const auto& a,const auto& b){return a.row<b.row;});
    FILE* output=std::fopen(argv[6],"wx");
    need(output,"sample output already exists or cannot open");
    std::fprintf(output,"From,To,exact,exp855_prediction,a_row_id,stratum_id\n");
    std::vector<uint64_t> pair_keys; pair_keys.reserve(wanted);
    uint64_t previous=0;
    for (const auto& r:selected) {
        need(r.row>previous && r.exact!=r.prediction,"sample repeated row or exact prediction");
        previous=r.row;
        const auto comma=r.endpoints.find(',');
        const auto s=pin(std::string_view(r.endpoints).substr(0,comma),ports,true);
        const auto t=pin(std::string_view(r.endpoints).substr(comma+1),ports,false);
        const uint32_t si=(s.x*550+s.y)*336+s.id,ti=(t.x*550+t.y)*336+t.id;
        pair_keys.push_back((uint64_t(si)<<32)|ti);
        ++pair_sample[s.id*336+t.id];
        const double loss=1-point(r.prediction,r.exact);
        sample_stats[r.stratum].add(r.prediction,r.exact,loss);
        sample_total.add(r.prediction,r.exact,loss);
        need(std::fprintf(output,"%s,%d,%d,%llu,%d\n",r.endpoints.c_str(),r.exact,r.prediction,
                          (unsigned long long)r.row,r.stratum)>0,"sample write failed");
    }
    need(std::fclose(output)==0,"sample close failed");
    std::sort(pair_keys.begin(),pair_keys.end());
    need(std::adjacent_find(pair_keys.begin(),pair_keys.end())==pair_keys.end(),"duplicate directed request");
    need(std::freopen(argv[7],"wx",stdout),"summary already exists or cannot open");
    auto covered=[](const auto& v){return std::count_if(v.begin(),v.end(),[](uint64_t n){return n>0;});};
    std::printf("{\"rows_scanned\":%llu,\"error_population_rows\":%llu,\"sample_rows\":%llu,"
                "\"seed\":%llu,\"unique_directed_pairs\":true,\"all_predictions_differ\":true,"
                "\"error_port_pairs\":%lld,\"sample_port_pairs\":%lld,"
                "\"population_metrics\":",
                (unsigned long long)expected,(unsigned long long)population_total.n,(unsigned long long)wanted,
                (unsigned long long)seed,(long long)covered(pair_population),(long long)covered(pair_sample));
    population_total.print(); std::printf(",\"sample_metrics\":"); sample_total.print();
    std::printf(",\"strata\":[");
    bool first=true; long double weighted_loss=0;
    for (size_t i=0;i<strata;++i) if (counts[i]) {
        const size_t rb=i%9,sg=(i/9)%2,fp=(i/18)%36,d=i/(18*36);
        const double weight=double(counts[i])/quota[i];
        weighted_loss+=sample_stats[i].loss*weight;
        std::printf("%s{\"id\":%zu,\"distance_bin\":%zu,\"source_family\":\"%s\","
                    "\"target_family\":\"%s\",\"error_direction\":\"%s\",\"relative_error_bin\":%zu,"
                    "\"population_rows\":%llu,\"sample_rows\":%llu,\"inclusion_probability\":%.15g,"
                    "\"inverse_probability_weight\":%.15g,\"population\":",
                    first?"":",",i,d,families[fp/6].c_str(),families[fp%6].c_str(),
                    sg?"over":"under",rb+1,(unsigned long long)counts[i],(unsigned long long)quota[i],
                    double(quota[i])/counts[i],weight);
        population_stats[i].print(); std::printf(",\"sample\":"); sample_stats[i].print();
        std::printf("}"); first=false;
    }
    std::printf("],\"weighted_error_population_accuracy_pp\":%.12Lf}\n",
                100*(1-weighted_loss/population_total.n));
    need(std::fflush(stdout)==0,"summary write failed");
    return 0;
}
