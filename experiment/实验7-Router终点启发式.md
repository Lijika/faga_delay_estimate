# 实验7 Router 终点启发式审计与修复

日期 2026-09-17，基线 cff6aa3。涉及文件：
tests/router_terminal_probe.cpp、validation/results/router-terminal-*.{json,stdout.txt,time.txt,sha256}、
src/router.h、src/router.cpp、src/architecture.h，以及本日志。endpoint 相关文件属于并行会话，未触碰。

## 代码核对

调用关系。buildSpanHeuristic 只在 Router::init 调用一次（src/router.cpp:38），按每条 Net 落点 I 端口的
最便宜出弧给该跳定价，容量为名义 span 加水平 Block 跳格奖励，DP 得 spanBound_。spanBound_ 只被
heuristic()（src/router.h）用于 search 的种子入堆与陈旧项判定。computeTargetBounds 只被 Router::search
调用一次；distanceField 只服务 buildLandmarks。

结构性触发。spanBound_ 假设每一跳之后都要付一次落点出弧，但目标本身是 I 端口时最后一跳只有 Net，
没有尾随 Arc，跳费可以为零。名字核对结果，ZDEA[0] 不存在于 SRB_Port.json，真实名字为 ZDE[0] 到
ZDE[7]；审计用 ZDE[0] 构造了同类反例。

## 修复实现

1. span credit。search 中当目标是 I 端口时取该端口最便宜出弧作为 terminalCredit_，
   heuristic 的 span 项改为 max(0, spanBound - terminalCredit_)，其余目标 credit 为 0。
   所有合法到 I 的路径在末端都可接该 Arc，缺少它时界可能大于真实距离，扣除后界可采纳；
   同一常数对所有状态扣除并在 0 处截断，Z 图各边一致性保持。查询时按目标出度求一次，未新建表。
2. 真实前驱 geometry helper。src/architecture.h 把逐坐标逻辑提为 private resolveOffset(x, y, dx, dy)，
   resolveNet 与新增 resolveNetPredecessor 都是薄封装，反向传负位移；未复制 Block/Line 算法，
   未建逆表。全量互逆检查通过，见下。
3. computeTargetBounds。I 与 logic 分支改用 resolveNetPredecessor 的真实前驱，费用为真实 gap
   加 terminal Arc（logic 目标），对完整真实前驱集合取 min；Z 目标仍直接读 landmark 表。
   旧实现用 tx-net.dx、ty-net.dy 的名义前驱，Block skip 时会漏掉真实候选，而 logic 目标是在
   多前驱上取 min，漏项可能让这个 min 变大，不再保证是下界。

## 已验证项

helper 全量互逆。命令
`g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/router_terminal_probe
tests/router_terminal_probe.cpp src/architecture.cpp src/router.cpp` 编译通过；
`./build/router_terminal_probe --arch doc/eda比赛文件/arch --helper-check` 输出
forward_valid=9417280、reverse_valid=9417280、两侧 mismatch 均为 0、counts_equal=yes、0.60s，
exit 0，RSS 47124 KiB。

正向语义未变。build/verify_internal 在 architecture.h 改动之后重新编译
（mtime 20:51:39 晚于 architecture.h 的 20:50:32），`--resolver` 的全量独立 resolver 对照
（10,560,000 组，0 mismatch）通过，`--quick` 的 counts 与八条路径也通过；本轮以 --resolver 结果为准。

span 修复前后对照（同一探针、144 例、plain Dijkstra 为参考）：

| 配置 | 修复前 初始 h 大于 exact | 修复后 |
|---|---:|---:|
| span-only | 17，超出量之和 802 | 0 |
| ALT-only k=1 | 0 | 0 |
| span+ALT k=1 | 17，超出量之和 802 | 0 |

修复前 stdout 原样保存为 validation/results/router-terminal-before.stdout.txt，
来源 /tmp/eda7c.txt（sha256 记于同目录 .sha256 与 time.txt），修复后输出为
validation/results/router-terminal-after-span.json（只含 span credit 修复的表列数据），
而 computeTargetBounds 改写之后的完整四配置运行见下一节
validation/results/router-terminal-after.json。修复前样本里的答案全部正确，
仅初始界不满足可采纳性。

初始界口径。Router::Stats::initialBoundSum 是各 seed 的 min(g+h)，不是 h 之和；
单一 Z 源时等于该 seed 的 h。探针只在单 Z 源上断言初始界不超过 exact，答案比较对所有源执行。

## 正式运行结果（修复后）

命令与产物。

```sh
timeout 600s /usr/bin/time -f "RSS=%MKiB user=%U sys=%S wall=%e" ./build/router_terminal_probe \
    --arch doc/eda比赛文件/arch --json validation/results/router-terminal-after.json \
    > validation/results/router-terminal-after.stdout.txt
```

exit 0，RSS 484,700 KiB，user 38.19s，sys 0.99s，wall 39.01s。Router 构建 19.65s，
其中 1 landmark 建表 6.23s，144 例乘三种启发式配置加 radix 的查询 12.38s。

主样本 144 例，参考仍为 plain Dijkstra：

| 配置 | 答案不一致 | 初始 h 大于 exact |
|---|---:|---:|
| span-only | 0 | 0 |
| ALT-only k=1 | 0 | 0 |
| span+ALT k=1 | 0 | 0 |
| span+ALT k=1 radix | 0 | 未单独断言（答案与二叉堆逐例一致） |

近场 ALT 诊断。源为 landmark 状态 SRB_115_530/ZSEA[0]（buildLandmarks 的 kXs 与 kYs 叉积中
x+y 最大者，车道取升序第一个 Z 端口），枚举 landmark 行及其上下各一行的有效源单元乘全部 Net，
按真实 resolveNet 落点与目标 pin 去重，取 logic-out 16 条、I 端口 8 条，共 24 条，全部可达并测完。
结果 bound_above_exact=0、answer_mismatch=0，未发现反例，命中即停的规则没有触发。

回归清单 9 条，failures=0，覆盖两条零费 Net 到 I、Line 费 Net 到 I、skip Net 到 I、
Net 到 Z 最便宜 Arc、Net 到 logic 输出 Arc、两条同格 Arc 以及一条两跳 Net 到 I 链。
radix 队列与二叉堆在全部样本上答案一致，answer_mismatches=0。
JSON 的 failures.total=0，五类失败计数（主答案、主初始界、ALT、回归、radix）全部为 0。

修复前 ALT 的证据状态。旧实现用名义前驱 tx-net.dx、ty-net.dy，且 logic 目标在多前驱上取 min。
修复前的 144 例主样本上 ALT-only 记录到零次初始界违规与零次答案不一致，这是局部证据。
其后两次扩展采样（近场枚举与按归并类型首例的远距采样）都因为远距 plain 查询开销过大而提前终止，
没有形成完成结果；y=0 的样本本身有效，只是未能在预算内跑完。
因此旧 ALT 的全局安全性没有建立，也没有观察到旧 ALT 的错误答案。
本轮的近场诊断运行在修复后代码上，不能当成对旧实现的验证。

## 限制

1. 只测 1 个 landmark，多 landmark 与 landmark 位置的影响未测。
2. 近场 ALT 诊断的上限是 16 条 logic-out 与 8 条 I 目标；未命中反例不等于全局安全。
3. span credit 只覆盖 I 端口目标；Z、logic 目标的末步本来就要付 Arc，credit 为 0。
4. 本轮未运行百万行评分，未重建根 estimate（estimate 仍是 45b592f2...）。
