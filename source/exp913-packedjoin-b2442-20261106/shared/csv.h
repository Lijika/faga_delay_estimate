// Streaming CSV adapter.  The adapter owns file I/O and text preservation; it
// knows nothing about how a delay is computed.
#pragma once

#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

namespace delayest {

// Reads a file line by line with a private buffer; no row is ever retained.
class LineReader {
 public:
  explicit LineReader(const std::string& path, size_t bufferSize = 1u << 20) {
    file_ = std::fopen(path.c_str(), "rb");
    if (file_) buffer_.resize(bufferSize);
  }
  ~LineReader() {
    if (file_) std::fclose(file_);
  }
  LineReader(const LineReader&) = delete;
  LineReader& operator=(const LineReader&) = delete;

  bool good() const { return file_ != nullptr; }

  // Returns false at end of file.  The line excludes '\n' and '\r'.
  bool next(std::string& line) {
    if (!file_) return false;
    line.clear();
    for (;;) {
      if (pos_ >= filled_) {
        filled_ = std::fread(buffer_.data(), 1, buffer_.size(), file_);
        pos_ = 0;
        if (filled_ == 0) return !line.empty();
      }
      const char* begin = buffer_.data() + pos_;
      const char* end = buffer_.data() + filled_;
      const char* nl = static_cast<const char*>(std::memchr(begin, '\n', static_cast<size_t>(end - begin)));
      if (nl) {
        line.append(begin, static_cast<size_t>(nl - begin));
        pos_ = static_cast<size_t>(nl - buffer_.data()) + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        return true;
      }
      line.append(begin, static_cast<size_t>(end - begin));
      pos_ = filled_;
    }
  }

 private:
  std::FILE* file_ = nullptr;
  std::vector<char> buffer_;
  size_t pos_ = 0;
  size_t filled_ = 0;
};

// Buffered writer that flushes large blocks to a FILE*.
class BufferedWriter {
 public:
  explicit BufferedWriter(std::FILE* file, size_t flushThreshold = 1u << 20)
      : file_(file), threshold_(flushThreshold) {
    buffer_.reserve(flushThreshold + 4096);
  }

  bool write(const char* data, size_t length) {
    buffer_.append(data, length);
    if (buffer_.size() >= threshold_) return flush();
    return true;
  }
  bool write(const std::string& text) { return write(text.data(), text.size()); }

  bool flush() {
    if (buffer_.empty()) return true;
    const size_t written = std::fwrite(buffer_.data(), 1, buffer_.size(), file_);
    const bool ok = written == buffer_.size();
    buffer_.clear();
    return ok;
  }

 private:
  std::FILE* file_ = nullptr;
  std::string buffer_;
  size_t threshold_ = 1u << 20;
};

// Whitespace trimming without a copy; callers that need a std::string use trim() below.
inline std::string_view trimView(std::string_view text) {
  size_t begin = 0;
  size_t end = text.size();
  while (begin < end && (text[begin] == ' ' || text[begin] == '\t' || text[begin] == '\r' || text[begin] == '\n')) ++begin;
  while (end > begin && (text[end - 1] == ' ' || text[end - 1] == '\t' || text[end - 1] == '\r' || text[end - 1] == '\n')) --end;
  return text.substr(begin, end - begin);
}

inline std::string trim(const std::string& text) { return std::string(trimView(text)); }

}  // namespace delayest
