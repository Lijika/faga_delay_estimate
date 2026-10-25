#include "../build/exp552/trace/scaffold.cpp"

#include <cstring>
#include <iostream>
#include <set>

template <class T>
std::vector<T> readBinary(const char* path, size_t count, size_t skip = 0) {
  std::ifstream input(path, std::ios::binary);
  input.seekg(0, std::ios::end);
  if (!input || input.tellg() != static_cast<std::streamoff>(skip + count * sizeof(T)))
    throw std::runtime_error(std::string("binary size differs: ") + path);
  input.seekg(skip);
  std::vector<T> values(count);
  input.read(reinterpret_cast<char*>(values.data()), count * sizeof(T));
  if (!input) throw std::runtime_error("binary read failed");
  return values;
}

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--help") {
      std::cout << "usage: trace-paths ARCH QUERIES GOLD ORBIT OUTPUT-STEM\n";
      return 0;
    }
    if (argc != 6) throw std::runtime_error("use --help for trace-paths arguments");
    std::ifstream header(argv[2], std::ios::binary);
    char magic[8];
    uint32_t count = 0;
    header.read(magic, 8);
    header.read(reinterpret_cast<char*>(&count), 4);
    if (!header || std::memcmp(magic, "EX535Q01", 8) || count < 59904)
      throw std::runtime_error("expected a complete full-port query set");
    const auto query = readBinary<int32_t>(argv[2], size_t(count) * 10, 12);
    const auto gold = readBinary<int32_t>(argv[3], count);
    Architecture arch;
    arch.load(argv[1]);
    std::set<int> sources, targets;
    std::set<std::pair<int, int>> pairs;
    std::vector<int> zPorts, zCode(arch.portCount(), -1);
    for (int p = 0; p < arch.portCount(); ++p)
      if (arch.isNetSource(p)) {
        zCode[p] = static_cast<int>(zPorts.size());
        zPorts.push_back(p);
      }
    if (zPorts.size() != 160) throw std::runtime_error("Z dictionary differs");
    for (uint32_t i = 0; i < count; ++i) {
      const int32_t* q = query.data() + 10 * i;
      if (q[8] < 0 || q[8] >= arch.portCount() || q[9] < 0 || q[9] >= arch.portCount() ||
          !arch.exists(q[0], q[1]) || !arch.exists(q[2], q[3]) || gold[i] < 0)
        throw std::runtime_error("query or exact label invalid");
      sources.insert(q[8]);
      targets.insert(q[9]);
      pairs.emplace(q[8], q[9]);
    }
    if (sources.size() != 208 || targets.size() != 288 || pairs.size() != 59904)
      throw std::runtime_error("incomplete port coverage");
    ResidueEstimator residue;
    ResidueEstimator::Options residueOptions;
    residueOptions.cacheBytes = 0;
    residueOptions.residueMultiplier = 2;
    residueOptions.endpointMode = ResidueEstimator::EndpointMode::Off;
    residueOptions.residualMode = ResidueEstimator::ResidualMode::Off;
    residue.init(arch, residueOptions);
    Exp147SafeResidueAccess::restoreOrbit(residue, argv[4]);
    Exp147SafeResidueAccess::initGrowth(residue);
    VariantProvider provider;
    provider.init(arch, residue);
    provider.fastMode = true;
    Router router;
    Router::Options options;
    options.enableQueryCache = false;
    options.landmarkCount = 0;
    options.boundProvider = &provider;
    options.useRadixHeap = true;
    router.init(arch, options);
    const std::string stem(argv[5]);
    std::ofstream lengths(stem + ".lengths.u32", std::ios::binary);
    std::ofstream words(stem + ".words.u8", std::ios::binary);
    std::ofstream summaries(stem + ".summary.i32", std::ios::binary);
    if (!lengths || !words || !summaries) throw std::runtime_error("cannot write trace files");
    const auto arcFee = [&](int from, int to) {
      if (from == to) return 0;
      int best = std::numeric_limits<int>::max();
      for (const auto& arc : arch.outgoingArcs(from))
        if (arc.to == to) best = std::min(best, arc.delay);
      if (best == std::numeric_limits<int>::max()) throw std::runtime_error("trace Arc absent");
      return best;
    };
    long long replays = 0;
    uint64_t totalHops = 0;
    uint32_t maxHops = 0, emptyPaths = 0;
    const double started = processCpuSeconds();
    for (uint32_t i = 0; i < count; ++i) {
      const int32_t* q = query.data() + 10 * i;
      const int sx = q[0], sy = q[1], tx = q[2], ty = q[3], sp = q[8], tp = q[9];
      const int answer = terminalQuery(router, arch, sx, sy, sp, tx, ty, tp, true, replays);
      if (answer != gold[i]) throw std::runtime_error("trace answer differs at row " + std::to_string(i));
      std::array<int32_t, 8> sums{};
      std::vector<uint8_t> word;
      const auto replay = [&](int x, int y, int port, int targetX, int targetY, int targetPort) {
        const int index = arch.netOfOutput(port);
        if (index < 0 || zCode[port] < 0) throw std::runtime_error("trace Net absent");
        const auto& net = arch.net(index);
        const auto edge = arch.resolveNet(x, y, index);
        if (!edge.valid || edge.x != targetX || edge.y != targetY)
          throw std::runtime_error("trace Net coordinate differs");
        const int line = arch.lineDelayCrossing(delayest::Axis::Vertical, x, edge.x) +
                         arch.lineDelayCrossing(delayest::Axis::Horizontal, y, edge.y);
        if (edge.delay < line) throw std::runtime_error("trace Net fee differs");
        sums[0] += arcFee(net.to, targetPort);
        sums[1] += line;
        sums[2] += edge.delay - line;
        sums[3] += net.dx;
        sums[4] += net.dy;
        ++sums[5];
        sums[6] += edge.x - x != net.dx;
        sums[7] += edge.x - x - net.dx;
        word.push_back(static_cast<uint8_t>(zCode[port]));
      };
      const auto& trace = router.lastTrace;
      if (trace.empty()) {
        if (sx == tx && sy == ty) {
          sums[0] = arcFee(sp, tp);
        } else if (arch.isNetSource(sp) && arch.isNetSink(tp)) {
          replay(sx, sy, sp, tx, ty, tp);
        } else {
          throw std::runtime_error("unexplained empty parent trace");
        }
        ++emptyPaths;
      } else {
        const auto& first = trace.front();
        if (first.x != sx || first.y != sy) throw std::runtime_error("trace seed position differs");
        sums[0] = arcFee(sp, first.port);
        if (first.g != static_cast<uint32_t>(sums[0])) throw std::runtime_error("trace seed fee differs");
        for (size_t j = 1; j < trace.size(); ++j) {
          const auto& a = trace[j - 1];
          const auto& b = trace[j];
          replay(a.x, a.y, a.port, b.x, b.y, b.port);
          if (b.g != static_cast<uint32_t>(sums[0] + sums[1] + sums[2]))
            throw std::runtime_error("trace prefix fee differs");
        }
        const auto& last = trace.back();
        if (last.x != tx || last.y != ty || last.port != tp)
          replay(last.x, last.y, last.port, tx, ty, tp);
      }
      if (sums[0] + sums[1] + sums[2] != answer ||
          sums[3] + sums[7] != tx - sx || sums[4] != ty - sy ||
          sums[5] != static_cast<int32_t>(word.size()))
        throw std::runtime_error("complete trace conservation differs");
      const auto hops = static_cast<uint32_t>(word.size());
      totalHops += hops;
      maxHops = std::max(maxHops, hops);
      lengths.write(reinterpret_cast<const char*>(&hops), sizeof(hops));
      words.write(reinterpret_cast<const char*>(word.data()), word.size());
      summaries.write(reinterpret_cast<const char*>(sums.data()), sizeof(sums));
      if ((i + 1) % 16384 == 0) {
        lengths.flush(); words.flush(); summaries.flush();
        if (!lengths || !words || !summaries) throw std::runtime_error("trace write failed");
        std::cout << "{\"progress_rows\":" << i + 1 << "}\n" << std::flush;
      }
    }
    lengths.close(); words.close(); summaries.close();
    if (!lengths || !words || !summaries || provider.unknown || provider.incomplete)
      throw std::runtime_error("trace output or bound completeness differs");
    std::ifstream status("/proc/self/status");
    std::string line;
    int threads = 0;
    while (std::getline(status, line))
      if (line.rfind("Threads:", 0) == 0) threads = std::stoi(line.substr(8));
    if (threads != 1) throw std::runtime_error("trace thread count differs");
    std::cout << "{\"complete\":true,\"rows\":" << count << ",\"pairs\":" << pairs.size()
              << ",\"hops\":" << totalHops << ",\"max_hops\":" << maxHops
              << ",\"empty_parent_paths\":" << emptyPaths << ",\"terminal_folds\":" << replays
              << ",\"cpu_s\":" << processCpuSeconds() - started << ",\"threads\":" << threads
              << ",\"z_ports\":[";
    for (size_t i = 0; i < zPorts.size(); ++i) std::cout << (i ? "," : "") << zPorts[i];
    std::cout << "],\"z_names\":[";
    for (size_t i = 0; i < zPorts.size(); ++i)
      std::cout << (i ? "," : "") << '"' << arch.portName(zPorts[i]) << '"';
    std::cout << "]}\n";
  } catch (const std::exception& error) {
    std::cerr << "exp552: " << error.what() << '\n';
    return 1;
  }
}
