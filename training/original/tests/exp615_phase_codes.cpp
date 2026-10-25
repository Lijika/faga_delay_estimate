#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void require(bool value, const char* message) {
    if (!value) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

static std::vector<unsigned char> table(const char* path, const char* magic, unsigned contexts) {
    FILE* f = std::fopen(path, "rb");
    require(f != nullptr, "open table");
    char header[8];
    uint32_t dimensions[2];
    require(std::fread(header, 1, 8, f) == 8 && std::memcmp(header, magic, 8) == 0, "table magic");
    require(std::fread(dimensions, 4, 2, f) == 2 &&
            dimensions[0] == 59904 && dimensions[1] == contexts, "table dimensions");
    std::vector<unsigned char> data(uint64_t(59904) * contexts * 5 / 8 + 1);
    require(std::fread(data.data(), 1, data.size(), f) == data.size(), "table body");
    require(std::fgetc(f) == EOF && !std::ferror(f), "table EOF");
    require(std::fclose(f) == 0, "close table");
    return data;
}

static int lookup(const std::vector<unsigned char>& data, uint64_t index) {
    const uint64_t bit = 5 * index, byte = bit / 8;
    require(byte + 1 < data.size(), "table index");
    const unsigned value = unsigned(data[byte]) | (unsigned(data[byte + 1]) << 8);
    return 2 * (int((value >> (bit % 8)) & 31) - 16);
}

int main(int argc, char** argv) {
    require(argc == 6, "usage: decode B.p5 P.p5 keys.bin B-query.i32 P-query.i32");
    const auto b = table(argv[1], "EX615B01", 4);
    const auto p = table(argv[2], "EX615P01", 480);
    FILE* input = std::fopen(argv[3], "rb");
    FILE* out_b = std::fopen(argv[4], "wb");
    FILE* out_p = std::fopen(argv[5], "wb");
    require(input && out_b && out_p, "open query files");
    char magic[8];
    uint32_t count;
    require(std::fread(magic, 1, 8, input) == 8 && std::memcmp(magic, "EX615K01", 8) == 0,
            "query magic");
    require(std::fread(&count, 4, 1, input) == 1 && count == 1000000, "query count");
    std::array<bool, 59904> seen{};
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t key[4];
        require(std::fread(key, 4, 4, input) == 4, "query key");
        const auto pair = key[0], context = key[1], qx = key[2], qy = key[3];
        require(pair < 59904 && context < 480 && qx < 12 && qy < 46, "key range");
        seen[pair] = true;
        const int32_t cb = qx + qy > 3 ? lookup(b, uint64_t(pair) * 4 + context / 120) : 0;
        const int32_t cp = qx + qy > 3 ? lookup(p, uint64_t(pair) * 480 + context) : 0;
        require(std::fwrite(&cb, 4, 1, out_b) == 1 && std::fwrite(&cp, 4, 1, out_p) == 1,
                "write correction");
    }
    require(std::fgetc(input) == EOF && !std::ferror(input), "query EOF");
    require(std::fclose(input) == 0 && std::fclose(out_b) == 0 &&
            std::fclose(out_p) == 0, "close query files");
    for (bool value : seen) require(value, "full port coverage");
    std::puts("{\"rows\":1000000,\"port_pairs\":59904,\"independent_scalar_lookup\":true}");
}
