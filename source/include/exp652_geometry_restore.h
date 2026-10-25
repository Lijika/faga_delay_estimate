#pragma once
#include <zstd.h>

extern "C" const unsigned char exp652_compressed_begin[], exp652_compressed_end[];
alignas(64) static unsigned char exp579_geometry[kGeometryBytes];

static void restoreGeometry652() {
    const size_t compressed = size_t(exp652_compressed_end - exp652_compressed_begin);
    require(ZSTD_getFrameContentSize(exp652_compressed_begin, compressed) == kGeometryBytes,
            "compressed geometry content size");
    const size_t frame = ZSTD_findFrameCompressedSize(exp652_compressed_begin, compressed);
    require(!ZSTD_isError(frame) && frame == compressed, "compressed geometry frame");
    const size_t written = ZSTD_decompress(exp579_geometry, sizeof(exp579_geometry),
                                          exp652_compressed_begin, compressed);
    require(!ZSTD_isError(written), ZSTD_getErrorName(written));
    require(written == sizeof(exp579_geometry), "restored geometry length");
#ifdef EXP579_AUDIT
    FILE* output = std::fopen("build/exp720/restored.bin", "wb");
    require(output != nullptr, "restored audit open");
    require(std::fwrite(exp579_geometry, 1, written, output) == written, "restored audit write");
    require(std::fclose(output) == 0, "restored audit close");
#endif
}
