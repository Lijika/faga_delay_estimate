#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
#include "exp619_phase_lookup.h"

static std::vector<unsigned char> read(const char* path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "input open");
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

template <class T>
static void write(const char* path, const std::vector<T>& values) {
    std::ofstream stream(path, std::ios::binary);
    require(bool(stream), "output open");
    stream.write(reinterpret_cast<const char*>(values.data()),
                 std::streamsize(values.size() * sizeof(T)));
    stream.close();
    require(bool(stream), "output write");
}

int main(int argc, char** argv) {
    try {
        require(argc == 5, "model keys full-output query-output");
        const auto model = read(argv[1]), keys = read(argv[2]);
        require(model.size() == 14377024, "model size");
        initializePhaseCodes619(model.data());
        require(keys.size() == 12 + 1000000 * 16 &&
                std::memcmp(keys.data(), "EX615K01", 8) == 0, "keys size and magic");
        const auto* count = reinterpret_cast<const uint32_t*>(keys.data() + 8);
        require(*count == 1000000, "keys rows");
        std::vector<int8_t> full(59904 * 480);
        for (unsigned pair = 0; pair < 59904; ++pair)
            for (unsigned phase = 0; phase < 480; ++phase)
                full[pair * 480 + phase] = int8_t(phaseCorrection619(pair, phase, 4, 0));
        const auto* row = reinterpret_cast<const uint32_t*>(keys.data() + 12);
        std::vector<int32_t> queries(1000000);
        for (unsigned i = 0; i < 1000000; ++i, row += 4) {
            require(row[0] < 59904 && row[1] < 480, "query key");
            queries[i] = phaseCorrection619(row[0], row[1], row[2], row[3]);
        }
        write(argv[3], full);
        write(argv[4], queries);
        std::cout << "{\"full_values\":" << full.size()
                  << ",\"query_rows\":" << queries.size() << "}\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
