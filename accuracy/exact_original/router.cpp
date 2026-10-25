#include "router.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace delayest {
namespace {

inline uint64_t mix64(uint64_t x) {
  x += 0x9E3779B97F4A7C15ull;
  x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull;
  x = (x ^ (x >> 27)) * 0x94D049BB133111EBull;
  return x ^ (x >> 31);
}

}  // namespace

void Router::init(const Architecture& arch, const Options& options) {
  arch_ = &arch;
  const int portCount = arch.portCount();
  zIndexOfPort_.assign(portCount, -1);
  zPortOfIndex_.clear();
  for (int p = 0; p < portCount; ++p) {
    if (arch.isNetSource(p)) {
      zIndexOfPort_[p] = static_cast<int>(zPortOfIndex_.size());
      zPortOfIndex_.push_back(p);
    }
  }
  zPortCount_ = static_cast<int>(zPortOfIndex_.size());
  if (zPortCount_ == 0) throw std::runtime_error("architecture exposes no Z* net sources");
  useHeuristic_ = options.useSpanHeuristic;
  useRadixHeap_ = options.useRadixHeap;
  boundProvider_ = options.boundProvider;

  buildArcTemplates();
  buildSpanHeuristic();
  buildTransitions();

  // Search scratch must exist before any landmark Dijkstra runs.
  dist_.assign(static_cast<size_t>(Architecture::kCellCount) * zPortCount_, kInf32);
  touched_.reserve(1 << 16);
  heap_.reserve(1 << 16);

  landmarkCount_ = std::max(0, std::min<int>(options.landmarkCount, kMaxLandmarks));
  if (landmarkCount_ > 0) buildLandmarks();

  if (options.enableQueryCache && options.queryCacheEntries > 0) {
    cache_.init(options.queryCacheEntries);
  } else {
    cache_.init(0);
  }
  {
    const double landmarkSeconds = stats_.landmarkBuildSeconds;
    stats_ = Stats();
    stats_.landmarkBuildSeconds = landmarkSeconds;
  }
}

// All 8192 published Arcs go Input -> Output and no Arc leaves an Output port,
// so an in-SRB Arc chain is exactly one Arc.  Only direct templates are kept.
void Router::buildArcTemplates() {
  const int portCount = arch_->portCount();
  arcTemplates_.assign(portCount, {});
  arcCost_.assign(static_cast<size_t>(portCount) * portCount, kInf16);
  for (int source = 0; source < portCount; ++source) {
    for (const ArcTemplate& arc : arch_->outgoingArcs(source)) {
      const size_t index = static_cast<size_t>(source) * portCount + arc.to;
      if (arc.delay < arcCost_[index]) arcCost_[index] = static_cast<uint16_t>(arc.delay);
    }
    for (int q = 0; q < portCount; ++q) {
      const uint16_t delay = arcCost_[static_cast<size_t>(source) * portCount + q];
      if (delay != kInf16) arcTemplates_[source].push_back({q, delay});
    }
  }
}

// Lower bound on the Arc+Net cost of moving k columns/rows.
//
// A hop uses exactly one Net template and displaces the state by at most that
// template's displacement capacity: its nominal |span| plus every coordinate it
// may skip over crossable Block cells (Blocks are only crossable horizontally,
// so a horizontal Net can gain at most the widest row band of crossable Block
// cells and a vertical Net gains nothing).  Its cost is at least the cheapest
// Arc out of the Net's destination input port.  The DP below is the cheapest
// multiset of templates whose capacities cover k, which is therefore a valid
// lower bound for every real route; being a min over a superset, it can only
// underestimate.  All edge costs are positive, so the bound is consistent and
// A* with it returns exact shortest distances.
void Router::buildSpanHeuristic() {
  int horizontalBonus = 0;
  for (int y = 0; y < Architecture::kHeight; ++y) {
    int crossableInRow = 0;
    for (int x = 0; x < Architecture::kWidth; ++x) {
      const int block = arch_->blockAt(x, y);
      if (block >= 0 && arch_->blocks()[block].crossable[0]) ++crossableInRow;
    }
    horizontalBonus = std::max(horizontalBonus, crossableInRow);
  }

  struct Step {
    uint32_t capacity = 0;
    uint32_t cost = kInf32;
  };
  std::vector<Step> xSteps, ySteps;
  auto addStep = [](std::vector<Step>& steps, uint32_t capacity, uint32_t cost) {
    if (capacity == 0 || cost == kInf32) return;
    for (Step& step : steps) {
      if (step.capacity == capacity) {
        step.cost = std::min(step.cost, cost);
        return;
      }
    }
    steps.push_back({capacity, cost});
  };
  for (int netIndex = 0; netIndex < arch_->netCount(); ++netIndex) {
    const NetTemplate& net = arch_->net(netIndex);
    const int span = net.dx != 0 ? std::abs(net.dx) : std::abs(net.dy);
    if (span == 0) continue;
    uint32_t cheapestArc = kInf32;
    for (const ArcTemplate& arc : arch_->outgoingArcs(net.to)) {
      cheapestArc = std::min<uint32_t>(cheapestArc, static_cast<uint32_t>(arc.delay));
    }
    const uint32_t capacity = static_cast<uint32_t>(span) + (net.dx != 0 ? static_cast<uint32_t>(horizontalBonus) : 0u);
    addStep(net.dx != 0 ? xSteps : ySteps, capacity, cheapestArc);
  }

  auto buildAxis = [](int length, const std::vector<Step>& steps, std::vector<uint32_t>& out) {
    out.assign(length, kInf32);
    out[0] = 0;
    for (int k = 1; k < length; ++k) {
      uint32_t best = kInf32;
      for (const Step& step : steps) {
        const int rest = k > static_cast<int>(step.capacity) ? k - static_cast<int>(step.capacity) : 0;
        if (out[rest] == kInf32 || step.cost == kInf32) continue;
        best = std::min<uint32_t>(best, out[rest] + step.cost);
      }
      out[k] = best;
    }
  };
  std::vector<uint32_t> alongX, alongY;
  buildAxis(Architecture::kWidth, xSteps, alongX);
  buildAxis(Architecture::kHeight, ySteps, alongY);
  spanBound_.assign(Architecture::kWidth + Architecture::kHeight, 0);
  for (int k = 0; k < Architecture::kWidth; ++k) spanBound_[k] = alongX[k];
  for (int k = 0; k < Architecture::kHeight; ++k) spanBound_[Architecture::kWidth + k] = alongY[k];
}

// Exact forward distances from every landmark state.  The landmark set is a
// spread of cells across the array; the lane is the first Z* port, which exists
// in every SRB.  Fields are stored interleaved so one 16-byte load serves the
// whole bound.
void Router::buildLandmarks() {
  const auto startTime = std::chrono::steady_clock::now();
  static const int kXs[] = {20, 45, 70, 95, 115};
  static const int kYs[] = {60, 180, 300, 420, 530};
  std::vector<std::pair<int, int>> cells;
  for (int x : kXs) {
    for (int y : kYs) {
      if (arch_->exists(x, y)) cells.push_back({x, y});
    }
  }
  // Greedy farthest-point selection keeps landmarks spread regardless of how
  // many are requested; the order is deterministic.
  {
    std::vector<std::pair<int, int>> ordered;
    ordered.reserve(cells.size());
    std::vector<bool> used(cells.size(), false);
    size_t first = 0;
    for (size_t i = 1; i < cells.size(); ++i) {
      if (cells[i].first + cells[i].second > cells[first].first + cells[first].second) first = i;
    }
    used[first] = true;
    ordered.push_back(cells[first]);
    while (ordered.size() < cells.size()) {
      size_t best = 0;
      long bestScore = -1;
      for (size_t i = 0; i < cells.size(); ++i) {
        if (used[i]) continue;
        long nearest = 1 << 30;
        for (const auto& chosen : ordered) {
          const long dx = cells[i].first - chosen.first;
          const long dy = cells[i].second - chosen.second;
          nearest = std::min(nearest, dx * dx + dy * dy);
        }
        if (nearest > bestScore) {
          bestScore = nearest;
          best = i;
        }
      }
      used[best] = true;
      ordered.push_back(cells[best]);
    }
    cells.swap(ordered);
  }
  const int lanePort = zPortOfIndex_[0];
  const size_t stateCount = static_cast<size_t>(Architecture::kCellCount) * zPortCount_;
  // The stride is fixed to the number of landmarks that will actually be built;
  // changing it later would misalign every stored field.
  const int landmarks = std::min<int>(landmarkCount_, static_cast<int>(cells.size()));
  if (landmarks <= 0) {
    landmarkCount_ = 0;
    return;
  }
  landmarkTable_.assign(stateCount * landmarks, kInf16);
  std::vector<uint16_t> field(stateCount, kInf16);
  for (int built = 0; built < landmarks; ++built) {
    std::fill(field.begin(), field.end(), kInf16);
    distanceField(cells[built].first, cells[built].second, lanePort, field);
    for (size_t s = 0; s < stateCount; ++s) landmarkTable_[s * landmarks + built] = field[s];
  }
  landmarkCount_ = landmarks;
  landmarkCellMin_.assign(static_cast<size_t>(Architecture::kCellCount) * landmarkCount_, kInf16);
  for (int cell = 0; cell < Architecture::kCellCount; ++cell) {
    for (int l = 0; l < landmarkCount_; ++l) {
      uint16_t best = kInf16;
      for (int z = 0; z < zPortCount_; ++z) {
        const uint16_t d = landmarkTable_[(static_cast<size_t>(cell) * zPortCount_ + z) * landmarkCount_ + l];
        if (d < best) best = d;
      }
      landmarkCellMin_[static_cast<size_t>(cell) * landmarkCount_ + l] = best;
    }
  }
  stats_.landmarkBuildSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - startTime).count();
}

// Plain Dijkstra over the implicit graph, used only for landmark fields.
void Router::distanceField(int x0, int y0, int zPort, std::vector<uint16_t>& out) {
  touched_.clear();
  heap_.clear();
  const auto relax = [&](int x, int y, int zNext, uint32_t g) {
    const int state = stateId(x, y, zIndexOfPort_[zNext]);
    if (g < dist_[state]) {
      if (dist_[state] == kInf32) touched_.push_back(state);
      dist_[state] = g;
      heap_.push_back((static_cast<uint64_t>(g) << 32) | static_cast<uint64_t>(state));
      std::push_heap(heap_.begin(), heap_.end(), std::greater<uint64_t>());
    }
  };
  relax(x0, y0, zPort, 0);
  while (!heap_.empty()) {
    std::pop_heap(heap_.begin(), heap_.end(), std::greater<uint64_t>());
    const uint64_t key = heap_.back();
    heap_.pop_back();
    const uint32_t g = static_cast<uint32_t>(key >> 32);
    const int state = static_cast<int>(key & 0xFFFFFFFFu);
    if (g != dist_[state]) continue;  // stale entry
    const int cell = state / zPortCount_;
    const int zIndex = state - cell * zPortCount_;
    const int x = cell % Architecture::kWidth;
    const int y = cell / Architecture::kWidth;
    const int netIndex = arch_->netOfOutput(zPortOfIndex_[zIndex]);
    const ResolvedEdge edge = arch_->resolveNet(x, y, netIndex);
    if (!edge.valid) continue;
    const uint32_t base = g + static_cast<uint32_t>(edge.delay);
    for (const auto& [destPort, cost] : successorsOfZ_[zIndex]) {
      relax(edge.x, edge.y, destPort, base + static_cast<uint32_t>(cost));
    }
  }
  for (int state : touched_) {
    if (dist_[state] <= 0xFFFEu) {
      out[state] = static_cast<uint16_t>(dist_[state]);
    } else {
      // Finite but outside the stored range: count it, the entry stays infinite.
      ++stats_.clippedFieldStates;
    }
    dist_[state] = kInf32;
  }
}

// Valid lower bounds on d(landmark, target pin).  The predecessor of a landing
// is the real resolver predecessor, so crossable Block skips are followed and
// the gap delay and the terminal Arc are charged for every candidate.  Taking the
// minimum over the complete predecessor set is what keeps the bound valid.  A
// candidate whose real Net edge does not exist is not part of the reachable
// predecessor set at all, so it contributes no term.
void Router::computeTargetBounds(int tx, int ty, int targetPort) {
  for (int l = 0; l < kMaxLandmarks; ++l) queryTargetBound_[l] = kInf16;
  if (landmarkCount_ == 0) return;
  if (arch_->isNetSource(targetPort)) {
    const int state = stateId(tx, ty, zIndexOfPort_[targetPort]);
    for (int l = 0; l < landmarkCount_; ++l)
      queryTargetBound_[l] = landmarkTable_[static_cast<size_t>(state) * landmarkCount_ + l];
    return;
  }
  auto raise = [&](int cell, int zPort, int extra, int l) {
    const uint16_t base =
        landmarkTable_[static_cast<size_t>(stateId(cell % Architecture::kWidth, cell / Architecture::kWidth,
                                                  zIndexOfPort_[zPort])) *
                           landmarkCount_ +
                       l];
    if (base == kInf16) return;
    const int value = static_cast<int>(base) + extra;
    const uint16_t candidate = static_cast<uint16_t>(std::min(value, static_cast<int>(kInf16)));
    if (candidate < queryTargetBound_[l]) queryTargetBound_[l] = candidate;
  };
  if (arch_->isNetSink(targetPort)) {
    const int netIndex = arch_->netOfInput(targetPort);
    const ResolvedEdge origin = arch_->resolveNetPredecessor(tx, ty, netIndex);
    if (!origin.valid) return;
    const int cell = origin.y * Architecture::kWidth + origin.x;
    const int zPort = arch_->net(netIndex).from;
    for (int l = 0; l < landmarkCount_; ++l) raise(cell, zPort, origin.delay, l);
    return;
  }
  // Logic output: the last step is an Arc from an interconnect input port that is
  // itself the real landing of a Net hop.
  for (const ArcTemplate& arc : arch_->incomingArcs(targetPort)) {
    const int netIndex = arch_->netOfInput(arc.to);  // loader stores the Arc source here
    if (netIndex < 0) continue;
    const ResolvedEdge origin = arch_->resolveNetPredecessor(tx, ty, netIndex);
    if (!origin.valid) continue;
    const int cell = origin.y * Architecture::kWidth + origin.x;
    const int zPort = arch_->net(netIndex).from;
    for (int l = 0; l < landmarkCount_; ++l) raise(cell, zPort, origin.delay + arc.delay, l);
  }
}
void Router::buildTransitions() {
  netDestOfZ_.assign(zPortCount_, -1);
  successorsOfZ_.assign(zPortCount_, {});
  for (int z = 0; z < zPortCount_; ++z) {
    const int port = zPortOfIndex_[z];
    const int netIndex = arch_->netOfOutput(port);
    if (netIndex < 0) throw std::runtime_error("Z* port without Net template");
    const NetTemplate& net = arch_->net(netIndex);
    netDestOfZ_[z] = net.to;
    for (const auto& [dest, cost] : arcTemplates_[net.to]) {
      if (arch_->isNetSource(dest)) successorsOfZ_[z].push_back({dest, cost});
    }
  }
}

int Router::queryText(std::string_view from, std::string_view to) {
  int sx, sy, sp, tx, ty, tp;
  if (!arch_->parsePin(from, sx, sy, sp) || !arch_->parsePin(to, tx, ty, tp)) {
    ++stats_.unreachable;
    return kUnreachable;
  }
  return query(sx, sy, sp, tx, ty, tp);
}

int Router::query(int sx, int sy, int sourcePort, int tx, int ty, int targetPort) {
  ++stats_.queries;
  if (sx == tx && sy == ty && sourcePort == targetPort) return 0;
  if (!arch_->exists(sx, sy) || !arch_->exists(tx, ty)) {
    ++stats_.unreachable;
    return kUnreachable;
  }
  uint64_t cacheKey = 0;
  if (cache_.capacity() != 0) {
    cacheKey = (static_cast<uint64_t>(arch_->pinId(sx, sy, sourcePort)) << 26) |
               static_cast<uint64_t>(arch_->pinId(tx, ty, targetPort));
    int cached = 0;
    if (cache_.lookup(cacheKey, cached)) {
      ++stats_.cacheHits;
      if (cached == kUnreachable) ++stats_.unreachable;
      return cached;
    }
  }
  const int answer = search(sx, sy, sourcePort, tx, ty, targetPort);
  if (answer == kUnreachable) ++stats_.unreachable;
  if (cache_.capacity() != 0) cache_.insert(cacheKey, answer);
  return answer;
}

int Router::search(int sx, int sy, int sourcePort, int tx, int ty, int targetPort) {
  ++stats_.exactSearches;
  queryTargetPort_ = targetPort;
  computeTargetBounds(tx, ty, targetPort);
  // Credit the span bound for the final Net hop when the target is an I* port.
  // Any path to an I* pin ends with a Net landing there, so the span charge for
  // that hop can be credited back, which restores admissibility by reducing the
  // bound.  O(outdegree) per query
  // keeps the change local; an empty arc set means no credit is possible.
  terminalCredit_ = 0;
  if (arch_->isNetSink(targetPort)) {
    uint32_t cheapest = kInf32;
    for (const ArcTemplate& arc : arch_->outgoingArcs(targetPort)) {
      cheapest = std::min<uint32_t>(cheapest, static_cast<uint32_t>(arc.delay));
    }
    terminalCredit_ = cheapest == kInf32 ? 0u : cheapest;
  }
  const bool targetIsZ = arch_->isNetSource(targetPort);
  const int goalState = targetIsZ ? stateId(tx, ty, zIndexOfPort_[targetPort]) : -1;
  uint32_t best = kInf32;
#ifdef EDA_EXP107_DIAG
  std::vector<std::pair<int, uint32_t>> expandedF;
#endif
  touched_.clear();
  heap_.clear();
#ifdef EDA_EXP107_HIGH_G
  tieHeap_.clear();
#endif
  radix_.clear();

  // The frontier is either the binary heap (`heap_`) or the monotone radix heap;
  // both pop the minimum f, so the search logic below is shared.
  auto frontierPush = [&](uint32_t key, int state) {
    if (useRadixHeap_) {
      radix_.push(key, state);
      ++stats_.radixPushes;
    } else {
#ifdef EDA_EXP107_HIGH_G
      tieHeap_.emplace_back(key, kInf32 - dist_[state], state);
      std::push_heap(tieHeap_.begin(), tieHeap_.end(), std::greater<>());
#else
      heap_.push_back((static_cast<uint64_t>(key) << 32) | static_cast<uint64_t>(state));
      std::push_heap(heap_.begin(), heap_.end(), std::greater<uint64_t>());
#endif
    }
  };
#ifdef EDA_EXP107_HIGH_G
  auto frontierEmpty = [&]() { return useRadixHeap_ ? radix_.empty() : tieHeap_.empty(); };
#else
  auto frontierEmpty = [&]() { return useRadixHeap_ ? radix_.empty() : heap_.empty(); };
#endif
  auto frontierTop = [&]() -> uint64_t {
    // The radix heap removes the minimum in top(); the binary heap does not.
    if (useRadixHeap_) return radix_.top();
#ifdef EDA_EXP107_HIGH_G
    return (static_cast<uint64_t>(std::get<0>(tieHeap_.front())) << 32) |
           static_cast<uint32_t>(std::get<2>(tieHeap_.front()));
#else
    return heap_.front();
#endif
  };
  auto frontierPop = [&]() {
    if (useRadixHeap_) return;
#ifdef EDA_EXP107_HIGH_G
    std::pop_heap(tieHeap_.begin(), tieHeap_.end(), std::greater<>());
    tieHeap_.pop_back();
#else
    std::pop_heap(heap_.begin(), heap_.end(), std::greater<uint64_t>());
    heap_.pop_back();
#endif
  };

  auto relax = [&](int x, int y, int zPort, uint32_t g) {
    if (g >= best) return;
    const int state = stateId(x, y, zIndexOfPort_[zPort]);
    if (g < dist_[state]) {
      if (dist_[state] == kInf32) touched_.push_back(state);
      dist_[state] = g;
      frontierPush(g + heuristic(state, x, y, tx, ty), state);
    }
  };

  // Source seeding.
  if (arch_->isNetSource(sourcePort)) {
    relax(sx, sy, sourcePort, 0);
  } else {
    for (const auto& [dest, cost] : arcTemplates_[sourcePort]) {
      if (arch_->isNetSource(dest)) {
        relax(sx, sy, dest, static_cast<uint32_t>(cost));
      } else if (dest == targetPort && sx == tx && sy == ty) {
        best = std::min<uint32_t>(best, static_cast<uint32_t>(cost));
      }
    }
  }

  if (!frontierEmpty()) {
    uint32_t initial = kInf32;
    if (useRadixHeap_) {
      initial = radix_.minKey();
    } else {
#ifdef EDA_EXP107_HIGH_G
      for (const auto& key : tieHeap_) initial = std::min<uint32_t>(initial, std::get<0>(key));
#else
      for (uint64_t key : heap_) initial = std::min<uint32_t>(initial, static_cast<uint32_t>(key >> 32));
#endif
    }
    stats_.initialBoundSum += initial;
  }
  while (!frontierEmpty()) {
    const uint64_t key = frontierTop();
    frontierPop();
    const uint32_t f = static_cast<uint32_t>(key >> 32);
    const int state = static_cast<int>(key & 0xFFFFFFFFu);
    if (f >= best) break;
    const uint32_t g = dist_[state];
    const int cell = state / zPortCount_;
    const int zIndex = state - cell * zPortCount_;
    const int x = cell % Architecture::kWidth;
    const int y = cell / Architecture::kWidth;
    if (f != g + heuristic(state, x, y, tx, ty)) continue;  // stale entry
    if (state == goalState) {
      best = g;
      break;
    }
    const int zPort = zPortOfIndex_[zIndex];
    const int netIndex = arch_->netOfOutput(zPort);
    const ResolvedEdge edge = arch_->resolveNet(x, y, netIndex);
    if (!edge.valid) continue;
    const uint32_t base = g + static_cast<uint32_t>(edge.delay);
    if (base >= best) continue;
    ++stats_.expandedStates;
#ifdef EDA_EXP107_DIAG
    expandedF.emplace_back(state, f);
#endif
    const int inputPort = netDestOfZ_[zIndex];
    if (!targetIsZ) {
      // Target reached by an Arc at this SRB (logic output), or by the Net
      // transition itself when the requested pin is an interconnect input.
      if (inputPort == targetPort && edge.x == tx && edge.y == ty) {
        if (base < best) best = base;
      }
      const uint16_t terminalCost = arcCost_[static_cast<size_t>(inputPort) * arch_->portCount() + targetPort];
      if (terminalCost != kInf16 && edge.x == tx && edge.y == ty) {
        const uint32_t candidate = base + terminalCost;
        if (candidate < best) best = candidate;
      }
    }
    for (const auto& [destPort, cost] : successorsOfZ_[zIndex]) {
      ++stats_.relaxedEdges;
      const uint32_t candidate = base + static_cast<uint32_t>(cost);
      if (candidate >= best) continue;
      relax(edge.x, edge.y, destPort, candidate);
    }
  }

#ifdef EDA_EXP107_DIAG
  for (const auto& [state, f] : expandedF) {
    (void)state;
    stats_.expandedStrictF += f < best;
    stats_.expandedEqualF += f == best;
  }
  std::sort(expandedF.begin(), expandedF.end());
  for (size_t i = 0; i < expandedF.size(); ++i) {
    if (expandedF[i].second < best && (i == 0 || expandedF[i].first != expandedF[i - 1].first)) {
      ++stats_.expandedStrictFUnique;
    }
  }
#endif
  for (int state : touched_) dist_[state] = kInf32;
  if (best != kInf32) stats_.answerSum += best;
  return best == kInf32 ? kUnreachable : static_cast<int>(best);
}

}  // namespace delayest
