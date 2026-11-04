# 实验20B：标准CCH局部原型

## 目标
按 `doc/paper/12-Customizable-Contraction-Hierarchies.md` §4/5/7.1/7.5/8.1 实现标准CCH：无向无权
拓扑用真实嵌套剖分顺序消元成clique（不做metric witness pruning）、弧上原方向权重初始化（缺方向
INF）、lower-triangle双向customization、source向上与target反向向下的两条Dijkstra取共同hub最小和。
只做窗口内原型：不读golden、不算分、不改生产。测试代码只在 `tests/`，未进 `src/`。

## 方法
- **顺序**：`tests/cch_probe.cpp --dump-graph` 把每个图的**无向无权骨架**导成CSR到 `/tmp/exp20b`
  （含FNV-1a 64骨架指纹）；`validation/exp20b_order.py` 调真实
  `pymetis.nested_dissection(adjacency, Options(seed=20260919))`（pymetis 2025.2.2 驱动 METIS
  NodeND），把顺序写进 `validation/results/exp20b-order-*.txt`，header带版本/seed/ordering秒/骨架
  指纹/perm的sha256/identity计数。探针拒绝缺失、节点数不符、指纹不符或非双射的order文件；顺序不是
  身份（4x4 identity 1/7936、8x8 1/31744），也没有用初始度或几何sort冒充ND。
- **拓扑**（`tests/cch.h`）：顶点按order重排使 id==rank，弧只从低rank指向高rank；按rank升序消元，
  每个被消元顶点的up邻域补成clique，**全部fill边保留为弧**（无witness pruning）。
- **customization**：每条弧两个权重 `up`(低→高)/`down`(高→低)；原图有向边按方向装载、缺方向INF；
  按lower endpoint升序枚lower triangle：`up(x,y)=min(up, down(z,x)+up(z,y))`、
  `down(x,y)=min(down, down(z,y)+up(z,x))`。换权只重跑customization，拓扑不重建。
- **query**：源在up权上向上Dijkstra，目标在down权的反向图上Dijkstra（两条搜索都遍历同一批up弧）；
  每个方向各自在**自己队首≥当前最优和**时停（不用两队首之和），答案是共同hub的最小和；未做stalling。
- **计时/内存**：ordering在Python侧计时，topology/customization/query在C++侧独立计时；内存分开报
  element口径与capacity口径（vector容量+头部，**不含allocator元数据**），并给getrusage进程峰值。
- **采样**：请求与20A同源——4x4用固定seed 20260919生成160条真实SRB port请求，8x8直接重放
  `validation/results/exp20a-queries-8x8.csv` 的160条（源/目标/参考距离逐行相同，见验证器）。

## 结果（数字以 `validation/results/exp20b.json` 与逐行CSV为准，`exp20b_verify.py` 115项核对）

| 窗口 | 节点 | 无向边 | fill | 弧 | fill比 | max up/down | topology | customize(init+tri) | 三角形 | 请求/一致/不可达 | 峰值RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4x4 (20,200) | 7936 | 132096 | 651498 | 783594 | 4.932 | 383/1045 | 1.98s | 1.45s (0.008+1.44) | 6.38e7 | 160/160/19 | 58792 KiB |
| 8x8 (20,200) | 31744 | 530432 | 7136945 | 7667377 | 13.455 | 1778/4317 | 269.5s | 122.8s (0.092+122.7) | 3.00e9 | 160/160/15 | 400572 KiB |

- 每条查询的延迟、settled/scanned（含p95、up/down分向）、弧方向分布、结构字节与预算字段一律引用
  JSON：4x4 延迟均值 29.5/145.3 µs、扫描均值 1445.9/12667.4；8x8 延迟均值 185.1/3528.5 µs、
  p95 980.9/21975.2、扫描均值 7949.5/211484.9（左plain右CCH）。
- **人工图**（8x4，非对称权重/零权/单向/无出边/无入边）：62无向边→140弧(78 fill)，两组metric各
  1024对**全部**与独立plain一致（mismatches 0/0，不可达各61对），第二组只换权且翻转部分方向后
  `topology_stable_across_customization=true`（拓扑hash不变）。
- **为什么CCH没变快（实测原因）**：ND消元后fill比4.9→13.5，平均up度 783594/7936≈99 与
  7667377/31744≈241；8x8弧里 up_only 1.63M/down_only 1.90M/both 1.03M/neither 3.11M，**40%的弧
  两个方向都没有真实边**（纯拓扑fill，仍被扫描）。本实现没有perfect witness search裁剪这些弧、没有
  stalling、也没有把两条搜索压到更小search space，所以settled虽少（8x8 791→261），scanned反而
  26倍于plain（7949→211485），单查询慢约19倍。这是本实现下的结论，不代表ND-CCH结构无效。
- **2e9 B预算**：8x8 `projected_total_bytes`=292030988 B、峰值RSS 400572 KiB，都在预算内；4x4的
  `structure_bytes`（capacity口径）30507728 B。8x8的 `structure_bytes` 是**size口径**（旧修订，
  容量未采集，不推算），JSON里用 `structure_bytes_scope` 标注，两种口径都不含allocator元数据。
- **abort路径实测**（只写/tmp，不进结果）：`--budget 60000000` →
  `ABORTED before fill growth at vertex 5632 after 5632 vertices (resident 57044992 + worst case
  3246144 > budget 60000000)`，`passed=false`、0请求，不把部分CCH算通过；`--budget 90000000`
  正常完成。预算检查在实际RSS与"下一步fill增长最坏值"上判定。
- **16x16不做**：4x4→8x8顶点×4时fill×10.95（651498→7136945），拓扑1.98s→269.5s（×136）。按此
  增长16x16的弧量在1e8量级、拓扑要数十分钟且索引结构会逼近/超过2GB预算；扩大窗口留给接口图/更稀疏
  骨架的任务，本轮不临时扩窗口、不做重复的final计时。

## 失败记录
- 首版 query 用原node id直接索引rank数组、backward 走 `downArcs`(hi→lo) 从t向下、`readRss_` 的
  KiB与bytes直接相加：三处均在首轮真实计时前由审查发现；修为 rank 转换、backward 在 `upArcs` 上以
  `down` 权放松 `arc.hi`、RSS×1024。人工图与4x4通过后才跑8x8（避免带已知错误做长计时）。
- FNV-1a offset basis 少写一位（1469598103934665603 vs 14695981039346656037），导致order与CSR
  指纹对不上；order文件 `# key value` 的key被解析成空串。两处都修在首次运行暴露。
- 负控制脚本自己先把真实4x4 CSV/order/merged JSON改坏（先mutate后设RESULTS目录）：重跑4x4（4秒）与
  确定性order生成（perm sha256不变）后恢复；现负控制先设目录，clean/tamper/restore三态均验证过
  （篡改距离/顺序/统计分别被对应检查抓到并exit 1）。
- 一次4x4峰值读数96808 KiB，重复5次为58656~58792 KiB，判为环境异常读数；发布的是重复一致的run。
- 首版`projected_total_bytes`超预算判定写在序列化`passed`之后（会把超预算窗口标成passed）：已把预算
  判定（projection与真实RSS两个flag）移到写`passed`之前；8x8那批是旧修订，JSON里没有这两个flag，
  验证器对旧修订只核对它确实在预算内。

## 未验证边界
- 未做perfect customization/perfect witness search、stalling、path unpacking、并行customization、
  phantom level、多metric SIMD；只窗口内exact。
- 骨架是窗口port图（含Net长边），未做接口图/跨窗口骨架；未测16x16及以上规模；未读golden、未计分。
- 8x8的capacity口径内存未采集（按审查要求不重跑大窗口、不推算未测值）。

## 复跑
```
g++ -std=c++17 -O2 -o build/cch_probe tests/cch_probe.cpp src/architecture.cpp && \
build/venv-ml/bin/python validation/exp20b_order.py && \
./build/cch_probe --windows none --json validation/results/exp20b-run-artificial.json && \
./build/cch_probe --windows 4x4 --skip-artificial --json validation/results/exp20b-run-4x4.json --csv-dir validation/results && \
./build/cch_probe --windows 8x8 --skip-artificial --requests 8x8=validation/results/exp20a-queries-8x8.csv \
                 --json validation/results/exp20b-run-8x8.json --csv-dir validation/results && \
python3 validation/exp20b_finalize.py && python3 validation/exp20b_verify.py
```
8x8约7分钟；重跑会覆盖发布产物（`exp20b-run-8x8.json` 目前是旧修订run，重跑后内存字段会变成容量口径）。
`exp20b_finalize.py` 只做两件机械事：`metis_version`→`pymetis_version`（值不变，pymetis.version是包
版本不是METIS库版本）与补 `structure_bytes_scope`；窗口对象其余部分与raw run逐字段相同，验证器用
独立的normalize函数核对。
