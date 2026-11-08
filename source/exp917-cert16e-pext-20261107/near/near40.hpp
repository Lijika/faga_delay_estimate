#pragma once
#include <cstdint>

// The key is ((source_role * 288 + target_role) * 480 + context).
// context = direction*120 + (abs(dx)%10)*12 + abs(dy)%12.
// j = qx*8+qy; qx=0..4, qy=0..7. Every raw value equals true nominal E minus
// 125*qx + (dy<0 ? 125 : 127)*qy. No parent model or physical boundary included.
namespace near40 {
constexpr unsigned KeysPerSource = 288*480;
using SourceReady = void (*)(unsigned source, void* user);
// Single-shot and single-thread. In streaming mode raw() is valid inside
// SourceReady only for its current group of eight. Retain mode retains all keys.
// use_avx2 requires caller-validated CPU support and applies only to retain mode.
namespace nearpack {struct Line {uint16_t low;uint8_t d[40];};struct Extra{uint64_t hi[3];};}
struct NativeView {const nearpack::Line* rows;const nearpack::Extra*const* planes;};
NativeView nativeRows(unsigned source);
void useTiledRows();
void initialize(SourceReady on_source = nullptr, void* user = nullptr, bool retain = true, bool use_avx2 = false);
// Fast-only: call in source order after the final load40/raw read for each source.
void releaseMaterialized(unsigned source);
int raw(unsigned key,unsigned j) noexcept;
void load40(uint32_t key,int16_t out[40]) noexcept;
}
