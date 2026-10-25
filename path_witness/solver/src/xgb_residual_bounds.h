// Experiment 40: candidate residual features with the experiment 31 lower bound.
//
// The 47 feature slots are the 44 production slots plus
//   [44] L                    (port quotient + mandatory Line, architecture only)
//   [45] fast - L
//   [46] L / max(fast, 1)
// The tree data lives in the generated kXgbBounds* header.  Nothing here reads
// exact values or golden; the caller passes the L computed by lowerBound().
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "architecture.h"
#include "xgb_residual.h"
#include "xgb_residual_bounds_model.h"

namespace delayest {

static constexpr int kXgbBoundsFeatureTotal = 47;

// Fills the 44 production slots and then the three L-derived slots.
inline void xgbBoundsFeatures(const Architecture& arch, int sx, int sy, int sourcePort, int tx,
                              int ty, int targetPort, int fast, int lower, float* out) {
  xgbFeatures(arch, sx, sy, sourcePort, tx, ty, targetPort, fast, out);
  out[44] = static_cast<float>(lower);
  out[45] = static_cast<float>(fast - lower);
  out[46] = static_cast<float>(lower) / static_cast<float>(std::max(fast, 1));
}

// Same float summation order as the production walk.
inline float xgbBoundsRaw(const float* features) {
  float value = kXgbBoundsBaseScore;
  for (int tree = 0; tree < kXgbBoundsTreeCount; ++tree) {
    int32_t node = kXgbBoundsTreeRoots[tree];
    while (kXgbBoundsNodes[node].left != -1) {
      const XgbBoundsTreeNode& current = kXgbBoundsNodes[node];
      node = features[current.feature] < current.threshold ? current.left : current.right;
    }
    value += kXgbBoundsNodes[node].threshold;
  }
  return value;
}

}  // namespace delayest
