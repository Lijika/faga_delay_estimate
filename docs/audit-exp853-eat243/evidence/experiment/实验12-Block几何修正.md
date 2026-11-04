# 实验12 Block 几何修正（Material Passport）

日期 2026-09-17，基线提交 6a071eb。目标：只验证能否用架构真实 Block/Line 几何减少
residue 的系统性低估。结论：**不采纳**。公开 1M 上确实有 +0.37 accuracy 的收益，但同一项
在架构自造的 skip 见证集合上把该组 proxyAcc 从 64.6 打到 11.1，端点几何无法区分两种机制，
因此不提交任何生产 src 改动；保留独立 probe 与否决记录。生产 `estimate`、ResidueEstimator、
main 与 root 二进制均未改动（src 工作树与 6a071eb 逐字节一致）。

## 1. 材料清单（passport）

| 材料 | 身份 |
|---|---|
| 架构 | doc/eda比赛文件/arch（5 个 JSON，未改动） |
| 探针源码 | tests/block_geometry_probe.cpp `766603bf730500445c62c5b03f151cfcc73fa4474a53c89fd4269b1bc190230b` |
| 探针二进制 | build/block_geometry_probe `70fe79192520157ee96eb34c13d113d80e4014a8045f8493a07e1e873117d639` |
| 临时候选二进制（仅测量，src 已回滚） | build/estimate-exp12 `a97e77ab8e0522fdaa244407cab5ad25d47cf4ebd587ae862d5346106f412c77` |
| root 提交二进制（未重建） | estimate `45b592f2edb87165f42fa9c1d13a4de13221ad5107f00e67ba256aeb6ab9b9ee` |
| 大结果 CSV（不入库，在 /tmp/exp12） | baseline `3044018c…`、cross_net `00162732…`、cross_full `6f79c1db…`、noncross `8402280c…`、combo `43a0e703…`（完整 sha 见 metrics JSON） |

编译（探针）：

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/block_geometry_probe \
    tests/block_geometry_probe.cpp src/architecture.cpp src/router.cpp src/residue_estimator.cpp
```

标签来源：探针用 exact Router（span+8 ALT，实验7/10 已验证与 plain Dijkstra 逐行一致）生成
exact 标签，每次运行前 `--verify-labels 8..12` 再用 plain Dijkstra 复核，本轮 4 次运行均
0 mismatch。**golden 从不作为输入特征**：1M 对照是对 `estimate` 结果 CSV 做离线 replay，
只读 From/To 与预测 delay 列，From/To 逐行保留（cmp 首两列完全一致）。

## 2. 特征语义（可达性与方向性）

架构的真实几何：6 条水平可穿越带 x∈[76,89]，y 分别为 [0,49]、[100,149]、[200,249]、
[300,349]、[400,449]、[500,549]，crossable[Horizontal]=true、crossDelay=292，
crossable[Vertical]=false；另有实心块 x∈[0,15]、y∈[0,99]（两轴都不可穿越，区域内无 SRB）。

| 特征 | 定义（只用端点与架构） | 语义与边界 |
|---|---|---|
| `crossable_h` | 两端行都落在同一条带的行范围内，且 x 区间严格跨过该带左右边界 | 只有该跳真的走进带内单元才付 292；带外绕行的 gap 行不付。行（reachability）上**不是**必经：路径可以绕，因此这是经验估计而非下界，不得标 exact/lower bound |
| `noncross_v` | 两端列都在带的列范围内，且 y 区间严格跨过该带行范围 | 垂直不可穿越，路径必须离开带列再回来；费用 = 强制绕行列数 × 模型自身最便宜每列代价 |
| `endpoint_block` | 真实首 Net（源）与末 Net（目标）的 resolver block charge（delay 减 Line） | 这是**端点** charge，与全路径跨带 charge 是两回事，单独消融 |
| `cross_full` | 每条 `crossable_h` 带 +292 | 把 published 跨带费用全额加上 |
| `cross_net` | 每条 `crossable_h` 带 +max(0, 292 − 带宽度 14 × 每列 13ps) = +110 | 每列 13ps = round(min\|slope\|/scale) = round(750/60)，来自 estimator 自身斜率，非 golden 拟合 |

只有水平方向有候选：这 6 条带垂直不可穿越，所以不存在对称的垂直 crossable 项；
实心块方向（kNonCrossableVerticalBlock）在本轮 67 行样本里只出现 2 行，没有稳定信号。

## 3. 群体占比（全量 1M 请求扫描，无需标签）

`crossable_h` 18,303 行 = 1.830%；`noncross_v` 2,729 行 = 0.273%；合计 2.10%，
与实验2 §6.8 的 2.1% 一致。

## 4. 消融

### 4.1 独立 probe（510 行：334 步长样本 + 150 定向 crossable_h + 26 定向 noncross_v，exact Router 标签）

| 变体 | crossable_h 组（161 行）proxyAcc | MAPE | meanDelta | 全样本 proxyAcc |
|---|---:|---:|---:|---:|
| off | 69.56 | 8.21% | −143.5 | 83.29 |
| endpoint_block | 68.19 | 8.56% | −94.6 | 该组内更差（组外不变） |
| cross_full（+292） | 65.39 | 9.33% | +148.5 | 该组内更差，156/161 变高估 |
| **cross_net（+110）** | **89.53** | **2.77%** | −33.5 | 89.59 |
| noncross | 不适用 | — | — | 83.73（noncross_v 组 69.82→78.53，但 meanDelta +73.9，12 高/14 低） |

### 4.2 公开 1M 官方指标（离线 replay，与 C++ 实现输出逐字节一致）

| 变体 | accuracy | MAPE | P95 | P99 | ≤5% | 高估 | 低估 | 输出 SHA |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| off（默认） | 91.6214 | 2.2175% | 8.3841% | 18.348% | 89.1138% | 0 | 948,869 | `3044018c…` |
| cross_full | 91.5645 | 2.2322% | 8.6473% | 18.246% | 89.0035% | 17,681 | 931,196 | `6f79c1db…` |
| noncross | 91.6451 | 2.2109% | 8.3373% | 18.315% | 89.1786% | 1,808 | 947,066 | `8402280c…` |
| **cross_net** | **91.9870** | **2.1180%** | **7.8423%** | **17.908%** | **90.3083%** | 5,501 | 943,173 | `00162732…` |
| combo | 92.0107 | 2.1114% | 7.7922% | 17.864% | 90.3731% | 7,309 | 941,370 | `43a0e703…` |

`cross_full` 用全额 292 全局相加会变差（−0.057，高估 17,681 行），证明不能按几何相交直接加 292；
`noncross` 只有 +0.024（噪声级）；`cross_net` +0.366 与 probe 组内测量（1.83% × 20 点 ≈ 0.37）一致。

### 4.3 两个独立留出集（exact Router 标签，未参与调参）

| 留出集 | crossable_h 行数 | off proxyAcc / MAPE | cross_net proxyAcc / MAPE | 判定 |
|---|---:|---|---|---|
| endpoint holdout 32 条 | 10（31.3%） | 43.88 / 16.24% | **83.42 / 4.27%** | 改善 |
| 实验5 样本 67 条（含 exp4 skip 见证） | 13（19.4%） | 64.57 / 9.81% | **11.14 / 42.44%** | **严重回退** |

第二组里既有单跳 skip 见证（真实位移 15 > 名义 1，residue 本来就高估，例如
`SRB_75_0/ZSEA[0] -> SRB_90_0/ISEA[0]` exact 292、residue 327），也有真正付 292 的跨带路径；
端点无法区分，`+110` 把前者推到 +135 的 meanDelta。这就是否决的直接原因。

## 5. 临时开关实验与回滚

为满足"off 与候选对照 + 5 次一致性 + 10M 重复 timing"，本轮临时给 ResidueEstimator 加了
`BlockGeometry::CrossNet`、给 main 加 `-block-geometry off|cross-net`（默认 off），
用 `build/estimate-exp12` 测得：

| 运行 | exit | user | sys | wall | RSS | 输出 SHA |
|---|---:|---:|---:|---:|---:|---|
| 1M 默认（重建二进制） | 0 | — | — | — | — | `3044018c…`（与冻结 baseline 相同） |
| 1M cross-net ×5 | 0 | 11.89–12.45s | 0.28–0.81s | 12.22–13.27s | 417,748–417,892 KiB | 5 次全部 `0016273293f0dfe4…` |
| 10M 默认（复用 /tmp/endpoint8/requests-10m.csv） | 0 | 17.84s | 2.68s | 20.78s | 417,860 KiB | `c2f3d8c8d20377e8…` |
| 10M cross-net | 0 | 17.59s | 2.70s | 20.52s | 417,680 KiB | `28f6c20884897183…` |

10M 由查询缓存主导（1M 重复 10 次，9M 命中），候选没有可测的 CPU/内存代价。
**由于 4.3 的第二个留出集回滚，这三处 src 改动已全部 revert**（`git checkout --` 恢复），
当前 `git status` 不含任何 src 修改，root `estimate` 也从未重建。

## 6. 证据等级

| 主张 | 等级 | 依据 |
|---|---|---|
| crossable_h 组在公开分布上系统性低估 | A | 510 行 exact 标签，meanDelta −143.5，161/161 全低估 |
| +110/带在公开 1M 上 +0.37 accuracy | A | 离线 replay + 官方公式，5 次一致 SHA |
| 全额 +292 会变差 | A | 1M 91.5645 < 91.6214，高估 17,681 行 |
| 该修正在其它分布上不稳定 | A | 第二个留出集 crossable_h 组 64.6 → 11.1 |
| 端点几何能区分两种机制 | **否**（C） | 端点看不到中间跳的落点，无法判定是否真的跨带 |
| 生产收益 | C | 未采纳，默认路径与二进制不变 |

## 7. 未验证边界与结论

1. 该终止项不是下界：绕行 gap 行可以不付 292，所以 `cross_net` 只是经验模型；日志与代码
   都没有把它标成 exact/lower bound。
2. 只看水平可穿越带；垂直不可穿越与实心块方向样本太少（2 行），没有可判定的信号。
3. `endpoint_block`（真实首/末 Net 的 charge）单独消融后更差，已删除该分支。
4. 公开 1M 是开发集；两个留出集规模只有 32/67 行，第二组的回退已足以否决，但样本量本身
   不足以给出"在什么分布上会好"的完整刻画。
5. 本轮不产生生产收益结论、不接入 PDB/CRP/TNR/CCH/ML，也不改 endpoint 逻辑。
