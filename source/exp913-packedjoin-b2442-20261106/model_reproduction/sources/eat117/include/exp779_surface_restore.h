#pragma once
#include <zstd.h>
#include "surface_assets779.h"

alignas(64) static uint32_t records779[59904 * 480];
alignas(64) static int16_t first779[4 * 2048 * 552];
alignas(64) static int16_t second779[4 * 256 * 552];
alignas(64) static unsigned char scratch779[sizeof(first779)];

static void decompress779(unsigned part, size_t bytes) {
    const auto& frame = frames779[part];
    const auto* begin = surface779_begin + frame.offset;
    // Streaming frames omit content size; verify the actual decoded length below.
    const size_t size = ZSTD_findFrameCompressedSize(begin, frame.bytes);
    require(!ZSTD_isError(size) && size == frame.bytes, "surface frame length");
    const size_t written = ZSTD_decompress(scratch779, sizeof(scratch779), begin, frame.bytes);
    require(!ZSTD_isError(written), ZSTD_getErrorName(written));
    require(written == bytes, "surface restored length");
}

static void restoreBook779(unsigned part, int16_t* values, size_t count) {
    decompress779(part, count * 2);
    uint16_t previous = 0;
    for (size_t i = 0; i < count; ++i) {
        uint16_t value = uint16_t(scratch779[i] | (unsigned(scratch779[count + i]) << 8));
        if (frames779[part].delta && i % 552) value = uint16_t(value + previous);
        previous = value;
        std::memcpy(values + i, &value, sizeof(value));
    }
}

static void restoreSurfaces779() {
    restoreBook779(0, first779, 4 * 2048 * 552);
    restoreBook779(1, second779, 4 * 256 * 552);
    constexpr unsigned rows = 288 * 480;
    for (unsigned source = 0; source < 208; ++source) {
        decompress779(source + 2, rows * 5);
        unsigned pc = 0, pa = 0, pb = 0;
        for (unsigned i = 0; i < rows; ++i) {
            unsigned c = scratch779[i] | (unsigned(scratch779[rows + i]) << 8);
            unsigned a = scratch779[2 * rows + i] | (unsigned(scratch779[3 * rows + i]) << 8);
            unsigned b = scratch779[4 * rows + i];
            if (frames779[source + 2].delta && i % 12) {
                c = (c + pc) & 65535; a = (a + pa) & 65535; b = (b + pb) & 255;
            }
            pc = c; pa = a; pb = b;
            require(c <= 1011 && a < 2048 && b < 256, "surface code range");
            records779[source * rows + i] = c | (a << 10) | (b << 22);
        }
    }
#ifdef EXP579_AUDIT
    const void* data[] = {records779, first779, second779};
    const size_t bytes[] = {sizeof(records779), sizeof(first779), sizeof(second779)};
    const char* names[] = {"build/exp779/restored-records.u32", "build/exp779/restored-first.i16",
                          "build/exp779/restored-second.i16"};
    for (unsigned i = 0; i < 3; ++i) {
        FILE* file = std::fopen(names[i], "wb");
        require(file && std::fwrite(data[i], 1, bytes[i], file) == bytes[i], "surface audit write");
        require(std::fclose(file) == 0, "surface audit close");
    }
#endif
}

static inline int surface779(uint32_t word, unsigned context, unsigned qx, unsigned qy) {
    const unsigned direction = context / 120, cell = qx * 46 + qy;
    return int(word & 1023) - 67 +
        first779[(direction * 2048 + ((word >> 10) & 4095)) * 552 + cell] +
        second779[(direction * 256 + (word >> 22)) * 552 + cell];
}
