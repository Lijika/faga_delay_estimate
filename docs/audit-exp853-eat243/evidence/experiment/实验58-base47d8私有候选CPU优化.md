# 实验58 续：私有 base-d8 候选的 CPU 优化（工程性能，不改变预测）

日期：2026-09-26。承接 `实验58-base特征与深度组合预注册.md`。本轮只做私有候选
`xgb-base47-d8` 的推理工程优化：模型、特征语义、阈值、输入和输出全部冻结，
精度证据沿用 [16M,18M) 冻结窗口（6178 行），不重训、不调参。

## 冻结身份

| 对象 | 路径 | SHA-256 |
| --- | --- | --- |
| 正式基线（未改动） | `./estimate`、`build/submission/estimate` | `db2cca1e…88ba35` |
| 冻结模型 | `build/exp57/exp58-model-base-d8.json` | `f98d7260…39661e` |
| 原 47 槽 header | `src/xgb_residual_base47_model.h` | `afb318fc…e386810` |
| 优化前候选二进制 | `build/exp58/estimate-base47d8` | `ff6ccd6e…350f9b0` |
| 优化后候选二进制 | `build/exp58/estimate-base47d8-opt` | `e80cc8fb…0d2afc2d` |
| 新增 padded header | `build/exp58/opt-src/xgb_residual_base47_fast_model.h` | `b31214d9…f6ffa928` |
| 1M unique 计时输入 | `build/exp57/timing-1m-unique.csv` | `2cf587f1…a018d7bd` |
| 200k 计时输入（计时输入前缀） | `build/exp58/prof-200k.csv` | `389fa737…3eb66130` |
| 6178 行请求 | `build/exp58/fresh-6178-requests.csv` | `deffaf1f…13b2c4d2f43` |

精度（实验58 冻结结论，本轮未重测）：base-d8 相对实验29 pooled 加权 accuracy
`95.89258233` vs `95.77198496`，`gain_pp = +0.12059737022848083`，bootstrap 95% 下界为正，
false finite `0`、reachable false unreachable `0`、负 exact `99` 行保持 `-1`。
据此新增 CPU 预算 `96 × 0.1205973702 = 11.5773 s`（1M unique distinct 输入一次完整运行）。

## 优化内容与等价性

两项单变量改动都保留 47 槽数值映射、float32 阈值、`features[f] < threshold` 判定方向、
每棵树按顺序 float 累加和 `xgbRound`：

1. **紧凑特征写入**（`xgbBase47FeaturesCompact`）。冻结模型只读 38/47 列
   （0–17、20、21、23、28、30、31、32、34–46）。新写入函数不再 `std::fill` 44 槽、
   不再计算未被读取的 18 槽，其余列用与生产完全相同的表达式。恒零槽 19、22、24–27
   与未使用槽 29、33 既不写也不被任何树读取（export 脚本的 used-feature 审计固定该集合）。
   直接证据：`build/exp58/feature_compare` 在 6178 行真实端点上比较新旧写入函数的
   38 个使用槽，`234764` 次 float 位比较 `0` 不匹配。
2. **固定深度 8 分支无关树遍历**（`xgbBase47FastRaw` + 生成 header
   `xgb_residual_base47_fast_model.h`）。每棵树按堆序补全为深度 8 完全二叉树
   （511 节点/树），补全区整段填原叶值；因此越过原叶后无论比较走向都返回同一叶值，
   8 次比较固定、无数据相关方向分支。生成脚本
   `validation/exp58_export_base47d8_fast_model.py` 校验：64 棵树最大深度均为 8；
   512 行 probe 立方上 padded 遍历与紧凑遍历**逐位相同**；与 XGBoost booster 预测
   最大偏差 `4.39e-05`（容差 1e-3）。

未做：`lowerBound()`/L 槽、quotient bounds table（模型不读 L，路径不进入）、
任何缓存键或端点/残差表改动、并行化、浮点编译选项、跳过模型树、缓存换时间。

## 结果

### 1. 6178 行逐行契约（`validation/results/exp58-base47d8-opt-contract.json`）

`d8-pre`（优化前二进制）、`d8`、`d8-feat`、`d8-walk`、`d8-all` 五种模式输出
**逐字节相同**，而且与冻结 Python `base-d8` 列逐行相同：

| 模式 | 行数 | 端点差异 | 与 base-d8 不同行 | 负 exact=-1 | 输出 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| d8-pre | 6178 | 0 | 0 | 是（99 行） | `dedf0ccb…0533fb` |
| d8 | 6178 | 0 | 0 | 是 | 同上 |
| d8-feat | 6178 | 0 | 0 | 是 | 同上 |
| d8-walk | 6178 | 0 | 0 | 是 | 同上 |
| d8-all | 6178 | 0 | 0 | 是 | 同上 |

same-pin=0、非法/畸形输入 `-1`、空输入只有 header、EOF 契约与正式基线一致。

### 2. 200k 行同二进制消融（`validation/results/exp58-base47d8-opt-screen.json`）

同一 `estimate-base47d8-opt` 内 5 条路径 + 生产 `xgb` 参考，6 轮交错、`taskset -c 3`、
每标签一次预热、CPU 为 user+sys。所有 d8 变体输出 SHA 同为 `abeaf99b…`（200k 行也等价），
`xgb` 参考为 `41c9c958…`。峰值 RSS `925,999,104 B`，线程 `1`。

相对**同源码 `xgb` 参考**的配对 CPU 差（秒 / 200k 行；括号为 95% CI）：

| 路径 | 200k 配对均值 | 95% CI | ×5 折算 1M |
| --- | ---: | --- | ---: |
| d8-pre（优化前二进制） | +1.068 | [+0.955, +1.182] | +5.34 |
| d8（优化前实现，优化后二进制内） | +0.473 | [+0.371, +0.575] | +2.37 |
| d8-feat（只紧凑特征） | +0.593 | [+0.374, +0.813] | +2.97 |
| d8-walk（只固定深度遍历） | **+0.078** | [+0.035, +0.121] | **+0.39** |
| d8-all（两项都做） | **+0.005** | [−0.129, +0.139] | **+0.03** |

读法：
- **模型推理工程收益**：base-d8 相对生产模型的增量由 `+0.473` 降到 `+0.078`（d8-walk）
  或 `+0.005`（d8-all），即省下 `0.40–0.47 s / 200k` ≈ `2.0–2.3 s / 1M`。收益来自
  固定深度分支无关遍历。
- **紧凑特征单项落在噪声内**：`d8-feat` 比 `d8` 慢 `0.12 s/200k`（CI 重叠），
  `d8-all` 比 `d8-walk` 快 `0.07 s/200k`（同量级噪声，符号相反）。按“收益小于噪声取最简单
  实现”的约定，本轮把 `d8-walk` 作为推荐候选，`d8-all` 作为备选（两者输出逐字节相同）。
- **端点共享路径**（estimateBase / estimateEndpoint / 缓存 / 残差表）本轮未改动。

### 3. 微基准（`build/exp58/walkbench`，2M 行 × 7 轮，`taskset -c 3`）

同一批特征行上比较两条 C++ 遍历，逐行 float 位相同（`bit_mismatches=0`）：

| 特征驻留 | 紧凑遍历 | padded 遍历 | 加速 |
| --- | ---: | ---: | ---: |
| 流式 2M 行 | 5783.6 ns/行 | 2807.6 ns/row | 2.06× |
| 旋转窗口 1024（模拟生产栈数组） | 5658.7 ns/行 | 2774.1 ns/row | 2.04× |

与流水线消融一致：`2.9 µs/行` 的遍历差 × 1M ≈ `2.9 s`，实测 `2.0–2.3 s`。

### 4. 计时运行状态（重要）

- **timing-b1**（`validation/results/exp58-base47d8-private.json`，原冻结协议 10 对，
  02:25–02:47）：在 round 1–2 期间与本地 prof 运行共用同一物理核，**仅为 contaminated
  screening**，不作判决。报告值 mean `-2.337 s`，CI `[-4.374, -0.300]`，
  最大 RSS `925,671,424 B`，线程 `1`，baseline 输出 SHA 复现实验57 冻结身份
  `30565755…`；报告已另存 `exp58-base47d8-private-timing-b1.json` 与
  `…-timing-contaminated.json`。该轮 baseline/candidate 的 1M 输出比较只核对了
  baseline 行前缀（旧脚本缺口），**不能算通过**。
- **timing-b2**（02:49–02:59，`build/exp58/timing-b2*`）：与本地模型导出/编译/微基准并发，
  中途终止，`timing-1m-base47d8-b2.csv` 截断在 20 MiB。**aborted/concurrent，不可用**。
- **timing-b3**（`build/exp58/timing-b3.log`、`timing-1m-baseline-b3.csv`、`timing-b3-*`）：
  由监控侧以 `validation/exp58_base47d8_private.py --stage timing-clean` 启动（该 stage
  不在本轮新增 harness 里，日志文本 `timing-clean: waiting for quiet …` 与本轮 harness 的
  `opt-*` 命名明显不同）。03:12–03:15 先等待安静；03:26–03:28 在 screen 结束后重启并产生一个
  基线子进程（PID 483617/483618），本轮执行 agent 按指示终止该子进程；随后监控侧在 03:29
  再次启动同一 stage（PID 486511），基线 warmup 完成并写入 `timing-1m-baseline-b3.csv`
  （39 MiB），随后推进到 d8 warmup。**截至本记录，b3 是“监控侧进行中/未完成”，
  不得作为判决数据；本轮执行 agent 未启动过任何 timing/1M 阶段，也未再测量。**
  全部 b3 文件保留，未删除。

因此本轮**没有**合格的 1M 十对判决数据。

## 判定与后续计划

- 已在预算内：以最保守的 200k 数字（`d8-pre` 相对同源码 xgb 参考 `+5.34 s/1M`）折算，
  也低于 `11.5773 s` 预算；`d8-walk`/`d8-all` 折算 `+0.39 / +0.03 s/1M`。
  但**判决口径要求正式基线 `./estimate`**，且上述数字含一次未解释的
  二进制/布局差（同一实现 `d8` 在优化前后两个二进制内相差 `0.595 s/200k ≈ 3.0 s/1M`，
  源码与输出均相同，机制未查明）。
- 待办（未启动）：安静的 10 对 1M unique 协议，同场比较
  `baseline=./estimate:xgb`、`d8-pre=build/exp58/estimate-base47d8:xgb-base47-d8`、
  `d8-walk`、`d8-all`（同一 `estimate-base47d8-opt`），串行、交错、固定预热，
  并执行新增的严格逐行校验：对 baseline **和每个 candidate** 全部 1M 行核对
  端点顺序、恰好 3 字段、整数 delay、EOF、负 exact 位置集合，以及各轮 SHA 稳定
  （`validation/exp58_base47d8_ablation.py --stage timing|verify-outputs`）。
- 只有该协议通过后，才谈 1B 正式验收；本轮不启动五次 1B。

## 后续验收

- `实验58-base47d8五次1B验收.md`：五对交错 repeated-1B 正式验收（10 轮全部通过资源与
  输出契约门禁，配对 CPU 均值 −9.606 s、95% 区间 [−29.368, +10.156] s，预算 11.5773 s
  通过；综合收益 95% 下界 −0.02823 不为正）。

## 局限

- 6178 行窗口的 `d8-pre`/`d8-walk` 输出等价是逐字节证据；200k 行只有 SHA 等价证据，
  完整的 1M 逐行等价尚未在安静条件下重做。
- 200k 消融的参考是同一二进制内的 `xgb` 路径，不是冻结 `./estimate`；冻结基线只在
  contaminated 的 b1 中出现过。
- 作弊用 TSC 计数定位瓶颈的方法在本虚拟机上不可靠（rdtsc 读数与真实 CPU 时间不一致），
  本轮结论全部来自配对 CPU 时间、微基准和位级比较，未使用 TSC 单次读数判决。

## 清理与空间

- 开工 `df -h /dev/sdd`：`422G` 可用；收尾 `421G` 可用；本轮新增约 `0.9 GiB`
  （`build/exp58` 现 521 MiB + `validation/results` JSON）。
- **未删除任何文件**（含 39 MiB 的 timing CSV、20 MiB 截断 CSV、prof 输出和 b2/b3 日志）。
  按名引用的长期输入（`doc/`、五个 arch JSON、`build/exp57/timing-1m-unique.csv`、
  `build/exp58/fresh-6178-requests.csv`、`build/exp58/prof-200k.csv`、正式二进制）均保留。

### 本轮命令账（不含任何 timing/1M 阶段）

按时间：`validation/exp58_export_base47d8_fast_model.py`（生成 padded header + 512 行位级/booster
自检）→ `sh build/exp58/build_opt.sh`（编译 `estimate-base47d8-opt`）→ 编译并运行
`feature_compare`（6178 行×38 槽位比较）与 `walkbench`（2M 行 7/5/5 轮，流式与 hot-window）
→ `exp58_base47d8_ablation.py --stage contract`（5 模式 6178 行逐字节契约）
→ `exp58_base47d8_ablation.py --stage screen`（200k 行、6 标签×6 轮，03:03–03:24）。
之后只读文件、写日志与证据文件。**未运行 `--stage timing`，未运行 `verify-outputs`
（它需要 1M 测量产物），未启动后台命令或定时器。**

### 大文件清单（2026-09-26 03:35，只读 `find`，未删除）

仓库内 >10 GiB：

| 路径 | 大小 | 处置 |
| --- | ---: | --- |
| `build/exp29/output-1b.csv` | 37.56 GiB | 保留（未动） |
| `build/exp41/out-1b.csv` | 37.56 GiB | 保留（未动） |
| `build/exp56/formal-1b.csv` | 37.56 GiB | 保留（未动） |
| `build/exp57/formal-1b.csv` | 37.56 GiB | 保留（未动） |
| `build/final-scale/requests-1b.csv` | 32.96 GiB | 长期保留（按名引用） |

`build/exp58` 合计 555 MiB，最大单文件均为本轮/上轮 1M 输出（39 MiB ×4、
20 MiB 截断 b2、7.8 MiB ×19 的 200k 屏幕输出），无新增 >10 GiB 对象。
