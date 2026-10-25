// Full-graph shared pattern database with a provable lower bound.
//
// The abstraction keeps every published port (496) and the displacement residue
// modulo the largest horizontal and vertical Net spans (10 and 12), so the
// abstract graph has 120 residues times 496 ports states.  Every real edge of the
// architecture maps to one abstract edge: an Arc has zero displacement, a merged
// real Net hop carries its actual displacement and its block charge (Line charges
// stay outside the graph and are added to the query, as in the linear bound).
//
// Potentials h come from one Bellman-Ford pass per quadrant on the full port
// graph with an all-zero super source; the slopes are derived directly from the
// architecture (cheapest self-loop per unit displacement), not from any table.
// Reduced costs rc = S*cost - a*dx - b*dy + h[u] - h[v] are audited to be
// non-negative, which makes a reverse Dijkstra from (0,0,target) well defined.
//
// For a concrete path, displacement telescopes to a*dx + b*dy, and the reduced
// costs telescope to
//
//   sum rc = S*pathCost - a*dx - b*dy + h[s] - h[t]
//
// so S*d >= a*dx + b*dy + dq[(-dx mod Mx, -dy mod My, s)] + h[t] - h[s], where dq
// is the reverse Dijkstra table of quadrant q.  Taking ceil and the maximum over
// the four quadrants keeps a valid lower bound, and the mandatory Line crossings
// are added afterwards.  The pattern database argument is Lemma 1 of Culberson
// and Schaeffer, Pattern Databases (1998), section 3.
#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "architecture.h"

namespace delayest {

class PatternDatabase {
 public:
  static constexpr int kQuadrants = 4;
  static constexpr int32_t kInf32 = std::numeric_limits<int32_t>::max();

  struct Stats {
    long long validHops = 0;
    long long invalidHops = 0;
    long long hopTypes = 0;
    long long arcEdges = 0;
    long long reducedChecks = 0;
    long long negativeReduced = 0;
    long long minReduced = 0;
    int bellmanRounds[kQuadrants] = {0, 0, 0, 0};
    long long abstractStates = 0;
    long long tableBytesPerTarget = 0;
    long long preparedTargets = 0;
    long long targetFiniteStates = 0;
    long long targetZFiniteStates = 0;
    double initSeconds = 0.0;
    double prepareSeconds = 0.0;
  };

  // Coverage of one prepared target; a Router user must know whether every Z
  // abstract state of the target is finite, since an infinite entry cannot be
  // turned into a zero without breaking the consistency of the bound.
  struct TargetInfo {
    int port = 0;
    long long finiteStates = 0;
    long long totalStates = 0;
    long long zFiniteStates = 0;
    long long zTotalStates = 0;
    long long tableBytes = 0;
    bool allZFinite = false;
  };

  // init must be called once per instance.  It resets every derived table of a
  // previous call, so a second init starts clean instead of reusing stale
  // targets; the query entry points below are const and never accumulate state.
  void init(const Architecture& arch) {
    arch_ = &arch;
    const auto start = std::chrono::steady_clock::now();
    // Every container that only appends during a build must be emptied here:
    // mergeHops reserves and appends hop types and audit edges, so a second init
    // would otherwise double the audit set and mix two architectures.
    netTypes_.clear();
    edges_.clear();
    tables_.clear();
    targetInfo_.clear();
    stats_ = Stats{};
    portCount_ = arch.portCount();
    buildSlopes();
    mergeHops();
    buildPotentials();
    buildAuditEdges();
    stats_.initSeconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  }

  int modulusX() const { return mx_; }
  int modulusY() const { return my_; }
  long long scale() const { return scale_; }
  long long slopeA(int quadrant) const { return slopeA_[quadrant]; }
  long long slopeB(int quadrant) const { return slopeB_[quadrant]; }
  const Stats& stats() const { return stats_; }
  bool isPrepared(int port) const { return tables_.count(port) != 0; }
  long long preparedTableBytes() const {
    return static_cast<long long>(tables_.size()) * kQuadrants * stateCount() * static_cast<long long>(sizeof(int32_t));
  }
  long long zStateCount() const { return static_cast<long long>(zPortCount_) * mx_ * my_; }
  const std::map<int, TargetInfo>& targets() const { return targetInfo_; }

  // Pins must exist in the architecture and use published ports.
  bool pinsValid(int sx, int sy, int sp, int tx, int ty, int tp) const {
    if (!arch_->exists(sx, sy) || !arch_->exists(tx, ty)) return false;
    return sp >= 0 && sp < portCount_ && tp >= 0 && tp < portCount_;
  }

  // Builds the four reverse tables of one target port on demand.  Every published
  // port is a legal target, so the cache is bounded by the port count.
  void prepareTarget(int port) {
    if (port < 0 || port >= portCount_) throw std::runtime_error("prepareTarget: port out of range");
    if (tables_.count(port) != 0) return;
    const auto start = std::chrono::steady_clock::now();
    std::array<std::vector<int32_t>, kQuadrants> tables;
    long long finite = 0, zFinite = 0;
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      tables[quadrant].assign(stateCount(), kInf32);
      reverseDijkstra(quadrant, port, tables[quadrant]);
      for (int state = 0; state < stateCount(); ++state) {
        if (tables[quadrant][state] == kInf32) continue;
        ++finite;
        if (zIndexOfPort_[state % portCount_] >= 0) ++zFinite;
      }
    }
    stats_.targetFiniteStates = finite;
    stats_.targetZFiniteStates = zFinite;
    stats_.tableBytesPerTarget = static_cast<long long>(kQuadrants) * stateCount() * sizeof(int32_t);
    TargetInfo info;
    info.port = port;
    info.finiteStates = finite;
    info.totalStates = static_cast<long long>(kQuadrants) * stateCount();
    info.zFiniteStates = zFinite;
    info.zTotalStates = kQuadrants * static_cast<long long>(zPortCount_) * mx_ * my_;
    info.tableBytes = stats_.tableBytesPerTarget;
    info.allZFinite = (zFinite == info.zTotalStates);
    targetInfo_[port] = info;
    tables_.emplace(port, std::move(tables));
    ++stats_.preparedTargets;
    stats_.prepareSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  }

  // 0 for an identical pin; false when the pins are invalid or the abstract state
  // needed by the query was not reached by the reverse search (unsupported).
  // const and side-effect free: the caller times a whole batch, not each call.
  bool lowerBound(int sx, int sy, int sp, int tx, int ty, int tp, long long& value) const {
    if (!pinsValid(sx, sy, sp, tx, ty, tp)) return false;
    if (sx == tx && sy == ty && sp == tp) {
      value = 0;
      return true;
    }
    const auto found = tables_.find(tp);
    if (found == tables_.end()) throw std::runtime_error("lowerBound: target port is not prepared");
    const long long dx = tx - sx;
    const long long dy = ty - sy;
    // The abstract state is the source port at the residue that complements the
    // query displacement, matching the reverse search started at (0,0,target).
    const int rx = ((mx_ - (static_cast<int>(dx) % mx_)) % mx_ + mx_) % mx_;
    const int ry = ((my_ - (static_cast<int>(dy) % my_)) % my_ + my_) % my_;
    const int state = (rx + mx_ * ry) * portCount_ + sp;
    const std::array<std::vector<int32_t>, kQuadrants>& tables = found->second;
    long long best = std::numeric_limits<long long>::min();
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      const int32_t reducedDistance = tables[quadrant][state];
      if (reducedDistance == kInf32) continue;
      const long long raw = slopeA_[quadrant] * dx + slopeB_[quadrant] * dy +
                            static_cast<long long>(reducedDistance) + potential_[quadrant][tp] -
                            potential_[quadrant][sp];
      const long long candidate = ceilPositive(raw, scale_);
      if (candidate > best) best = candidate;
    }
    if (best == std::numeric_limits<long long>::min()) {
      return false;
    }
    value = std::max<long long>(0, best) + mandatoryLine(sx, sy, tx, ty);
    return true;
  }

  // Same linear bound as the experiment 5 probe, for tightness comparison.
  long long linearBound(int sx, int sy, int sp, int tx, int ty, int tp) const {
    if (!pinsValid(sx, sy, sp, tx, ty, tp)) throw std::runtime_error("linearBound: invalid pins");
    if (sx == tx && sy == ty && sp == tp) return 0;
    const long long dx = tx - sx;
    const long long dy = ty - sy;
    long long best = std::numeric_limits<long long>::min();
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      const long long raw = slopeA_[quadrant] * dx + slopeB_[quadrant] * dy + potential_[quadrant][tp] -
                            potential_[quadrant][sp];
      best = std::max(best, ceilPositive(raw, scale_));
    }
    return std::max<long long>(0, best) + mandatoryLine(sx, sy, tx, ty);
  }

  // Self-check hook: minimum reduced cost with one potential entry perturbed.
  long long minReducedWithTamperedPotential(int quadrant, int port, long long delta) const {
    std::vector<long long> tampered = potential_[quadrant];
    tampered[port] += delta;
    return minReducedWith(quadrant, tampered);
  }

  long long auditMinReduced() const {
    long long best = std::numeric_limits<long long>::max();
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      best = std::min(best, minReducedWith(quadrant, potential_[quadrant]));
    }
    return best;
  }

 private:
  struct NetType {
    int netIndex = 0;
    int dx = 0;
    int dy = 0;
    int blockDelay = 0;
    long long count = 0;
  };
  struct Edge {
    int from = 0;
    int to = 0;
    int dx = 0;
    int dy = 0;
    long long cost = 0;
  };
  struct Incoming {
    int from = 0;
    int dx = 0;
    int dy = 0;
    int32_t reduced = 0;
  };

  int stateCount() const { return mx_ * my_ * portCount_; }
  int residueOf(int dx, int dy) const {
    const int rx = ((dx % mx_) + mx_) % mx_;
    const int ry = ((dy % my_) + my_) % my_;
    return rx + mx_ * ry;
  }
  static long long ceilPositive(long long value, long long scale) {
    if (value <= 0) return 0;
    return (value + scale - 1) / scale;
  }
  long long mandatoryLine(int sx, int sy, int tx, int ty) const {
    return arch_->lineDelayCrossing(Axis::Vertical, sx, tx) + arch_->lineDelayCrossing(Axis::Horizontal, sy, ty);
  }

  // Slopes from the architecture: for every signed direction the cheapest
  // self-loop cost per unit displacement, scaled by the common period.
  void buildSlopes() {
    zIndexOfPort_.assign(portCount_, -1);
    zPorts_.clear();
    for (int port = 0; port < portCount_; ++port) {
      if (!arch_->isNetSource(port)) continue;
      zIndexOfPort_[port] = static_cast<int>(zPorts_.size());
      zPorts_.push_back(port);
    }
    zPortCount_ = static_cast<int>(zPorts_.size());
    if (zPortCount_ == 0) throw std::runtime_error("architecture exposes no Z* net sources");

    int maxX = 1, maxY = 1;
    for (int netIndex = 0; netIndex < arch_->netCount(); ++netIndex) {
      const NetTemplate& net = arch_->net(netIndex);
      if ((net.dx == 0) == (net.dy == 0)) throw std::runtime_error("Net template is not axis aligned");
      maxX = std::max(maxX, std::abs(net.dx));
      maxY = std::max(maxY, std::abs(net.dy));
    }
    mx_ = maxX;
    my_ = maxY;
    scale_ = std::lcm(mx_, my_);

    // Self-loop cost of a Z port: cheapest Arc from its Net landing back to it.
    std::vector<long long> selfLoop(zPortCount_, std::numeric_limits<long long>::max());
    for (int z = 0; z < zPortCount_; ++z) {
      const NetTemplate& net = arch_->net(arch_->netOfOutput(zPorts_[z]));
      for (const ArcTemplate& arc : arch_->outgoingArcs(net.to)) {
        if (arc.to != zPorts_[z]) continue;
        selfLoop[z] = std::min<long long>(selfLoop[z], arc.delay);
      }
    }
    const int signX[kQuadrants] = {1, 1, -1, -1};
    const int signY[kQuadrants] = {1, -1, 1, -1};
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      long long bestA = 0, bestB = 0;
      for (int z = 0; z < zPortCount_; ++z) {
        if (selfLoop[z] == std::numeric_limits<long long>::max()) continue;
        const NetTemplate& net = arch_->net(arch_->netOfOutput(zPorts_[z]));
        if (net.dx * signX[quadrant] > 0) {
          const long long value = selfLoop[z] * (scale_ / std::abs(net.dx));
          if (bestA == 0 || value < bestA) bestA = value;
        }
        if (net.dy * signY[quadrant] > 0) {
          const long long value = selfLoop[z] * (scale_ / std::abs(net.dy));
          if (bestB == 0 || value < bestB) bestB = value;
        }
      }
      if (bestA == 0 || bestB == 0) throw std::runtime_error("no positive self-loop for a quadrant");
      slopeA_[quadrant] = signX[quadrant] * bestA;
      slopeB_[quadrant] = signY[quadrant] * bestB;
    }
  }

  // Every real resolveNet hop, merged by (net, actual displacement, block charge).
  void mergeHops() {
    std::map<std::tuple<int, int, int, int>, NetType> types;
    for (int y = 0; y < Architecture::kHeight; ++y) {
      for (int x = 0; x < Architecture::kWidth; ++x) {
        if (!arch_->exists(x, y)) continue;
        for (int netIndex = 0; netIndex < arch_->netCount(); ++netIndex) {
          const ResolvedEdge edge = arch_->resolveNet(x, y, netIndex);
          if (!edge.valid) {
            ++stats_.invalidHops;
            continue;
          }
          ++stats_.validHops;
          const int lineDelay = arch_->lineDelayCrossing(Axis::Vertical, x, edge.x) +
                                arch_->lineDelayCrossing(Axis::Horizontal, y, edge.y);
          const auto key = std::make_tuple(netIndex, edge.x - x, edge.y - y, edge.delay - lineDelay);
          const auto found = types.find(key);
          if (found == types.end()) {
            types.emplace(key, NetType{netIndex, edge.x - x, edge.y - y, edge.delay - lineDelay, 1});
          } else {
            ++found->second.count;
          }
        }
      }
    }
    netTypes_.reserve(types.size());
    for (const auto& [key, type] : types) netTypes_.push_back(type);
    stats_.hopTypes = static_cast<long long>(netTypes_.size());
    stats_.arcEdges = 0;
    for (int port = 0; port < portCount_; ++port) stats_.arcEdges += arch_->outgoingArcs(port).size();
    edges_.reserve(netTypes_.size() + stats_.arcEdges);
    for (const NetType& type : netTypes_) {
      const NetTemplate& net = arch_->net(type.netIndex);
      edges_.push_back({net.from, net.to, type.dx, type.dy, type.blockDelay});
    }
    for (int port = 0; port < portCount_; ++port) {
      for (const ArcTemplate& arc : arch_->outgoingArcs(port)) {
        edges_.push_back({port, arc.to, 0, 0, arc.delay});
      }
    }
  }

  // One Bellman-Ford pass per quadrant on the full port graph with an all-zero
  // super source.  A negative cycle is a hard error, never a silent slope change.
  void buildPotentials() {
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      std::vector<long long>& potential = potential_[quadrant];
      potential.assign(portCount_, 0);
      bool changed = true;
      while (changed) {
        changed = false;
        ++stats_.bellmanRounds[quadrant];
        if (stats_.bellmanRounds[quadrant] > portCount_ + 1) {
          throw std::runtime_error("negative cycle in the port constraint graph");
        }
        for (const Edge& edge : edges_) {
          const long long weight = scale_ * edge.cost - slopeA_[quadrant] * edge.dx - slopeB_[quadrant] * edge.dy;
          const long long candidate = potential[edge.from] + weight;
          if (candidate < potential[edge.to]) {
            potential[edge.to] = candidate;
            changed = true;
          }
        }
      }
    }
  }

  // Per quadrant incoming edge lists with reduced costs, plus the edge audit.
  void buildAuditEdges() {
    incomingByQuadrant_ = {};
    stats_.minReduced = std::numeric_limits<long long>::max();
    for (int quadrant = 0; quadrant < kQuadrants; ++quadrant) {
      incomingByQuadrant_[quadrant].assign(portCount_, {});
      const std::vector<long long>& potential = potential_[quadrant];
      for (const Edge& edge : edges_) {
        const long long weight = scale_ * edge.cost - slopeA_[quadrant] * edge.dx - slopeB_[quadrant] * edge.dy;
        const long long reduced = weight + potential[edge.from] - potential[edge.to];
        ++stats_.reducedChecks;
        if (reduced < 0) {
          // Infeasible potentials mean no reverse table can be trusted, so this
          // is a hard failure instead of a warning: the class only promises a
          // certified lower bound when every reduced cost is non-negative.
          ++stats_.negativeReduced;
          stats_.minReduced = std::min(stats_.minReduced, reduced);
          throw std::runtime_error("negative reduced cost: the potential is not feasible");
        }
        if (reduced > kInf32) throw std::runtime_error("reduced cost exceeds int32");
        stats_.minReduced = std::min(stats_.minReduced, reduced);
        incomingByQuadrant_[quadrant][edge.to].push_back(
            {edge.from, edge.dx, edge.dy, static_cast<int32_t>(reduced)});
      }
    }
    stats_.abstractStates = stateCount();
  }

  long long minReducedWith(int quadrant, const std::vector<long long>& potential) const {
    long long best = std::numeric_limits<long long>::max();
    for (const Edge& edge : edges_) {
      const long long weight = scale_ * edge.cost - slopeA_[quadrant] * edge.dx - slopeB_[quadrant] * edge.dy;
      best = std::min(best, weight + potential[edge.from] - potential[edge.to]);
    }
    return best;
  }

  // Reverse Dijkstra from the target residue (0,0) over negated displacements;
  // table[(r,v)] is the minimum reduced cost from (r,v) to (0,0,target).
  void reverseDijkstra(int quadrant, int targetPort, std::vector<int32_t>& table) const {
    using Entry = std::pair<int64_t, int>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
    const int source = targetPort;  // residue (0,0)
    table[source] = 0;
    queue.push({0, source});
    while (!queue.empty()) {
      const auto [distance, state] = queue.top();
      queue.pop();
      if (distance != table[state]) continue;
      const int port = state % portCount_;
      const int residue = state / portCount_;
      const int rx = residue % mx_;
      const int ry = residue / mx_;
      for (const Incoming& edge : incomingByQuadrant_[quadrant][port]) {
        const int px = ((rx - edge.dx) % mx_ + mx_) % mx_;
        const int py = ((ry - edge.dy) % my_ + my_) % my_;
        const int nextState = (px + mx_ * py) * portCount_ + edge.from;
        const int64_t candidate = static_cast<int64_t>(distance) + edge.reduced;
        // The sentinel is INT32_MAX, so a value that reaches or exceeds it can no
        // longer be told apart from an unreachable state: fail loudly instead of
        // storing an ambiguous distance.
        if (candidate >= kInf32) throw std::runtime_error("reverse Dijkstra distance exceeds the int32 sentinel");
        if (candidate < table[nextState]) {
          table[nextState] = static_cast<int32_t>(candidate);
          queue.push({candidate, nextState});
        }
      }
    }
  }

  const Architecture* arch_ = nullptr;
  int portCount_ = 0;
  int mx_ = 0;
  int my_ = 0;
  long long scale_ = 0;
  std::array<long long, kQuadrants> slopeA_{};
  std::array<long long, kQuadrants> slopeB_{};
  std::vector<int> zPorts_;
  std::vector<int> zIndexOfPort_;
  int zPortCount_ = 0;
  std::vector<NetType> netTypes_;
  std::vector<Edge> edges_;
  std::array<std::vector<long long>, kQuadrants> potential_;
  std::array<std::vector<std::vector<Incoming>>, kQuadrants> incomingByQuadrant_;
  std::map<int, std::array<std::vector<int32_t>, kQuadrants>> tables_;
  std::map<int, TargetInfo> targetInfo_;
  Stats stats_;
};

}  // namespace delayest
