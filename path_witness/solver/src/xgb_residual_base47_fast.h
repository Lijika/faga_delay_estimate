#pragma once

#include "xgb_residual_base47_fast_model.h"

namespace delayest {

inline float xgbBase47FastRaw(const float* features) {
  float value = kXgbB47FastBaseScore;
  for (int tree = 0; tree < kXgbB47FastTreeCount; ++tree) {
    const int nodeBase = tree * kXgbB47FastNodesPerTree;
    int node = 0;
#pragma GCC unroll 8
    for (int level = 0; level < kXgbB47FastDepth; ++level) {
      const XgbB47FastNode& current = kXgbB47FastNodes[nodeBase + node];
      node = 2 * node + 1 + (features[current.feature] < current.threshold ? 0 : 1);
    }
    value += kXgbB47FastLeaves[tree * kXgbB47FastLeavesPerTree + node -
                               (kXgbB47FastLeavesPerTree - 1)];
  }
  return value;
}

}  // namespace delayest
