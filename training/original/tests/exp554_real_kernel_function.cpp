#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>

struct Node { int32_t left, right, feature; float value; };
static_assert(sizeof(Node) == 16);

static void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

template<class T> static void load(FILE* file, T* out, size_t n) {
    require(std::fread(out, sizeof(T), n, file) == n, "truncated file");
}

static FILE* open(const char* path) {
    FILE* file = std::fopen(path, "rb");
    require(file != nullptr, "cannot open input");
    return file;
}

static void end(FILE* file) {
    require(std::fgetc(file) == EOF && !std::ferror(file), "trailing bytes or read error");
    require(std::fclose(file) == 0, "close failed");
}

struct Model {
    uint32_t features;
    std::vector<uint32_t> roots;
    std::vector<Node> nodes;
    explicit Model(const char* path) {
        FILE* f = open(path);
        char magic[8]; uint32_t trees, count;
        load(f, magic, 8);
        require(std::memcmp(magic, "E554M001", 8) == 0, "model magic");
        load(f, &trees, 1); load(f, &count, 1); load(f, &features, 1);
        require(trees <= 128 && count <= 128 * 511 && features <= 128, "model shape");
        roots.resize(trees); nodes.resize(count);
        load(f, roots.data(), trees); load(f, nodes.data(), count); end(f);
        for (uint32_t root : roots) require(root < count, "root range");
        for (const auto& node : nodes) {
            if (node.left < 0) require(node.right == -1, "leaf shape");
            else require(node.right >= 0 && uint32_t(node.left) < count &&
                         uint32_t(node.right) < count && node.feature >= 0 &&
                         uint32_t(node.feature) < features, "node range");
        }
    }
    float predict(const float* x, uint64_t& comparisons) const {
        float result = 0.f;
        for (uint32_t root : roots) {
            uint32_t at = root;
            while (nodes[at].left >= 0) {
                const auto& n = nodes[at];
                at = x[n.feature] < n.value ? n.left : n.right;
                ++comparisons;
            }
            result += nodes[at].value;
        }
        return result;
    }
};

#ifndef EXP554_MODEL_ONLY
int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: predict FEATURES FOLDS MODEL0 MODEL1 MODEL2 OUTPUT");
        return 0;
    }
    try {
        require(argc == 7, "arguments");
        FILE* f = open(argv[1]);
        char magic[8]; uint32_t rows, cols;
        load(f, magic, 8);
        require(std::memcmp(magic, "E554F001", 8) == 0, "feature magic");
        load(f, &rows, 1); load(f, &cols, 1);
        require(rows == 1000000 && cols <= 128 && cols > 0, "full input shape");
        std::vector<float> features(size_t(rows) * cols);
        load(f, features.data(), features.size()); end(f);
        f = open(argv[2]);
        std::vector<uint8_t> folds(rows);
        load(f, folds.data(), rows); end(f);
        std::vector<Model> models;
        for (int i = 3; i < 6; ++i) models.emplace_back(argv[i]);
        for (const auto& model : models) require(model.features <= cols, "feature count");
        std::vector<float> predictions(rows);
        uint64_t comparisons = 0;
        for (uint32_t i = 0; i < rows; ++i) {
            require(folds[i] < 3, "fold range");
            predictions[i] = models[folds[i]].predict(features.data() + size_t(i) * cols, comparisons);
        }
        f = std::fopen(argv[6], "wbx");
        require(f != nullptr, "output exists or cannot create");
        require(std::fwrite(predictions.data(), sizeof(float), rows, f) == rows, "output write");
        require(std::fclose(f) == 0, "output close");
        std::printf("{\"rows\":%u,\"threads\":1,\"comparisons\":%llu}\n", rows,
                    static_cast<unsigned long long>(comparisons));
    } catch (const std::exception& e) {
        std::fprintf(stderr, "%s\n", e.what());
        return 1;
    }
}
#endif
