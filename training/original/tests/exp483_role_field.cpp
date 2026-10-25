// Reuse the certified nominal solver; add complete non-I endpoint roles.
#include "../build/exp483/solver.hpp"

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

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--help") {
      std::cout << "usage: role-field ARCH --self-check\n"
                   "       role-field ARCH SOURCE OUTPUT\n";
      return 0;
    }
    if (argc != 3 && argc != 4) throw std::runtime_error("use --help");
    Architecture arch;
    arch.load(argv[1]);
    if (argc == 3) {
      if (std::string(argv[2]) != "--self-check") throw std::runtime_error("use --help");
      checkRoles(arch);
      return 0;
    }
    const auto sources = roleSources(arch), targets = roleTargets(arch);
    if (sources.size() != 208 || targets.size() != 288)
      throw std::runtime_error("endpoint coverage mismatch");
    const int source = arch.portId(argv[2]);
    if (std::find(sources.begin(), sources.end(), source) == sources.end())
      throw std::runtime_error("invalid source role");
    if (std::ifstream(argv[3]).good()) throw std::runtime_error("output exists");
    Graph g(arch);
    const int s = sourceGraph(g, arch, source);
    const double start = cpu();
    const auto field = solve(g, s, 160, 608);
    const double solved = cpu();
    std::vector<int32_t> values;
    values.reserve(4*2*288*12*46);
    for (const auto sign : {std::pair<int,int>{1,1}, {1,-1}, {-1,1}, {-1,-1}})
      for (const auto phase : {std::pair<int,int>{0,0}, {5,6}})
        for (int target : targets)
          for (int i = 0; i < 12; ++i)
            for (int j = 0; j < 46; ++j) {
              const int x = sign.first*(phase.first+10*i);
              const int y = sign.second*(phase.second+12*j);
              const int value = terminal(arch,g,field,source,x,y,target,true);
              if (value >= kInf) throw std::runtime_error("unreachable nominal target");
              values.push_back(value);
            }
    std::ofstream out(argv[3], std::ios::binary);
    out.write("EX483D01",8);
    const int32_t header[]{source, int32_t(targets.size()), 4, 2, 12, 46};
    out.write(reinterpret_cast<const char*>(header),sizeof(header));
    out.write(reinterpret_cast<const char*>(targets.data()), targets.size()*sizeof(int));
    out.write(reinterpret_cast<const char*>(values.data()), values.size()*sizeof(int32_t));
    out.close();
    if (!out) throw std::runtime_error("output write failed");
    rusage usage{};
    getrusage(RUSAGE_SELF,&usage);
    std::cout << std::setprecision(12) << "{\"source\":" << std::quoted(argv[2])
              << ",\"source_id\":" << source << ",\"target_ports\":" << targets.size()
              << ",\"certified_values\":" << values.size()
              << ",\"solve_cpu_s\":" << solved-start
              << ",\"total_cpu_s\":" << cpu() << ",\"rss_bytes\":"
              << usage.ru_maxrss*1024LL << "}\n";
  } catch (const std::exception& e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
