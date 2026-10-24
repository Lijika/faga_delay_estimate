# 实验18 跨距离 PDB 配对与 exact 标签

日期 2026-09-18，基线 c3d2150（默认 source-short 150 配 mult2）。目标是把实验10 的
PatternDatabase 界接进 tests/query_profile.cpp 的取样流程，量化近场 176 条样本之外的
跨距离收益，并产出一套 exact 标签供后续非线性残差研究使用。golden 全程未读。

## 1. 工具改动（tests/query_profile.cpp）

新增 `--pdb`、`--pdb-only`、`--endpoint-mode off|source|both|source-short`、
`--endpoint-short-distance N`、`--dedup-endpoints` 与逐带进度输出。

- `--pdb` 保留配对模式，同时跑基准 Router（span 加 ALT=8）与接上同一 Provider 的 Router，
  两者都关闭查询缓存、只用二叉堆；目标表在计时区间之外按需构建，建表与 prepare 时间单独
  统计。dump 追加 `expanded_base,expanded_pdb,us_base,us_pdb,agree,pdb_prepare_s`。
- `--pdb-only` 隐含 `--pdb`，只初始化并运行 PDB 引导的搜索，`agree` 记为 -1 表示本轮没有
  配对；exact 来源在 JSON 的 `search.pdb_only` 与 stdout 都写明。
- 配对出现任何答案不一致时计数并让进程以 1 退出；一致声明只在计数为 0 时打印。
- `--dedup-endpoints` 在每个距离带内按端点端口对去重；每条 dump 行写完立即 flush，超时也能
  保留已完成标签。
- JSON 新增 `search`（landmarks、residue multiplier、endpoint 模式与阈值、radix_heap、
  pdb_only）、`pdb`（build、prepare、prepared_targets、disagreements、hop_types、
  reduced_checks、min_reduced）与 `pdb_bands`（每带 rows、mode、expanded_run、
  expanded_pair、us_run、us_pair）。旧 dump 列序不变，旧 replay 语义不变。

## 2. 每带 100 样本的 base 与 PDB 配对（622 条）

命令要点：`--request delay_estimate_request.csv --limit 1000000 --samples-per-band 100
--landmarks 8 --pdb --endpoint-mode source-short --residue-mult 2`。

| 距离带 | 基准展开 | PDB 展开 | 比值 | 基准 us/查询 | PDB us/查询 |
|---|---:|---:|---:|---:|---:|
| 0 | 4,416 | 149 | 0.034 | 6,508 | 171 |
| 1-12 | 6,257 | 174 | 0.028 | 6,503 | 216 |
| 13-24 | 18,562 | 163 | 0.009 | 15,228 | 313 |
| 25-50 | 43,461 | 165 | 0.004 | 33,607 | 399 |
| 51-100 | 134,148 | 209 | 0.002 | 120,764 | 561 |
| 101-300 | 483,043 | 1,855 | 0.004 | 510,036 | 3,032 |
| 301+ | 1,355,001 | 4,609 | 0.003 | 1,454,685 | 13,175 |

PDB 侧单独统计：构建 0.26s，prepare 合计 14.84s（226 个目标），答案不一致 0 条。工具峰值
RSS 1,862,808 KiB，其中 residue mult2 表 776 MiB、PDB 表与 Router 地标表占其余部分；这是
诊断工具的占用，不影响提交路径。

## 3. 99 行小回归（新模式）

`--pdb-only` 在 validation/results/exp17-holdout99.csv 上取样 85 行：exact 列与仓库里已
提交的 exact 标签 0 不一致，fast 列与 exp17 的 ss150/mult2 预测 0 不一致。配对模式的
622 条与这条回归共同支撑"PDB 引导的 exact 与基准 exact 一致"。

## 4. 跨距离 exact 标签（1M 取样，每带 1667，带内端点去重）

**本节是旧批次，已被 §6 的 18B 批次取代。** 旧批次把端点键写成 `{p1, p2}` 两个端口号，
凡是端口相同而坐标不同的请求都会被当作重复丢掉，因此每个带都偏少，总数只有 9,376。
旧文件保留作对照：validation/results/exp18-labels.csv 与 exp18-labels.json。

| 距离带 | 池 | 选中 | 唯一标签合计 |
|---|---:|---:|---:|
| 0 | 22 | 22 | 22 |
| 1-12 | 4,797 | 1,546 | 1,568 |
| 13-24 | 12,513 | 1,575 | 3,143 |
| 25-50 | 47,707 | 1,543 | 4,686 |
| 51-100 | 143,422 | 1,556 | 6,242 |
| 101-300 | 523,280 | 1,569 | 7,811 |
| 301+ | 268,259 | 1,565 | 9,376 |

实际唯一标签 9,376 条，少于设计里的约 10,024 条。0 距离带只有 22 条，与预期一致；
1-12 带去重后 1,546 条，是主要缺口；其余带各约 1,543 到 1,575 条。运行 wall 107.6s、
user+sys 106.3s、峰值 RSS 1,525,856 KiB，未触发 1800s 超时，因此这次是全量完成。

标签文件 validation/results/exp18-labels.csv 共 9,376 行数据。fast 列是当前候选
（source-short 150 配 mult2），exact 列来自 PDB 引导的搜索；带内几何列与标签列在两次运行
之间逐行一致，`pdb_prepare_s` 与微秒列是计时噪声，因此整文件不做字节级复现声明。
JSON 里给出每带的展开与耗时。

用这批标签看当前候选的跨距离误差（exact 当标签，proxyAcc 为本地代理指标）：

| 距离带 | 行数 | proxyAcc | MAE |
|---|---:|---:|---:|
| 0 | 21 | 54.74 | 71.5 |
| 1-12 | 1,546 | 70.18 | 53.7 |
| 13-24 | 1,575 | 79.27 | 37.5 |
| 25-50 | 1,543 | 88.01 | 28.4 |
| 51-100 | 1,556 | 92.23 | 29.7 |
| 101-300 | 1,569 | 95.07 | 32.6 |
| 301+ | 1,565 | 96.10 | 47.5 |

## 5. 证据与未验证边界

编译与运行命令（可复跑；当前生效批次是 §6 的 10024 条）：

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/query_profile_exp18b \
    tests/query_profile.cpp src/architecture.cpp src/router.cpp src/residue_estimator.cpp

# 每带 2 条的小配对，检查配对统计与退出码
./build/query_profile_exp18b --arch doc/eda比赛文件/arch --request delay_estimate_request.csv \
    --limit 1000000 --samples-per-band 2 --samples-per-tag 0 --landmarks 8 --pdb --residue-mult 1 \
    --dump validation/results/exp18b-pair-small.csv --json validation/results/exp18b-pair-small.json

# 99 行回归（全部行参与，不去重）
./build/query_profile_exp18b --arch doc/eda比赛文件/arch \
    --request validation/results/exp17-holdout99.csv --limit 200 --samples-per-band 99 \
    --samples-per-tag 0 --landmarks 8 --pdb-only --endpoint-mode source-short \
    --endpoint-short-distance 150 --residue-mult 2 \
    --dump validation/results/exp18b-regress-99.csv --json validation/results/exp18b-regress-99.json

# 10024 条跨距离标签（每带 1667，完整端点去重，固定种子 20260919）
./build/query_profile_exp18b --arch doc/eda比赛文件/arch --request delay_estimate_request.csv \
    --limit 1000000 --samples-per-band 1667 --samples-per-tag 0 --landmarks 8 --pdb-only \
    --dedup-endpoints --endpoint-mode source-short --endpoint-short-distance 150 --residue-mult 2 \
    --dump validation/results/exp18b-labels.csv --json validation/results/exp18b-labels.json

# 全部证据检查（99 行回归、10024 标签唯一性与计数、小配对求和）
python3 validation/exp18b_verify_regress.py
```

抽样种子固定在源码常量 kSampleSeed=20260919，去重路径按 band 使用 seed+band 派生随机数，
JSON 的 sampling 块记录 dedup 与 seed；命令行没有 seed 选项。标签只跑了单次，几何与标签列
在同配置下稳定，计时列随窗口变化，本日志不声明标签文件可字节级复现。

## 6. 18B 修正批次（2026-09-18 提交，取代 §4）

修正内容（2026-09-19，Asia/Shanghai）：

1. 端点键改为完整六元组 (x1,y1,p1,x2,y2,p2)，先对整带 pool 去重，再用固定种子
   20260919 的 std::mt19937 加 std::shuffle 均匀抽前 min(K,n) 个；旧的非去重路径保留原有
   步长采样，以便复用 622 条配对证据。JSON 记录 seed、dedup 与每带 raw_pool、unique_pool、
   selected；命令行没有 seed 选项，固定常量 kSampleSeed 与 band 一起决定每带随机数。
2. 标签模式的列语义修正：只有 PDB 引导的搜索在跑，测量值写入 expanded_pdb/us_pdb，
   expanded_base/us_base 在 CSV 里留空、在 JSON 里为 null，agree 记 -1；配对模式仍分列。
   stdout 在标签模式打印 "PDB run"，不再称 pair。删除了 JSON 里重复的 prefix_mismatches。
3. addSample 的分数改为用 pointOf 覆盖所有行，same-pin 且 exact=fast=0 的合法零对拿满点，
   相对误差分母仍只统计正参考。`--self-check` 新增零对、去重与定种子三项断言。
4. 99 行回归改为 --samples-per-band 99、不加去重，全部 99 行参与；新增
   validation/exp18b_verify_regress.py 用多重集键核对 exact 与 fast 两列，退出码即结论。

新批次结果（1M 取样，每带 1667，完整端点去重，seed 20260919，pdb-only）：

| 距离带 | raw pool | unique pool | selected | proxyAcc | MAE | 零 exact 行 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 22 | 22 | 22 | 56.797 | 68.27 | 1 |
| 1-12 | 4,797 | 4,797 | 1,667 | 68.857 | 56.75 | 0 |
| 13-24 | 12,513 | 12,513 | 1,667 | 78.681 | 39.15 | 0 |
| 25-50 | 47,707 | 47,707 | 1,667 | 87.405 | 30.40 | 0 |
| 51-100 | 143,422 | 143,422 | 1,667 | 92.588 | 27.67 | 0 |
| 101-300 | 523,280 | 523,280 | 1,667 | 94.805 | 34.19 | 0 |
| 301+ | 268,259 | 268,259 | 1,667 | 96.184 | 46.36 | 0 |

唯一标签 10,024 条，与设计值一致。公开 1M 的这些带里没有重复的完整端点对（raw 等于
unique），所以 18B 的去重本身不删行，旧批次的缺口全部来自错误的端口级键。分带样本等权
整体 proxyAcc 86.355（这是 10,024 条样本按条均分，其中 0 距离带 22 条、其余每带 1667 条；
既不是公开 1M 成绩，也不是近邻子集成绩）。运行 wall 129.0s、user+sys 131.1s、峰值 RSS 1,535,640 KiB，未触发
1800s 超时。PDB 构建 0.25s、prepare 18.33s（256 目标，计时外），不一致计数 0。

小配对核验：每带 2 条共 14 条，agree 全为 1，base 与 PDB 两列都有值，逐带展开数之和与
JSON 的 pdb_bands 一致（时间列允许每行一微秒的取整差），PDB 展开比值每带 0.001 到 0.011。
这些检查与 99 行回归、10024 标签的唯一性与计数一起放进 validation/exp18b_verify_regress.py，
输出三行 PASS 与 "all exp18b checks PASSED"，exit 0。

99 行回归（全部 99 行）：`python3 validation/exp18b_verify_regress.py` 输出
"99 rows, exact and fast match the committed files"，exit 0。旧的 85 行版本是取样不全的
证据，保留在 exp18-regress-99.* 里。

18B 证据：validation/results/exp18b-labels.{csv,json,txt,time.txt}、
exp18b-regress-99.{csv,json,txt,time.txt}、validation/exp18b_verify_regress.py。

新增未验证项：定种子抽样只在该种子下验证；标签仍只覆盖 7 个带，band 0 只有 22 条。

证据在 validation/results：exp18-pdb-100.{txt,json,time.txt} 与 /tmp/exp18/dump-100.csv、
exp18-regress-99.{txt,json,time.txt}、exp18-labels.{csv,json,txt,time.txt}。

未验证：

1. 当前标签 10,024 条，覆盖 7 个距离带；band 0 只有 22 条，短距离样本量小。旧的 9,376 条
   与 85 行回归是历史证据，已被 §6 批次取代。
2. exact 标签由 PDB 引导的搜索给出，其与基准 exact 的一致性在 622 条配对样本、14 条小配对
   与 99 行回归上实测为 0 不一致，未做全量比对。
3. 每带展开与耗时来自单次运行，窗口内 load 约 2 到 3；标签文件的计时列不可字节复现。
4. 本轮不改生产路径，不新增生产接口；1B 规模与 SOTA 未验证。
