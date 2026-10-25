#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <initializer_list>
#include <zstd.h>

#include "asset646.h"

extern "C" const unsigned char asset646_begin[], asset646_end[];
alignas(64) static unsigned char restored646[kRawBytes646];

static void require646(bool ok, const char* why) {
    if (!ok) {
        std::fprintf(stderr, "exp646: %s\n", why);
        std::exit(1);
    }
}

static double cpu646() {
    timespec value{};
    require646(clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) == 0, "clock");
    return double(value.tv_sec) + double(value.tv_nsec) / 1e9;
}

static void accumulate646(unsigned char* data, size_t rows, unsigned rank) {
    for (size_t i = rank; i < rows * rank; ++i)
        data[i] = static_cast<unsigned char>(unsigned(data[i]) + data[i - rank]);
}

static void selfCheck646() {
    for (unsigned rank : {64u, 96u}) {
        unsigned char original[4 * 96]{}, encoded[4 * 96]{};
        for (unsigned i = 0; i < 4 * rank; ++i)
            original[i] = static_cast<unsigned char>((i * 73 + 128) % 256);
        for (unsigned i = 0; i < 4 * rank; ++i)
            encoded[i] = static_cast<unsigned char>(
                unsigned(original[i]) - (i < rank ? 0u : unsigned(original[i - rank])));
        accumulate646(encoded, 4, rank);
        require646(std::memcmp(original, encoded, 4 * rank) == 0, "modular self-check");
    }
}

int main(int argc, char** argv) {
    require646(argc == 2, "restore OUTPUT_ASSET");
    selfCheck646();
    const double start = cpu646();
    const size_t compressed = size_t(asset646_end - asset646_begin);
    require646(ZSTD_getFrameContentSize(asset646_begin, compressed) == kRawBytes646,
               "frame content size");
    const size_t frame = ZSTD_findFrameCompressedSize(asset646_begin, compressed);
    require646(!ZSTD_isError(frame) && frame == compressed, "one complete frame");
    const size_t written = ZSTD_decompress(restored646, sizeof(restored646),
                                          asset646_begin, compressed);
    require646(!ZSTD_isError(written), ZSTD_getErrorName(written));
    require646(written == sizeof(restored646), "decoded length");
    const double decoded = cpu646();
    require646(std::memcmp(restored646, "EX589Q01", 8) == 0, "geometry magic");
    uint32_t meta[6]{};
    std::memcpy(meta, restored646 + 8, sizeof(meta));
    const uint32_t expected[6]{512, kFarRank646, 64, 64, 4800, 260160};
    require646(std::memcmp(meta, expected, sizeof(meta)) == 0, "geometry dimensions");
    size_t at = 64 + 59904 * 2;
    for (unsigned group = 0; group < 2; ++group) {
        const unsigned rank = group ? kFarRank646 : 512;
        const unsigned blocks = (rank + 63) / 64;
        const size_t rows[2]{group ? 4 * 59904u : 59904u, group ? 260160u : 4800u};
        for (size_t count : rows) {
            require646(at <= written && count * rank <= written - at, "factor bounds");
            if (kDelta646) accumulate646(restored646 + at, count, rank);
            at += count * rank;
        }
        require646(at <= written && (rows[0] + rows[1]) * blocks * 4 <= written - at,
                   "scale bounds");
        at += (rows[0] + rows[1]) * blocks * 4;
    }
    require646(at == written, "geometry EOF");
    const double ready = cpu646();
    FILE* output = std::fopen(argv[1], "wb");
    require646(output != nullptr, "open output");
    require646(std::fwrite(restored646, 1, written, output) == written, "write output");
    require646(std::fclose(output) == 0, "close output");
    std::fprintf(stderr,
        "{\"raw_bytes\":%zu,\"compressed_bytes\":%zu,\"delta\":%s,"
        "\"decoder_version\":\"%s\",\"decode_cpu_s\":%.9f,\"transform_cpu_s\":%.9f,"
        "\"restore_cpu_s\":%.9f,\"write_cpu_s\":%.9f,\"self_check_passed\":true}\n",
        written, compressed, kDelta646 ? "true" : "false", ZSTD_versionString(),
        decoded - start, ready - decoded, ready - start, cpu646() - ready);
}
