# 实验14 PDB 下界地板消融

日期 2026-09-17，基线提交 adaa1a0。目标：验证实验9 的 PatternDatabase 可采纳下界作为
ResidueEstimator 输出的可选 floor（`-pdb-floor`，默认 off）能否改善比赛分数。

**结论：不启用。** 地板在公开 1M 与 10M 上都逐字节无变化（`applied=0`），但带来
+16s CPU/1M 与 +200MB RSS；两个独立 exact 留出集（32+67 行）同样 0 行变化。默认保持
实验13 的 `source`，`-endpoint-mode off` 兼容不变；`-pdb-floor` 作为可复现实验开关保留。

## 1. 机制与实现（最小改动）

数学性质：PDB 界 `L` 经实验9 审计可采纳（`L <= 精确距离 d`），所以
`max(估计值, L)` 与真实距离的绝对误差不可能大于原估计值：
`L <= 估计值` 时不变；`估计值 < L` 时新值 = L ≤ d，绝对误差从 `d−估计值` 降到 `d−L`。
因此该地板是逐行弱提升，理论上不会让 accuracy 变差（对 `g=0` 行，若 `L>0` 会丢掉
那一行的零约定分，本轮 1M 的 1 个零 golden 行未受影响）。

实现（只改 3 个文件，无新抽象）：

- `src/residue_estimator.h`：`Options::pdbFloor`（默认 false）、`Stats` 四个计数器、
  `PatternDatabase pdb_` 成员与 `applyPdbFloor(...)` 声明。
- `src/residue_estimator.cpp`：init 时按需 `pdb_.init(arch)`（0.28s）；`estimate` 得到
  base 或 endpoint 结果后调用 `applyPdbFloor`；目标表按需 `prepareTarget` 并缓存状态
  （0 未知 / 1 unsupported / 2 ready）；`lowerBound` 返回 false（抽象状态无穷、或 48 个
  入度为 0 的端口）时**原值回退**，绝不把 INF 当 0；异常一律回退并计数。
- `src/main.cpp`：`-pdb-floor` 开关（默认 off）、usage、启动与结束计数器打印。

## 2. 公开 1M（四配置，官方公式评分）

| 配置 | accuracy | MAPE | P95 | P99 | ≤5% | 高估/低估 | CPU | RSS | 输出 SHA |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| off | 91.6214 | 2.2175% | 8.3841% | 18.348% | 89.1138% | 0 / 948,869 | 11.86s | 417,912 KiB | `3044018c…` |
| source（默认） | 93.2407 | 1.7457% | 6.1162% | 12.836% | 92.8961% | 0 / 943,259 | 14.56s | 417,932 KiB | `a9271af4…` |
| pdb-floor（endpoint off + floor） | 91.6214 | 2.2175% | 8.3841% | 18.348% | 89.1138% | 0 / 948,869 | 27.85s | 621,360 KiB | `3044018c…`（与 off 逐字节相同） |
| source+pdb-floor（默认 + floor） | 93.2407 | 1.7457% | 6.1162% | 12.836% | 92.8961% | 0 / 943,259 | 31.51s | 621,428 KiB | `a9271af4…`（与 source 逐字节相同） |

地板计数（1M）：`applied=0`、`unsupported=0`、`targets=256`、`prepare=15.34s`。
即 1,000,000 次查询里没有任何一次被抬高，但为 256 个目标建表花了 15.3s 与约 200MB。

## 3. 10M 重复与一致性

| 运行 | 输出 SHA | CPU | RSS |
|---|---|---:|---:|
| 10M source（实验13） | `35429810d21baf5f…` | 20.64s | 417,796 KiB |
| 10M source+pdb-floor | `35429810d21baf5f…`（**逐字节相同**，`cmp` 通过） | 37.29s | 621,428 KiB |
| 1M source+pdb-floor 复跑 ×2 | 均 `a9271af4c26bc7de…` | — | — |

10M 上地板同样 0 次生效（`applied` 计数为 0，缓存命中 9M 不触发新查询）。

## 4. 独立 holdout（32 + 67 行，exact Router 标签）

逐行比较 floor 与无 floor：holdout32 **0 行变高、0 行变低**；holdout67 同样 **0/0**。
诊断（用 `validation/results/pdb-samples.csv` 的 L_pdb 列与 1M/holdout 估计值）：

- holdout32 全部 32 行 `L_pdb == 估计值`；
- holdout67 的 66 个可比行里 `L_pdb <= 估计值` 恒成立，最大差值是 exp4 skip 见证那几行
  （`L=292`，估计 336–339，精确 292）。

原因：PDB（实验9）与 residue（实验8）都建立在同一组方向势函数与斜率上，residue 估计值
在真实架构上普遍高于这个已审计下界，因此地板被估计值支配，无法提供增益。

## 5. 回归与兼容

| 检查 | 结果 |
|---|---|
| 默认（source）1M 输出 | `a9271af4…` 不变（改动前后一致） |
| `-endpoint-mode off` 1M 输出 | `3044018c…` 不变 |
| `verify_internal --quick`（改动后重建） | 八条路径全过，ALL CHECKS PASSED |
| `endpoint_integration`（改动后重建） | 144 checks，0 failures |
| 根 `./estimate` | 未重建，仍 `45b592f2…` |

## 6. 未验证边界

## 7. 制品与证据身份

| 制品 | sha256 |
|---|---|
| build/estimate-exp14 | `461bf9afe955b451971914b77ad845cb158eeda73337dfb3e0d7d460d6259498` |
| src/residue_estimator.h | `ba8fef5ad422826497fd6b65d688c58addf497b95f7fce0b503b1f995759a981` |
| src/residue_estimator.cpp | `b30b3aed0ae1fd2ddbab5d7b050f87f73c09adb6d6fb06bbdd397fa140a081c3` |
| src/main.cpp | `250dd52dca62a6fd1a5d0eb417264486529013e0c7256efb04c57f521aaa8174` |
| validation/results/exp14-metrics-1m.json | `80781e62fb4ecc26ef770cd79115cbb4a655d32e1399a86dba6cff44c79e4755` |
| validation/results/exp14-consistency-and-hashes.txt | `3ad583c4f238a36004f097b5e2dd3af7bac486a6d438c66175362c0a2f8a9a6a` |
| validation/results/exp14-endpoint-integration.txt | `540d3c09806c0a1874271026e73d318339e91f910888e052134ed0b35abc3453` |

大体积 1M/10M 结果 CSV 位于 /tmp/exp14（每份约 39–400MB），仓库内只保留上表小文件；
`validation/results/exp13-metrics-1m.json` 等历史证据未被修改（本实验的指标写入
`exp14-metrics-1m.json`）。

1. 未在其它架构或其它请求分布上验证「residue 估计值 ≥ PDB 界」这一支配关系；本轮只在
   公开 1M、10M 重复、32+67 行 holdout 上实测（1M/10M 是逐字节证明的 0 次生效）。
2. 未测 1B 规模；若启用，448 个可用目标全建表约 450MiB，加上 residue 表与缓存仍在 2GB 内，
   但本轮实测的 256 目标已占 621MB RSS。
3. 零 golden 行的零约定在本轮未受地板影响，但理论上若某零延迟对有 `L>0`，地板会损失该行分数。
4. 未把地板与 bias/其它候选组合测试；本轮只做 off / source / floor / source+floor 四配置。
