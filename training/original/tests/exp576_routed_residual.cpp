#define EXP554_MODEL_ONLY
#include "exp554_real_kernel_function.cpp"

#include <ctime>

static double cpu() {
    timespec stamp{};
    require(clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &stamp) == 0, "clock");
    return double(stamp.tv_sec) + double(stamp.tv_nsec) * 1e-9;
}

static unsigned route_of(const float* x) {
    const int nx = int(x[8]) + int(x[6]), ny = int(x[9]) + int(x[7]);
    const unsigned ax = nx < 0 ? -nx : nx, ay = ny < 0 ? -ny : ny;
    return 4 * (2 * (nx < 0) + (ny < 0)) + 2 * (ax >= 20) + (ay >= 24);
}

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: routed-predict FEATURES FOLDS ROUTES MODEL_LIST OUTPUT");
        return 0;
    }
    try {
        require(argc == 6, "arguments");
        FILE* f = open(argv[1]);
        char magic[8];
        uint32_t rows, columns;
        load(f, magic, 8); load(f, &rows, 1); load(f, &columns, 1);
        require(std::memcmp(magic, "E554F001", 8) == 0 && rows == 1000000 &&
                (columns == 53 || columns == 54), "feature shape");
        std::vector<float> features(size_t(rows) * columns);
        load(f, features.data(), features.size()); end(f);
        std::vector<uint8_t> folds(rows), routes(rows);
        f = open(argv[2]); load(f, folds.data(), rows); end(f);
        f = open(argv[3]); load(f, routes.data(), rows); end(f);
        f = open(argv[4]);
        unsigned groups;
        require(std::fscanf(f, "%u\n", &groups) == 1 && (groups == 1 || groups == 16), "group count");
        std::vector<Model> models;
        char path[4096];
        for (unsigned k = 0; k < 3 * groups; ++k) {
            require(std::fgets(path, sizeof(path), f) != nullptr, "model list truncated");
            const size_t n = std::strlen(path);
            require(n > 1 && path[n - 1] == '\n', "model list line");
            path[n - 1] = 0;
            models.emplace_back(path);
        }
        end(f);
        for (const auto& model : models) require(model.features <= columns, "feature count");
        std::vector<float> predictions(rows);
        std::vector<uint8_t> pair_seen(59904);
        for (unsigned i = 0; i < rows; ++i) {
            require(folds[i] < 3 && routes[i] < 16, "route or fold range");
            const float* x = features.data() + size_t(i) * columns;
            // The existing 53-feature schema starts with source/target family and lane.
            const unsigned sf = unsigned(x[0]), sl = unsigned(x[1]);
            const unsigned tf = unsigned(x[2]), tl = unsigned(x[3]);
            require(sf < 26 && tf < 36 && sl < 8 && tl < 8 && x[0] == float(sf) &&
                    x[1] == float(sl) && x[2] == float(tf) && x[3] == float(tl), "port fields");
            require(route_of(x) == routes[i], "route formula");
            pair_seen[(sf * 8 + sl) * 288 + tf * 8 + tl] = 1;
        }
        for (auto seen : pair_seen) require(seen == 1, "full port coverage");
        uint64_t comparisons = 0;
        const double start = cpu();
        for (unsigned i = 0; i < rows; ++i) {
            const float* x = features.data() + size_t(i) * columns;
            const unsigned route = groups == 1 ? 0 : route_of(x);
            predictions[i] = models[unsigned(folds[i]) * groups + route].predict(
                x, comparisons);
        }
        const double elapsed = cpu() - start;
        f = std::fopen(argv[5], "wbx");
        require(f != nullptr, "output exists or cannot create");
        require(std::fwrite(predictions.data(), sizeof(float), rows, f) == rows, "output write");
        require(std::fclose(f) == 0, "output close");
        std::printf("{\"rows\":1000000,\"port_pairs\":59904,\"groups\":%u,"
                    "\"threads\":1,\"kernel_allocations\":0,\"comparisons\":%llu,\"kernel_cpu_s\":%.9f}\n",
                    groups, static_cast<unsigned long long>(comparisons), elapsed);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
