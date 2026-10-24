# exp688 冻结提交版源码

本目录对应固定提交包 `exp688-v8-boundary-generic-1b243s-1965119f-dirty-20261025-0035`，
查询实现为 exp686/N。代码、五份 SRB 架构、模型参数及固定资产均取自已测构建，
逐文件来源见 `provenance/source-origin.json`。`SHA256SUMS` 核对本目录的归档内容。

## 独立重建

复现环境为 Ubuntu 22.04 x86-64、GCC 11.4.0
(`Ubuntu 11.4.0-1ubuntu1~22.04.3`)、binutils 2.38、glibc 2.35
(`Ubuntu GLIBC 2.35-0ubuntu3.15`)。安装相应静态 C/C++ 运行库后执行

```sh
cd source
python3 build.py
./build/estimate -in request.csv -out result.csv
```

脚本使用 Python 3 标准库，检查归档 SHA、嵌入架构文本、静态链接及十进制
100 MB 容量限制，并逐一比较五份目标文件和最终 ELF 的完整 SHA。
构建结果写入 `build/estimate`，报告写入 `build/build-report.json`。
相同工具链用于字节复现；其他工具链生成的程序需要独立验收。

本快照已在 r9 的独立目录重建，五份目标文件和最终 ELF 均与冻结版本
逐字节一致，记录见 `provenance/standalone-build-r9.json`。
提交 ZIP 中的 `bin/estimate` 也已按完整 SHA 与重建结果核对，
记录见 `provenance/publication-verification.json`。本次复用原 100M 和 1B 验收，
新增完整估计程序运行次数为零。

Zstandard 的冻结静态库、头文件和许可证位于 `third_party/zstd/`，
其身份来自原发布构建。程序启动时单线程恢复几何数据。
构建使用已提供的模型参数，无需安装 CatBoost、XGBoost 或重新训练。

## 实现与资产

| 路径 | 作用 |
| --- | --- |
| `src/entry.cpp` | 固定选择通用 SSE2 查询入口，并统计查询阶段的动态分配 |
| `src/worker.cpp` | 批 8 解析、首 Net 对齐、特征计算、模型选择、预测和完整 CSV 输出 |
| `src/architecture.cpp` | 有向端口图、真实 Net 落点、Block 和 Line 规则 |
| `include/exp601_port_parser.h` | exp688 使用的短端口名哈希解析 |
| `include/exp582_int8_geometry.h`、`include/exp608_geometry.h` | 近域 N512 和远域四方向 D64 背景的寻址及点积 |
| `include/exp652_geometry_restore.h` | Zstandard 几何资产恢复 |
| `include/exp652_distance_curve_lookup.h` | 远域完整端口对、方向和余类对应的二维距离曲线修正 |
| `include/symmetric640.h` | 16 路对称树修正，生产配置每次使用 8 棵 |
| `include/exp679_hv_events.h`、`include/replacement679.h` | V 事件判定及独立函数中的 8 棵专家树 |
| `assets/D64-geometry.zst` | 56,503,992 B 的压缩背景，恢复为 69,303,616 B |
| `assets/D64.curves.u8` | 29,308,992 B 的字节曲线资产 |
| `models/` | 原始 S16 和 H64/V64 模型 JSON，便于检查导出参数 |
| `arch/`、`src/embedded_arch.cpp` | 五份官方 JSON 及嵌入文本 |
| `provenance/` | 冻结编译、源文件身份、提交包身份与验收记录 |

生产宏为 `EXP640_TREES=8`、`EXP684_V_ONLY`、`EXP608_SIMD=0`。
S16 模型只使用前 8 棵，V64 专家只使用前 8 棵；H 专家在此构建中关闭。
原始生成头文件保留审计分支，`EXP579_AUDIT` 下的历史输出路径属于离线检查。
生产构建使用 `build.py` 固定参数。

汇编文件只将 `.incbin` 的机器绝对路径替换为本目录相对路径，
原文件保存在 `provenance/original-compressed.S` 和 `original-codes.S`。
查询代码、模型常数、计算顺序与舍入规则保持冻结状态。

## 已有完整测试

exp688 在 r9 Xeon 完成全端口、非重复 1B，CPU 243.302538 秒，
wall 269.009493 秒，峰值 RSS 206,372,864 B，单线程。
同次输出中每个端口对抽 64 条，共 3,833,856 条 exact 样本，
人口加权 Acc 为 98.658061657%。输入曾用于历史版本验证；
完整输出契约已检查，评分范围是上述分层样本。

冻结 ELF 为 93,402,392 B，SHA-256 为

```text
66fb0307d24b4ce2fa4514350e97420acf9de37171419f15c6001ac15dc985e3
```

固定提交 ZIP 为 81,369,669 B，SHA-256 为

```text
fb39a2476d0d2ea99d2cf6c29536a63383bfed0a8174505db1a5f8c601a5f94c
```

比赛平台成绩、其他 CPU 表现和全量 1B exact 精度仍待验证。
最终目标为总体 Acc 严格大于 99%，1B CPU 小于 200 秒并争取约 100 秒。
历史验收记录与后续研究进展分别见根目录的 `experiment/` 和 `docs/exp688/`。
