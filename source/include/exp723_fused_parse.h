#pragma once

template<char Delimiter>
static inline bool pin723(const char*& at, const char* end, int& x, int& y, int& port) {
    if (end-at < 12 || std::memcmp(at, "SRB_", 4) != 0) return false;
    at += 4;
    if (*at < '0' || *at > '9') return false;
    const auto a = coordinate601(at, end, x);
    if (a.ec != std::errc{} || a.ptr == end || *a.ptr != '_') return false;
    at = a.ptr+1;
    if (at == end || *at < '0' || *at > '9') return false;
    const auto b = coordinate601(at, end, y);
    if (b.ec != std::errc{} || b.ptr == end || *b.ptr != '/') return false;
    const char* name = b.ptr+1;
    // A complete maximum-length port and its delimiter must be readable.
    if (end-name < 8) return false;
    unsigned length = 4;
    while (length < 8 && name[length] != Delimiter) ++length;
    if (length == 8) return false;
    const std::string_view text(name, length);
    const auto& entry = portSlots580[portIndex704(text)];
    if (entry.port < 0 || entry.length != length || entry.key != portKey580(text)) return false;
    port = entry.port;
    at = name+length+1;
    return true;
}

static inline bool row723(const char* begin, const char* end, int32_t* q, size_t& consumed) {
    const char* at = begin;
    if (!pin723<','>(at, end, q[0], q[1], q[8]) ||
        !pin723<'\n'>(at, end, q[2], q[3], q[9])) return false;
    consumed = size_t(at-begin);
    return true;
}
