#include <zstd.h>

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static void check(size_t status, const char* operation) {
  if (ZSTD_isError(status)) {
    throw std::runtime_error(std::string(operation) + ": " + ZSTD_getErrorName(status));
  }
}

int main(int argc, char** argv) {
  try {
    if (argc != 6) {
      std::fprintf(stderr, "usage: zstd_capacity <level> <input> <output> <roundtrip> "
                           "<previous-or-dash>\n");
      return 2;
    }
    const int level = std::stoi(argv[1]);
    if (level != 3 && level != 9 && level != 19) throw std::runtime_error("level differs");
    for (int i : {3, 4})
      if (std::string(argv[i]) != "/dev/null" && std::ifstream(argv[i]).good())
        throw std::runtime_error("output already exists");
    std::ifstream input(argv[2], std::ios::binary);
    if (!input) throw std::runtime_error("input open failed");
    std::vector<char> source((std::istreambuf_iterator<char>(input)),
                             std::istreambuf_iterator<char>());
    if (input.bad() || source.size() != 230'031'360)
      throw std::runtime_error("input size differs");
    const size_t bound = ZSTD_compressBound(source.size());
    std::vector<char> compressed(bound);
    ZSTD_CCtx* context = ZSTD_createCCtx();
    if (!context) throw std::runtime_error("compression context allocation failed");
    check(ZSTD_CCtx_setParameter(context, ZSTD_c_compressionLevel, level), "set level");
    check(ZSTD_CCtx_setParameter(context, ZSTD_c_checksumFlag, 1), "enable checksum");
    check(ZSTD_CCtx_setParameter(context, ZSTD_c_contentSizeFlag, 1), "enable content size");
    check(ZSTD_CCtx_setParameter(context, ZSTD_c_nbWorkers, 0), "disable workers");
    const size_t compressedSize =
        ZSTD_compress2(context, compressed.data(), compressed.size(), source.data(), source.size());
    check(compressedSize, "compress");
    ZSTD_freeCCtx(context);
    compressed.resize(compressedSize);
    bool repeatedEqual = std::string(argv[5]) == "-";
    if (!repeatedEqual) {
      std::ifstream previous(argv[5], std::ios::binary);
      if (!previous) throw std::runtime_error("previous frame open failed");
      std::vector<char> expected((std::istreambuf_iterator<char>(previous)),
                                 std::istreambuf_iterator<char>());
      repeatedEqual = expected == compressed;
      if (!repeatedEqual) throw std::runtime_error("repeat compression differs");
    }
    const size_t frameSize = ZSTD_findFrameCompressedSize(compressed.data(), compressed.size());
    check(frameSize, "find frame");
    if (frameSize != compressed.size() ||
        ZSTD_getFrameContentSize(compressed.data(), compressed.size()) != source.size())
      throw std::runtime_error("frame metadata or exact EOF differs");
    std::vector<char> decoded(source.size());
    const size_t outputSize = ZSTD_decompress(decoded.data(), decoded.size(),
                                              compressed.data(), compressed.size());
    check(outputSize, "decompress");
    if (outputSize != source.size() || decoded != source)
      throw std::runtime_error("byte-for-byte round trip differs");
    if (std::string(argv[3]) != "/dev/null") {
      std::ofstream packed(argv[3], std::ios::binary | std::ios::trunc);
      packed.write(compressed.data(), static_cast<std::streamsize>(compressed.size()));
      packed.close();
      if (!packed) throw std::runtime_error("compressed evidence write failed");
    }
    if (std::string(argv[4]) != "/dev/null") {
      std::ofstream restored(argv[4], std::ios::binary | std::ios::trunc);
      restored.write(decoded.data(), static_cast<std::streamsize>(decoded.size()));
      if (!restored) throw std::runtime_error("restored evidence write failed");
    }
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
}
