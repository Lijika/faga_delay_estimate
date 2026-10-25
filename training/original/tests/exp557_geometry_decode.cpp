#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "%s\n", why); _exit(1); }
}

static const unsigned char* mapped(const char* path, uint64_t& bytes) {
    const int fd = open(path, O_RDONLY);
    struct stat info{};
    require(fd >= 0 && fstat(fd, &info) == 0 && info.st_size > 0, "open input");
    bytes = uint64_t(info.st_size);
    void* address = mmap(nullptr, bytes, PROT_READ, MAP_PRIVATE, fd, 0);
    require(address != MAP_FAILED && close(fd) == 0, "map input");
    return static_cast<const unsigned char*>(address);
}

static uint32_t integer(const unsigned char* p) {
    uint32_t value;
    std::memcpy(&value, p, 4);
    return value;
}

static double cpu() {
    timespec stamp{};
    require(clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &stamp) == 0, "clock");
    return double(stamp.tv_sec) + double(stamp.tv_nsec) * 1e-9;
}

alignas(64) static double result[1000000];

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: geometry-decode MODEL KEYS OUTPUT");
        return 0;
    }
    require(argc == 4, "arguments");
    uint64_t bytes;
    const auto* raw = mapped(argv[1], bytes);
    require(bytes >= 64 && std::memcmp(raw, "EX557Q01", 8) == 0, "model magic");
    const uint32_t rows = integer(raw + 8), columns = integer(raw + 12);
    const uint32_t regions = integer(raw + 16), rank = integer(raw + 20);
    require(rows == 59904 && columns == 264960 && regions >= 1 && regions <= 4 &&
            (rank == 64 || rank == 96), "model shape");
    for (unsigned i = 24; i < 64; ++i) require(raw[i] == 0, "model padding");
    const uint64_t expected = 64 + 2 * uint64_t(rows) + columns + 8 * rank +
                              2 * (uint64_t(regions) * rows + columns) * rank;
    require(bytes == expected, "model length");
    const auto* group = raw + 64 + 2 * rows;
    const auto* le = reinterpret_cast<const int32_t*>(group + columns);
    const auto* left = reinterpret_cast<const int16_t*>(le + rank);
    const auto* re = reinterpret_cast<const int32_t*>(left + uint64_t(regions) * rows * rank);
    const auto* right = reinterpret_cast<const int16_t*>(re + rank);
    for (unsigned j = 0; j < columns; ++j) require(group[j] < regions, "region range");
    double scale[96];
    for (unsigned k = 0; k < rank; ++k) {
        require(le[k] > -500 && le[k] < 500 && re[k] > -500 && re[k] < 500, "exponent range");
        scale[k] = std::ldexp(1., le[k] + re[k]);
        require(std::isfinite(scale[k]) && scale[k] > 0, "scale range");
    }
    const auto* keys = reinterpret_cast<const int32_t*>(mapped(argv[2], bytes));
    require(bytes == 8000000, "key length");
    const double start = cpu();
    for (unsigned i = 0; i < 1000000; ++i) {
        const int32_t p = keys[2 * i], j = keys[2 * i + 1];
        require(p >= 0 && p < int32_t(rows) && j >= 0 && j < int32_t(columns), "key range");
        const auto* a = left + (uint64_t(group[j]) * rows + unsigned(p)) * rank;
        const auto* b = right + uint64_t(j) * rank;
        double value = 0.;
        for (unsigned k = 0; k < rank; ++k)
            value += double(int32_t(a[k]) * int32_t(b[k])) * scale[k];
        require(std::isfinite(value), "nonfinite response");
        result[i] = value;
    }
    const double elapsed = cpu() - start;
    const int fd = open(argv[3], O_WRONLY | O_CREAT | O_EXCL, 0600);
    require(fd >= 0, "output exists or cannot create");
    const auto* p = reinterpret_cast<const unsigned char*>(result);
    size_t remaining = sizeof(result);
    while (remaining) {
        const ssize_t done = write(fd, p, remaining);
        require(done > 0, "output write");
        p += done; remaining -= size_t(done);
    }
    require(close(fd) == 0, "output close");
    std::printf("{\"rows\":1000000,\"kernel_cpu_s\":%.9f,\"production_timing\":false}\n", elapsed);
}
