# 实验32 短距/Block 条件残差候选

日期 2026-09-21，起点提交 `1c4e23d`，候选代码提交 `7f6e18a`。目标：检查「在已有距离/Block/端点标签上做条件残差修正，或等价的短距分层，能否减少短距与 Block 行的误修，同时保留长距收益」。范围限定为一个事先声明的候选族，不新增依赖、不做全图索引、不改训练标签、golden 只在最终评分读取。**结论：假设不成立，候选不采纳，保持默认 off；正式交付仍为实验29。**

## 1. 候选族（评估前固定）

冻结模型不变（实验19A 的 64 树，`validation/results/exp19a-model.json`，sha256 `18279168…`），候选只是在模型输出之后按已有标签改写短距行的修正量：

| 变体 | 条件（只用 dist 与 tags） | 动作 |
|---|---|---|
| plain | — | 全量应用模型（基线） |
| revert24 | dist ≤ 24 | 保留 fast |
| revert24_noblock | dist ≤ 24 且无 Block 标签（bit 2/3/5） | 保留 fast |
| revert100_noblock | dist ≤ 100 且无 Block 标签 | 保留 fast |
| long_existing | dist ≤ 100 | 保留 fast（已部署的 `-residual long`） |
| shrink50_100 | dist ≤ 100 | fast + raw/2 |
| shrink50_24 | dist ≤ 24 | fast + raw/2 |
| shrink50_bigcorr | dist ≤ 100 且 abs(raw) > 0.10·max(fast,1) | fast + raw/2 |

标签集与实验19A完全相同：`validation/results/exp18b-labels.csv`，10,024 行，sha256 `1cb99392…`；无 golden。外层留出复用实验19A 的六个 fold（endpoint_hash_20、pair_hash_20、spatial 双向、distance ≤300→>300、distance >24→1..24），每个 fold 内部再按 `inner` 前缀做 80/20：内层选网格、选变体，外层只评一次；训练/测试完整端点交集为 0（六折均为 0，pair 交集只在空间折上非零，与19A一致）。99 条 stress 从未参与拟合（冻结模型在 10,012 行上拟合，已剔除 12 条与 stress 同端口对的行）。

## 2. 标签层结果：假设不成立

六折外层带宽加权 accuracy 相对 plain 的差（百分点）与胜出折数：

| 变体 | 平均 Δ | 胜出折 |
|---|---:|---:|
| plain | 0.000 | 0/6 |
| revert24 | −0.405 | 0/6 |
| revert24_noblock | −0.355 | 0/6 |
| revert100_noblock | −0.522 | 0/6 |
| long_existing | −0.738 | 0/6 |
| shrink50_100 | −0.046 | 1/6 |
| **shrink50_24** | **+0.029** | **3/6** |
| shrink50_bigcorr | +0.011 | 1/6 |

内层选择在六个 fold 上**全部选中 plain**。shrink50_24 的逐折外层差为 +0.002、−0.011、−0.005、+0.001、0.000、+0.186：唯一正贡献来自 distance >24→1..24 外推折，其余折在噪声内或为负。按事先声明的门槛（平均为正且至少 5/6 折为正）判定 `hypothesis_supported=false`。

99 条 stress（带宽加权 / 样本等权）：plain 80.556 / 70.011；revert24 82.498 / 87.811；revert24_noblock 80.626 / 77.042；revert100_noblock 78.396 / 76.943；shrink50_24 81.321 / 78.021；long_existing 59.162 / 86.879。stress 在19A/19B已多次观察，只能作为旁证；它与六折的方向并不一致（revert24 在 stress 上带宽加权更高、在六折上平均 −0.405），本实验以事先声明的六折门槛为准，不据此改判。

证据：`validation/results/exp32-selection.json`。

## 3. 端到端候选：shrink50_24

按「平均差最好」取候选 shrink50_24，在 C++ 中实现为 `-residual xgb-shrink24`（枚举值、默认 off；折半在 double 中完成，整数结果与 Python 规则逐位一致）。候选二进制 `build/exp32/estimate-shrink24` 用 `-residual xgb` 在公开 1M 上与实验29 参考逐字节相同（sha256 `c5ba12ae…`）。

### 3.1 独立架构 3,107 条

复用 `validation/results/exp24-holdout-samples.csv` 与 exp24 的完整端点剔除、分带权重规则；C++ 输出与 Python 规则的差异只有 6 条负 exact 可达性修复（`all_negative_exact=true`）。

| 方法 | 等带加权 accuracy | 语料加权 accuracy | 语料加权 MAPE | 样本等权 accuracy |
|---|---:|---:|---:|---:|
| off | 78.797 | 93.578 | 1.655% | 84.721 |
| xgb | **81.760** | **95.376** | **1.184%** | **87.517** |
| shrink50_24 | 81.323 | 95.359 | 1.191% | 87.283 |

分带（语料加权 accuracy，候选−xgb）：band 0 −1.738（35 行）、1-12 +0.102、13-24 −1.397、25-50 及以上 0.000。Block 分组（语料加权 accuracy）：crossable_h_block 68 行 90.230→90.201、noncross_v_block 3 行不变、target_land_block 44 行 89.322→89.394。候选在独立集上同样净退化。

证据：`validation/results/exp32-holdout-eval.json`。

### 3.2 公开 1M replay 与 CPU

三次运行都用同一候选二进制，串行、单线程；规则在跑公开集之前已冻结，golden 只在评分时读取。

| 方法 | 全量 accuracy | 全量 MAPE | 剔除标签池后 accuracy | MAPE | CPU (user+sys) | 峰值 RSS |
|---|---:|---:|---:|---:|---:|---:|
| off | 94.0890 | 1.5156% | 94.1673 | 1.4914% | 55.38 s | 903,600 KiB |
| xgb | **96.1160** | **0.9871%** | **96.1868** | **0.9666%** | 50.01 s | 903,752 KiB |
| shrink50_24 | 96.1043 | 0.9930% | 96.1769 | 0.9714% | 47.32 s | 903,740 KiB |

候选相对 xgb 改变 17,324 行，全部 Manhattan ≤ 24（band 0 21 行、1-12 4,790 行、13-24 12,513 行），长距行逐字节不变。分带 accuracy 差（候选−xgb）：band 0 +1.580（22 行）、1-12 −0.251、13-24 −0.842，25-50 及以上 0.000。全量 accuracy 净 −0.0117 个百分点，MAPE 变差 0.0059 个百分点；CPU 差异（47.32 对 50.01 s）只有单次运行，且与短距折半应带来的微小节省同量级，不作为加速证据。

证据：`validation/results/exp32-public1m-score.json`、`exp32-public1m-summary.json`、`exp32-1m-*.time.txt`。

## 4. 结论与不采纳理由

1. 标签层六个外层折上没有任何条件规则稳定优于 plain；内层选择 6/6 选 plain。直接针对 Block 标签的 revert 变体一致为负（−0.36 到 −0.52 平均），而 Block 标签行本身从模型中受益（§3.1 分组：crossable_h_block 语料加权 accuracy xgb 90.230 对 off 72.689，target_land_block 89.322 对 88.605）。因此「短/Block 行被模型误修」在本标签集上不成立。
2. 唯一平均为正的 shrink50_24 只有 3/6 折为正、平均 +0.029 个百分点，独立集语料加权 −0.017、等带 −0.437，公开 1M 全量 −0.012、MAPE +0.006，均为净退化。
3. 因此候选保持默认 off，不进入生产；正式交付、`build/submission` 与默认配置不变。C++ 里保留显式 `-residual xgb-shrink24` 仅用于复现本失败实验。

## 5. 限制与未验证

- 标签只有 10,024 行，band 0 仅 22 行；条件规则的可分辨性受限，负结果只限当前标签、特征与容量。
- 99 条 stress 在19A/19B已观察，不是干净留出；独立 3,107 条与公开 1M 未被候选选择过程使用。
- 公开 1M 的 CPU 只各测一次，未做正反顺序重复；候选 CPU 与 xgb 的差异不构成加速结论。
- 未做统计显著性检验；未测十亿规模；未测其它阈值（24 与 100 来自既有距离带边界与19B 常量，评估前固定）。
- 未改动 `src/` 默认路径、模型文件、训练标签与 golden；无新依赖、无全图索引。

## 6. 复跑

```sh
# 标签层选择（六折外层 + 99 stress）
build/venv-ml/bin/python validation/exp32_short_block_residual.py
# 独立 3,107 条（先用候选二进制生成 exp24 预测，再评估）
build/venv-ml/bin/python validation/exp32_short_block_residual.py --holdout
# 公开 1M：off / xgb / 候选三次运行与评分
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/exp32/estimate-shrink24 \
    src/main.cpp src/architecture.cpp src/router.cpp src/residue_estimator.cpp
./build/exp32/estimate-shrink24 -residual xgb-shrink24 -in delay_estimate_request.csv \
    -out build/exp32/1m-xgb-shrink24.csv
build/venv-ml/bin/python validation/exp19c_score.py --out validation/results/exp32-public1m-score.json \
    --out-dir build/exp32 --result-name "1m-%s.csv" --modes off,xgb,xgb-shrink24 \
    --timing-template "validation/results/exp32-%s-%s.time.txt" --time-prefix 1m \
    --legacy-summary validation/results/exp32-legacy-summary.json
```
