# 实验46 短距 xgb-base 混合策略预注册

日期 2026-09-23。起点提交 `f56aef8`（工作树只有用户未跟踪 `blobs/`，保持不动）。开工
`df -h /dev/sdd`：1007G 总 / 493G 用 / 464G 可用；真实生成请求前重读一次。

本协议先于任何 [6M,8M) 标签、golden、预测或评分产生，单独提交；只固定检验既有冻结策略的
组合规则，不训练模型、不调阈值、不改 C++/Python 生产或实验实现。

## 假设与策略

生产 `xgb`（实验29）与实验41 候选 `xgb-base` 的差别集中在短距端点几何；候选在公开 1M 与
新架构样本上都为正，但全量 1B 计时（实验42/44）未落入预算。本轮检验**固定混合**：

- `distance <= 24`（既有距离带 `0`、`1-12`、`13-24`，即 band 0/1/2）用冻结 `xgb-base`；
- `distance > 24` 用冻结 `xgb`。

距离按 `validation/exp19c_score.py` 的既有定义从引脚名算：`SRB_<i>_<j>/...` 取 `(i,j)`，
`distance = |Δi| + |Δj|`，与 `band_of()` 的 7 带边界（12/24/50/100/300）一致。阈值 24 由既有
距离带预先固定，不得按新样本调整；模型不重训。

## 冻结身份

| 角色 | 二进制 | sha256 |
|---|---|---|
| baseline `xgb`（实验29，正式） | `./estimate` | `db2cca1eb976df543b2b7281326402fd77fc7b58bf1492d530535903df88ba35` |
| 候选 `xgb-base`（实验41 冻结） | `build/exp41/frozen-1b-v1/estimate-base` | `d66c067658a7e7ad92edc5cc0351119661543648c61adaa3682779df390c45c5` |

公共参数 `-residue-mult 2 -endpoint-mode source-short -endpoint-short-distance 150`；策略参数
`-residual xgb` / `-residual xgb-base`。候选输出只写 `build/exp46/` 与
`validation/results/exp46-*`，**严禁覆盖 `./estimate` 与 `build/submission/`**（保持实验29）。

## 数据与索引

新架构请求用生成器 `scripts/make_scale_requests.py` 的 `unique` 模式：行 `k` 取
`j = (a*k + b) mod space`（a、b 由架构固定，非随机种子），输出 `--rows 8000000`，再切
`[6M, 8M)` 得 `build/exp46/fresh-2m.csv`。范围不重叠的依据只用生成器索引定义与既有范围：
实验31 记录 `[0,4M)`（`build/exp31/unique-4m.csv`，`c509c1d2…`）、实验43 用 `[4M,6M)`
（`build/exp43/unique-6m.csv`，`39354817…`），因此 `[6M,8M)` 按索引不重叠；执行时再验证新 8M
文件的 `[0,6M)` 前缀逐字节等于既有 6M 文件、`[0,4M)` 等于既有 4M 文件。**不得读取新范围的
exact/score 来挑选范围或样本。**

抽样沿用实验43 的冻结规则：探针 `build/query_profile_exp18b`
（sha256 `613139d1b2d3363f1909c2d4a15dbe31c61fa8592732afc8ed5136e26b2730e5`），
`--pdb-only --dedup-endpoints --samples-per-band 1024 --samples-per-tag 0 --landmarks 8`
加公共参数，探针内固定 seed 20260919、7 距离带、每带上限 1024。完整来源排除列表（请求行与
引脚并集，零交集、**无替代抽样**，命中即失败）：

1. `validation/results/exp18b-labels.csv`（引脚）
2. `validation/results/exp18b-regress-99.csv`（引脚）
3. `validation/results/exp24-holdout-samples.csv`（引脚）
4. `build/exp31/exp31-new-samples.csv`（引脚）
5. `build/exp31/exp31-new-kept.csv`（请求行）
6. `delay_estimate_request.csv`（公开 1M 请求行）
7. `build/exp41/labels-base-off.csv`、`build/exp41/holdout-base-off.csv`、
   `build/exp41/stress-base-off.csv`（实验41 训练/留出/stress 请求行）
8. `build/exp43/fresh-samples.csv`（引脚）、`build/exp43/fresh-kept.csv`（请求行）

公开 1M（`delay_estimate_request.csv`）只做开发分布与预算评估，不充当独立验证。

## 预声明统计与门槛

唯一主候选是 **混合 − baseline**，在 [6M,8M) 同一留出上一次性评估；完整 `xgb-base` 是次级
诊断，不参与阈值调整。分层配对 bootstrap 复用实验43 修正后的口径：7 距离带、每个 replicate
在带内重采完整行、跨带合并分子与合并可达分母、negative exact 保留在可达性统计、band0 全量
时不重采；`seed 20260923`、10000 次。

准确性通过门槛（全过才算通过）：

- 新架构语料加权 accuracy 增益 > 0 且 95% 配对下界 > 0；
- 等带加权 accuracy 不下降（混合 ≥ baseline）；
- 可达性不劣（`false_reachable` 不增、`reachable_false_unreachable` 不增）；
- negative exact 无 false reachable。

## 一次性评估与复核

同一留出上各跑一次：baseline（`xgb`）、完整候选（`xgb-base`）、混合（按距离逐行选两者输出，
行序与请求一致）。报告每距离带行数、每带 accuracy 贡献、混合相对完整候选的 accuracy 差。
公开 1M 上各策略固定输出一份并评分（golden 仅此一步读取），用于分布与预算。

Python/C++ 策略复核：用现有二进制在制造请求上核对混合选择（边界 `dist=24` 走候选、`dist=25`
走 baseline、无效引脚与空集按既有错误路径处理），并核对混合输出逐行等于所选策略在同行上的
输出；negative exact 行为按既有可达性口径检查（不计入 accuracy、计可达性）。

## CPU 预算推导与性能协议

平台换算（`experiment/平台运行记录-01.md`）：1 个 accuracy 百分点 = 0.8 分；1 CPU 秒 = 0.15/1800·100
= 1/120 分。故 `Δscore = 0.8·Δacc − ΔCPU/120`，盈亏平衡 `ΔCPU = 0.8·120·Δacc = 96·Δacc`
秒，其中 `Δacc` 是 accuracy 的**百分点**差（不是百分制分数差）。公开 1M 上混合相对 baseline 的
accuracy 增益 `Δacc_1m` 允许的新增 CPU 为 `96·Δacc_1m` 秒/1M 次运行。

计时协议现在冻结：同一新架构 1M unique 输入（`build/exp46/fresh-1m.csv`，生成器 `[6M,7M)` 切片），
`taskset -c 3`、串行、3600 秒硬超时、线程 ==1、RSS×1024 ≤ 2,000,000,000、每轮保留 run/verify
JSON 与 time/log。每侧先跑 1 轮预热（丢弃），再 4 对配对、顺序 `B,C,C,B,B,C,C,B`（df=3，
t=3.182446），baseline 跑完整 1M；混合按距离拆成两个不相交子文件（`≤24` 给候选、`>24` 给
baseline），各跑一次并把 rusage CPU 相加作为该轮混合 CPU（如实计入两次进程/表初始化），子文件
行数与哈希随证据记录。契约：baseline 完整 1M 输出用 `scripts/verify_scale_output.py` 核对；
混合两个子文件输出核对行数/行序且逐行等于对应策略在同行上的输出。

预算门槛：混合 − baseline 的配对 CPU 差 95% 上界 < `96·Δacc_1m` 秒，且上述准确性门槛全过，
才算本机预算证据。正式入口不能升级；全量 `xgb-base` 的 1B 证据（实验42/44 inconclusive）仍是
它自己的完整策略限制，混合不自动继承；若进入后续，另需重跑混合的正式五次 1B 验收。

## 失败处置

任一门槛不过即结论失败：默认 `xgb` 与正式实验29 入口保持不变，候选保持私有，不做接入讨论。
每次提交候选实验代码后必须给出消融（完整 `xgb-base` vs 混合 vs baseline），只有精度与 CPU
双门槛都过才讨论接入。证据按阶段提交：请求/抽样/排除/预测/评分/计时各一份 JSON，失败保留
原始记录，不删除既有证据。

## 执行记录与结果

驱动 `validation/exp46_mixed_strategy.py`（提交 `a0c7880`，22 项 focused selfcheck）。证据
`validation/results/exp46-stage-*.json` 与 `validation/results/exp46-timing*/`。

**数据**：生成器 `unique` 8M（`build/exp46/unique-8m.csv`，sha256 `b09d4a11…`，286,015,863 B），
`[0,4M)`/`[0,6M)` 前缀逐字节等于既有 4M/6M 文件（`c509c1d2…`/`39354817…`）；切片 `[6M,8M)`
2,000,000 行、`[6M,7M)` 1,000,000 行。冻结探针采样 6,177 行（band0 全量 33/33，其余 6 带各
1024），11 组排除来源**零交集**（`rows_removed=0`，无替代抽样），Python `pin_distance` 与探针
`dist` 逐行一致（0 处不符）。

**策略消融（新架构 [6M,8M) 留出，6,177 行，88 条 negative exact）**

| 策略 | 语料加权 | 等带加权 | MAPE | 语料加权增益 | 配对 95% 区间 |
|---|---:|---:|---:|---:|---:|
| baseline `xgb` | 95.600744 | 84.135552 | 3.2550% | — | — |
| 完整 `xgb-base` | 95.698755 | 85.489426 | 2.8856% | +0.098011 | [0.061175, 0.133928] |
| 混合（≤24 候选 / >24 baseline） | 95.645183 | 85.375213 | 2.9212% | +0.044440 | [0.035391, 0.053501] |

混合相对完整候选 −0.053572（语料加权）；短距组（≤24，2,081 行）baseline 75.7619 → 混合 78.6068。
六项门槛全过（增益 >0、95% 下界 >0、等带不降、0 false reachable、可达性不劣、negative 不劣）；
band0 全量不重采。逐带贡献见 `exp46-stage-score.json`。

**公开 1M**（golden 只在此步读取）：baseline 96.116008008（与 `exp19c-score.json` 完全一致）、
完整候选 96.184033910（与实验41 的 96.184034 一致，两项回归自检 True）、混合 96.162326831。
混合 − baseline = **+0.046318822 百分点**，完整候选 − baseline = +0.068025902，混合 − 完整候选
= −0.021707080。逐带看混合只在 0/1-12/13-24 生效（+10.3881/+3.4639/+2.3555），完整候选在
101-300/301+ 反而低于 baseline（−0.0155/−0.0257），混合避开了这两带。

**CPU 预算**：`Δscore = 0.8·Δacc − ΔCPU/120`，盈亏平衡 `ΔCPU = 96·Δacc` 秒（Δacc 为 accuracy
百分点）；`96 × 0.046318822 = 4.4466 s/1M`。

**计时（冻结协议）**：同一 `[6M,7M)` 1M unique，按距离拆分 17,282 短 / 982,718 长；`taskset -c 3`、
串行、3600 s 上限、线程 1、RSS≈903.8 MB、每轮契约退出码 0。每侧 1 预热丢弃 + 4 对
`B,C,C,B,B,C,C,B`：

| 轮 | 侧 | CPU s | wall s |
|---|---|---:|---:|
| r1 | baseline | 56.00 | 52.02 |
| r2 | mixed | 91.59 | 86.04 |
| r3 | mixed | 92.81 | 86.04 |
| r4 | baseline | 58.60 | 55.03 |
| r5 | baseline | 57.62 | 54.03 |
| r6 | mixed | 90.94 | 85.04 |
| r7 | mixed | 89.44 | 82.04 |
| r8 | baseline | 55.29 | 51.02 |

配对差（mixed − baseline）**+35.591 / +34.208 / +33.318 / +34.153 s**，均值 **+34.3175 s**，
CI95 **[32.819, 35.816]**（df=3，t=3.182446），预算 4.4466 s → **CPU 门槛不通过**（慢约 7.7 倍预算）。
原因是混合按两进程部署：短/长两半各付一次约 34 s 的表构建与启动，固定开销翻倍。

**边界与错误路径**：公开请求中 dist=24/25 各取一行（行号 13/233），两个二进制输出不同
（649/646、644/641），混合按规则分别取候选/baseline（`selection_ok=True`）；无效引脚两二进制都
exit 0 并输出 `-1`（不可达哨兵），空集 exit 0 且只写表头——这是既有宽松路径，混合把无法解析的
行归到 baseline 侧。

**两处计时插桩缺陷（如实记录，原始轮次未改）**

1. 首次计时用 `run_scale.cpu_seconds()`（`RUSAGE_SELF`，量到驱动自身 ~0.02 s）；改为
   `RUSAGE_CHILDREN` 增量后重跑。原始首轮证据保留在 `exp46-stage-timing-cpu-bug.json` 与
   `exp46-timing-cpu-bug/`（wall 与修正轮一致，如 r1 59.0 vs 52.0 s）。
2. 配对聚合按固定位置取符号，`B,C,C,B,B,C,C,B` 下正负抵消（均值误为 +0.14 s）；改为按每对轮次
   侧定向后重算，pre-fix 聚合保留在 `exp46-stage-timing-pairing-bug.json`。重算只用已记录的
   每轮 CPU，不重新测量、不删轮次。

**判定**：准确性门槛全过、CPU 门槛不通过 → 按预声明**不接入**。默认 `xgb` 与正式实验29 入口
保持 `db2cca1e…` 不变；`xgb-base` 与混合都保持私有输出（`build/exp46/`），不进入混合的五次 1B
验收。若日后重试，需先消除两进程双份固定开销（例如单进程内按行切换模型）并重新预注册。

**空间**：开工 1007G 总 / 493G 用 / 464G 可用；收尾 494G 用 / 463G 可用（新增 `build/exp46`
682 MB 与证据 JSON）。`blobs/` 未触碰。
