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

static uint32_t local_column(uint32_t column, unsigned& group) {
    const uint32_t tile = column / 552, cell = column % 552;
    const uint32_t x = cell / 46, y = cell % 46;
    group = x + y > 3;
    if (group == 0) return tile * 10 + x * (9 - x) / 2 + y;
    const uint32_t before = x < 4 ? (x + 1) * (8 - x) / 2 : 10;
    return tile * 542 + cell - before;
}

alignas(64) static double result[1000000];
static bool ports_seen[59904];

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: geometry-decode MODEL KEYS OUTPUT");
        return 0;
    }
    require(argc == 4, "arguments");
    uint64_t bytes;
    const auto* raw = mapped(argv[1], bytes);
    require(bytes >= 64 && std::memcmp(raw, "EX575Q01", 8) == 0, "model magic");
    const uint32_t rows = integer(raw + 8), columns = integer(raw + 12);
    const uint32_t rank[2] = {integer(raw + 16), integer(raw + 20)};
    const uint32_t count[2] = {integer(raw + 24), integer(raw + 28)};
    require(rows == 59904 && columns == 264960 && count[0] == 4800 && count[1] == 260160 &&
            (rank[0] == 96 || rank[0] == 128 || rank[0] == 192) && rank[1] == 96, "model shape");
    for (unsigned i = 32; i < 64; ++i) require(raw[i] == 0, "model padding");
    uint64_t expected = 64 + 2 * uint64_t(rows);
    for (unsigned g = 0; g < 2; ++g) expected += 8 * rank[g] + 2 * (uint64_t(rows) + count[g]) * rank[g];
    require(bytes == expected, "model length");
    const auto* at = raw + 64 + 2 * rows;
    const int16_t* left[2];
    const int16_t* right[2];
    double scale[2][192];
    for (unsigned g = 0; g < 2; ++g) {
        const auto* le = reinterpret_cast<const int32_t*>(at);
        left[g] = reinterpret_cast<const int16_t*>(le + rank[g]);
        const auto* re = reinterpret_cast<const int32_t*>(left[g] + uint64_t(rows) * rank[g]);
        right[g] = reinterpret_cast<const int16_t*>(re + rank[g]);
        at = reinterpret_cast<const unsigned char*>(right[g] + uint64_t(count[g]) * rank[g]);
        for (unsigned k = 0; k < rank[g]; ++k) {
            require(le[k] > -500 && le[k] < 500 && re[k] > -500 && re[k] < 500, "exponent range");
            scale[g][k] = std::ldexp(1., le[k] + re[k]);
            require(std::isfinite(scale[g][k]) && scale[g][k] > 0, "scale range");
        }
    }
    require(at == raw + bytes, "payload end");
    uint32_t counts[2]{};
    for (unsigned j = 0; j < columns; ++j) {
        unsigned group;
        const uint32_t local = local_column(j, group);
        require(local == counts[group]++, "geometry index order");
    }
    require(counts[0] == count[0] && counts[1] == count[1], "complete geometry index");
    const auto* keys = reinterpret_cast<const int32_t*>(mapped(argv[2], bytes));
    require(bytes == 8000000, "key length");
    const double start = cpu();
    for (unsigned i = 0; i < 1000000; ++i) {
        const int32_t p = keys[2 * i], j = keys[2 * i + 1];
        require(p >= 0 && p < int32_t(rows) && j >= 0 && j < int32_t(columns), "key range");
        ports_seen[p] = true;
        unsigned group;
        const uint32_t local = local_column(unsigned(j), group);
        require(local < count[group], "local key range");
        const auto* a = left[group] + uint64_t(p) * rank[group];
        const auto* b = right[group] + uint64_t(local) * rank[group];
        double value = 0.;
        for (unsigned k = 0; k < rank[group]; ++k)
            value += double(int32_t(a[k]) * int32_t(b[k])) * scale[group][k];
        require(std::isfinite(value), "nonfinite response");
        result[i] = value;
    }
    const double elapsed = cpu() - start;
    for (bool seen : ports_seen) require(seen, "full port coverage");
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
    std::printf("{\"rows\":1000000,\"port_pairs\":59904,\"kernel_cpu_s\":%.9f,\"production_timing\":false}\n", elapsed);
}
