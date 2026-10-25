#include "residue_estimator.h"
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
#include "embedded_residue.h"
#endif
#ifdef DELAY_ESTIMATE_PRECOMPUTED_TEMPLATES
#include "embedded_templates.h"
#endif

#include "xgb_residual.h"
#include "xgb_residual_base.h"
#include "xgb_residual_base47.h"
#include "xgb_residual_base47_fast.h"
#include "xgb_residual_bounds.h"
#include "router.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <sys/mman.h>
#include <unistd.h>

namespace delayest {
namespace {

int gcdInt(int a, int b) {
  while (b != 0) {
    const int t = a % b;
    a = b;
    b = t;
  }
  return a < 0 ? -a : a;
}

int lcmInt(int a, int b) { return a / gcdInt(a, b) * b; }

// Experiment 47: the experiment 46 pre-declared short-distance boundary.  Rows at
// or below it take the frozen XgbBase leaf; rows above it take the production Xgb
// model.  The boundary is frozen by the experiment 46 protocol and is not tuned
// on any new sample.
constexpr int kXgbBase24Distance = 24;

}  // namespace

void ResidueEstimator::buildPorts(const Architecture& arch, int residueMultiplier) {
  const int portCount = arch.portCount();
  zIndexOfPort_.assign(portCount, -1);
  for (int p = 0; p < portCount; ++p) {
    if (!arch.isNetSource(p)) continue;
    zIndexOfPort_[p] = static_cast<int>(zPorts_.size());
    zPorts_.push_back(p);
  }
  if (zPorts_.empty()) throw std::runtime_error("architecture exposes no Z* net sources");

  vx_.assign(zPorts_.size(), 0);
  vy_.assign(zPorts_.size(), 0);
  int maxX = 0, maxY = 0;
  for (size_t i = 0; i < zPorts_.size(); ++i) {
    const NetTemplate& net = arch.net(arch.netOfOutput(zPorts_[i]));
    vx_[i] = static_cast<int8_t>(net.dx);
    vy_[i] = static_cast<int8_t>(net.dy);
    maxX = std::max(maxX, std::abs(net.dx));
    maxY = std::max(maxY, std::abs(net.dy));
    if ((net.dx == 0) == (net.dy == 0)) throw std::runtime_error("Net template is not axis aligned");
  }
  minArcCost_ = kInf16;
  if (residueMultiplier < 1) throw std::runtime_error("residue multiplier must be >= 1");
  mx_ = maxX * residueMultiplier;
  my_ = maxY * residueMultiplier;
  if (mx_ <= 0 || my_ <= 0) throw std::runtime_error("degenerate Net spans");
  scale_ = lcmInt(mx_, my_);
  residueCount_ = mx_ * my_;

  // Sources: every Z* port, then every other port that drives an Arc.
  sourceOfPort_.assign(portCount, -1);
  for (size_t i = 0; i < zPorts_.size(); ++i) {
    sourceOfPort_[zPorts_[i]] = static_cast<int>(sourcePorts_.size());
    sourcePorts_.push_back(zPorts_[i]);
  }
  for (int p = 0; p < portCount; ++p) {
    if (arch.isNetSource(p) || arch.outgoingArcs(p).empty()) continue;
    sourceOfPort_[p] = static_cast<int>(sourcePorts_.size());
    sourcePorts_.push_back(p);
  }
  landingSourceOfZ_.resize(zPorts_.size());
  for (size_t p = 0; p < zPorts_.size(); ++p) {
    const int landing = arch.net(arch.netOfOutput(zPorts_[p])).to;
    landingSourceOfZ_[p] = sourceOfPort_[landing];
    if (landingSourceOfZ_[p] < static_cast<int>(zPorts_.size())) {
      throw std::runtime_error("Z* landing port cannot act as a non-Z source");
    }
  }
  // Targets: every Z* port, every interconnect input (Net landing) and every
  // port that an Arc can drive.
  targetOfPort_.assign(portCount, -1);
  for (int p = 0; p < portCount; ++p) {
    const bool isTarget = arch.isNetSource(p) || arch.isNetSink(p) || !arch.incomingArcs(p).empty();
    if (!isTarget) continue;
    targetOfPort_[p] = static_cast<int>(targetPorts_.size());
    targetPorts_.push_back(p);
  }
  // Hoist the logic-output terminal scan: each entry is a predecessor Z index
  // plus the actual Arc delay, computed once instead of per residue.
  terminalPreds_.assign(targetPorts_.size(), {});
  for (size_t t = 0; t < targetPorts_.size(); ++t) {
    const int port = targetPorts_[t];
    if (arch.isNetSource(port) || arch.isNetSink(port)) continue;
    for (const ArcTemplate& arc : arch.incomingArcs(port)) {
      const int netIndex = arch.netOfInput(arc.to);
      if (netIndex < 0) continue;
      terminalPreds_[t].push_back({zIndexOfPort_[arch.net(netIndex).from], arc.delay});
    }
  }
  iPredecessorOf_.assign(targetPorts_.size(), -1);
  for (size_t t = 0; t < targetPorts_.size(); ++t) {
    const int port = targetPorts_[t];
    if (!arch.isNetSink(port)) continue;
    iPredecessorOf_[t] = zIndexOfPort_[arch.net(arch.netOfInput(port)).from];
  }
  // Experiment 17 phase B: only Z* and logic targets own a table column.  Every
  // I* target is a Net landing whose value is derived from the Z* target that the
  // Net starts from, so it only needs that column plus a per-quadrant term.
  storedTargetOfTarget_.assign(targetPorts_.size(), -1);
  storedTargets_.clear();
  for (size_t t = 0; t < targetPorts_.size(); ++t) {
    if (arch.isNetSink(targetPorts_[t])) continue;
    storedTargetOfTarget_[t] = static_cast<int>(storedTargets_.size());
    storedTargets_.push_back(static_cast<int>(t));
  }
  storedTargetCount_ = static_cast<int>(storedTargets_.size());
  for (size_t t = 0; t < targetPorts_.size(); ++t) {
    if (!arch.isNetSink(targetPorts_[t])) continue;
    const int p = iPredecessorOf_[t];
    storedTargetOfTarget_[t] = storedTargetOfTarget_[targetOfPort_[zPorts_[p]]];
  }
  prevResidue_.assign(zPorts_.size() * residueCount_, 0);
  for (size_t p = 0; p < zPorts_.size(); ++p) {
    for (int residue = 0; residue < residueCount_; ++residue) {
      prevResidue_[p * residueCount_ + residue] =
          static_cast<uint16_t>(residueShift(residue, -vx_[p], -vy_[p]));
    }
  }
}

void ResidueEstimator::buildTranslationGraph(const Architecture& arch) {
  const size_t zCount = zPorts_.size();
  arcCost_.assign(zCount * zCount, kInf16);
  for (size_t p = 0; p < zCount; ++p) {
    const int iPort = arch.net(arch.netOfOutput(zPorts_[p])).to;
    for (const ArcTemplate& arc : arch.outgoingArcs(iPort)) {
      if (arc.delay < minArcCost_) minArcCost_ = arc.delay;
      const int q = zIndexOfPort_[arc.to];
      if (q < 0) continue;  // logic destination: handled as a terminal
      uint16_t& slot = arcCost_[p * zCount + q];
      if (arc.delay < slot) slot = static_cast<uint16_t>(arc.delay);
    }
  }
}

void ResidueEstimator::buildPotentials() {
  const size_t zCount = zPorts_.size();
  slopeA_.assign(kQuadrants, 0);
  slopeB_.assign(kQuadrants, 0);
  // Quadrant order: (E,N), (E,S), (W,N), (W,S).
  const int signX[kQuadrants] = {1, 1, -1, -1};
  const int signY[kQuadrants] = {1, -1, 1, -1};

  for (int q = 0; q < kQuadrants; ++q) {
    // Smallest published self-loop cost per unit displacement, scaled by S.
    int bestA = 0, bestB = 0;
    for (size_t p = 0; p < zCount; ++p) {
      const int selfLoop = arcCost_[p * zCount + p];
      if (selfLoop == kInf16) continue;
      if (vx_[p] * signX[q] > 0) {
        const int value = selfLoop * (scale_ / std::abs(vx_[p]));
        if (bestA == 0 || value < bestA) bestA = value;
      }
      if (vy_[p] * signY[q] > 0) {
        const int value = selfLoop * (scale_ / std::abs(vy_[p]));
        if (bestB == 0 || value < bestB) bestB = value;
      }
    }
    if (bestA == 0 || bestB == 0) {
      throw std::runtime_error("no positive self-loop for a residue slope");
    }
    slopeA_[q] = signX[q] * bestA;
    slopeB_[q] = signY[q] * bestB;
    // Bellman-Ford from an artificial zero-cost super source: with h all zero
    // the relaxation computes h[q] <= h[p] + w[p][q], which is exactly the
    // potential needed for nonnegative reduced costs.  A negative cycle would
    // make the construction invalid.
    std::vector<int32_t> h(zCount, 0);
    bool changed = true;
    size_t rounds = 0;
    while (changed) {
      changed = false;
      if (++rounds > zCount + 1) throw std::runtime_error("negative cycle in the translation graph");
      for (size_t p = 0; p < zCount; ++p) {
        for (size_t to = 0; to < zCount; ++to) {
          const uint16_t cost = arcCost_[p * zCount + to];
          if (cost == kInf16) continue;
          const int32_t weight = static_cast<int32_t>(scale_ * cost) - slopeA_[q] * vx_[p] - slopeB_[q] * vy_[p];
          const int64_t candidate = static_cast<int64_t>(h[p]) + weight;
          if (candidate < h[to]) {
            h[to] = static_cast<int32_t>(candidate);
            changed = true;
          }
        }
      }
    }
    potential_[q] = h;
    // Reduced costs must be nonnegative; verify instead of assuming.
    successors_[q].assign(zCount, {});
    int minReduced = kInfTable;
    for (size_t p = 0; p < zCount; ++p) {
      for (size_t to = 0; to < zCount; ++to) {
        const uint16_t cost = arcCost_[p * zCount + to];
        if (cost == kInf16) continue;
        const int32_t weight = static_cast<int32_t>(scale_ * cost) - slopeA_[q] * vx_[p] - slopeB_[q] * vy_[p];
        const int64_t reduced = static_cast<int64_t>(weight) + h[p] - h[to];
        if (reduced < 0) throw std::runtime_error("negative reweighted edge");
        // The successor list stores the reduced cost as uint16_t, so 65535 is the
        // hard limit of this table.  A larger residue multiplier raises scale_ and
        // can push a reduced cost past it (mult=5 does); wrapping silently would
        // corrupt the table, so the overflow is rejected here, before buildTables
        // allocates the table itself.
        if (reduced > 65535) {
          throw std::runtime_error("reduced edge cost " + std::to_string(reduced) +
                                   " exceeds the uint16 successor range (65535) at quadrant " +
                                   std::to_string(q) + ", Z port pair " +
                                   arch_->portName(zPorts_[p]) + " -> " + arch_->portName(zPorts_[to]));
        }
        if (reduced > maxReducedEdge_) maxReducedEdge_ = static_cast<int>(reduced);
        if (reduced < minReduced) minReduced = static_cast<int>(reduced);
        successors_[q][p].push_back({static_cast<int>(to), static_cast<uint16_t>(reduced)});
      }
    }
    if (q == 0) stats_.minReducedEdge = minReduced;
  }
}

// Dijkstra over the finite residue graph.  Reduced edges are nonnegative, so
// shifting all seeds by their minimum gives the radix queue monotone keys.
void ResidueEstimator::runResidueDijkstra(int quadrant, const std::vector<std::pair<int, int32_t>>& seeds,
                                          std::vector<int32_t>& dist) {
  const size_t stateCount = static_cast<size_t>(residueCount_) * zPorts_.size();
  dist.assign(stateCount, kInfTable);
  if (seeds.empty()) return;
  const int32_t base = std::min_element(seeds.begin(), seeds.end(),
      [](const auto& left, const auto& right) { return left.second < right.second; })->second;
  RadixFrontier queue;
  queue.clear();
  for (const auto& seed : seeds) {
    if (seed.second < dist[seed.first]) {
      dist[seed.first] = seed.second;
      queue.push(static_cast<uint32_t>(static_cast<int64_t>(seed.second) - base), seed.first);
    }
  }
  while (!queue.empty()) {
    const uint64_t entry = queue.top();
    const int32_t current = static_cast<int32_t>(static_cast<int64_t>(entry >> 32) + base);
    const int state = static_cast<int>(static_cast<uint32_t>(entry));
    if (dist[state] != current) continue;
    const int zIndex = state % static_cast<int>(zPorts_.size());
    const int residue = state / static_cast<int>(zPorts_.size());
    const int shifted = residueShift(residue, vx_[zIndex], vy_[zIndex]);
    for (const auto& edge : successors_[quadrant][zIndex]) {
      const int32_t next = current + edge.second;
      const int nextState = shifted * static_cast<int>(zPorts_.size()) + edge.first;
      if (next < dist[nextState]) {
        dist[nextState] = next;
        queue.push(static_cast<uint32_t>(static_cast<int64_t>(next) - base), nextState);
      }
    }
  }
}

void ResidueEstimator::fillTargets(int quadrant, int sourceIndex, const std::vector<int32_t>& dist) {
  const size_t zCount = zPorts_.size();
  const int a = slopeA_[quadrant];
  const int b = slopeB_[quadrant];
  const std::vector<int32_t>& h = potential_[quadrant];
  // Only stored targets own a column.  I* targets are derived in estimateBase.
  for (int column = 0; column < storedTargetCount_; ++column) {
    const int targetIndex = storedTargets_[column];
    const int port = targetPorts_[targetIndex];
    for (int residue = 0; residue < residueCount_; ++residue) {
      int64_t best = kInfTable;
      const int zIndex = zIndexOfPort_[port];
      if (zIndex >= 0) {
        // Z* target: land on the state itself.
        const int32_t d = dist[static_cast<size_t>(residue) * zCount + zIndex];
        if (d != kInfTable) best = static_cast<int64_t>(d) + h[zIndex];
      } else {
        // Logic output: minimum over the pre-aggregated incoming Arc list.
        for (const auto& pred : terminalPreds_[targetIndex]) {
          const int p = pred.first;
          const int previous = prevResidue_[static_cast<size_t>(p) * residueCount_ + residue];
          const int32_t d = dist[static_cast<size_t>(previous) * zCount + p];
          if (d == kInfTable) continue;
          const int64_t value =
              static_cast<int64_t>(d) + h[p] - a * vx_[p] - b * vy_[p] + static_cast<int64_t>(scale_) * pred.second;
          if (value < best) best = value;
        }
      }
      *tableSlot(quadrant, sourceIndex, column, residue) =
          best >= kInfTable ? kInfTable : static_cast<int32_t>(best);
    }
  }
  // A direct source Arc into a logic-output target is a zero-displacement path.
  const int sourcePort = sourcePorts_[sourceIndex];
  if (!arch_->isNetSource(sourcePort)) {
    for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
      const int targetIndex = targetOfPort_[arc.to];
      if (targetIndex < 0) continue;
      if (arch_->isNetSource(arc.to) || arch_->isNetSink(arc.to)) continue;  // covered above
      const int64_t value = static_cast<int64_t>(scale_) * arc.delay;
      int32_t& slot = *tableSlot(quadrant, sourceIndex, storedTargetOfTarget_[targetIndex], 0);
      if (slot == kInfTable || value < slot) slot = static_cast<int32_t>(value);
    }
  }
}

void ResidueEstimator::buildTables() {
  const size_t storedSize = static_cast<size_t>(kQuadrants) *
      (sourcePorts_.size() - zPorts_.size()) * storedTargetCount_ * residueCount_;
  table_.assign(storedSize, kInfTable);
#ifdef MADV_COLLAPSE
  // Best-effort physical-page coalescing for the densely used query table.
  // Older kernels may reject the hint; the vector and its values stay valid.
  const long pageSize = sysconf(_SC_PAGESIZE);
  if (pageSize > 0) {
    const uintptr_t address = reinterpret_cast<uintptr_t>(table_.data());
    const uintptr_t begin = (address + pageSize - 1) / pageSize * pageSize;
    const uintptr_t end = (address + storedSize * sizeof(int32_t)) / pageSize * pageSize;
    if (end > begin) {
      (void)madvise(reinterpret_cast<void*>(begin), end - begin, MADV_COLLAPSE);
    }
  }
#endif
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
  if (arch_->residueInputsMatchEmbedded() && mx_ == embedded_residue::kModulusX &&
      my_ == embedded_residue::kModulusY) {
    embedded_residue::restore(table_);
    return;
  }
#endif
  std::vector<int32_t> dist;
  std::vector<std::pair<int, int32_t>> seeds;
  // Non-Z* sources own stored rows; tableValue derives each Z* source from its
  // Net landing when read.
  for (int sourceIndex = 0; sourceIndex < static_cast<int>(sourcePorts_.size()); ++sourceIndex) {
    const int sourcePort = sourcePorts_[sourceIndex];
    if (arch_->isNetSource(sourcePort)) continue;
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      seeds.clear();
      for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
        const int zIndex = zIndexOfPort_[arc.to];
        if (zIndex < 0) continue;  // logic destination: terminal only
        const int32_t cost = static_cast<int32_t>(static_cast<int64_t>(scale_) * arc.delay -
                                                  potential_[quadrant][zIndex]);
        seeds.push_back({zIndex, cost});
      }
      runResidueDijkstra(quadrant, seeds, dist);
      fillTargets(quadrant, sourceIndex, dist);
      ++stats_.residueDijkstraRuns;
    }
  }
}

// A Z* source is one fixed transit away from the source at its own Net landing,
// so its whole table follows from the landing's table.  For every quadrant and
// every target
//
//   F(q, Z_p, t, r) = F(q, I_p, t, r - v_p) - (a_q*v_px + b_q*v_py)
//
// The reason is that the first edge of any Z_p path is the Net of p plus one Arc
// from I_p, and the I_p source seeds exactly those Arcs at residue zero, which
// shifts every reached state by v_p and lowers its value by a_q*v_px+b_q*v_py.
// Two zero-cost trivial paths bypass the shifted value, and both are added as
// candidates after the shifted slot has been tested for INF:
//   target Z_p at residue zero                     -> 0
//   target I_p at the displacement residue         -> -(a_q*v_px + b_q*v_py)
int32_t ResidueEstimator::tableValue(int quadrant, int sourceIndex, int column, int residue) const {
  if (sourceIndex >= static_cast<int>(zPorts_.size())) {
    return *tableSlot(quadrant, sourceIndex, column, residue);
  }
  const int zIndex = sourceIndex;  // buildPorts puts the Z* sources first.
  const int previous = prevResidue_[static_cast<size_t>(zIndex) * residueCount_ + residue];
  const int32_t shifted = *tableSlot(quadrant, landingSourceOfZ_[zIndex], column, previous);
  const int vpx = vx_[zIndex];
  const int vpy = vy_[zIndex];
  const int64_t transit = static_cast<int64_t>(slopeA_[quadrant]) * vpx +
                          static_cast<int64_t>(slopeB_[quadrant]) * vpy;
  int64_t best = shifted == kInfTable ? kInfTable : static_cast<int64_t>(shifted) - transit;
  if (targetPorts_[storedTargets_[column]] == sourcePorts_[sourceIndex] && residue == 0 && best > 0) {
    best = 0;
  }
  return best >= kInfTable ? kInfTable : static_cast<int32_t>(best);
}

void ResidueEstimator::buildBoundsTable(const Architecture& arch) {
  const auto startTime = std::chrono::steady_clock::now();
  const int portCount = arch.portCount();
  // Experiment 31 lower bound: any real path projected onto its port sequence is
  // a quotient walk whose Arc edges keep their published delay and whose Net
  // edges cost at most zero, so the projection is safe only when every real
  // Arc, Block cross and Line delay is non-negative.  Audit before Dijkstra and
  // fail through the existing init error path when the premise is broken.
  long long negatives = 0;
  for (int p = 0; p < portCount; ++p) {
    for (const ArcTemplate& arc : arch.outgoingArcs(p)) {
      if (arc.delay < 0) ++negatives;
    }
  }
  for (const Block& block : arch.blocks()) {
    if (block.crossDelay[0] < 0 || block.crossDelay[1] < 0) ++negatives;
  }
  for (int axis = 0; axis < 2; ++axis) {
    for (int delay : arch.lineDelays(static_cast<Axis>(axis))) {
      if (delay < 0) ++negatives;
    }
  }
  if (negatives > 0) {
    throw std::runtime_error("bounds table: " + std::to_string(negatives) +
                             " negative architecture delay(s) break the lower-bound premise");
  }

  // Quotient graph over all ports: Arc edges keep the published delay, Net edges
  // cost zero and ignore geometry.  Finite distances are bounded by
  // (portCount - 1) times the largest delay, far inside int32.
  std::vector<std::vector<std::pair<int, int>>> adjacency(portCount);
  for (int p = 0; p < portCount; ++p) {
    for (const ArcTemplate& arc : arch.outgoingArcs(p)) {
      adjacency[p].push_back({arc.to, arc.delay});
    }
    if (arch.isNetSource(p)) {
      adjacency[p].push_back({arch.net(arch.netOfOutput(p)).to, 0});
    }
  }
  quotientPortCount_ = portCount;
  quotientDistance_.assign(static_cast<size_t>(portCount) * portCount, kInfTable);
  std::vector<int> row(portCount);
  for (int source = 0; source < portCount; ++source) {
    std::fill(row.begin(), row.end(), kInfTable);
    std::priority_queue<std::pair<int, int>, std::vector<std::pair<int, int>>,
                        std::greater<std::pair<int, int>>>
        queue;
    row[source] = 0;
    queue.push({0, source});
    while (!queue.empty()) {
      const auto top = queue.top();
      queue.pop();
      if (top.first != row[top.second]) continue;
      for (const auto& edge : adjacency[top.second]) {
        const int candidate = top.first + edge.second;
        if (candidate < row[edge.first]) {
          row[edge.first] = candidate;
          queue.push({candidate, edge.first});
        }
      }
    }
    for (int target = 0; target < portCount; ++target) {
      quotientDistance_[static_cast<size_t>(source) * portCount + target] = row[target];
    }
  }
  stats_.boundsTableBytes = quotientDistance_.size() * sizeof(int32_t);
  stats_.boundsBuildSeconds =
      std::chrono::duration<double>(std::chrono::steady_clock::now() - startTime).count();
}

int ResidueEstimator::quotientDistance(int from, int to) const {
  if (quotientDistance_.empty() || from < 0 || to < 0 || from >= quotientPortCount_ ||
      to >= quotientPortCount_) {
    return -1;
  }
  const int32_t value = quotientDistance_[static_cast<size_t>(from) * quotientPortCount_ + to];
  return value >= kInfTable ? -1 : value;
}

int ResidueEstimator::lowerBound(int sx, int sy, int sourcePort, int tx, int ty,
                                 int targetPort) const {
  const int distance = quotientDistance(sourcePort, targetPort);
  if (distance < 0) return -1;
  // Same prefix convention as estimateBase; the explicit range check keeps the
  // prefix indexing safe for a direct caller that has no valid pair yet.
  if (sx < 0 || sx >= Architecture::kWidth || tx < 0 || tx >= Architecture::kWidth ||
      sy < 0 || sy >= Architecture::kHeight || ty < 0 || ty >= Architecture::kHeight) {
    return -1;
  }
  int value = distance;
  value += arch_->lineDelayCrossing(Axis::Vertical, sx, tx);
  value += arch_->lineDelayCrossing(Axis::Horizontal, sy, ty);
  return value;
}

void ResidueEstimator::init(const Architecture& arch, const Options& options) {
  const auto startTime = std::chrono::steady_clock::now();
  arch_ = &arch;
  boundsMode_ = options.boundsMode;
  templateSelection_ = options.templateSelection;
  templateBias_ = options.templateBias;
  if (templateSelection_) {
#ifndef DELAY_ESTIMATE_PRECOMPUTED_TEMPLATES
    throw std::runtime_error("template selection requires embedded template fields");
#else
    if (options.residueMultiplier != 2 || options.endpointMode != EndpointMode::SourceShort ||
        options.endpointShortDistance != 150 || options.pdbFloor ||
        options.residualMode != ResidualMode::XgbBase47D8 ||
        options.boundsMode != BoundsMode::Off || templateBias_ != -3) {
      throw std::runtime_error("template selection requires the fixed production configuration");
    }
#endif
  }
  // Experiment 31: build (and audit) the quotient table before any residue
  // structure, so a negative-delay architecture fails the bounds premise before
  // the translation graph / Dijkstra work starts.  Upper1 alone needs no table.
  // Experiment 58's XgbBase47D8 is deliberately absent: its model reads no L
  // feature, so neither the table nor lowerBound() is ever needed for it.
  if (boundsMode_ == BoundsMode::Lower || boundsMode_ == BoundsMode::Both ||
      options.residualMode == ResidualMode::XgbBounds ||
      options.residualMode == ResidualMode::XgbBase ||
      options.residualMode == ResidualMode::XgbBase24) {
    buildBoundsTable(arch);
  }
  buildPorts(arch, options.residueMultiplier);
  buildTranslationGraph(arch);
  buildPotentials();
  buildTables();
  stats_.tableBytes = table_.size() * sizeof(int32_t);
#ifdef DELAY_ESTIMATE_PRECOMPUTED_TEMPLATES
  if (templateSelection_) {
    embedded_templates::restore(arch, zIndexOfPort_, templateValues_, templateIndexOfPort_);
    stats_.templateBytes = templateValues_.size() * sizeof(uint16_t);
    templateSourcePossible_.assign(static_cast<size_t>(arch.portCount()), 0);
    for (int port = 0; port < arch.portCount(); ++port) {
      if (templateIndexOfPort_[port] >= 0) {
        templateSourcePossible_[port] = 1;
        continue;
      }
      for (const ArcTemplate& arc : arch.outgoingArcs(port)) {
        if (templateIndexOfPort_[arc.to] >= 0) {
          templateSourcePossible_[port] = 1;
          break;
        }
      }
    }
  }
#endif
  endpointMode_ = options.endpointMode;
  endpointShortDistance_ = options.endpointShortDistance;
  pdbFloor_ = options.pdbFloor;
  residualMode_ = options.residualMode;
  if (pdbFloor_) {
    pdb_.init(arch);
  }
  pdbTargetState_.assign(arch.portCount(), 0);
  if (endpointMode_ != EndpointMode::Off) {
    // Scratch capacity from the real maximum Arc fan-in/out, so one request
    // never reallocates its endpoint lists.
    size_t maxOut = 0;
    size_t maxIn = 0;
    for (int port = 0; port < arch.portCount(); ++port) {
      maxOut = std::max(maxOut, arch.outgoingArcs(port).size());
      maxIn = std::max(maxIn, arch.incomingArcs(port).size());
    }
    exits_.reserve(maxOut);
    entrances_.reserve(maxIn);
  }
  if (options.cacheBytes > 0) {
    cache_.init(options.cacheBytes / sizeof(BoundedQueryCache::Entry));
  } else {
    cache_.init(0);
  }
  stats_.cacheEntries = cache_.capacity();
  stats_.buildSeconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - startTime).count();
}

// Experiment 51 stage 1: one computation, two views.  quadrantDiagnostics() owns the
// whole pure residue lookup, so the probe and the production answer cannot diverge;
// estimateBase() extracts the production fields from it and changes nothing else.
ResidueEstimator::QuadrantDiagnostics ResidueEstimator::quadrantDiagnostics(
    int sx, int sy, int sourcePort, int tx, int ty, int targetPort) {
  QuadrantDiagnostics out;
  if (sx == tx && sy == ty && sourcePort == targetPort) {
    out.samePin = true;
    out.value = 0;
    return out;
  }
  if (!arch_->exists(sx, sy) || !arch_->exists(tx, ty)) {
    out.unreachable = true;
    return out;
  }
  // Both cells exist, so sx/sy/tx/ty are inside the Line prefix arrays.  The Line
  // charges are recorded before the role check because the probe reports them for
  // role-unreachable rows as well; the production answer never uses them there.
  out.lineVertical = arch_->lineDelayCrossing(Axis::Vertical, sx, tx);
  out.lineHorizontal = arch_->lineDelayCrossing(Axis::Horizontal, sy, ty);
  const int sourceIndex = sourceOfPort_[sourcePort];
  const int targetIndex = targetOfPort_[targetPort];
  if (sourceIndex < 0 || targetIndex < 0) {
    out.unreachable = true;
    return out;
  }
  const int dx = tx - sx;
  const int dy = ty - sy;
  const int residue = residueOf(dx, dy);
  out.dx = dx;
  out.dy = dy;
  out.residue = residue;
  // Derivation of a stored I* target and its displacement fold, both outside the
  // quadrant loop: for an I* target the shifted residue and (dx - v_px, dy - v_py)
  // reproduce a*dx + b*dy + F(s, Z_p, r - v_p) - (a*v_px + b*v_py) in every
  // quadrant.  True endpoint coordinates and Line charges are untouched.
  out.derivedTarget = arch_->isNetSink(targetPort);
  const int storedColumn = storedTargetOfTarget_[targetIndex];
  int lookupDx = dx;
  int lookupDy = dy;
  int lookupResidue = residue;
  if (out.derivedTarget) {
    const int p = iPredecessorOf_[targetIndex];
    lookupDx = dx - vx_[p];
    lookupDy = dy - vy_[p];
    lookupResidue = prevResidue_[static_cast<size_t>(p) * residueCount_ + residue];
  }
  out.lookupDx = lookupDx;
  out.lookupDy = lookupDy;
  out.lookupResidue = lookupResidue;
  int64_t best = 0;
  int64_t second = 0;
  int64_t worst = 0;
  bool haveQuadrant = false;
  bool haveSecond = false;
  const bool zSource = sourceIndex < static_cast<int>(zPorts_.size());
  const int rowSource = zSource ? landingSourceOfZ_[sourceIndex] : sourceIndex;
  const int rowResidue = zSource
      ? prevResidue_[static_cast<size_t>(sourceIndex) * residueCount_ + lookupResidue]
      : lookupResidue;
  const int32_t* row = table_.data() + tableOffset(0, rowSource, storedColumn, rowResidue);
  const bool zeroPath = targetPorts_[storedTargets_[storedColumn]] == sourcePorts_[sourceIndex] &&
                        lookupResidue == 0;
  for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
    int32_t value = row[quadrant];
    if (zSource) {
      const int64_t transit = static_cast<int64_t>(slopeA_[quadrant]) * vx_[sourceIndex] +
                              static_cast<int64_t>(slopeB_[quadrant]) * vy_[sourceIndex];
      int64_t shifted = value == kInfTable ? kInfTable : static_cast<int64_t>(value) - transit;
      if (zeroPath && shifted > 0) shifted = 0;
      value = shifted >= kInfTable ? kInfTable : static_cast<int32_t>(shifted);
    }
    out.slot[quadrant] = value;
    if (value == kInfTable) continue;
    const int64_t candidate = static_cast<int64_t>(slopeA_[quadrant]) * lookupDx +
                              static_cast<int64_t>(slopeB_[quadrant]) * lookupDy + value;
    out.candidate[quadrant] = candidate;
    ++out.finiteQuadrants;
    if (!haveQuadrant) {
      best = candidate;
      worst = candidate;
      out.dominant = quadrant;
      haveQuadrant = true;
      continue;
    }
    if (candidate > best) {
      second = best;
      best = candidate;
      out.dominant = quadrant;
      haveSecond = true;
    } else if (!haveSecond || candidate > second) {
      // A tie keeps the first argmax as dominant and still counts the repeated
      // value as the second largest.
      second = candidate;
      haveSecond = true;
    }
    if (candidate < worst) worst = candidate;
  }
  out.best = haveQuadrant ? best : -1;
  out.secondBest = haveSecond ? second : -1;
  out.worst = haveQuadrant ? worst : -1;
  int delay = 0;
  if (!haveQuadrant) {
    // No quadrant reached the target residue: fall back to a straight-line
    // estimate so a valid endpoint pair never reports a negative delay.
    out.fallback = true;
    const int hops = (std::abs(dx) + mx_ - 1) / mx_ + (std::abs(dy) + my_ - 1) / my_;
    delay = hops * std::max(1, minArcCost_);
  } else {
    delay = static_cast<int>(std::llround(static_cast<double>(best) / scale_));
  }
  // Exactly mandatory Line Gap crossings between the two endpoints.
  delay += out.lineVertical;
  delay += out.lineHorizontal;
  out.unclampedDelay = delay;
  if (delay < 0) {
    delay = 0;
    out.clamped = true;
  }
  out.value = delay;
  return out;
}

ResidueEstimator::BaseAnswer ResidueEstimator::estimateBase(int sx, int sy, int sourcePort, int tx,
                                                            int ty, int targetPort) {
  const QuadrantDiagnostics diagnostics =
      quadrantDiagnostics(sx, sy, sourcePort, tx, ty, targetPort);
  BaseAnswer out;
  out.value = diagnostics.value;
  out.unreachable = diagnostics.unreachable;
  out.fallback = diagnostics.fallback;
  return out;
}

// Experiment 6 source exit: the real first Net (Z source) or Arc + real first
// Net (other sources), with the mandatory Line charge of that Net included.
void ResidueEstimator::collectExits(int sx, int sy, int sourcePort) {
  exits_.clear();
  if (arch_->isNetSource(sourcePort)) {
    const int net = arch_->netOfOutput(sourcePort);
    const ResolvedEdge edge = arch_->resolveNet(sx, sy, net);
    if (edge.valid) exits_.push_back({edge.x, edge.y, arch_->net(net).to, edge.delay});
    return;
  }
  for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
    const int net = arch_->netOfOutput(arc.to);
    if (net < 0) continue;  // Arc into a logic port is not a Net transition.
    const ResolvedEdge edge = arch_->resolveNet(sx, sy, net);
    if (!edge.valid) continue;
    exits_.push_back({edge.x, edge.y, arch_->net(net).to, arc.delay + edge.delay});
  }
}

// Experiment 6 target entrance: for an I* target the Net lands directly on the
// pin; for Z* and logic output targets the last step is an Arc from an I port
// in the same SRB whose own Net predecessor is resolved by the inverse helper.
void ResidueEstimator::collectEntrances(int tx, int ty, int targetPort) {
  entrances_.clear();
  if (arch_->isNetSink(targetPort)) {
    const int net = arch_->netOfInput(targetPort);
    const ResolvedEdge predecessor = arch_->resolveNetPredecessor(tx, ty, net);
    if (predecessor.valid) {
      entrances_.push_back({predecessor.x, predecessor.y, arch_->net(net).from, predecessor.delay});
    }
    return;
  }
  for (const ArcTemplate& arc : arch_->incomingArcs(targetPort)) {
    const int sourcePort = arc.to;  // loader stores the Arc source here
    const int net = arch_->netOfInput(sourcePort);
    if (net < 0) continue;  // an Arc from a non-landing port is not reachable
    const ResolvedEdge predecessor = arch_->resolveNetPredecessor(tx, ty, net);
    if (!predecessor.valid) continue;
    entrances_.push_back(
        {predecessor.x, predecessor.y, arch_->net(net).from, predecessor.delay + arc.delay});
  }
}

void ResidueEstimator::dedupMinEndpoints(std::vector<Endpoint>& items) {
  std::sort(items.begin(), items.end(), [](const Endpoint& a, const Endpoint& b) {
    if (a.x != b.x) return a.x < b.x;
    if (a.y != b.y) return a.y < b.y;
    if (a.port != b.port) return a.port < b.port;
    return a.cost < b.cost;
  });
  size_t write = 0;
  for (size_t i = 0; i < items.size(); ++i) {
    if (write > 0 && items[i].x == items[write - 1].x && items[i].y == items[write - 1].y &&
        items[i].port == items[write - 1].port) {
      continue;  // sorted by cost, the first entry is the cheapest
    }
    items[write++] = items[i];
  }
  items.resize(write);
  std::sort(items.begin(), items.end(),
            [](const Endpoint& a, const Endpoint& b) { return a.cost < b.cost; });
}

void ResidueEstimator::mergeMin(int value, int& best) {
  if (value < 0) return;
  if (best < 0 || value < best) best = value;
}

// Complete legal paths inside the source's first Net (or a same-pin / same-cell
// Arc), so a one-Net route is never forced through a second Net.
void ResidueEstimator::mergeShortCandidates(int sx, int sy, int sourcePort, int tx, int ty,
                                            int targetPort, int& best) {
  if (sx == tx && sy == ty && sourcePort == targetPort) mergeMin(0, best);
  if (sx == tx && sy == ty) {
    for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
      if (arc.to == targetPort) mergeMin(arc.delay, best);
    }
  }
  for (const Endpoint& exit : exits_) {
    if (exit.x != tx || exit.y != ty) continue;
    if (exit.port == targetPort) mergeMin(exit.cost, best);
    for (const ArcTemplate& arc : arch_->outgoingArcs(exit.port)) {
      if (arc.to == targetPort) mergeMin(exit.cost + arc.delay, best);
    }
  }
}

int ResidueEstimator::estimateEndpoint(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                                       EndpointMode mode, int* shortUpper) {
  collectExits(sx, sy, sourcePort);
  dedupMinEndpoints(exits_);
  int best = -1;
  mergeShortCandidates(sx, sy, sourcePort, tx, ty, targetPort, best);
  // Experiment 31: hand the <=1-Net real-path minimum back before the residue
  // leaves below modify `best`; the Source early return is already covered.
  if (shortUpper != nullptr) *shortUpper = best;

  if (mode == EndpointMode::Source) {
    // An I* target owns no stored column: estimateBase derives its value from the
    // nominal Net predecessor column, which does not prove that the physical target
    // tile can be reached by a real last Net.  The Target and Both paths validate that
    // through collectEntrances (resolveNetPredecessor); the Source path never did, so
    // it could return a finite value for a target that no Net can land on.  One check
    // per query is enough: the same-pin and direct Arc candidates merged above stay
    // valid and are returned unchanged, and the middle leaves keep their own rules.
    if (arch_->isNetSink(targetPort) &&
        !arch_->resolveNetPredecessor(tx, ty, arch_->netOfInput(targetPort)).valid) {
      return best;
    }
    for (const Endpoint& exit : exits_) {
      if (best >= 0 && exit.cost >= best) break;  // later prefixes are not smaller
      const BaseAnswer middle = estimateBase(exit.x, exit.y, exit.port, tx, ty, targetPort);
      if (middle.value < 0) continue;
      mergeMin(exit.cost + middle.value, best);
    }
    return best;
  }

  collectEntrances(tx, ty, targetPort);
  dedupMinEndpoints(entrances_);

  if (mode == EndpointMode::Target) {
    for (const Endpoint& entrance : entrances_) {
      if (best >= 0 && entrance.cost >= best) break;
      const BaseAnswer middle = estimateBase(sx, sy, sourcePort, entrance.x, entrance.y, entrance.port);
      if (middle.value < 0) continue;
      mergeMin(middle.value + entrance.cost, best);
    }
    return best;
  }

  // Both: one residue query per exit x entrance pair.  The middle estimate is
  // never negative, so prefix + suffix is a valid prune.
  for (const Endpoint& exit : exits_) {
    if (best >= 0 && exit.cost >= best) break;
    for (const Endpoint& entrance : entrances_) {
      if (best >= 0 && exit.cost + entrance.cost >= best) break;
      const BaseAnswer middle =
          estimateBase(exit.x, exit.y, exit.port, entrance.x, entrance.y, entrance.port);
      if (middle.value < 0) continue;
      mergeMin(exit.cost + middle.value + entrance.cost, best);
    }
  }
  return best;
}

int ResidueEstimator::estimate(int sx, int sy, int sourcePort, int tx, int ty, int targetPort) {
  ++stats_.queries;
  const BaseAnswer base = estimateBase(sx, sy, sourcePort, tx, ty, targetPort);
  if (base.unreachable) {
    // Same-pin already returned 0 inside estimateBase; every other
    // invalid/unreachable endpoint class must not start endpoint enumeration
    // (a same-cell Arc on a Block hole would otherwise be accepted), and the
    // final answer is -1.
    ++stats_.unreachable;
    return -1;
  }
  if (base.fallback) ++stats_.fallback;
  if (endpointMode_ == EndpointMode::Off) {
    int answer = pdbFloor_ ? applyPdbFloor(sx, sy, sourcePort, tx, ty, targetPort, base.value) : base.value;
    if (residualMode_ != ResidualMode::Off) {
      answer = applyResidual(sx, sy, sourcePort, tx, ty, targetPort, answer, base.value);
    }
    return applyTemplateSelection(
        sx, sy, sourcePort, tx, ty, targetPort,
        applyBounds(sx, sy, sourcePort, tx, ty, targetPort, answer, -1));
  }
  // The endpoint minimum replaces the table answer; the middle leaves above go
  // through estimateBase, so they neither touch the memo nor recurse.  The
  // SourceShort policy only chooses which existing path runs for this request:
  // nothing is cached or recorded before the choice, so a selected request is
  // byte-identical to Both and an unselected one to Source.
  EndpointMode effective = endpointMode_;
  if (endpointMode_ == EndpointMode::SourceShort) {
    const int manhattan = std::abs(tx - sx) + std::abs(ty - sy);
    if (manhattan <= endpointShortDistance_) {
      effective = EndpointMode::Both;
      ++stats_.shortBoth;
    } else {
      effective = EndpointMode::Source;
      ++stats_.shortSource;
    }
  }
  int shortUpper = -1;
  const int endpoint = estimateEndpoint(sx, sy, sourcePort, tx, ty, targetPort, effective, &shortUpper);
  if (endpoint < 0) {
    // A valid base pair can still have an empty endpoint candidate set (e.g.
    // an invalid boundary first Net); the final answer is -1 and the counter
    // must follow the final answer, not the base.
    ++stats_.unreachable;
    return endpoint;
  }
  int answer = pdbFloor_ ? applyPdbFloor(sx, sy, sourcePort, tx, ty, targetPort, endpoint) : endpoint;
  if (residualMode_ != ResidualMode::Off) {
    answer = applyResidual(sx, sy, sourcePort, tx, ty, targetPort, answer, base.value);
  }
  return applyTemplateSelection(
      sx, sy, sourcePort, tx, ty, targetPort,
      applyBounds(sx, sy, sourcePort, tx, ty, targetPort, answer, shortUpper));
}

// Frozen experiment 19A model.  The long variant keeps fast at or below the fixed
// boundary; fast <= 0 results are never modified.  The experiment 32 variant halves
// the raw correction on very short rows; the halving happens in double so the
// integer result matches the Python candidate bit for bit.
// Experiment 47: XgbBase24 selects the frozen XgbBase leaf below the pre-declared
// distance boundary and the production Xgb model above it.  Both models run in
// this same estimator, so they share the residue table, endpoint enumeration and
// request cache; only the residual dispatch differs.
int ResidueEstimator::applyResidual(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                                    int value, int baseValue) const {
  if (value <= 0) return value;
  const int manhattan = std::abs(tx - sx) + std::abs(ty - sy);
  if (residualMode_ == ResidualMode::Long && manhattan <= kResidualShortDistance) {
    return value;
  }
  // Experiment 58: the 47-slot base-feature model.  Everything it needs is the
  // pre-endpoint answer already computed by estimate(); unlike XgbBase it reads
  // no L slot, so the quotient lower bound is neither computed nor required here.
  if (residualMode_ == ResidualMode::XgbBase47D8) {
    if (baseValue >= 0) {
      float base47Features[kXgbB47FeatureTotal];
      xgbBase47Features(*arch_, sx, sy, sourcePort, tx, ty, targetPort, value, baseValue,
                        base47Features);
      return xgbRound(value, static_cast<double>(xgbBase47FastRaw(base47Features)));
    }
  }
  // Experiment 41: base + L features.  Both the pre-endpoint answer and the
  // quotient bound must be available; otherwise fall through to the base model.
  // Experiment 47 reuses exactly this leaf for the short rows of the hybrid.
  const bool wantsBase = residualMode_ == ResidualMode::XgbBase ||
                         (residualMode_ == ResidualMode::XgbBase24 &&
                          manhattan <= kXgbBase24Distance);
  if (wantsBase) {
    const int lower = lowerBound(sx, sy, sourcePort, tx, ty, targetPort);
    if (lower >= 0 && baseValue >= 0) {
      float baseFeatures[kXgbB0FeatureTotal];
      xgbBaseFeatures(*arch_, sx, sy, sourcePort, tx, ty, targetPort, value, baseValue, lower,
                      baseFeatures);
      return xgbRound(value, static_cast<double>(xgbBaseRaw(baseFeatures)));
    }
  }
  // Experiment 40: the L-feature model.  L comes from the audited quotient table
  // built at init; an unavailable bound falls back to the base model rather than
  // inventing a value.
  if (residualMode_ == ResidualMode::XgbBounds) {
    const int lower = lowerBound(sx, sy, sourcePort, tx, ty, targetPort);
    if (lower >= 0) {
      float boundsFeatures[kXgbBoundsFeatureTotal];
      xgbBoundsFeatures(*arch_, sx, sy, sourcePort, tx, ty, targetPort, value, lower, boundsFeatures);
      return xgbRound(value, static_cast<double>(xgbBoundsRaw(boundsFeatures)));
    }
  }
  float features[44];
  xgbFeatures(*arch_, sx, sy, sourcePort, tx, ty, targetPort, value, features);
  double raw = static_cast<double>(xgbRaw(features));
  if (residualMode_ == ResidualMode::XgbShrink24 && manhattan <= kResidualShrinkDistance) {
    raw *= 0.5;
  }
  return xgbRound(value, raw);
}

// Pattern-database floor: the bound is audited admissible, so raising the answer
// to it can only move an underestimate towards the true distance.  An unknown
// bound leaves the answer untouched; an infinite abstract state is reported as
// unsupported and is never clamped to zero.
int ResidueEstimator::applyPdbFloor(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                                    int value) {
  if (!pdbFloor_ || targetPort < 0 || targetPort >= static_cast<int>(pdbTargetState_.size())) {
    if (pdbFloor_) ++stats_.pdbFloorUnsupported;
    return value;
  }
  if (pdbTargetState_[targetPort] == 0) {
    try {
      pdb_.prepareTarget(targetPort);
      pdbTargetState_[targetPort] = 2;
      ++stats_.pdbTargetsPrepared;
      stats_.pdbPrepareSeconds = pdb_.stats().prepareSeconds;
    } catch (const std::exception&) {
      pdbTargetState_[targetPort] = 1;
      ++stats_.pdbFloorUnsupported;
      return value;
    }
  } else if (pdbTargetState_[targetPort] == 1) {
    ++stats_.pdbFloorUnsupported;
    return value;
  }
  long long bound = 0;
  if (!pdb_.lowerBound(sx, sy, sourcePort, tx, ty, targetPort, bound)) {
    ++stats_.pdbFloorUnsupported;
    return value;
  }
  if (bound > value) {
    ++stats_.pdbFloorApplied;
    return static_cast<int>(bound);
  }
  return value;
}

// Experiment 31: clamp a finished positive answer into the real-path interval.
// `upper1` is the caller's captured <=1-Net minimum (-1 when unknown).  Zero and
// negative answers are preserved, an unknown bound never truncates, and an
// inconsistent interval (L > U1, impossible for a real short path) is counted
// and left untouched rather than trusted.
int ResidueEstimator::applyBounds(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                                  int value, int upper1) {
  if (boundsMode_ == BoundsMode::Off || value <= 0) return value;
  const bool wantsLower = boundsMode_ == BoundsMode::Lower || boundsMode_ == BoundsMode::Both;
  const bool wantsUpper = boundsMode_ == BoundsMode::Upper1 || boundsMode_ == BoundsMode::Both;
  const int lower = wantsLower ? lowerBound(sx, sy, sourcePort, tx, ty, targetPort) : -1;
  const int upper = wantsUpper ? upper1 : -1;
  if (wantsLower && lower < 0) ++stats_.boundsUnknownLower;
  if (wantsUpper && upper < 0) ++stats_.boundsUnknownUpper;
  if (lower >= 0 && upper >= 0 && lower > upper) {
    ++stats_.boundsInconsistent;
    return value;
  }
  const int before = value;
  if (lower >= 0 && value < lower) value = lower;
  if (upper >= 0 && value > upper) value = upper;
  if (value != before) ++stats_.boundsApplied;
  return value;
}

int ResidueEstimator::applyTemplateSelection(int sx, int sy, int sourcePort, int tx, int ty,
                                             int targetPort, int value) {
  if (!templateSelection_) return value;
  ++stats_.templateQueries;
  if (sourcePort < 0 || sourcePort >= static_cast<int>(templateSourcePossible_.size()) ||
      !templateSourcePossible_[sourcePort]) {
    return value;
  }
  if (value < 0) return value;
  int base = value + templateBias_;
  if (base < 0) base = 0;
  if (base == 0) return value;

  auto addMinimum = [](std::vector<Endpoint>& endpoints, int x, int y, int port, int cost) {
    for (Endpoint& endpoint : endpoints) {
      if (endpoint.x == x && endpoint.y == y && endpoint.port == port) {
        endpoint.cost = std::min(endpoint.cost, cost);
        return;
      }
    }
    endpoints.push_back({x, y, port, cost});
  };

  exits_.clear();
  if (arch_->isNetSource(sourcePort)) {
    addMinimum(exits_, sx, sy, sourcePort, 0);
  } else {
    for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
      if (arch_->isNetSource(arc.to)) addMinimum(exits_, sx, sy, arc.to, arc.delay);
    }
  }
  entrances_.clear();
  if (arch_->isNetSource(targetPort)) {
    addMinimum(entrances_, tx, ty, targetPort, 0);
  } else if (arch_->isNetSink(targetPort)) {
    const int net = arch_->netOfInput(targetPort);
    const ResolvedEdge predecessor = arch_->resolveNetPredecessor(tx, ty, net);
    if (predecessor.valid) {
      addMinimum(entrances_, predecessor.x, predecessor.y, arch_->net(net).from,
                 predecessor.delay);
    }
  } else {
    for (const ArcTemplate& arc : arch_->incomingArcs(targetPort)) {
      const int net = arch_->netOfInput(arc.to);
      if (net < 0) continue;
      const ResolvedEdge predecessor = arch_->resolveNetPredecessor(tx, ty, net);
      if (predecessor.valid) {
        addMinimum(entrances_, predecessor.x, predecessor.y, arch_->net(net).from,
                   predecessor.delay + arc.delay);
      }
    }
  }

  int direct = std::numeric_limits<int>::max();
  if (sx == tx && sy == ty && sourcePort == targetPort) direct = 0;
  if (sx == tx && sy == ty) {
    for (const ArcTemplate& arc : arch_->outgoingArcs(sourcePort)) {
      if (arc.to == targetPort) direct = std::min(direct, arc.delay);
    }
  }

  int raw = std::numeric_limits<int>::max();
  bool hit = false;
  for (const Endpoint& start : exits_) {
    const int field = templateIndexOfPort_[start.port];
    if (field < 0) continue;
    const int net = arch_->netOfOutput(start.port);
    const bool validNet = arch_->resolveNet(start.x, start.y, net).valid;
    for (const Endpoint& target : entrances_) {
      if (!validNet && (start.x != target.x || start.y != target.y ||
                        start.port != target.port)) {
        continue;
      }
      const int ax = 60 + target.x - start.x;
      const int ay = 284 + target.y - start.y;
      if (!arch_->exists(ax, ay)) continue;
      const int targetIndex = zIndexOfPort_[target.port];
      if (targetIndex < 0) continue;
      const uint16_t distance = templateValues_[
          static_cast<size_t>(field) * Architecture::kCellCount * 160 +
          static_cast<size_t>(targetIndex) * Architecture::kCellCount +
          static_cast<size_t>(ay) * Architecture::kWidth + ax];
      if (distance == 0xFFFF) continue;
      const int before = arch_->lineDelayCrossing(Axis::Vertical, 60, ax) +
                         arch_->lineDelayCrossing(Axis::Horizontal, 284, ay);
      const int after = arch_->lineDelayCrossing(Axis::Vertical, start.x, target.x) +
                        arch_->lineDelayCrossing(Axis::Horizontal, start.y, target.y);
      const int core = static_cast<int>(distance) - before + after;
      if (core < 0) continue;
      raw = std::min(raw, start.cost + core + target.cost);
      hit = true;
    }
  }
  if (!hit) return value;
  raw = std::min(raw, direct);
  if (raw < 0 || raw >= base || base - raw > base / 20) return value;

  ++stats_.templateSelections;
  return raw - templateBias_;
}

int ResidueEstimator::estimateText(std::string_view from, std::string_view to) {
  int sx, sy, sp, tx, ty, tp;
  if (!arch_->parsePin(from, sx, sy, sp) || !arch_->parsePin(to, tx, ty, tp)) {
    ++stats_.invalid;
    return -1;
  }
  const int64_t key = (static_cast<int64_t>(arch_->pinId(sx, sy, sp)) << 26) |
                      static_cast<int64_t>(arch_->pinId(tx, ty, tp));
  int cached = 0;
  if (cache_.lookup(static_cast<uint64_t>(key), cached)) {
    ++stats_.cacheHits;
    return cached;
  }
  const int answer = estimate(sx, sy, sp, tx, ty, tp);
  cache_.insert(static_cast<uint64_t>(key), answer);
  return answer;
}

}  // namespace delayest
