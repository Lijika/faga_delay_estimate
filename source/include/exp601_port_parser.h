// Exact short-name index for the fixed embedded architecture.
#pragma once

struct PortSlot580 { uint64_t key = 0; int16_t port = -1; uint8_t length = 0; };
static PortSlot580 portSlots580[2048];

static inline uint64_t portKey580(std::string_view name) {
    uint32_t first, last;
    std::memcpy(&first, name.data(), 4);
    std::memcpy(&last, name.data() + name.size() - 4, 4);
    return (uint64_t(first) << 32) | last;
}

static inline unsigned portHash580(uint64_t key) {
    key ^= key >> 33;
    key *= 0xff51afd7ed558ccdULL;
    key ^= key >> 33;
    return unsigned(key) & 2047;
}

static void initializePorts580() {
    for (int p = 0; p < arch.portCount(); ++p) {
        const auto& name = arch.portName(p);
        require(name.size() >= 4 && name.size() <= 7, "short port length");
        const uint64_t key = portKey580(name);
        unsigned slot = portHash580(key);
        while (portSlots580[slot].port >= 0) slot = (slot + 1) & 2047;
        portSlots580[slot] = {key, int16_t(p), uint8_t(name.size())};
    }
}

static inline std::from_chars_result coordinate601(const char* at, const char* end, int& value) {
    if (end - at >= 4) {
        const unsigned a=unsigned(at[0])-'0', b=unsigned(at[1])-'0';
        const unsigned c=unsigned(at[2])-'0', d=unsigned(at[3])-'0';
        if (a < 10) {
            if (b >= 10) { value=int(a); return {at+1, std::errc{}}; }
            if (c >= 10) { value=int(10*a+b); return {at+2, std::errc{}}; }
            if (d >= 10) { value=int(100*a+10*b+c); return {at+3, std::errc{}}; }
        }
    }
    return std::from_chars(at,end,value);
}

static inline bool parsePin601(std::string_view text, int& x, int& y, int& port) {
    if (text.size() < 12 || text.compare(0, 4, "SRB_") != 0) return false;
    const char* at = text.data() + 4;
    const char* end = text.data() + text.size();
    if (*at < '0' || *at > '9') return false;
    int xx, yy;
    const auto a = coordinate601(at, end, xx);
    if (a.ec != std::errc{} || a.ptr == end || *a.ptr != '_') return false;
    at = a.ptr + 1;
    if (at == end || *at < '0' || *at > '9') return false;
    const auto b = coordinate601(at, end, yy);
    if (b.ec != std::errc{} || b.ptr == end || *b.ptr != '/') return false;
    const std::string_view name(b.ptr + 1, size_t(end - b.ptr - 1));
    if (name.size() < 4 || name.size() > 7) return false;
    const uint64_t key = portKey580(name);
    unsigned slot = portHash580(key);
    while (portSlots580[slot].port >= 0) {
        const auto& entry = portSlots580[slot];
        if (entry.key == key && entry.length == name.size()) {
            x = xx; y = yy; port = entry.port;
            return true;
        }
        slot = (slot + 1) & 2047;
    }
    return false;
}

static inline bool parsePin580(std::string_view text, int& x, int& y, int& port) {
#ifdef EXP601_VERIFY_PARSER
    int rx=x, ry=y, rp=port;
    const bool expected=arch.parsePin(text,rx,ry,rp);
#endif
    const bool actual=parsePin601(text,x,y,port);
#ifdef EXP601_VERIFY_PARSER
    require(actual==expected && x==rx && y==ry && port==rp, "short coordinate reference mismatch");
#endif
    return actual;
}

#ifdef EXP580_VERIFY_PARSER
static void verifyPorts580() {
    uint64_t checked = 0;
    for (int p = 0; p < arch.portCount(); ++p) {
        const auto& name = arch.portName(p);
        std::vector<std::string> names = {name, name.substr(0, name.size()-1), name + "X"};
        for (size_t j = 0; j < name.size(); ++j) {
            auto damaged = name; damaged[j] ^= 1; names.push_back(damaged);
        }
        for (const auto& candidate : names) {
            for (const auto& prefix : {"SRB_0_0/", "SRB_001_002/", "SRB_119_549/",
                 "SRB_2147483648_2/", "SRB_1_2147483648/", "SRB_-1_2/", "SRB_1_+2/",
                 "SRB__2/", "SRB_1_/", "SRB_1_2_3/", "SRB_1_2//"}) {
                const std::string text = std::string(prefix) + candidate;
                int ax=-7, ay=-8, ap=-9, bx=ax, by=ay, bp=ap;
                const bool a=arch.parsePin(text, ax, ay, ap), b=parsePin580(text, bx, by, bp);
                require(a == b && ax == bx && ay == by && ap == bp, "parser reference mismatch");
                ++checked;
            }
        }
    }
    require(checked > 40000, "parser coverage");
}
#endif
