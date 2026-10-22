// Architecture model: ports, SRB instances, intra-SRB arcs, inter-SRB nets and
// gaps.  All positions come from the published JSON files; nothing in this
// header depends on the competition CSV format.
#pragma once
#include "embedded_resolver_data.h"

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace delayest {

// Axis indices used for direction-specific gaps.
enum class Axis : int { Horizontal = 0, Vertical = 1 };

struct ArcTemplate {
  int to = -1;      // destination port id
  int delay = 0;    // picoseconds
};

struct NetTemplate {
  int from = -1;    // Z* output port id
  int to = -1;      // I* input port id
  int dx = 0;
  int dy = 0;
  int index = 0;
};

struct Block {
  int id = 0;
  int lower = 0, upper = 0, left = 0, right = 0;
  bool crossable[2] = {false, false};  // [Horizontal], [Vertical]
  int crossDelay[2] = {0, 0};
};

// One resolved Net transition: destination SRB plus accumulated gap delay.
struct ResolvedEdge {
  int x = 0;
  int y = 0;
  int delay = 0;
  bool valid = false;
};

class Architecture {
 public:
  static constexpr int kWidth = 120;
  static constexpr int kHeight = 550;
  static constexpr int kCellCount = kWidth * kHeight;

  // Loads SRB_Port.json, SRB_Arc.json, SRB_Net.json, SRB_Inst.json and
  // SRB_Gap.json from `dir`.  Throws std::runtime_error on failure.
  void load(const std::string& dir);

#ifdef DELAY_ESTIMATE_EMBEDDED_ARCH
  // Loads the architecture compiled into the binary by
  // scripts/gen_embedded_arch.py.  Used by the self-contained submission build
  // when no arch directory can be found next to the executable.
  void loadEmbedded();
#endif
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
  bool residueInputsMatchEmbedded() const { return residueInputsMatchEmbedded_; }
  bool resolverMatchesEmbedded() const { return resolverMatchesEmbedded_; }
#ifdef DELAY_ESTIMATE_RESOLVER_AUDIT
  void disableResolverForAudit() { resolverMatchesEmbedded_ = false; }
  ResolvedEdge referenceNetForAudit(int x, int y, int net, bool reverse) const {
    const auto& n = nets_[net];
    return resolveOffset(x, y, reverse ? -n.dx : n.dx, reverse ? -n.dy : n.dy);
  }
#endif
#endif

  // ---- ports ----
  int portCount() const { return static_cast<int>(portNames_.size()); }
  int portId(const std::string& name) const {
    auto it = portId_.find(name);
    return it == portId_.end() ? -1 : it->second;
  }
  const std::string& portName(int id) const { return portNames_[id]; }
  bool isOutputPort(int id) const { return portOutput_[id]; }
  bool isNetSource(int id) const { return netOfZ_[id] >= 0; }  // Z*
  bool isNetSink(int id) const { return netOfI_[id] >= 0; }    // I*
  bool isLogicPort(int id) const { return !isNetSource(id) && !isNetSink(id); }

  // ---- arcs ----
  const std::vector<ArcTemplate>& outgoingArcs(int port) const { return outgoing_[port]; }
  const std::vector<ArcTemplate>& incomingArcs(int port) const { return incoming_[port]; }

  // ---- nets ----
  int netCount() const { return static_cast<int>(nets_.size()); }
  const NetTemplate& net(int index) const { return nets_[index]; }
  int netOfOutput(int zPort) const { return netOfZ_[zPort]; }
  int netOfInput(int iPort) const { return netOfI_[iPort]; }
  const std::vector<int>& netSources() const { return netSources_; }
  const std::vector<int>& netSinks() const { return netSinks_; }

  // ---- grid ----
  bool exists(int x, int y) const {
    return x >= 0 && x < kWidth && y >= 0 && y < kHeight && exists_[y * kWidth + x];
  }
  int blockAt(int x, int y) const { return blockId_[y * kWidth + x]; }
  const std::vector<Block>& blocks() const { return blocks_; }
  const std::vector<int>& lineDelays(Axis axis) const { return lineDelay_[static_cast<int>(axis)]; }
  const std::vector<int>& lineSites(Axis axis) const { return lineSite_[static_cast<int>(axis)]; }
  int lineDelayCrossing(Axis axis, int from, int to) const {
    const std::vector<int>& prefix = linePrefix_[static_cast<int>(axis)];
    const int lo = from < to ? from : to;
    const int hi = from < to ? to : from;
    return prefix[hi] - prefix[lo];
  }

  // The only code allowed to interpret Gap Block/Line geometry: walks one
  // coordinate at a time from (x,y) along a signed axis offset.  Crossable Blocks
  // consume no offset step; non-crossable Blocks consume an ordinary step.  Line
  // Gaps are charged once per crossed boundary site.
  ResolvedEdge resolveNet(int x, int y, int netIndex) const {
    const NetTemplate& n = nets_[netIndex];
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
    if (resolverMatchesEmbedded_) return resolveLookup(x, y, resolver_data::kForward[netIndex]);
#endif
    return resolveOffset(x, y, n.dx, n.dy);
  }

  // Real predecessor of the published Net hop that lands on (x,y).  The walk is
  // the same offset rule in the opposite direction, so an origin found here is
  // exactly an origin whose forward resolveNet lands on (x,y) with the same gap
  // delay.  No reverse table is built; the cost is one walk from the landing.
  ResolvedEdge resolveNetPredecessor(int x, int y, int netIndex) const {
    const NetTemplate& n = nets_[netIndex];
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
    if (resolverMatchesEmbedded_) return resolveLookup(x, y, resolver_data::kReverse[netIndex]);
#endif
    return resolveOffset(x, y, -n.dx, -n.dy);
  }

  // ---- pins ----
  // Parses "SRB_<x>_<y>/<Port>".  Returns false when the text or the port is
  // not part of the published architecture.
  // Accepts SRB_<x>_<y>/<port> only: non negative decimal coordinates, an existing port name.
  // The view is used inside the call and never stored.
  bool parsePin(std::string_view text, int& x, int& y, int& port) const;

  // Compact identifier for a pin on the 120x550 grid.
  int64_t pinId(int x, int y, int port) const {
    return (static_cast<int64_t>(y) * kWidth + x) * portCount() + port;
  }

  // Invariants used by the internal self-check.
  struct Stats {
    int ports = 0;
    int zPorts = 0;
    int iPorts = 0;
    int logicPorts = 0;
    int arcs = 0;
    int nets = 0;
    int srb = 0;
    int blocks = 0;
    int horizontalLines = 0;
    int verticalLines = 0;
    long long netEdgesToZ = 0;  // Z states x outgoing arcs that reach a Z port
  };
  const Stats& stats() const { return stats_; }

  const std::string& sourceDirectory() const { return sourceDir_; }

 private:
  std::vector<std::string> portNames_;
  std::vector<uint8_t> portOutput_;
  std::unordered_map<std::string, int> portId_;
  std::vector<std::vector<ArcTemplate>> outgoing_;
  std::vector<std::vector<ArcTemplate>> incoming_;
  std::vector<NetTemplate> nets_;
  std::vector<int> netOfZ_;   // per port: net index or -1
  std::vector<int> netOfI_;   // per port: net index or -1
  std::vector<int> netSources_;
  std::vector<int> netSinks_;
  std::vector<uint8_t> exists_;
  std::vector<int8_t> blockId_;
  std::vector<Block> blocks_;
  std::vector<int> lineSite_[2];    // gap boundary site per axis
  std::vector<int> lineDelay_[2];   // after load: delay sum per site, per axis
  std::vector<int> linePrefix_[2];  // prefix[k] = sum of delays of sites < k
  Stats stats_;
  std::string sourceDir_;
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
  bool residueInputsMatchEmbedded_ = true;
  bool resolverMatchesEmbedded_ = false;
#endif

  void loadImpl(const std::string& dir, bool embedded);

  ResolvedEdge resolveLookup(int x, int y, int type) const {
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) return {};
    const auto& info = resolver_data::kTypes[type];
    const int group = info.horizontal ? 2 * (y < 100) + (y % 100 < 50)
                                     : (x < 16 ? 0 : (76 <= x && x <= 89 ? 1 : 2));
    const int index = info.start + (info.horizontal ? group * kWidth + x : group * kHeight + y);
    const auto cell = resolver_data::kCells[index];
    if (cell.coordinate == 65535) return {};
    return {info.horizontal ? cell.coordinate : x, info.horizontal ? y : cell.coordinate,
            cell.delay, true};
  }


  // Shared walk used by the forward resolver and its predecessor search: one
  // coordinate step per ordinary cell, no step for crossable Block cells, Block
  // charges per axis and the Gap Line prefix difference over the walked
  // interval.  Passing the negated offset walks the same cells backwards, which
  // is why the predecessor needs no reverse table.
  ResolvedEdge resolveOffset(int x, int y, int dx, int dy) const {
    ResolvedEdge out;
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight || !exists_[y * kWidth + x]) return out;
    if ((dx == 0) == (dy == 0)) return out;  // zero or diagonal template
    const bool horizontal = dx != 0;
    const int stepX = dx > 0 ? 1 : (dx < 0 ? -1 : 0);
    const int stepY = dy > 0 ? 1 : (dy < 0 ? -1 : 0);
    const int axis = horizontal ? 0 : 1;
    int remaining = horizontal ? (dx > 0 ? dx : -dx) : (dy > 0 ? dy : -dy);
    int cx = x, cy = y;
    uint32_t seenBlocks = 0;
    int blockDelay = 0;
    while (remaining > 0) {
      cx += stepX;
      cy += stepY;
      if (cx < 0 || cx >= kWidth || cy < 0 || cy >= kHeight) return out;
      const int block = blockId_[cy * kWidth + cx];
      if (block >= 0) {
        const Block& b = blocks_[block];
        if (b.crossable[axis]) {
          if (!(seenBlocks & (1u << block))) {
            seenBlocks |= (1u << block);
            blockDelay += b.crossDelay[axis];
          }
          continue;  // crossable Block consumes no offset step
        }
      }
      --remaining;  // ordinary coordinate step
    }
    if (!exists_[cy * kWidth + cx]) return out;  // landed inside a Block
    // Gap Line axis is perpendicular to the move: a horizontal Net crosses the
    // column ("vertical") gaps, whose site is an x coordinate; a vertical Net
    // crosses the row ("horizontal") gaps, whose site is a y coordinate.
    const int lineAxis = horizontal ? 1 : 0;
    const std::vector<int>& prefix = linePrefix_[lineAxis];
    const int from = horizontal ? x : y;
    const int to = horizontal ? cx : cy;
    const int lo = from < to ? from : to;
    const int hi = from < to ? to : from;
    out.x = cx;
    out.y = cy;
    out.delay = blockDelay + (prefix[hi] - prefix[lo]);
    out.valid = true;
    return out;
  }
};

}  // namespace delayest
