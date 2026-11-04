# 实验146：C1 Router 安全 residue 启发式组件探针结果

2026-10-10，Asia/Shanghai。协议先于重跑提交，见
`实验146-C1 Router安全residue启发式组件探针.md`。本轮仅 test-only `Router::BoundProvider`
接入；生产 Router、默认选项、根入口和正式交付包均未修改。

## 结果

组合样本92行：28条真实路径见证，加开发集按固定等距索引抽取的64行。span 与 safe 均
逐行匹配保存的 exact，且两者答案逐行一致；8条预先固定的 plain Dijkstra 对照也全部匹配
span。同状态目标 `h=0` 断言通过，known bound 搜索无不完整项，单线程。

| 配置 | 查询数 | CPU (s) | wall (s) | expanded states | relaxed edges |
| --- | ---: | ---: | ---: | ---: | ---: |
| plain Dijkstra | 8 | 14.149 | 13.714 | 17,985,590 | 308,727,025 |
| span A* | 92 | 111.971 | 108.553 | 130,490,437 | 2,239,628,123 |
| safe residue A* | 92 | 41.578 | 40.307 | 11,463,114 | 196,630,375 |

safe 搜索扩张数比 span 少约91.2%。这一轮单次 query-only CPU 少70.393秒；该值是筛选
观察，不是统计显著的性能结论。全进程含 residue 初始化 CPU `180.09 s`、wall `182.83 s`，
峰值 RSS `971,568 KiB`，线程数1。

provider 收到43,454,629次调用，其中29,656,358次来自缓存，计算13,798,271个状态界；
其中525个状态计算选择了非零 `c`，无 unknown 或搜索截断。按目标复用的 `unordered_map`
峰值达到9,632,000个状态项，显著增加临时内存。这是下一轮的工程优化点，改用紧凑的状态
索引数组缓存后重新计量。

## 判定与边界

- 组件正确性门通过，当前 A* 的状态重开与 `min_f >= best` 终止在样本上返回 exact。
- 该结果没有检验所有状态边上的启发式一致性，也没有建立超出实验145前提的数学证明。
- 本轮没有完整1M预测、精度变化或正式交付验收。正式路径继续使用exp131。
- CPU只测一轮且执行顺序固定，环境噪声和顺序效应尚未量化；不能据此宣称普遍CPU收益。

## 证据

- `validation/results/exp146-router-safe-residue.json`
- `validation/results/exp146-router-safe-residue.csv`
- `tests/exp146_router_safe_residue.cpp`
- `validation/exp146_router_safe_residue.py`
- 正式二进制 SHA：`aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c`
