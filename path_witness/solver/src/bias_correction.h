// Opt-in additive bias table for the residue estimator.
//
// The residue answer under-estimates on the public sample and is not a proven
// lower bound on the real Block graph (counterexamples in
// experiment/实验4-真实图下界审计.md); its slack is largest in relative terms
// for short queries.  Applying the median observed slack per
// distance band removes that bias on the measured corpus, at zero query cost,
// but it is an empirical calibration: it must be justified by held-out evidence
// and stays OFF unless the operator passes the offsets explicitly.  No fitted
// constant is compiled in; the mechanism is code, the data is a flag.
//
// Bands use the endpoint Manhattan distance: 0, 1-12, 13-24, 25-50, 51-100,
// 101-300, 301+.
#pragma once

#include <cstdlib>
#include <string>
#include <vector>

namespace delayest {

struct BiasTable {
  static constexpr int kBandCount = 7;
  int offsets[kBandCount] = {0, 0, 0, 0, 0, 0, 0};
  bool enabled = false;

  static int bandOf(int distance) {
    if (distance <= 0) return 0;
    if (distance <= 12) return 1;
    if (distance <= 24) return 2;
    if (distance <= 50) return 3;
    if (distance <= 100) return 4;
    if (distance <= 300) return 5;
    return 6;
  }

  // Applies the band offset and clamps at zero so the output stays a delay.
  int apply(int delay, int distance) const {
    if (!enabled) return delay;
    const int corrected = delay + offsets[bandOf(distance)];
    return corrected < 0 ? 0 : corrected;
  }

  // Accepts either one value (all bands) or kBandCount comma-separated values.
  bool parse(const std::string& text) {
    std::vector<int> values;
    size_t begin = 0;
    while (begin <= text.size()) {
      const size_t comma = text.find(',', begin);
      const std::string piece =
          text.substr(begin, comma == std::string::npos ? std::string::npos : comma - begin);
      if (!piece.empty()) values.push_back(std::atoi(piece.c_str()));
      if (comma == std::string::npos) break;
      begin = comma + 1;
    }
    if (values.empty()) return false;
    if (values.size() == 1) {
      for (int band = 0; band < kBandCount; ++band) offsets[band] = values[0];
    } else if (values.size() == kBandCount) {
      for (int band = 0; band < kBandCount; ++band) offsets[band] = values[band];
    } else {
      return false;
    }
    enabled = true;
    return true;
  }
};

}  // namespace delayest
