#include "hidden_suite.h"

#include <cstring>
#include <filesystem>
#include <random>

using namespace hidden;

struct Record {
  uint64_t high, low, pair;
  bool operator<(const Record& other) const {
    if (high != other.high) return high < other.high;
    if (low != other.low) return low < other.low;
    return pair < other.pair;
  }
};
static_assert(sizeof(Record) == 24);
uint64_t mix(uint64_t v) {
  v ^= v >> 30; v *= 0xbf58476d1ce4e5b9ULL;
  v ^= v >> 27; v *= 0x94d049bb133111ebULL;
  return v ^ (v >> 31);
}
uint64_t bounded(std::mt19937_64& rng, uint64_t size) {
  const uint64_t threshold = -size % size;
  uint64_t r;
  do { r = rng(); } while (r < threshold);
  return r % size;
}
int main(int argc, char** argv) {
  if (argc != 8) {
    std::fprintf(stderr, "usage: make_hidden_suite <arch> <reach.bin> <U-output|U-role> <rows> <proposal-seed> <shuffle-seed> <new-directory>\n");
    return 2;
  }
  try {
    const std::string profile = argv[3], directory = argv[7];
    require(profile == "U-output" || profile == "U-role", "bad profile");
    const uint64_t wanted = std::stoull(argv[4]);
    require(wanted > 0 && wanted <= 1000000000, "bad rows");
    require(std::filesystem::create_directory(directory), "output directory already exists");
    Domain domain(argv[1], argv[2], profile == "U-role");
    std::mt19937_64 proposal(std::stoull(argv[5])), shuffle(std::stoull(argv[6]));
    size_t slots = 1;
    while (slots < wanted * 2) slots *= 2;
    std::vector<uint64_t> table(slots, UINT64_MAX);
    std::array<FILE*, 256> buckets{};
    for (unsigned b = 0; b < 256; ++b) {
      const std::string path = directory + "/shuffle-" + std::to_string(b) + ".bin";
      buckets[b] = std::fopen(path.c_str(), "wb");
      require(buckets[b], "cannot create shuffle bucket");
      require(std::setvbuf(buckets[b], nullptr, _IOFBF, 1 << 18) == 0, "bucket buffering failed");
    }
    FILE* accepted = std::fopen((directory + "/accepted.bin").c_str(), "wb");
    require(accepted, "cannot create accepted records");
    Stats proposed(domain), retained(domain);
    uint64_t self = 0, unreachable = 0, duplicates = 0, count = 0;
    while (count < wanted) {
      const uint32_t ft = bounded(proposal, domain.cells.size());
      const uint32_t fp = domain.sources[bounded(proposal, domain.sources.size())];
      const uint32_t tt = bounded(proposal, domain.cells.size());
      const uint32_t tp = domain.targets[bounded(proposal, domain.targets.size())];
      const uint32_t f = ft * 496 + fp, t = tt * 496 + tp;
      const uint64_t pair = (uint64_t(f) << 32) | t;
      proposed.add(domain, pair);
      if (f == t) { ++self; continue; }
      if (!domain.reachable(f, t)) { ++unreachable; continue; }
      size_t slot = mix(pair) & (slots - 1);
      while (table[slot] != UINT64_MAX && table[slot] != pair) slot = (slot + 1) & (slots - 1);
      if (table[slot] == pair) { ++duplicates; continue; }
      table[slot] = pair;
      const Record record{shuffle(), shuffle(), pair};
      require(std::fwrite(&record, sizeof(record), 1, buckets[record.high >> 56]) == 1,
              "shuffle bucket write failed");
      // Retain the original proposal ordinal for independent first-occurrence audit.
      const uint64_t identity[] = {pair, proposed.rows - 1};
      require(std::fwrite(identity, sizeof(identity), 1, accepted) == 1, "accepted write failed");
      retained.add(domain, pair);
      ++count;
      if (count % 10000000 == 0) {
        std::fprintf(stderr, "accepted=%llu proposed=%llu unreachable=%llu duplicate=%llu\n",
                     (unsigned long long)count, (unsigned long long)proposed.rows,
                     (unsigned long long)unreachable, (unsigned long long)duplicates);
      }
    }
    for (auto file : buckets) require(std::fclose(file) == 0, "bucket close failed");
    require(std::fclose(accepted) == 0, "accepted close failed");
    table.clear(); table.shrink_to_fit();
    std::vector<std::string> names(domain.cells.size() * 496);
    std::vector<uint8_t> needed(496);
    for (int p : domain.sources) needed[p] = 1;
    for (int p : domain.targets) needed[p] = 1;
    for (unsigned t = 0; t < domain.cells.size(); ++t)
      for (unsigned p = 0; p < 496; ++p) if (needed[p]) names[t * 496 + p] = domain.pin(t * 496 + p);
    FILE* csv = std::fopen((directory + "/requests.csv").c_str(), "wb");
    require(csv, "cannot create CSV");
    require(std::fwrite("From,To\n", 8, 1, csv) == 1, "CSV header write failed");
    std::string buffer;
    buffer.reserve(1 << 23);
    Stats output(domain);
    uint64_t ties = 0, bytes = 8;
    Record previous{};
    bool havePrevious = false;
    for (unsigned b = 0; b < 256; ++b) {
      const std::string path = directory + "/shuffle-" + std::to_string(b) + ".bin";
      const uint64_t size = std::filesystem::file_size(path);
      require(size % sizeof(Record) == 0, "short shuffle bucket");
      std::vector<Record> records(size / sizeof(Record));
      std::ifstream in(path, std::ios::binary);
      in.read(reinterpret_cast<char*>(records.data()), size);
      require(bool(in), "shuffle bucket read failed");
      std::sort(records.begin(), records.end());
      for (const Record& record : records) {
        if (havePrevious) {
          require(!(record < previous), "shuffle order mismatch");
          ties += record.high == previous.high && record.low == previous.low;
        }
        previous = record; havePrevious = true;
        output.add(domain, record.pair, true);
        buffer += names[record.pair >> 32];
        buffer += ',';
        buffer += names[uint32_t(record.pair)];
        buffer += '\n';
        if (buffer.size() >= (1 << 22)) {
          require(std::fwrite(buffer.data(), buffer.size(), 1, csv) == 1, "CSV write failed");
          bytes += buffer.size(); buffer.clear();
        }
      }
      if (b % 16 == 15) std::fprintf(stderr, "shuffle_buckets=%u csv_rows=%llu\n", b + 1, (unsigned long long)output.rows);
    }
    if (!buffer.empty()) {
      require(std::fwrite(buffer.data(), buffer.size(), 1, csv) == 1, "CSV tail write failed");
      bytes += buffer.size();
    }
    require(std::fclose(csv) == 0 && output.rows == wanted, "incomplete CSV");
    std::ofstream report(directory + "/generation.json");
    report << "{\"profile\":\"" << profile << "\",\"rows\":" << wanted
           << ",\"proposal_seed\":" << argv[5] << ",\"shuffle_seed\":" << argv[6]
           << ",\"rng\":\"std::mt19937_64 C++17; rejection modulo for bounded integers\""
           << ",\"proposed_rows\":" << proposed.rows << ",\"rejected_self_rows\":" << self
           << ",\"rejected_unreachable_rows\":" << unreachable << ",\"duplicate_proposals\":" << duplicates
           << ",\"shuffle_ties\":" << ties << ",\"bytes\":" << bytes << ",\"proposed\":";
    proposed.json(report); report << ",\"retained\":"; retained.json(report);
    report << ",\"output\":"; output.json(report); report << "}\n";
    report.close();
    require(bool(report), "generation report write failed");
    std::fprintf(stderr, "done rows=%llu bytes=%llu\n", (unsigned long long)wanted, (unsigned long long)bytes);
  } catch (const std::exception& error) {
    std::fprintf(stderr, "make_hidden_suite: %s\n", error.what());
    return 1;
  }
}
