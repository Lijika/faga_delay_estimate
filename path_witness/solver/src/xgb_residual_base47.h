// Experiment 58: base-feature residual with the frozen 47-slot depth-8 model.
//
// The 47 slots are the 44 production slots of xgbFeatures() plus
//   [44] base                 (pure residue answer before endpoint refinement)
//   [45] base - fast
//   [46] base / max(fast, 1)
// and nothing else: the experiment 40/41 L group is absent from this model, so
// this path never calls lowerBound() and never builds the quotient bounds table.
// The tree data lives in the generated kXgbB47* header; the caller only passes
// the finished estimate (`fast` value) and the pre-endpoint answer (baseValue).
// Nothing here reads exact values or golden.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "architecture.h"
#include "xgb_residual.h"
#include "xgb_residual_base47_model.h"

namespace delayest {

// Builds the frozen 47 columns in the exact training order: xgbFeatures() fills
// slots 0..43 (including the zero fill of the six masked production slots), then
// the three architecture-computable base columns are appended.
inline void xgbBase47Features(const Architecture& arch, int sx, int sy, int sourcePort, int tx,
                              int ty, int targetPort, int fast, int baseValue, float* out) {
  xgbFeatures(arch, sx, sy, sourcePort, tx, ty, targetPort, fast, out);
  out[44] = static_cast<float>(baseValue);
  out[45] = static_cast<float>(baseValue - fast);
  out[46] = static_cast<float>(baseValue) / static_cast<float>(std::max(fast, 1));
}

// Same float summation order as the production walk (xgbRaw): start from the
// booster base score and add one leaf value per tree.
inline float xgbBase47Raw(const float* features) {
  float value = kXgbB47BaseScore;
  for (int tree = 0; tree < kXgbB47TreeCount; ++tree) {
    int32_t node = kXgbB47TreeRoots[tree];
    while (kXgbB47Nodes[node].left != -1) {
      const XgbB47TreeNode& current = kXgbB47Nodes[node];
      node = features[current.feature] < current.threshold ? current.left : current.right;
    }
    value += kXgbB47Nodes[node].threshold;
  }
  return value;
}

}  // namespace delayest
