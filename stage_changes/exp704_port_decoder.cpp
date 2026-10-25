#include "architecture.h"
#include <array>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

static delayest::Architecture arch;
static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
namespace original {
#include "original_parser.h"
}
namespace candidate {
#include "exp601_port_parser.h"
}

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: port-decoder-test ARCH");
        arch.load(argv[1]);
        original::initializePorts580();
        candidate::initializePorts580();
        uint64_t checks = 0;
        const auto verify = [&](const std::string& text) {
            int ax=-7, ay=-8, ap=-9, bx=ax, by=ay, bp=ap;
            const bool a=original::parsePin580(text,ax,ay,ap);
            const bool b=candidate::parsePin580(text,bx,by,bp);
            require(a==b && ax==bx && ay==by && ap==bp, "parser outputs differ");
            ++checks;
        };
        for (int p=0; p<arch.portCount(); ++p) {
            const std::string& name=arch.portName(p);
            for (const char* prefix : {"SRB_0_0/","SRB_001_002/","SRB_119_549/",
                 "SRB_2147483648_2/","SRB_1_2147483648/","SRB_-1_2/","SRB_1_+2/",
                 "SRB__2/","SRB_1_/","SRB_1_2_3/","SRB_1_2//"}) {
                verify(std::string(prefix)+name);
                verify(std::string(prefix)+name+"X");
                verify(std::string(prefix)+name.substr(0,name.size()-1));
            }
            for (size_t pos=0; pos<name.size(); ++pos) {
                for (unsigned byte=0; byte<256; ++byte) {
                    auto changed=name;
                    changed[pos]=char(byte);
                    verify(std::string("SRB_119_549/")+changed);
                }
            }
        }
        uint32_t random=uint32_t(20261025704ULL);
        for (unsigned i=0; i<100000; ++i) {
            std::string name(3+i%7,'\0');
            for (char& c : name) {
                random^=random<<13; random^=random>>17; random^=random<<5;
                c=char(random);
            }
            verify(std::string("SRB_37_108/")+name);
        }
        require(checks>750000, "insufficient parser coverage");
        std::cout<<"{\"checks\":"<<checks<<",\"ports\":"<<arch.portCount()
                 <<",\"all_equal\":true}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<"\n";
        return 1;
    }
}
