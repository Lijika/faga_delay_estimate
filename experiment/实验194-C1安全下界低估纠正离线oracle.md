# 实验194 C1 安全下界低估纠正离线 oracle

2026-10-10。正式基线为 `exp131`，本轮只做离线诊断，不修改正式源码、`estimate`、
交付包、已注册候选或既有统计门。

## 目的

复用已推导并通过固定架构资格审计的

```text
h_safe(s,t) = min_c [R_nominal(s,t; dx - 14c, dy)
                     + Line(s,t) + 292*|c|]
```

作为一个可部署的低估侧下界候选，先测它在 `exp174` 的 6176 条七带加权请求上能否
提供足够的低估纠正空间。在线候选的离线理想变换是
`P_safe = max(P, h_safe)`；exact 只用于独立验证下界和计算 oracle 上限，不能进入
`h_safe` 的计算。

理论前提沿用 Obsidian《安全跳格修正启发式的下界证明》和《安全跳格界一致性的候选
移位证明》：固定公开架构、`residueMultiplier=2`、水平跳格宽度 14、费用 292、原始
端点 Line、完整 `c` 搜索及尾部停止证书。该前提给出可采纳性，不代表生产查询的一致
性能或跨架构资格。

## 固定输入与输出

- 请求、exact、基线预测、七带权重：`validation/results/exp174-predictions.csv`。
- 架构：`doc/eda比赛文件/arch`，身份在 freeze JSON 中记录。
- `h_safe` 计算不读取 exact；C++ 只接收请求、架构和 residue 表。
- 逐行输出保存 `h_safe`、support/known/complete、选择的 `c` 和求值次数。

## 预注册检查与门

1. 所有 finite 且 complete 的 `h_safe` 必须满足 `h_safe <= exact`；不满足立即停止。
2. 不可达、零延迟和同针脚语义保持；不把 unknown 当成零下界。
3. 计算 `P_safe=max(P,h_safe)` 的七带加权 accuracy、配对 bootstrap 区间、
   `G-h_safe` 分布、低估行捕获率和每行求值成本。
4. `P_safe` 只是离线 oracle，不接入生产。若点增益达到 `0.20 pp` 且区间下界为正，
   才值得扩大到未参与选择的新请求；否则保留理论和失败证据，转向其他低估方法。

## 计时边界

本轮不以 CPU 门选型。记录 provider 初始化、总求值数和进程资源，避免把 oracle 的
离线成本误报为生产收益。生产候选未来仍须单独证明它能删除的在线工作和完整 CPU。

## 命令

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp194_safe_lower_oracle.py freeze
git add experiment/实验194-C1安全下界低估纠正离线oracle.md \
  tests/exp194_safe_lower_oracle.cpp validation/exp194_safe_lower_oracle.py \
  && git commit -m "exp194: preregister safe lower-bound oracle"
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp194_safe_lower_oracle.py run
```

原始证据写入 `validation/results/exp194-safe-lower-oracle.csv` 和
`validation/results/exp194-safe-lower-oracle.json`。本轮不运行新最短路求解器、
完整 1M 或正式 ELF。
