# 实验20A：窗口内显式port图的两级CRP

## 目标
实现 doc/paper/13 的多级customization与组合查询：同一窗口内，plain(G0)、一级overlay(H1)、
两级overlay(H2)三种查询对同一冻结请求列表给出一致结果，并给出真实成本。只做窗口内原型，
不读 golden、不算公开1M分、不改生产默认。

## 方法
- 测试helper（后续CCH/TNR/HL复用）：`tests/window_graph.h` 建窗口内显式port图，状态是完整
  (tile,port)，保留lane与方向；同tile原始Arc（同(from,to)取最小delay，与生产router一致）；
  每个真实Z经 `resolveNet` 连到落点I，跨cell费用只在Net边上计一次；落在窗口外的边丢弃，
  故结果严格称为窗口内exact。非SRB tile保留allocated槽但不参与请求池。
- `tests/crp.h` 两级结构：两级嵌套方格；entry有入跨cell边、exit有出跨cell边；每cell完整
  entry→exit矩阵由限制在该cell内的Dijkstra定制（矩阵不含跨cell边），二级矩阵在一级的
  H1 overlay上于父cell内再定制；查询时源/目标一级cell展开G0、源/目标二级cell其余区域展开H1、
  外部展开H2，路径可离开并重入；1级消融与2级查询复用同一套矩阵。
- 独立参照：探针内独立plain Dijkstra，直接查询源/目标port状态；不复用 plan_probe 的
  terminalCost。

## 验证
- 人工有向图（8x4，非对称权重、零成本、单向、有出边/无出边、跨cell重入）：1024 全对 ×
  1级/2级 与参照逐对相等（0 不一致），不可达 223 对，2级实际被用 250 对；2级未被用则判失败。
- 真实窗口（seed 20260919，冻结请求列表，每窗口 ≥160 条：合法walk、Z/I/logic 各类端点、
  同pin、无出边源构成的不可达对）：1级/2级与参照逐条相等；矩阵每行含全部exit（entries>0 的cell
  检查 stride==exit 数，row_problems=0）。
- Block窗口先确认真实hop：ZLE[0]→ILE[0] delay=370 net=16 落在 (90,100)，该边加入冻结列表
  （kind=block-hop）；hop 缺失即判失败。
- JSON 用 std::ostringstream 写出（不再用固定缓冲 snprintf），`validation/exp20a_verify.py`
  实际 json.load 后逐行CSV重算行数、matched/unreachable/level2_used、各模式延迟平均/p95、
  展开与扫描平均/p95，与JSON一致才 PASS。

| 窗口 | allocated/valid states | cells L1/L2 | entries L1/L2 | matrix | 请求/不可达/H2用 |
|---|---|---|---|---|---|
| (20,200) 8x8, 2x2/4x4 | 31744/31744 | 16/4 | 4096/2048 | 8.5 MB | 160/15/100 |
| (20,200) 16x16, 4x4/8x8 | 126976/126976 | 16/4 | 14848/6656 | 100.3 MB | 160/16/78 |
| (64,96) 32x16 Block, 4x4/8x8 | 253952/170624 | 32/8 | 20352/11008 | 139.2 MiB | 161/17/76 |

延迟、展开与扫描一律引用 `validation/results/exp20a.json` 每个窗口对象的
`latency_average_us`、`latency_p95_us`、`settled_average`、`settled_p95`、`relaxed_average`、`mode_seconds`
与各级 `customize_seconds`（本文件不重复手抄这些数值，`exp20a_verify.py` 已将它们与逐行 CSV 对齐）。
数量级：三窗口 plain 平均延迟 0.15/0.74/2.64 ms、1 级与 2 级同量级；
两级在 8x8 略快于 plain，在 16x16/Block 上慢于 plain：矩阵弧展开量大（Block 扫描均值
约为 plain 的 8 倍），本实现没有双向搜索与 stalling，故结论是本实现下尚未加速，
而不是两级结构无效。
内存：`matrix_bytes` 是两级矩阵元素 payload 合计（各窗口 L1+L2 元素数 × 4 B，例如 8x8 为
(1081344+1048576)×4 = 8519680 B，不含 vector/allocator 开销），`matrix_and_interface_bytes`
再加上真实索引数组；`peak_rss_kib_before_customize` 是**建表前**峰值，
`peak_rss_kib_process` 是建表与查询后进程结束前的 getrusage 峰值（三个窗口都用带该字段的最终
二进制串行重测），三者及 `projected_total_bytes`、`budget_bytes` 均以 JSON 为准。
20C起 `CustomizableCh` 增加 `order_`（rank→node）并计入 index capacity；20A/20B 的
`structure_bytes` 是其当时修订的口径（无该字段），按审查要求不重测。
`validation/results/exp20a-*.time.txt` 是**早前 pre-ostringstream 版本**旁证（mtime
04:01 早于最终 JSON 04:12），不作为最终 RSS 证据，仅注明版本保留。
L1/L2 矩阵有限密度见 JSON 的 `matrix_finite/matrix_entries`（L2 在 Block 窗口为 98.1%，
不是全有限）。

## 失败记录（有确切输出）
- 首版矩阵行按采样12×64检查不完整：改为 stride==exit 数全量检查后 row_problems=0。
- `plainDijkstra` 改为返回 -1 表示不可达后，旧的 `>= kNf` 判断把不可达统计成0：Block窗口
  曾报 unreachable=0；改为 `reference < 0` 后为 17。
- 一版JSON用固定 snprintf + tail[1024]，新增字段后参数错位且可能截断：改为
  std::ostringstream（setprecision(9)），并由 exp20a_verify.py 逐字段与CSV核对。
- Block窗口请求池最初包含 hole 上的 dummy port 零对：改为 `tileOf + arch.exists` 过滤后，
  valid_states 170624 < allocated 253952，请求来自真实SRB。
- 修 JSON 序列化那次 build 失败（格式参数错位）后，三个窗口仍用旧二进制跑了
  8x8/16x16/Block，其 JSON/CSV（无 `us_*` 列、Block 池含 dummy 槽）已全部丢弃，
  修复后串行重测；现库内证据均来自含有效tile采样与延迟列的二进制。
- 首版快照把 `peak_rss_kib_before_customize` 误写成“建表后 peak”：该字段实为建表前测量，
  整进程峰值改用 time 文件；本轮已加 `peak_rss_kib_process`/`rss_kib_now`，并**后来用带该字段的
  最终二进制把三个窗口全部串行重测**（8x8 process=47108 ≥ before=47108 KiB、now=43380 KiB，
  16x16/Block 分别为 139124/201516 KiB，均见 JSON 各窗口对象）。

## 边界与下一步
- 仅窗口内exact；分区是规则方格，未用PUNCH/METIS，未做双向搜索、stalling、phantom level；
  三级以上层级、跨窗口衔接、路径解包（path unpacking）均未验证。
- 可复跑：`g++ -std=c++17 -O2 -o build/crp_probe tests/crp_probe.cpp src/architecture.cpp` 后
  依次 `--windows 8x8|16x16|block`（各自写 JSON 与逐行CSV），最后 `python3 validation/exp20a_verify.py`。
- 结构计数供后续CCH/骨架：各级 entry/exit、矩阵元素与有限密度、跨cell边（Net）条数
  一律见 JSON（`level1`/`level2` 子对象、`net_edges`）；Block 的 L2 有限密度为 98.1%，
  存在少量不可达条目。
