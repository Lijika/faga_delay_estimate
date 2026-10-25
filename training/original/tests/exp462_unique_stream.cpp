#include "../src/csv.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>

using delayest::BufferedWriter;

namespace {
void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

uint64_t mix(uint64_t value) {
  value ^= value >> 30; value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27; value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31);
}

struct Permutation {
  uint64_t size, mask;
  unsigned half = 1;
  std::array<uint64_t, 6> keys{};

  Permutation(uint64_t count, uint64_t seed) : size(count) {
    require(count > 0 && count < (uint64_t(1) << 62), "bad permutation domain");
    while ((uint64_t(1) << (2 * half)) < size) ++half;
    mask = (uint64_t(1) << half) - 1;
    for (unsigned r = 0; r < keys.size(); ++r)
      keys[r] = mix(seed ^ (0x9e3779b97f4a7c15ULL * (r + 1)));
  }

  uint64_t block(uint64_t value, bool reverse) const {
    uint64_t left = value >> half, right = value & mask;
    for (unsigned r = 0; r < keys.size(); ++r) {
      if (reverse) {
        const uint64_t before = right ^ (mix(left ^ keys[keys.size() - 1 - r]) & mask);
        right = left; left = before;
      } else {
        const uint64_t after = left ^ (mix(right ^ keys[r]) & mask);
        left = right; right = after;
      }
    }
    return (left << half) | right;
  }

  uint64_t apply(uint64_t value, bool reverse = false) const {
    require(value < size, "permutation input outside domain");
    do { value = block(value, reverse); } while (value >= size);
    return value;
  }
};

std::vector<std::string> lines(const char* path) {
  std::ifstream input(path);
  require(bool(input), "list open failed");
  std::vector<std::string> values;
  std::string line;
  while (std::getline(input, line)) {
    require(!line.empty(), "empty list entry");
    values.push_back(line);
  }
  require(input.eof() && !values.empty(), "list read failed");
  require(std::set<std::string>(values.begin(), values.end()).size() == values.size(),
          "duplicate list entry");
  return values;
}

FILE* create(const std::string& path) {
  require(!std::filesystem::exists(path), "output exists");
  FILE* file = std::fopen(path.c_str(), "wb");
  require(file != nullptr, "output open failed");
  return file;
}

void generate(char** argv) {
  const auto sources = lines(argv[2]), cells = lines(argv[3]), ports = lines(argv[4]);
  const uint64_t rows = std::stoull(argv[5]), seed = std::stoull(argv[6]);
  const uint64_t targets = cells.size() * ports.size(), total = sources.size() * targets;
  require(rows > 0 && rows <= total, "bad request count");
  Permutation permutation(total, seed);
  FILE* file = create(argv[7]);
  FILE* warm = create(argv[8]);
  BufferedWriter output(file), warmup(warm);
  require(output.write("From,To\n", 8) && warmup.write("From,To\n", 8), "header write failed");
  std::string line;
  for (uint64_t i = 0; i < rows; ++i) {
    const uint64_t key = permutation.apply(i);
    // Checking every inverse ties uniqueness to the actual emitted ordinal.
    require(permutation.apply(key, true) == i, "inverse ordinal differs");
    const uint64_t source = key / targets, target = key % targets;
    line = sources[source];
    line += ',';
    line += cells[target / ports.size()];
    line += ports[target % ports.size()];
    line += '\n';
    require(output.write(line), "request write failed");
    if (i < 20000) require(warmup.write(line), "warmup write failed");
  }
  require(output.flush() && warmup.flush(), "flush failed");
  require(std::fclose(file) == 0 && std::fclose(warm) == 0, "close failed");
  std::cout << "{\"rows\":" << rows << ",\"unique_pairs\":" << rows
            << ",\"inverse_checks\":" << rows << ",\"universe\":" << total
            << ",\"source_pins\":" << sources.size() << ",\"target_pins\":" << targets << "}\n";
}

void check(char** argv) {
  std::ifstream input(argv[2], std::ios::binary), output(argv[3], std::ios::binary);
  require(bool(input) && bool(output), "CSV open failed");
  const uint64_t wanted = std::stoull(argv[4]);
  const auto positions = lines(argv[5]);
  std::vector<uint64_t> selected;
  for (const auto& text : positions) selected.push_back(std::stoull(text));
  require(std::is_sorted(selected.begin(), selected.end()) &&
          std::adjacent_find(selected.begin(), selected.end()) == selected.end() &&
          selected.back() < wanted,
          "bad sample positions");
  FILE* sampleFile = create(argv[6]);
  BufferedWriter sample(sampleFile);
  require(sample.write("row,From,To,delay\n", 18), "sample header write failed");
  std::string request, result;
  require(bool(std::getline(input, request)) && request == "From,To", "input header differs");
  require(bool(std::getline(output, result)) && result == "From,To,delay", "output header differs");
  size_t next = 0;
  uint64_t inputBytes = 8, outputBytes = 14;
  for (uint64_t i = 0; i < wanted; ++i) {
    require(bool(std::getline(input, request)) && !input.eof(), "input row/newline missing");
    require(bool(std::getline(output, result)) && !output.eof(), "output row/newline missing");
    const size_t first = request.find(',');
    require(first != std::string::npos && request.find(',', first + 1) == std::string::npos,
            "input field count differs");
    require(result.size() > request.size() + 1 &&
            result.compare(0, request.size(), request) == 0 && result[request.size()] == ',',
            "endpoint order differs");
    const char* begin = result.data() + request.size() + 1;
    const char* end = result.data() + result.size();
    int delay = -2;
    const auto parsed = std::from_chars(begin, end, delay);
    require(parsed.ec == std::errc{} && parsed.ptr == end && delay >= -1, "bad integer delay");
    char canonical[16];
    const auto written = std::to_chars(canonical, canonical + sizeof(canonical), delay);
    require(written.ec == std::errc{} && std::string_view(canonical, written.ptr - canonical) ==
            std::string_view(begin, end - begin), "delay text differs");
    inputBytes += request.size() + 1; outputBytes += result.size() + 1;
    if (next < selected.size() && selected[next] == i) {
      const std::string row = std::to_string(i) + "," + result + "\n";
      require(sample.write(row), "sample write failed");
      ++next;
    }
  }
  require(!std::getline(input, request) && input.eof() &&
          !std::getline(output, result) && output.eof(), "trailing CSV data/read error");
  require(inputBytes == std::filesystem::file_size(argv[2]) &&
          outputBytes == std::filesystem::file_size(argv[3]), "CSV byte count differs");
  require(next == selected.size() && sample.flush() && std::fclose(sampleFile) == 0,
          "incomplete sample");
  std::cout << "{\"rows\":" << wanted << ",\"input_bytes\":" << inputBytes
            << ",\"output_bytes\":" << outputBytes << ",\"sample_rows\":" << next
            << ",\"contract_passed\":true}\n";
}

void selfcheck() {
  uint64_t checks = 0;
  for (uint64_t size = 1; size <= 257; ++size)
    for (uint64_t seed : {uint64_t(0), uint64_t(20261018462), UINT64_MAX}) {
      Permutation permutation(size, seed);
      std::set<uint64_t> found;
      for (uint64_t i = 0; i < size; ++i) {
        const uint64_t key = permutation.apply(i);
        require(found.insert(key).second && permutation.apply(key, true) == i,
                "small-domain permutation differs");
        ++checks;
      }
    }
  std::cout << "{\"all_passed\":true,\"permutation_checks\":" << checks << "}\n";
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "selfcheck") selfcheck();
    else if (argc == 9 && std::string(argv[1]) == "generate") generate(argv);
    else if (argc == 7 && std::string(argv[1]) == "check") check(argv);
    else throw std::runtime_error(
      "usage: unique-stream selfcheck | generate SOURCES CELLS PORTS ROWS SEED OUTPUT WARMUP"
      " | check INPUT OUTPUT ROWS POSITIONS SAMPLE");
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
