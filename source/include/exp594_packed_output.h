#pragma once

#ifdef EXP594_PACKED
struct PackedModel594 {
    uint32_t node[120];
    float value[128];
};
static constexpr auto packModels594() {
    std::array<PackedModel594, sizeof(kModels) / sizeof(kModels[0])> result{};
    for (unsigned m = 0; m < result.size(); ++m) {
        for (unsigned n = 0; n < 120; ++n)
            result[m].node[n] = uint32_t(uint16_t(kModels[m].threshold[n])) << 16 |
                                kModels[m].feature[n];
        for (unsigned n = 0; n < 128; ++n) result[m].value[n] = kModels[m].value[n];
    }
    return result;
}
alignas(64) static constexpr auto kPacked594 = packModels594();
#endif

#ifdef EXP594_WRITER
class RowWriter594 {
 public:
    explicit RowWriter594(FILE* file) : file_(file) {}
    bool write(const char* data, size_t length) {
        if (length > buffer_.size())
            return flush() && std::fwrite(data, 1, length, file_) == length;
        if (length > buffer_.size() - used_ && !flush()) return false;
        std::memcpy(buffer_.data() + used_, data, length);
        used_ += length;
        return true;
    }
    bool row(std::string_view text, int value) {
        if (text.size() > buffer_.size() - 24) {
            char number[24]; number[0] = ',';
            auto end = std::to_chars(number + 1, number + sizeof(number) - 1, value);
            if (end.ec != std::errc{}) return false;
            *end.ptr = '\n';
            return write(text.data(), text.size()) && write(number, size_t(end.ptr - number) + 1);
        }
        if (text.size() + 24 > buffer_.size() - used_ && !flush()) return false;
        char* at = buffer_.data() + used_;
        std::memcpy(at, text.data(), text.size()); at += text.size(); *at++ = ',';
        auto end = std::to_chars(at, buffer_.data() + buffer_.size() - 1, value);
        if (end.ec != std::errc{}) return false;
        *end.ptr++ = '\n';
        used_ = size_t(end.ptr - buffer_.data());
        return true;
    }
    bool flush() {
        if (!used_) return true;
        const bool ok = std::fwrite(buffer_.data(), 1, used_, file_) == used_;
        used_ = 0;
        return ok;
    }
 private:
    FILE* file_;
    std::array<char, 1u << 20> buffer_;
    size_t used_ = 0;
};
#endif
