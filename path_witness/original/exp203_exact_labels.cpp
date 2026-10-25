#include "../build/exp158/scaffold.cpp"

int main(int argc, char** argv) {
  try {
    if (argc != 5)
      throw std::runtime_error("usage: exact_labels <arch> <rows> <orbit-i16> <output>");
    const auto rows = readRows(argv[2]);
    if (rows.empty()) throw std::runtime_error("empty label requests");
    Architecture arch;
    arch.load(argv[1]);
    ResidueEstimator residue;
    ResidueEstimator::Options residueOptions;
    residueOptions.cacheBytes = 0;
    residueOptions.residueMultiplier = 2;
    residueOptions.endpointMode = ResidueEstimator::EndpointMode::Off;
    residueOptions.residualMode = ResidueEstimator::ResidualMode::Off;
    residue.init(arch, residueOptions);
    Exp147SafeResidueAccess::restoreOrbit(residue, argv[3]);
    Exp147SafeResidueAccess::initGrowth(residue);
    VariantProvider provider;
    provider.init(arch, residue);
    provider.fastMode = true;
    Router router, reference;
    Router::Options options;
    options.enableQueryCache = false;
    options.landmarkCount = 0;
    options.boundProvider = &provider;
    options.useRadixHeap = true;
    router.init(arch, options);
    options.boundProvider = nullptr;
    options.useRadixHeap = false;
    reference.init(arch, options);
    terminalChecks(router, arch);
    terminalChecks(reference, arch);
    std::ofstream output(argv[4]);
    if (!output) throw std::runtime_error("cannot write exact labels");
    output << "index,from,to,exact,expanded,relaxed,cpu_s\n" << std::setprecision(12);
    long long knownChecks = 0, spanChecks = 0, replays = 0;
    for (size_t i = 0; i < rows.size(); ++i) {
      const auto& row = rows[i];
      int sx, sy, sp, tx, ty, tp;
      if (!arch.parsePin(row.from, sx, sy, sp) || !arch.parsePin(row.to, tx, ty, tp))
        throw std::runtime_error("label pin parse failed");
      const auto before = router.stats();
      const double start = processCpuSeconds();
      const int answer = terminalQuery(router, arch, sx, sy, sp, tx, ty, tp, true, replays);
      const double seconds = processCpuSeconds() - start;
      const auto after = router.stats();
      if (row.label != -2) {
        if (answer != row.label) throw std::runtime_error("saved exact regression failed");
        ++knownChecks;
      } else if (row.plainCheck) {
        long long referenceReplays = 0;
        if (terminalQuery(reference, arch, sx, sy, sp, tx, ty, tp, true, referenceReplays) != answer)
          throw std::runtime_error("new request span exact disagreement");
        ++spanChecks;
      }
      output << i << ',' << row.from << ',' << row.to << ',' << answer << ','
             << after.expandedStates - before.expandedStates << ','
             << after.relaxedEdges - before.relaxedEdges << ',' << seconds << '\n';
      if ((i + 1) % 256 == 0) {
        output.flush();
        std::printf("labels_progress rows=%zu known_checks=%lld span_checks=%lld\n",
                    i + 1, knownChecks, spanChecks);
        std::fflush(stdout);
      }
    }
    output.close();
    if (!output || provider.unknown || provider.incomplete)
      throw std::runtime_error("label output or provider completeness failed");
    std::ifstream status("/proc/self/status");
    std::string statusLine;
    int threadCount = 0;
    while (std::getline(status, statusLine))
      if (statusLine.rfind("Threads:", 0) == 0)
        threadCount = std::stoi(statusLine.substr(8));
    if (threadCount != 1) throw std::runtime_error("label threads differ");
    std::printf("labels_done rows=%zu known_checks=%lld span_checks=%lld threads=%d\n",
                rows.size(), knownChecks, spanChecks, threadCount);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "exp203: %s\n", error.what());
    return 1;
  }
}
