#include "scaffold.hpp"
#include <numeric>
#include <zstd.h>

namespace {

template <typename T>
void save(const std::string& path, const std::vector<T>& data) {
  if (std::ifstream(path).good()) throw std::runtime_error("output already exists");
  std::ofstream out(path, std::ios::binary);
  out.write(reinterpret_cast<const char*>(data.data()), data.size() * sizeof(T));
  out.close();
  if (!out) throw std::runtime_error("output write failed");
}

std::vector<uint8_t> load(const char* path, size_t size) {
  std::ifstream in(path, std::ios::binary);
  std::vector<uint8_t> data(size);
  in.read(reinterpret_cast<char*>(data.data()), size);
  if (!in || in.peek() != std::char_traits<char>::eof())
    throw std::runtime_error("input size or EOF differs");
  return data;
}

double cpu() { return static_cast<double>(std::clock()) / CLOCKS_PER_SEC; }

void generate(const Architecture& arch, const char* directory, int budget) {
  const auto graph = buildQuotient(arch, 1);
  const auto partA = runPartA(arch, graph, buildQuotient(arch, 2));
  const int source = graph.indexOfPort.at(arch.portId("ZSEA[0]"));
  if (partA.failures || source != 0 || graph.zCount != 160)
    throw std::runtime_error("quotient certificate differs");
  const auto bounds = deriveBounds(graph, partA, budget, source);
  const double searchStart = cpu(), searchWall = now();
  const auto search = infiniteDijkstra(graph, source, budget, bounds);
  const double searchCpu = cpu() - searchStart, searchSeconds = now() - searchWall;
  if (search.boundErrors || bounds.estimatedStates != static_cast<long long>(search.dist.size()))
    throw std::runtime_error("nominal completeness box failed");
  int minArc = kInf;
  for (const auto cost : graph.cost) minArc = std::min(minArc, cost);
  if (minArc <= 0 || budget >= 65535 || budget / minArc >= 254)
    throw std::runtime_error("positive-cost or depth encoding premise differs");
  std::vector<uint8_t> parent(search.dist.size(), 255);
  std::vector<uint16_t> distance(search.dist.size(), 65535);
  long long finite = 0, certificates = 0;
  const double parentStart = cpu(), parentWall = now();
  for (int x = bounds.dxMin; x <= bounds.dxMax; ++x)
    for (int y = bounds.dyMin; y <= bounds.dyMax; ++y)
      for (int z = 0; z < graph.zCount; ++z) {
        const auto id = search.index(z, x, y);
        const auto cost = search.dist[id];
        if (cost == kInf64) continue;
        if (cost < 0 || cost > budget) throw std::runtime_error("finite cost outside budget");
        ++finite;
        distance[id] = static_cast<uint16_t>(cost);
        if (cost == 0) {
          if (z != source || x || y) throw std::runtime_error("root differs");
          parent[id] = 254;
          continue;
        }
        for (int p = 0; p < graph.zCount; ++p) {
          const int arc = graph.edge(p, z);
          if (arc == kInf) continue;
          const auto before = search.value(p, x - graph.vx[p], y - graph.vy[p]);
          if (before != kInf64 && before + arc == cost) {
            if (before >= cost) throw std::runtime_error("nondecreasing parent");
            parent[id] = static_cast<uint8_t>(p);
            ++certificates;
            break;
          }
        }
        if (parent[id] == 255) throw std::runtime_error("optimal parent missing");
      }
  const double parentCpu = cpu() - parentStart, parentSeconds = now() - parentWall;
  const double depthStart = cpu();
  std::vector<uint8_t> depth(parent.size(), 255);
  depth[search.index(source, 0, 0)] = 0;
  std::vector<size_t> pending;
  int maxDepth = 0;
  for (size_t id = 0; id < parent.size(); ++id) {
    if (parent[id] == 255 || depth[id] != 255) continue;
    pending.clear();
    size_t current = id;
    while (depth[current] == 255) {
      pending.push_back(current);
      const int p = parent[current];
      if (p >= graph.zCount || pending.size() > static_cast<size_t>(budget / minArc))
        throw std::runtime_error("full parent chain broken");
      const int y = (current / graph.zCount) % search.dySpan + search.dyMin;
      const int x = current / (graph.zCount * search.dySpan) + search.dxMin;
      if (!search.inRange(x - graph.vx[p], y - graph.vy[p]))
        throw std::runtime_error("full parent chain left box");
      current = search.index(p, x - graph.vx[p], y - graph.vy[p]);
    }
    int value = depth[current];
    for (auto it = pending.rbegin(); it != pending.rend(); ++it) depth[*it] = ++value;
    maxDepth = std::max(maxDepth, value);
  }
  if (finite != certificates + 1 || finite != search.settled || maxDepth > budget / minArc)
    throw std::runtime_error("full certificate counts differ");
  const double depthCpu = cpu() - depthStart;
  const std::string dir(directory);
  save(dir + "/parents.u8", parent);
  save(dir + "/distances.u16", distance);
  std::vector<uint8_t> target;
  target.reserve(parent.size());
  for (int z = 0; z < graph.zCount; ++z)
    for (int y = bounds.dyMin; y <= bounds.dyMax; ++y)
      for (int x = bounds.dxMin; x <= bounds.dxMax; ++x)
        target.push_back(parent[search.index(z, x, y)]);
  save(dir + "/target.u8", target);
  std::printf("summary budget=%d source=%d dx_min=%lld dx_max=%lld dy_min=%lld dy_max=%lld "
              "slots=%zu finite=%lld parent_certificates=%lld settled=%lld relaxations=%lld "
              "bound_errors=%lld min_arc=%d max_hops=%d threads=%lld search_cpu_s=%.9f "
              "search_wall_s=%.9f parent_cpu_s=%.9f parent_wall_s=%.9f depth_cpu_s=%.9f\n",
              budget, source, bounds.dxMin, bounds.dxMax, bounds.dyMin, bounds.dyMax,
              parent.size(), finite, certificates, search.settled, search.relaxed,
              search.boundErrors, minArc, maxDepth, threads(), searchCpu, searchSeconds,
              parentCpu, parentSeconds, depthCpu);
}

struct Terminal { int x, y, z, net, arc; };
struct Query { std::string from, to; int sx, sy, sp, tx, ty, tp, exact; };
enum Failure {
  Outside, Unknown, Broken, HopCap, MissingArc, Budget, InvalidHop,
  EndpointMismatch, InvalidTerminal, Legal, FailureCount
};
struct Result {
  std::array<int, FailureCount> count{};
  int seed = -1, terminals = 0, upper = -1, winner = -1, maxHops = 0;
  int resolverCalls = 0, predecessors = 0, terminalUnavailable = 0;
};

Result replay(const Architecture& arch, const Quotient& graph, const Query& query,
              const std::vector<uint8_t>& parent, int xmin, int ymin, int nx, int ny,
              int budget, int maxHops) {
  Result out;
  const auto at = [&](int z, int x, int y) -> int {
    if (z < 0 || z >= 160 || x < xmin || x >= xmin + nx || y < ymin || y >= ymin + ny)
      return 255;
    return parent[(static_cast<size_t>(z) * ny + y - ymin) * nx + x - xmin];
  };
  if (query.sp == graph.zPorts[0]) out.seed = 0;
  else
    for (const auto& arc : arch.outgoingArcs(query.sp))
      if (arc.to == graph.zPorts[0] && (out.seed < 0 || arc.delay < out.seed)) out.seed = arc.delay;
  std::vector<Terminal> ends;
  const auto add = [&](int input, int arc) {
    const int net = arch.netOfInput(input);
    if (net < 0) return;
    ++out.predecessors;
    const auto before = arch.resolveNetPredecessor(query.tx, query.ty, net);
    if (!before.valid) { ++out.terminalUnavailable; return; }
    ++out.resolverCalls;
    const auto edge = arch.resolveNet(before.x, before.y, net);
    if (!edge.valid || edge.x != query.tx || edge.y != query.ty || edge.delay != before.delay)
      throw std::runtime_error("terminal inverse certificate differs");
    ends.push_back({before.x, before.y, graph.indexOfPort[arch.net(net).from], net, arc});
  };
  if (arch.isNetSource(query.tp))
    ends.push_back({query.tx, query.ty, graph.indexOfPort[query.tp], -1, 0});
  else if (arch.isNetSink(query.tp)) add(query.tp, 0);
  else for (const auto& arc : arch.incomingArcs(query.tp)) add(arc.to, arc.delay);
  out.terminals = static_cast<int>(ends.size());
  if (out.seed < 0 || !arch.exists(query.sx, query.sy) || !arch.exists(query.tx, query.ty))
    return out;
  std::array<uint16_t, 50> path{};
  if (maxHops > static_cast<int>(path.size())) throw std::runtime_error("path capacity differs");
  for (size_t t = 0; t < ends.size(); ++t) {
    const auto& end = ends[t];
    int x = end.x - query.sx, y = end.y - query.sy, z = end.z;
    if (x < xmin || x >= xmin + nx || y < ymin || y >= ymin + ny) {
      ++out.count[Outside]; continue;
    }
    if (at(z, x, y) == 255) { ++out.count[Unknown]; continue; }
    int hops = 0, nominal = 0, failure = -1;
    while (z != 0 || x || y) {
      const int p = at(z, x, y);
      if (p >= 160) { failure = Broken; break; }
      const int arc = graph.edge(p, z);
      if (arc == kInf) { failure = MissingArc; break; }
      if (hops == maxHops) { failure = HopCap; break; }
      path[hops++] = p * 160 + z;
      nominal += arc;
      x -= graph.vx[p]; y -= graph.vy[p]; z = p;
    }
    out.maxHops = std::max(out.maxHops, hops);
    if (failure < 0 && nominal > budget) failure = Budget;
    int fee = out.seed;
    x = query.sx; y = query.sy; z = 0;
    for (int i = hops - 1; failure < 0 && i >= 0; --i) {
      const int p = path[i] / 160, q = path[i] % 160;
      if (z != p) throw std::runtime_error("port chain differs");
      const auto edge = arch.resolveNet(x, y, arch.netOfOutput(graph.zPorts[p]));
      ++out.resolverCalls;
      if (!edge.valid) { failure = InvalidHop; break; }
      fee += edge.delay + graph.edge(p, q);
      x = edge.x; y = edge.y; z = q;
    }
    if (failure < 0 && (x != end.x || y != end.y || z != end.z)) failure = EndpointMismatch;
    if (failure < 0 && end.net >= 0) {
      const auto edge = arch.resolveNet(x, y, end.net);
      ++out.resolverCalls;
      if (!edge.valid || edge.x != query.tx || edge.y != query.ty) failure = InvalidTerminal;
      else fee += edge.delay + end.arc;
    }
    if (failure < 0) {
      if (query.exact < 0 || fee < query.exact) throw std::runtime_error("legal U below exact");
      failure = Legal;
      if (out.upper < 0 || fee < out.upper) { out.upper = fee; out.winner = t; }
    }
    ++out.count[failure];
  }
  if (std::accumulate(out.count.begin(), out.count.end(), 0) != out.terminals)
    throw std::runtime_error("funnel partition differs");
  return out;
}

void queries(int argc, char** argv, const Architecture& arch) {
  if (argc != 13) throw std::runtime_error("query <arch> <raw> <xmin> <ymin> <nx> <ny> <budget> <requests> <rows> <repeats> <expected_rows>");
  const int xmin = std::stoi(argv[4]), ymin = std::stoi(argv[5]);
  const int nx = std::stoi(argv[6]), ny = std::stoi(argv[7]), budget = std::stoi(argv[8]);
  const int repeats = std::stoi(argv[11]), expectedRows = std::stoi(argv[12]);
  if (nx <= 0 || ny <= 0 || repeats <= 0) throw std::runtime_error("query shape differs");
  const double loadStart = cpu(), loadWall = now();
  const auto parent = load(argv[3], static_cast<size_t>(nx) * ny * 160);
  const double loadCpu = cpu() - loadStart, loadSeconds = now() - loadWall;
  const auto graph = buildQuotient(arch, 1);
  const int minArc = *std::min_element(graph.cost.begin(), graph.cost.end());
  if (graph.zCount != 160 || graph.name(0) != "ZSEA[0]" || minArc <= 0 ||
      parent[static_cast<size_t>(-ymin) * nx - xmin] != 254)
    throw std::runtime_error("query graph or root differs");
  std::vector<Query> input;
  std::ifstream in(argv[9]);
  Query q;
  while (in >> q.from >> q.to >> q.exact) {
    if (!arch.parsePin(q.from, q.sx, q.sy, q.sp) || !arch.parsePin(q.to, q.tx, q.ty, q.tp))
      throw std::runtime_error("query pin differs");
    input.push_back(q);
  }
  if (!in.eof() || static_cast<int>(input.size()) != expectedRows)
    throw std::runtime_error("query rows or EOF differs");
  std::ofstream rows(argv[10]);
  rows << "index,from,to,exact,source_arc,terminals,attempts,upper,slack,best_terminal,max_hops,"
          "resolver_calls,predecessor_calls,terminal_unavailable,outside_box,unknown_initial,"
          "broken_parent,hop_cap,missing_arc,nominal_budget,invalid_hop,endpoint_mismatch,invalid_terminal,legal\n";
  std::vector<Result> reference;
  for (size_t i = 0; i < input.size(); ++i) {
    const auto& row = input[i];
    const auto r = replay(arch, graph, row, parent, xmin, ymin, nx, ny, budget, budget / minArc);
    reference.push_back(r);
    rows << i << ',' << row.from << ',' << row.to << ',' << row.exact << ',' << r.seed << ','
         << r.terminals << ',' << std::accumulate(r.count.begin(), r.count.end(), 0) << ','
         << r.upper << ',' << (r.upper >= 0 ? r.upper - row.exact : -1) << ',' << r.winner
         << ',' << r.maxHops << ',' << r.resolverCalls << ',' << r.predecessors << ','
         << r.terminalUnavailable;
    for (const int n : r.count) rows << ',' << n;
    rows << '\n';
  }
  rows.close();
  if (!rows) throw std::runtime_error("query evidence write failed");
  const double start = cpu(), wall = now();
  for (int repetition = 0; repetition < repeats; ++repetition)
    for (size_t i = 0; i < input.size(); ++i) {
      const auto r = replay(arch, graph, input[i], parent, xmin, ymin, nx, ny, budget, budget / minArc);
      const auto& ref = reference[i];
      if (r.count != ref.count || r.upper != ref.upper || r.winner != ref.winner ||
          r.maxHops != ref.maxHops || r.resolverCalls != ref.resolverCalls ||
          r.predecessors != ref.predecessors || r.terminalUnavailable != ref.terminalUnavailable)
        throw std::runtime_error("repeat query differs");
    }
  std::printf("summary rows=%zu repeats=%d load_cpu_s=%.9f load_wall_s=%.9f "
              "query_cpu_s=%.9f query_wall_s=%.9f threads=%lld\n", input.size(), repeats,
              loadCpu, loadSeconds, cpu() - start, now() - wall, threads());
}

void restore(const char* frame, const char* output) {
  std::ifstream in(frame, std::ios::binary | std::ios::ate);
  if (!in) throw std::runtime_error("frame open failed");
  const auto data = load(frame, static_cast<size_t>(in.tellg()));
  const auto size = ZSTD_getFrameContentSize(data.data(), data.size());
  const auto frameSize = ZSTD_findFrameCompressedSize(data.data(), data.size());
  if (ZSTD_isError(frameSize) || frameSize != data.size() || size > 2'000'000'000)
    throw std::runtime_error("frame content size or exact EOF differs");
  const double start = cpu(), wall = now();
  std::vector<uint8_t> decoded(size);
  const auto got = ZSTD_decompress(decoded.data(), decoded.size(), data.data(), data.size());
  if (ZSTD_isError(got) || got != size) throw std::runtime_error("decompression failed");
  const double seconds = cpu() - start, wallSeconds = now() - wall;
  if (std::string(output) != "-") save(output, decoded);
  std::printf("summary bytes=%zu restore_cpu_s=%.9f restore_wall_s=%.9f threads=%lld zstd=%s\n",
              decoded.size(), seconds, wallSeconds, threads(), ZSTD_versionString());
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 4 && std::string(argv[1]) == "restore") restore(argv[2], argv[3]);
    else {
      if (argc < 3) throw std::runtime_error("expected generate, query or restore");
      Architecture arch;
      arch.load(argv[2]);
      if (argc == 5 && std::string(argv[1]) == "generate")
        generate(arch, argv[3], std::stoi(argv[4]));
      else if (std::string(argv[1]) == "query") queries(argc, argv, arch);
      else throw std::runtime_error("invalid command");
    }
    if (threads() != 1) throw std::runtime_error("thread count differs");
  } catch (const std::exception& error) {
    std::fprintf(stderr, "exp208: %s\n", error.what());
    return 1;
  }
}
