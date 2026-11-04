# 实验22：独立的 AIR 式二维 map 基线

## 目标
按 doc/paper/01-AIR §III.A/Algorithm 3 做一个**独立**的二维 map 估计基线：真实 flood × 采样位置 ×
wire 家族，折叠成 map[起点家族][目标家族][|dx|][|dy|]。默认生产配置与根 `estimate` 不动，不训练校正，
不做 pruning，只留一版 map。

## 方法
- **论文算法**：`BUILD_MAP_LOOKAHEAD` 对每个采样位置、每种 wire 类型与方向，从参考节点做 Dijkstra
  flood，再把每个到达位置按 (wire, orientation, |dx|, |dy|) 折叠，同一格取**所有采样位置的最小值**。
- **Pango 适配**（`tests/air_map_probe.cpp`）：
  - wire 家族 = Z* 端口名的完整前缀（到 lane index 之前），共 20 类；**A/B 线型即使位移相同也分开**。
    每类的参考节点是该家族**最低 bus lane** 的真实 Z* 端口。
  - flood 直接用生产 `Router::distanceField`（经 `AirMapAccess` 测试 friend 调用，非复制搜索），
    landmarks=0、Router 内部 cache 关闭；field 是 uint16，新增**仅诊断**的 clipped 计数：出现
    finite > 0xFFFE 时必须显式失败而不能当作不可达。
  - map 维度 `[start family 20][target family 20][|dx| 0..119][|dy| 0..549]`、uint16：
    lane 由 target family 归并、采样位置由 MIN 归并，与论文的 MIN 一致。
  - 采样位置：四角+中心各取**最近的 exists SRB**（Manhattan 距离，tie 用架构坐标顺序），只依架构选择。
  - 端点接法：Z 源用其家族；I/logic 源枚举**同 tile 真实出 Arc 到 Z** 并加 Arc；Z 目标用其家族；
    I 目标用 `resolveNetPredecessor` 找最后一个 Z 原点加一次 Gap；logic 目标用 `incomingArcs`
    里的 I 前驱（该模板的 from 存在 `arc.to`）加 Gap+Arc。**Z 源/每个出 Arc 候选都要真实
    `resolveNet` 首跳有效**，否则该候选不成立（不能借其它采样位置的家族行预测可达）；同 pin=0；
    同 tile 直接 Arc 只是**候选**之一，与 map 路径一起取 min。map 无覆盖单独计 `map_miss`，
    不称原图不可达；缺项绝不用 residue 顶替。
  - 查询复用 `src/csv.h`（reader/writer/字段切分）与 64MiB `BoundedQueryCache`（同生产的 key）。
- 与论文 map 的差异（日志口径）：论文是 `map[wire][orientation][|dx|][|dy|]`，本适配把 wire 类型换成
  **含方向/跨度/A-B 的家族**，并增加 target 家族维度（用于表示指定 pin/落线），位移取绝对值；
  论文同时累积 delay 与 congestion，这里只有真实的 delay field；采样点固定 5 个。

## 结果（数字以 `validation/results/exp22.json`、`exp22-floods.csv`、`exp22-score.json`、
`exp22-holdout99.json` 为准）
- 家族 20、Z* 端口 160；采样点 (0,0)→**(16,0)**（(0,0) 无 SRB，最近 16）、(119,0)→(119,0)、
  (0,549)→(0,549)、(119,549)→(119,549)、(60,275)→(60,275)。
- **flood 100 次**：60 次覆盖整芯片（9,632,000 = 60,200 个 SRB tile × 160 端口），40 次只到自身
  （角点处该家族 Net 朝芯片外）：per-sample 10/10/10/10/0，**没有任何家族在 5 个采样点都退化**
  （即没有空 map 行）。`clipped=0` 全部 100 次 → uint16 足够（最远有限距离 8394）。首次 flood 4.74s。
- **map**：条目 26,400,000、有限 26,030,000（98.6%）、更新 83,850,397、分配 52,800,000B（=26.4M×2）。
- **field 校验**：9 例（起点零距离、7 个 stride 有限点、最长有限 8394）与 Router exact Z*→Z* 查询
  全部一致（0 不一致）；"出界无合法首 Net" 例：(16,0) ZSSA[0] flood 只到自身 finite=1，exact 到其它态
  = -1，一致。
- **构表成本（分阶段）**：`exp22.json` 的 `build` 阶段（arch load 之后到 field 校验结束：router init
  0.08s + 100 次 flood + 校验）**CPU 324.2s / wall 297.2s**（其中 flood 阶段 wall 297.0s）；
  整进程（构表 + 1M + 99 两个输入 + 写盘）在 `exp22.time.txt` 为 **CPU 327.65s（user 327.16 + sys 0.49）
  / wall 329.77s**，与 `exp22.stdout.txt` 的峰值 RSS 247,556KiB 同一次运行。
- **1M 请求**（默认配置同请求）：rows 1,000,000、有限 996,666（**覆盖率 99.67%**）、`map_miss` 3,334、
  原图不可达 0；逐行耗时 3.01s wall / 3.27s CPU。端点检查实际触发：`candidate_cannot_leave`
  **129,171**（出 Arc 的 Z 首跳无效被拒），`source_cannot_leave` 0；map 单元查询 77.1M、缺 0.61%。
- **公开分（golden 只在这里读）**：全量 1M accuracy **74.964**、MAPE **7.302%**、≤5% **51.33%**；
  排除 10,024 标签池的 989,976 行 holdout accuracy **75.156**、MAPE **7.220%**、≤5% **51.51%**。
  分带 accuracy（holdout）：1-12 **31.9%**、13-24 37.2%、25-50 43.1%、51-100 61.1%、101-300 77.0%、
  301+ **86.6%** —— 短距最差、长距最好。这与 map 折叠（5 个采样点 + 方向/位移取绝对值）会丢掉近场
  信息**一致**，也与 AIR 论文里 map lookahead 对长线更有利的动机一致；但本轮没有做单项消融，
  所以只记为假说，不作为因果结论。
- **99 stress 请求**（对既有 `exact` 列评分，未读 golden）：98 个 exact≥0 行 accuracy **62.9%**、
  MAPE **13.12%**、≤5% **43.30%**；唯一 exact=-1 行 AIR 也返回 -1（`source_cannot_leave` 1，一致）；
  `map_miss` 0；分带：`0` 4 行 100%、`1-12` 53 行 58.1%、`13-24` 32 行 71.2%、`25-50` 6 行 42.2%、
  `51-100` 3 行 50.7%。
- **内存**：进程峰值 247,556KiB（242MB），map 52.8MB，全部 < 2e9B（`budget_ok=true`）。
- **综合筛选分（CPU 含构表，0.8·holdout acc + 0.15·100·(1−CPU/1800) + 5）**：
  19C m2-off 94.9319（48.2s）、m2-xgb 96.5278（50.6s）、21 m3-off 94.7733（99.4s）、
  **22 AIR map 77.3943（327.7s）** → 作为独立估计器远落后于 residue 引擎，默认不动。

## 失败记录
- 首版 flood 后未把 field 缓冲重置为 INF，导致"无效首跳"的 flood 复用了上一次的 9,632,000 个有限值：
  该诊断因此报假不一致；改为每次 flood 前 `std::fill(field, kInf16)`（与 landmark 建表一致）。
- 首版对 stress 表只认 `From,To` 表头，把 `band,...` 表头当作 1 条请求（多 1 行且缺输出表头）：
  按已知 stress schema 用坐标列是否为数字判定并跳过表头，只取 x1,y1,p1 与 x2,y2,p2。
- 首版同 tile 直接 Arc 命中就提前 return，违反"作为候选"的设计；改为与 map 路径一起取 min，且
  source/target 候选为空时仍保留直接 Arc 答案。
- `AirMap` 的 block 最小值/最大值统计更新有误（新 slot 重置、已有 slot 下降不改最大值）：直接删掉
  这两项统计与输出列，只留总项/有限项/更新数；probe 内重复的 CSV 切分换成 `src/csv.h::splitCsv`。
- 采样家族参考节点按"最低 bus lane"选定后，角点上 8-10 个家族的 Net 朝芯片外（flood 只到自身）：
  这些位置由其它采样点补齐（检查项 `no_family_trivial_everywhere` 保证无空行），家族行在近场因此变薄，
  **可能是**短距误差的来源之一（未做消融，只作假说）。
- 编译失败（真实记录）：把 `splitCsv` 加进 `src/csv.h` 后，
  `g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -fsyntax-only tests/verify_estimator.cpp`
  在第 404 行报重载歧义（`delayest::splitCsv` 与该测试匿名 namespace 自己的 `splitCsv`）。
  最小修复：把该 helper 移回 `tests/air_map_probe.cpp` 的匿名 namespace，
  `src/csv.h` 恢复原内容（不含任何解析 helper），不再扩仓库解析重构；修复后 verify_estimator 与
  AIR probe 都能编译，已有 100 次 flood 结果按审查要求直接复用、未重跑建表。

## 未验证边界
- 只 5 个采样点、20 个家族、绝对值位移折叠：**近似，不宣称下界或上界**；无 congestion 项、无 pruning、
  无训练校正、未做路径解包；只窗口/全芯片内，不涉及跨窗口或 AIR 的 lazy/增量机制。
- 公开分只用公开标签与请求（选择偏差未消除）；综合分是**筛选分**（未测 5 次一致性）；`median_off` 与
  AIR 无关，本实验未采用。

## 复跑
```
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/air_map_probe \
    tests/air_map_probe.cpp src/architecture.cpp src/router.cpp
mkdir -p /tmp/exp22
/usr/bin/time -o validation/results/exp22.time.txt -f 'RSS=%MKib user=%U sys=%S wall=%e' \
    ./build/air_map_probe --json validation/results/exp22.json \
    --flood-log validation/results/exp22-floods.csv \
    --block-log validation/results/exp22-map-blocks.csv --out-dir /tmp/exp22
cp /tmp/exp22/air-1m.csv /tmp/exp22/air-1m-off.csv     # scorer 的结果名模板
cp validation/results/exp22.time.txt validation/results/exp22-1m-off.time.txt
build/venv-ml/bin/python validation/exp19c_score.py --out validation/results/exp22-score.json \
    --out-dir /tmp/exp22 --result-name air-1m-%s.csv --modes off \
    --timing-template "validation/results/exp22-%s-%s.time.txt" \
    --legacy-summary validation/results/exp22-summary.json
python3 validation/exp22_check.py     # map 汇总/端点接法/99 行评分小检查（不读 golden）
```
构表一次（约 300s）后串行跑 1M 与 99 两个输入；大 CSV 只在 /tmp/exp22。
