#pragma once

#ifdef DELAY_ESTIMATE_PRECOMPUTED_TEMPLATES

#include <cstdint>
#include <stdexcept>
#include <vector>

#include <zstd.h>

#include "architecture.h"
#include "embedded_templates_data.h"

extern "C" const unsigned char delayest_template_blob[];

namespace delayest {
namespace embedded_templates {

inline void restore(const Architecture& arch, const std::vector<int>& zIndexOfPort,
                    std::vector<uint16_t>& values, std::vector<int>& fieldByPort) {
  constexpr size_t kSlots = static_cast<size_t>(Architecture::kCellCount) * 160;
  if (kFieldCount != 12 || kFieldBytes != kSlots * sizeof(uint16_t) ||
      zIndexOfPort.size() != static_cast<size_t>(arch.portCount())) {
    throw std::runtime_error("embedded template schema differs");
  }
  values.resize(kFieldCount * kSlots);
  fieldByPort.assign(static_cast<size_t>(arch.portCount()), -1);
  for (size_t field = 0; field < kFieldCount; ++field) {
    const int port = arch.portId(kPorts[field]);
    if (port < 0 || !arch.isNetSource(port) || fieldByPort[port] >= 0 ||
        kOffsets[field] > kBlobBytes || kFrameBytes[field] > kBlobBytes - kOffsets[field]) {
      throw std::runtime_error("embedded template field metadata differs");
    }
    const unsigned char* frame = delayest_template_blob + kOffsets[field];
    const size_t frameBytes = kFrameBytes[field];
    const size_t actualFrameBytes = ZSTD_findFrameCompressedSize(frame, frameBytes);
    if (ZSTD_isError(actualFrameBytes) || actualFrameBytes != frameBytes ||
        ZSTD_getFrameContentSize(frame, frameBytes) != kFieldBytes) {
      throw std::runtime_error("embedded template frame metadata differs");
    }
    std::vector<unsigned char> planes(kFieldBytes);
    const size_t decodedPlanes = ZSTD_decompress(planes.data(), planes.size(), frame, frameBytes);
    if (ZSTD_isError(decodedPlanes) || decodedPlanes != kFieldBytes) {
      throw std::runtime_error("embedded template field decompression failed");
    }
    uint16_t* output = values.data() + field * kSlots;
    for (size_t index = 0; index < kSlots; ++index) {
      output[index] = static_cast<uint16_t>(
          planes[index] | (static_cast<uint16_t>(planes[kSlots + index]) << 8));
    }
    for (size_t z = 0; z < 160; ++z) {
      for (size_t y = 1; y < 550; ++y) {
        uint16_t* row = output + (z * 550 + y) * 120;
        const uint16_t* previous = row - 120;
        for (size_t x = 0; x < 120; ++x) {
          row[x] = static_cast<uint16_t>(row[x] + previous[x]);
        }
      }
    }
    const int zIndex = zIndexOfPort[port];
    if (zIndex < 0) {
      throw std::runtime_error("embedded template port is outside Z schema");
    }
    const size_t own = (static_cast<size_t>(zIndex) * Architecture::kCellCount +
                        284 * Architecture::kWidth + 60);
    if (output[own] != 0) {
      throw std::runtime_error("embedded template anchor differs");
    }
    fieldByPort[port] = static_cast<int>(field);
  }
}

}  // namespace embedded_templates
}  // namespace delayest

#endif
