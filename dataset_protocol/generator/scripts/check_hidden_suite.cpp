#include "hidden_suite.h"

#include <filesystem>
#include <random>

using namespace hidden;
int main(int argc, char** argv) {
  if (argc != 8) {
    std::fprintf(stderr, "usage: check_hidden_suite <arch> <reach.bin> <eligibility.bin> <profile> <rows> <csv> <new-check-directory>\n");
    return 2;
  }
  try {
    const std::string profile = argv[4], directory = argv[7];
    require(profile == "U-output" || profile == "U-role", "bad profile");
    const uint64_t wanted = std::stoull(argv[5]);
    require(std::filesystem::create_directory(directory), "check directory already exists");
    Domain d(argv[1], argv[2], profile == "U-role");
    std::ifstream eligibility(argv[3], std::ios::binary);
    char magic[8];
    eligibility.read(magic, 8);
    require(bool(eligibility) && std::string(magic, 8) == "HEQUAL01", "bad independent eligibility");
    std::vector<uint32_t> cells(d.cells.size());
    eligibility.read(reinterpret_cast<char*>(cells.data()), cells.size() * 4);
    require(cells == d.cells, "independent tile mapping differs");
    std::vector<uint8_t> source(d.sourceOK.size()), target(d.targetOK.size()), direct(d.direct.size());
    eligibility.read(reinterpret_cast<char*>(source.data()), source.size());
    eligibility.read(reinterpret_cast<char*>(target.data()), target.size());
    eligibility.read(reinterpret_cast<char*>(direct.data()), direct.size());
    require(bool(eligibility) && eligibility.peek() == EOF && direct == d.direct,
            "independent eligibility dimensions/Arc differ");
    for (unsigned t = 0; t < cells.size(); ++t) {
      for (int p : d.sources) require(source[t * 496 + p] == d.sourceOK[t * 496 + p], "source eligibility differs");
      for (int p : d.targets) require(target[t * 496 + p] == d.targetOK[t * 496 + p], "target eligibility differs");
    }
    std::array<bool, 496> fromAllowed{}, toAllowed{};
    for (int p : d.sources) fromAllowed[p] = true;
    for (int p : d.targets) toAllowed[p] = true;
    std::array<FILE*, 256> buckets{};
    for (unsigned b = 0; b < 256; ++b) {
      const std::string path = directory + "/pairs-" + std::to_string(b) + ".bin";
      buckets[b] = std::fopen(path.c_str(), "wb");
      require(buckets[b], "cannot create pair bucket");
      require(std::setvbuf(buckets[b], nullptr, _IOFBF, 1 << 18) == 0, "pair bucket buffering failed");
    }
    std::ifstream input(argv[6], std::ios::binary);
    std::string line;
    require(bool(std::getline(input, line)) && line == "From,To", "unexpected CSV header");
    Stats stats(d);
    struct Sample { uint64_t row, pair; unsigned stratum; };
    std::array<std::vector<Sample>, 64> samples;
    std::array<uint64_t, 64> seen{};
    const uint64_t sampleSeed = profile == "U-role" ? 2026101402 : 2026101401;
    std::mt19937_64 sampleRng(sampleSeed);
    uint64_t bytes = 8;
    while (std::getline(input, line)) {
      require(!input.eof() && !line.empty() && line.find('\r') == std::string::npos, "CSV newline contract failed");
      const auto comma = line.find(',');
      require(comma != std::string::npos && line.find(',', comma + 1) == std::string::npos, "CSV field count differs");
      int sx, sy, sp, tx, ty, tp;
      const std::string_view text(line);
      require(d.arch.parsePin(text.substr(0, comma), sx, sy, sp) &&
                  d.arch.parsePin(text.substr(comma + 1), tx, ty, tp), "invalid pin");
      require(fromAllowed[sp] && toAllowed[tp], "invalid endpoint role");
      const int ft = d.tileAt[sy * 120 + sx], tt = d.tileAt[ty * 120 + tx];
      require(ft >= 0 && tt >= 0, "pin tile does not exist");
      const uint32_t f = ft * 496 + sp, t = tt * 496 + tp;
      require(f != t, "self query");
      require((source[f] && target[t]) || (ft == tt && direct[sp * 496 + tp]),
              "independent reachability failed");
      const uint64_t key = (uint64_t(f) << 32) | t;
      // The bucket assignment changes cost only; full 64-bit keys determine equality.
      const uint64_t folded = key ^ (key >> 17) ^ (key >> 37);
      require(std::fwrite(&key, 8, 1, buckets[folded & 255]) == 1, "pair bucket write failed");
      stats.add(d, key, true);
      const int distance = std::abs(tx - sx) + std::abs(ty - sy);
      auto type = [&](int p) { const char c = d.arch.portName(p)[0]; return c == 'Z' ? 0 : c == 'A' ? 1 : 2; };
      const unsigned stratum = distance == 0 ? 63 : (type(sp) * 3 + type(tp)) * 7 + band(distance);
      const uint64_t available = ++seen[stratum];
      const unsigned capacity = stratum == 63 ? 1024 : profile == "U-role" ? 2048 : 4096;
      auto& sample = samples[stratum];
      if (sample.size() < capacity) {
        sample.push_back({stats.rows - 1, key, stratum});
      } else {
        const uint64_t threshold = -available % available;
        uint64_t random;
        do { random = sampleRng(); } while (random < threshold);
        const uint64_t slot = random % available;
        if (slot < capacity) sample[slot] = {stats.rows - 1, key, stratum};
      }
      bytes += line.size() + 1;
      if (stats.rows % 10000000 == 0)
        std::fprintf(stderr, "checked_csv_rows=%llu\n", (unsigned long long)stats.rows);
    }
    require(input.eof() && stats.rows == wanted && bytes == std::filesystem::file_size(argv[6]),
            "CSV count/EOF/size failed");
    for (auto file : buckets) require(std::fclose(file) == 0, "pair bucket close failed");
    uint64_t duplicates = 0, unique = 0;
    for (unsigned b = 0; b < 256; ++b) {
      const std::string path = directory + "/pairs-" + std::to_string(b) + ".bin";
      const uint64_t size = std::filesystem::file_size(path);
      require(size % 8 == 0, "short pair bucket");
      std::vector<uint64_t> pairs(size / 8);
      std::ifstream bucket(path, std::ios::binary);
      bucket.read(reinterpret_cast<char*>(pairs.data()), size);
      require(bool(bucket), "pair bucket read failed");
      std::sort(pairs.begin(), pairs.end());
      for (size_t i = 1; i < pairs.size(); ++i) duplicates += pairs[i] == pairs[i - 1];
      unique += pairs.size();
      if (b % 16 == 15) std::fprintf(stderr, "dedup_buckets=%u\n", b + 1);
    }
    require(duplicates == 0 && unique == wanted, "exact CSV dedup failed");
    std::vector<Sample> allSamples;
    for (auto& stratum : samples) allSamples.insert(allSamples.end(), stratum.begin(), stratum.end());
    std::sort(allSamples.begin(), allSamples.end(), [](const Sample& a, const Sample& b) { return a.row < b.row; });
    std::ofstream sampleOut(directory + "/label-sample.csv");
    sampleOut << "row_ordinal,From,To,stratum\n";
    for (const auto& s : allSamples)
      sampleOut << s.row << ',' << d.pin(s.pair >> 32) << ',' << d.pin(uint32_t(s.pair)) << ',' << s.stratum << '\n';
    sampleOut.close();
    require(bool(sampleOut), "label sample write failed");
    std::ofstream report(directory + "/check.json");
    report << "{\"status\":\"passed\",\"rows\":" << wanted << ",\"bytes\":" << bytes
           << ",\"unique_rows\":" << unique << ",\"duplicate_rows\":" << duplicates
           << ",\"self_rows\":0,\"unreachable_rows\":0,\"independent_json_eligibility\":true"
           << ",\"label_sample_seed\":" << sampleSeed << ",\"label_sample_rows\":" << allSamples.size()
           << ",\"label_sample_population\":";
    Stats::array(report, seen);
    report << ",\"stats\":";
    stats.json(report);
    report << "}\n";
    report.close();
    require(bool(report), "check report write failed");
  } catch (const std::exception& error) {
    std::fprintf(stderr, "check_hidden_suite: %s\n", error.what());
    return 1;
  }
}
