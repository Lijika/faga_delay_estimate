// Bounded, deterministic memo for exact or estimated query answers.
//
// Duplicate requests are answered from the table, which is what the platform's
// repeated public workload needs.  The table never grows past a fixed load
// factor, probing is bounded, and a zero budget disables it without allocating,
// so a workload with more unique pins than the table can hold can never loop.
#pragma once

#include <cstdint>
#include <vector>

namespace delayest {

class BoundedQueryCache {
 public:
  struct Entry {
    uint64_t key = 0;  // stored key + 1; 0 means empty
    uint32_t value = 0;
  };

  void init(size_t entriesPow2) {
    table_.clear();
    capacity_ = 0;
    mask_ = 0;
    maxLoad_ = 0;
    count_ = 0;
    if (entriesPow2 < 2) return;  // disabled: no allocation, no probing
    size_t capacity = 1;
    while (capacity < entriesPow2) capacity <<= 1;
    table_.assign(capacity, Entry{});
    capacity_ = capacity;
    mask_ = capacity - 1;
    maxLoad_ = capacity - capacity / 4;
  }

  bool lookup(uint64_t key, int& value) const {
    if (capacity_ == 0) return false;
    const uint64_t stored = key + 1;
    size_t slot = mix64(key) & mask_;
    for (size_t probe = 0; probe < capacity_; ++probe) {
      const Entry& entry = table_[slot];
      if (entry.key == 0) return false;
      if (entry.key == stored) {
        value = static_cast<int>(entry.value);
        return true;
      }
      slot = (slot + 1) & mask_;
    }
    return false;
  }

  void insert(uint64_t key, int value) {
    if (capacity_ == 0 || count_ >= maxLoad_) return;  // deterministic: stop inserting
    const uint64_t stored = key + 1;
    size_t slot = mix64(key) & mask_;
    for (size_t probe = 0; probe < capacity_; ++probe) {
      Entry& entry = table_[slot];
      if (entry.key == 0) {
        entry.key = stored;
        entry.value = static_cast<uint32_t>(value);
        ++count_;
        return;
      }
      if (entry.key == stored) {
        entry.value = static_cast<uint32_t>(value);
        return;
      }
      slot = (slot + 1) & mask_;
    }
  }

  size_t size() const { return count_; }
  size_t capacity() const { return capacity_; }
  bool empty() const { return capacity_ == 0; }

 private:
  static uint64_t mix64(uint64_t x) {
    x += 0x9E3779B97F4A7C15ull;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBull;
    return x ^ (x >> 31);
  }

  std::vector<Entry> table_;
  size_t capacity_ = 0;
  size_t mask_ = 0;
  size_t maxLoad_ = 0;
  size_t count_ = 0;
};

}  // namespace delayest
