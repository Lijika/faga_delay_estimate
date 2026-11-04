# 实验47 单进程短距 xgb-base 混合验证（预注册）

日期 2026-09-24。起点提交 `dbef7cc`（工作树只有用户未跟踪 `blobs/`，保持不动）。
开工 `df -h /dev/sdd`：1007G 总 / 495G 用 / 461G 可用。

本协议先于任何新候选构建、计时、预测或评分产生，单独提交。只把实验46已冻结的两进程
逐行选择搬进一个估计进程，不训练模型、不调阈值、不改公开 1M/新切片的选择规则。

## 假设

实验46 的两进程混合在 1M unique 上比 baseline 多 **34.3175 s CPU**（95% 区间
[32.819, 35.816]），主因是短/长两半各付一次约 34 s 的 residue 建表与进程启动。公开 1M 的
精度增益 **+0.046318822 点**只允许 **4.446606959188102 s/1M** 的新增 CPU。

主假设：把 `distance <= 24 → xgb-base`、`distance > 24 → xgb` 的逐行选择放进同一个
`ResidueEstimator`，共享一次 residue 建表、一次端点/解析路径和一个 64 MiB 请求缓存后，
1M unique 的混合 − baseline CPU 差落入 4.4466 s 预算；输出与实验46 已记录的混合输出
**逐字节一致**（纯部署等价改动，精度直接继承，不重新选型）。

## 冻结身份

| 角色 | 路径 | sha256 |
|---|---|---|
| baseline（实验29 正式） | `./estimate` | `db2cca1eb976df543b2b7281326402fd77fc7b58bf1492d530535903df88ba35` |
| 候选（本轮构建，私有） | `build/exp47/estimate-hybrid24` | 构建后记录 |
| 实验46 混合参考（公开 1M） | `build/exp46/public-mixed.csv` | `3df2eaedd29afaba313f9637d95b11927f1edd9bf35017653bae6f23584af1e0` |
| 实验46 混合参考（[6M,7M) 1M） | `build/exp46/pred-mixed.csv` | `ef5c9c57b1b03b21cc24b964f3854e6c10ab38ea115a37285f279f4f1bb81462` |
| 实验46 baseline 参考（公开 1M） | `build/exp46/public-baseline.csv` | `c5ba12aeb6c2c5d921f4515e91759b9c132679dbae70f73d68e5635535946e61` |

公共参数 `-residue-mult 2 -endpoint-mode source-short -endpoint-short-distance 150`；策略参数
`-residual xgb`（baseline）/ `-residual xgb-base24`（本轮候选）。候选输出只写
`build/exp47/` 与 `validation/results/exp47-*`，**严禁覆盖 `./estimate` 与
`build/submission/`**。源码改动限定为新增一个残差模式，不改变任何现有模式的行为。

## 选择规则与语义

距离定义沿用 `validation/exp19c_score.py`：`SRB_<i>_<j>/...` 取 `(i,j)`，
`distance = |Δi| + |Δj|`，阈值 24（实验46 预注册，不得按新样本调整）。

- `distance <= 24`：走与冻结 `-residual xgb-base` **完全相同**的 base+L 特征与树推理；
  该路径中 `lower < 0` 或 `baseValue < 0` 时回退到生产 xgb 模型，这是冻结候选自身的既有语义，
  混合不改变它。
- `distance > 24`：走与生产 `-residual xgb` 完全相同的 44 特征与树推理。
- 无法解析的引脚、无效端点、不可达、零结果：两条路径都保持既有 `-1`/0 契约；选择只在
  `applyResidual` 内部发生，不影响端点枚举、缓存键或输出格式。
- 缓存存最终整数结果，逐请求键包含完整 pin 对；距离由 pin 对唯一决定，因此单进程逐行选择
  与两进程逐行拼接在语义上等价。

## 数据与输入

- 公开 1M `delay_estimate_request.csv`（开发分布与评分）。
- 实验46 新切片 `build/exp46/fresh-1m.csv`（`[6M,7M)` 1M unique，sha256 `508807c5…`）与
  `build/exp46/fresh-2m.csv`（`[6M,8M)` 2M，用于更大范围等价核对）。
- 边界 `build/exp46/boundary.csv`（dist 24/25）、`boundary-invalid.csv`、
  `boundary-empty.csv`；零距离行从公开 1M 按距离筛出。
- 100M repeated：`build/exp29/requests-100m.csv`（3,539,461,608 B，公开 1M 逐块重复）。
- 100M mixed：用 `scripts/make_scale_requests.py --mode mixed` 生成 90M repeated 前缀 +
  10M unique 后缀（与实验23 同规则），输入身份随证据记录。
- 1B repeated：`build/final-scale/requests-1b.csv`（35,394,616,008 B，公开 1M 重复 1000 次）。

## 预声明门槛

**A. 等价与契约（全过才继续计时）**

1. 公开 1M 输出 SHA-256 等于 `build/exp46/public-mixed.csv`。
2. `[6M,7M)` 1M 输出 SHA-256 等于 `build/exp46/pred-mixed.csv`。
3. `[6M,8M)` 2M 上，混合输出逐行等于「dist<=24 取 `-residual xgb-base`、否则取
   `-residual xgb`」的逐行选择（同一候选二进制分别以两个冻结模式各跑一次，按距离拼接比较）。
4. 边界：dist=24 行取 xgb-base 值、dist=25 行取 xgb 值；无效引脚输出 `-1`；空输入 exit 0
   且只写表头；输出行数、行序、端点原文与整数格式与输入契约一致。
5. 公开 accuracy 独立复核等于实验46 混合值 **96.162326831**（等价通过时是确认，不是新收益）。

**B. CPU 预算（1M unique，冻结计时协议）**

- 同一 `build/exp46/fresh-1m.csv`，`taskset -c 3`、串行、3600 s 硬超时、线程 ==1、
  RSS×1024 ≤ 2,000,000,000；每侧先跑 1 轮预热（丢弃），再 4 对配对，顺序
  `B,C,C,B,B,C,C,B`（df=3，t=3.182446）；每轮保留 run/verify JSON 与 time/log。
- 预算 `96 × 0.046318822 = 4.446606959188102 s/1M`；门槛为混合 − baseline 配对 CPU 差的
  95% 上界 < 预算。

**C. 规模与资源（描述性 + 硬约束）**

- 100M repeated 与 100M mixed 各 2 对交错，报告 CPU、wall、峰值 RSS、线程、缓存命中、建表秒数
  与输出契约；重复输入核对 100/100 块，mixed 核对 90/90 重复块与后缀行数/端点。
- 所有轮次线程 ==1、RSS×1024 ≤ 2,000,000,000、退出码 0。

**D. 1B 正式验收（仅当 A、B、C 通过才执行）**

- 五次 baseline + 五次候选交错（`B,C,B,C,B,C,B,C,B,C`），`taskset -c 3`、3600 s 超时；
  每轮完整输出核对（1000/1000 块、精确 EOF、完整 SHA-256）；同侧五次 SHA 必须唯一；
  五次退出码 0、线程 1、RSS 合规。配对 CPU 差报点估计与 95% 区间（df=4，t=2.776）作为
  诊断；1B 计时噪声远大于 4.4466 s 时如实标注不可分辨。

## 补充预声明（同日、看任何新计时结果之前写入）

### 采纳门槛（AGENTS.md 口径）

正式接入要求 **Δ综合分 95% 置信下界 > 0**，且**点估计达到预先固定的最小实际收益**。本轮把
最小实际收益固定为 **+0.01 综合分**（在 0.8·Δaccuracy − ΔCPU/120 的同一量纲上）。

精度沿用实验46 冻结结果，不重新选型：新切片语料加权 +0.044440 点，配对 95% 区间
[0.035391, 0.053501]；公开 1M 点估计 +0.046318822 点。CPU 差以 1B 一次完整运行的秒数计。

- **B2 联合保守下界**：`0.8 × 0.035391 − U95/120 > 0`，即 CPU 差 95% 上界
  **U95 < 3.397536 s/1B**。
- **B1 点估计最小实际收益**：`0.8 × Δacc_point − ΔCPU_point/120 ≥ 0.01`。用保守的
  新切片点估计 +0.044440 得 **ΔCPU_point ≤ 3.066240 s/1B**；用公开点估计 +0.046318822 得
  ΔCPU_point ≤ 3.246607 s/1B。两个都报，门槛以较严的新切片点估计为准。
- **单列**：公开点估计的盈亏预算 `96 × 0.046318822 = 4.446607 s/1B`，只作分布对照，
  不替代上面两条。

### 同源码 xgb 诊断对照

当前源码含实验35/36 的象限存储布局与余数等价改写，与冻结 `./estimate`（实验29）不是同一
源码状态；实验39 的 repeated 1B 交错里该布局候选比正式版高 1.265%。因此本轮同时构建
`build/exp47/estimate-xgb-samesrc`（同一提交、同一 flags、`-residual xgb`），并把它作为
CPU 归因诊断：

- 主门槛比较用 **混合 − 同源码 xgb**（只有残差选择不同，隔离本轮改动）；
- 同时报 **混合 − 冻结 ./estimate**（实验46 可比的部署差）与
  **同源码 xgb − 冻结 ./estimate**（源码布局/余数差）；
- 三者都要报点估计与配对区间。若混合 − 同源码通过而混合 − 冻结不通过，如实报告并把
  「是否随混合一起携带布局/余数源码差」列为未决的独立候选问题，不并入本轮结论。

### 扩展条件（同样在看计时前固定）

- 进入 100M/1B 的充要条件：主门槛（混合 − 同源码 xgb 的 B1 点估计与 B2 上界）全过，
  **且**混合 − 冻结 ./estimate 的 1M 点估计 ≤ 4.446607 s。任一条不满足则停止扩展，
  保留已测证据与负结果，正式入口不变。
- 1B 阶段沿用同一组 CPU 门槛与资源硬约束，只把 1M 换为 `build/final-scale/requests-1b.csv`。

### 旧标签是否足以宣称联合区间（如实标注）

实验46 的 [6M,8M) 切片标签已在该轮预测与评分中使用，公开 1M golden 也在其预算步骤读取过。
本轮是纯部署等价改动（输出逐字节一致），**没有**在新标签上重新选型，因此：

- 精度分量不是新的独立估计，而是实验46 已冻结结论的直接复用；
- B1/B2 的联合区间是**沿用旧标签的保守重述**，不构成新的泛化证据；
- 若等价门槛全过，accuracy 视为精确继承（同一整数输出、同一评分口径），不再引入额外精度
  不确定性；若等价不过，本轮不宣称任何精度收益。

## 协议操作化（计时开始前固定）

- **B 段顺序**：预注册的 4 对 `B,C,C,B,B,C,C,B`（n=4、df=3、t=3.182446）逐字保留。
  补充要求的同源码 xgb 诊断插入每对之间，不改变 B/C 子序列：
  `(B,S,C) (C,S,B) (B,S,C) (C,S,B)`，其中 B=baseline、C=hybrid、S=同源码 xgb；
  B/C 子序列仍为 `B,C,C,B,B,C,C,B`。三种比较各得 n=4 个配对差（df=3）。
- **每轮硬约束**：线程 ==1、RSS×1024 ≤ 2,000,000,000 B、wall ≤ 3600 s（与 timeout 硬杀
  同一上限），三条都进入每段 gates；线程采样用 `scripts/run_scale.py` 的
  `subtree_max_threads` 覆盖 `taskset → /usr/bin/time → timeout → estimator` 子树，
  selfcheck 用一个带 3 个额外线程的子进程验证采样器能看见后代线程（期望 ≥4）。
- **C 段**：repeated 与 mixed 各 2 对交错（n=2、df=1），描述性，不作门槛。
  repeated 每侧 1 轮预热；mixed 单轮约 6 分钟，只做 1 轮 baseline 预热（输入文件与页面
  缓存对所有侧共享），这是资源约束下的偏差，已记录。
- **D 段**：顺序按预注册 `B,C,B,C,B,C,B,C,B,C`（n=5、df=4、t=2.776445），无预热，
  每轮完整 1000/1000 块核对、精确 EOF、完整 SHA；同侧五次 SHA 必须唯一。

## 失败处置与停止条件

- 等价门槛任一不过：停止，不进入计时；保留原始 diff 与首个不一致行，结论为负。
- 1M CPU 区间上界 ≥ 预算：按预声明停止扩展（不跑 100M/1B），保留负结果，正式入口不变。
- 资源硬约束任一违反：停止扩展并记录。
- 不删除既有证据与用户文件；候选输出只写私有目录。

## 消融与报告

- 主对照：单进程混合 − 实验29 baseline（同机、同输入、同协议）。
- 分解：建表秒数（stderr `build=`）、1M 短距行数 17,282 的额外模型成本、L 商表构建
  （实验31 记录约 0.016 s，本轮复测）、缓存命中/未命中。
- 结论同时报精度来源（继承实验46 公开 +0.046318822、新切片 +0.044440）与 CPU 不确定性；
  若通过，仍需另行预注册才谈正式接入。

## 执行记录与结果

### 身份与构建

起点提交 `dbef7cc`；预注册 `e9c585b`、`9b14345`；实现 `e107f1a`。候选二进制
`build/exp47/estimate-hybrid24`，sha256
`709830327afab2240863b8374eeb1fa564d90e2ddde0b436070b17eff47d8a2e`，构建命令
`sh scripts/build_exp47.sh`（`g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter`）。
`./estimate` 与 `build/submission/estimate` 保持 `db2cca1e…` 未变。源码改动只在
`ResidualMode::XgbBase24`、`applyResidual` 的距离分派、CLI 名称与 `Exp47HybridAccess` 测试钩子；
focused 检查在 `tests/exp47_hybrid_check.cpp`。

### 等价与契约（`validation/results/exp47-stage-equiv.json`，all_ok=True）

| 检查 | 结果 |
|---|---|
| 公开 1M 对实验46 混合 | SHA-256 `3df2eaed…` 逐字节一致；0 值不一致；1,000,000 行契约通过 |
| 公开 1M accuracy（独立评分） | 96.16232683050625 = 实验46 混合 96.162326831 |
| [6M,7M) 1M 对实验46 选择 | 0 不一致（17,282 短行）；实验46 两进程分割输出对参考 0 不一致 |
| [6M,8M) 2M 逐行 | 对「≤24 取冻结 xgb-base / 否则取 `./estimate` xgb」0 不一致（34,518 短行） |
| 同源码 xgb 对冻结实验29 | 公开 1M 与 [6M,7M) 输出均逐字节一致（0 不一致） |
| 边界 24/25 | dist24 → 646（xgb-base 值）、dist25 → 644（xgb 值），与 exp46 记录的逐模式值一致 |
| 零距离 | 24 行（22 公开 + 2 同 pin）全部等于 xgb-base 侧；3 个 0 值均为同 pin |
| 无效引脚 / 空输入 | `-1` / exit 0 且只写表头 |
| focused（cacheBytes=0） | 三组 20k/24 行 dispatch mismatches=0；独立缓存实例 0→0→1 命中；包装链线程探针观测 4 线程 |
| CLI | usage 含 `xgb-base24`；错误配置 exit 2 |

### 1M unique screen（`exp47-stage-timing1m.json`）

4 对 `B,C,C,B,B,C,C,B`（n=4、df=3、t=3.182446），同源码 xgb 诊断插在每对之间；每侧 1 轮预热。
12 轮全部 exit 0、线程 1、RSS 903.6–903.8 MB、wall<3600 s、输出对参考 SHA 一致。

| 比较 | 点估计 s | 95% 区间 s | 门槛 |
|---|---:|---:|---|
| hybrid − 同源码 xgb | **−0.157** | [−1.050, +0.735] | 点估计 ≤3.066、上界 <3.398 → 过 |
| hybrid − 冻结 baseline | **−4.802** | [−5.796, −3.809] | 公开盈亏 4.446607 → 过 |
| 同源码 xgb − 冻结 baseline | −4.645 | [−5.319, −3.971] | 源码布局/余数差（实验35/36） |

三侧建表均约 27.5 s。两进程混合的 +34.32 s 固定开销消失。

### 100M repeated / mixed（描述性，各 2 对）

| 输入 | baseline s | 同源码 xgb s | hybrid s | hybrid − baseline | hybrid − 同源码 |
|---|---:|---:|---:|---:|---:|
| 100M repeated（99M 命中） | 98.28 / 94.81 | 94.83 / 95.24 | 96.18 / 92.13 | −2.39 | −0.88 |
| 100M mixed（89M 命中 + 10M 独特） | 303.67 / 296.30 | 244.10 / 243.92 | 253.00 / 250.70 | −48.14 | **+7.84** |

mixed 唯一后缀的距离分布：`≤24` 173,489 行（1.735%），`≤150` 3,642,183 行。
单独特短行诊断（173,489 行全为 `≤24` unique）：hybrid − 同源码 = +1.55 / +0.43 s，点估计
**+0.99 s ≈ 5.7 µs/行**。该值只能解释 mixed 增量的一小部分，约 6.8 s 残差未解释；该诊断的
四次运行与操作方 `recovery-block05-hybrid24` 同时钉 core 3（wall≈2×CPU、build 56 s vs 28 s），
已标 `contaminated=true`，需要静机复测才能定性。

### 1B repeated 五次交错验收（`exp47-stage-timing1b.json`）

顺序 `B,C,B,C,B,C,B,C,B,C`（n=5、df=4、t=2.776445）。10 轮全部 exit 0、线程 1、
RSS 903.6–903.8 MB、wall<3600 s、1000/1000 块 + 精确 EOF + 完整 SHA 通过。

| 侧 | 五次 CPU s | 均值 s | SHA-256 |
|---|---|---:|---|
| baseline | 506.85 / 490.94 / 506.84 / 505.64 / 496.64 | 501.382 | `cb64ba261083ea34…`（与 exp29 记录一致） |
| hybrid | 511.94 / 491.46 / 489.30 / 493.24 / 508.04 | 498.796 | `37828c89dc3872d4…` |

配对差 **−2.586 s**，95% 区间 [−17.591, +12.419]。抽查第 1/2/5/1000 块逐字节等于混合 1M 输出。
操作方在 stage 结束后补跑 `block05-baseline`（CPU 521.26、wall 866.84、SHA 同一、verify 通过）
与 `block05-hybrid24`（CPU 527.36、wall 674.21、RSS 903,796 KiB、build 27.8 s、
cache_hits 999,000,000、SHA `37828c89…`、verify 1000/1000 通过），两者都确认同一输出身份；
`block05-hybrid24` 在 stage 内与恢复轮同时钉 core 3，wall 856.97 s（CPU 508.04 s），属争用污染。
另有 pre-review 的 v1 focused 日志 `exp47-focused-{fresh,public}20k.txt`（当时用 64 MiB 缓存、
未显式禁用），已被 v2（`cache_bytes=0`）取代，保留作记录。

### 采纳门槛（`exp47-report.json`）

- **1M screen（判定口径）**：composite 点估计 `0.8×0.044440 − (−0.157)/120 = +0.03686 ≥ 0.01`；
  联合下界 `0.8×0.035391 − 0.735/120 = +0.02219 > 0`。两条都过。
- **1B（诊断）**：composite 点估计 `0.8×0.044440 + 2.586/120 = +0.05710`，但 CI 上界 12.419 s
  给出联合下界 `−0.07517`，即 1B 配对 CI 无法分辨 3.4 s 预算（预注册已声明只作诊断）。
- 公开盈亏预算 `4.446607 s/1B` 单列：hybrid − 冻结 baseline 在 1M 为 −4.802 s、在 1B 为 −2.586 s，
  都低于该预算。

### 结论与局限

单进程 `xgb-base24` 与实验46 的两进程逐行选择在公开 1M、[6M,7M) 1M 与 [6M,8M) 2M 上完全一致，
因此精度直接继承公开 **+0.046318822** 点、新切片 **+0.044440** 点；两进程的第二次建表与启动开销
消除，1M unique 上候选与同源码 xgb 无差异（−0.157 s），比冻结实验29 快 4.802 s。资源与输出
一致性在 1B 五次交错中全部通过。按预注册门槛（1M screen 主门槛 + 扩展条件）**通过**。

局限：精度证据复用实验46 的旧标签，不是新的独立盲测；1B 配对 CI 宽于预算，只能作诊断；
mixed 的 +7.84 s 有约 6.8 s 未解释，短行诊断受争用污染；同源码 xgb 在 1M unique 上比冻结基线快
4.6 s 来自实验35/36 的布局/余数改动，属独立候选问题，不并入本轮结论；隐藏集与赛方机器未验证。

### 静机复测（计时收尾）

第一阶段的 mixed `hybrid − 同源码` +7.84 s 与短行诊断的争用读数都在静机重测过：

| 复测 | 轮次 CPU s | 配对差 | 结论 |
|---|---|---:|---|
| 100M mixed 复测（`exp47-mixed-recheck.json`） | samesrc 257.38 / 281.68；hybrid 260.34 / 273.53 | 均值 **−2.60 s**（−73.18, +67.99） | 原 +7.84 s 未复现；同侧跨块漂移达 24 s，属机器状态 |
| 173,489 条全 `≤24` unique 短行（`exp47-short-row-diagnostic-clean.json`） | samesrc 34.60 / 33.42；hybrid 33.70 / 33.64 | 均值 **−0.34 s ≈ −2.0 µs/行** | 混合的模型边际成本低于本次分辨率（±3 µs/行） |

即：在 1M unique、100M repeated、100M mixed 复测与全短行输入上，候选与同源码 xgb 均无
可分辨的 CPU 差；mixed 第一阶段的 +7.84 s 不成立。被争用污染的原诊断
（`exp47-short-row-diagnostic.json`，`contaminated=true`）保留作记录。

### 空间

开工 1007G 总 / 495G 用 / 461G 可用。收尾删除本轮可重建产物：`build/exp47/timing1b-out.csv`
（40,332,874,014 B，SHA `37828c89…`）、`timing100m-repeated-out.csv`（4,033,286,414 B，
SHA `21f5a55a…`）、`timing100m-mixed-out.csv`（4,036,514,587 B，SHA `97b13a55…`）、
`timing100m-mixed-recheck-out.csv`、`short-only-out*.csv`，重建命令见
`validation/results/exp47-cleanup.json`（各阶段重跑 `validation/exp47_single_process_hybrid.py`）。
长期保留：`build/exp47/requests-100m-mixed.csv`（被驱动按名引用）、
`build/final-scale/requests-1b.csv`、`build/exp46/*` 参考、候选二进制与 `validation/results/exp47-*`。
操作方补跑的 `build/exp47/timing1b-recovery-block05-{baseline,hybrid24}.csv`（各约 40 GB）
未动，是否清理由操作方决定。
（2026-09-26 追加：操作方决定删除。
`build/exp47/timing1b-recovery-block05-{baseline,hybrid24}.csv` 与 `timing100m-{repeated,mixed}-out.csv`
共四项已删，释放 88.74 GB；改用尺寸+头尾 64 MiB 指纹比对与既有 SHA-256 记录，未重算完整摘要，
见 `validation/results/exp58-cleanup.json`。）
本轮结束 `df -h /dev/sdd`：1007G 总 / 574G 用 / 382G 可用；
其中 `build/exp47` 79 GB，几乎全为上述两个未动的恢复轮输出。
