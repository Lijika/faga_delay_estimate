// Keep complete input lines in the read buffer until the next call.
#pragma once

class CsvViewReader591 {
 public:
    explicit CsvViewReader591(const char* path) : file_(std::fopen(path, "rb"))
#ifdef EXP591_VERIFY_READER
        , reference_(path)
#endif
    {
        carry_.reserve(256);
#ifdef EXP591_VERIFY_READER
        reference_line_.reserve(256);
#endif
    }
    ~CsvViewReader591() { if (file_) std::fclose(file_); }
    CsvViewReader591(const CsvViewReader591&) = delete;
    CsvViewReader591& operator=(const CsvViewReader591&) = delete;
    bool good() const { return file_ != nullptr; }

    bool next(std::string_view& line) {
        const bool found = read(line);
#ifdef EXP591_VERIFY_READER
        const bool expected = reference_.next(reference_line_);
        require(found == expected && (!found || line == reference_line_), "reader reference mismatch");
#endif
        return found;
    }

    bool nextParsed(std::string_view& line, int32_t* q, bool first, bool& parsed) {
        parsed=false;
        const char* begin=buffer_.data()+pos_;
        const char* end=buffer_.data()+filled_;
        size_t consumed=0;
        if (row723(begin,end,q,consumed)) {
            line=std::string_view(begin,consumed-1);
            pos_+=consumed;
            parsed=true;
        } else if (first) {
            return next(line);
        } else {
            const char* nl=static_cast<const char*>(std::memchr(begin,'\n',size_t(end-begin)));
            if (!nl) return false;
            line=std::string_view(begin,size_t(nl-begin));
            pos_=size_t(nl-buffer_.data())+1;
            if (!line.empty() && line.back()=='\r') line.remove_suffix(1);
        }
#ifdef EXP591_VERIFY_READER
        require(reference_.next(reference_line_) && line==reference_line_, "parsed reader mismatch");
#endif
        return true;
    }

 private:
    bool read(std::string_view& line) {
        if (!file_) return false;
        carry_.clear();
        for (;;) {
            if (pos_ >= filled_) {
                filled_ = std::fread(buffer_.data(), 1, buffer_.size(), file_);
                pos_ = 0;
                if (filled_ == 0) {
                    line = carry_;
                    return !carry_.empty();
                }
            }
            const char* begin = buffer_.data() + pos_;
            const char* end = buffer_.data() + filled_;
            const char* nl = static_cast<const char*>(std::memchr(begin, '\n', size_t(end - begin)));
            if (nl) {
                if (carry_.empty()) line = std::string_view(begin, size_t(nl - begin));
                else {
                    carry_.append(begin, size_t(nl - begin));
                    line = carry_;
                }
                pos_ = size_t(nl - buffer_.data()) + 1;
                if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
                return true;
            }
            carry_.append(begin, size_t(end - begin));
            pos_ = filled_;
        }
    }

    std::FILE* file_;
    std::array<char, 1u << 20> buffer_;
    std::string carry_;
    size_t pos_ = 0, filled_ = 0;
#ifdef EXP591_VERIFY_READER
    delayest::LineReader reference_;
    std::string reference_line_;
#endif
};
