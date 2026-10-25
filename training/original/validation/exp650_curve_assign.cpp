#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

template <class T>
std::vector<T> read(const std::string& path, size_t count) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "input open");
    std::vector<T> values(count);
    stream.read(reinterpret_cast<char*>(values.data()), std::streamsize(count * sizeof(T)));
    require(size_t(stream.gcount()) == count * sizeof(T) && stream.peek() == EOF, "input size");
    return values;
}

template <class T>
void write(const std::string& path, const std::vector<T>& values) {
    std::ofstream stream(path, std::ios::binary);
    require(bool(stream), "output open");
    stream.write(reinterpret_cast<const char*>(values.data()),
                 std::streamsize(values.size() * sizeof(T)));
    stream.close();
    require(bool(stream), "output write");
}

void assign(const std::vector<int16_t>& values, const std::vector<int16_t>& centers,
            const std::vector<double>& weights, unsigned n, unsigned dim,
            std::vector<uint8_t>& codes, std::vector<double>& losses) {
    require(centers.size() == size_t(256) * dim && weights.size() == dim, "shape");
    for (double w : weights) require(w > 0 && std::isfinite(w), "weight");
    for (unsigned i = 0; i < n; ++i) {
        const auto* row = values.data() + size_t(i) * dim;
        unsigned best = 0;
        double distance = INFINITY;
        for (unsigned c = 0; c < 256; ++c) {
            const auto* center = centers.data() + size_t(c) * dim;
            double current = 0;
            for (unsigned j = 0; j < dim; ++j)
                current += weights[j] * std::abs(int(row[j]) - int(center[j]));
            if (c == 0 || current < distance - 1e-12 * std::max(1., distance)) {
                distance = current;
                best = c;
            }
        }
        codes[i] = uint8_t(best);
        losses[i] = distance;
    }
}

void self_check() {
    const std::vector<int16_t> values{-2, -2, -32767, 32767, 0, 0};
    std::vector<int16_t> centers(256 * 2, 0);
    centers[2] = centers[3] = -4;
    centers[4] = -32767;
    centers[5] = 32767;
    std::vector<uint8_t> codes(3);
    std::vector<double> losses(3);
    assign(values, centers, {1., 3.}, 3, 2, codes, losses);
    require(codes == std::vector<uint8_t>({0, 2, 0}), "ties and signed extremes");
    require(losses == std::vector<double>({8., 0., 0.}), "weighted losses");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        self_check();
        if (argc == 2 && std::string(argv[1]) == "--self-check") {
            std::cout << "{\"self_check_passed\":true}\n";
            return 0;
        }
        require(argc == 7, "rows.i16 centers.i16 weights.f64 row-count dimension output-prefix");
        const unsigned n = unsigned(std::stoul(argv[4]));
        const unsigned dim = unsigned(std::stoul(argv[5]));
        require(n > 0 && n <= 718848 && dim > 0 && dim <= 64, "frozen bounds");
        const auto values = read<int16_t>(argv[1], size_t(n) * dim);
        const auto centers = read<int16_t>(argv[2], size_t(256) * dim);
        const auto weights = read<double>(argv[3], dim);
        std::vector<uint8_t> codes(n);
        std::vector<double> losses(n);
        assign(values, centers, weights, n, dim, codes, losses);
        write(std::string(argv[6]) + ".codes.u8", codes);
        write(std::string(argv[6]) + ".losses.f64", losses);
        std::cout << "{\"rows\":" << n << ",\"dimension\":" << dim
                  << ",\"self_check_passed\":true}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
