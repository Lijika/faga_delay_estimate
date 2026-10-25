// Experiment 19C: inference for the frozen experiment 19A residual model.
//
// The trees and thresholds live in the generated header; this file computes the
// query-visible features in the exact schema order the Python model used and
// walks the trees.  Tag semantics are copied from tests/query_profile.cpp,
// including target_land_block, which is a nominal predecessor label.
#pragma once

#include <cmath>
#include <cstdint>
#include <vector>

#include "architecture.h"
#include "xgb_residual_model.h"

namespace delayest {

// Conservative short-distance rule of experiment 19B, fixed before evaluation.
static constexpr int kResidualShortDistance = 100;
// Experiment 32 candidate: halve the correction at or below this Manhattan distance.
static constexpr int kResidualShrinkDistance = 24;
static constexpr int kXgbFeatureTotal = 44;

// Static per port metadata, built once per architecture.
struct XgbPortInfo {
  float classOneHot[4] = {0, 0, 0, 0};
  float netDx = 0.0f;
  float netDy = 0.0f;
  float lane = -1.0f;
};

inline const std::vector<XgbPortInfo>& xgbPortTable(const Architecture& arch) {
  static const Architecture* owner = nullptr;
  static std::vector<XgbPortInfo> table;
  if (owner != &arch) {
    table.assign(arch.portCount(), XgbPortInfo{});
    const char* classes = "ZISA";
    for (int port = 0; port < arch.portCount(); ++port) {
      XgbPortInfo& info = table[port];
      const std::string& name = arch.portName(port);
      const char klass = name.empty() ? '?' : name[0];
      for (int i = 0; i < 4; ++i) info.classOneHot[i] = klass == classes[i] ? 1.0f : 0.0f;
      const int netIndex = arch.isNetSource(port) ? arch.netOfOutput(port) : arch.netOfInput(port);
      if (netIndex >= 0) {
        info.netDx = static_cast<float>(arch.net(netIndex).dx);
        info.netDy = static_cast<float>(arch.net(netIndex).dy);
      }
      const size_t open = name.rfind('[');
      if (open != std::string::npos && !name.empty() && name.back() == ']') {
        int lane = 0;
        bool ok = true;
        for (size_t i = open + 1; i + 1 < name.size(); ++i) {
          if (name[i] < '0' || name[i] > '9') ok = false;
          else lane = lane * 10 + (name[i] - '0');
        }
        info.lane = ok ? static_cast<float>(lane) : -1.0f;
      }
    }
    owner = &arch;
  }
  return table;
}

// True when the published Net of zPort can land on (x,y) with the nominal offset,
// the same nominal test query_profile used for the target_land_block tag.
inline bool xgbNominalLands(const Architecture& arch, int x, int y, int zPort) {
  const NetTemplate& net = arch.net(arch.netOfOutput(zPort));
  const int px = x - net.dx;
  const int py = y - net.dy;
  if (px < 0 || px >= Architecture::kWidth || py < 0 || py >= Architecture::kHeight) return false;
  const ResolvedEdge edge = arch.resolveNet(px, py, arch.netOfOutput(zPort));
  return edge.valid && edge.x == x && edge.y == y;
}

inline bool xgbLandingBlocked(const Architecture& arch, int x, int y, int port) {
  if (arch.isNetSource(port)) return !xgbNominalLands(arch, x, y, port);
  if (arch.isNetSink(port)) {
    const int zPort = arch.net(arch.netOfInput(port)).from;
    return !xgbNominalLands(arch, x, y, zPort);
  }
  for (const ArcTemplate& arc : arch.incomingArcs(port)) {
    const int netIndex = arch.netOfInput(arc.to);
    if (netIndex < 0) continue;
    if (xgbNominalLands(arch, x, y, arch.net(netIndex).from)) return false;
  }
  return true;
}

// Only the tag bits the trees read are computed; the launch diagnosis of
// query_profile is not needed by the frozen model.
inline int xgbUsedTags(const Architecture& arch, int sx, int sy, int sp, int tx, int ty, int tp) {
  int tags = 0;
  if (sx == tx && sy == ty && sp == tp) tags |= 1 << 0;
  for (const Block& block : arch.blocks()) {
    if (block.crossable[0]) {
      const bool bandY = sy >= block.lower && sy <= block.upper && ty >= block.lower && ty <= block.upper;
      const bool straddleX = (sx < block.left && tx > block.right) || (tx < block.left && sx > block.right);
      if (bandY && straddleX) tags |= 1 << 2;
    }
    if (!block.crossable[1]) {
      const bool bandX = sx >= block.left && sx <= block.right && tx >= block.left && tx <= block.right;
      const bool straddleY = (sy < block.lower && ty > block.upper) || (ty < block.lower && sy > block.upper);
      if (bandX && straddleY) tags |= 1 << 3;
    }
  }
  // target_land_block keeps the nominal predecessor semantics of the labels.
  if (xgbLandingBlocked(arch, tx, ty, tp)) tags |= 1 << 5;
  return tags;
}

// Fills only the 33 feature slots the trees read; the rest stay zero.
inline void xgbFeatures(const Architecture& arch, int sx, int sy, int sp, int tx, int ty, int tp, int fast,
                        float* out) {
  const int dx = tx - sx;
  const int dy = ty - sy;
  const int tags = xgbUsedTags(arch, sx, sy, sp, tx, ty, tp);
  std::fill(out, out + kXgbFeatureTotal, 0.0f);
  out[0] = static_cast<float>(fast);
  out[1] = static_cast<float>(dx);
  out[2] = static_cast<float>(dy);
  out[3] = static_cast<float>(std::abs(dx));
  out[4] = static_cast<float>(std::abs(dy));
  out[5] = static_cast<float>(std::abs(dx) + std::abs(dy));
  out[6] = static_cast<float>(((dx % 20) + 20) % 20);
  out[7] = static_cast<float>(((dy % 24) + 24) % 24);
  out[8] = static_cast<float>(arch.lineDelayCrossing(Axis::Vertical, sx, tx));
  out[9] = static_cast<float>(arch.lineDelayCrossing(Axis::Horizontal, sy, ty));
  out[10] = static_cast<float>(sx);
  out[11] = static_cast<float>(sy);
  out[12] = static_cast<float>(tx);
  out[13] = static_cast<float>(ty);
  out[14] = static_cast<float>(std::min(sx, Architecture::kWidth - 1 - sx));
  out[15] = static_cast<float>(std::min(sy, Architecture::kHeight - 1 - sy));
  out[16] = static_cast<float>(std::min(tx, Architecture::kWidth - 1 - tx));
  out[17] = static_cast<float>(std::min(ty, Architecture::kHeight - 1 - ty));
  out[18] = (tags & (1 << 0)) ? 1.0f : 0.0f;  // same pin
  out[20] = (tags & (1 << 2)) ? 1.0f : 0.0f;  // crossable horizontal block
  out[21] = (tags & (1 << 3)) ? 1.0f : 0.0f;  // non crossable vertical block
  out[23] = (tags & (1 << 5)) ? 1.0f : 0.0f;  // nominal target block landing
  const std::vector<XgbPortInfo>& table = xgbPortTable(arch);
  const XgbPortInfo& one = table[sp];
  const XgbPortInfo& two = table[tp];
  for (int i = 0; i < 4; ++i) {
    out[28 + i] = one.classOneHot[i];
    out[32 + i] = two.classOneHot[i];
  }
  out[36] = static_cast<float>(sp);
  out[37] = static_cast<float>(tp);
  out[38] = one.netDx;
  out[39] = one.netDy;
  out[40] = two.netDx;
  out[41] = two.netDy;
  out[42] = one.lane;
  out[43] = two.lane;
}

// Shared rounding: half up, clamped at zero.  fast <= 0 stays untouched.  The
// residual is a double so the experiment 32 halving is exact.
inline int xgbRound(int fast, double raw) {
  if (fast <= 0) return fast;
  const int corrected = static_cast<int>(std::floor(static_cast<double>(fast) + raw + 0.5));
  return corrected > 0 ? corrected : 0;
}

// Sums the tree outputs in float order, exactly like the booster's transform.
inline float xgbRaw(const float* features) {
  float value = kXgbBaseScore;
  for (int tree = 0; tree < kXgbTreeCount; ++tree) {
    int32_t node = kXgbTreeRoots[tree];
    while (kXgbNodes[node].left != -1) {
      const XgbTreeNode& current = kXgbNodes[node];
      node = features[current.feature] < current.threshold ? current.left : current.right;
    }
    value += kXgbNodes[node].threshold;
  }
  return value;
}

}  // namespace delayest
