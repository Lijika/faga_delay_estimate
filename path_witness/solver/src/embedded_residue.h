#pragma once

#include <cstdint>
#include <stdexcept>
#include <vector>
#include <zstd.h>

#include "embedded_residue_data.h"

extern "C" const unsigned char delayest_residue_blob[];

namespace delayest {
namespace embedded_residue {

inline void decodeDx(const unsigned char* planes, std::vector<int32_t>& table,
                     int mx, int my, int quantum) {
  const size_t count = table.size();
  const size_t rowEntries = static_cast<size_t>(mx) * my * 4;
  if (mx <= 0 || my <= 0 || quantum <= 0 || count % rowEntries != 0) {
    throw std::runtime_error("embedded residue table shape differs");
  }
  size_t index = 0;
  for (size_t row = 0; row < count / rowEntries; ++row) {
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
      for (int y = 0; y < my; ++y) {
        uint16_t value = 0;
        for (int x = 0; x < mx; ++x, ++index) {
          const uint16_t delta = static_cast<uint16_t>(
              planes[index] | (static_cast<uint16_t>(planes[count + index]) << 8));
          value = static_cast<uint16_t>(value + delta);
          const int32_t signedValue = value <= 32767 ? value : int32_t(value) - 65536;
          table[row * rowEntries + (static_cast<size_t>(y) * mx + x) * 4 + quadrant] =
              value == 32768 ? INT32_MAX : signedValue * quantum;
        }
      }
    }
  }
}

inline void restore(std::vector<int32_t>& table) {
  if (table.size() != kEntries) {
    throw std::runtime_error("embedded residue table entry count differs");
  }
  std::vector<unsigned char> planes(kEntries * 2);
  const size_t frameBytes = ZSTD_findFrameCompressedSize(delayest_residue_blob, kBlobBytes);
  if (ZSTD_isError(frameBytes) || frameBytes != kBlobBytes ||
      ZSTD_getFrameContentSize(delayest_residue_blob, kBlobBytes) != planes.size()) {
    throw std::runtime_error("embedded residue frame metadata differs");
  }
  const size_t outputBytes = ZSTD_decompress(planes.data(), planes.size(),
                                            delayest_residue_blob, kBlobBytes);
  if (ZSTD_isError(outputBytes) || outputBytes != planes.size()) {
    throw std::runtime_error("embedded residue table decompression failed");
  }
  decodeDx(planes.data(), table, kModulusX, kModulusY, kQuantum);
}

}  // namespace embedded_residue
}  // namespace delayest
