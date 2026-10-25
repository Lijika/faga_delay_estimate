#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>

static void require(bool ok, const char* text) {
    if (!ok) throw std::runtime_error(text);
}

template<class T> static void read(FILE* f, std::vector<T>& value) {
    require(std::fread(value.data(), sizeof(T), value.size(), f) == value.size(), "truncated input");
}

static FILE* open(const char* name) {
    FILE* f = std::fopen(name, "rb");
    require(f != nullptr, "cannot open input");
    return f;
}

static void end(FILE* f) {
    require(std::fgetc(f) == EOF && !std::ferror(f), "trailing data or read error");
    require(std::fclose(f) == 0, "close input");
}

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
        std::puts("usage: trend-decode MODEL KEYS OUTPUT");
        return 0;
    }
    try {
        require(argc == 4, "arguments");
        FILE* f = open(argv[1]);
        char magic[8]; uint32_t shape[3];
        require(std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "EX510Q01", 8) == 0, "magic");
        require(std::fread(shape, 4, 3, f) == 3, "shape");
        require(shape[0] == 59904 && shape[1] == 264960 && shape[2] == 96, "model shape");
        std::vector<int32_t> le(96), re(96);
        std::vector<int16_t> left(size_t(shape[0]) * 96), right(size_t(shape[1]) * 96);
        read(f, le); read(f, left); read(f, re); read(f, right); end(f);
        std::vector<int32_t> keys(2000000);
        f = open(argv[2]); read(f, keys); end(f);
        std::vector<double> result(1000000);
        for (size_t i = 0; i < result.size(); ++i) {
            int32_t row = keys[2 * i], column = keys[2 * i + 1];
            require(row >= 0 && row < 59904 && column >= 0 && column < 264960, "key range");
            double value = 0.;
            for (size_t k = 0; k < 96; ++k)
                value += std::ldexp(double(left[size_t(row) * 96 + k]), le[k]) *
                         std::ldexp(double(right[size_t(column) * 96 + k]), re[k]);
            require(std::isfinite(value), "nonfinite response");
            result[i] = value;
        }
        f = std::fopen(argv[3], "wbx");
        require(f != nullptr, "output exists or cannot create");
        require(std::fwrite(result.data(), sizeof(double), result.size(), f) == result.size(), "write");
        require(std::fclose(f) == 0, "close output");
    } catch (const std::exception& e) {
        std::fprintf(stderr, "%s\n", e.what());
        return 1;
    }
}
