#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
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

alignas(64) static double result[1000000];
static unsigned coverage[59904];

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: leaf-decode MODEL KEYS OUTPUT");
        return 0;
    }
    require(argc == 4, "arguments");
    uint64_t bytes;
    const auto* raw = mapped(argv[1], bytes);
    require(bytes >= 64 && std::memcmp(raw, "EX567L01", 8) == 0, "model magic");
    require(integer(raw+8) == 59904 && integer(raw+12) == 264960 &&
            integer(raw+16) == 8 && integer(raw+20) == 64, "model shape");
    const auto encoding = integer(raw+24);
    require(encoding <= 1, "model encoding");
    for (unsigned i = 28; i < 64; ++i) require(raw[i] == 0, "model padding");
    require(bytes == 64+119808+2119680+32+uint64_t(59904)*512*(encoding ? 2 : 8), "model length");
    const auto* leaf = raw+64+119808;
    const auto* exponent = reinterpret_cast<const int32_t*>(leaf+2119680);
    const auto* weights = reinterpret_cast<const int16_t*>(exponent+8);
    const auto* floating = reinterpret_cast<const double*>(exponent+8);
    double scale[8];
    for (unsigned t = 0; t < 8; ++t) {
        require(exponent[t] > -500 && exponent[t] < 500, "exponent range");
        scale[t] = std::ldexp(1., exponent[t]);
    }
    for (unsigned j = 0; j < 2119680; ++j) require(leaf[j] < 64, "leaf range");
    const auto* keys = reinterpret_cast<const int32_t*>(mapped(argv[2], bytes));
    require(bytes == 8000000, "key length");
    for (unsigned i = 0; i < 1000000; ++i) {
        const int p = keys[2*i], j = keys[2*i+1];
        require(p >= 0 && p < 59904 && j >= 0 && j < 264960, "key range");
        ++coverage[p];
        double value = 0.;
        for (unsigned t = 0; t < 8; ++t) {
            const uint64_t at = uint64_t(p)*512+64*t+leaf[uint64_t(j)*8+t];
            value += encoding ? double(weights[at])*scale[t] : floating[at];
        }
        require(std::isfinite(value), "finite response");
        result[i] = value;
    }
    for (unsigned p = 0; p < 59904; ++p) require(coverage[p] > 0, "full port-pair coverage");
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
    std::puts("{\"rows\":1000000,\"port_pairs\":59904,\"production_timing\":false}");
}
