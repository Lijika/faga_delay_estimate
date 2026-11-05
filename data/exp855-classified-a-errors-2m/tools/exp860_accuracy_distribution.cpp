// Full-file diagnostics for the frozen exp855 predictions; no model fitting.
#include <algorithm>
#include <array>
#include <cassert>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

static void need(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "%s\n", why); std::exit(1); }
}
static int integer(std::string_view s) {
    int v = 0;
    auto r = std::from_chars(s.data(), s.data()+s.size(), v);
    need(r.ec == std::errc{} && r.ptr == s.data()+s.size(), "invalid integer");
    return v;
}
static std::pair<std::string_view,int> row(std::string_view s) {
    need(!s.empty() && s.back() == '\n', "missing LF");
    s.remove_suffix(1);
    const auto a=s.find(','), b=s.rfind(',');
    need(a!=s.npos && a!=b && s.find(',',a+1)==b, "three fields required");
    return {s.substr(0,b),integer(s.substr(b+1))};
}
// Same point function as exp857_full_accuracy.cpp and validation/verify.py.
static double point(int prediction, int exact) {
    if (exact == 0) return prediction == 0 ? 1.0 : 0.0;
    if (prediction < 0) return 0.0;
    return 1.0-std::tanh(4.0*std::abs(double(prediction)-exact)/exact);
}
struct Stats {
    uint64_t n=0, equal=0, under=0, over=0, beyond5=0;
    int64_t absolute=0, signed_error=0;
    double loss=0, relative=0;
    void add(int prediction,int exact,double loss_value) {
        const int64_t delta=int64_t(prediction)-exact, err=std::abs(delta);
        ++n; equal+=delta==0; under+=delta<0; over+=delta>0;
        beyond5+=exact>0 && 20*err>exact;
        absolute+=err; signed_error+=delta; loss+=loss_value;
        if (exact>0) relative+=double(err)/exact;
    }
    void print() const {
        std::printf("{\"rows\":%llu,\"accuracy_pp\":%.12f,\"loss_sum\":%.12f,"
                    "\"exact_rows\":%llu,\"under_rows\":%llu,\"over_rows\":%llu,"
                    "\"beyond5_rows\":%llu,\"absolute_error_sum\":%lld,"
                    "\"signed_error_sum\":%lld,\"relative_error_sum\":%.12f}",
                    (unsigned long long)n, n?100*(1-loss/n):0,loss,
                    (unsigned long long)equal,(unsigned long long)under,(unsigned long long)over,
                    (unsigned long long)beyond5,(long long)absolute,(long long)signed_error,relative);
    }
};
struct Partition {
    std::string name;
    std::vector<std::string> labels;
    std::vector<Stats> groups;
    Partition(std::string n,std::vector<std::string> l):
        name(std::move(n)),labels(std::move(l)),groups(labels.size()) {}
    void print(const Stats& total) const {
        uint64_t n=0; double loss=0;
        std::printf(",\"%s\":[",name.c_str());
        bool first=true;
        for (size_t i=0;i<groups.size();++i) {
            const auto& s=groups[i]; n+=s.n; loss+=s.loss;
            if (!s.n) continue;
            std::printf("%s{\"group\":\"%s\",\"metrics\":",first?"":",",labels[i].c_str());
            s.print(); std::printf("}"); first=false;
        }
        std::printf("]");
        need(n==total.n && std::abs(loss-total.loss)<1e-3,"partition totals differ");
    }
};
static const std::vector<std::string> families={"A","S","ZS","ZD","ZQ","ZL"};
struct Pin { int x,y,id,family,seen; };
struct Port { int id,family,seen_source,seen_target; };
static Pin pin(std::string_view s,const std::unordered_map<std::string,Port>& ports,bool source) {
    need(s.substr(0,4)=="SRB_","pin prefix");
    const auto u=s.find('_',4), slash=s.find('/',u);
    need(u!=s.npos && slash!=s.npos,"pin separators");
    const int x=integer(s.substr(4,u-4)),y=integer(s.substr(u+1,slash-u-1));
    need(x>=0 && x<120 && y>=0 && y<550,"pin coordinates");
    auto p=ports.find(std::string(s.substr(slash+1)));
    need(p!=ports.end(),"unknown port");
    const auto& v=p->second;
    return {x,y,v.id,v.family,source?v.seen_source:v.seen_target};
}
static int distance_bin(int d) {
    return (d>0)+(d>12)+(d>24)+(d>50)+(d>100)+(d>300);
}
static int relative_bin(int64_t err,int exact) {
    if (!err) return 0;
    if (!exact) return 9;
    return 1+(1000*err>exact)+(200*err>exact)+(100*err>exact)+
        (50*err>exact)+(20*err>exact)+(10*err>exact)+(5*err>exact)+(2*err>exact);
}
static void self_check() {
    assert(point(0,0)==1 && point(1,0)==0 && point(-1,100)==0);
    assert(std::abs(point(101,100)-(1-std::tanh(.04)))<1e-15);
    assert(point(99,100)==point(101,100));
    auto r=row("SRB_1_2/A_AY,SRB_3_4/ZLE[0],321\n");
    assert(r.second==321 && r.first=="SRB_1_2/A_AY,SRB_3_4/ZLE[0]");
    assert(distance_bin(0)==0 && distance_bin(12)==1 && distance_bin(13)==2);
    assert(distance_bin(300)==5 && distance_bin(301)==6);
    assert(relative_bin(0,100)==0 && relative_bin(5,100)==5 &&
           relative_bin(6,100)==6 && relative_bin(1,0)==9);
    Stats s; s.add(100,100,0); s.add(95,100,1-point(95,100)); s.add(106,100,1-point(106,100));
    assert(s.n==3 && s.equal==1 && s.under==1 && s.over==1 && s.beyond5==1);
    assert(s.absolute==11 && s.signed_error==1);
}
int main(int argc,char** argv) {
    self_check();
    if (argc==2 && std::string_view(argv[1])=="--self-check") return 0;
    need(argc==4,"usage: distribution EXACT.csv PREDICTION.csv ROWS; port-metadata.tsv beside executable");
    const uint64_t expected=std::stoull(argv[3]);
    std::ifstream metadata(std::filesystem::path(argv[0]).parent_path()/"port-metadata.tsv");
    need(bool(metadata),"cannot read port metadata");
    std::unordered_map<std::string,Port> ports;
    std::vector<std::string> names;
    std::string name, family; int seen_s,seen_t;
    while (metadata>>name>>family>>seen_s>>seen_t) {
        const auto f=std::find(families.begin(),families.end(),family);
        need(f!=families.end() && (seen_s==0 || seen_s==1) && (seen_t==0 || seen_t==1),
             "invalid metadata");
        need(ports.emplace(name,Port{int(names.size()),int(f-families.begin()),seen_s,seen_t}).second,
             "duplicate port metadata");
        names.push_back(name);
    }
    need(metadata.eof() && names.size()==336,"non-I metadata port count differs");
    std::vector<std::string> pair_names;
    for (auto& a:families) for (auto& b:families) pair_names.push_back(a+"->"+b);
    const std::vector<std::string> distances={"0","1-12","13-24","25-50","51-100","101-300","301+"};
    std::vector<std::string> distance_pairs,coverage_distance;
    const std::vector<std::string> coverage={"both_unseen","target_unseen","source_unseen","both_seen"};
    for (const auto& d:distances) {
        for (const auto& p:pair_names) distance_pairs.push_back(d+":"+p);
        for (const auto& p:coverage) coverage_distance.push_back(d+":"+p);
    }
    Partition distance("manhattan_distance",distances),
        rel("relative_error",{"0","(0,0.1%]","(0.1%,0.5%]","(0.5%,1%]","(1%,2%]",
            "(2%,5%]","(5%,10%]","(10%,20%]","(20%,50%]","50%+"}),
        abs("absolute_error",{"0","1","2-5","6-10","11-20","21-50","51-100","101-200","201+"}),
        sign("error_direction",{"under","exact","over"}),
        axis("direction",{"same_site","horizontal","vertical","dx+dy+","dx+dy-","dx-dy+","dx-dy-"}),
        source("source_family",families),target("target_family",families),
        pairs("family_pair",pair_names),d_pairs("distance_family_pair",distance_pairs),
        source_port("source_port",names),target_port("target_port",names),
        public_seen("public1m_port_coverage",coverage),d_seen("distance_public1m_port_coverage",coverage_distance),
        edge("outer_edge_5",{"neither","source_only","target_only","both"}),
        delay("exact_delay",{"0","1-200","201-500","501-1000","1001-2000","2001-5000","5001+"});
    std::vector<Stats> concrete_pairs(names.size()*names.size());
    FILE* gold=std::fopen(argv[1],"rb"),*pred=std::fopen(argv[2],"rb");
    need(gold && pred,"cannot open CSV");
    char *gl=nullptr,*pl=nullptr; size_t gc=0,pc=0;
    auto header=[](FILE* f,char** p,size_t* c) {
        const auto n=getline(p,c,f);
        need(n>0 && std::string_view(*p,size_t(n))=="From,To,delay\n","header differs");
    };
    header(gold,&gl,&gc); header(pred,&pl,&pc);
    Stats total; long double precise_points=0; std::map<int64_t,uint64_t> error_hist;
    std::array<std::string,3> worst_endpoints;
    std::array<int,3> worst_exact{},worst_prediction{};
    std::array<double,3> worst_loss{{-1,-1,-1}};
    for (ssize_t gn;(gn=getline(&gl,&gc,gold))>=0;) {
        const auto pn=getline(&pl,&pc,pred);
        need(pn>0 && total.n<expected,"row counts differ");
        auto g=row({gl,size_t(gn)}),p=row({pl,size_t(pn)});
        need(g.first==p.first && g.second>=0 && p.second>=0,"endpoints/order or delay differ");
        const auto comma=g.first.find(',');
        const auto s=pin(g.first.substr(0,comma),ports,true),t=pin(g.first.substr(comma+1),ports,false);
        const int dx=t.x-s.x,dy=t.y-s.y,d=distance_bin(std::abs(dx)+std::abs(dy));
        const int e=g.second,v=p.second;
        const int64_t err=std::abs(int64_t(v)-e);
        const double value=point(v,e),loss=1-value;
        precise_points+=value; total.add(v,e,loss); ++error_hist[err];
        distance.groups[d].add(v,e,loss); rel.groups[relative_bin(err,e)].add(v,e,loss);
        abs.groups[(err>0)+(err>1)+(err>5)+(err>10)+(err>20)+(err>50)+(err>100)+(err>200)].add(v,e,loss);
        sign.groups[(v>=e)+(v>e)].add(v,e,loss);
        const int direction=dx==0 && dy==0?0:dy==0?1:dx==0?2:3+2*(dx<0)+(dy<0);
        axis.groups[direction].add(v,e,loss);
        source.groups[s.family].add(v,e,loss); target.groups[t.family].add(v,e,loss);
        const int fp=s.family*6+t.family,cov=s.seen+2*t.seen;
        pairs.groups[fp].add(v,e,loss); d_pairs.groups[d*36+fp].add(v,e,loss);
        source_port.groups[s.id].add(v,e,loss); target_port.groups[t.id].add(v,e,loss);
        public_seen.groups[cov].add(v,e,loss); d_seen.groups[d*4+cov].add(v,e,loss);
        const bool se=std::min({s.x,119-s.x,s.y,549-s.y})<5,te=std::min({t.x,119-t.x,t.y,549-t.y})<5;
        edge.groups[se+2*te].add(v,e,loss);
        delay.groups[(e>0)+(e>200)+(e>500)+(e>1000)+(e>2000)+(e>5000)].add(v,e,loss);
        concrete_pairs[s.id*names.size()+t.id].add(v,e,loss);
        if (loss>worst_loss[2]) {
            worst_loss[2]=loss; worst_endpoints[2]=g.first; worst_exact[2]=e; worst_prediction[2]=v;
            for (int k=2;k>0 && worst_loss[k]>worst_loss[k-1];--k) {
                std::swap(worst_loss[k],worst_loss[k-1]); std::swap(worst_endpoints[k],worst_endpoints[k-1]);
                std::swap(worst_exact[k],worst_exact[k-1]); std::swap(worst_prediction[k],worst_prediction[k-1]);
            }
        }
    }
    need(total.n==expected && getline(&pl,&pc,pred)<0 && !ferror(gold) && !ferror(pred),"rows/EOF differ");
    std::fclose(gold); std::fclose(pred); std::free(gl); std::free(pl);
    need(std::abs(double(precise_points)-(total.n-total.loss))<1e-3,"point sums differ");
    std::printf("{\"rows\":%llu,\"accuracy_pp\":%.15Lf,\"point_sum\":%.18Lf,"
                "\"endpoint_order_integer_eof_contract_passed\":true,\"overall\":",
                (unsigned long long)total.n,100*precise_points/total.n,precise_points);
    total.print();
    for (const auto* p:{&distance,&rel,&abs,&sign,&axis,&source,&target,&pairs,&d_pairs,
                       &source_port,&target_port,&public_seen,&d_seen,&edge,&delay}) p->print(total);
    std::printf(",\"absolute_error_histogram\":[");
    bool first=true;
    for (auto [error,n]:error_hist) {
        std::printf("%s[%lld,%llu]",first?"":",",(long long)error,(unsigned long long)n); first=false;
    }
    std::printf("],\"top_port_pairs_by_loss\":[");
    std::vector<size_t> order(concrete_pairs.size()); std::iota(order.begin(),order.end(),0);
    std::partial_sort(order.begin(),order.begin()+30,order.end(),
        [&](size_t a,size_t b){return concrete_pairs[a].loss>concrete_pairs[b].loss;});
    for (size_t j=0;j<30;++j) {
        const size_t i=order[j];
        std::printf("%s{\"source\":\"%s\",\"target\":\"%s\",\"metrics\":",j?",":"",
                    names[i/names.size()].c_str(),names[i%names.size()].c_str());
        concrete_pairs[i].print(); std::printf("}");
    }
    std::printf("],\"worst_score_examples\":[");
    for (int i=0;i<3;++i)
        std::printf("%s{\"endpoints\":\"%s\",\"exact\":%d,\"prediction\":%d,\"score\":%.12f}",
                    i?",":"",worst_endpoints[i].c_str(),worst_exact[i],worst_prediction[i],1-worst_loss[i]);
    std::printf("]}\n");
    return 0;
}
