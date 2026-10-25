#include <cstdint>
#include <omp.h>

// Offline fitting only; each worker owns a complete port-pair row.
extern "C" void aggregate(const int16_t* values, const int16_t* center,
                          const double* inverse, const uint8_t* leaves,
                          double* rhs, double* energy) {
    constexpr int rows = 59904, columns = 264960, trees = 8, width = 512;
    #pragma omp parallel for num_threads(8) schedule(static)
    for (int p = 0; p < rows; ++p) {
        const auto* row = values + uint64_t(p) * columns;
        double* output = rhs + uint64_t(p) * width;
        double squared = 0.;
        for (int j = 0; j < columns; ++j) {
            const double value = (int(row[j]) - int(center[p])) * inverse[j];
            squared += value * value;
            for (int t = 0; t < trees; ++t)
                output[64 * t + leaves[uint64_t(j) * trees + t]] += value;
        }
        energy[p] = squared;
    }
}
