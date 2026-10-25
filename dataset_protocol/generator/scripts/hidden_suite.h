#pragma once
#include "../src/architecture.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace hidden {
constexpr uint32_t missing = UINT32_MAX;
inline void require(bool value, const char* text) {
  if (!value) throw std::runtime_error(text);
}
template <class T> std::vector<T> readVector(std::ifstream& in) {
  uint64_t n = 0;
  in.read(reinterpret_cast<char*>(&n), 8);
  require(bool(in) && n <= 200000000, "invalid index vector");
  std::vector<T> out(n);
  in.read(reinterpret_cast<char*>(out.data()), n * sizeof(T));
  require(bool(in), "short index vector");
  return out;
}
struct Domain {
  delayest::Architecture arch;
  std::vector<uint32_t> cells, component, predecessor, sizes;
  std::vector<uint64_t> dag;
  std::vector<int> sources, targets, zIndex, tileAt;
  std::vector<uint8_t> sourceOK, targetOK, direct;
  std::vector<uint32_t> lineSide, blockLeft, blockRight, blockBelow, blockAbove;
  uint32_t core = 0;
  explicit Domain(const std::string& directory, const std::string& index, bool role) {
    arch.load(directory);
    std::ifstream in(index, std::ios::binary);
    char magic[8];
    in.read(magic, 8);
    require(bool(in) && std::string(magic, 8) == "HREACH01", "bad reach index");
    cells = readVector<uint32_t>(in);
    component = readVector<uint32_t>(in);
    predecessor = readVector<uint32_t>(in);
    sizes = readVector<uint32_t>(in);
    dag = readVector<uint64_t>(in);
    require(in.peek() == EOF, "trailing reach index data");
    core = std::max_element(sizes.begin(), sizes.end()) - sizes.begin();
    require(cells.size() == 60200 && component.size() == cells.size() * 160 &&
                predecessor.size() == component.size(), "bad reach dimensions");
    require(sizes.size() == component.size() - sizes[core] + 1 &&
                dag.size() == sizes.size() - 1, "unverified condensation");
    for (uint64_t edge : dag)
      require((edge >> 32) == core, "unsupported condensation edge");
    tileAt.assign(delayest::Architecture::kCellCount, -1);
    for (unsigned t = 0; t < cells.size(); ++t) {
      require(cells[t] < tileAt.size() && tileAt[cells[t]] == -1, "bad tile mapping");
      tileAt[cells[t]] = t;
    }
    zIndex.assign(arch.portCount(), -1);
    for (unsigned z = 0; z < arch.netSources().size(); ++z) zIndex[arch.netSources()[z]] = z;
    direct.resize(arch.portCount() * arch.portCount());
    for (int p = 0; p < arch.portCount(); ++p) {
      if (arch.isNetSource(p) || (role && arch.isLogicPort(p) && !arch.outgoingArcs(p).empty()))
        sources.push_back(p);
      if (arch.isOutputPort(p)) targets.push_back(p);
      for (auto a : arch.outgoingArcs(p)) direct[p * arch.portCount() + a.to] = 1;
    }
    require(sources.size() == (role ? 208 : 160) && targets.size() == 288,
            "bad endpoint profile");
    const unsigned pins = cells.size() * arch.portCount();
    sourceOK.resize(pins);
    targetOK.resize(pins);
    lineSide.resize(cells.size());
    blockLeft.resize(cells.size()); blockRight.resize(cells.size());
    blockBelow.resize(cells.size()); blockAbove.resize(cells.size());
    for (unsigned t = 0; t < cells.size(); ++t) {
      const int x = cells[t] % 120, y = cells[t] / 120;
      require(arch.exists(x, y), "reach tile missing from architecture");
      for (int p : sources) {
        bool ok = zIndex[p] >= 0 && component[t * 160 + zIndex[p]] == core;
        for (auto a : arch.outgoingArcs(p))
          if (zIndex[a.to] >= 0) ok |= component[t * 160 + zIndex[a.to]] == core;
        sourceOK[t * arch.portCount() + p] = ok;
      }
      for (int p : targets) {
        bool ok = zIndex[p] >= 0;
        for (auto a : arch.incomingArcs(p)) {
          const int n = arch.netOfInput(a.to);
          if (n < 0) continue;
          const int z = zIndex[arch.net(n).from];
          const uint32_t before = predecessor[t * 160 + z];
          if (before != missing) ok |= component[before] == core;
        }
        targetOK[t * arch.portCount() + p] = ok;
      }
      unsigned bit = 0;
      for (int site : arch.lineSites(delayest::Axis::Horizontal)) {
        if (y > site) lineSide[t] |= 1u << bit;
        ++bit;
      }
      for (int site : arch.lineSites(delayest::Axis::Vertical)) {
        if (x > site) lineSide[t] |= 1u << bit;
        ++bit;
      }
      require(bit <= 20 && arch.blocks().size() == 7, "unexpected gap count");
      for (unsigned b = 0; b < arch.blocks().size(); ++b) {
        const auto& block = arch.blocks()[b];
        if (x < block.left) blockLeft[t] |= 1u << b;
        if (x > block.right) blockRight[t] |= 1u << b;
        if (y < block.lower) blockBelow[t] |= 1u << b;
        if (y > block.upper) blockAbove[t] |= 1u << b;
      }
    }
  }
  bool reachable(uint32_t from, uint32_t to) const {
    if (sourceOK[from] && targetOK[to]) return true;
    const uint32_t ft = from / arch.portCount(), tt = to / arch.portCount();
    const int fp = from % arch.portCount(), tp = to % arch.portCount();
    return ft == tt && (fp == tp || direct[fp * arch.portCount() + tp]);
  }
  std::string pin(uint32_t id) const {
    const unsigned tile = id / arch.portCount(), port = id % arch.portCount();
    return "SRB_" + std::to_string(cells[tile] % 120) + "_" +
        std::to_string(cells[tile] / 120) + "/" + arch.portName(port);
  }
};
inline unsigned band(int d) {
  constexpr int limits[] = {0, 12, 24, 50, 100, 300};
  unsigned b = 0;
  while (b < 6 && d > limits[b]) ++b;
  return b;
}
struct Stats {
  std::vector<uint64_t> fromPort, toPort, fromTile, toTile, strata, signs, lineCross, blockCross;
  std::array<uint64_t, 6> adjacent{};
  uint64_t rows = 0, previous = 0;
  explicit Stats(const Domain& d) :
      fromPort(496), toPort(496), fromTile(d.cells.size()), toTile(d.cells.size()),
      strata(63), signs(9), lineCross(1 << 20), blockCross(1 << 14) {}
  void add(const Domain& d, uint64_t key, bool adjacency = false) {
    const uint32_t f = key >> 32, t = uint32_t(key);
    const unsigned ft = f / 496, tt = t / 496, fp = f % 496, tp = t % 496;
    const int dx = int(d.cells[tt] % 120) - int(d.cells[ft] % 120);
    const int dy = int(d.cells[tt] / 120) - int(d.cells[ft] / 120);
    auto type = [&](unsigned p) { const char c = d.arch.portName(p)[0]; return c == 'Z' ? 0 : c == 'A' ? 1 : 2; };
    ++fromPort[fp]; ++toPort[tp]; ++fromTile[ft]; ++toTile[tt];
    ++strata[(type(fp) * 3 + type(tp)) * 7 + band(std::abs(dx) + std::abs(dy))];
    ++signs[(1 + (dx > 0) - (dx < 0)) * 3 + 1 + (dy > 0) - (dy < 0)];
    ++lineCross[d.lineSide[ft] ^ d.lineSide[tt]];
    const uint32_t horizontal = (d.blockLeft[ft] & d.blockRight[tt]) | (d.blockRight[ft] & d.blockLeft[tt]);
    const uint32_t vertical = (d.blockBelow[ft] & d.blockAbove[tt]) | (d.blockAbove[ft] & d.blockBelow[tt]);
    ++blockCross[horizontal | (vertical << 7)];
    if (adjacency && rows) {
      const uint32_t pf = previous >> 32, pt = uint32_t(previous);
      adjacent[0] += f == pf; adjacent[1] += t == pt;
      adjacent[2] += ft == pf / 496; adjacent[3] += tt == pt / 496;
      adjacent[4] += fp == pf % 496; adjacent[5] += tp == pt % 496;
    }
    previous = key;
    ++rows;
  }
  template <class T> static void array(std::ostream& out, const T& values) {
    out << '[';
    for (size_t i = 0; i < values.size(); ++i) out << (i ? "," : "") << values[i];
    out << ']';
  }
  void json(std::ostream& out) const {
    out << "{\"rows\":" << rows << ",\"from_port\":"; array(out, fromPort);
    out << ",\"to_port\":"; array(out, toPort);
    out << ",\"from_tile\":"; array(out, fromTile);
    out << ",\"to_tile\":"; array(out, toTile);
    out << ",\"type_type_band\":"; array(out, strata);
    out << ",\"dx_dy_sign\":"; array(out, signs);
    out << ",\"adjacent\":"; array(out, adjacent);
    auto sparse = [&](const std::vector<uint64_t>& values) {
      out << '{';
      bool first = true;
      for (unsigned i = 0; i < values.size(); ++i)
        if (values[i]) { out << (first ? "" : ",") << '"' << i << "\":" << values[i]; first = false; }
      out << '}';
    };
    out << ",\"line_cross_masks\":"; sparse(lineCross);
    out << ",\"block_cross_masks\":"; sparse(blockCross);
    out << '}';
  }
};
}  // namespace hidden
