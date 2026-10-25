// Minimal, dependency-free JSON reader for the five SRB architecture files.
// Only the subset needed by the architecture format is supported: objects,
// arrays, strings, numbers, booleans and null.  Values are stored in an arena
// so the whole document can be released with one delete.
#pragma once

#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace jsonlite {

struct Value;
using ValuePtr = Value*;

struct Member {
  std::string key;
  ValuePtr value;
};

struct Value {
  enum class Kind : uint8_t { Null, Bool, Number, String, Array, Object };
  Kind kind = Kind::Null;
  bool boolean = false;
  double number = 0.0;
  std::string text;             // string value or object key holder
  std::vector<ValuePtr> items;  // array elements
  std::vector<Member> members;  // object members

  bool isObject() const { return kind == Kind::Object; }
  bool isArray() const { return kind == Kind::Array; }
  bool isNumber() const { return kind == Kind::Number; }
  bool isString() const { return kind == Kind::String; }

  // Object lookup; returns nullptr when absent.
  ValuePtr find(const std::string& key) const {
    for (const Member& m : members)
      if (m.key == key) return m.value;
    return nullptr;
  }
  ValuePtr findAny(std::initializer_list<const char*> keys) const {
    for (const char* k : keys)
      if (ValuePtr v = find(k)) return v;
    return nullptr;
  }
  long asInt(long fallback = 0) const {
    return kind == Kind::Number ? static_cast<long>(number + (number < 0 ? -0.5 : 0.5)) : fallback;
  }
  double asDouble(double fallback = 0) const { return kind == Kind::Number ? number : fallback; }
  const std::string& asString() const { return text; }

  ValuePtr at(size_t i) const { return i < items.size() ? items[i] : nullptr; }
};

// Owns the arena and exposes the root value.
class Document {
 public:
  Document() = default;
  Document(const Document&) = delete;
  Document& operator=(const Document&) = delete;
  Document(Document&&) = default;
  Document& operator=(Document&&) = default;

  static Document parse(const std::string& content) {
    Document doc;
    doc.pool_ = std::make_unique<Pool>();
    size_t pos = 0;
    doc.root_ = doc.parseValue(content, pos);
    doc.skipWhitespace(content, pos);
    if (pos != content.size()) throw std::runtime_error("trailing content in JSON document");
    return doc;
  }

  ValuePtr root() const { return root_; }

 private:
  struct Pool {
    std::vector<std::unique_ptr<Value>> values;
    ValuePtr make() {
      values.push_back(std::make_unique<Value>());
      return values.back().get();
    }
  };
  std::unique_ptr<Pool> pool_;
  ValuePtr root_ = nullptr;

  ValuePtr makeValue() { return pool_->make(); }

  static bool isSpace(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }

  void skipWhitespace(const std::string& s, size_t& pos) const {
    while (pos < s.size() && isSpace(s[pos])) ++pos;
  }

  [[noreturn]] void fail(const char* what) const { throw std::runtime_error(std::string("JSON parse error: ") + what); }

  ValuePtr parseValue(const std::string& s, size_t& pos) {
    skipWhitespace(s, pos);
    if (pos >= s.size()) fail("unexpected end of input");
    char c = s[pos];
    switch (c) {
      case '{': return parseObject(s, pos);
      case '[': return parseArray(s, pos);
      case '"': {
        ValuePtr v = makeValue();
        v->kind = Value::Kind::String;
        v->text = parseString(s, pos);
        return v;
      }
      case 't': case 'f': case 'n': return parseKeyword(s, pos);
      default: return parseNumber(s, pos);
    }
  }

  ValuePtr parseObject(const std::string& s, size_t& pos) {
    ValuePtr v = makeValue();
    v->kind = Value::Kind::Object;
    ++pos;  // '{'
    skipWhitespace(s, pos);
    if (pos < s.size() && s[pos] == '}') { ++pos; return v; }
    while (true) {
      skipWhitespace(s, pos);
      if (pos >= s.size() || s[pos] != '"') fail("expected object key");
      Member m;
      m.key = parseString(s, pos);
      skipWhitespace(s, pos);
      if (pos >= s.size() || s[pos] != ':') fail("expected ':'");
      ++pos;
      m.value = parseValue(s, pos);
      v->members.push_back(std::move(m));
      skipWhitespace(s, pos);
      if (pos >= s.size()) fail("unterminated object");
      if (s[pos] == ',') { ++pos; continue; }
      if (s[pos] == '}') { ++pos; return v; }
      fail("expected ',' or '}'");
    }
  }

  ValuePtr parseArray(const std::string& s, size_t& pos) {
    ValuePtr v = makeValue();
    v->kind = Value::Kind::Array;
    ++pos;  // '['
    skipWhitespace(s, pos);
    if (pos < s.size() && s[pos] == ']') { ++pos; return v; }
    while (true) {
      v->items.push_back(parseValue(s, pos));
      skipWhitespace(s, pos);
      if (pos >= s.size()) fail("unterminated array");
      if (s[pos] == ',') { ++pos; continue; }
      if (s[pos] == ']') { ++pos; return v; }
      fail("expected ',' or ']'");
    }
  }

  std::string parseString(const std::string& s, size_t& pos) {
    std::string out;
    ++pos;  // opening quote
    while (pos < s.size()) {
      char c = s[pos++];
      if (c == '"') return out;
      if (c != '\\') { out.push_back(c); continue; }
      if (pos >= s.size()) fail("unterminated escape");
      char e = s[pos++];
      switch (e) {
        case '"': out.push_back('"'); break;
        case '\\': out.push_back('\\'); break;
        case '/': out.push_back('/'); break;
        case 'b': out.push_back('\b'); break;
        case 'f': out.push_back('\f'); break;
        case 'n': out.push_back('\n'); break;
        case 'r': out.push_back('\r'); break;
        case 't': out.push_back('\t'); break;
        case 'u': {
          if (pos + 4 > s.size()) fail("bad \\u escape");
          unsigned code = 0;
          for (int i = 0; i < 4; ++i) {
            char h = s[pos++];
            code <<= 4;
            if (h >= '0' && h <= '9') code |= unsigned(h - '0');
            else if (h >= 'a' && h <= 'f') code |= unsigned(h - 'a' + 10);
            else if (h >= 'A' && h <= 'F') code |= unsigned(h - 'A' + 10);
            else fail("bad hex digit");
          }
          // Encode as UTF-8; surrogate pairs are not needed by this format.
          if (code < 0x80) {
            out.push_back(char(code));
          } else if (code < 0x800) {
            out.push_back(char(0xC0 | (code >> 6)));
            out.push_back(char(0x80 | (code & 0x3F)));
          } else {
            out.push_back(char(0xE0 | (code >> 12)));
            out.push_back(char(0x80 | ((code >> 6) & 0x3F)));
            out.push_back(char(0x80 | (code & 0x3F)));
          }
          break;
        }
        default: fail("unknown escape");
      }
    }
    fail("unterminated string");
  }

  ValuePtr parseKeyword(const std::string& s, size_t& pos) {
    ValuePtr v = makeValue();
    if (s.compare(pos, 4, "true") == 0) {
      v->kind = Value::Kind::Bool; v->boolean = true; pos += 4; return v;
    }
    if (s.compare(pos, 5, "false") == 0) {
      v->kind = Value::Kind::Bool; v->boolean = false; pos += 5; return v;
    }
    if (s.compare(pos, 4, "null") == 0) {
      v->kind = Value::Kind::Null; pos += 4; return v;
    }
    fail("invalid keyword");
  }

  ValuePtr parseNumber(const std::string& s, size_t& pos) {
    size_t start = pos;
    if (pos < s.size() && (s[pos] == '-' || s[pos] == '+')) ++pos;
    while (pos < s.size() && ((s[pos] >= '0' && s[pos] <= '9') || s[pos] == '.' || s[pos] == 'e' || s[pos] == 'E' ||
                              s[pos] == '-' || s[pos] == '+'))
      ++pos;
    if (pos == start) fail("invalid number");
    ValuePtr v = makeValue();
    v->kind = Value::Kind::Number;
    v->number = std::stod(s.substr(start, pos - start));
    return v;
  }
};

}  // namespace jsonlite
