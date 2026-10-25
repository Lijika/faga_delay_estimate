#include "architecture.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>

static void require(bool value, const char* reason) {
    if (!value) { std::fprintf(stderr, "%s\n", reason); std::exit(1); }
}

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: sample-groups INPUT.csv OUTPUT.u8"); return 0;
    }
    require(argc == 3, "arguments");
    delayest::Architecture arch;
    arch.loadEmbedded();
    std::ifstream input(argv[1]);
    FILE* output = std::fopen(argv[2], "wb");
    require(bool(input) && output, "open files");
    std::string row;
    require(bool(std::getline(input, row)) && row == "From,To", "header");
    size_t count = 0;
    while (std::getline(input, row)) {
        const size_t comma = row.find(',');
        require(comma != std::string::npos && row.find(',', comma + 1) == std::string::npos, "row fields");
        int sx, sy, sp, tx, ty, tp;
        require(arch.parsePin(row.substr(0, comma), sx, sy, sp) &&
                arch.parsePin(row.substr(comma + 1), tx, ty, tp), "pin syntax");
        require(arch.exists(sx, sy) && arch.exists(tx, ty), "existing endpoints");
        int ax = sx, ay = sy;
        const int net = arch.netOfOutput(sp);
        if (net >= 0) {
            const auto edge = arch.resolveNet(sx, sy, net);
            require(edge.valid, "valid first net"); ax = edge.x; ay = edge.y;
        }
        unsigned char forced = 0;
        for (const auto& block : arch.blocks())
            forced |= ((ax < block.left && tx > block.right) || (tx < block.left && ax > block.right)) &&
                      ay >= block.lower && ay <= block.upper && ty >= block.lower && ty <= block.upper;
        require(std::fwrite(&forced, 1, 1, output) == 1, "write flag");
        ++count;
    }
    require(input.eof() && std::fclose(output) == 0, "EOF and close");
    std::printf("{\"rows\":%zu}\n", count);
}
