// Experiment 41: candidate residual features with the pre-endpoint base answer.
//
// The 50 feature slots are the 44 production slots plus
//   [44] base                 (pure residue answer before endpoint refinement)
//   [45] base - fast
//   [46] base / max(fast, 1)
//   [47] L                    (experiment 31 lower bound)
//   [48] fast - L
//   [49] L / max(fast, 1)
// The tree data lives in the generated kXgbBase* header.  Nothing here reads exact
// values or golden; the caller passes the base answer and the L computed by
// lowerBound().
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "architecture.h"
#include "xgb_residual.h"
#include "xgb_residual_base_model.h"

namespace delayest {

static constexpr int kXgbB0FeatureTotal = 50;

inline void xgbBaseFeatures(const Architecture& arch, int sx, int sy, int sourcePort, int tx,
                            int ty, int targetPort, int fast, int baseValue, int lower, float* out) {
  xgbFeatures(arch, sx, sy, sourcePort, tx, ty, targetPort, fast, out);
  out[44] = static_cast<float>(baseValue);
  out[45] = static_cast<float>(baseValue - fast);
  out[46] = static_cast<float>(baseValue) / static_cast<float>(std::max(fast, 1));
  out[47] = static_cast<float>(lower);
  out[48] = static_cast<float>(fast - lower);
  out[49] = static_cast<float>(lower) / static_cast<float>(std::max(fast, 1));
}

// Same float summation order as the production walk.
inline float xgbBaseRaw(const float* features) {
  float value = kXgbB0BaseScore;
  for (int tree = 0; tree < kXgbB0TreeCount; ++tree) {
    int32_t node = kXgbB0TreeRoots[tree];
    while (kXgbB0Nodes[node].left != -1) {
      const XgbB0TreeNode& current = kXgbB0Nodes[node];
      node = features[current.feature] < current.threshold ? current.left : current.right;
    }
    value += kXgbB0Nodes[node].threshold;
  }
  return value;
}

}  // namespace delayest
