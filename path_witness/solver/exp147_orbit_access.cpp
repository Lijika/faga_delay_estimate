#include <array>
#include <numeric>
// Experiment 147: dense state-index cache for the safe residue Router bound.
//
// The probe keeps the production Router unchanged.  It compares plain
// Dijkstra, the built-in span A*, and the test-only safe residue provider on
// the same deterministic request set.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <vector>

#include "src/architecture.h"
#include "src/residue_estimator.h"
#include "src/router.h"

namespace delayest {

struct Exp147SafeResidueAccess {
  static void restoreOrbit(const ResidueEstimator& e, const char* path) {
    orbitGroups = std::gcd(e.mx_, 14);
    const size_t entries = e.zPorts_.size() * e.storedTargetCount_ * e.my_ * orbitGroups * 4;
    if (e.mx_ != 20 || e.my_ != 24 || entries != 8'847'360 || e.scale_ != 120)
      throw std::runtime_error("frozen orbit restore dimensions changed");
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input || input.tellg() != static_cast<std::streamoff>(entries * sizeof(int16_t)))
      throw std::runtime_error("narrow orbit input size differs");
    std::vector<int16_t> narrow(entries);
    input.seekg(0);
    input.read(reinterpret_cast<char*>(narrow.data()),
               static_cast<std::streamsize>(entries * sizeof(int16_t)));
    if (!input) throw std::runtime_error("narrow orbit input read failed");
    orbitMinimum.resize(entries);
    universalOrbits = 0;
    for (size_t i = 0; i < entries; ++i) {
      orbitMinimum[i] = narrow[i] == -32768 ? kMissingOrbit : 10 * static_cast<int32_t>(narrow[i]);
      if (narrow[i] != -32768) ++universalOrbits;
    }
  }
  static inline std::vector<int32_t> orbitMinimum;
  static inline int orbitGroups = 0;
  static inline long long universalOrbits = 0;
  static constexpr int32_t kMissingOrbit = std::numeric_limits<int32_t>::min();

  static int64_t floorDivide(int64_t value, int scale) {
    return value >= 0 ? value / scale : -((-value + scale - 1) / scale);
  }

  static void initOrbit(const ResidueEstimator& e) {
    orbitGroups = std::gcd(e.mx_, 14);
    const int period = e.mx_ / orbitGroups;
    if (period != 10 || e.my_ != 24 || e.zPorts_.size() != 160)
      throw std::runtime_error("frozen residue orbit dimensions changed");
    for (const int a : e.slopeA_)
      if (292 - (14LL * std::abs(a) + e.scale_ - 1) / e.scale_ <= 0)
        throw std::runtime_error("orbit tail has no positive slope");
    const size_t entries = e.zPorts_.size() * e.storedTargetCount_ * e.my_ * orbitGroups * 4;
    orbitMinimum.assign(entries, kMissingOrbit);
    universalOrbits = 0;
    size_t offset = 0;
    for (int source = 0; source < static_cast<int>(e.zPorts_.size()); ++source) {
      for (int column = 0; column < e.storedTargetCount_; ++column) {
        for (int ry = 0; ry < e.my_; ++ry) {
          for (int group = 0; group < orbitGroups; ++group) {
            std::array<int32_t, 4> minimum;
            minimum.fill(std::numeric_limits<int32_t>::max());
            std::array<bool, 4> complete{true, true, true, true};
            for (int rx = group; rx < e.mx_; rx += orbitGroups) {
              for (int q = 0; q < 4; ++q) {
                const int32_t value = e.tableValue(q, source, column, rx + e.mx_ * ry);
                if (value == kMissingOrbit)
                  throw std::runtime_error("finite table uses reserved orbit sentinel");
                if (value == e.kInfTable) complete[q] = false;
                else minimum[q] = std::min(minimum[q], value);
              }
            }
            for (int q = 0; q < 4; ++q) {
              if (complete[q]) {
                orbitMinimum[offset + q] = minimum[q];
                ++universalOrbits;
              }
            }
            offset += 4;
          }
        }
      }
    }
    if (offset != entries) throw std::runtime_error("orbit table size mismatch");
  }

  static std::array<int64_t, 4> orbitConstants(const ResidueEstimator& e, int sourcePort,
                                              int targetPort, int dx, int dy) {
    std::array<int64_t, 4> out;
    out.fill(std::numeric_limits<int64_t>::min());
    const int source = e.sourceOfPort_[sourcePort], target = e.targetOfPort_[targetPort];
    if (source < 0 || source >= static_cast<int>(e.zPorts_.size()) || target < 0) return out;
    const int column = e.storedTargetOfTarget_[target];
    if (e.arch_->isNetSink(targetPort)) {
      const int predecessor = e.iPredecessorOf_[target];
      dx -= e.vx_[predecessor];
      dy -= e.vy_[predecessor];
    }
    const int residue = e.residueOf(dx, dy);
    const int ry = residue / e.mx_, group = (residue % e.mx_) % orbitGroups;
    const size_t offset =
        (((static_cast<size_t>(source) * e.storedTargetCount_ + column) * e.my_ + ry) *
         orbitGroups + group) * 4;
    for (int q = 0; q < 4; ++q) {
      if (orbitMinimum[offset + q] == kMissingOrbit) continue;
      out[q] = floorDivide(static_cast<int64_t>(e.slopeA_[q]) * dx +
                           static_cast<int64_t>(e.slopeB_[q]) * dy +
                           orbitMinimum[offset + q], e.scale_);
    }
    return out;
  }

  static int64_t orbitTail(const ResidueEstimator& e, const std::array<int64_t, 4>& constants,
                           int line, int magnitude) {
    int64_t lower = 292LL * magnitude;
    for (int q = 0; q < 4; ++q) {
      if (constants[q] == std::numeric_limits<int64_t>::min()) continue;
      const int64_t growth = 292 - (14LL * std::abs(e.slopeA_[q]) + e.scale_ - 1) / e.scale_;
      lower = std::max(lower, constants[q] + growth * magnitude);
    }
    return line + lower;
  }
  static inline int64_t commonOrbitGrowth = 0;

  static void initGrowth(const ResidueEstimator& e) {
    for (int q = 0; q < 4; ++q) {
      const int64_t growth = 292 - (14LL * std::abs(e.slopeA_[q]) + e.scale_ - 1) / e.scale_;
      if (growth <= 0 || (q > 0 && growth != commonOrbitGrowth))
        throw std::runtime_error("orbit growth is not a common positive constant");
      commonOrbitGrowth = growth;
    }
  }

  static int64_t scalarConstants(const ResidueEstimator& e, int sourcePort,
                                int targetPort, int dx, int dy) {
    int64_t out = std::numeric_limits<int64_t>::min();
    const int source = e.sourceOfPort_[sourcePort], target = e.targetOfPort_[targetPort];
    if (source < 0 || source >= static_cast<int>(e.zPorts_.size()) || target < 0) return out;
    const int column = e.storedTargetOfTarget_[target];
    if (e.arch_->isNetSink(targetPort)) {
      const int predecessor = e.iPredecessorOf_[target];
      dx -= e.vx_[predecessor];
      dy -= e.vy_[predecessor];
    }
    const int residue = e.residueOf(dx, dy);
    const int ry = residue / e.mx_, group = (residue % e.mx_) % orbitGroups;
    const size_t offset =
        (((static_cast<size_t>(source) * e.storedTargetCount_ + column) * e.my_ + ry) *
         orbitGroups + group) * 4;
    for (int q = 0; q < 4; ++q) {
      if (orbitMinimum[offset + q] == kMissingOrbit) continue;
      const int64_t constant = floorDivide(static_cast<int64_t>(e.slopeA_[q]) * dx +
                                           static_cast<int64_t>(e.slopeB_[q]) * dy +
                                           orbitMinimum[offset + q], e.scale_);
      out = std::max(out, constant);
    }
    return out;
  }

  static int64_t scalarTail(const ResidueEstimator&, int64_t constant,
                            int line, int magnitude) {
    int64_t lower = 292LL * magnitude;
    if (constant != std::numeric_limits<int64_t>::min())
      lower = std::max(lower, constant + commonOrbitGrowth * magnitude);
    return line + lower;
  }
  static int64_t maxFloorConstants(const ResidueEstimator& e, int sourcePort,
                                  int targetPort, int dx, int dy) {
    int64_t numerator = std::numeric_limits<int64_t>::min();
    const int source = e.sourceOfPort_[sourcePort], target = e.targetOfPort_[targetPort];
    if (source < 0 || source >= static_cast<int>(e.zPorts_.size()) || target < 0)
      return numerator;
    const int column = e.storedTargetOfTarget_[target];
    if (e.arch_->isNetSink(targetPort)) {
      const int predecessor = e.iPredecessorOf_[target];
      dx -= e.vx_[predecessor];
      dy -= e.vy_[predecessor];
    }
    const int residue = e.residueOf(dx, dy);
    const int ry = residue / e.mx_, group = (residue % e.mx_) % orbitGroups;
    const size_t offset =
        (((static_cast<size_t>(source) * e.storedTargetCount_ + column) * e.my_ + ry) *
         orbitGroups + group) * 4;
    for (int q = 0; q < 4; ++q) {
      if (orbitMinimum[offset + q] == kMissingOrbit) continue;
      const int64_t value = static_cast<int64_t>(e.slopeA_[q]) * dx +
                            static_cast<int64_t>(e.slopeB_[q]) * dy +
                            orbitMinimum[offset + q];
      numerator = std::max(numerator, value);
    }
    return numerator == std::numeric_limits<int64_t>::min()
               ? numerator : floorDivide(numerator, e.scale_);
  }
  struct PureResult {
    bool supported = false;
    bool finite = false;
    bool fallback = false;
    int floored = 0;
  };

  struct SafeResult {
    bool supported = false;
    bool known = false;
    bool complete = false;
    bool fallback = false;
    int value = 0;
    int chosenC = 0;
  };

  static PureResult pure(const ResidueEstimator& e, int sourcePort, int targetPort, int dx, int dy) {
    PureResult out;
    if (sourcePort < 0 || targetPort < 0 ||
        sourcePort >= static_cast<int>(e.sourceOfPort_.size()) ||
        targetPort >= static_cast<int>(e.targetOfPort_.size())) {
      return out;
    }
    const int sourceIndex = e.sourceOfPort_[sourcePort];
    const int targetIndex = e.targetOfPort_[targetPort];
    if (sourceIndex < 0 || targetIndex < 0) return out;
    const int residue = e.residueOf(dx, dy);
    const int storedColumn = e.storedTargetOfTarget_[targetIndex];
    int lookupDx = dx;
    int lookupDy = dy;
    int lookupResidue = residue;
    if (e.arch_->isNetSink(targetPort)) {
      const int p = e.iPredecessorOf_[targetIndex];
      lookupDx -= e.vx_[p];
      lookupDy -= e.vy_[p];
      lookupResidue = e.prevResidue_[static_cast<size_t>(p) * e.residueCount_ + residue];
    }
    bool have = false;
    int64_t best = std::numeric_limits<int64_t>::min();
    for (int quadrant = 0; quadrant < e.kQuadrants; ++quadrant) {
      const int32_t value = e.tableValue(quadrant, sourceIndex, storedColumn, lookupResidue);
      if (value == e.kInfTable) continue;
      const int64_t candidate =
          static_cast<int64_t>(e.slopeA_[quadrant]) * lookupDx +
          static_cast<int64_t>(e.slopeB_[quadrant]) * lookupDy + value;
      best = std::max(best, candidate);
      have = true;
    }
    out.supported = true;
    if (!have) {
      out.fallback = true;
      return out;
    }
    out.finite = true;
    const double scaled = static_cast<double>(best) / static_cast<double>(e.scale_);
    out.floored = std::max(0, static_cast<int>(std::floor(scaled)));
    return out;
  }

  static SafeResult safe(const Architecture& arch, const ResidueEstimator& e, int sx, int sy,
                         int sourcePort, int tx, int ty, int targetPort) {
    SafeResult out;
    if (sx == tx && sy == ty && sourcePort == targetPort) {
      out.supported = true;
      out.known = true;
      out.complete = true;
      return out;
    }
    const int dx = tx - sx;
    const int dy = ty - sy;
    const int line = arch.lineDelayCrossing(Axis::Vertical, sx, tx) +
                     arch.lineDelayCrossing(Axis::Horizontal, sy, ty);
    const PureResult first = pure(e, sourcePort, targetPort, dx, dy);
    if (!first.supported) return out;
    out.supported = true;
    out.fallback = first.fallback;
    bool haveBest = first.finite;
    out.value = first.finite ? first.floored + line : std::numeric_limits<int>::max();
    out.chosenC = 0;

    for (int magnitude = 1; magnitude <= 128; ++magnitude) {
      for (const int c : {magnitude, -magnitude}) {
        const PureResult candidate = pure(e, sourcePort, targetPort, dx - 14 * c, dy);
        if (!candidate.finite) continue;
        const int value = candidate.floored + line + 292 * std::abs(c);
        if (!haveBest || value < out.value) {
          out.value = value;
          out.chosenC = c;
          haveBest = true;
        }
      }
      if (haveBest && line + 292 * (magnitude + 1) > out.value) {
        out.known = true;
        out.complete = true;
        return out;
      }
    }
    out.known = haveBest;
    return out;
  }
};

}  // namespace delayest

namespace {

using delayest::Architecture;
using delayest::Exp147SafeResidueAccess;
using delayest::ResidueEstimator;
using delayest::Router;

struct Row {
  std::string kind;
  std::string from;
  std::string to;
  int label = -2;
  bool plainCheck = false;
};

struct Observation {
  int answer = -2;
  long long expanded = 0;
  long long relaxed = 0;
};

struct EngineReport {
  double cpuSeconds = 0.0;
  double wallSeconds = 0.0;
  long long expanded = 0;
  long long relaxed = 0;
  long long answerMismatches = 0;
  long long labelMismatches = 0;
};

struct Provider : Router::BoundProvider {
  const Architecture* arch = nullptr;
  const ResidueEstimator* estimator = nullptr;
  mutable long long calls = 0;
  mutable long long computed = 0;
  mutable long long known = 0;
  mutable long long unknown = 0;
  mutable long long incomplete = 0;
  mutable long long nonzeroC = 0;
  mutable long long cacheHits = 0;
  mutable size_t currentCacheEntries = 0;
  mutable size_t maxCacheEntries = 0;
  mutable int cachedTargetX = -1;
  mutable int cachedTargetY = -1;
  mutable int cachedTargetPort = -1;
  mutable uint32_t generation = 0;
  size_t zCount = 0;
  size_t cacheBytes = 0;
  std::vector<int> zIndexOfPort;
  mutable std::vector<uint32_t> cacheStamp;
  mutable std::vector<int32_t> cacheValue;

  void init(const Architecture& architecture, const ResidueEstimator& residue) {
    arch = &architecture;
    estimator = &residue;
    zIndexOfPort.assign(static_cast<size_t>(arch->portCount()), -1);
    for (int port = 0; port < arch->portCount(); ++port) {
      if (arch->isNetSource(port)) zIndexOfPort[port] = static_cast<int>(zCount++);
    }
    const size_t states = static_cast<size_t>(Architecture::kCellCount) * zCount;
    cacheStamp.assign(states, 0);
    cacheValue.assign(states, -1);
    cacheBytes = cacheStamp.size() * sizeof(cacheStamp[0]) +
                 cacheValue.size() * sizeof(cacheValue[0]);
  }

  void resetCounters() const {
    calls = computed = known = unknown = incomplete = nonzeroC = cacheHits = 0;
    maxCacheEntries = currentCacheEntries;
  }

  bool bound(int sx, int sy, int sp, int tx, int ty, int tp, long long& value) const override {
    ++calls;
    if (tx != cachedTargetX || ty != cachedTargetY || tp != cachedTargetPort) {
      cachedTargetX = tx;
      cachedTargetY = ty;
      cachedTargetPort = tp;
      currentCacheEntries = 0;
      if (++generation == 0) {
        std::fill(cacheStamp.begin(), cacheStamp.end(), 0);
        generation = 1;
      }
    }
    if (sx < 0 || sx >= Architecture::kWidth || sy < 0 ||
        sy >= Architecture::kHeight || sp < 0 ||
        sp >= static_cast<int>(zIndexOfPort.size()) || zIndexOfPort[sp] < 0) {
      ++unknown;
      return false;
    }
    const size_t state =
        static_cast<size_t>(sy * Architecture::kWidth + sx) * zCount + zIndexOfPort[sp];
    if (cacheStamp[state] == generation) {
      ++cacheHits;
      if (cacheValue[state] < 0) {
        ++unknown;
        return false;
      }
      ++known;
      value = cacheValue[state];
      return true;
    }
    ++computed;
    cacheStamp[state] = generation;
    ++currentCacheEntries;
    maxCacheEntries = std::max(maxCacheEntries, currentCacheEntries);
    const auto result = Exp147SafeResidueAccess::safe(*arch, *estimator, sx, sy, sp, tx, ty, tp);
    if (!result.supported) {
      ++unknown;
      cacheValue[state] = -1;
      return false;
    }
    if (!result.complete) {
      ++incomplete;
      ++unknown;
      cacheValue[state] = -1;
      return false;
    }
    if (!result.known) {
      ++unknown;
      cacheValue[state] = -1;
      return false;
    }
    ++known;
    if (result.chosenC != 0) ++nonzeroC;
    value = result.value;
    cacheValue[state] = result.value;
    return true;
  }
};

std::vector<std::string> split(const std::string& line) {
  std::vector<std::string> fields;
  std::string field;
  for (char c : line) {
    if (c == ',') {
      fields.push_back(field);
      field.clear();
    } else {
      field.push_back(c);
    }
  }
  fields.push_back(field);
  return fields;
}

std::vector<Row> readRows(const std::string& path) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot read " + path);
  std::vector<Row> rows;
  std::string line;
  bool header = true;
  while (std::getline(input, line)) {
    if (header) {
      header = false;
      continue;
    }
    if (line.empty()) continue;
    const auto fields = split(line);
    if (fields.size() < 5) throw std::runtime_error("short input row");
    Row row;
    row.kind = fields[0];
    row.from = fields[1];
    row.to = fields[2];
    if (fields.size() >= 4 && !fields[3].empty()) row.label = std::stoi(fields[3]);
    row.plainCheck = fields[4] == "1";
    rows.push_back(std::move(row));
  }
  return rows;
}

double processCpuSeconds() {
  struct timespec ts {};
  if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts) != 0) throw std::runtime_error("clock_gettime");
  return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
}

double wallSeconds() {
  using clock = std::chrono::steady_clock;
  static const clock::time_point origin = clock::now();
  return std::chrono::duration<double>(clock::now() - origin).count();
}

long long peakRssKib() {
  struct rusage usage {};
  if (getrusage(RUSAGE_SELF, &usage) != 0) return -1;
  return static_cast<long long>(usage.ru_maxrss);
}

long long threadCount() {
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    if (line.rfind("Threads:", 0) == 0) return std::stoll(line.substr(8));
  }
  return -1;
}

EngineReport runEngine(const char* name, Router& router, const Architecture& arch,
                       const std::vector<Row>& rows, std::vector<Observation>& observations,
                       bool compareLabels, bool selectedOnly = false) {
  EngineReport report;
  observations.assign(rows.size(), {});
  const double cpuStart = processCpuSeconds();
  const double wallStart = wallSeconds();
  for (size_t i = 0; i < rows.size(); ++i) {
    if (selectedOnly && !rows[i].plainCheck) continue;
    int sx = 0, sy = 0, sp = -1, tx = 0, ty = 0, tp = -1;
    if (!arch.parsePin(rows[i].from, sx, sy, sp) || !arch.parsePin(rows[i].to, tx, ty, tp)) {
      observations[i].answer = Router::kUnreachable;
      if (compareLabels && rows[i].label != -2 && rows[i].label != Router::kUnreachable)
        ++report.labelMismatches;
      continue;
    }
    const Router::Stats before = router.stats();
    const int answer = router.query(sx, sy, sp, tx, ty, tp);
    const Router::Stats after = router.stats();
    observations[i].answer = answer;
    observations[i].expanded = after.expandedStates - before.expandedStates;
    observations[i].relaxed = after.relaxedEdges - before.relaxedEdges;
    report.expanded += observations[i].expanded;
    report.relaxed += observations[i].relaxed;
    if (compareLabels && rows[i].label != -2 && answer != rows[i].label) ++report.labelMismatches;
  }
  report.cpuSeconds = processCpuSeconds() - cpuStart;
  report.wallSeconds = wallSeconds() - wallStart;
  (void)name;
  return report;
}

void writeObservations(const std::vector<Row>& rows, const std::vector<Observation>& plain,
                       const std::vector<Observation>& span, const std::vector<Observation>& safe,
                       const std::string& path) {
  std::ofstream output(path);
  if (!output) throw std::runtime_error("cannot write " + path);
  output << "kind,from,to,label,plain_checked,plain,span,safe,plain_expanded,span_expanded,safe_expanded,"
            "plain_relaxed,span_relaxed,safe_relaxed\n";
  for (size_t i = 0; i < rows.size(); ++i) {
    output << rows[i].kind << ',' << rows[i].from << ',' << rows[i].to << ',' << rows[i].label << ','
           << (rows[i].plainCheck ? 1 : 0) << ',' << plain[i].answer << ',' << span[i].answer << ','
           << safe[i].answer << ','
           << plain[i].expanded << ',' << span[i].expanded << ',' << safe[i].expanded << ','
           << plain[i].relaxed << ',' << span[i].relaxed << ',' << safe[i].relaxed << '\n';
  }
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 4) {
    std::fprintf(stderr, "usage: exp146_router_safe_residue <arch-dir> <rows.csv> <output.csv>\n");
    return 2;
  }
  try {
    const std::vector<Row> rows = readRows(argv[2]);
    if (rows.empty()) throw std::runtime_error("empty row set");

    Architecture arch;
    arch.load(argv[1]);

    ResidueEstimator::Options residueOptions;
    residueOptions.cacheBytes = 0;
    residueOptions.residueMultiplier = 2;
    residueOptions.endpointMode = ResidueEstimator::EndpointMode::Off;
    residueOptions.residualMode = ResidueEstimator::ResidualMode::Off;
    ResidueEstimator residue;
    residue.init(arch, residueOptions);
    int checkX = 0, checkY = 0, checkPort = -1;
    if (!arch.parsePin("SRB_75_0/ZSEA[0]", checkX, checkY, checkPort)) {
      throw std::runtime_error("same-state self-check pin is missing");
    }
    const auto sameState =
        Exp147SafeResidueAccess::safe(arch, residue, checkX, checkY, checkPort,
                                      checkX, checkY, checkPort);
    if (!sameState.known || !sameState.complete || sameState.value != 0) {
      throw std::runtime_error("safe bound is nonzero at the identical Z* target state");
    }

    Router router;
    Router::Options plainOptions;
    plainOptions.queryCacheEntries = 0;
    plainOptions.enableQueryCache = false;
    plainOptions.useSpanHeuristic = false;
    plainOptions.landmarkCount = 0;
    plainOptions.useRadixHeap = false;

    std::vector<Observation> plain;
    router.init(arch, plainOptions);
    const EngineReport plainReport = runEngine("plain", router, arch, rows, plain, false, true);

    Router::Options spanOptions = plainOptions;
    spanOptions.useSpanHeuristic = true;
    Provider provider;
    provider.init(arch, residue);
    Router::Options safeOptions = spanOptions;
    safeOptions.boundProvider = &provider;
    auto runSpan = [&](std::vector<Observation>& observations) {
      router.init(arch, spanOptions);
      return runEngine("span", router, arch, rows, observations, true);
    };
    auto runSafe = [&](std::vector<Observation>& observations) {
      router.init(arch, safeOptions);
      return runEngine("safe", router, arch, rows, observations, true);
    };

    std::vector<Observation> warmSpan, warmSafe;
    runSpan(warmSpan);
    runSafe(warmSafe);
    provider.resetCounters();

    struct Pair {
      EngineReport span;
      EngineReport safe;
      bool spanFirst = true;
    };
    std::vector<Pair> pairs;
    std::vector<Observation> span, safe;
    long long repeatedAnswerMismatches = 0;
    long long repeatedLabelMismatches = 0;
    for (int round = 0; round < 5; ++round) {
      Pair pair;
      pair.spanFirst = (round % 2 == 0);
      std::vector<Observation> roundSpan, roundSafe;
      if (pair.spanFirst) {
        pair.span = runSpan(roundSpan);
        pair.safe = runSafe(roundSafe);
      } else {
        pair.safe = runSafe(roundSafe);
        pair.span = runSpan(roundSpan);
      }
      for (size_t i = 0; i < rows.size(); ++i) {
        repeatedAnswerMismatches += roundSpan[i].answer != roundSafe[i].answer;
      }
      repeatedLabelMismatches += pair.span.labelMismatches + pair.safe.labelMismatches;
      span = std::move(roundSpan);
      safe = std::move(roundSafe);
      pairs.push_back(pair);
    }

    writeObservations(rows, plain, span, safe, argv[3]);

    long long plainSpanMismatches = 0;
    long long safeSpanMismatches = 0;
    for (size_t i = 0; i < rows.size(); ++i) {
      if (rows[i].plainCheck) plainSpanMismatches += plain[i].answer != span[i].answer;
      safeSpanMismatches += span[i].answer != safe[i].answer;
    }
    const bool labelsMatch = repeatedLabelMismatches == 0;
    const bool answersMatch = plainSpanMismatches == 0 && safeSpanMismatches == 0 &&
                              repeatedAnswerMismatches == 0;
    const bool providerSafe = provider.incomplete == 0;
    const long long rss = peakRssKib();
    const long long threads = threadCount();

    std::printf(
        "summary rows=%zu plain_checked=%lld repeated_answer_mismatches=%lld "
        "repeated_label_mismatches=%lld "
        "plain_span_mismatches=%lld safe_span_mismatches=%lld "
        "answers_match=%d labels_match=%d provider_incomplete=%lld provider_known=%lld "
        "provider_unknown=%lld provider_nonzero_c=%lld provider_cache_hits=%lld "
        "provider_cache_bytes=%zu provider_states=%zu peak_rss_kib=%lld threads=%lld\n",
        rows.size(), static_cast<long long>(std::count_if(rows.begin(), rows.end(),
                      [](const Row& row) { return row.plainCheck; })),
        repeatedAnswerMismatches, repeatedLabelMismatches,
        plainSpanMismatches, safeSpanMismatches, answersMatch ? 1 : 0,
        labelsMatch ? 1 : 0, provider.incomplete, provider.known, provider.unknown,
        provider.nonzeroC, provider.cacheHits, provider.cacheBytes,
        provider.cacheStamp.size(), rss, threads);
    std::printf("engine plain cpu_s=%.6f wall_s=%.6f expanded=%lld relaxed=%lld\n",
                plainReport.cpuSeconds, plainReport.wallSeconds, plainReport.expanded,
                plainReport.relaxed);
    for (size_t i = 0; i < pairs.size(); ++i) {
      const Pair& pair = pairs[i];
      std::printf(
          "pair index=%zu order=%s span_cpu_s=%.6f span_wall_s=%.6f span_expanded=%lld "
          "span_relaxed=%lld safe_cpu_s=%.6f safe_wall_s=%.6f safe_expanded=%lld "
          "safe_relaxed=%lld\n",
          i, pair.spanFirst ? "span-safe" : "safe-span", pair.span.cpuSeconds,
          pair.span.wallSeconds, pair.span.expanded, pair.span.relaxed, pair.safe.cpuSeconds,
          pair.safe.wallSeconds, pair.safe.expanded, pair.safe.relaxed);
    }
    std::printf("provider calls=%lld computed=%lld known=%lld unknown=%lld incomplete=%lld "
                "nonzero_c=%lld cache_hits=%lld max_cache_entries=%zu\n",
                provider.calls, provider.computed, provider.known, provider.unknown,
                provider.incomplete, provider.nonzeroC, provider.cacheHits,
                provider.maxCacheEntries);
    return labelsMatch && answersMatch && providerSafe ? 0 : 1;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "exp147: %s\n", error.what());
    return 2;
  }
}
