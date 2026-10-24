# 实验146：C1 Router 安全 residue 启发式组件探针

## 目标与假设

把实验145通过审计的

```text
h_safe(s,t) = min_c [
  R_nominal(s,t; dx - 14c,dy)
  + Line(actual endpoints)
  + 292 * |c|
]
```

作为 `Router::BoundProvider` 的 test-only 外部下界，检查当前 A* 搜索在真实有向图上的
答案一致性和扩张成本。`R_nominal` 必须同时平移 residue 槽位和象限位移项，`Line` 使用
原始端点，候选向下取整；无有限 residue 值或 fallback 时 provider 返回 unknown，由内置
span 下界继续工作。

本轮只验证 Router 组件，不修改生产搜索逻辑、`./estimate`、正式包或默认选项。当前
`Router::search` 允许更低 `g` 重新入队，并在 frontier 最小 `f >= best` 时终止；该实现
语义将作为不一致启发式的安全终止基线，探针不把启发式一致性假设写入生产代码。

## 固定数据与比较

- 架构：`doc/eda比赛文件/arch`，运行前记录五个 JSON 的 SHA-256。
- 跳格见证：`validation/results/real-bound-witnesses.csv` 的全部 28 行。
- 开发抽样：`validation/results/exp127-development-rows.csv` 按原文件顺序等距选择 64 行，
  固定索引 `floor(k*(N-1)/63)`，重复键只保留第一次；脚本写出组合输入并记录其 SHA。
- 每行保存原始 `exact` 标签，仅作独立标签一致性报告；答案门以 plain Dijkstra 为准。

三种 Router 配置均 `queryCacheEntries=0`、`enableQueryCache=false`、`landmarkCount=0`、
`useRadixHeap=false`：

1. `plain`：`useSpanHeuristic=false`，无外部 provider，只运行组合样本中固定索引
   `floor(k*(N-1)/7)` 的8行，`k=0..7`；
2. `span`：内置 span heuristic，无外部 provider，运行全部样本；
3. `safe`：内置 span heuristic 加 `h_safe` provider，运行全部样本。

所有样本上 span 与 safe 都对照保存的 exact 标签并互相比答案；plain 在8行上对照 span。
每行记录答案、`expandedStates`、`relaxedEdges`，并分别累计进程 CPU 与 wall 时间。
provider 对同一目标的 Router 状态启发值做 test-only 缓存，记录查询、缓存命中、已知下界、
unknown 与不完整搜索数。首次完整预定样本运行在出现目标状态启发值未显式归零的代码风险
后中止，没有产生逐行结果；中止前 plain 阶段进程CPU为157.78秒、峰值RSS为599,644 KiB。
该中止数据只用于固定上述成本控制，不作为答案或性能证据。调整后的协议在重跑前提交。

## 检查与门槛

1. 全部样本上 `span == safe`，包括不可达答案和同针脚/同单元边界分支；plain 抽样8行
   满足 `plain == span`。
2. 全部样本上 `span`、`safe` 与保存的 exact 标签一致；标签不参与 safe 的选择或终止。
3. safe provider 的候选搜索完整：任一已知返回都来自有限 `|c|` 搜索，尾部由
   `Line + 292(|c|+1) > current_best` 停止；fallback/unknown 不冒充下界。
4. 资源报告包含三种配置的 CPU、wall、峰值 RSS、线程数，以及扩张/松弛总数。该结果只
   作为 Router 组件证据，不能替代完整 1M 验收或隐藏集成绩。

若答案出现 mismatch，立即停止 C1 接入，保留逐行记录，优先检查 provider 的 I* 折回、
logic-output 终端 Arc、跳格符号和 `min_f >= best` 终止条件。若答案一致，再依据扩张和
CPU 方向决定是否做更大样本探针；本轮不直接修改生产默认路径。

## 命令

```sh
python3 validation/exp146_router_safe_residue.py
```

原始报告写入 `validation/results/exp146-router-safe-residue.json`，逐行证据写入
`validation/results/exp146-router-safe-residue.csv`，临时文件写入 `build/exp146/`。

## 预注册判决

- `plain == safe` 且 provider 没有越界终止证据：进入下一轮更大 Router 样本和端到端 CPU
  筛选，生产源码仍保持默认关闭。
- 任一答案不一致、标签不一致或 provider 产生不安全 fallback：关闭当前实现，回到商图
  `L` 或重新推导跳格状态。
- 只有在独立完整 1M 输出、资源契约和精度收益证据通过后，才允许评估正式接入。
