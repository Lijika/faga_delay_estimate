#define main exp26_reference_main
#include "periodic_theory_probe.cpp"
#undef main

#include <array>
#include <ctime>
#include <map>
#include <set>
#include "../src/router.h"

namespace {

struct DirectoryRoot {
  int16_t dx = 0;
  uint16_t cost = 65535, offset = 0, length = 0;
  int16_t xmin = 0, xmax = 0, ymin = 0, ymax = 0;
};
static_assert(sizeof(DirectoryRoot) == 16, "frozen root encoding differs");
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "frozen experiment uses little-endian");

long long threads() {
  std::ifstream input("/proc/self/status");
  std::string key;
  while (input >> key) {
    if (key == "Threads:") {
      long long count;
      input >> count;
      return count;
    }
    std::string rest;
    std::getline(input, rest);
  }
  throw std::runtime_error("cannot read thread count");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 6)
      throw std::runtime_error("usage: path_directory <arch> <roots> <steps> <replays> <directory>");
    Architecture arch;
    arch.load(argv[1]);
    const auto graph = buildQuotient(arch, 1);
    const auto graph2 = buildQuotient(arch, 2);
    const auto a = runPartA(arch, graph, graph2);
    const int source = graph.indexOfPort[arch.portId("ZSEA[0]")];
    const auto bounds = deriveBounds(graph, a, 1200, source);
    if (a.failures || source != 0 || graph.zCount != 160 ||
        bounds.dxMin != -97 || bounds.dxMax != 97 || bounds.dyMin != -116 || bounds.dyMax != 116)
      throw std::runtime_error("frozen nominal completeness box differs");
    int minArc = kInf, edges = 0;
    for (int p = 0; p < graph.zCount; ++p)
      for (int q = 0; q < graph.zCount; ++q)
        if (graph.edge(p, q) != kInf) {
          minArc = std::min(minArc, graph.edge(p, q));
          ++edges;
        }
    if (edges != 2752 || minArc != 48) throw std::runtime_error("frozen quotient differs");
    const double searchStart = static_cast<double>(std::clock()) / CLOCKS_PER_SEC;
    const auto search = infiniteDijkstra(graph, source, 1200, bounds);
    const double searchCpu = static_cast<double>(std::clock()) / CLOCKS_PER_SEC - searchStart;
    if (search.boundErrors) throw std::runtime_error("nominal budget box incomplete");
    std::ofstream rootsOut(argv[2]), stepsOut(argv[3]), replaysOut(argv[4]);
    if (!rootsOut || !stepsOut || !replaysOut) throw std::runtime_error("cannot write directory evidence");
    rootsOut << "dx,cost,hops,offset,first_edge,xmin,xmax,ymin,ymax\n";
    stepsOut << "root_dx,step,p,q,x,y,arc,source_distance,remaining\n";
    replaysOut << "sx,sy,dx,status,cost,resolver_calls,exact_checked,exact,slack\n";
    std::vector<DirectoryRoot> roots;
    std::vector<uint16_t> actions;
    std::map<std::tuple<int, int, int>, int> suffixDistance;
    std::map<std::tuple<int, int, int>, std::set<uint16_t>> suffixFirstSteps;
    suffixDistance[{source, 0, 0}] = 0;
    suffixFirstSteps[{source, 0, 0}] = {};
    int covered = 0, maxHops = 0, runs = 0, previous = -3;
    for (int dx = -97; dx <= 97; ++dx) {
      DirectoryRoot root;
      root.dx = static_cast<int16_t>(dx);
      root.offset = static_cast<uint16_t>(actions.size());
      const int64_t distance = search.value(source, dx, 0);
      std::vector<uint16_t> path;
      if (distance != kInf64) {
        int z = source, x = dx, y = 0;
        int64_t remaining = distance;
        while (z != source || x != 0 || y != 0) {
          int parent = -1;
          for (int p = 0; p < graph.zCount; ++p) {
            if (graph.edge(p, z) == kInf) continue;
            const auto before = search.value(p, x - graph.vx[p], y - graph.vy[p]);
            if (before != kInf64 && before + graph.edge(p, z) == remaining) {
              parent = p;
              break;
            }
          }
          if (parent < 0 || path.size() >= 25)
            throw std::runtime_error("optimal prefix witness missing or too long");
          path.push_back(static_cast<uint16_t>(parent * graph.zCount + z));
          remaining -= graph.edge(parent, z);
          x -= graph.vx[parent];
          y -= graph.vy[parent];
          z = parent;
        }
        if (remaining != 0) throw std::runtime_error("parent replay source distance differs");
        std::reverse(path.begin(), path.end());
        root.cost = static_cast<uint16_t>(distance);
        root.length = static_cast<uint16_t>(path.size());
        ++covered;
        maxHops = std::max(maxHops, static_cast<int>(path.size()));
        int x0 = 0, y0 = 0, z0 = source, cost = 0;
        for (size_t step = 0; step < path.size(); ++step) {
          const int p = path[step] / graph.zCount, q = path[step] % graph.zCount;
          if (p != z0 || graph.edge(p, q) == kInf ||
              search.value(p, x0, y0) != cost)
            throw std::runtime_error("nominal path prefix certificate differs");
          const auto key = std::make_tuple(p, dx - x0, -y0);
          const int suffixCost = static_cast<int>(distance) - cost;
          if (suffixDistance.count(key) && suffixDistance.at(key) != suffixCost)
            throw std::runtime_error("suffix translation distance differs");
          suffixDistance[key] = suffixCost;
          suffixFirstSteps[key].insert(path[step]);
          stepsOut << dx << ',' << step << ',' << p << ',' << q << ',' << x0 << ',' << y0
                   << ',' << graph.edge(p, q) << ',' << cost << ',' << suffixCost << '\n';
          x0 += graph.vx[p];
          y0 += graph.vy[p];
          cost += graph.edge(p, q);
          z0 = q;
          root.xmin = static_cast<int16_t>(std::min<int>(root.xmin, x0));
          root.xmax = static_cast<int16_t>(std::max<int>(root.xmax, x0));
          root.ymin = static_cast<int16_t>(std::min<int>(root.ymin, y0));
          root.ymax = static_cast<int16_t>(std::max<int>(root.ymax, y0));
        }
        if (x0 != dx || y0 != 0 || z0 != source || cost != distance)
          throw std::runtime_error("nominal root endpoint or fee differs");
        actions.insert(actions.end(), path.begin(), path.end());
      }
      const int first = root.cost == 65535 ? -2 : path.empty() ? -1 : path.front();
      if (first != previous) ++runs;
      previous = first;
      rootsOut << dx << ',' << (root.cost == 65535 ? -1 : root.cost) << ',' << root.length
               << ',' << root.offset << ',' << first << ',' << root.xmin << ',' << root.xmax
               << ',' << root.ymin << ',' << root.ymax << '\n';
      roots.push_back(root);
    }
    std::ofstream packed(argv[5], std::ios::binary);
    const std::array<uint32_t, 4> header = {static_cast<uint32_t>(roots.size()),
        static_cast<uint32_t>(actions.size()), 160, 1200};
    packed.write(reinterpret_cast<const char*>(header.data()), sizeof(header));
    packed.write(reinterpret_cast<const char*>(roots.data()), roots.size() * sizeof(DirectoryRoot));
    packed.write(reinterpret_cast<const char*>(actions.data()), actions.size() * sizeof(uint16_t));
    packed.close();
    if (!packed || actions.size() > 65535) throw std::runtime_error("packed path directory differs");
    std::ifstream restored(argv[5], std::ios::binary);
    std::array<uint32_t, 4> restoredHeader{};
    std::vector<DirectoryRoot> restoredRoots(195);
    std::vector<uint16_t> restoredActions(actions.size());
    restored.read(reinterpret_cast<char*>(restoredHeader.data()), sizeof(header));
    restored.read(reinterpret_cast<char*>(restoredRoots.data()), roots.size() * sizeof(DirectoryRoot));
    restored.read(reinterpret_cast<char*>(restoredActions.data()), actions.size() * sizeof(uint16_t));
    if (!restored || restored.peek() != std::char_traits<char>::eof() ||
        restoredHeader != header || restoredActions != actions ||
        std::memcmp(restoredRoots.data(), roots.data(), roots.size() * sizeof(DirectoryRoot)) != 0)
      throw std::runtime_error("packed directory restoration differs");
    delayest::Router router;
    delayest::Router::Options options;
    options.enableQueryCache = false;
    options.landmarkCount = 0;
    router.init(arch, options);
    const std::set<int> exactDx{-60, -40, -20, -10, -2, -1, 0, 1, 2, 10, 20, 40, 60};
    int checked = 0, matched = 0, calls = 0;
    double replayCpu = 0, exactCpu = 0;
    for (const int sx : {30, 60, 72, 74, 90})
      for (const int sy : {48, 49, 50, 260, 268, 300})
        for (const auto& root : restoredRoots) {
          const double replayStart = static_cast<double>(std::clock()) / CLOCKS_PER_SEC;
          int status = 0, x = sx, y = sy, z = source, cost = 0, used = 0;
          if (root.cost == 65535) status = 1;
          else if (!arch.exists(sx, sy) || !arch.exists(sx + root.dx, sy)) status = 2;
          else {
            for (int step = 0; step < root.length; ++step) {
              const int code = restoredActions[root.offset + step];
              const int p = code / graph.zCount, q = code % graph.zCount;
              if (p != z) throw std::runtime_error("restored port sequence differs");
              const auto edge = arch.resolveNet(x, y, arch.netOfOutput(graph.zPorts[p]));
              ++used;
              if (!edge.valid) {
                status = 3;
                break;
              }
              x = edge.x;
              y = edge.y;
              cost += edge.delay + graph.edge(p, q);
              z = q;
            }
            if (status == 0 && (x != sx + root.dx || y != sy || z != source)) status = 4;
          }
          replayCpu += static_cast<double>(std::clock()) / CLOCKS_PER_SEC - replayStart;
          calls += used;
          const bool exactCheck = status != 1 && status != 2 && exactDx.count(root.dx);
          int exact = -2;
          if (exactCheck) {
            const double exactStart = static_cast<double>(std::clock()) / CLOCKS_PER_SEC;
            exact = router.query(sx, sy, graph.zPorts[source], sx + root.dx, sy, graph.zPorts[source]);
            exactCpu += static_cast<double>(std::clock()) / CLOCKS_PER_SEC - exactStart;
            ++checked;
            if (status == 0) {
              if (exact < 0 || cost < exact) throw std::runtime_error("real path upper-bound violated");
              matched += cost == exact;
            }
          }
          replaysOut << sx << ',' << sy << ',' << root.dx << ',' << status << ','
                     << (status == 0 ? cost : -1) << ',' << used << ',' << exactCheck << ','
                     << exact << ',' << (status == 0 && exactCheck ? cost - exact : -1) << '\n';
        }
    rootsOut.flush();
    stepsOut.flush();
    replaysOut.flush();
    if (!rootsOut || !stepsOut || !replaysOut || threads() != 1)
      throw std::runtime_error("directory output or resource differs");
    size_t firstStepChoices = 0;
    for (const auto& item : suffixFirstSteps) firstStepChoices += item.second.size();
    std::printf("summary roots=195 covered=%d max_hops=%d actions=%zu directory_bytes=%zu "
                "suffix_keys=%zu selected_first_step_choices=%zu first_step_runs=%d settled=%lld relaxations=%lld "
                "bound_errors=%lld exact_checked=%d upper_equals_exact=%d resolver_calls=%d "
                "threads=%lld search_cpu_s=%.9f replay_cpu_s=%.9f exact_cpu_s=%.9f\n",
                covered, maxHops, actions.size(), sizeof(header) + 195 * sizeof(DirectoryRoot) +
                actions.size() * sizeof(uint16_t), suffixDistance.size(), firstStepChoices, runs,
                search.settled, search.relaxed, search.boundErrors, checked, matched, calls,
                threads(), searchCpu, replayCpu, exactCpu);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "exp167: %s\n", error.what());
    return 1;
  }
}
