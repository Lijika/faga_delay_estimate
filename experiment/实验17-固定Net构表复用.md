# 实验17 固定 Net 构表复用

日期 2026-09-18（阶段A 与阶段B 同日提交），基线 d2970bc。目标是用架构的固定 Net 消掉 residue 构表里的重复最短路，
让 mult=2 拿到稳定的综合分收益，并为更细格点腾出内存。

阶段A 只改构表方式，表内容与查询路径不变。阶段B 压缩 I* 目标列。

## 1. 阶段A 方法与数学

每个 Z_p 的 Net 位移固定为 v_p 并落在 I_p，reduced-cost 图里 Z_p 路径的第一条边就是这条
Net 加一条从 I_p 出发的 Arc，而 I_p 源正好把这些 Arc 以 residue 0 作为种子，所以对每个
象限与每个目标

    F(q, Z_p, t, r) = F(q, I_p, t, r - v_p) - (a_q*v_px + b_q*v_py)

两条零成本平凡路径不满足该平移关系，作为候选单独补齐，且都在平移槽先判 INF 之后才比较：
目标是 Z_p 且 residue 0 时为 0，目标是 I_p 且 residue 为位移余数时为 -(a_q*v_px+b_q*v_py)。
注释与实现只声称表值等价，不额外断言中间态的 dist 关系。

构表因此只对 208 个非 Z 源跑 Dijkstra，160 个 Z 源由对应 I 源的表平移填充。实测
Dijkstra 次数 1472 降到 832，与 368×4 与 208×4 一致。

## 2. 全表等价验证

tests/residue_table_equiv.cpp 用旧规则独立重建参考表（逐源 Dijkstra + 旧目标公式），
每次只持有一个源的 dist 数组，不复制生产表；读取生产表用测试文件里定义的
`delayest::ResidueTableAccess`（friend），生产类不暴露测试 API。

| mult | 比较项 | 差异 | Dijkstra 次数（记录/新/旧） | 最大 reduced | 平凡路径违规 |
|---:|---:|---:|---|---:|---:|
| 1 | 79,134,720 | 0 | 832 / 832 / 1472 | 16,200 | 0 |
| 2 | 316,538,880 | 0 | 832 / 832 / 1472 | 32,400 | 0 |

两张表中 INF 条目都是 0，所以本轮只覆盖了 INF 分支的代码路径，实际并未触发；不能据此
声称 INF 语义已验证。最大 reduced 分别为 16,200 与 32,400，都在 successors_ 的 uint16
存储范围内（65535），本轮没有溢出风险；mult=3 需要先审计该窄化，本轮不跑。

## 3. 输出等价与成本（本地代理分）

公开 1M 的旧结果 SHA 记录在 git 证据里（mult1 `4e4cca21819945a1…`、mult2
`3433bd19aa2f3145…`）。新旧二进制在同一输入上输出逐字节相同，1M、holdout32、holdout67
全部 cmp 通过，因此复用旧 SHA 即可，不为同一等价结论反复跑旧建表。`/tmp/exp15` 与
`/tmp/exp16` 已被系统清理，日志与证据文件保留哈希与合并后的 99 行留出集。

同窗口交错两轮（load 约 2，`/usr/bin/time` 的 user+sys 与 stderr 的 build 秒数）：

| 轮次 | 配置 | 总 CPU | build | RSS | 输出 SHA |
|---|---|---:|---:|---:|---|
| 1 | 旧 mult1 | 39.03s | 13.2s | 417,888 KiB | `4e4cca21…` |
| 1 | 新 mult1 | 33.66s | 7.1s | 417,904 KiB | `4e4cca21…` |
| 1 | 旧 mult2 | 91.20s | 59.7s | 1,345,136 KiB | `3433bd19…` |
| 1 | 新 mult2 | 62.82s | 29.6s | 1,345,208 KiB | `3433bd19…` |
| 2 | 旧 mult1 | 32.55s | 12.1s | 417,716 KiB | `4e4cca21…` |
| 2 | 新 mult1 | 29.01s | 6.1s | 417,816 KiB | `4e4cca21…` |
| 2 | 旧 mult2 | 83.70s | 54.8s | 1,345,108 KiB | `3433bd19…` |
| 2 | 新 mult2 | 55.85s | 28.3s | 1,345,188 KiB | `3433bd19…` |

构表时间 m1 少约 5.9s（−46%），m2 少约 28.5s（−50%）；配对总 CPU m1 少 3.5~5.4s，
m2 少 27.9~28.4s。按 exp16 的口径（Δproxy = 0.4376 − ΔCPU/120），mult2 相对 mult1 的
CPU 差从约 52s 降到约 24s，代理分从约 −0.0037 变为约 +0.23。这是本地筛选代理分，
1B 与 SOTA 都未验证。

## 4. 回归与边界

`verify_internal --quick` 只涉及未改动的 Router 与 Architecture，沿用实验16 的结果，
本轮不重复运行。查询路径未改，缓存与 endpoint 逻辑未改。完整的五次计时放在阶段B 完成后
的最终候选上。

未验证：mult=3 及以上（uint16 窄化未审计）；INF 非空架构；1B 规模；与 bias、PDB floor
的组合。

## 5. 阶段B 方法与数学（2026-09-18 提交）

I* 目标没有自己的列：它与同一个源的 Z* 列满足

    F(s, I_p, r) = F(s, Z_p, r - v_p) - (a*v_px + b*v_py)

所以存储只为 Z* 与 logic 目标建列（448 → 288），I* 目标记录它所属 Z* 目标的列号，查询时
按该列取值。查询的线性项可以合并，把位移换成 (dx - v_px, dy - v_py) 后
a*dx + b*dy + F(s, Z_p, r - v_p) - (a*v_px + b*v_py) 等于
a*(dx-v_px) + b*(dy-v_py) + F(s, Z_p, r - v_p)，因此不需要按象限存位移修正项。

实现上把 isNetSink 判断、列号、位移余数换算与 (lookupDx, lookupDy) 都放在四象限循环之外，
循环内只有一次查表加一次线性组合。真实端点坐标 sx/sy/tx/ty 与 Line 计费不变；端点模式、
缓存、bias、PDB floor 都没有改动。

| 项 | 阶段A | 阶段B |
|---|---|---|
| mult1 表 | 301.9 MiB | 194.1 MiB |
| mult2 表 | 1207.5 MiB | 776.2 MiB |
| mult2 峰值 RSS | 1,345,256 KiB | 903,664 KiB |

## 6. 阶段B 等价、成本与默认决策

全表等价仍用独立旧 Dijkstra 参考，参考侧对所有目标类都走旧目标公式，不调用查询路径。
压缩后的生产表由测试里的读取器（friend）还原 I* 值，还原公式与查询路径一致，因此这一步
同时检验了压缩存储与查询推导。mult1 79,134,720 项、mult2 316,538,880 项全部相等，0 差异，
平凡路径违规 0，最大 reduced 16,200 / 32,400 仍在 uint16 内。表内 INF 条目为 0，INF 分支
未实际触发。

同窗口交错两轮（A 与新 B 二进制，m1 与 m2 各两轮）：

| 轮次 | A m1 CPU/build | B m1 CPU/build | A m2 CPU/build | B m2 CPU/build |
|---|---|---|---|---|
| 1 | 26.80s / 6.4s | 28.18s / 6.2s | 60.28s / 31.7s | 53.74s / 29.1s |
| 2 | 28.33s / 6.3s | 26.97s / 6.8s | 60.01s / 32.0s | 57.27s / 30.2s |

RSS：A m1 417,936/417,828 KiB 对 B m1 307,488/307,600 KiB；A m2 1,345,256/1,345,228 KiB
对 B m2 903,448/903,600 KiB。四轮输出都与历史一致（m1 `4e4cca21…`、m2 `3433bd19…`）。

最终五次计时用同一个 B 二进制（`build/estimate-exp17b`），m1 与 m2 交错，同一窗口：

| 配置 | 五次 CPU | 均值 CPU | 峰值 RSS | 代理分 |
|---|---|---:|---:|---:|
| B m1 | 27.66 / 28.54 / 30.30 / 29.05 / 30.41 | 29.19s | 307,604 KiB | 94.5903 |
| B m2 | 55.35 / 57.82 / 54.18 / 55.03 / 56.63 | 55.80s | 903,640 KiB | 94.8062 |

Δproxy(m2−m1) = +0.2159。10M 重复各一次：m1 user+sys 32.42s、wall 33.08s、RSS 307,488 KiB、
输出 `bcc1f756…`，代理分 94.5633；m2 64.62s、wall 64.94s、RSS 903,664 KiB、输出
`ef42d345…`，代理分 94.7327，Δ = +0.1694，两次都是 9,000,000 次缓存命中。所有代理分都是
本地筛选值，1B 与 SOTA 未验证。

内存换算：903,664 KiB = 925,351,936 B = 925.4 MB 十进制 = 0.862 GiB 二进制，上限
2 GB = 2,000,000,000 B 与 2 GiB = 2,147,483,648 B 两种解释都通过。

10M 第一次运行 exit 4，原因是 /tmp 清理后 `/tmp/endpoint8/requests-10m.csv` 不存在；按公开
1M 请求重复 10 次（表头一次）重建为 /tmp/exp17/requests-10m.csv 后两次都成功。

**决策**：把默认 `residueMultiplier` 提升为 2（配 `source-short 150`）。依据是同一个 B
二进制、同一窗口的五次均值，1M 代理分 +0.2159、10M 口径 +0.1694；精度增益是确定性的
（公开 1M +0.547，两条 exact 留出集改善且 0 行变差，输出与历史哈希逐字节相同），峰值 RSS
0.862 GiB 仍在 2 GB 内。`-residue-mult 1` 仍逐字节复现 `4e4cca21…`。

默认提升后的复核：默认输出 `3433bd19aa2f3145…`，`-residue-mult 1` 输出
`4e4cca21819945a1…`，merged 99 行留出集默认 `cb348a7820a00678…`、mult1
`54d349893d3c1246…`。`endpoint_integration` 针对阶段B 查表路径重新构建并运行，144 checks，
0 failures（wall 30.06s，RSS 241,916 KiB，build 6.5s）。`verify_internal --quick` 只覆盖
未改动的 Router 与 Architecture，沿用实验16 的证据。

证据文件：validation/results/exp17a-bench-r{1,2}-{old,new}-m{1,2}.{time.txt,stdout.txt}、
exp17b-bench-r{1,2}-{a,b}-m{1,2}.*、exp17b-final-1m-{m1,m2}-run{1..5}.*、
exp17b-final-10m-{m1,m2}.*、exp17b-default-{default,mult1}.*、
exp17-table-equivalence{,-b}-mult{1,2}.{txt,json}、exp17-holdout99*.csv、
exp17b-endpoint-integration.*、exp17b-consistency-and-hashes.txt（十个 1M 输出、两个 10M
输出与 A/B/final 二进制 SHA）。大 CSV 在 /tmp/exp17。

## 7. 阶段B 未验证边界

1. mult=3 及以上未测；uint16 的 successors_ 窄化在 mult2 下最大 reduced 为 32,400，仍有约
   一倍余量，更大倍率需要先审计。
2. INF 分支在两张表中都没有实际条目，只覆盖了代码路径。
3. 官方 1B 规模未测；10M 是 1M 重复，9M 缓存命中，只说明重复负载下的成本。
4. 未测与 bias、PDB floor、以及其它 endpoint 模式的组合。
5. 计时窗口有其它作业，load 约 2；跨批次比较只用同窗口数据。
