// DESIGN.md section 8 submission engine: lane-preserving residue tables.
//
// Every Z* port keeps its identity (160 of them).  For each quadrant (signed
// horizontal/vertical slope pair) the ports form a 160-node translation graph;
// Bellman-Ford potentials turn its edge costs into nonnegative reduced costs,
// and a Dijkstra over the finite residue graph (rx, ry, port) with
// rx in [0, Mx), ry in [0, My) yields a table per (source, quadrant) that is
// queried by four lookups and constant arithmetic:
//
//   H(dx, dy, s, t) = max_quadrant((a*dx + b*dy + table[q, s, t, dx%Mx, dy%My]) / S)
//
// Exactly mandatory Line Gap charges are added on top.  Block geometry is a
// documented outstanding approximation: this revision ignores the Block-skip
// displacement bonus and the non-crossable Block veto.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "architecture.h"
#include "pattern_database.h"
#include "query_cache.h"

namespace delayest {

class ResidueEstimator {
 public:
  // Experiment 6/8 endpoint refinement.  Off keeps the pure residue answer;
  // Source/Target/Both expand the real first and/or last Net around the same
  // residue table (see experiment/实验6-真实端点修正.md).
  // SourceShort (experiment 15) is a dispatch policy, not a new algorithm: it
  // runs the existing Both path for requests whose Manhattan distance is at most
  // endpointShortDistance and the existing Source path otherwise.
  enum class EndpointMode { Off = 0, Source = 1, Target = 2, Both = 3, SourceShort = 4 };
  // Experiment 19C: frozen residual model, off by default.  Long applies it only
  // above the fixed short-distance boundary.  XgbShrink24 (experiment 32) is the
  // best-by-mean variant of a pre-declared short/Block guard family: it applies the
  // same model but halves the raw correction on rows with |dx|+|dy| <= 24.  It is
  // an explicit candidate, off by default, because the label-level gate failed.
  enum class ResidualMode { Off = 0, Xgb = 1, Long = 2, XgbShrink24 = 3, XgbBounds = 4, XgbBase = 5,
                            XgbBase24 = 6, XgbBase47D8 = 7 };
  // Experiment 31: explicit fused real-path bounds for the trained residue
  // configuration.  Off keeps every existing code path; Lower builds the port
  // quotient table and raises a positive answer to L; Upper1 lowers it to the
  // <=1-Net short-path minimum that mergeShortCandidates already computes;
  // Both applies the interval.  See experiment/实验31-生产上下界融合.md.
  enum class BoundsMode { Off = 0, Lower = 1, Upper1 = 2, Both = 3 };

  struct Stats {
    long long queries = 0;
    long long cacheHits = 0;
    long long unreachable = 0;   // endpoint class that cannot be a source/target
    long long invalid = 0;       // malformed pin text
    long long fallback = 0;      // all quadrants infinite; straight-line estimate
    long long pdbFloorApplied = 0;      // answers raised to the audited PDB bound
    long long pdbFloorUnsupported = 0;  // pair whose PDB bound is unknown: unchanged
    long long pdbTargetsPrepared = 0;   // lazily built per-target tables
    long long shortBoth = 0;            // SourceShort requests dispatched to Both
    long long shortSource = 0;          // SourceShort requests dispatched to Source
    long long templateQueries = 0;      // template evaluations on cache misses
    long long templateSelections = 0;   // miss-path outputs replaced by the template
    double buildSeconds = 0.0;
    double pdbPrepareSeconds = 0.0;
    size_t tableBytes = 0;
    size_t templateBytes = 0;
    size_t cacheEntries = 0;
    int minReducedEdge = 0;      // must be >= 0
    long long residueDijkstraRuns = 0;  // residue Dijkstra calls in buildTables
    // Experiment 31 fused bounds; all zero when the bounds mode is Off.
    long long boundsApplied = 0;       // positive answers changed by the interval
    long long boundsUnknownLower = 0;  // quotient lower bound unavailable: unchanged
    long long boundsUnknownUpper = 0;  // <=1-Net minimum unavailable: unchanged
    long long boundsInconsistent = 0;  // L > U1 observed and never used
    double boundsBuildSeconds = 0.0;   // port quotient all-pairs table build
    size_t boundsTableBytes = 0;       // quotient table bytes, separate from tableBytes
  };

  struct Options {
    size_t cacheBytes = 64u << 20;
    // Residue lattice multiplier: the moduli are (largest horizontal span) * m
    // and (largest vertical span) * m.  m = 1 reproduces the current table; a
    // larger m tightens the value (smaller residue classes) at m^2 times the
    // table memory and build time.  The reduced-cost non-negativity check guards
    // the nominal Gap-free translation graph only; on the real Block graph the
    // value is an estimate with counterexamples above the true distance, see
    // experiment/实验4-真实图下界审计.md.
    int residueMultiplier = 1;
    // Endpoint refinement; Off is the production default.
    EndpointMode endpointMode = EndpointMode::Off;
    // SourceShort dispatch threshold on the endpoint Manhattan distance.
    int endpointShortDistance = 150;
    // Experiment 14 candidate: raise the answer to the audited pattern-database
    // lower bound when that bound is available.  Off is the production default.
    bool pdbFloor = false;
    ResidualMode residualMode = ResidualMode::Off;
    // Experiment 139: the packaged default may select an already-bias-corrected
    // translated-field candidate on cache misses only.
    bool templateSelection = false;
    int templateBias = 0;
    // Experiment 31 candidate: fused real-path interval; Off is the production
    // default and keeps the existing output byte for byte.
    BoundsMode boundsMode = BoundsMode::Off;
  };

  void init(const Architecture& arch, const Options& options);
  const Stats& stats() const { return stats_; }
  int sourceCount() const { return static_cast<int>(sourcePorts_.size()); }
  int targetCount() const { return static_cast<int>(targetPorts_.size()); }
  int quadrantCount() const { return kQuadrants; }
  // Residue geometry exposed for the independent verification binary.
  int modulusX() const { return mx_; }
  int modulusY() const { return my_; }
  int scale() const { return scale_; }
  long long tableEntries() const { return static_cast<long long>(table_.size()); }
  const std::vector<int>& slopeA() const { return slopeA_; }
  const std::vector<int>& slopeB() const { return slopeB_; }
  // Read-only potential per quadrant, indexed by the estimator's Z order
  // (ports scanned in increasing id order, Z* ports only).  Used by the
  // independent bound audit; no production behaviour changes.
  const std::vector<int32_t>& potential(int quadrant) const { return potential_[quadrant]; }

  int estimateText(std::string_view from, std::string_view to);
  int estimate(int sx, int sy, int sourcePort, int tx, int ty, int targetPort);

 private:
  static constexpr int kQuadrants = 4;
  static constexpr uint16_t kInf16 = 0xFFFF;
  static constexpr uint32_t kInf32 = 0xFFFFFFFFu;
  static constexpr int32_t kInfTable = 0x7FFFFFFF;

  // Pure numeric residue path: same-pin / validity / endpoint class / table
  // lookup / straight-line fallback / mandatory Line / rounding.  No query
  // counters and no memo, so endpoint leaves can call it directly.
  struct BaseAnswer {
    int value = -1;
    bool unreachable = false;
    bool fallback = false;
  };
  BaseAnswer estimateBase(int sx, int sy, int sourcePort, int tx, int ty, int targetPort);

  // Experiment 51 stage 1 read-only probe: the four quadrant candidates that the
  // pure residue lookup reduces to one max, plus the fold and Line state that
  // produced them.  estimateBase() is a thin extractor over this computation, so
  // the probe can never observe a different numeric path than production.  All
  // slot and candidate values are table units; kInfTable marks an infinite
  // quadrant, and best/secondBest/worst are -1 when too few quadrants are finite.
  struct QuadrantDiagnostics {
    int value = -1;              // -endpoint-mode off -residual off answer
    bool unreachable = false;    // missing cell / port cannot serve its role
    bool fallback = false;       // all four quadrants infinite: straight line
    bool samePin = false;        // same cell and port: 0 without any lookup
    bool derivedTarget = false;  // I* target: the displacement fold is applied
    bool clamped = false;        // Line-inclusive delay was negative and set to 0
    int dx = 0;
    int dy = 0;
    int residue = 0;        // residueOf(dx, dy), before any fold
    int lookupDx = 0;       // displacement every quadrant candidate uses
    int lookupDy = 0;
    int lookupResidue = 0;  // table residue every quadrant slot is read at
    int finiteQuadrants = 0;
    int dominant = -1;  // first argmax over the finite candidates
    int32_t slot[kQuadrants] = {kInfTable, kInfTable, kInfTable, kInfTable};
    // kInfTable when the quadrant is infinite; a finite candidate is never that
    // value in this architecture (slope*displacement stays far below 2^31).
    int64_t candidate[kQuadrants] = {kInfTable, kInfTable, kInfTable, kInfTable};
    int64_t best = -1;        // max finite candidate
    int64_t secondBest = -1;  // second largest with multiplicity, -1 below 2 finite
    int64_t worst = -1;       // min finite candidate, -1 when none is finite
    int unclampedDelay = 0;   // Line-inclusive answer before the zero clamp
    int lineVertical = 0;     // mandatory Line charges, added only on a lookup
    int lineHorizontal = 0;
  };
  QuadrantDiagnostics quadrantDiagnostics(int sx, int sy, int sourcePort, int tx, int ty,
                                          int targetPort);
  // Experiment 6 candidate minimum for the configured EndpointMode.  The
  // <=1-Net real-path minimum is written to *shortUpper (-1 when unknown) before
  // the residue leaves below can improve `best`; every branch, including the
  // Source early return, passes through the capture.
  int estimateEndpoint(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                       EndpointMode mode, int* shortUpper);

  // One real endpoint transition: exit = Net landing (source side) or
  // entrance = Net predecessor + optional terminal Arc (target side).
  struct Endpoint {
    int32_t x = 0;
    int32_t y = 0;
    int32_t port = -1;
    int32_t cost = 0;
  };
  void collectExits(int sx, int sy, int sourcePort);
  void collectEntrances(int tx, int ty, int targetPort);
  void mergeShortCandidates(int sx, int sy, int sourcePort, int tx, int ty, int targetPort, int& best);
  static void dedupMinEndpoints(std::vector<Endpoint>& items);
  static void mergeMin(int value, int& best);
  // Raises `value` to the pattern-database lower bound for this pair.  Returns
  // the value unchanged when the floor is off, when the table cannot be built or
  // when the abstract state is infinite (never treats that as zero).
  int applyPdbFloor(int sx, int sy, int sourcePort, int tx, int ty, int targetPort, int value);
  // Applies the frozen residual model to a finished estimate.  XgbBase24 is the
  // experiment 47 single-process hybrid: the frozen XgbBase path at Manhattan
  // distance <= 24 (the experiment 46 boundary) and the production Xgb path above it, sharing
  // one residue table and one request cache.  The dispatch happens after the
  // cache lookup, so a repeated request costs the same as any other hit.
  // XgbBase47D8 is the experiment 58 candidate: the frozen 47-slot depth-8 model
  // (44 production slots + base, base - fast, base / max(fast, 1)) replaces the
  // production model for every positive answer.  It reads no L slot, so it never
  // calls lowerBound(), and its init path skips the quotient bounds table.
  int applyResidual(int sx, int sy, int sourcePort, int tx, int ty, int targetPort, int value,
                    int baseValue) const;
  // Experiment 31 fused bounds.  buildBoundsTable audits the non-negative delay
  // premise and then builds the 496-port all-pairs quotient distances (Arc keeps
  // its published delay, Net costs zero); lowerBound adds the mandatory Line
  // charges.  applyBounds clamps a finished positive answer after applyResidual
  // with the caller's captured <=1-Net minimum (upper1, -1 when unknown):
  // zero/negative answers and unknown bounds are preserved, and an inconsistent
  // interval is counted and never used.  No cross-call bound state is kept.
  void buildBoundsTable(const Architecture& arch);
  int quotientDistance(int from, int to) const;
  int lowerBound(int sx, int sy, int sourcePort, int tx, int ty, int targetPort) const;
  int applyBounds(int sx, int sy, int sourcePort, int tx, int ty, int targetPort, int value,
                  int upper1);
  int applyTemplateSelection(int sx, int sy, int sourcePort, int tx, int ty, int targetPort,
                             int value);

  void buildPorts(const Architecture& arch, int residueMultiplier);
  void buildTranslationGraph(const Architecture& arch);
  void buildPotentials();
  void buildTables();
  void runResidueDijkstra(int quadrant, const std::vector<std::pair<int, int32_t>>& seeds,
                          std::vector<int32_t>& dist);
  void fillTargets(int quadrant, int sourceIndex, const std::vector<int32_t>& dist);
  // Restore a logical Z* source row from its Net landing's stored row.
  int32_t tableValue(int quadrant, int sourceIndex, int targetIndex, int residue) const;
  // Experiment 17 equivalence test only.  The struct lives in the test file and
  // reads the stored table through this friendship, so the class exposes no test
  // API of its own; callers must pass ports that exist in the built port lists.
  friend struct ResidueTableAccess;
  // Experiment 31 bounds check only: numeric access to the fused lower bound and
  // the last <=1-Net minimum, so the production interface grows no test API.
  friend struct Exp31BoundsAccess;
  // Experiment 47 focused check only: switch the residual mode on one initialized
  // estimator so the hybrid dispatch can be compared against the two frozen modes
  // on the same residue table, with no second 814 MB table build.
  friend struct Exp47HybridAccess;
  // Experiment 51 stage 1 probe only: read the four quadrant candidates and the
  // fold/Line state of one request, with no effect on any production path.
  friend struct Exp51QuadrantAccess;
  // Experiment 53 first checkpoint probe only: read the production endpoint
  // enumeration state (scratch exit/entrance lists, options, dispatch and the
  // private estimateBase/estimateEndpoint/mergeShortCandidates leaves) so the
  // complete no-prune candidate multiset can be rebuilt beside the production
  // loops.  Nothing in the production path changes; the friend is test-only.
  friend struct Exp53EndpointAccess;
  // Experiment 145 offline audit only: reconstruct the pure residue candidate
  // at an arbitrary nominal displacement without requiring a real target cell.
  // This does not participate in production queries.
  friend struct Exp145SafeResidueAccess;
  // Experiment 147 dense-cache benchmark only: evaluate the same test-only
  // safe residue bound while changing only the state-value cache representation.
  friend struct Exp147SafeResidueAccess;
  // Experiment 146 Router component probe only: build the safe jump-corrected
  // lower bound for an arbitrary Router state and target pin.
  friend struct Exp146SafeResidueAccess;
  int32_t* tableSlot(int quadrant, int sourceIndex, int targetIndex, int residue) {
    return &table_[tableOffset(quadrant, sourceIndex, targetIndex, residue)];
  }
  const int32_t* tableSlot(int quadrant, int sourceIndex, int targetIndex, int residue) const {
    return &table_[tableOffset(quadrant, sourceIndex, targetIndex, residue)];
  }
  // Experiment 35: quadrant is the innermost index, so the four quadrant values of
  // one (source, storedTarget, residue) leaf are contiguous 16 bytes.  Storage
  // order only; every stored value, the max order, the rounding, the INF sentinel
  // and the I* target derivation are unchanged.
  size_t tableOffset(int quadrant, int sourceIndex, int targetIndex, int residue) const {
    return ((static_cast<size_t>(sourceIndex - static_cast<int>(zPorts_.size())) * storedTargetCount_ + targetIndex) * residueCount_ +
            residue) *
               kQuadrants +
           quadrant;
  }
  // Experiment 36: two remainders instead of four.  For a positive modulus
  // (init keeps mx_/my_ positive) C++ truncating % gives r in (-m, m), so adding m
  // once when r < 0 is the same as the previous ((d % m) + m) % m.
  int residueOf(int dx, int dy) const {
    int rx = dx % mx_;
    if (rx < 0) rx += mx_;
    int ry = dy % my_;
    if (ry < 0) ry += my_;
    return rx + mx_ * ry;
  }
  int residueShift(int residue, int vx, int vy) const {
    const int rx = (residue % mx_ + vx % mx_ + mx_) % mx_;
    const int ry = (residue / mx_ + vy % my_ + my_) % my_;
    return rx + mx_ * ry;
  }

  const Architecture* arch_ = nullptr;
  int mx_ = 0;               // horizontal modulus (largest horizontal Net span)
  int my_ = 0;               // vertical modulus
  int scale_ = 0;            // S = lcm(mx_, my_)
  int residueCount_ = 0;     // mx_ * my_
  std::vector<int> zPorts_;  // 160 Z* ports in deterministic order
  std::vector<int> zIndexOfPort_;
  std::vector<int8_t> vx_;   // Net displacement per Z* port
  std::vector<int8_t> vy_;
  std::vector<uint16_t> arcCost_;  // [p][q] cheapest Arc from Net input of p to Z q
  std::vector<std::vector<std::pair<int, uint16_t>>> successors_[kQuadrants];
  std::vector<int32_t> potential_[kQuadrants];
  std::vector<int> slopeA_, slopeB_;
  std::vector<int> sourcePorts_;  // 368: Z* + interconnect input + logic input
  std::vector<int> sourceOfPort_;
  std::vector<int> landingSourceOfZ_;
  std::vector<int> targetPorts_;  // 448: Z* + interconnect input + logic output
  std::vector<int> targetOfPort_;
  // Per target index: terminal predecessors (Z port index, Arc delay) for
  // logic outputs, hoisted out of the residue loop.
  std::vector<std::vector<std::pair<int, int>>> terminalPreds_;
  // Previous-residue lookup per (Z port, residue): avoids the modulo in the
  // table fill inner loop.
  std::vector<uint16_t> prevResidue_;
  std::vector<uint16_t> templateValues_;
  std::vector<int> templateIndexOfPort_;
  std::vector<uint8_t> templateSourcePossible_;
  std::vector<int> iPredecessorOf_;  // target index -> Z port index for Net landings
  // Experiment 17 phase B storage map.  An I* target owns no column: its value
  // follows from the Z* column of the same source at the shifted residue,
  //   F(s, I_p, r) = F(s, Z_p, r - v_p) - (a*v_px + b*v_py),
  // so it stores the base column of that Z* target plus a per-quadrant term.
  std::vector<int> storedTargetOfTarget_;  // per target index -> stored column
  std::vector<int> storedTargets_;         // target index owning each column
  // The query path folds the derivation into the displacement: for an I* target
  // it looks up the base column at r - v_p with (dx - v_px, dy - v_py), which
  // equals a*dx + b*dy + F(s, Z_p, r - v_p) - (a*v_px + b*v_py) for every quadrant.
  int storedTargetCount_ = 0;
  std::vector<int32_t> table_;
  int maxReducedEdge_ = 0;
  int minArcCost_ = 0;
  EndpointMode endpointMode_ = EndpointMode::Off;
  int endpointShortDistance_ = 150;
  PatternDatabase pdb_;
  bool pdbFloor_ = false;
  ResidualMode residualMode_ = ResidualMode::Off;
  std::vector<int8_t> pdbTargetState_;  // per port: 0 unknown, 1 unsupported, 2 ready
  std::vector<Endpoint> exits_;      // scratch, cleared per request
  std::vector<Endpoint> entrances_;  // scratch, cleared per request
  BoundedQueryCache cache_;
  Stats stats_;
  // Experiment 31 bounds state.  quotientDistance_ is empty unless the Lower or
  // Both mode built it; the <=1-Net minimum is a local of estimate() and is not
  // kept across calls.
  BoundsMode boundsMode_ = BoundsMode::Off;
  bool templateSelection_ = false;
  int templateBias_ = 0;
  int quotientPortCount_ = 0;
  std::vector<int32_t> quotientDistance_;
};

}  // namespace delayest
