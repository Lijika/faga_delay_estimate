// Reuse the certified solver and endpoint handling without changing graph semantics.
#include "../build/exp499/roles.hpp"

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--help") {
      std::cout << "usage: full-residue-field ARCH --self-check\n"
                   "       full-residue-field ARCH SOURCE OUTPUT|-\n";
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
    const bool streaming = std::string(argv[3]) == "-";
    if (!streaming && std::ifstream(argv[3]).good()) throw std::runtime_error("output exists");
    Graph graph(arch);
    const int ordinal = sourceGraph(graph, arch, source);
    const double start = cpu();
    const auto field = solve(graph, ordinal, 160, 608);
    const double solved = cpu();
    std::ofstream file;
    if (!streaming) file.open(argv[3], std::ios::binary);
    std::ostream& out = streaming ? std::cout : file;
    out.write("EX499D01", 8);
    const int32_t header[]{source, 288, 4, 120, 12, 46};
    out.write(reinterpret_cast<const char*>(header), sizeof(header));
    out.write(reinterpret_cast<const char*>(targets.data()), targets.size() * sizeof(int));
    uint64_t count = 0;
    int minimum = 32767, maximum = -32768;
    std::array<int16_t, 552> residual{};
    for (const auto& sign : {std::pair<int,int>{1,1}, {1,-1}, {-1,1}, {-1,-1}})
      for (int rx = 0; rx < 10; ++rx)
        for (int ry = 0; ry < 12; ++ry)
          for (int target : targets) {
            for (int i = 0; i < 12; ++i)
              for (int j = 0; j < 46; ++j) {
                const int x = sign.first * (rx + 10 * i);
                const int y = sign.second * (ry + 12 * j);
                const int value = terminal(arch, graph, field, source, x, y, target, true);
                if (value < 0 || value >= kInf)
                  throw std::runtime_error("invalid nominal distance");
                const int delta = value - 125 * i - (sign.second > 0 ? 127 : 125) * j;
                if (delta < -32768 || delta > 32767)
                  throw std::runtime_error("residual does not fit int16");
                minimum = std::min(minimum, delta);
                maximum = std::max(maximum, delta);
                residual[i * 46 + j] = static_cast<int16_t>(delta);
                ++count;
              }
            out.write(reinterpret_cast<const char*>(residual.data()), sizeof(residual));
          }
    out.flush();
    if (!streaming) file.close();
    if (!out || count != uint64_t(4) * 120 * 288 * 552)
      throw std::runtime_error("incomplete field output");
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    std::ostream& log = streaming ? std::cerr : std::cout;
    log << std::setprecision(12) << "{\"source\":" << std::quoted(argv[2])
              << ",\"source_id\":" << source << ",\"target_ports\":288"
              << ",\"contexts\":480,\"certified_values\":" << count
              << ",\"residual_min\":" << minimum << ",\"residual_max\":" << maximum
              << ",\"solve_cpu_s\":" << solved - start << ",\"total_cpu_s\":" << cpu()
              << ",\"rss_bytes\":" << usage.ru_maxrss * 1024LL << "}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
