#include "architecture.h"

#include <algorithm>
#include <climits>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int kInf = INT_MAX / 4;
const std::vector<std::string> kModes = {
    "cycle1", "cycle2", "cycle3", "cycle4",
    "cycle5", "cycle6", "cycle7", "xor4"};

struct Tree {
  std::string name;
  int source = -1, xmin = 0, ymin = 0, nx = 0, ny = 0;
  std::vector<uint8_t> data;

  int parent(int z, int x, int y) const {
    if (z < 0 || z >= 160 || x < xmin || y < ymin ||
        x >= xmin + nx || y >= ymin + ny)
      return 255;
    return data[(static_cast<size_t>(z) * ny + y - ymin) * nx + x - xmin];
  }
};

struct Query {
  std::string from, to;
  int sx = 0, sy = 0, sp = -1, tx = 0, ty = 0, tp = -1;
  int exact = 0, baseline = 0;
  std::string weight;
};

struct End {
  int x = 0, y = 0, z = -1, net = -1, arc = 0;
};

struct ModeResult {
  int upper = -1;
  int prediction = -1;
  int valid_paths = 0;
  int tree_hits = 0;
};

struct Mapped {
  std::vector<int> map;
  std::vector<int> inverse;
};

std::vector<std::string> split(const std::string& line) {
  std::vector<std::string> fields;
  std::stringstream stream(line);
  std::string field;
  while (std::getline(stream, field, ',')) fields.push_back(field);
  return fields;
}

Mapped makeMapping(const delayest::Architecture& arch, const std::string& mode,
                   const std::vector<int>& zPorts) {
  const bool cycle = mode.rfind("cycle", 0) == 0;
  const int k = std::stoi(mode.substr(cycle ? 5 : 3));
  Mapped out{std::vector<int>(160, -1), std::vector<int>(160, -1)};
  for (int i = 0; i < 160; ++i) {
    const std::string& name = arch.portName(zPorts[i]);
    const size_t left = name.find('[');
    if (left == std::string::npos || name.back() != ']')
      throw std::runtime_error("bad Z name");
    const int lane = std::stoi(name.substr(left + 1, name.size() - left - 2));
    const int mappedLane = cycle ? (lane + k) % 8 : (lane ^ k);
    const int mappedPort = arch.portId(name.substr(0, left) + "[" +
                                       std::to_string(mappedLane) + "]");
    if (mappedPort < 0)
      throw std::runtime_error("mapped Z port missing");
    const auto it = std::find(zPorts.begin(), zPorts.end(), mappedPort);
    if (it == zPorts.end())
      throw std::runtime_error("mapped Z port not indexed");
    out.map[i] = static_cast<int>(it - zPorts.begin());
  }
  for (int i = 0; i < 160; ++i) {
    if (out.map[i] < 0 || out.inverse[out.map[i]] >= 0)
      throw std::runtime_error("mapping is not a permutation");
    out.inverse[out.map[i]] = i;
  }
  return out;
}

std::vector<Tree> readTrees(const std::string& manifest) {
  std::ifstream input(manifest);
  if (!input) throw std::runtime_error("cannot open tree manifest");
  std::vector<Tree> trees;
  std::string line;
  while (std::getline(input, line)) {
    if (line.empty()) continue;
    std::istringstream row(line);
    Tree tree;
    std::string path;
    if (!(row >> tree.name >> tree.source >> tree.xmin >> tree.ymin >>
          tree.nx >> tree.ny >> path))
      throw std::runtime_error("bad tree manifest row");
    std::ifstream raw(path, std::ios::binary);
    if (!raw) throw std::runtime_error("cannot open parent tree: " + path);
    tree.data.assign(std::istreambuf_iterator<char>(raw), {});
    if (tree.data.size() != static_cast<size_t>(160) * tree.nx * tree.ny)
      throw std::runtime_error("parent tree size mismatch");
    if (tree.parent(tree.source, 0, 0) != 254)
      throw std::runtime_error("parent tree root mismatch");
    trees.push_back(std::move(tree));
  }
  if (trees.size() != 40) throw std::runtime_error("expected 40 trees");
  return trees;
}

std::vector<Query> readQueries(const delayest::Architecture& arch,
                               const std::string& path) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot open predictions");
  std::string line;
  if (!std::getline(input, line)) throw std::runtime_error("empty predictions");
  std::vector<Query> queries;
  while (std::getline(input, line)) {
    if (line.empty()) continue;
    const auto fields = split(line);
    if (fields.size() != 8) throw std::runtime_error("bad prediction row");
    Query query;
    query.from = fields[0];
    query.to = fields[1];
    query.weight = fields[3];
    query.exact = std::stoi(fields[4]);
    query.baseline = std::stoi(fields[7]);
    if (!arch.parsePin(query.from, query.sx, query.sy, query.sp) ||
        !arch.parsePin(query.to, query.tx, query.ty, query.tp))
      throw std::runtime_error("prediction pin parse failed");
    queries.push_back(std::move(query));
  }
  if (queries.size() != 6176) throw std::runtime_error("expected 6176 queries");
  return queries;
}

int seedFee(const delayest::Architecture& arch, int source, int target) {
  int fee = source == target ? 0 : kInf;
  for (const auto& arc : arch.outgoingArcs(source))
    if (arc.to == target) fee = std::min(fee, arc.delay);
  return fee;
}

std::vector<End> endpoints(const delayest::Architecture& arch, const Query& query,
                           const std::vector<int>& zIndex) {
  std::vector<End> ends;
  if (arch.isNetSource(query.tp)) {
    ends.push_back({query.tx, query.ty, zIndex[query.tp], -1, 0});
    return ends;
  }
  const auto add = [&](int input, int arc) {
    const int net = arch.netOfInput(input);
    if (net < 0) return;
    const auto before = arch.resolveNetPredecessor(query.tx, query.ty, net);
    if (!before.valid) return;
    const auto forward = arch.resolveNet(before.x, before.y, net);
    if (!forward.valid || forward.x != query.tx || forward.y != query.ty ||
        forward.delay != before.delay)
      throw std::runtime_error("terminal predecessor mismatch");
    ends.push_back({before.x, before.y, zIndex[arch.net(net).from], net, arc});
  };
  if (arch.isNetSink(query.tp)) {
    add(query.tp, 0);
  } else {
    for (const auto& arc : arch.incomingArcs(query.tp)) add(arc.to, arc.delay);
  }
  return ends;
}

int transformedParent(const Tree& tree, const Mapped& mapping, int z, int x, int y) {
  const int originalZ = mapping.inverse[z];
  const int parent = tree.parent(originalZ, x, y);
  return parent < 160 ? mapping.map[parent] : parent;
}

ModeResult evaluateTree(const delayest::Architecture& arch, const Tree& tree,
                        const Mapped& mapping, const Query& query,
                        const std::vector<int>& zPorts,
                        const std::vector<int>& zIndex,
                        const std::vector<int8_t>& vx,
                        const std::vector<int8_t>& vy,
                        const int arcCost[160][160],
                        const std::vector<End>& ends) {
  const int mappedSource = mapping.map[tree.source];
  const int seed = seedFee(arch, query.sp, zPorts[mappedSource]);
  if (seed >= kInf) return {};
  ModeResult result;
  ++result.tree_hits;
  for (const End& end : ends) {
    int x = end.x - query.sx;
    int y = end.y - query.sy;
    int z = end.z;
    if (transformedParent(tree, mapping, z, x, y) == 255) continue;
    std::vector<std::pair<int, int>> path;
    int nominal = 0;
    bool complete = true;
    while (z != mappedSource || x != 0 || y != 0) {
      const int p = transformedParent(tree, mapping, z, x, y);
      if (p >= 160 || arcCost[p][z] >= 65535 || path.size() >= 32) {
        complete = false;
        break;
      }
      path.push_back({p, z});
      nominal += arcCost[p][z];
      x -= vx[p];
      y -= vy[p];
      z = p;
    }
    if (!complete || z != mappedSource || nominal > 1200) continue;
    x = query.sx;
    y = query.sy;
    z = mappedSource;
    int fee = seed;
    for (auto it = path.rbegin(); it != path.rend(); ++it) {
      const int p = it->first;
      const int q = it->second;
      if (p != z) {
        complete = false;
        break;
      }
      const auto edge = arch.resolveNet(x, y, arch.netOfOutput(zPorts[p]));
      if (!edge.valid) {
        complete = false;
        break;
      }
      x = edge.x;
      y = edge.y;
      z = q;
      fee += edge.delay + arcCost[p][q];
    }
    if (!complete || x != end.x || y != end.y || z != end.z) continue;
    if (end.net >= 0) {
      const auto edge = arch.resolveNet(x, y, end.net);
      if (!edge.valid || edge.x != query.tx || edge.y != query.ty) continue;
      fee += edge.delay + end.arc;
    }
    ++result.valid_paths;
    result.upper = result.upper < 0 ? fee : std::min(result.upper, fee);
  }
  if (result.upper >= 0)
    result.prediction = query.baseline < 0 ? result.upper
                                           : std::min(query.baseline, result.upper);
  else
    result.prediction = query.baseline;
  return result;
}

void writeRow(std::ofstream& output, const std::string& mode, size_t index,
              const Query& query, const ModeResult& result) {
  output << mode << ',' << index << ',' << query.from << ',' << query.to << ','
         << query.exact << ',' << query.weight << ',' << query.baseline << ','
         << result.upper << ',' << result.prediction << ','
         << result.valid_paths << ',' << result.tree_hits << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 5)
      throw std::runtime_error("usage: mapped_parent_paths <arch> <predictions> <manifest> <output>");
    delayest::Architecture arch;
    arch.load(argv[1]);
    std::vector<int> zPorts;
    std::vector<int> zIndex(arch.portCount(), -1);
    for (int port = 0; port < arch.portCount(); ++port) {
      if (arch.isNetSource(port)) {
        zIndex[port] = static_cast<int>(zPorts.size());
        zPorts.push_back(port);
      }
    }
    if (zPorts.size() != 160) throw std::runtime_error("expected 160 Z ports");
    std::vector<int8_t> vx(160), vy(160);
    int arcCost[160][160];
    for (int p = 0; p < 160; ++p) {
      const auto& net = arch.net(arch.netOfOutput(zPorts[p]));
      vx[p] = static_cast<int8_t>(net.dx);
      vy[p] = static_cast<int8_t>(net.dy);
      for (int q = 0; q < 160; ++q) arcCost[p][q] = 65535;
      for (const auto& arc : arch.outgoingArcs(net.to)) {
        const int q = zIndex[arc.to];
        if (q >= 0) arcCost[p][q] = std::min(arcCost[p][q], arc.delay);
      }
    }
    const auto trees = readTrees(argv[3]);
    const auto queries = readQueries(arch, argv[2]);
    std::vector<Mapped> mappings;
    for (const auto& mode : kModes) mappings.push_back(makeMapping(arch, mode, zPorts));
    std::vector<std::vector<ModeResult>> results(
        kModes.size() + 1, std::vector<ModeResult>(queries.size()));
    std::ofstream output(argv[4]);
    if (!output) throw std::runtime_error("cannot open output");
    output << "mode,index,from,to,exact,weight,baseline,upper,prediction,valid_paths,tree_hits\n";
    for (size_t mode = 0; mode < kModes.size(); ++mode) {
      for (const auto& tree : trees) {
        for (size_t i = 0; i < queries.size(); ++i) {
          const auto ends = endpoints(arch, queries[i], zIndex);
          const ModeResult one = evaluateTree(
              arch, tree, mappings[mode], queries[i], zPorts, zIndex, vx, vy,
              arcCost, ends);
          auto& total = results[mode][i];
          total.valid_paths += one.valid_paths;
          total.tree_hits += one.tree_hits;
          if (one.upper >= 0)
            total.upper = total.upper < 0 ? one.upper : std::min(total.upper, one.upper);
        }
      }
      for (size_t i = 0; i < queries.size(); ++i) {
        auto& row = results[mode][i];
        row.prediction = row.upper >= 0
            ? (queries[i].baseline < 0 ? row.upper : std::min(queries[i].baseline, row.upper))
            : queries[i].baseline;
        writeRow(output, kModes[mode], i, queries[i], row);
      }
    }
    for (size_t i = 0; i < queries.size(); ++i) {
      ModeResult combined;
      for (size_t mode = 0; mode < kModes.size(); ++mode) {
        combined.valid_paths += results[mode][i].valid_paths;
        combined.tree_hits += results[mode][i].tree_hits;
        if (results[mode][i].upper >= 0)
          combined.upper = combined.upper < 0
              ? results[mode][i].upper
              : std::min(combined.upper, results[mode][i].upper);
      }
      combined.prediction = combined.upper >= 0
          ? (queries[i].baseline < 0 ? combined.upper
                                     : std::min(queries[i].baseline, combined.upper))
          : queries[i].baseline;
      results.back()[i] = combined;
      writeRow(output, "combined", i, queries[i], combined);
    }
    output.close();
    std::cout << "rows=" << queries.size() << " modes=" << kModes.size()
              << " complete_mappings=" << kModes.size() << "\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
