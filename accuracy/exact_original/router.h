// Implicit route engine.
//
// The quotient graph has one state per (x, y, Z*) pin position.  A transition
// is: Net resolver (Z* -> I* with gap charges) followed by an Arc template or a
// short chain of Arc templates inside the destination SRB.  Neighbours are
// generated on demand; the 9.6M-state graph is never materialised.
//
// The search is A* with a consistent lower bound derived from the minimum arc
// delay of every Net span, so the answer is the exact shortest delay.
#pragma once

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <string_view>
#ifdef EDA_EXP107_HIGH_G
#include <tuple>
#endif
#include <vector>

#include "architecture.h"
#include "query_cache.h"

namespace delayest {

// Monotone radix heap for integer keys (Ahuja-Mehlhorn-Orlin-Tarjan).
// Dijkstra with a consistent heuristic pushes keys in non-decreasing order, so
// the bucket split by (key ^ last) is valid; pops are the true minimum, which
// keeps the search exact.  The win over a binary heap is the O(1) push.
class RadixFrontier {
 public:
  static constexpr int kBuckets = 33;

  void clear() {
    if (buckets_.empty()) buckets_.resize(kBuckets);
    for (auto& bucket : buckets_) bucket.clear();
    last_ = 0;
    count_ = 0;
  }
  bool empty() const { return count_ == 0; }
  size_t size() const { return count_; }

  void push(uint32_t key, int state) {
    if (key < last_) throw std::runtime_error("radix push violates monotone keys");
    const uint32_t diff = key ^ last_;
    const int bucket = diff == 0 ? 0 : (32 - __builtin_clz(diff));
    buckets_[bucket].push_back((static_cast<uint64_t>(key) << 32) | static_cast<uint32_t>(state));
    ++count_;
  }

  uint32_t minKey() const {
    uint32_t best = 0xFFFFFFFFu;
    for (const auto& bucket : buckets_)
      for (uint64_t entry : bucket) best = std::min(best, static_cast<uint32_t>(entry >> 32));
    return best;
  }

  uint64_t top() {
    if (buckets_[0].empty()) {
      int bucket = 1;
      while (bucket < kBuckets && buckets_[bucket].empty()) ++bucket;
      uint32_t best = 0xFFFFFFFFu;
      for (uint64_t entry : buckets_[bucket]) best = std::min(best, static_cast<uint32_t>(entry >> 32));
      last_ = best;
      // Every entry moves to a lower bucket, so this vector stays stable.
      for (uint64_t entry : buckets_[bucket]) {
        const uint32_t key = static_cast<uint32_t>(entry >> 32);
        const uint32_t diff = key ^ last_;
        buckets_[diff == 0 ? 0 : (32 - __builtin_clz(diff))].push_back(entry);
      }
      buckets_[bucket].clear();
    }
    const uint64_t entry = buckets_[0].back();
    buckets_[0].pop_back();
    --count_;
    return entry;
  }

 private:
  std::vector<std::vector<uint64_t>> buckets_;
  uint32_t last_ = 0;
  size_t count_ = 0;
};

class Router {
 public:
  static constexpr int kUnreachable = -1;

  // Optional external lower bound used as one more term of the A* heuristic.
  // The provider must be admissible: for every state (sx,sy,sp) and every target
  // (tx,ty,tp) the value has to satisfy bound <= true shortest distance.  A
  // false return means the bound is unknown for that pair; it is then ignored,
  // never treated as zero.  Only the binary heap may be combined with an
  // external bound: the radix heap needs a monotone key order, which is proven
  // for the built-in consistent bounds only.
  class BoundProvider {
   public:
    virtual ~BoundProvider() = default;
    virtual bool bound(int sx, int sy, int sp, int tx, int ty, int tp, long long& value) const = 0;
  };

  struct Options {
    size_t queryCacheEntries = 1u << 22;  // power of two; 0 disables the cache
    bool enableQueryCache = true;
    // The span bound is exact-safe; disabling it turns the search into plain
    // Dijkstra, which the self-check uses as an independent reference.
    bool useSpanHeuristic = true;
    // Number of ALT landmarks (0 disables the precomputed landmark bound).
    int landmarkCount = 8;
    // Integer-key radix heap instead of std::push_heap/pop_heap in the query
    // search (diagnostic: identical answers, different constant factors).
    bool useRadixHeap = false;
    // Admissible external bound; nullptr keeps the built-in heuristic only.
    const BoundProvider* boundProvider = nullptr;
  };

  struct Stats {
    long long queries = 0;
    long long exactSearches = 0;
    long long cacheHits = 0;
    long long unreachable = 0;
    long long expandedStates = 0;
    long long relaxedEdges = 0;
    double landmarkBuildSeconds = 0.0;
    long long initialBoundSum = 0;  // diagnostic: source lower bound vs answer
    long long answerSum = 0;
    // Radix-vs-binary heap diagnostic counters.
    long long radixPushes = 0;
    long long radixRedistributions = 0;
    // Diagnostic only: field states whose exact distance is finite but above the
    // uint16 storage range of distanceField.  Such a value is stored as infinite,
    // so a consumer that needs the real distance must check this counter instead
    // of reading the entry as unreachable.  No search behaviour depends on it.
    long long clippedFieldStates = 0;
#ifdef EDA_EXP107_DIAG
    long long expandedStrictF = 0;
    long long expandedStrictFUnique = 0;
    long long expandedEqualF = 0;
#endif
  };

  void init(const Architecture& arch, const Options& options);
  void resetStats() { stats_ = Stats(); }
  const Stats& stats() const { return stats_; }
  size_t queryCacheCapacity() const { return cache_.capacity(); }
  int landmarkCount() const { return landmarkCount_; }
  const Architecture& arch() const { return *arch_; }

  // Exact minimum delay for one pin pair, or kUnreachable when no route exists.
  int query(int sx, int sy, int sourcePort, int tx, int ty, int targetPort);

  // Exact minimum delay for one parsed request row; parses pin text.
  int queryText(std::string_view from, std::string_view to);

  // Bounded, deterministic memo of exact answers (shared with the residue engine).
  using QueryCache = BoundedQueryCache;

  // Test-only access for the AIR map baseline (experiment 22), which must use this
  // exact full-graph flood instead of copying the search.  The struct lives in the
  // probe so the class exports no test API of its own.
  friend struct AirMapAccess;

 private:
  int search(int sx, int sy, int sourcePort, int tx, int ty, int targetPort);
  void buildArcTemplates();
  void buildSpanHeuristic();
  void buildTransitions();
  void buildLandmarks();
  // Fills `out` (size = state count) with exact distances from one state.
  void distanceField(int x0, int y0, int zPort, std::vector<uint16_t>& out);
  // Lower bounds on d(landmark, target pin) for the current query.
  void computeTargetBounds(int tx, int ty, int targetPort);
  uint32_t heuristic(int state, int x, int y, int tx, int ty) const {
    uint32_t h = 0;
    if (useHeuristic_) {
      h = spanBound_[x < tx ? tx - x : x - tx] +
          spanBound_[Architecture::kWidth + (y < ty ? ty - y : y - ty)];
      // The span bound charges every Net hop with the cheapest Arc out of the
      // hop's landing I port.  When the target is an I* port, the last hop ends
      // on the target itself and needs no trailing Arc, so the charge for that
      // one hop must be credited back; without the credit the bound can exceed
      // the true distance and the heuristic is not admissible.  The credit
      // lowers the value, the same constant is subtracted for every state, and
      // clamping at zero keeps the heuristic consistent, so h(v) <= w + h(u)
      // still holds for every edge.
      h = h > terminalCredit_ ? h - terminalCredit_ : 0u;
    }
    if (landmarkCount_ > 0) {
      const uint16_t* row = &landmarkTable_[static_cast<size_t>(state) * landmarkCount_];
      for (int l = 0; l < landmarkCount_; ++l) {
        const uint16_t target = queryTargetBound_[l];
        const uint16_t fromLandmark = row[l];
        if (target == kInf16 || fromLandmark == kInf16) continue;
        const uint32_t candidate = target > fromLandmark ? target - fromLandmark : 0u;
        if (candidate > h) h = candidate;
      }
    }
    if (boundProvider_ != nullptr) {
      long long external = 0;
      const int statePort = zPortOfIndex_[state % zPortCount_];
      if (boundProvider_->bound(x, y, statePort, tx, ty, queryTargetPort_, external) && external > 0) {
        const uint32_t clamped =
            external > static_cast<long long>(kInf32) ? kInf32 : static_cast<uint32_t>(external);
        if (clamped > h) h = clamped;
      }
    }
    return h;
  }
  int stateId(int x, int y, int zIndex) const { return (y * Architecture::kWidth + x) * zPortCount_ + zIndex; }

  const Architecture* arch_ = nullptr;
  int zPortCount_ = 0;
  std::vector<int> zIndexOfPort_;   // port id -> Z index or -1
  std::vector<int> zPortOfIndex_;   // Z index -> port id
  // arcTemplates_[p] = direct Arc templates out of p (all published Arcs are
  // Input -> Output, so an in-SRB chain is exactly one Arc).
  std::vector<std::vector<std::pair<int, int>>> arcTemplates_;
  // arcCost_[p * portCount + q] = cheapest direct Arc p -> q (kInf16 if none).
  std::vector<uint16_t> arcCost_;
  // Per Z* state: Net destination input port and the Z* successors after its arcs.
  std::vector<int> netDestOfZ_;                  // per Z index: I* port reached by the Net
  std::vector<std::vector<std::pair<int, int>>> successorsOfZ_;  // per Z index: (Z port, arc cost)
  // Span heuristic tables: index [0, kWidth) is |dx|, [kWidth, kWidth+kHeight) is |dy|.
  std::vector<uint32_t> spanBound_;
  bool useHeuristic_ = true;
  // Cheapest outgoing Arc of an I* target, subtracted once from the span bound
  // because the final Net hop does not need a trailing Arc.  Zero for every
  // other target class.
  uint32_t terminalCredit_ = 0;

  // ALT landmark data: landmarkTable_[state * K + l] = exact distance from
  // landmark l to that state; landmarkCellMin_[cell * K + l] = min over Z*
  // states of the cell.  queryTargetBound_ holds d(lower bound)(landmark, target).
  static constexpr int kMaxLandmarks = 16;
  std::vector<uint16_t> landmarkTable_;
  std::vector<uint16_t> landmarkCellMin_;
  int landmarkCount_ = 0;
  uint16_t queryTargetBound_[kMaxLandmarks] = {};
  static constexpr uint16_t kInf16 = 0xFFFF;
  static constexpr uint32_t kInf32 = 0xFFFFFFFFu;

  // Search scratch (kept between queries to avoid reallocation).
  std::vector<uint32_t> dist_;
  std::vector<int> touched_;
  std::vector<uint64_t> heap_;
#ifdef EDA_EXP107_HIGH_G
  std::vector<std::tuple<uint32_t, uint32_t, int>> tieHeap_;
#endif
  RadixFrontier radix_;
  bool useRadixHeap_ = false;
  const BoundProvider* boundProvider_ = nullptr;
  int queryTargetPort_ = -1;
  QueryCache cache_;
  Stats stats_;
};

}  // namespace delayest
