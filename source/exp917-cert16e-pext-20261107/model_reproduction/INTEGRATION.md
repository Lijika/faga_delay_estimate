# exp855 模型资产复现源码接入

2026-11-05 按用户要求补入正式源码及
`subm/versions/exp855-gpt-pro-fast-generic-20261105/source/model_reproduction/`。
来源为 `subm/gpt_pro/FPGA-model-assets-reproduction-kit/model-assets-reproduction/`。
原包 52 个文件共 7,861,814 B，包括 `build/exp483/solver.hpp` 与
`build/exp499/roles.hpp` 两个求解器头文件。接入时先逐项保留；补齐 EAT117 后，
其中 `sources/repro/inputs/trace.py` 按该版本适配，另外 51 项保持原字节。
原包身份和适配文件身份分别记录在 `origin.json`。

这些文件用于离线生成。正式 `build.py` 继续读取既有 `model/`、`near/` 和
`shared/`，本次接入仅补充源码与说明。正式 ELF 为 99,418,200 B，SHA-256 为
`4674fd2846a3e029cc6f0812da097a38c29b43e258dd86777996ebb0eda648fc`。
本次按要求跳过编译、训练、推理运行和提交 ZIP 生成。

| 用途 | 源码入口 | 输入与输出 |
| --- | --- | --- |
| 整源名义距离场 | `sources/repro/nominal_source/build.sh`、`tests/exp499_full_residue_field.cpp` | 五份架构 JSON → 四份各 152,618,144 B 的训练场 |
| 锚点与插值系数 | `sources/knots/fit.py` | 训练场 → 各方向的观测点与回归 NPZ |
| 码本训练与码流生成 | `sources/knots/encode_rates.py`、`export.cpp` | 训练场、观测 NPZ、公开请求角色频率 → `books.npz` 与 832 个压缩帧 |
| 三资产导出 | `tools/pack_assets.py` | 832 帧、码本 NPZ、五份 JSON → `frames.bin`、`books.f32`、`arch.bin`、`frameBytes.inc` |
| 冻结表核对 | `tools/check_frozen_tables.py` | 八份冻结 NPZ → 与六张正式 `*.inc` 逐文本字节比较 |
| 完整训练入口 | `tools/full_train.sh` | 随包 `sources/eat117/`、工作目录、`inputs/cohort.csv.gz` → 新模型资产 |

算法说明和上游验证范围保留在
[`三项模型资产的算法与完整复现报告.md`](三项模型资产的算法与完整复现报告.md)。
`receipts/` 是原包的历史收据。本次接入检查记录在主仓库
`validation/results/exp855-model-reproduction/`，两次检查的身份分别保存。

从仓库根目录复现冻结资产时，可使用以下命令。输出写入项目 `build/`；
执行前应按项目约定检查宿主盘余量。依赖为 Python、NumPy、系统 `zstd` 和 `libzstd.so.1`。

```bash
REPRO="$PWD/src/gpt_pro_fast/model_reproduction"
WORK="$PWD/build/gpt-pro-model-assets"
python3 -B "$REPRO/tools/split_frames.py" \
  --frames "$PWD/src/gpt_pro_fast/model/frames.bin" \
  --lengths "$PWD/src/gpt_pro_fast/shared/frameBytes.inc" \
  --out "$WORK/wire" --reencode
python3 -B "$REPRO/tools/pack_assets.py" \
  --wire-dir "$WORK/wire" --out "$WORK/model" --compare-frozen
python3 -B "$REPRO/tools/check_frozen_tables.py" \
  --inc-dir "$PWD/src/gpt_pro_fast/shared"
```

该流程从冻结 `frames.bin` 拆出码流，再从冻结码本和原始 JSON 生成三个文件。
其验证范围是编码格式与发布字节。历史收据记录三资产 SHA 一致；从原始图重新训练
120 组码本并生成全部 832 帧的完整过程仍待实跑。

完整训练依赖的 EAT117 源树及 `assets/surface779/` 已从本地补齐。历史 Git 提交为
`b6fa91570c193548bf8e3b311912e9a4d0ab47f0`，`source/` 子树为
`a31d2d4fde17ba27137e351d5f3eead02cb50ecf`，对应 2026-11-02 的 EAT117。
源树、资产和追踪脚本的适配以此身份固定。原包的追踪脚本包含 EAT243 专有引用，
其完整训练命令同时指定了 EAT117 的 `surface779` 布局，本次按 EAT117 统一。

| 补入内容 | 当前相对路径 | 数量与大小 | 本地来源 |
| --- | --- | --- | --- |
| EAT117 完整 `source/` | `sources/eat117/` | 248 文件，95,273,523 B | 正式 EAT117 源码、本地 Git 历史及已有架构 JSON |
| 上一行包含的曲面资产 | `sources/eat117/assets/surface779/` | 210 帧，82,872,955 B | `/home/lhjysyx/EDA2026_EAT_eval_data/assets/` |
| 完整公开 cohort | `inputs/cohort.csv.gz` | 1,000,000 行；压缩 14,872,894 B；展开 42,333,955 B | 原 GPT Pro 自包含源码包的 `validation/public/` |
| 历史来源与检查清单 | `receipts/eat117-*.json` | 历史源码、资产、身份、导出验收和本地文件来源共 5 份 | 本地 Git 历史及本轮检查 |

248 项文件已逐项核对 Git blob 身份，32 项历史构建输入和 210 帧另与历史 SHA-256 清单核对。
五份 JSON 与 `raw_arch/` 相同；208 个源与 288 个目标的角色顺序分别与
`sources.ids`、`targets.oldidx` 相同。完整来源见 `receipts/eat117-local-files.json`。
本轮文件下载次数为 0。补入源码与版本归档之间的冻结文件采用只读硬链接以节省空间；
它们已存于本仓库内，外部 EAT 资产目录可保持只读。

在正式工作源码中，完整训练的调用格式如下。归档目录的运行方式是先复制为可写副本，
再将 `REPRO` 指向副本里的 `source/model_reproduction`。

```bash
REPRO="$PWD/src/gpt_pro_fast/model_reproduction"
bash "$REPRO/tools/full_train.sh" \
  "$REPRO/sources/eat117" \
  "$PWD/build/gpt-pro-model-training" \
  "$REPRO/inputs/cohort.csv.gz"
```

首个参数包含 `arch/`、`assets/surface779/`、`src/worker.cpp`、
`include/exp579-models.h`、静态 Zstd 库和支持 `--assets` 的 `build.py`。
训练时该构建器生成 `build/build-report.json`，追踪脚本据此编译带诊断输出的 worker。
复现包的 `trace.py` 已做三项适配。

- 按 `-o` 定位编译和链接输出，保留其后的 `-DEXP640_TREES=8`。原脚本将最后一个参数
  当作目标文件，会在查找链接对象时抛出 `ValueError`；本轮通过模拟命令生成复现了该异常。
- EAT117 的曲面查询使用 `surface779`，追踪代码据此移除对 `direct_exact` 与
  `kDirectCurveMarker` 的引用。
- 在生成的诊断 worker 中加入 `ordinary` 字段及 `event==0 && !override_cycle` 赋值，
  保持原来的六个 `int32_t` 字段布局。冻结 EAT117 的 248 个文件保持原字节。

编码器从追踪数据读取第 0 列的 `pair*480+context`，公开角色频率使用 `key//480`；
这一路径和 208×288 角色顺序保持原定义。此次验证执行了完整源树与资产身份核对、角色映射核对、
1M cohort 行数检查，以及模拟编译器的构建/追踪命令生成检查。模拟过程没有生成 ELF，
生成的 C++ 仍待真实编译与运行验证。

训练依赖列在 `requirements-training.txt`，历史精确版本记录缺失。本机仍缺少 Pandas、SciPy、
scikit-learn、Python `zstandard` 与系统 `zstd` 命令。完整训练及重新训练后的字节一致性
保持未验。训练完成后需同步导出六张推理表和帧长度表，并为新模型重新评测。

`sources/knots/native/build.py` 保留历史算法导出逻辑，同时引用原包未提供的
`core.inc`、`fast.inc` 和物理头数据。三资产导出采用独立的 `tools/pack_assets.py`；
完整训练入口也使用该工具。`near/mask.zst`、`near/topology.dat` 和物理残差头的
重新生成属于本包覆盖范围之外，随正式源码保留其冻结发布资产。
