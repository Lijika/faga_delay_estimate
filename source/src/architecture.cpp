#include "architecture.h"

#include <algorithm>
#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string_view>

#include "json.h"

#ifdef DELAY_ESTIMATE_EMBEDDED_ARCH
#include "embedded_arch.h"
#endif

namespace delayest {
namespace {

std::string readFile(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open architecture file: " + path);
  std::ostringstream buffer;
  buffer << in.rdbuf();
  if (in.bad()) throw std::runtime_error("failed while reading architecture file: " + path);
  return buffer.str();
}

struct LoadedDocument {
  jsonlite::Document doc;
  jsonlite::ValuePtr root = nullptr;
};

LoadedDocument loadJsonText(std::string content, const std::string& file) {
  LoadedDocument out;
  out.doc = jsonlite::Document::parse(content);
  out.root = out.doc.root();
  if (!out.root || !out.root->isObject()) throw std::runtime_error("unexpected JSON root in " + file);
  return out;
}

long requireInt(jsonlite::ValuePtr object, const char* key, const std::string& file) {
  jsonlite::ValuePtr v = object->find(key);
  if (!v || !v->isNumber()) throw std::runtime_error(std::string("missing numeric field '") + key + "' in " + file);
  return v->asInt();
}

std::string requireString(jsonlite::ValuePtr object, const char* key, const std::string& file) {
  jsonlite::ValuePtr v = object->find(key);
  if (!v || !v->isString()) throw std::runtime_error(std::string("missing string field '") + key + "' in " + file);
  return v->asString();
}

jsonlite::ValuePtr requireArrayField(jsonlite::ValuePtr root, std::initializer_list<const char*> names,
                                     const std::string& file) {
  jsonlite::ValuePtr v = root->findAny(names);
  if (!v || !v->isArray()) throw std::runtime_error("missing array field in " + file);
  return v;
}

bool parseBool(jsonlite::ValuePtr v, bool fallback) {
  if (!v) return fallback;
  if (v->kind == jsonlite::Value::Kind::Bool) return v->boolean;
  if (v->isNumber()) return v->asInt() != 0;
  if (v->isString()) return v->asString() == "true" || v->asString() == "1";
  return fallback;
}

}  // namespace

void Architecture::load(const std::string& dir) {
  sourceDir_ = dir;
  loadImpl(dir, false);
}

#ifdef DELAY_ESTIMATE_EMBEDDED_ARCH
void Architecture::loadEmbedded() {
  sourceDir_ = "<embedded>";
  loadImpl(std::string(), true);
}
#endif

void Architecture::loadImpl(const std::string& dir, bool embedded) {
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
  residueInputsMatchEmbedded_ = true;
  resolverMatchesEmbedded_ = true;
#endif
  const std::string slash = dir.empty() || dir.back() == '/' ? "" : "/";
  // `embedded` is only meaningful in the self-contained submission build; the
  // regular build always reads the five JSON files from `dir`.
  auto fetch = [&](const char* name) {
#ifdef DELAY_ESTIMATE_EMBEDDED_ARCH
    if (embedded) {
      const char* text = embedded_arch::text(name);
      if (text == nullptr) throw std::runtime_error(std::string("no embedded architecture for ") + name);
      return loadJsonText(text, name);
    }
#else
    (void)embedded;
#endif
    std::string content = readFile(dir + slash + name);
#ifdef DELAY_ESTIMATE_PRECOMPUTED_RESIDUE
    const std::string_view file(name);
    if (file == "SRB_Port.json" || file == "SRB_Arc.json" || file == "SRB_Net.json") {
      // Generated raw string literals add one newline on each side.
      std::string_view reference(embedded_arch::text(name));
      reference.remove_prefix(1);
      reference.remove_suffix(1);
      residueInputsMatchEmbedded_ = residueInputsMatchEmbedded_ && content == reference;
    }
    if (file == "SRB_Net.json" || file == "SRB_Gap.json" || file == "SRB_Inst.json") {
      std::string_view reference(embedded_arch::text(name));
      reference.remove_prefix(1);
      reference.remove_suffix(1);
      resolverMatchesEmbedded_ = resolverMatchesEmbedded_ && content == reference;
    }
#endif
    return loadJsonText(std::move(content), name);
  };

  // ---------------- ports ----------------
  {
    LoadedDocument doc = fetch("SRB_Port.json");
    const std::string file = "SRB_Port.json";
    jsonlite::ValuePtr arr = requireArrayField(doc.root, {"Port", "Ports"}, file);
    portNames_.reserve(arr->items.size());
    portOutput_.reserve(arr->items.size());
    for (jsonlite::ValuePtr item : arr->items) {
      if (!item || !item->isObject()) throw std::runtime_error("malformed port entry in " + file);
      const std::string name = requireString(item, "Name", file);
      std::string direction = requireString(item, "Direction", file);
      std::transform(direction.begin(), direction.end(), direction.begin(),
                     [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
      if (portId_.count(name)) throw std::runtime_error("duplicate port name: " + name);
      portId_[name] = static_cast<int>(portNames_.size());
      portNames_.push_back(name);
      portOutput_.push_back(direction == "output" ? 1 : 0);
    }
  }

  const int portCount = static_cast<int>(portNames_.size());
  outgoing_.assign(portCount, {});
  incoming_.assign(portCount, {});
  netOfZ_.assign(portCount, -1);
  netOfI_.assign(portCount, -1);

  // ---------------- arcs ----------------
  {
    LoadedDocument doc = fetch("SRB_Arc.json");
    const std::string file = "SRB_Arc.json";
    jsonlite::ValuePtr arr = requireArrayField(doc.root, {"Arcs", "Arc"}, file);
    for (jsonlite::ValuePtr item : arr->items) {
      if (!item || !item->isObject()) throw std::runtime_error("malformed arc entry in " + file);
      const std::string from = requireString(item, "from", file);
      const std::string to = requireString(item, "to", file);
      const int fromId = portId(from);
      const int toId = portId(to);
      if (fromId < 0 || toId < 0) {
        throw std::runtime_error("arc references unknown port: " + from + " -> " + to);
      }
      ArcTemplate arc;
      arc.to = toId;
      arc.delay = static_cast<int>(requireInt(item, "delay", file));
      outgoing_[fromId].push_back(arc);
      incoming_[toId].push_back(ArcTemplate{fromId, arc.delay});
      ++stats_.arcs;
    }
  }

  // ---------------- nets ----------------
  {
    LoadedDocument doc = fetch("SRB_Net.json");
    const std::string file = "SRB_Net.json";
    jsonlite::ValuePtr arr = requireArrayField(doc.root, {"Nets", "Net"}, file);
    nets_.reserve(arr->items.size());
    for (jsonlite::ValuePtr item : arr->items) {
      if (!item || !item->isObject()) throw std::runtime_error("malformed net entry in " + file);
      const std::string from = requireString(item, "from", file);
      const std::string to = requireString(item, "to", file);
      NetTemplate net;
      net.from = portId(from);
      net.to = portId(to);
      if (net.from < 0 || net.to < 0) throw std::runtime_error("net references unknown port: " + from + " -> " + to);
      net.dx = static_cast<int>(requireInt(item, "delta x", file));
      net.dy = static_cast<int>(requireInt(item, "delta y", file));
      net.index = static_cast<int>(nets_.size());
      if (netOfZ_[net.from] >= 0) throw std::runtime_error("output port drives more than one net: " + from);
      if (netOfI_[net.to] >= 0) throw std::runtime_error("input port is target of more than one net: " + to);
      netOfZ_[net.from] = net.index;
      netOfI_[net.to] = net.index;
      netSources_.push_back(net.from);
      netSinks_.push_back(net.to);
      nets_.push_back(net);
    }
  }

  // ---------------- SRB instances ----------------
  {
    LoadedDocument doc = fetch("SRB_Inst.json");
    const std::string file = "SRB_Inst.json";
    jsonlite::ValuePtr arr = requireArrayField(doc.root, {"Inst", "Insts"}, file);
    exists_.assign(kCellCount, 0);
    for (jsonlite::ValuePtr item : arr->items) {
      if (!item || !item->isObject()) throw std::runtime_error("malformed instance entry in " + file);
      const int x = static_cast<int>(requireInt(item, "x", file));
      const int y = static_cast<int>(requireInt(item, "y", file));
      if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) throw std::runtime_error("SRB instance outside array bounds");
      exists_[y * kWidth + x] = 1;
      ++stats_.srb;
    }
  }

  // ---------------- gaps ----------------
  {
    LoadedDocument doc = fetch("SRB_Gap.json");
    const std::string file = "SRB_Gap.json";
    jsonlite::ValuePtr gaps = doc.root->findAny({"Gap", "Gaps"});
    if (!gaps || !gaps->isObject()) throw std::runtime_error("missing Gap object in " + file);
    jsonlite::ValuePtr lines = gaps->findAny({"Line", "Lines"});
    if (lines && lines->isArray()) {
      for (jsonlite::ValuePtr item : lines->items) {
        if (!item || !item->isObject()) throw std::runtime_error("malformed line gap in " + file);
        std::string direction = requireString(item, "direction", file);
        std::transform(direction.begin(), direction.end(), direction.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        const int site = static_cast<int>(requireInt(item, "site", file));
        const int delay = static_cast<int>(requireInt(item, "delay", file));
        // "vertical" line gaps run along columns (site = x); "horizontal" line
        // gaps run along rows (site = y).
        if (direction == "vertical") {
          if (site < 0 || site > kWidth) throw std::runtime_error("vertical line gap site out of range");
          lineDelay_[1].push_back(delay);
          lineSite_[1].push_back(site);
          ++stats_.verticalLines;
        } else if (direction == "horizontal") {
          if (site < 0 || site > kHeight) throw std::runtime_error("horizontal line gap site out of range");
          lineDelay_[0].push_back(delay);
          lineSite_[0].push_back(site);
          ++stats_.horizontalLines;
        } else {
          throw std::runtime_error("unknown line gap direction: " + direction);
        }
      }
    }
    jsonlite::ValuePtr blocks = gaps->findAny({"Block", "Blocks"});
    blockId_.assign(kCellCount, -1);
    if (blocks && blocks->isArray()) {
      for (jsonlite::ValuePtr item : blocks->items) {
        if (!item || !item->isObject()) throw std::runtime_error("malformed block gap in " + file);
        Block b;
        b.id = static_cast<int>(item->find("id") ? requireInt(item, "id", file) : blocks_.size());
        b.lower = static_cast<int>(requireInt(item, "lower", file));
        b.upper = static_cast<int>(requireInt(item, "upper", file));
        b.left = static_cast<int>(requireInt(item, "left", file));
        b.right = static_cast<int>(requireInt(item, "right", file));
        b.crossable[0] = parseBool(item->find("horizontal crossable"), false);
        b.crossable[1] = parseBool(item->find("vertical crossable"), false);
        b.crossDelay[0] = static_cast<int>(item->find("horizontal cross delay") ? requireInt(item, "horizontal cross delay", file) : 0L);
        b.crossDelay[1] = static_cast<int>(item->find("vertical cross delay") ? requireInt(item, "vertical cross delay", file) : 0L);
        const int blockIndex = static_cast<int>(blocks_.size());
        if (blockIndex >= 32) throw std::runtime_error("more block gaps than the bitmask supports");
        for (int y = b.lower; y <= b.upper; ++y) {
          for (int x = b.left; x <= b.right; ++x) {
            if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) throw std::runtime_error("block gap outside array bounds");
            blockId_[y * kWidth + x] = static_cast<int8_t>(blockIndex);
          }
        }
        blocks_.push_back(b);
      }
    }
  }

  // Prefix sums of line gap delays: prefix[k] = sum of delays of gaps with site < k.
  for (int axis = 0; axis < 2; ++axis) {
    const int size = axis == 0 ? kHeight : kWidth;
    linePrefix_[axis].assign(size + 1, 0);
    for (size_t i = 0; i < lineSite_[axis].size(); ++i) {
      const int site = lineSite_[axis][i];
      if (site < 0 || site >= size) continue;
      linePrefix_[axis][site + 1] += lineDelay_[axis][i];
    }
    for (int k = 1; k <= size; ++k) linePrefix_[axis][k] += linePrefix_[axis][k - 1];
    // lineDelay_ is kept as one delay per site for reporting; collapse it.
    std::vector<int> perSite(size, 0);
    for (size_t i = 0; i < lineSite_[axis].size(); ++i) {
      const int site = lineSite_[axis][i];
      if (site >= 0 && site < size) perSite[site] += lineDelay_[axis][i];
    }
    lineDelay_[axis] = std::move(perSite);
  }

  // ---------------- statistics and invariants ----------------
  stats_.ports = portCount;
  stats_.nets = static_cast<int>(nets_.size());
  stats_.blocks = static_cast<int>(blocks_.size());
  long long edgesToZ = 0;
  for (int p = 0; p < portCount; ++p) {
    if (netOfZ_[p] >= 0) ++stats_.zPorts;
    else if (netOfI_[p] >= 0) ++stats_.iPorts;
    else ++stats_.logicPorts;
  }
  for (int z : netSources_) {
    const int i = nets_[netOfZ_[z]].to;
    for (const ArcTemplate& arc : outgoing_[i]) {
      if (netOfZ_[arc.to] >= 0) ++edgesToZ;
    }
  }
  stats_.netEdgesToZ = edgesToZ;
}

bool Architecture::parsePin(std::string_view text, int& x, int& y, int& port) const {
  const size_t slash = text.find('/');
  if (slash == std::string_view::npos) return false;
  const std::string_view srb = text.substr(0, slash);
  // The port names are short, so this temporary stays in the small string buffer and the
  // existing port map is reused unchanged.
  const int id = portId(std::string(text.substr(slash + 1)));
  if (id < 0) return false;
  // SRB_<x>_<y>
  if (srb.size() < 5 || srb.compare(0, 4, "SRB_") != 0) return false;
  const size_t sep = srb.find('_', 4);
  if (sep == std::string_view::npos) return false;
  const std::string_view xs = srb.substr(4, sep - 4);
  const std::string_view ys = srb.substr(sep + 1);
  if (xs.empty() || ys.empty()) return false;
  for (char c : xs)
    if (c < '0' || c > '9') return false;
  for (char c : ys)
    if (c < '0' || c > '9') return false;
  int parsedX = 0;
  int parsedY = 0;
  const auto rx = std::from_chars(xs.data(), xs.data() + xs.size(), parsedX);
  const auto ry = std::from_chars(ys.data(), ys.data() + ys.size(), parsedY);
  if (rx.ec != std::errc() || rx.ptr != xs.data() + xs.size()) return false;
  if (ry.ec != std::errc() || ry.ptr != ys.data() + ys.size()) return false;
  x = parsedX;
  y = parsedY;
  port = id;
  return true;
}

}  // namespace delayest
