# exp728 冻结阶段版源码

本目录对应 `exp728-coordinate-masks-generic-1b184s-20261025`，查询实现来自 exp727。逐文件来源见 [source-origin.json](provenance/source-origin.json)，编译参数及组件认证见 [exp727-freeze.json](provenance/exp727-freeze.json)。

## 独立构建

字节复现环境为 Ubuntu 22.04 x86-64、GCC 11.4.0 (`Ubuntu 11.4.0-1ubuntu1~22.04.3`)、binutils 2.38、glibc 2.35 (`Ubuntu GLIBC 2.35-0ubuntu3.15`) 和匹配的静态运行库。

```sh
cd source
python3 build.py
./build/estimate -in request.csv -out result.csv
```

脚本核对 `SHA256SUMS`、嵌入架构文本、五份目标文件、静态链接、十进制 100 MB 容量限制和最终 ELF SHA。输出为 `build/estimate`，报告为 `build/build-report.json`。其他工具链生成的程序需独立验收。

本轮已在 r9 的独立目录重建，五份对象与最终 ELF 都与冻结 exp728 逐字节相同，见 [standalone-build-r9.json](provenance/standalone-build-r9.json)。完整程序验收复用该 ELF 原有的 100M 和 1B 证据，本轮新增完整运行次数为零。

Zstandard 冻结库、头文件和许可证位于 `third_party/zstd/`。推理构建使用已冻结模型，无需安装 CatBoost 或重新训练。

## 当前实现

| 路径 | 作用 |
| --- | --- |
| `src/entry.cpp` | 固定通用 SSE2 worker，查询分配计数 |
| `src/worker.cpp` | 八行批处理、准备状态、背景和残差组合、完整 CSV 输出 |
| `src/architecture.cpp` | 有向完整端口图、真实 Net、Block 和 Line |
| `include/exp601_port_parser.h` | 已接入 exp704 的 688 槽直接端口目录 |
| `include/exp707_prepare_metadata.h` | 首 Net、Line、Block 与端口准备元数据 |
| `include/exp723_fused_parse.h`、`exp596_csv_batch.h` | CSV 扫描与端点解析融合 |
| `include/exp582_int8_geometry.h`、`exp608_geometry.h` | 近域 N512、远域四方向 D64 和点积 |
| `include/exp652_geometry_restore.h` | 启动时恢复压缩几何 |
| `include/exp652_distance_curve_lookup.h` | 远域完整 pair、方向和余类的距离曲线 |
| `include/symmetric640.h`、`reference727.h` | 当前 T2D6、76,526 B 坐标掩码及原等价参考 |
| `include/exp679_hv_events.h`、`replacement679.h` | V 事件及 V8 专家 |
| `models/T2D6-final-*.json` | 当前普通路径 16 个 route 的完整两树模型 |
| `models/V64-final.json` | V 专家冻结模型，部署前八棵 |
| `models/H64-final.json` | 原导出所附历史 H 模型，当前生产关闭 |
| `assets/D64-geometry.zst` | 56,503,992 B，恢复为 69,303,616 B |
| `assets/D64.curves.u8` | 29,308,992 B |
| `arch/`、`src/embedded_arch.cpp` | 五份官方 JSON 及嵌入文本 |

生产宏保留 `EXP640_TREES=8`、`EXP684_V_ONLY`、`EXP608_SIMD=0`。普通路径实际执行两棵 depth6 树；V 路径执行八棵 depth4 树。请结合实际调用及 `EXP579_AUDIT` 分支判断执行内容。旧 S16 参数已移至 `training/baselines/exp688/`，供历史配对重训使用。

汇编 `.incbin` 仅改为本目录相对路径，原文件仍在 `provenance/`。数值链保留原运算次序和舍入规则。当前查询 ELF 没有接入 exp716 ISA 分派。

## 冻结表现与边界

exp728 完整非重复 1B 的 CPU 为 184.190953 秒、wall 为 205.239648 秒、峰值 RSS 为 206,639,104 B，单线程。覆盖全部 59,904 个角色端口 pair，完整输出契约通过。3,833,856 条分层 exact 加权 Acc 为 98.6448996487895%。原结果见 [1b-report](provenance/exp728-1b-report.json)。

ELF 为 93,442,072 B，SHA-256 为

```text
9c05eb2ce01450f58ffa6d2adaa6793f307f44d8962a66e5d36453be32c5c68f
```

ZIP 为 81,350,223 B，SHA-256 为

```text
9bb01e1ca3c5a2e57f65a4ddc2408f537ff7e73dd31d6f54668c88e668618081
```

当前 Acc 仍低于 99%。1B 输入已有开发历史，当前 1B 运行只有一次。实机为 6226R，6242R、官方隐藏集、角色域外覆盖及其他 CPU 性能未验证。见 [提问书](../docs/exp728/exp728-外部AI提问书.md)和[完整研究复盘](../docs/research/exp707-732复盘与停止范围.md)。
