#define main exp147_reference_main
#include "exp147_orbit_access.cpp"
#undef main

#include <numeric>

namespace delayest {

struct Exp148SafeResidueAccess {
  using PureResult = Exp147SafeResidueAccess::PureResult;
  using SafeResult = Exp147SafeResidueAccess::SafeResult;

  static SafeResult enumerate(const Architecture& arch, const ResidueEstimator& e, int sx, int sy,
                             int sourcePort, int tx, int ty, int targetPort,
                             long long& evaluations) {
    SafeResult out;
    if (sx == tx && sy == ty && sourcePort == targetPort) {
      out.supported = out.known = out.complete = true;
      return out;
    }
    const int dx = tx - sx, dy = ty - sy;
    const int line = arch.lineDelayCrossing(Axis::Vertical, sx, tx) +
                     arch.lineDelayCrossing(Axis::Horizontal, sy, ty);
    ++evaluations;
    const auto first = Exp147SafeResidueAccess::pure(e, sourcePort, targetPort, dx, dy);
    if (!first.supported) return out;
    out.supported = true;
    out.fallback = first.fallback;
    bool haveBest = first.finite;
    out.value = first.finite ? first.floored + line : std::numeric_limits<int>::max();
    const auto constants = Exp147SafeResidueAccess::scalarConstants(e, sourcePort, targetPort, dx, dy);
    if (haveBest && Exp147SafeResidueAccess::scalarTail(e, constants, line, 1) > out.value) {
      out.known = out.complete = true;
      return out;
    }
    for (int magnitude = 1; magnitude <= 128; ++magnitude) {
      for (const int c : {magnitude, -magnitude}) {
        ++evaluations;
        const auto candidate = Exp147SafeResidueAccess::pure(
            e, sourcePort, targetPort, dx - 14 * c, dy);
        if (!candidate.finite) continue;
        const int value = candidate.floored + line + 292 * magnitude;
        if (!haveBest || value < out.value) {
          out.value = value;
          out.chosenC = c;
          haveBest = true;
        }
      }
      if (haveBest && Exp147SafeResidueAccess::scalarTail(e, constants, line, magnitude + 1)
                          > out.value) {
        out.known = out.complete = true;
        return out;
      }
    }
    out.known = haveBest;
    return out;
  }
  static SafeResult periodic(const Architecture& arch, const ResidueEstimator& e, int sx, int sy,
                             int sourcePort, int tx, int ty, int targetPort, int period,
                             long long& evaluations) {
    (void)period;
    SafeResult out;
    if (sx == tx && sy == ty && sourcePort == targetPort) {
      out.supported = out.known = out.complete = true;
      return out;
    }
    const int dx = tx - sx, dy = ty - sy;
    const int line = arch.lineDelayCrossing(Axis::Vertical, sx, tx) +
                     arch.lineDelayCrossing(Axis::Horizontal, sy, ty);
    ++evaluations;
    const auto first = Exp147SafeResidueAccess::pure(e, sourcePort, targetPort, dx, dy);
    if (!first.supported) return out;
    out.supported = true;
    out.fallback = first.fallback;
    bool haveBest = first.finite;
    out.value = first.finite ? first.floored + line : std::numeric_limits<int>::max();
    const auto constants = Exp147SafeResidueAccess::maxFloorConstants(e, sourcePort, targetPort, dx, dy);
    if (haveBest && Exp147SafeResidueAccess::scalarTail(e, constants, line, 1) > out.value) {
      out.known = out.complete = true;
      return out;
    }
    for (int magnitude = 1; magnitude <= 128; ++magnitude) {
      for (const int c : {magnitude, -magnitude}) {
        ++evaluations;
        const auto candidate = Exp147SafeResidueAccess::pure(
            e, sourcePort, targetPort, dx - 14 * c, dy);
        if (!candidate.finite) continue;
        const int value = candidate.floored + line + 292 * magnitude;
        if (!haveBest || value < out.value) {
          out.value = value;
          out.chosenC = c;
          haveBest = true;
        }
      }
      if (haveBest && Exp147SafeResidueAccess::scalarTail(e, constants, line, magnitude + 1)
                          > out.value) {
        out.known = out.complete = true;
        return out;
      }
    }
    out.known = haveBest;
    return out;
  }
};

}  // namespace delayest

namespace {

using delayest::Exp148SafeResidueAccess;

struct VariantProvider : Provider {
  mutable bool fastMode = false;
  mutable bool auditMode = false;
  int period = 0;
  mutable long long pureEvaluations = 0;
  mutable long long auditStates = 0;
  mutable long long auditMismatches = 0;
  mutable long long auditEnumEvaluations = 0;
  mutable long long auditFastEvaluations = 0;

  void init(const Architecture& architecture, const ResidueEstimator& residue) {
    Provider::init(architecture, residue);
    period = residue.modulusX() / std::gcd(residue.modulusX(), 14);
  }

  void clearCache() {
    std::fill(cacheStamp.begin(), cacheStamp.end(), 0);
    generation = 0;
    currentCacheEntries = 0;
    cachedTargetX = cachedTargetY = cachedTargetPort = -1;
  }

  void resetVariantCounters() {
    Provider::resetCounters();
    pureEvaluations = 0;
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
    ++currentCacheEntries;
    maxCacheEntries = std::max(maxCacheEntries, currentCacheEntries);
    cacheStamp[state] = generation;
    delayest::Exp147SafeResidueAccess::SafeResult result;
    if (auditMode) {
      long long enumCalls = 0;
      long long fastCalls = 0;
      const auto reference = Exp148SafeResidueAccess::enumerate(
          *arch, *estimator, sx, sy, sp, tx, ty, tp, enumCalls);
      result = Exp148SafeResidueAccess::periodic(
          *arch, *estimator, sx, sy, sp, tx, ty, tp, period, fastCalls);
      ++auditStates;
      auditEnumEvaluations += enumCalls;
      auditFastEvaluations += fastCalls;
      auditMismatches +=
          reference.supported != result.supported || reference.known != result.known ||
          reference.complete != result.complete || reference.fallback != result.fallback ||
          reference.value != result.value || reference.chosenC != result.chosenC;
      if (auditMismatches) throw std::runtime_error("orbit bound state differs");
      result = reference;
    } else if (fastMode) {
      long long count = 0;
      result = Exp148SafeResidueAccess::periodic(
          *arch, *estimator, sx, sy, sp, tx, ty, tp, period, count);
      pureEvaluations += count;
    } else {
      long long count = 0;
      result = Exp148SafeResidueAccess::enumerate(
          *arch, *estimator, sx, sy, sp, tx, ty, tp, count);
      pureEvaluations += count;
    }

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

}  // namespace
namespace {

int terminalQuery(Router& router, const Architecture& arch, int sx, int sy, int sp,
                  int tx, int ty, int tp, bool fold, long long& replays) {
  if (!fold || !arch.isNetSink(tp) || (sx == tx && sy == ty && sp == tp))
    return router.query(sx, sy, sp, tx, ty, tp);
  const int net = arch.netOfInput(tp);
  const auto origin = arch.resolveNetPredecessor(tx, ty, net);
  if (!origin.valid) return Router::kUnreachable;
  const auto forward = arch.resolveNet(origin.x, origin.y, net);
  if (!forward.valid || forward.x != tx || forward.y != ty || forward.delay != origin.delay)
    throw std::runtime_error("terminal predecessor replay failed");
  ++replays;
  const int value = router.query(sx, sy, sp, origin.x, origin.y, arch.net(net).from);
  return value < 0 ? value : value + origin.delay;
}

void terminalChecks(Router& router, const Architecture& arch) {
  struct Check { const char* from; const char* to; int answer; };
  const Check cases[] = {
      {"SRB_75_0/ZSEA[0]", "SRB_90_0/ISEA[0]", 292},
      {"SRB_90_0/ZSWA[0]", "SRB_75_0/ISWA[0]", 292},
      {"SRB_30_300/ZSEA[0]", "SRB_31_300/ISEA[0]", 0},
      {"SRB_33_300/ZSEA[0]", "SRB_34_300/ISEA[0]", 9},
      {"SRB_88_250/ILN[3]", "SRB_88_250/ILN[3]", 0},
      {"SRB_66_255/IQW[4]", "SRB_88_250/ILN[3]", -1},
  };
  for (const auto& test : cases) {
    int sx, sy, sp, tx, ty, tp;
    if (!arch.parsePin(test.from, sx, sy, sp) || !arch.parsePin(test.to, tx, ty, tp))
      throw std::runtime_error("terminal self-check pin missing");
    long long replays = 0;
    const int value = terminalQuery(router, arch, sx, sy, sp, tx, ty, tp, true, replays);
    if (value != test.answer)
      throw std::runtime_error(std::string("terminal self-check failed: ") + test.from + " -> " +
                               test.to + " expected=" + std::to_string(test.answer) +
                               " actual=" + std::to_string(value));
    if (test.answer >= 0 && std::string(test.from) != test.to) {
      const int old = terminalQuery(router, arch, sx, sy, sp, tx, ty, tp, false, replays);
      if (old != value) throw std::runtime_error("terminal self-check control differs");
    }
  }
}

}  // namespace
// Assembled with the frozen exp148 provider and exp150 terminal helpers.
