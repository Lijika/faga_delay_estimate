// Reuse the certified nominal solver; add complete non-I endpoint roles.
#include "../exp483/solver.hpp"

namespace {
std::vector<int> roleSources(const Architecture& arch) {
  std::vector<int> result;
  for (int p = 0; p < arch.portCount(); ++p)
    if (arch.isNetSource(p) ||
        (arch.isLogicPort(p) && !arch.outgoingArcs(p).empty()))
      result.push_back(p);
  return result;
}

std::vector<int> roleTargets(const Architecture& arch) {
  std::vector<int> result;
  for (int p = 0; p < arch.portCount(); ++p)
    if (arch.isOutputPort(p)) result.push_back(p);
  return result;
}

int sourceGraph(Graph& g, const Architecture& arch, int source) {
  auto it = std::find(g.ports.begin(), g.ports.end(), source);
  if (it != g.ports.end()) return int(it - g.ports.begin());
  std::vector<Edge> first;
  for (auto arc : arch.outgoingArcs(source)) {
    it = std::find(g.ports.begin(), g.ports.end(), arc.to);
    if (it != g.ports.end()) first.push_back({int(it-g.ports.begin()), arc.delay});
    else if (!arch.isOutputPort(arc.to))
      throw std::runtime_error("unsupported source Arc target");
  }
  if (first.empty()) throw std::runtime_error("source has no Z entrance");
  const int ordinal = int(g.ports.size());
  g.ports.push_back(source);
  g.dx.push_back(0); g.dy.push_back(0);
  g.edges.push_back(std::move(first));
  for (auto& phi : g.phi) phi.push_back(0);
  return ordinal;
}

int terminal(const Architecture& arch, const Graph& g, const Field& field,
             int source, int x, int y, int target, bool certificate) {
  auto it = std::find(g.ports.begin(), g.ports.begin()+160, target);
  const auto read = [&](int dx, int dy, int p) {
    if (!field.inside(dx, dy) ||
        (certificate && !field.certified(g, dx, dy, p)))
      throw std::runtime_error("nominal window certificate failed");
    return field.d[field.id(dx, dy, p)];
  };
  if (it != g.ports.begin()+160) return read(x, y, int(it-g.ports.begin()));
  int best = kInf;
  for (auto arc : arch.incomingArcs(target)) {
    const int net = arch.netOfInput(arc.to);
    if (net >= 0) {
      const auto& n = arch.net(net);
      it = std::find(g.ports.begin(), g.ports.begin()+160, n.from);
      if (it == g.ports.begin()+160) throw std::runtime_error("terminal source missing");
      const int dx = x-n.dx, dy = y-n.dy;
      if (!field.inside(dx, dy) && !certificate) continue;
      best = std::min(best, read(dx, dy, int(it-g.ports.begin()))+arc.delay);
    } else if (x == 0 && y == 0 && arc.to == source) {
      best = std::min(best, arc.delay);
    }
  }
  return std::min(best, kInf);
}

void checkRoles(const Architecture& arch) {
  uint64_t compared = 0, endpointValues = 0;
  const auto sources = roleSources(arch), targets = roleTargets(arch);
  if (sources.size() != 208 || targets.size() != 288)
    throw std::runtime_error("endpoint coverage mismatch");
  for (int source : sources) {
    Graph g(arch);
    const int s = sourceGraph(g, arch, source);
    const auto radix = solve(g, s, 12, 14);
    const auto heap = solve(g, s, 12, 14, true);
    if (radix.d != heap.d || radix.boundary != heap.boundary)
      throw std::runtime_error("heap comparison failed");
    compared += radix.d.size();
    // Independent full-port graph includes both Net and Arc states explicitly.
    Field full(12,14,arch.portCount());
    using Item = std::pair<int,int>;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    full.d[full.id(0,0,source)] = 0;
    queue.emplace(0,full.id(0,0,source));
    while (!queue.empty()) {
      const auto [cost,id] = queue.top(); queue.pop();
      if (cost != full.d[id]) continue;
      const int p=id%full.n, x=(id/full.n)%full.width-full.rx;
      const int y=(id/full.n)/full.width-full.ry;
      const auto relax = [&](int nx,int ny,int np,int delay) {
        if (!full.inside(nx,ny)) return;
        const int next=full.id(nx,ny,np);
        if (cost+delay < full.d[next]) {
          full.d[next]=cost+delay; queue.emplace(cost+delay,next);
        }
      };
      for (auto arc:arch.outgoingArcs(p)) relax(x,y,arc.to,arc.delay);
      const int ni=arch.netOfOutput(p);
      if (ni>=0) {
        const auto& n=arch.net(ni);
        relax(x+n.dx,y+n.dy,n.to,0);
      }
    }
    for (int target : targets)
      for (const auto xy : {std::pair<int,int>{0,0}, {1,-1}, {-1,1}}) {
        if (terminal(arch,g,radix,source,xy.first,xy.second,target,false) !=
            full.d[full.id(xy.first,xy.second,target)])
          throw std::runtime_error("terminal comparison failed");
        ++endpointValues;
      }
  }
  std::cout << "{\"source_ports\":208,\"target_ports\":288,\"heap_equal_states\":"
            << compared << ",\"endpoint_values\":" << endpointValues << "}\n";
}
}  // namespace
