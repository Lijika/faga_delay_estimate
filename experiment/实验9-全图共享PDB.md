# 实验9 全图共享、可证明下界的 PDB

日期 2026-09-17，基线 04083a9。本阶段只新增 PDB 与其探针，不碰 Router、ResidueEstimator、
main 与默认链接。新增文件：src/pattern_database.h（header-only）、tests/pattern_database_probe.cpp、
本日志、validation/results/pdb-*。

结论：抽象图 59,520 状态、每目标 4 张反向 Dijkstra 表，势函数审计与篡改自检都通过；
99 行既有 exact 样本（67 行实验5 样本加 32 行端点留出）上 L_pdb 无一超过 exact、无一低于线性界，
35 行取到 exact；86 个已建 target 的全部 Z 抽象状态都是有限值。候选可进入与 ALT 的组合比较阶段。

## 设计

抽象图保留全部 496 个已发布端口与位移余数（水平模 10、垂直模 12），状态数 120 × 496 = 59,520。
每条真实边映射为一条抽象边：Arc 位移为零，归并后的真实 Net 跳带实际位移与 block 费
（gap 减 mandatoryLine）。Line 费不进图，查询时单独加，与实验5 一致。

势函数。四个象限各做一次全端口 Bellman-Ford，超级源初值全零；斜率直接从 arch 推导，
不建立 ResidueEstimator：对每个 Z 端口取其 Net 位移与该端口最便宜自环 Arc 费，
同一符号方向取每单位位移的最小值再乘周期 S。实测 Mx=10、My=12、S=60，
四象限 (a,b) = (750,635)、(750,-625)、(-750,635)、(-750,-625)，与实验5 记录一致。
边权 w = S*cost - a*dx - b*dy，reduced cost 为 rc = w + h[u] - h[v]。

可采纳性。真实路径的位移望远镜求和为 a*dx + b*dy，reduced cost 望远镜求和为

    sum rc = S*pathCost - a*dx - b*dy + h[s] - h[t]

故 S*d >= a*dx + b*dy + dq[(-dx mod Mx, -dy mod My, s)] + h[t] - h[s]，其中 dq 由从
(0,0,target) 出发的反向 Dijkstra 给出（反向边保留 rc，位移取负）。于是

    L_q = max(0, ceil((a*dx + b*dy + dq[(-dx mod Mx, -dy mod My, s)] + h[t] - h[s]) / S))
    L   = max_q L_q + mandatoryLine(s,t)

每个象限单独有效，取 max 仍有效；Line 必须被跨过至少一次，其费用由 resolveNet 计入。
抽象 PDB 与 max 组合的依据是 Culberson 与 Schaeffer 的 Pattern Databases §3 Lemma 1：
"For any state, for any pattern database, the cost of the pattern induced by the state with
respect to the database is a lower bound on the cost of the state."

## 实现与接口

PatternDatabase 只依赖 Architecture，header-only，不改任何既有手工链接命令。init 约定每实例一次，
且会清空旧表、旧 target 信息与统计，重复 init 不会复用上次的缓存；查询入口是 const 且无副作用，
不在热路径计时也不累计统计。prepareTarget(port) 按需建立该目标的 4 张反向表并缓存，
缓存上界就是端口总数 496。lowerBound 与 linearBound 同参数，另有 pinsValid、isPrepared、stats、targets。
lowerBound 的一次调用里，std::map 查 target 表与互补余数 (-dx mod Mx, -dy mod My) 只在四象限循环外做一次；
同 pin 返回 0，非法 pin 返回 false，未建表的目标直接抛错而不是当成 0；表值用 int32 存储，
构建时检查溢出，算术用 int64。unsupported（四个象限全为无穷）返回 false 并计数，绝不把无穷改成 0。

两处硬失败。其一，审计发现负 reduced cost 时抛错，探针捕获后写出证据 JSON 并 exit 1，
不再「只计数继续」——负 reduced 意味着势函数在真实图上不可行，此时任何反向表都不可信。
其二，反向 Dijkstra 用 int64 累加，一旦候选值触及 int32 sentinel（kInf32）就抛错，
明确区分「不可达」与「有限但溢出」；只有检查通过后才写入 int32。当前架构不触发这两条。
斜率周期用 C++17 的 std::lcm/std::gcd，没有自制版本。

## 审计与自检

真实 hop 9,417,280 条、无效 hop 214,720 条、归并类型 240 种、Arc 8,192 条，
reduced cost 检查 4 × 8,432 = 33,728 次，min_reduced=0，negative_reduced=0，
Bellman-Ford 轮数 4/3/4/3。篡改势函数自检：把一个有出边的端口电位加 max(1, min_reduced+1)，
审计必须给出负值，实测 tampered_min_reduced=-1，自检通过（自检模式单独运行 exit 0）。

## 验证

样本 99 行，来自 validation/results/linear-bound-samples.csv（67 行，含 exp4 见证与 exp5 规则）
与 validation/results/endpoint-holdout-exact.csv（32 行，表头不同），exact 列直接复用，不重算。
98 行支持、0 行 unsupported、0 行非法 pin、1 行不可达（SRB_33_0/ZSSA[5] -> SRB_33_12/A_CD，
与实验5 记录一致）。

| 检查 | 结果 |
|---|---:|
| L_pdb > exact | 0 |
| L_linear > exact | 0 |
| L_pdb < L_linear | 0 |
| L_linear 与 CSV 的 L 列不一致 | 0 |
| L_pdb == exact | 35 / 98 |
| 输入行数 67 + 32 = 99 且可达 98 | 是 |

输入不变量已写进退出码：行数不是 67 + 32、可达不是 98、出现非法 pin 或 unsupported 都会失败，
所以空输入、截断读取或缺列不可能静默通过。失败类共十一种一起计入 failures.total：
audit（负 reduced）、L_linear > exact、L_pdb > exact、L_pdb < L_linear、CSV 线性界不一致、
非法 pin、unsupported、输入计数不符、Z 覆盖不全、篡改自检、边界用例（同 pin、非法 pin 拒绝、未建表抛错）。

线性界列与实验5 的 CSV 逐行相等，说明斜率与势函数推导独立复现了实验5 的界。
平均 gap：PDB 61.31 对线性界 240.00；94 行 PDB 严格更紧，4 行相等。
最大 gap 780（rule-31，SRB_72_120/ZDW[6] -> SRB_72_132/ILW[5]，exact 1322，PDB 542）。

已知样例：exp4 见证 28 行全部取到 exact，含 292 的八个端口对、400、402 与零费 Net（0）；
Line 样例（exact 9、78、98）也在 PDB 上取到 exact；holdout 32 行中 6 行取到 exact，
例如 179 -> 179 两行，439 -> 421（gap 18）。

## 覆盖与代价

86 个 target 建表，全部 Z 抽象状态有限：每个 target 的 Z 状态 19,200 × 4 象限 = 76,800 全部有限；
每个 target 的有限状态总数为 176,640（56 个 target）或 176,644（30 个 target），
占 238,080 的 74.19% 到 74.20%。表字节 952,320 B/target，86 个 target 共
81,899,520 B（78.1 MiB）。若把 496 个 target 全部建表，需要约 450 MiB，接入 Router 需要预算或按需池。

三次测量，输入相同，warm checksum 都是 398372585，热查询都是 1,000,090 次调用：

| 运行 | exit | RSS | user / wall | init | 86 target 建表 | 热查询 |
|---|---:|---:|---:|---:|---:|---:|
| 修复前 pdb-audit.* | 0 | 86,604 KiB | 5.98s / 5.73s | 0.260s | 5.306s | 57.5 ns/call |
| 修复后空载 pdb-audit-timed.* | 0 | 86,684 KiB | 5.20s / 4.93s | 0.217s | 4.579s | 49 ns/call |
| 修复后与 endpoints 集成回归并行 pdb-audit-review.* | 0 | 86,640 KiB | 6.62s / 6.25s | 0.333s | 5.746s | 64.7 ns/call |

引用修复后空载一行；修复前一行作对照；并行一行只说明争抢影响，不作吞吐结论。

热查询的说明（空载 49 ns、并行 64.7 ns）：benchmark 只在这批 98 个支持行上循环，
反复读同样的 392 个抽象状态，
测到的是热重复访问成本，缓存命中率没有测；它不是 Router 真实查询流的成本。真实流每次查询要在
该 target 的 4 张共 952,320 B 的表上各取一个 int32，缓存缺失会成为主要开销；
与 Router 现有 landmark/ALT 的性价比比较留给下一阶段实测。

## 全目标覆盖与代价（496 target）

`--prepare-all` 把全部 496 个已发布端口都建成 target，探针把任何一个 target 的 Z 抽象状态不全有限
都计入失败，所以这一模式既能给出全覆盖检查，也能给出满缓存的代价：

- 448/496 个 target 的 Z 状态全部有限（每个 76,800/76,800）；有限状态总数 176,640（320 个 target）
  或 176,644（128 个 target）。
- 48/496 个 target 不满足：每个只有 4 个有限状态。原因已定位：这 48 个端口在抽象图里入度为 0
  （没有任何 Arc 或 Net 边进入），反向表只剩目标自身的四个象限状态。它们正是
  A_{A..H}{Q0,Q1,Y} 与 S_{A..H}{Q0,Q1,Y} 这 24+24 个端口名。探针对到它们的查询返回 unsupported，
  不会把无穷改 0；该次运行 failures.total=48、exit 1，是预期的诊断结果而不是工具故障。
- 请求适用性：/tmp/endpoint8/requests-1m.csv 的 1,000,000 条请求里，目标是这 48 个端口的为 0 条；
  32 条 holdout 请求同样是 0 条。1M 文件里出现 256 个不同 target 端口名，全部落在 448 个全覆盖端口内。
- 代价：496 张表共 472,350,720 B（450.5 MiB），prepare-all 部分 19.361s，RSS 466,992 KiB，
  该次运行 user 25.68s、sys 0.53s、wall 26.80s；同样的 99 行验证结果不变（0 违规、35 行取到 exact），
  产出的 CSV 与其它三次逐字节相同。
- 给 Router 的条件因此可以写成：448 个 target 可直接用；48 个入度为 0 的 target 必须显式回退，
  不能把无穷当 0。

## 复核发现的重复 init 缺陷与修复

复核发现 init 只清空表、target 信息与统计，而 mergeHops 只用 reserve 与 append 填 netTypes_ 与 edges_。
复现（修复前二进制，同一实例连续两次 init）：hop_types 240 -> 480、reduced_checks 33728 -> 68416、
Bellman-Ford 轮数 4/3/4/3 -> 3/2/3/2；重复 init 会把审计集翻倍，换架构还会混入旧图。

修复只有两行：init 内加 netTypes_.clear() 与 edges_.clear()，与 tables_、targetInfo_、stats_ 的清空放在一起。

回归测试加在既有 --self-check 路径，不新增文件：同一实例第二次 init 后检查 hop_types、reduced_checks、
minReduced 与首次一致、缓存已清空、重新建表后同一查询值不变。修复前该检查 exit 1
（validation/results/pdb-self-check-repeat-init-before-fix.txt：hop_types=240->480、reduced_checks=33728->68416、
pass=no），修复后 exit 0（validation/results/pdb-self-check-review.txt：hop_types=240->240、
reduced_checks=33728->33728、cache_cleared=yes、query=8224->8224、rebuilt_tables=952320、pass=yes）。

## 复现命令、文件身份与计时保留

```sh
# 编译
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/pattern_database_probe \
    tests/pattern_database_probe.cpp src/architecture.cpp
# 自检
./build/pattern_database_probe --arch doc/eda比赛文件/arch --self-check
# 99 行审计
timeout 600s /usr/bin/time -f "RSS=%MKiB user=%U sys=%S wall=%e" -o <time.txt> \
    ./build/pattern_database_probe --arch doc/eda比赛文件/arch \
    --json <json> --csv <csv> > <stdout.txt> 2>&1
# 修复后空载计时（86 个 CSV target）
timeout 600s /usr/bin/time -f "RSS=%MKiB user=%U sys=%S wall=%e" \
    -o validation/results/pdb-audit-timed.time.txt \
    ./build/pattern_database_probe --arch doc/eda比赛文件/arch \
    --json validation/results/pdb-audit-timed.json --csv /tmp/pdb-samples-timed.csv \
    > validation/results/pdb-audit-timed.stdout.txt 2>&1
# 全部 496 个 target 的覆盖与满缓存代价
timeout 900s /usr/bin/time -f "RSS=%MKiB user=%U sys=%S wall=%e" \
    -o validation/results/pdb-alltargets.time.txt \
    ./build/pattern_database_probe --arch doc/eda比赛文件/arch --prepare-all \
    --json validation/results/pdb-alltargets.json --csv /tmp/pdb-samples-alltargets.csv \
    > validation/results/pdb-alltargets.stdout.txt 2>&1
```

SHA256（当前二进制与源码）。build/pattern_database_probe
40a39eaa8830a6b936366e8fbe2037431dc3f498e818a386f216fef42b8eeaed；
src/pattern_database.h ab57e90eaed93d1eb2bf0ce7013ee0e8cdc43726ae0ae60564f22ee06c913dd8；
tests/pattern_database_probe.cpp 2705ee3b327261bd86cdab126d0b8f7aaac852c5f92f23f7d453954f5b3d6f92。
历史二进制 dc39251a109d4bef7e8627ae6f75fb7325602ed3d773ea62390373f60cbf18ed（加扩展前）产生了
validation/results/pdb-audit-review.*，其余产物由当前二进制产生。
输入身份。validation/results/linear-bound-samples.csv
9bdfe717e11d411264c28f2f77feaf18b12931a47b4f77120d2ab1a91fa902ee；
validation/results/endpoint-holdout-exact.csv
a3bd69d4a643f0d9cb1d5c460596bec3a48f708a81427df82e131a4b60cb75e8。
输出。修复前 pdb-audit.json 48eb1667fd552c4fa8af19efe0e59533c605f479e237777546b65b6b7a28a69e；
修复后空载 pdb-audit-timed.json 75933d3c1f01e1eff9b75334ba60f9d4a13a36b0a6b5a4aa8d395b4649c61124；
496 target 的 pdb-alltargets.json 702805fd6d7cb0c1554def263921bcbce0672d34c774a618310a1e212653c128；
修复后并行 pdb-audit-review.json 4714288b4622eaf023cbd7ad8c99f9b524ff5aad543d94ff29b9c48d2183a89e。
四份样本 CSV（pdb-samples.csv、pdb-samples-review.csv 与两次临时输出）逐字节相同，
sha256 都是 284255fa3fadafc5706b029035e5b60eec530b184eb70f5015b256b35448009f；
除 timing 与 memory 外，修复前与修复后的 JSON 字段完全一致，warm checksum 四次运行都是 398372585。

计时的保留方式见「覆盖与代价」的三行表：修复前一行保留为对照，正文引用修复后空载一行，
并行一行只作争抢说明。重复 init 修复只影响 init 内两个 clear，查询路径未改。

## 适用条件与限制

1. 只适用于当前 arch：斜率、S、Mx、My 都由 arch 推导，换架构必须重新 init（实测 0.26s）。
2. 只覆盖已发布端口；非法 pin 明确拒绝，同 pin 为 0，未建表的目标抛错。
3. Line 费不在抽象图内，由 mandatoryLine 精确补齐；抽象图不含 Line 边。
4. unsupported 只表示抽象状态无穷，探针拒绝该查询并计入退出码；本批样本为 0。
5. 给 Router 用时必须检查每个已支持 target 的全部 Z 抽象状态有限：样本用到的 86 个 target 全部通过，
   496 个端口的全量检查是 448 个通过、48 个入度为 0 的端口不通过，这 48 个必须显式回退；
   不能随状态把无穷改 0，否则可能破坏一致性并影响依赖一致性的搜索。
6. 审计必须保持硬失败语义：负 reduced cost 或 int32 溢出都终止，不允许降级成警告。
7. 查询热路径 49 ns（空载，热重复访问）比实验5 线性界的 40.8 ns 贵；真实流的代价还取决于表缺失，
   是否接入 Router 由下一阶段的组合比较决定。
