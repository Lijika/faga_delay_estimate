// Architecture-only distance fields for the affine-tail research probe.
#include <array>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <stdexcept>
#include <sys/resource.h>
#include <vector>

#include "../../src/architecture.h"
#include "../../src/router.h"

using namespace delayest;
namespace {
constexpr int kInf = 1000000000;
constexpr int kScale = 120;
constexpr std::array<std::array<int, 2>, 4> kSlope{{
    {1500, 1270}, {1500, -1250}, {-1500, 1270}, {-1500, -1250}}};
struct Edge { int to, cost; };
struct Graph {
  std::vector<int> ports, dx, dy;
  std::vector<std::vector<Edge>> edges;
  std::array<std::vector<int>, 4> phi;
  explicit Graph(const Architecture& arch) {
    ports = arch.netSources();
    std::sort(ports.begin(), ports.end());
    std::vector<int> ordinal(arch.portCount(), -1);
    for (size_t p = 0; p < ports.size(); ++p) ordinal[ports[p]] = int(p);
    for (int port : ports) {
      const auto& net = arch.net(arch.netOfOutput(port));
      dx.push_back(net.dx);
      dy.push_back(net.dy);
      assert((net.dx == 0) != (net.dy == 0));
      edges.emplace_back();
      for (const auto& arc : arch.outgoingArcs(net.to)) {
        assert(arc.delay > 0);
        if (ordinal[arc.to] >= 0) edges.back().push_back({ordinal[arc.to], arc.delay});
      }
    }
    for (int k = 0; k < 4; ++k) {
      auto& h = phi[k];
      h.assign(ports.size(), 0);
      for (size_t it = 0; it < ports.size(); ++it) {
        bool changed = false;
        for (size_t p = 0; p < ports.size(); ++p)
          for (auto e : edges[p]) {
            const int v = h[p] + kScale * e.cost - kSlope[k][0] * dx[p] -
                          kSlope[k][1] * dy[p];
            if (h[e.to] > v) { h[e.to] = v; changed = true; }
          }
        if (!changed) break;
        if (it + 1 == ports.size()) throw std::runtime_error("infeasible slope");
      }
      for (size_t p = 0; p < ports.size(); ++p)
        for (auto e : edges[p])
          assert(kScale * e.cost - kSlope[k][0] * dx[p] - kSlope[k][1] * dy[p] +
                 h[p] - h[e.to] >= 0);
    }
  }
};
struct Field {
  int rx, ry, n, width;
  std::vector<int> d;
  std::array<std::array<int64_t, 4>, 4> boundary;
  Field(int x, int y, int ports)
      : rx(x), ry(y), n(ports), width(2 * x + 1),
        d(size_t(width) * (2 * y + 1) * n, kInf) {
    if (d.size() >= size_t(std::numeric_limits<int>::max()))
      throw std::runtime_error("state identifier overflow");
    for (auto& side : boundary) side.fill(int64_t(1) << 60);
  }
  bool inside(int x, int y) const { return std::abs(x) <= rx && std::abs(y) <= ry; }
  int id(int x, int y, int p) const { return ((y + ry) * width + x + rx) * n + p; }
  bool certified(const Graph& g, int x, int y, int p) const {
    int64_t bound = int64_t(1) << 60;
    for (const auto& side : boundary) {
      int64_t best = -(int64_t(1) << 60);
      for (int k = 0; k < 4; ++k)
        best = std::max(best, side[k] + kSlope[k][0] * x + kSlope[k][1] * y +
                                 g.phi[k][p]);
      bound = std::min(bound, best);
    }
    const int value = d[id(x, y, p)];
    return value < kInf && int64_t(kScale) * value <= bound;
  }
};
Field solve(const Graph& g, int source, int rx, int ry, bool binary = false) {
  Field f(rx, ry, int(g.ports.size()));
  RadixFrontier radix;
  radix.clear();
  using Item = std::pair<int, int>;
  std::priority_queue<Item, std::vector<Item>, std::greater<Item>> heap;
  const auto push = [&](int cost, int id) {
    if (binary) heap.emplace(cost, id);
    else radix.push(uint32_t(cost), id);
  };
  f.d[f.id(0, 0, source)] = 0;
  push(0, f.id(0, 0, source));
  while (binary ? !heap.empty() : !radix.empty()) {
    int cost, id;
    if (binary) {
      std::tie(cost, id) = heap.top();
      heap.pop();
    } else {
      const auto entry = radix.top();
      cost = int(entry >> 32);
      id = int(uint32_t(entry));
    }
    if (cost != f.d[id]) continue;
    const int p = id % f.n;
    const int x = (id / f.n) % f.width - rx + g.dx[p];
    const int y = (id / f.n) / f.width - ry + g.dy[p];
    if (!f.inside(x, y)) {
      const int side = x < -rx ? 0 : x > rx ? 1 : y < -ry ? 2 : 3;
      for (auto e : g.edges[p])
        for (int k = 0; k < 4; ++k)
          f.boundary[side][k] = std::min(
              f.boundary[side][k], int64_t(kScale) * (cost + e.cost) -
                  kSlope[k][0] * x - kSlope[k][1] * y - g.phi[k][e.to]);
      continue;
    }
    const int base = f.id(x, y, 0);
    for (auto e : g.edges[p]) {
      const int next = cost + e.cost;
      if (next < f.d[base + e.to]) {
        f.d[base + e.to] = next;
        push(next, base + e.to);
      }
    }
  }
  return f;
}
void selfCheck(const Graph& g) {
  size_t equal = 0, certified = 0;
  for (int p : {0, 32, 80, 128}) {
    const auto small = solve(g, p, 5, 7);
    const auto reference = solve(g, p, 5, 7, true);
    assert(small.d == reference.d && small.boundary == reference.boundary);
    equal += small.d.size();
    const auto large = solve(g, p, 17, 19, true);
    for (int y = -7; y <= 7; ++y)
      for (int x = -5; x <= 5; ++x)
        for (int q = 0; q < small.n; ++q)
          if (small.certified(g, x, y, q)) {
            assert(small.d[small.id(x, y, q)] == large.d[large.id(x, y, q)]);
            ++certified;
          }
  }
  assert(certified > 0);
  std::cout << "{\"heap_equal_states\":" << equal
            << ",\"certified_large_window_checks\":" << certified << "}\n";
}
double cpu() {
  rusage u{};
  getrusage(RUSAGE_SELF, &u);
  return u.ru_utime.tv_sec + u.ru_stime.tv_sec +
         (u.ru_utime.tv_usec + u.ru_stime.tv_usec) * 1e-6;
}
}  // namespace