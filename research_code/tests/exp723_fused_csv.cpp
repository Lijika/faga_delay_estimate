#include "architecture.h"
#include "csv.h"
#include <array>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>

static delayest::Architecture arch;
static void require(bool value, const char* why) {
    if (!value) throw std::runtime_error(why);
}
#include "exp601_port_parser.h"
#include "exp723_fused_parse.h"
namespace original {
#include "original_reader.h"
}
namespace candidate {
#include "reader723.h"
}

static bool parsed(std::string_view text, int32_t* q) {
    const size_t comma=text.find(',');
    if (comma==text.npos || text.find(',',comma+1)!=text.npos) return false;
    return parsePin580(delayest::trimView(text.substr(0,comma)),q[0],q[1],q[8]) &&
           parsePin580(delayest::trimView(text.substr(comma+1)),q[2],q[3],q[9]);
}

static void same(const int32_t* a, const int32_t* b) {
    for (int index : {0,1,2,3,8,9}) require(a[index]==b[index],"parsed endpoint mismatch");
}

int main(int argc, char** argv) {
    try {
        require(argc==3,"usage: fused-csv-test ARCH WORKDIR");
        arch.load(argv[1]);
        initializePorts580();
        uint64_t checks=0, accepted=0;
        const auto verify=[&](const std::string& input) {
            std::string buffer=input+std::string(16,'x');
            int32_t a[10]{},b[10]{};
            size_t consumed=0;
            if (row723(buffer.data(),buffer.data()+buffer.size(),a,consumed)) {
                require(consumed==input.find('\n')+1,"first newline consumption");
                require(parsed(std::string_view(input.data(),consumed-1),b),"fast accepted invalid line");
                same(a,b);
                ++accepted;
            }
            ++checks;
        };
        for (int s=0;s<arch.portCount();++s) for (int t=0;t<arch.portCount();++t) {
            verify("SRB_119_549/"+arch.portName(s)+",SRB_0_0/"+arch.portName(t)+"\n");
        }
        require(accepted==496u*496u,"canonical complete-port coverage");
        for (int p=0;p<arch.portCount();++p) {
            const auto name=arch.portName(p);
            for (const char* prefix : {"SRB_001_002/","SRB_2147483647_549/","SRB_2147483648_2/",
                 "SRB_1_2147483648/","SRB_-1_2/","SRB_1_+2/","SRB__2/","SRB_1_/","SRB_1_2//"}) {
                verify(std::string(prefix)+name+",SRB_0_0/"+name+"\n");
            }
            for (size_t at=0;at<name.size();++at) for (unsigned byte=0;byte<256;++byte) {
                auto broken=name;
                broken[at]=char(byte);
                verify("SRB_1_2/"+broken+",SRB_3_4/"+name+"\n");
                verify("SRB_1_2/"+name+",SRB_3_4/"+broken+"\n");
            }
        }
        uint32_t random=2026102573;
        for (unsigned i=0;i<100000;++i) {
            std::string input(i%80,'\0');
            for (char& c : input) {
                random^=random<<13;random^=random>>17;random^=random<<5;
                c=char(random);
            }
            verify(input+"\n");
        }
        const auto pin="SRB_119_549/"+arch.portName(0);
        const std::string row=pin+","+pin+"\n";
        const size_t page=size_t(sysconf(_SC_PAGESIZE));
        char* guard=static_cast<char*>(mmap(nullptr,2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
        require(guard!=MAP_FAILED && mprotect(guard+page,page,PROT_NONE)==0,"guard mapping");
        for (size_t length=0;length<=row.size();++length) {
            char* begin=guard+page-length;
            std::memcpy(begin,row.data(),length);
            int32_t q[10]{};
            size_t consumed=0;
            const bool ok=row723(begin,guard+page,q,consumed);
            require(!ok || (length==row.size() && consumed==length),"truncated fast acceptance");
        }
        require(munmap(guard,2*page)==0,"guard unmap");
        const std::string fixture=std::string(argv[2])+"/reader-fixture.csv";
        {
            std::ofstream file(fixture,std::ios::binary);
            require(bool(file),"fixture open");
            file<<"From,To\n";
            for (unsigned i=0;i<45000;++i) {
                const auto a="SRB_"+std::to_string(i%120)+"_"+std::to_string(i%550)+"/"+arch.portName(i%496);
                const auto b="SRB_0_100/"+arch.portName((i*17)%496);
                switch (i%7) {
                    case 0: file<<a<<","<<b<<"\n"; break;
                    case 1: file<<a<<","<<b<<"\r\n"; break;
                    case 2: file<<" \t"<<a<<" , "<<b<<"\t \n"; break;
                    case 3: file<<a<<","<<b<<",extra\n"; break;
                    case 4: file<<"broken,"<<b<<"\n"; break;
                    case 5: file<<"\n"; break;
                    case 6: file<<a<<","<<b<<"\n"; break;
                }
            }
            file<<std::string((1u<<20)+17,'x')<<"\n"<<pin<<","<<pin;
            file.close();
            require(bool(file),"fixture close");
        }
        original::CsvViewReader591 before(fixture.c_str());
        candidate::CsvViewReader591 after(fixture.c_str());
        require(before.good() && after.good(),"reader open");
        uint64_t rows=0,fast=0;
        for (;;) {
            std::array<std::string_view,8> views{};
            std::array<std::string,8> retained{};
            size_t count=0;
            for (;count<8;++count) {
                int32_t a[10]{},b[10]{};
                bool isParsed=false;
                if (!after.nextParsed(views[count],a,count==0,isParsed)) break;
                std::string_view reference;
                require(before.next(reference) && views[count]==reference,"reader text mismatch");
                const bool wanted=parsed(reference,b);
                const bool got=isParsed || parsed(views[count],a);
                require(got==wanted,"reader query validity mismatch");
                if (got) same(a,b);
                retained[count]=views[count];
                fast+=isParsed;
                ++rows;
            }
            if (!count) break;
            for (size_t i=0;i<count;++i) require(views[i]==retained[i],"batch view invalidated");
        }
        std::string_view tail;
        require(!before.next(tail) && rows==45003 && fast>12000,"reader EOF/coverage");
        require(std::remove(fixture.c_str())==0,"fixture cleanup");
        std::cout<<"{\"all_equal\":true,\"checks\":"<<checks<<",\"fast_accepted\":"<<accepted
                 <<",\"reader_rows\":"<<rows<<",\"reader_fast_rows\":"<<fast
                 <<",\"guard_pages_passed\":true}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<"\n";
        return 1;
    }
}
