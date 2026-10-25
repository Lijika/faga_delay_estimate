// Experiment 26: periodic (nominal quotient) theory diagnostics.
//
// The quotient graph keeps the 160 Z* states.  An edge p -> q is p's nominal Net
// displacement followed by the Arc that leaves the Net landing towards q; the cost is
// that Arc only.  Gap, Block and the finite chip boundary belong to another graph and
// are not modelled here.  The probe answers three questions on that graph:
//
//   A. the slope polyhedron and Karp's minimum cycle mean: the four axial self loops
//      bound the feasible slope rectangle, Bellman-Ford potentials at the four corners
//      make every reduced edge nonnegative, and Karp's fractional cycle mean is
//      computed for the original costs and for the four reduced weightings;
//   B. De Schutter's consecutive powers: exact k edge min-plus matrices are checked
//      against M(k+c) = M(k) + c*lambda element wise, and one pair shows that M2 alone
//      merges two different net displacements;
//   C. budget limited gap free distances: a Dijkstra on the infinite displacement graph
//      inside a rectangle derived from the corner potentials, the observed exact - L
//      range per Manhattan band, one source table per multiplier (mx*my*160*4 entries)
//      to check L <= R1 <= R2 <= exact, and the axial rays of a source equal to its
//      target.  Everything is an observation inside the budget, not a global proof.
//
// Build and run (documented in the JSON too):
//   g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/periodic_theory_probe
//       tests/periodic_theory_probe.cpp src/architecture.cpp src/residue_estimator.cpp
//   ./build/periodic_theory_probe --arch "doc/eda比赛文件/arch"
//       --json validation/results/exp26-periodic-theory.json [--budget 1200]
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <tuple>
#include <vector>

#include "../src/architecture.h"
#include "../src/residue_estimator.h"

namespace delayest {
// The production cross check needs only the graph, the slopes and the potentials, so it
// uses the friendship that tests/residue_table_equiv.cpp already relies on and skips
// buildTables: no 368 source table is allocated.  This lives at the top level of namespace
// delayest to match the friend declaration in residue_estimator.h.
struct ResidueTableAccess {
  static void prepareGraph(ResidueEstimator& estimator, const Architecture& arch) {
    estimator.arch_ = &arch;
    estimator.buildPorts(arch, 1);
    estimator.buildTranslationGraph(arch);
    estimator.buildPotentials();
  }
};
}  // namespace delayest

namespace {

using delayest::Architecture;
using delayest::ArcTemplate;
using delayest::NetTemplate;

constexpr int kInf = std::numeric_limits<int>::max() / 4;
constexpr int64_t kInf64 = std::numeric_limits<int64_t>::max() / 4;

double now() {
  using clock = std::chrono::steady_clock;
  static const clock::time_point start = clock::now();
  return std::chrono::duration<double>(clock::now() - start).count();
}

long long peakRssKib() {
  struct rusage usage;
  getrusage(RUSAGE_SELF, &usage);
  return static_cast<long long>(usage.ru_maxrss);
}

// ------------------------------------------------------------------ JSON writer
// Minimal emitter: members are appended in order, nested values are passed as pre
// rendered text through raw().
class Jw {
 public:
  template <typename T>
  void num(const std::string& key, T value) {
    keyStart(key) << value;
  }
  void real(const std::string& key, double value, int precision = 6) {
    keyStart(key) << std::setprecision(precision) << value;
  }
  void str(const std::string& key, const std::string& value) {
    keyStart(key) << "\"" << escape(value) << "\"";
  }
  void flag(const std::string& key, bool value) {
    keyStart(key) << (value ? "true" : "false");
  }
  void raw(const std::string& key, const std::string& value) {
    keyStart(key) << value;
  }
  std::string text() const { return out_.str(); }

 private:
  std::ostringstream& keyStart(const std::string& key) {
    out_ << (first_ ? "" : ", ") << "\"" << escape(key) << "\": ";
    first_ = false;
    return out_;
  }
  static std::string escape(const std::string& value) {
    std::string out;
    for (char c : value) {
      if (c == '"' || c == '\\') out.push_back('\\');
      out.push_back(c);
    }
    return out;
  }
  std::ostringstream out_;
  bool first_ = true;
};

// ------------------------------------------------------------------ fractions
// Exact non reduced fraction with a positive denominator; comparisons cross multiply
// in 128 bit so a floating point value can never be read as a negative cycle.
struct Frac {
  int64_t num = 0;
  int64_t den = 1;
  bool valid = true;
};

Frac makeFrac(int64_t num, int64_t den) {
  Frac out;
  out.valid = den != 0;
  if (!out.valid) return out;
  if (den < 0) {
    num = -num;
    den = -den;
  }
  out.num = num;
  out.den = den;
  return out;
}

int compareFrac(const Frac& a, const Frac& b) {
  const __int128 left = static_cast<__int128>(a.num) * b.den;
  const __int128 right = static_cast<__int128>(b.num) * a.den;
  return left < right ? -1 : (left > right ? 1 : 0);
}

std::string fracText(const Frac& value) {
  if (!value.valid) return "{\"valid\": false}";
  std::ostringstream out;
  out << "{\"valid\": true, \"num\": " << value.num << ", \"den\": " << value.den << ", \"value\": "
      << std::setprecision(12) << (static_cast<double>(value.num) / value.den) << "}";
  return out.str();
}

// ------------------------------------------------------------------ quotient graph
struct Quotient {
  const Architecture* arch = nullptr;
  std::vector<int> zPorts;      // z index -> port id
  std::vector<int> indexOfPort; // port id -> z index (-1)
  std::vector<int> vx, vy;      // nominal Net displacement per Z* state
  std::vector<int> cost;        // zCount*zCount Arc cost, kInf when absent
  int zCount = 0;
  int mx = 0, my = 0, S = 0;

  int edge(int p, int q) const { return cost[static_cast<size_t>(p) * zCount + q]; }
  std::string name(int z) const { return arch->portName(zPorts[z]); }
  // Scaled weight of edge p -> q under the (a, b) corner: S*cost - a*vx - b*vy.
  int64_t weight(int p, int q, int a, int b) const {
    return static_cast<int64_t>(S) * edge(p, q) - static_cast<int64_t>(a) * vx[p] -
           static_cast<int64_t>(b) * vy[p];
  }
};

int gcdInt(int a, int b) {
  while (b != 0) {
    const int t = a % b;
    a = b;
    b = t;
  }
  return a;
}

Quotient buildQuotient(const Architecture& arch, int multiplier) {
  Quotient g;
  g.arch = &arch;
  g.indexOfPort.assign(arch.portCount(), -1);
  for (int p = 0; p < arch.portCount(); ++p) {
    if (!arch.isNetSource(p)) continue;
    g.indexOfPort[p] = static_cast<int>(g.zPorts.size());
    g.zPorts.push_back(p);
  }
  g.zCount = static_cast<int>(g.zPorts.size());
  if (g.zCount == 0) throw std::runtime_error("architecture exposes no Z* net sources");
  g.vx.assign(g.zCount, 0);
  g.vy.assign(g.zCount, 0);
  int maxX = 0, maxY = 0;
  for (int z = 0; z < g.zCount; ++z) {
    const NetTemplate& net = arch.net(arch.netOfOutput(g.zPorts[z]));
    g.vx[z] = net.dx;
    g.vy[z] = net.dy;
    maxX = std::max(maxX, std::abs(net.dx));
    maxY = std::max(maxY, std::abs(net.dy));
    if ((net.dx == 0) == (net.dy == 0)) throw std::runtime_error("Net template is not axis aligned");
  }
  g.mx = maxX * multiplier;
  g.my = maxY * multiplier;
  if (g.mx <= 0 || g.my <= 0) throw std::runtime_error("degenerate Net spans");
  g.S = g.mx / gcdInt(g.mx, g.my) * g.my;
  g.cost.assign(static_cast<size_t>(g.zCount) * g.zCount, kInf);
  for (int p = 0; p < g.zCount; ++p) {
    const int landing = arch.net(arch.netOfOutput(g.zPorts[p])).to;
    for (const ArcTemplate& arc : arch.outgoingArcs(landing)) {
      const int q = g.indexOfPort[arc.to];
      if (q < 0) continue;  // logic destination: a terminal, not a quotient edge
      int& slot = g.cost[static_cast<size_t>(p) * g.zCount + q];
      if (arc.delay < slot) slot = arc.delay;
    }
  }
  return g;
}

// ------------------------------------------------------------------ Bellman-Ford
// Matches the production construction: h starts at zero everywhere and is relaxed to a
// fixpoint, which yields h[to] <= h[from] + w.  A negative cycle makes the construction
// invalid and is reported instead of being hidden.
struct BfResult {
  bool feasible = false;
  int rounds = 0;
  int64_t minReduced = 0;
  int64_t maxReduced = 0;
  int negativeEdges = 0;
  int edges = 0;
  std::vector<int64_t> h;
};

BfResult bellmanFord(const Quotient& g, int a, int b) {
  BfResult result;
  result.h.assign(g.zCount, 0);
  bool changed = true;
  while (changed) {
    changed = false;
    if (++result.rounds > g.zCount + 1) return result;  // negative cycle
    for (int p = 0; p < g.zCount; ++p) {
      for (int q = 0; q < g.zCount; ++q) {
        if (g.edge(p, q) == kInf) continue;
        const int64_t candidate = result.h[p] + g.weight(p, q, a, b);
        if (candidate < result.h[q]) {
          result.h[q] = candidate;
          changed = true;
        }
      }
    }
  }
  result.minReduced = kInf64;
  result.maxReduced = -kInf64;
  for (int p = 0; p < g.zCount; ++p) {
    for (int q = 0; q < g.zCount; ++q) {
      if (g.edge(p, q) == kInf) continue;
      ++result.edges;
      const int64_t reduced = g.weight(p, q, a, b) + result.h[p] - result.h[q];
      if (reduced < 0) ++result.negativeEdges;
      result.minReduced = std::min(result.minReduced, reduced);
      result.maxReduced = std::max(result.maxReduced, reduced);
    }
  }
  result.feasible = result.negativeEdges == 0;
  return result;
}

// ------------------------------------------------------------------ Karp
// Minimum cycle mean over the strongly connected quotient graph:
//   lambda* = min_v max_{0 <= k < n} (F_n(v) - F_k(v)) / (n - k)
// with F_0(source) = 0 and F_0(v) = inf elsewhere.
struct KarpResult {
  bool ok = false;
  std::string error;
  Frac lambda;
  int witnessNode = -1;
  int reachableNodes = 0;
  int unreachableNodes = 0;
};

KarpResult karp(int n, const std::vector<int64_t>& weight) {
  KarpResult result;
  const int source = 0;
  std::vector<std::vector<int64_t>> f(n + 1, std::vector<int64_t>(n, kInf64));
  f[0][source] = 0;
  for (int k = 1; k <= n; ++k) {
    for (int v = 0; v < n; ++v) {
      int64_t best = kInf64;
      for (int u = 0; u < n; ++u) {
        const int64_t fu = f[k - 1][u];
        if (fu >= kInf64) continue;
        const int64_t w = weight[static_cast<size_t>(u) * n + v];
        if (w >= kInf64) continue;
        best = std::min(best, fu + w);
      }
      f[k][v] = best;
    }
  }
  for (int v = 0; v < n; ++v) {
    if (f[n][v] >= kInf64) {
      ++result.unreachableNodes;
      continue;
    }
    ++result.reachableNodes;
    Frac best;
    best.valid = false;
    for (int k = 0; k < n; ++k) {
      if (f[k][v] >= kInf64) continue;
      const Frac candidate = makeFrac(f[n][v] - f[k][v], n - k);
      if (!best.valid || compareFrac(candidate, best) > 0) best = candidate;
    }
    if (!best.valid) continue;
    if (result.witnessNode < 0 || compareFrac(best, result.lambda) < 0) {
      result.lambda = best;
      result.witnessNode = v;
    }
  }
  result.ok = result.witnessNode >= 0;
  if (!result.ok) result.error = "no reachable node for Karp";
  return result;
}

std::vector<int64_t> weightsOf(const Quotient& g, int a, int b, bool reduced,
                              const std::vector<int64_t>& h) {
  std::vector<int64_t> out(static_cast<size_t>(g.zCount) * g.zCount, kInf64);
  for (int p = 0; p < g.zCount; ++p) {
    for (int q = 0; q < g.zCount; ++q) {
      if (g.edge(p, q) == kInf) continue;
      int64_t w = g.weight(p, q, a, b);
      if (reduced) w += h[p] - h[q];
      out[static_cast<size_t>(p) * g.zCount + q] = w;
    }
  }
  return out;
}

bool stronglyConnected(const Quotient& g) {
  for (int start = 0; start < g.zCount; ++start) {
    std::vector<char> seen(g.zCount, 0);
    std::vector<int> stack{start};
    seen[start] = 1;
    int count = 1;
    while (!stack.empty()) {
      const int p = stack.back();
      stack.pop_back();
      for (int q = 0; q < g.zCount; ++q) {
        if (g.edge(p, q) == kInf || seen[q]) continue;
        seen[q] = 1;
        ++count;
        stack.push_back(q);
      }
    }
    if (count != g.zCount) return false;
  }
  return true;
}

// Plain Arc costs as an edge weight matrix (kInf64 when the edge is absent).
std::vector<int64_t> plainWeights(const Quotient& g) {
  std::vector<int64_t> out(static_cast<size_t>(g.zCount) * g.zCount, kInf64);
  for (int p = 0; p < g.zCount; ++p) {
    for (int q = 0; q < g.zCount; ++q) {
      if (g.edge(p, q) == kInf) continue;
      out[static_cast<size_t>(p) * g.zCount + q] = g.edge(p, q);
    }
  }
  return out;
}

// ------------------------------------------------------------------ min-plus
// M_k[p][q] = cost of an exact k edge walk from p to q, M_0 = identity.  Values are
// int64 with kInf64 for absent walks; no modulo is applied, so two walks with the same
// edge count but different net displacement are merged here, which is exactly what the
// pair demonstration below shows.
std::vector<int64_t> minPlusIdentity(int n) {
  std::vector<int64_t> m(static_cast<size_t>(n) * n, kInf64);
  for (int p = 0; p < n; ++p) m[static_cast<size_t>(p) * n + p] = 0;
  return m;
}

std::vector<int64_t> minPlusProduct(const std::vector<int64_t>& left,
                                    const std::vector<int64_t>& right, int n) {
  std::vector<int64_t> out(static_cast<size_t>(n) * n, kInf64);
  for (int p = 0; p < n; ++p) {
    for (int r = 0; r < n; ++r) {
      const int64_t l = left[static_cast<size_t>(p) * n + r];
      if (l >= kInf64) continue;
      for (int q = 0; q < n; ++q) {
        const int64_t rightValue = right[static_cast<size_t>(r) * n + q];
        if (rightValue >= kInf64) continue;
        const int64_t candidate = l + rightValue;
        int64_t& slot = out[static_cast<size_t>(p) * n + q];
        if (candidate < slot) slot = candidate;
      }
    }
  }
  return out;
}

// One exact identity check M(k+c) = M(k) + c*lambda with lambda = num/den, compared
// after multiplying by den so no rounding is involved: den*M(k+c) == den*M(k) + c*num.
struct IdentityCheck {
  bool holds = false;
  long long elements = 0;
  long long infinitePairs = 0;
  long long mismatches = 0;
};

IdentityCheck checkIdentity(const std::vector<int64_t>& later, const std::vector<int64_t>& earlier,
                            int n, int64_t c, const Frac& lambda) {
  IdentityCheck result;
  if (later.size() != static_cast<size_t>(n) * n || earlier.size() != static_cast<size_t>(n) * n) {
    // A missing matrix must never pass as an identity.
    result.holds = false;
    ++result.mismatches;
    return result;
  }
  result.holds = true;
  for (size_t i = 0; i < later.size(); ++i) {
    const int64_t a = later[i];
    const int64_t b = earlier[i];
    if (a >= kInf64 && b >= kInf64) {
      ++result.infinitePairs;
      continue;
    }
    ++result.elements;
    if (a >= kInf64 || b >= kInf64) {
      ++result.mismatches;
      result.holds = false;
      continue;
    }
    const __int128 left = static_cast<__int128>(lambda.den) * a;
    const __int128 right = static_cast<__int128>(lambda.den) * b + static_cast<__int128>(c) * lambda.num;
    if (left != right) {
      ++result.mismatches;
      result.holds = false;
    }
  }
  return result;
}

// ------------------------------------------------------------------ part A
struct Witness {
  int z = -1;
  int dx = 0, dy = 0;
  int loopCost = kInf;
  int64_t perUnit = 0;   // loopCost * (S / |displacement|), the corner slope magnitude
  bool divides = false;  // S is an exact multiple of the displacement
  std::string port;
};

Witness pickWitness(const Quotient& g, bool horizontal, int sign) {
  Witness best;
  for (int z = 0; z < g.zCount; ++z) {
    const int d = horizontal ? g.vx[z] : g.vy[z];
    const int other = horizontal ? g.vy[z] : g.vx[z];
    if (other != 0 || d == 0) continue;
    if ((d > 0) != (sign > 0)) continue;
    const int loop = g.edge(z, z);
    if (loop == kInf) continue;
    const bool divides = g.S % std::abs(d) == 0;
    const int64_t perUnit = divides ? static_cast<int64_t>(loop) * (g.S / std::abs(d))
                                    : static_cast<int64_t>(loop) * g.S / std::abs(d);
    if (best.z < 0 || perUnit < best.perUnit) {
      best.z = z;
      best.dx = g.vx[z];
      best.dy = g.vy[z];
      best.loopCost = loop;
      best.perUnit = perUnit;
      best.divides = divides;
      best.port = g.name(z);
    }
  }
  return best;
}

std::string witnessJson(const Witness& w) {
  Jw jw;
  if (w.z < 0) {
    jw.str("status", "no self loop in this direction");
    return "{" + jw.text() + "}";
  }
  jw.num("z_index", w.z);
  jw.str("port", w.port);
  jw.num("dx", w.dx);
  jw.num("dy", w.dy);
  jw.num("self_loop_cost", w.loopCost);
  jw.num("scaled_cost_per_unit", w.perUnit);
  jw.flag("S_divides_displacement", w.divides);
  return "{" + jw.text() + "}";
}

struct PartA {
  std::string json;
  std::vector<std::pair<int, int>> corners;  // (a, b) per quadrant, production order
  std::vector<BfResult> bfs;
  std::vector<KarpResult> karpReduced;
  KarpResult karpOriginal;
  bool strong = false;
  int failures = 0;
};

PartA runPartA(const Architecture& arch, const Quotient& g1, const Quotient& g2) {
  PartA out;
  // The four axial self loops define the bounding rectangle of feasible slopes.
  const Witness wxPlus = pickWitness(g1, true, 1);
  const Witness wxMinus = pickWitness(g1, true, -1);
  const Witness wyPlus = pickWitness(g1, false, 1);
  const Witness wyMinus = pickWitness(g1, false, -1);
  if (wxPlus.z < 0 || wxMinus.z < 0 || wyPlus.z < 0 || wyMinus.z < 0) {
    ++out.failures;
  }
  // A self loop span that does not divide S would make the integer slope wrong; that is a
  // reported failure, not a silent truncation.
  if (!wxPlus.divides || !wxMinus.divides || !wyPlus.divides || !wyMinus.divides) {
    ++out.failures;
  }
  // Karp's premise comes first: without strong connectivity the related items stop here.
  out.strong = stronglyConnected(g1);
  if (!out.strong) ++out.failures;
  // Quadrant order (E,N), (E,S), (W,N), (W,S) matches the production.
  const int signX[4] = {1, 1, -1, -1};
  const int signY[4] = {1, -1, 1, -1};
  for (int q = 0; q < 4; ++q) {
    const int a = signX[q] * static_cast<int>(signX[q] > 0 ? wxPlus.perUnit : wxMinus.perUnit);
    const int b = signY[q] * static_cast<int>(signY[q] > 0 ? wyPlus.perUnit : wyMinus.perUnit);
    out.corners.push_back({a, b});
    BfResult bf = bellmanFord(g1, a, b);
    if (!bf.feasible) ++out.failures;
    out.bfs.push_back(bf);
    if (bf.feasible && out.strong) {
      out.karpReduced.push_back(karp(g1.zCount, weightsOf(g1, a, b, true, bf.h)));
      // A corner is feasible exactly when its reduced weights are nonnegative; the
      // witness self loop has reduced weight zero, so lambda must be exactly zero.
      if (!out.karpReduced.back().ok || out.karpReduced.back().lambda.num != 0) ++out.failures;
    } else {
      KarpResult failed;
      failed.error = out.strong ? "corner infeasible, Karp skipped"
                                : "not strongly connected, Karp stopped for this item";
      out.karpReduced.push_back(failed);
    }
  }
  if (out.strong) {
    out.karpOriginal = karp(g1.zCount, plainWeights(g1));
    if (!out.karpOriginal.ok) ++out.failures;
  } else {
    out.karpOriginal.error = "not strongly connected: Karp stopped for this item";
  }

  // Multiplication by m scales the moduli, the least common multiple, the corner slopes
  // and the potentials by exactly m; the probe checks that on its own construction so no
  // second production table is needed.
  int scalingMismatches = 0;
  for (int q = 0; q < 4; ++q) {
    const int a2 = g2.S / g1.S * out.corners[q].first;
    const int b2 = g2.S / g1.S * out.corners[q].second;
    const BfResult bf2 = bellmanFord(g2, a2, b2);
    if (!bf2.feasible) ++scalingMismatches;
    for (int z = 0; z < g1.zCount; ++z) {
      if (bf2.h[z] != g2.S / g1.S * out.bfs[q].h[z]) ++scalingMismatches;
    }
  }
  if (scalingMismatches != 0) ++out.failures;

  // Four points outside the rectangle, one scaled unit beyond each boundary.
  std::vector<std::string> outside;
  struct OutsideCase {
    int a, b;
    const Witness* witness;
    const char* label;
  };
  const OutsideCase cases[4] = {
      {out.corners[0].first + 1, out.corners[0].second, &wxPlus, "a above the +x boundary"},
      {out.corners[2].first - 1, out.corners[2].second, &wxMinus, "a below the -x boundary"},
      {out.corners[0].first, out.corners[0].second + 1, &wyPlus, "b above the +y boundary"},
      {out.corners[1].first, out.corners[1].second - 1, &wyMinus, "b below the -y boundary"},
  };
  for (const OutsideCase& item : cases) {
    Jw jw;
    jw.str("case", item.label);
    jw.num("a", item.a);
    jw.num("b", item.b);
    if (item.witness->z >= 0) {
      const int64_t reduced = g1.weight(item.witness->z, item.witness->z, item.a, item.b);
      jw.num("witness_self_loop_reduced_weight", reduced);
      jw.flag("witness_self_loop_negative", reduced < 0);
      if (reduced >= 0) ++out.failures;
    }
    const KarpResult inside = karp(g1.zCount, weightsOf(g1, item.a, item.b, false, {}));
    if (inside.ok) {
      jw.raw("karp_lambda", fracText(inside.lambda));
      jw.flag("karp_negative", compareFrac(inside.lambda, makeFrac(0, 1)) < 0);
      if (compareFrac(inside.lambda, makeFrac(0, 1)) >= 0) ++out.failures;
    } else {
      jw.str("karp_error", inside.error);
      ++out.failures;
    }
    outside.push_back("{" + jw.text() + "}");
  }

  // Production cross check: the slopes and the potentials of the shipped implementation
  // at multiplier 1 (the only production table this probe instantiates).
  int slopeMismatch = 0;
  int potentialMismatch = 0;
  long long potentialCompared = 0;
  {
    delayest::ResidueEstimator estimator;
    delayest::ResidueTableAccess::prepareGraph(estimator, arch);
    for (int q = 0; q < 4; ++q) {
      if (estimator.slopeA()[q] != out.corners[q].first ||
          estimator.slopeB()[q] != out.corners[q].second) {
        ++slopeMismatch;
      }
      for (int z = 0; z < g1.zCount; ++z) {
        ++potentialCompared;
        if (estimator.potential(q)[z] != out.bfs[q].h[z]) ++potentialMismatch;
      }
    }
  }
  if (slopeMismatch != 0 || potentialMismatch != 0) ++out.failures;

  Jw jw;
  jw.raw("axial_self_loops",
         std::string("{\"+x\": ") + witnessJson(wxPlus) + ", \"-x\": " + witnessJson(wxMinus) +
             ", \"+y\": " + witnessJson(wyPlus) + ", \"-y\": " + witnessJson(wyMinus) + "}");
  std::vector<std::string> cornerJson;
  for (int q = 0; q < 4; ++q) {
    Jw cj;
    cj.num("quadrant", q);
    cj.num("a", out.corners[q].first);
    cj.num("b", out.corners[q].second);
    cj.flag("bellman_ford_feasible", out.bfs[q].feasible);
    cj.num("bellman_ford_rounds", out.bfs[q].rounds);
    cj.num("edges", out.bfs[q].edges);
    cj.num("negative_edges", out.bfs[q].negativeEdges);
    cj.num("min_reduced", out.bfs[q].minReduced);
    cj.num("max_reduced", out.bfs[q].maxReduced);
    cj.num("max_potential", out.bfs[q].h.empty() ? 0 : *std::max_element(out.bfs[q].h.begin(),
                                                                        out.bfs[q].h.end()));
    if (out.karpReduced[q].ok) cj.raw("karp_reduced_lambda", fracText(out.karpReduced[q].lambda));
    cornerJson.push_back("{" + cj.text() + "}");
  }
  jw.raw("corners", "[" + [&] {
           std::string joined;
           for (size_t i = 0; i < cornerJson.size(); ++i) joined += (i ? ", " : "") + cornerJson[i];
           return joined;
         }() + "]");
  jw.flag("strongly_connected", out.strong);
  jw.raw("karp_original_lambda", fracText(out.karpOriginal.lambda));
  jw.num("karp_original_witness_node", out.karpOriginal.witnessNode);
  jw.num("karp_reachable_nodes", out.karpOriginal.reachableNodes);
  jw.num("karp_unreachable_nodes", out.karpOriginal.unreachableNodes);
  jw.raw("outside_points", "[" + [&] {
           std::string joined;
           for (size_t i = 0; i < outside.size(); ++i) joined += (i ? ", " : "") + outside[i];
           return joined;
         }() + "]");
  jw.num("multiplier_scaling_mismatches", scalingMismatches);
  jw.num("production_slope_mismatches", slopeMismatch);
  jw.num("production_potential_mismatches", potentialMismatch);
  jw.num("production_potential_compared", potentialCompared);
  jw.num("failures", out.failures);
  out.json = "{" + jw.text() + "}";
  return out;
}

// ------------------------------------------------------------------ part C
// The corner potentials bound the reachable displacement of any walk whose cost is at
// most the budget: a*dx + b*dy <= S*C + h[source] - h[target] <= S*budget + h[source] -
// min h.  Intersecting the four corner half planes gives a finite rectangle, so the
// infinite displacement graph can be enumerated exactly inside the budget.  A state
// that is inside the budget but outside the rectangle is a bound error and fails the
// part; nothing is pruned silently.
struct Bounds {
  long long dxMin = 0, dxMax = 0, dyMin = 0, dyMax = 0;
  long long potentialSpread = 0;
  int a = 0, b = 0;  // |corner| magnitudes
  long long estimatedStates = 0;
};

struct Rect {
  long long dxMin = 0, dxMax = 0, dyMin = 0, dyMax = 0;
};

// Safe displacement rectangle from the smallest positive slope magnitudes and the
// potential derived right hand side; used by deriveBounds and by the self check with an
// asymmetric slope example.
Rect rectFromConstants(long long aMin, long long bMin, long long r) {
  Rect rect;
  if (aMin <= 0 || bMin <= 0) return rect;
  rect.dxMax = r / aMin;
  rect.dxMin = -rect.dxMax;
  rect.dyMax = r / bMin;
  rect.dyMin = -rect.dyMax;
  return rect;
}

Bounds deriveBounds(const Quotient& g, const PartA& partA, int budget, int sourceZ) {
  Bounds bounds;
  long long aMin = 0, bMin = 0, r = 0;
  for (int q = 0; q < 4; ++q) {
    if (!partA.bfs[q].feasible) return bounds;
    const long long a = std::abs(partA.corners[q].first);
    const long long b = std::abs(partA.corners[q].second);
    if (a > 0 && (aMin == 0 || a < aMin)) aMin = a;
    if (b > 0 && (bMin == 0 || b < bMin)) bMin = b;
    const auto minPotential = std::min_element(partA.bfs[q].h.begin(), partA.bfs[q].h.end());
    const long long candidate =
        static_cast<long long>(g.S) * budget + partA.bfs[q].h[sourceZ] - *minPotential;
    r = std::max(r, candidate);
    bounds.potentialSpread = std::max(bounds.potentialSpread,
                                      static_cast<long long>(*std::max_element(partA.bfs[q].h.begin(),
                                                                               partA.bfs[q].h.end())) -
                                          *minPotential);
  }
  // North and south slopes are not symmetric (this architecture has 635 north and 625
  // south at S=60), so the safe rectangle uses the smallest positive |a| and |b| over the
  // corners together with R = max_q (S*budget + h_q[source] - min h_q).  For the dx bound
  // the corner whose a sign matches dx makes the b term nonnegative, and the same argument
  // gives the dy bound, so the rectangle contains every state with cost <= budget.
  if (aMin == 0 || bMin == 0) return bounds;
  bounds.a = static_cast<int>(aMin);
  bounds.b = static_cast<int>(bMin);
  const Rect rect = rectFromConstants(aMin, bMin, r);
  bounds.dxMin = rect.dxMin;
  bounds.dxMax = rect.dxMax;
  bounds.dyMin = rect.dyMin;
  bounds.dyMax = rect.dyMax;
  bounds.estimatedStates = (bounds.dxMax - bounds.dxMin + 1) * (bounds.dyMax - bounds.dyMin + 1) *
                           g.zCount;
  return bounds;
}

struct InfiniteSearch {
  std::vector<int64_t> dist;  // flat, ((dx - dxMin) * dySpan + (dy - dyMin)) * zCount + z
  long long dxMin = 0, dyMin = 0, dxSpan = 0, dySpan = 0;
  int zCount = 0;
  long long settled = 0;
  long long boundErrors = 0;
  long long relaxed = 0;
  double seconds = 0.0;

  bool inRange(long long dx, long long dy) const {
    return dx >= dxMin && dx < dxMin + dxSpan && dy >= dyMin && dy < dyMin + dySpan;
  }
  long long index(int z, long long dx, long long dy) const {
    return ((dx - dxMin) * dySpan + (dy - dyMin)) * zCount + z;
  }
  int64_t value(int z, long long dx, long long dy) const {
    if (!inRange(dx, dy)) return kInf64;
    const long long i = index(z, dx, dy);
    return i >= 0 && i < static_cast<long long>(dist.size()) ? dist[i] : kInf64;
  }
  bool has(int z, long long dx, long long dy) const { return value(z, dx, dy) < kInf64; }
  // Read only view of the settled states, in the (key, cost) shape the report loops use.
  std::vector<std::pair<std::tuple<int, int, int>, int64_t>> entries() const {
    std::vector<std::pair<std::tuple<int, int, int>, int64_t>> out;
    for (long long dx = dxMin; dx < dxMin + dxSpan; ++dx) {
      for (long long dy = dyMin; dy < dyMin + dySpan; ++dy) {
        for (int z = 0; z < zCount; ++z) {
          const int64_t cost = value(z, dx, dy);
          if (cost >= kInf64) continue;
          out.push_back({{z, static_cast<int>(dx), static_cast<int>(dy)}, cost});
        }
      }
    }
    return out;
  }
};

InfiniteSearch infiniteDijkstra(const Quotient& g, int sourceZ, int budget, const Bounds& bounds) {
  InfiniteSearch search;
  search.dxMin = bounds.dxMin;
  search.dyMin = bounds.dyMin;
  search.dxSpan = bounds.dxMax - bounds.dxMin + 1;
  search.dySpan = bounds.dyMax - bounds.dyMin + 1;
  search.zCount = g.zCount;
  search.dist.assign(static_cast<size_t>(search.dxSpan) * search.dySpan * g.zCount, kInf64);
  const double started = now();
  using Entry = std::tuple<int64_t, int, int, int>;
  std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
  search.dist[search.index(sourceZ, 0, 0)] = 0;
  queue.emplace(0, sourceZ, 0, 0);
  while (!queue.empty()) {
    const Entry top = queue.top();
    queue.pop();
    const int64_t cost = std::get<0>(top);
    const int z = std::get<1>(top);
    const int dx = std::get<2>(top);
    const int dy = std::get<3>(top);
    if (search.value(z, dx, dy) != cost) continue;
    ++search.settled;
    if (!search.inRange(dx, dy)) ++search.boundErrors;
    for (int q = 0; q < g.zCount; ++q) {
      if (g.edge(z, q) == kInf) continue;
      const int64_t next = cost + g.edge(z, q);
      if (next > budget) continue;
      ++search.relaxed;
      const int nx = dx + g.vx[z];
      const int ny = dy + g.vy[z];
      if (!search.inRange(nx, ny)) {
        // Inside the budget but outside the derived rectangle: a bound error, reported
        // and never silently pruned.
        ++search.boundErrors;
        continue;
      }
      const long long i = search.index(q, nx, ny);
      if (next < search.dist[i]) {
        search.dist[i] = next;
        queue.emplace(next, q, nx, ny);
      }
    }
  }
  search.seconds = now() - started;
  return search;
}

// Lower bound from the corner potentials for a fixed source and target:
//   L = max_q (a_q*dx + b_q*dy + h_q[target] - h_q[source]) / S <= exact.
Frac lowerBound(const Quotient& g, const PartA& partA, int sourceZ, int targetZ, int dx, int dy) {
  Frac best = makeFrac(0, 1);
  bool first = true;
  for (int q = 0; q < 4; ++q) {
    if (!partA.bfs[q].feasible) continue;
    const int64_t value = static_cast<int64_t>(partA.corners[q].first) * dx +
                          static_cast<int64_t>(partA.corners[q].second) * dy +
                          partA.bfs[q].h[targetZ] - partA.bfs[q].h[sourceZ];
    const Frac candidate = makeFrac(value, g.S);
    if (first || compareFrac(candidate, best) > 0) {
      best = candidate;
      first = false;
    }
  }
  return best;
}

// One source table per multiplier: mx*my*zCount distances under the corner reduced
// costs, seeded at (residue 0, sourceZ).  This is the production construction for a
// single source, so no 368 source table is allocated.
struct SourceTable {
  int multiplier = 1;
  int mx = 0, my = 0, S = 0;
  std::vector<std::vector<int64_t>> dist;  // [quadrant][residue*zCount + z]
  long long entries = 0;
  double seconds = 0.0;
};

SourceTable buildSourceTable(const Quotient& g1, const PartA& partA, int multiplier, int sourceZ) {
  SourceTable table;
  table.multiplier = multiplier;
  table.mx = g1.mx * multiplier;
  table.my = g1.my * multiplier;
  table.S = table.mx / gcdInt(table.mx, table.my) * table.my;
  const int residues = table.mx * table.my;
  const double started = now();
  table.dist.assign(4, std::vector<int64_t>(static_cast<size_t>(residues) * g1.zCount, kInf64));
  for (int q = 0; q < 4; ++q) {
    if (!partA.bfs[q].feasible) continue;
    // The reduced weight of edge p -> q scales by the multiplier, so the mult m graph
    // uses m times the mult 1 reduced cost.
    std::vector<int64_t> reduced(static_cast<size_t>(g1.zCount) * g1.zCount, kInf64);
    for (int p = 0; p < g1.zCount; ++p) {
      for (int r = 0; r < g1.zCount; ++r) {
        if (g1.edge(p, r) == kInf) continue;
        reduced[static_cast<size_t>(p) * g1.zCount + r] =
            multiplier * (g1.weight(p, r, partA.corners[q].first, partA.corners[q].second) +
                          partA.bfs[q].h[p] - partA.bfs[q].h[r]);
      }
    }
    std::vector<int64_t>& dist = table.dist[q];
    const int seed = sourceZ;
    dist[seed] = 0;
    std::priority_queue<std::pair<int64_t, int>, std::vector<std::pair<int64_t, int>>,
                        std::greater<std::pair<int64_t, int>>>
        queue;
    queue.emplace(0, seed);
    while (!queue.empty()) {
      const auto [cost, state] = queue.top();
      queue.pop();
      if (dist[state] != cost) continue;
      const int z = state % g1.zCount;
      const int residue = state / g1.zCount;
      const int nx = ((residue % table.mx + g1.vx[z]) % table.mx + table.mx) % table.mx;
      const int ny = ((residue / table.mx + g1.vy[z]) % table.my + table.my) % table.my;
      const int shifted = nx + table.mx * ny;
      for (int r = 0; r < g1.zCount; ++r) {
        if (reduced[static_cast<size_t>(z) * g1.zCount + r] >= kInf64) continue;
        const int64_t next = cost + reduced[static_cast<size_t>(z) * g1.zCount + r];
        const int target = shifted * g1.zCount + r;
        if (next < dist[target]) {
          dist[target] = next;
          queue.emplace(next, target);
        }
      }
    }
  }
  table.entries = 4LL * residues * g1.zCount;  // four quadrants
  table.seconds = now() - started;
  return table;
}

// R_m(s, t, dx, dy) = max_q (a_m,q*dx + b_m,q*dy + dist_m,q[residue, t]) / S_m.
struct BoundValue {
  Frac value;
  bool valid = false;
};

// R_m(s, t, dx, dy) = max_q (m*a*dx + m*b*dy + dist_reduced - m*h[source] + m*h[target]) / S_m
// The linear term and the potential difference belong to the production query formula and
// must be added back.  All quadrants infinite is a real failure, not a zero.
BoundValue sourceTableValue(const SourceTable& table, const Quotient& g1, const PartA& partA,
                            int sourceZ, int targetZ, int dx, int dy) {
  BoundValue best;
  const int rx = ((dx % table.mx) + table.mx) % table.mx;
  const int ry = ((dy % table.my) + table.my) % table.my;
  const int residue = rx + table.mx * ry;
  const int64_t m = table.multiplier;
  for (int q = 0; q < 4; ++q) {
    if (table.dist[q].empty() || !partA.bfs[q].feasible) continue;
    const int64_t reduced = table.dist[q][static_cast<size_t>(residue) * g1.zCount + targetZ];
    if (reduced >= kInf64) continue;
    const int64_t value = m * partA.corners[q].first * dx + m * partA.corners[q].second * dy +
                          reduced - m * partA.bfs[q].h[sourceZ] + m * partA.bfs[q].h[targetZ];
    const Frac candidate = makeFrac(value, table.S);
    if (!best.valid || compareFrac(candidate, best.value) > 0) {
      best.value = candidate;
      best.valid = true;
    }
  }
  return best;
}

const int kBandEdges[8] = {0, 1, 13, 25, 51, 101, 301, 1073741824};

std::string bandName(int band) {
  static const char* names[7] = {"0", "1-12", "13-24", "25-50", "51-100", "101-300", "301+"};
  return names[band];
}

struct PartC {
  std::string json;
  int failures = 0;
};

PartC runPartC(const Quotient& g1, const PartA& partA, int budget) {
  PartC out;
  // One horizontal and one vertical source: the Net displacement decides the axis.
  int horizontal = -1, vertical = -1;
  for (int z = 0; z < g1.zCount; ++z) {
    if (horizontal < 0 && g1.vy[z] == 0 && g1.vx[z] != 0 && g1.edge(z, z) != kInf) horizontal = z;
    if (vertical < 0 && g1.vx[z] == 0 && g1.vy[z] != 0 && g1.edge(z, z) != kInf) vertical = z;
  }
  if (horizontal < 0 || vertical < 0) ++out.failures;

  std::vector<std::string> sourceJson;
  for (int sourceZ : {horizontal, vertical}) {
    if (sourceZ < 0) continue;
    const Bounds bounds = deriveBounds(g1, partA, budget, sourceZ);
    Jw jw;
    jw.num("source_z", sourceZ);
    jw.str("source_port", g1.name(sourceZ));
    jw.num("vx", g1.vx[sourceZ]);
    jw.num("vy", g1.vy[sourceZ]);
    // Report the estimate before the search: this is the budget/state count report.
    if (bounds.estimatedStates > 40000000LL) {
      jw.flag("resource_estimate_too_high", true);
      jw.num("budget_used", 800);
    } else {
      jw.flag("resource_estimate_too_high", false);
      jw.num("budget_used", budget);
    }
    const int usedBudget = bounds.estimatedStates > 40000000LL ? 800 : budget;
    const Bounds used = usedBudget == budget ? bounds : deriveBounds(g1, partA, usedBudget, sourceZ);
    // The rectangle that the search actually used, for the budget that was actually used.
    jw.num("estimated_states_before_search", used.estimatedStates);
    jw.raw("rectangle", std::string("{\"dx_min\": ") + std::to_string(used.dxMin) +
                            ", \"dx_max\": " + std::to_string(used.dxMax) +
                            ", \"dy_min\": " + std::to_string(used.dyMin) +
                            ", \"dy_max\": " + std::to_string(used.dyMax) +
                            ", \"abs_corner\": [" + std::to_string(used.a) + ", " +
                            std::to_string(used.b) + "], \"potential_spread\": " +
                            std::to_string(used.potentialSpread) + "}");
    const InfiniteSearch search = infiniteDijkstra(g1, sourceZ, usedBudget, used);
    jw.num("settled_states", search.settled);
    jw.num("relaxations", search.relaxed);
    jw.num("bound_errors", search.boundErrors);
    jw.real("search_seconds", search.seconds, 3);
    jw.num("settled_in_rectangle", search.settled);
    if (search.boundErrors != 0) ++out.failures;

    // exact - L per Manhattan band over every reachable Z target.
    std::vector<long long> counts(7, 0), negativeSlack(7, 0);
    std::vector<double> minSlack(7, 1e18), maxSlack(7, -1e18);
    for (const auto& entry : search.entries()) {
      const int targetZ = std::get<0>(entry.first);
      const int dx = std::get<1>(entry.first);
      const int dy = std::get<2>(entry.first);
      const int manhattan = std::abs(dx) + std::abs(dy);
      int band = 6;
      for (int i = 0; i < 7; ++i) {
        if (manhattan >= kBandEdges[i] && manhattan < kBandEdges[i + 1]) {
          band = i;
          break;
        }
      }
      const Frac lower = lowerBound(g1, partA, sourceZ, targetZ, dx, dy);
      const Frac slack = makeFrac(entry.second * lower.den - lower.num, lower.den);
      const double slackValue = static_cast<double>(slack.num) / slack.den;
      ++counts[band];
      if (slack.num < 0) ++negativeSlack[band];
      minSlack[band] = std::min(minSlack[band], slackValue);
      maxSlack[band] = std::max(maxSlack[band], slackValue);
    }
    std::vector<std::string> bandJson;
    for (int i = 0; i < 7; ++i) {
      if (counts[i] == 0) continue;
      Jw bj;
      bj.str("band", bandName(i));
      bj.num("states", counts[i]);
      bj.num("negative_slack", negativeSlack[i]);
      bj.real("min_exact_minus_L", minSlack[i], 6);
      bj.real("max_exact_minus_L", maxSlack[i], 6);
      bandJson.push_back("{" + bj.text() + "}");
      if (negativeSlack[i] != 0) ++out.failures;
    }
    jw.raw("bands", "[" + [&] {
             std::string joined;
             for (size_t i = 0; i < bandJson.size(); ++i) joined += (i ? ", " : "") + bandJson[i];
             return joined;
           }() + "]");

    // Axial ray with source = target: the witness self loop displacement is the period,
    // and an adjacent increment equals the loop cost when the ray walks that loop.
    // The ray follows the source's own Net axis and direction.
    const bool rayHorizontal = g1.vx[sourceZ] != 0;
    const int raySign = rayHorizontal ? (g1.vx[sourceZ] > 0 ? 1 : -1) : (g1.vy[sourceZ] > 0 ? 1 : -1);
    const Witness ray = pickWitness(g1, rayHorizontal, raySign);
    std::vector<std::string> rayJson;
    if (ray.z >= 0 && (ray.dx != 0 || ray.dy != 0)) {
      for (int k = 1; k <= 40; ++k) {
        const int dx = ray.dx * k, dy = ray.dy * k;
        const int64_t found = search.value(sourceZ, dx, dy);
        if (found >= kInf64) break;
        const int64_t previous = search.value(sourceZ, dx - ray.dx, dy - ray.dy);
        if (previous >= kInf64) continue;
        Jw rj;
        rj.num("k", k);
        rj.num("dx", dx);
        rj.num("dy", dy);
        rj.num("exact", found);
        rj.num("increment", found - previous);
        rj.num("period_cost", ray.loopCost);
        rj.flag("increment_equals_period_cost", found - previous == ray.loopCost);
        rayJson.push_back("{" + rj.text() + "}");
      }
    }
    jw.raw("axial_ray", "[" + [&] {
             std::string joined;
             for (size_t i = 0; i < rayJson.size(); ++i) joined += (i ? ", " : "") + rayJson[i];
             return joined;
           }() + "]");
    jw.num("ray_points", static_cast<long long>(rayJson.size()));
    jw.str("ray_witness_port", ray.z >= 0 ? g1.name(ray.z) : std::string());
    jw.num("ray_witness_dx", ray.dx);
    jw.num("ray_witness_dy", ray.dy);
    jw.num("ray_increment_matches", [&] {
      long long matches = 0;
      for (const std::string& item : rayJson) {
        if (item.find("\"increment_equals_period_cost\": true") != std::string::npos) ++matches;
      }
      return matches;
    }());

    // L <= R1 <= R2 <= exact for the same source over the reachable targets.
    std::vector<long long> boundViolations(7, 0), r1r2Violations(7, 0), pairCounts(7, 0);
    std::vector<double> minExactR1(7, 1e18), maxExactR1(7, -1e18);
    std::vector<double> minExactR2(7, 1e18), maxExactR2(7, -1e18);
    SourceTable table1, table2;
    table1 = buildSourceTable(g1, partA, 1, sourceZ);
    table2 = buildSourceTable(g1, partA, 2, sourceZ);
    jw.raw("source_table_entries", std::string("[") + std::to_string(table1.entries) + ", " +
                                       std::to_string(table2.entries) + "]");
    jw.real("source_table_seconds", table1.seconds + table2.seconds, 3);
    for (const auto& entry : search.entries()) {
      const int targetZ = std::get<0>(entry.first);
      const int dx = std::get<1>(entry.first);
      const int dy = std::get<2>(entry.first);
      const int manhattan = std::abs(dx) + std::abs(dy);
      int band = 6;
      for (int i = 0; i < 7; ++i) {
        if (manhattan >= kBandEdges[i] && manhattan < kBandEdges[i + 1]) {
          band = i;
          break;
        }
      }
      ++pairCounts[band];
      const Frac lower = lowerBound(g1, partA, sourceZ, targetZ, dx, dy);
      const BoundValue r1 = sourceTableValue(table1, g1, partA, sourceZ, targetZ, dx, dy);
      const BoundValue r2 = sourceTableValue(table2, g1, partA, sourceZ, targetZ, dx, dy);
      if (!r1.valid || !r2.valid) {
        // Every quadrant infinite at a point that the Dijkstra reached: a real failure.
        ++boundViolations[band];
        continue;
      }
      const Frac exact = makeFrac(entry.second, 1);
      if (compareFrac(lower, r1.value) > 0 || compareFrac(r1.value, exact) > 0) ++boundViolations[band];
      if (compareFrac(r1.value, r2.value) > 0 || compareFrac(r2.value, exact) > 0) {
        ++r1r2Violations[band];
      }
      const double gap = static_cast<double>(entry.second) -
                         static_cast<double>(r1.value.num) / r1.value.den;
      minExactR1[band] = std::min(minExactR1[band], gap);
      maxExactR1[band] = std::max(maxExactR1[band], gap);
      const double gap2 = static_cast<double>(entry.second) -
                          static_cast<double>(r2.value.num) / r2.value.den;
      minExactR2[band] = std::min(minExactR2[band], gap2);
      maxExactR2[band] = std::max(maxExactR2[band], gap2);
    }
    std::vector<std::string> boundJson;
    for (int i = 0; i < 7; ++i) {
      if (pairCounts[i] == 0) continue;
      Jw bj;
      bj.str("band", bandName(i));
      bj.num("states", pairCounts[i]);
      bj.num("violations_L_R1_R2_exact", boundViolations[i]);
      bj.num("violations_R1_R2_exact", r1r2Violations[i]);
      bj.real("min_exact_minus_R1", minExactR1[i], 6);
      bj.real("max_exact_minus_R1", maxExactR1[i], 6);
      bj.real("min_exact_minus_R2", minExactR2[i], 6);
      bj.real("max_exact_minus_R2", maxExactR2[i], 6);
      boundJson.push_back("{" + bj.text() + "}");
      if (boundViolations[i] != 0 || r1r2Violations[i] != 0) ++out.failures;
    }
    jw.raw("bounds_by_band", "[" + [&] {
             std::string joined;
             for (size_t i = 0; i < boundJson.size(); ++i) joined += (i ? ", " : "") + boundJson[i];
             return joined;
           }() + "]");
    sourceJson.push_back("{" + jw.text() + "}");
  }
  Jw jw;
  jw.num("budget", budget);
  jw.raw("sources", "[" + [&] {
           std::string joined;
           for (size_t i = 0; i < sourceJson.size(); ++i) joined += (i ? ", " : "") + sourceJson[i];
           return joined;
         }() + "]");
  jw.num("failures", out.failures);
  jw.str("scope", "observations inside the budget on the infinite nominal displacement "
                  "graph; not a global periodicity or bounded error proof");
  out.json = "{" + jw.text() + "}";
  return out;
}

// Small independent self checks of the algorithms used above: a fractional cycle mean, the
// unreachable node handling, a negative cycle, the asymmetric slope bounds and a known two
// step min-plus value.  Each failure is counted so it reaches the JSON and the exit code.
std::string selfCheck(const Quotient& g1, const PartA& partA, int* failures) {
  Jw jw;
  auto check = [&](const char* name, bool ok) {
    jw.flag(name, ok);
    if (!ok) ++*failures;
  };
  // Two node cycle with weights 1 and 2: the minimum cycle mean is 3/2.
  {
    std::vector<int64_t> w(4, kInf64);
    w[1] = 1;   // 0 -> 1
    w[2] = 2;   // 1 -> 0
    const KarpResult r = karp(2, w);
    check("fractional_cycle_mean", r.ok && compareFrac(r.lambda, makeFrac(3, 2)) == 0);
  }
  // A zero self loop plus an unreachable node: lambda 0 and one unreachable node.
  {
    std::vector<int64_t> w(4, kInf64);
    w[0] = 0;
    const KarpResult r = karp(2, w);
    check("unreachable_node", r.ok && r.unreachableNodes == 1 &&
                                  compareFrac(r.lambda, makeFrac(0, 1)) == 0);
  }
  // A self loop of weight -1 gives lambda -1.
  {
    std::vector<int64_t> w(1, -1);
    const KarpResult r = karp(1, w);
    check("negative_cycle", r.ok && compareFrac(r.lambda, makeFrac(-1, 1)) == 0);
  }
  // Asymmetric slopes through deriveBounds: x 750, north 635, south 625, S = 60 and
  // budget 1200 give R = 72000, so dy = -115 is inside and dy = -116 is outside.
  {
    Quotient synthetic;
    synthetic.zCount = 1;
    synthetic.S = 60;
    PartA syntheticPartA;
    syntheticPartA.corners = {{750, 635}, {750, -625}, {-750, 635}, {-750, -625}};
    for (int q = 0; q < 4; ++q) {
      BfResult bf;
      bf.feasible = true;
      bf.h.assign(1, 0);
      syntheticPartA.bfs.push_back(bf);
    }
    const Bounds bounds = deriveBounds(synthetic, syntheticPartA, 1200, 0);
    check("asymmetric_bounds_inside",
          bounds.dxMax == 96 && bounds.dxMin == -96 && bounds.dyMax == 115 && bounds.dyMin == -115);
    check("asymmetric_bounds_outside_116", !(static_cast<long long>(-116) >= bounds.dyMin));
  }
  // Two step min-plus: 0 -> 1 -> 2 costs 5 while 0 -> 1 in two steps is impossible.
  {
    std::vector<int64_t> single(9, kInf64);
    single[1] = 2;  // 0 -> 1
    single[5] = 3;  // 1 -> 2
    const std::vector<int64_t> m2 = minPlusProduct(single, single, 3);
    check("two_step_min_plus", m2[2] == 5 && m2[1] >= kInf64);
  }
  check("real_graph_strongly_connected", partA.strong);
  (void)g1;
  return "{" + jw.text() + "}";
}

std::string readArchDir(int argc, char** argv) {
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::strcmp(argv[i], "--arch") == 0) return argv[i + 1];
  }
  return "doc/eda比赛文件/arch";
}

std::string readStringArg(int argc, char** argv, const char* name) {
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::strcmp(argv[i], name) == 0) return argv[i + 1];
  }
  return "";
}

// ------------------------------------------------------------------ part B
struct PartB {
  std::string json;
  int failures = 0;
};

PartB runPartB(const Quotient& g1, const PartA& partA, int maxSteps, int maxPeriod) {
  PartB out;
  const int n = g1.zCount;
  std::vector<std::string> matrixJson;
  // The original costs plus the four corner reduced weightings.
  struct Case {
    std::string label;
    std::vector<int64_t> single;  // one edge weights
    Frac lambda;
  };
  std::vector<Case> cases;
  cases.push_back({"original", plainWeights(g1), partA.karpOriginal.lambda});
  for (int q = 0; q < 4; ++q) {
    if (!partA.karpReduced[q].ok) continue;
    cases.push_back({"corner_" + std::to_string(q),
                     weightsOf(g1, partA.corners[q].first, partA.corners[q].second, true,
                               partA.bfs[q].h),
                     partA.karpReduced[q].lambda});
  }
  for (const Case& item : cases) {
    // Ring of the most recent matrices so a period up to maxPeriod can be tested.
    const int ringSize = maxPeriod + 1;
    std::vector<std::vector<int64_t>> ring(ringSize);
    ring[0] = minPlusIdentity(n);
    int firstK = -1, firstC = -1;
    int k0 = -1;  // the earlier power of the confirmed identity, firstK is the later one
    long long elements = 0, infinitePairs = 0, continuationChecks = 0, continuationHolds = 0;
    bool stoppedEarly = false;
    for (int k = 1; k <= maxSteps; ++k) {
      ring[k % ringSize] = minPlusProduct(ring[(k - 1) % ringSize], item.single, n);
      for (int c = 1; c <= std::min(maxPeriod, k - 1); ++c) {
        const IdentityCheck check =
            checkIdentity(ring[k % ringSize], ring[(k - c) % ringSize], n, c, item.lambda);
        if (check.holds && check.elements > 0) {
          if (firstK < 0) {
            firstK = k;
            firstC = c;
            elements = check.elements;
            infinitePairs = check.infinitePairs;
          }
          break;
        }
      }
      if (firstK >= 0 && k0 < 0) {
        k0 = k - firstC;
        // One exact identity plus the fixed min-plus recurrence (right multiplication by
        // the one edge matrix) implies every later step, so a single next step is kept as
        // the self check instead of walking to the cap.
        ring[(k + 1) % ringSize] = minPlusProduct(ring[k % ringSize], item.single, n);
        const IdentityCheck again =
            checkIdentity(ring[(k + 1) % ringSize], ring[(k + 1 - firstC) % ringSize], n, firstC,
                          item.lambda);
        ++continuationChecks;
        if (again.holds) ++continuationHolds;
        stoppedEarly = true;
        break;
      }
    }
    if (firstK >= 0 && continuationChecks != continuationHolds) ++out.failures;
    Jw jw;
    jw.str("label", item.label);
    jw.raw("lambda", fracText(item.lambda));
    jw.num("first_k", firstK);
    jw.num("earlier_power_k0", k0);
    jw.num("period_c", firstC);
    jw.flag("confirmed", firstK >= 0);
    jw.num("elements_compared", elements);
    jw.num("infinite_pairs", infinitePairs);
    jw.num("continuation_checks", continuationChecks);
    jw.num("continuation_holds", continuationHolds);
    jw.flag("stopped_early", stoppedEarly);
    jw.num("max_steps", maxSteps);
    jw.num("max_period_tested", maxPeriod);
    if (firstK < 0) jw.flag("not_confirmed_in_range", true);
    matrixJson.push_back("{" + jw.text() + "}");
  }

  // One pair with two step paths grouped by their net displacement: M2 alone merges
  // the groups, so the displacement information is lost in the matrix entry.
  std::string pairJson;
  std::string fallbackJson;
  bool pairFound = false;
  const std::vector<int64_t> m2 = minPlusProduct(plainWeights(g1), plainWeights(g1), n);
  for (int p = 0; p < n && !pairFound; ++p) {
    for (int q = 0; q < n && !pairFound; ++q) {
      struct Group {
        int dx = 0, dy = 0;
        int minCost = kInf;
        int r = -1;
      };
      std::vector<Group> groups;
      for (int r = 0; r < n; ++r) {
        if (g1.edge(p, r) == kInf || g1.edge(r, q) == kInf) continue;
        const int dx = g1.vx[p] + g1.vx[r];
        const int dy = g1.vy[p] + g1.vy[r];
        const int cost = g1.edge(p, r) + g1.edge(r, q);
        bool merged = false;
        for (Group& group : groups) {
          if (group.dx == dx && group.dy == dy) {
            if (cost < group.minCost) {
              group.minCost = cost;
              group.r = r;
            }
            merged = true;
            break;
          }
        }
        if (!merged) groups.push_back(Group{dx, dy, cost, r});
      }
      if (groups.size() < 2) continue;
      // Report the pair when the group minima differ, otherwise still report the two
      // displacements and say that the merged value keeps the cheapest one.
      bool different = false;
      for (size_t i = 1; i < groups.size(); ++i) {
        if (groups[i].minCost != groups[0].minCost) different = true;
      }
      Jw jw;
      jw.num("p", p);
      jw.str("p_port", g1.name(p));
      jw.num("q", q);
      jw.str("q_port", g1.name(q));
      std::vector<std::string> groupJson;
      for (const auto& group : groups) {
        Jw gj;
        gj.num("dx", group.dx);
        gj.num("dy", group.dy);
        gj.num("min_cost", group.minCost);
       gj.num("via_r", group.r);
        gj.str("via_r_port", group.r >= 0 ? g1.name(group.r) : std::string());
        groupJson.push_back("{" + gj.text() + "}");
      }
      jw.raw("displacement_groups", "[" + [&] {
               std::string joined;
               for (size_t i = 0; i < groupJson.size(); ++i) joined += (i ? ", " : "") + groupJson[i];
               return joined;
             }() + "]");
      jw.flag("group_minima_differ", different);
      int minGroupCost = kInf;
      for (const Group& group : groups) minGroupCost = std::min(minGroupCost, group.minCost);
      const int64_t direct = m2[static_cast<size_t>(p) * n + q];
      jw.num("matrix_m2_value", direct >= kInf64 ? -1 : static_cast<int>(direct));
      jw.num("min_group_cost", minGroupCost);
      jw.flag("matrix_m2_equals_min_group", direct == static_cast<int64_t>(minGroupCost));
      if (direct != static_cast<int64_t>(minGroupCost)) ++out.failures;
      jw.str("note", "the two step matrix entry M2[p][q] keeps only the cheapest group "
                     "and therefore drops the net displacement of the walk");
      const std::string candidate = "{" + jw.text() + "}";
      if (fallbackJson.empty()) fallbackJson = candidate;
      if (different) {
        pairJson = candidate;
        pairFound = true;
      }
    }
  }
  Jw jw;
  jw.raw("matrices", "[" + [&] {
           std::string joined;
           for (size_t i = 0; i < matrixJson.size(); ++i) joined += (i ? ", " : "") + matrixJson[i];
           return joined;
         }() + "]");
  if (pairFound) jw.raw("pair_demo", pairJson);
  else if (!fallbackJson.empty()) jw.raw("pair_demo", fallbackJson);
  else jw.str("pair_demo", "no pair with two displacement groups found");
  jw.num("failures", out.failures);
  out.json = "{" + jw.text() + "}";
  return out;
}

}  // namespace

int main(int argc, char** argv) {
  const std::string archDir = readArchDir(argc, argv);
  std::string jsonPath = readStringArg(argc, argv, "--json");
  if (jsonPath.empty()) jsonPath = "validation/results/exp26-periodic-theory.json";
  int budget = 1200;
  const std::string budgetArg = readStringArg(argc, argv, "--budget");
  if (!budgetArg.empty()) budget = std::atoi(budgetArg.c_str());
  int maxSteps = 512;
  const std::string stepsArg = readStringArg(argc, argv, "--max-steps");
  if (!stepsArg.empty()) maxSteps = std::atoi(stepsArg.c_str());
  int maxPeriod = 64;
  const std::string periodArg = readStringArg(argc, argv, "--max-period");
  if (!periodArg.empty()) maxPeriod = std::atoi(periodArg.c_str());

  Jw root;
  int failures = 1;
  try {
    Architecture arch;
    arch.load(archDir);
    const double started = now();
    const Quotient g1 = buildQuotient(arch, 1);
    const Quotient g2 = buildQuotient(arch, 2);
    root.num("z_count", g1.zCount);
    root.num("modulus_x", g1.mx);
    root.num("modulus_y", g1.my);
    root.num("scale", g1.S);
    root.str("arch_dir", archDir);
    root.num("budget", budget);
    root.num("max_steps", maxSteps);
    root.num("max_period", maxPeriod);
    root.str("algorithm", "quotient graph: edge p->q is the Net displacement of p plus the Arc "
                          "from the Net landing to q, cost is that Arc only; Gap, Block and the "
                          "finite chip boundary are not modelled");
    const PartA partA = runPartA(arch, g1, g2);
    root.raw("part_a_slopes_and_karp", partA.json);
    int selfFailures = 0;
    root.raw("self_check", selfCheck(g1, partA, &selfFailures));
    const PartB partB = runPartB(g1, partA, maxSteps, maxPeriod);
    root.raw("part_b_consecutive_powers", partB.json);
    const PartC partC = runPartC(g1, partA, budget);
    root.raw("part_c_gap_free_budget", partC.json);
    failures = partA.failures + partB.failures + partC.failures + selfFailures;
    root.num("total_seconds", now() - started);
    root.num("peak_rss_kib", peakRssKib());
    root.flag("single_threaded", true);
    root.num("failures", failures);
    root.str("build_command", "g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o "
                              "build/periodic_theory_probe tests/periodic_theory_probe.cpp "
                              "src/architecture.cpp src/residue_estimator.cpp");
    root.str("run_command", "./build/periodic_theory_probe --arch " + archDir + " --json " +
                            jsonPath + " --budget " + std::to_string(budget));
  } catch (const std::exception& error) {
    root.str("error", error.what());
    root.num("failures", 1);
  }
  const std::string text = "{" + root.text() + "}";
  std::ofstream out(jsonPath);
  if (!out) {
    std::fprintf(stderr, "periodic_theory_probe: cannot write %s\n", jsonPath.c_str());
    return 2;
  }
  out << text << "\n";
  std::printf("%s\n", text.c_str());
  return failures == 0 ? 0 : 1;
}
