# 实验21：mult3 实际可行性与 uint16 缩窄检查

## 目标
先修 `ResidueEstimator::buildPotentials` 里已知的一处窄化（reduced cost 写进 `uint16_t` 前不校验上限），
再看 residue lattice 乘子 m=3 的候选是否真能跑：内存预算、1M 真实请求的 CPU/wall/RSS、表的独立等价、
m3 的公开分与综合筛选分。不改生产默认，不重训残差模型，不建 m4/m5。

## 方法
- **窄化修正**（`src/residue_estimator.cpp`，只在 `buildPotentials`）：保留原有 `reduced < 0` 检查，
  在 `static_cast<uint16_t>(reduced)` 之前新增 `reduced > 65535` 拒绝，错误信息给出数值、象限与 Z 端口对。
  该函数在 `buildTables()` 之前执行，所以超限在建大表之前返回。只修这一处已知窄化，不做通用兼容框架。
- **候选**：`build/estimate-exp21`（独立二进制，根 `estimate` 不动）：
  `g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/estimate-exp21 src/main.cpp
  src/architecture.cpp src/router.cpp src/residue_estimator.cpp`。
- **内存门**：先算 m3 表大小（4象限×368源×288存储target×1080残数×4B = 1,831,403,520B）加 64MiB 缓存，
  再用 2 行输入实测建表 RSS；预算 2,000,000,000B，RSS 超限直接判不合格。
- **等价**：复用 `tests/residue_table_equiv.cpp`（独立 reference，逐 source/quadrant 重建距离），
  `--mult 3` 全量比对；m1/m2 的等价证据继续复用（`exp17-table-equivalence-mult2.json`）。
- **holdout99**：由 `validation/results/exp18b-regress-99.csv` 的坐标生成 99 条请求，分别以 m2 与 m3 跑
  完整 residue 路径，逐行对照既有 `fast`（m2）与 `exact` 列。
- **评分**：只在最终离线评分读 golden，复用 `validation/exp19c_score.py`（行数/端点顺序/golden 端点/
  标签池校验不变），用 `--modes off --legacy-summary ... --timing-template ...` 输出 m3 分数；
  综合分用整进程 CPU（含建表），未做 5 次一致性，只作**筛选分**。

## 结果（数字以 `validation/results/exp21.json` 与其中列出的原始文件为准）
- **窄化负例（真实 mult5）**：`-residue-mult 5` → **exit 3**，
  `reduced edge cost 78300 exceeds the uint16 successor range (65535) at quadrant 0, Z port pair
  ZLS[0] -> ZSEA[0]`，RSS 47,120KiB（未到大表分配）；mult5 的表本身要约 5.1GB。
- **m3 通过内存门**：建表实测 RSS 1,897,304KiB、1M 首次运行 1,897,184KiB（user 96.97 + sys 3.87 =
  100.84s，wall 101.22s）、带 `time -o` 复测 1,897,280KiB（CPU 99.39s，wall 96.96s），都 < 2e9B
  （余量约 57MB）。两次 1M 输出**逐字节相同**（sha256 `5c6c26af...`）。建表 CPU：m2 28.57s vs m3 74.17s
  （2 行输入的计时 run），查询部分约 25.2s。
- **表等价（全量）**：m3 比对 **712,212,480** 项，**0 不一致**；`max_reduced=48,600`（< 65535，故新
  guard 对 m3 不触发；这也解释了 mult5 的 78300）；stored/reference INF 均为 0；
  trivial source/landing 违规 0/0；832 次 residue Dijkstra = 预期。448 个 target 全比对而只有 288 个
  存储列，**160 个被压缩的 I\* 列经派生路径一并验证**。m2 那一轮（316,538,880 项、0 不一致、
  max_reduced=32,400）继续复用。
- **holdout99**：m2 重跑与存档 `fast` 列 **99/99 一致**（同时验证请求映射与标签复用）。**分母写明**：
  99 行中有 98 行 exact≥0，另 1 行 exact=-1（架构内无合法路径），m2 与 m3 都返回 -1（一致）。
  在 **98 行（exact≥0）**上：m3 47 项非零、平均|误差| **24.327**、最大 222；m2 50 项非零、
  **25.051**、最大 222；m3 好/平/差 = **27/68/3**。把那条 exact=-1 按 0 误差计入 **全部 99 行**时：
  均值 **24.081/24.798**、好/平/差 **27/69/3**。JSON 的 `finite_exact_scope`（98）与 `all_rows_scope`
  （99）两个分母都写出，不再只有一个混合口径。
- **公开分（golden 只在这里读）**：m3 全量 1M accuracy **94.427**、排除 10,024 标签池的 989,976 行
  holdout accuracy **94.502**、MAPE **1.406%**、≤5% **94.77%**、MAE 35.29；标签池完整消费、0 重复键。
  对比 19C 复用证据：m2-off 94.089 / 94.167 / 1.491% / 94.44%，m2-xgb 96.116 / 96.187 / 0.967% / 98.07%。
- **综合筛选分**（0.8·holdout acc + 0.15·100·(1−CPU/1800) + 5，CPU 含建表）：
  m2-off 94.9319（48.23s）vs **m3-off 94.7733（99.39s）**：accuracy +0.335 点，但 CPU +51.16s，
  筛选分反而降 0.1586 → **不提升默认**（`promote_default=false`）。m2-xgb 96.5278 仍远高（m3 不适配
  A 模型）。`median_off` 是沿用 m2 训练残差偏置的 19C 中位基线，**不是 m3 拟合、本轮不采用**。
- **A 模型约束未解除**：`-residue-mult 3 -residual xgb` → **exit 2**
  （`-residual requires -residue-mult 2, -endpoint-mode source-short, no bias and no pdb floor`），不重训。
- **停止扩表**：m3 无净收益、mult5 已超 uint16 且需约 5.1GB，**m4/m5 表不建**。

## 失败记录
- 修前 mult5 会把 78300 静默截成 uint16 再继续分配约 5GB 的表；现在在建表前 exit 3 并给出数值/端口对。
- 首次 1M 的 `/usr/bin/time` 输出被 tee 只截到 `exit=0`（重定向写错文件）：改用 `time -o` 复测一次，
  复测输出与首次逐字节相同，因此这次复测同时充当确定性与计时证据。**建表运行次数（全部在案）**：
  m5 两次（都在建表分配前 exit 3）、m2 三次（2行投影、2行计时记录、99行 holdout 对账）、m3 五次
  （2行投影、2行计时记录、99行 holdout、1M 首次、1M 计时复测）；两次 2 行 m2/m3 的投影运行值在终端
  输出中，其记录版本就是 JSON 引用的两个 `exp21-*-2rows.time.txt`。没有为补报告字段再新增建表。
- 评分入口扩展 `--modes` 时先用 `MODES` 后 `global`（SyntaxError，被小 fixture 测试抓到）；
  之后又把 10M block 循环放宽到全部 MODES，给 19C JSON 多加了 `blocks_10m.long=null`：改为只遍历
  19C 的 off/xgb 对，之后 19C 的两个产物**逐字节不变**（`--modes` 现在也显式要求含 `off`，否则 exit 非 0）。
- `--modes xgb`（缺 off 基线）原先会被当作独立模式评分；现在直接拒绝，fixture 覆盖 off 单模式 +
  自定义 `--legacy-summary`/`--timing-template` 两个新路径。

## 未验证边界
- 只修了这一处已知窄化，未做通用 uint16/权重上限框架；m3 是候选，不是默认。
- m3 表全有限（INF 条数 0），"不可达"表路径本轮未在 m3 上出现；未建 m4/m5；未测 10M。
- 公开分只用公开标签与请求（复用带来的选择偏差未消除）；5 次一致性未测，综合分只称筛选分。

## 复跑
```
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/estimate-exp21 \
    src/main.cpp src/architecture.cpp src/router.cpp src/residue_estimator.cpp
# 窄化负例（预期 exit 3，78300）
./build/estimate-exp21 -arch "doc/eda比赛文件/arch" -in /tmp/exp19c/2rows.csv -out /tmp/exp21/m5-2rows.csv \
    -residue-mult 5 -endpoint-mode source-short -endpoint-short-distance 150 -residual off
# m3 全量（约 1.9GB RSS / 100s CPU）
/usr/bin/time -o validation/results/exp21-1m-off.time.txt -f 'RSS=%MKib user=%U sys=%S wall=%e' \
    ./build/estimate-exp21 -arch "doc/eda比赛文件/arch" -in delay_estimate_request.csv \
    -out /tmp/exp21/m3-1m-off.csv -residue-mult 3 -endpoint-mode source-short \
    -endpoint-short-distance 150 -residual off
# 表等价（全量 712,212,480 项，约 6 分钟）
./build/residue_table_equiv-exp21 --arch "doc/eda比赛文件/arch" --mult 3 \
    --json validation/results/exp21-table-equivalence-m3.json
# 评分（唯一读 golden 的步骤）
build/venv-ml/bin/python validation/exp19c_score.py --out validation/results/exp21-score.json \
    --out-dir /tmp/exp21 --result-name m3-1m-%s.csv --modes off \
    --timing-template "validation/results/exp21-%s-%s.time.txt" \
    --legacy-summary validation/results/exp21-summary.json
build/venv-ml/bin/python validation/exp19c_score_test.py   # 评分入口回归（默认路径逐字节不变）
python3 validation/exp21_report.py   # 从上面这些原始文件汇总出 validation/results/exp21.json
```
