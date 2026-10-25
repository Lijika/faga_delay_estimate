#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

static void require(bool ok, const char* message) {
    if (!ok) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}

static std::unordered_map<std::string, unsigned> ports(const char* path) {
    std::ifstream file(path);
    require(bool(file), "open ports");
    std::unordered_map<std::string, unsigned> result;
    std::string line;
    while (std::getline(file, line)) {
        require(!line.empty() && line.find('\r') == std::string::npos, "port line");
        const unsigned index = result.size();
        require(result.emplace(line, index).second, "duplicate port");
    }
    require(file.eof() && !result.empty(), "ports EOF");
    return result;
}

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: stratified-sample INPUT PLAN SOURCES TARGETS REQUESTS POSITIONS COUNTS");
        return 0;
    }
    require(argc == 8, "arguments");
    const auto source = ports(argv[3]), target = ports(argv[4]);
    FILE* plan = std::fopen(argv[2], "rb");
    require(plan, "open plan");
    char magic[8];
    uint64_t rows;
    uint32_t pairs, samples;
    require(std::fread(magic, 1, 8, plan) == 8 && std::memcmp(magic, "EX683S01", 8) == 0,
            "plan magic");
    require(std::fread(&rows, 8, 1, plan) == 1 && std::fread(&pairs, 4, 1, plan) == 1 &&
            std::fread(&samples, 4, 1, plan) == 1, "plan header");
    require(pairs == source.size() * target.size() && samples > 1, "plan shape");
    std::vector<uint32_t> population(pairs), seen(pairs), picked(pairs), ordinal(size_t(pairs) * samples);
    require(std::fread(population.data(), 4, pairs, plan) == pairs &&
            std::fread(ordinal.data(), 4, ordinal.size(), plan) == ordinal.size(), "plan arrays");
    require(std::fgetc(plan) == EOF && !std::ferror(plan) && std::fclose(plan) == 0, "plan EOF");
    uint64_t total = 0;
    for (unsigned pair = 0; pair < pairs; ++pair) {
        total += population[pair];
        require(population[pair] >= samples, "population support");
        for (unsigned k = 0; k < samples; ++k) {
            const auto value = ordinal[size_t(pair) * samples + k];
            require(value < population[pair] && (!k || value > ordinal[size_t(pair)*samples+k-1]),
                    "ordinal order");
        }
    }
    require(total == rows, "population total");
    std::ifstream input(argv[1]);
    FILE* requests = std::fopen(argv[5], "wx");
    FILE* positions = std::fopen(argv[6], "wx");
    FILE* counts = std::fopen(argv[7], "wx");
    require(bool(input) && requests && positions && counts, "exclusive outputs");
    std::string line;
    require(bool(std::getline(input, line)) && line == "From,To", "input header");
    require(std::fputs("From,To\n", requests) >= 0 && std::fputs("pair\tpopulation\tsample\n", counts) >= 0,
            "output headers");
    uint64_t row = 0, selected = 0;
    while (std::getline(input, line)) {
        require(row < rows && !input.eof() && line.size() < 256 &&
                line.find('\r') == std::string::npos, "input row or final newline");
        const size_t comma = line.find(','), first = line.find('/'), last = line.find('/', comma);
        require(comma != std::string::npos && first < comma && last > comma &&
                last != std::string::npos && line.find(',', comma + 1) == std::string::npos,
                "input fields");
        const auto a = source.find(line.substr(first+1, comma-first-1));
        const auto b = target.find(line.substr(last+1));
        require(a != source.end() && b != target.end(), "known ports");
        const unsigned pair = a->second * target.size() + b->second;
        require(seen[pair] < population[pair], "population overflow");
        if (picked[pair] < samples && seen[pair] == ordinal[size_t(pair)*samples+picked[pair]]) {
            require(std::fprintf(requests, "%s\n", line.c_str()) > 0 &&
                    std::fprintf(positions, "%llu\n", static_cast<unsigned long long>(row)) > 0,
                    "write sample");
            ++picked[pair];
            ++selected;
        }
        ++seen[pair];
        ++row;
    }
    require(input.eof() && row == rows && selected == uint64_t(pairs)*samples, "input EOF counts");
    for (unsigned pair = 0; pair < pairs; ++pair) {
        require(seen[pair] == population[pair] && picked[pair] == samples, "pair population and sample");
        require(std::fprintf(counts, "%u\t%u\t%u\n", pair, seen[pair], picked[pair]) > 0,
                "write counts");
    }
    require(std::fclose(requests) == 0 && std::fclose(positions) == 0 && std::fclose(counts) == 0,
            "close outputs");
    std::printf("{\"rows\":%llu,\"pairs\":%u,\"samples\":%llu,\"samples_per_pair\":%u}\n",
        static_cast<unsigned long long>(row), pairs, static_cast<unsigned long long>(selected), samples);
}
