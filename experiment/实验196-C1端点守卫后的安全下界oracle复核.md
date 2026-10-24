# 实验196 C1 端点守卫后的安全下界 oracle 复核

2026-10-10。承接 exp194 的不可达资格诊断和 exp195 的端点必要条件审计。本轮只做
离线复核，不修改正式源码、`estimate`、交付包、已注册候选或既有统计门。

## 固定输入

- `h_safe` 逐行值：`validation/results/exp194-safe-lower-oracle-initial.csv`。
- 端点资格：`validation/results/exp195-endpoint-reachability.csv`。
- 七带权重、exact 与 exp174 baseline：`validation/results/exp174-predictions.csv`。
- 架构、正式入口和全部上游身份由本协议 freeze 记录。

本轮不重新调用求解器，也不重新计算 h_safe。exp194 的 C++ 过程不以 exact 选择
候选；本轮只把 exp195 的 `local_direct || (E_s && E_t)` 作为使用资格，并重新计算
离线 `max(P,h_safe)`。exact 仅用于独立评分、下界核对和统计，不能进入候选值。

## 资格语义

```text
use_lower =
    baseline >= 0
    && safe_lower is known and complete
    && endpoint_guard == 1

candidate = max(baseline, safe_lower) when use_lower
            baseline                 otherwise
```

`endpoint_guard` 是必要过滤器，不宣称完整 reachability proof。`baseline < 0` 永远保留
不可达输出，避免有限名义 residue 项把 `-1` 转成 finite。

## 预注册门

- exact 可达行的 guard 过滤数必须为 0；
- 被使用的 finite `h_safe` 不得大于 exact；
- oracle 点增益至少 `0.20 pp` 且七带配对 bootstrap 95% 下界大于 0，才值得进入新请求；
- 本轮不做 CPU 门，也不把 oracle 增益当作可部署收益。

## 命令

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp196_guarded_safe_oracle.py freeze
git add experiment/实验196-C1端点守卫后的安全下界oracle复核.md \
  validation/exp196_guarded_safe_oracle.py \
  && git commit -m "exp196: freeze guarded safe oracle review"
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp196_guarded_safe_oracle.py run
```

证据写入 `validation/results/exp196-guarded-safe-oracle.csv` 与
`validation/results/exp196-guarded-safe-oracle.json`。本轮结果只决定是否继续
`h_safe` 精度路线，不授权生产接入。
