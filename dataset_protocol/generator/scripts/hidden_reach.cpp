// Offline reachability index for the fixed hidden-suite request domain.
#include "../src/architecture.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using delayest::Architecture;
constexpr uint32_t missing = UINT32_MAX;

static void require(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

template <typename T>
static void writeVector(std::ofstream& out, const std::vector<T>& values) {
  const uint64_t size = values.size();
  out.write(reinterpret_cast<const char*>(&size), sizeof(size));
  out.write(reinterpret_cast<const char*>(values.data()), size * sizeof(T));
  require(bool(out), "index write failed");
}

int main(int argc, char** argv) {
  if (argc != 4) {
    std::fprintf(stderr, "usage: hidden_reach <arch-dir> <index.bin> <report.json>\n");
    return 2;
  }
  try {
    Architecture arch;
    arch.load(argv[1]);
    require(arch.netCount() == 160 && arch.portCount() == 496, "unexpected architecture");
    const auto& ports = arch.netSources();
    std::vector<uint32_t> tileAt(Architecture::kCellCount, missing);
    std::vector<uint32_t> cells;
    for (int x = 0; x < Architecture::kWidth; ++x) {
      for (int y = 0; y < Architecture::kHeight; ++y) {
        if (arch.exists(x, y)) {
          tileAt[y * Architecture::kWidth + x] = cells.size();
          cells.push_back(y * Architecture::kWidth + x);
        }
      }
    }
    require(cells.size() == 60200 && ports.size() == 160, "unexpected tile/port count");
    std::vector<int> zIndex(arch.portCount(), -1);
    for (unsigned z = 0; z < ports.size(); ++z) zIndex[ports[z]] = z;
    std::array<std::vector<uint32_t>, 160> fanout;
    for (unsigned z = 0; z < ports.size(); ++z) {
      const auto& net = arch.net(arch.netOfOutput(ports[z]));
      for (auto arc : arch.outgoingArcs(net.to)) {
        if (zIndex[arc.to] >= 0) fanout[z].push_back(zIndex[arc.to]);
      }
    }
    const uint32_t n = cells.size() * 160;
    std::vector<uint32_t> landing(n, missing), predecessor(n, missing);
    uint64_t hops = 0, edges = 0, inverseMismatch = 0;
    for (uint32_t t = 0; t < cells.size(); ++t) {
      const int x = cells[t] % Architecture::kWidth, y = cells[t] / Architecture::kWidth;
      for (unsigned z = 0; z < 160; ++z) {
        const int ni = arch.netOfOutput(ports[z]);
        auto edge = arch.resolveNet(x, y, ni);
        if (!edge.valid) continue;
        const uint32_t dest = tileAt[edge.y * Architecture::kWidth + edge.x];
        require(dest != missing, "net landed on missing tile");
        landing[t * 160 + z] = dest * 160;
        require(predecessor[dest * 160 + z] == missing, "net has multiple predecessors");
        predecessor[dest * 160 + z] = t * 160 + z;
        const auto back = arch.resolveNetPredecessor(edge.x, edge.y, ni);
        inverseMismatch += !back.valid || back.x != x || back.y != y || back.delay != edge.delay;
        ++hops;
        edges += fanout[z].size();
      }
    }
    uint64_t inverseValid = 0;
    for (uint32_t t = 0; t < cells.size(); ++t) {
      const int x = cells[t] % Architecture::kWidth, y = cells[t] / Architecture::kWidth;
      for (unsigned z = 0; z < 160; ++z) {
        auto back = arch.resolveNetPredecessor(x, y, arch.netOfOutput(ports[z]));
        ++inverseValid;
        if (!back.valid) --inverseValid;
        const uint32_t saved = predecessor[t * 160 + z];
        inverseMismatch += back.valid != (saved != missing);
        if (back.valid && saved != missing)
          inverseMismatch += cells[saved / 160] != uint32_t(back.y * Architecture::kWidth + back.x);
      }
    }
    require(inverseMismatch == 0, "forward/inverse mismatch");
    std::fprintf(stderr, "graph nodes=%u hops=%llu edges=%llu inverse_mismatch=%llu\n",
                 n, (unsigned long long)hops, (unsigned long long)edges,
                 (unsigned long long)inverseMismatch);

    // Tarjan traverses implicit Net-then-Arc edges, retaining the original direction.
    std::vector<uint32_t> number(n, missing), low(n), component(n, missing), active;
    struct Frame { uint32_t node, next; };
    std::vector<Frame> dfs;
    std::vector<uint32_t> sizes;
    uint32_t clock = 0;
    auto enter = [&](uint32_t v) {
      number[v] = low[v] = clock++;
      active.push_back(v);
      dfs.push_back({v, 0});
    };
    for (uint32_t root = 0; root < n; ++root) {
      if (number[root] != missing) continue;
      enter(root);
      while (!dfs.empty()) {
        auto& frame = dfs.back();
        const uint32_t v = frame.node;
        const auto& arcs = fanout[v % 160];
        if (landing[v] != missing && frame.next < arcs.size()) {
          const uint32_t w = landing[v] + arcs[frame.next++];
          if (number[w] == missing) {
            enter(w);
          } else if (component[w] == missing) {
            low[v] = std::min(low[v], number[w]);
          }
          continue;
        }
        if (low[v] == number[v]) {
          uint32_t size = 0, w;
          do {
            w = active.back();
            active.pop_back();
            component[w] = sizes.size();
            ++size;
          } while (w != v);
          sizes.push_back(size);
        }
        dfs.pop_back();
        if (!dfs.empty()) {
          const uint32_t parent = dfs.back().node;
          low[parent] = std::min(low[parent], low[v]);
        }
      }
    }
    require(clock == n && active.empty(), "incomplete SCC traversal");
    const auto core = std::max_element(sizes.begin(), sizes.end()) - sizes.begin();
    std::vector<uint64_t> dag;
    uint64_t orderMismatch = 0;
    for (uint32_t v = 0; v < n; ++v) {
      if (landing[v] == missing) continue;
      for (uint32_t z : fanout[v % 160]) {
        const uint32_t w = landing[v] + z;
        const uint32_t a = component[v], b = component[w];
        if (a == b) continue;
        orderMismatch += a <= b;
        dag.push_back((uint64_t(a) << 32) | b);
      }
    }
    require(orderMismatch == 0, "SCC order violated");
    std::sort(dag.begin(), dag.end());
    dag.erase(std::unique(dag.begin(), dag.end()), dag.end());
    require(sizes[core] == hops && sizes.size() == n - hops + 1,
            "fixed graph does not have one core and dead-end singletons");
    require(dag.size() == sizes.size() - 1, "unexpected condensation graph");
    for (uint64_t edge : dag)
      require((edge >> 32) == uint64_t(core), "condensation edge is not core-to-sink");
    for (uint32_t v = 0; v < n; ++v)
      require((component[v] == core) == (landing[v] != missing),
              "Net eligibility differs from core membership");

    // Independent forward/reverse BFS verifies the SCC certificate.
    std::array<std::vector<uint32_t>, 160> reverseFanout;
    for (unsigned z = 0; z < 160; ++z)
      for (uint32_t to : fanout[z]) reverseFanout[to].push_back(z);
    const uint32_t witness = std::find(component.begin(), component.end(), core) - component.begin();
    std::array<uint64_t, 2> visitedCount{};
    for (unsigned reverse = 0; reverse < 2; ++reverse) {
      std::vector<uint8_t> seen(n);
      std::vector<uint32_t> queue{witness};
      seen[witness] = 1;
      auto visit = [&](uint32_t w) {
        if (component[w] == core && !seen[w]) {
          seen[w] = 1;
          queue.push_back(w);
        }
      };
      for (size_t head = 0; head < queue.size(); ++head) {
        const uint32_t v = queue[head];
        if (!reverse) {
          for (uint32_t z : fanout[v % 160]) visit(landing[v] + z);
        } else {
          const uint32_t tileBase = v / 160 * 160;
          for (uint32_t z : reverseFanout[v % 160]) {
            const uint32_t w = predecessor[tileBase + z];
            if (w != missing) visit(w);
          }
        }
      }
      visitedCount[reverse] = queue.size();
      require(queue.size() == sizes[core], "BFS core certificate failed");
    }
    std::ofstream out(argv[2], std::ios::binary);
    out.write("HREACH01", 8);
    writeVector(out, cells);
    writeVector(out, component);
    writeVector(out, predecessor);
    writeVector(out, sizes);
    writeVector(out, dag);
    out.close();
    require(bool(out), "index close failed");
    auto top = sizes;
    std::sort(top.begin(), top.end(), std::greater<uint32_t>());
    std::ofstream report(argv[3]);
    report << "{\"nodes\":" << n << ",\"net_hops\":" << hops << ",\"z_edges\":" << edges
           << ",\"inverse_valid\":" << inverseValid << ",\"inverse_mismatches\":" << inverseMismatch
           << ",\"components\":" << sizes.size() << ",\"core_component\":" << core
           << ",\"core_size\":" << sizes[core] << ",\"dag_edges\":" << dag.size()
           << ",\"forward_bfs_core\":" << visitedCount[0]
           << ",\"reverse_bfs_core\":" << visitedCount[1]
           << ",\"top_sizes\":[";
    for (unsigned i = 0; i < std::min<size_t>(20, top.size()); ++i)
      report << (i ? "," : "") << top[i];
    report << "]}\n";
    report.close();
    require(bool(report), "report write failed");
    std::fprintf(stderr, "SCC components=%zu core=%zu size=%u dag_edges=%zu\n",
                 sizes.size(), size_t(core), sizes[core], dag.size());
  } catch (const std::exception& error) {
    std::fprintf(stderr, "hidden_reach: %s\n", error.what());
    return 1;
  }
}
