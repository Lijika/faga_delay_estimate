# 实验76：base 锚点与固定目标新窗口验证预注册

日期：2026-09-26。测试比较固定为 3 对交错运行。

## 目的与冻结协议

- 当前正式基线是实验63 reachable-only base-d8 模型及其交付包。公开 1M 只用于最终契约和资源检查，不参与本轮模型选择。
- 新验证窗口固定为 affine unique 请求的 `[26M,28M)`，抽样和 exact 标签完成后才计算候选指标。窗口与训练端点完全隔离，命中排除集即停止且不补样。
- 训练池固定复用实验63的可达标签来源，完整端点去重，仍排除 `exact < 0`；47维 base 特征、六个屏蔽槽、64棵树、`max_depth=8`、`seed=20260919`、单线程和按距离带权重固定。
- 固定比较三个目标：
  - `fast-anchor`: `target = exact - fast`，`reg:absoluteerror`，当前正式配置控制组。
  - `base-anchor`: `target = exact - base`，同一特征和树配置，输出 `base + correction`。
  - `fast-pseudohuber`: `target = exact - fast`，只把目标固定为 `reg:pseudohubererror`，其余参数不变。
- 主指标为按新窗口距离带份额加权的 pooled accuracy。配对 bootstrap 10,000 次、seed `20260925`；候选须达到 `+0.03 pp`、95%下界大于0，且 false finite 与 reachable false unreachable 不增加。三个候选分别与当前正式输出比较。
- 只有精度通过的候选才进入同一 1M unique 输入上的 3 对 CPU 交错比较；输出 SHA、行数、端点顺序、整数 delay、EOF、单线程、RSS≤2 GB、wall≤3600 秒均须通过。精度失败的候选不测性能、不改正式入口。

## 证据与限制

请求生成器、probe、训练参数、输入身份和 exact 标签写入 `validation/results/exp76-*`。本轮只支持同架构新请求窗口的判断，隐藏分布和平台 1B 成绩以实际评测为准。

## 结果

- `[26M,28M)` 生成 2,000,000 行，按七带抽取 6,177 行；距离、带划分、完整端点去重和历史排除集均通过，命中 0。请求 SHA-256 为 `25ebb8cd3a6577c6488b9d6b8f2d22b8ae6decd418b4917f9d4f1c4c9cd5b27b`，样本 SHA-256 为 `ab50437d9a0c1e5a3c33cf18a9880a8b8af8d4c056dbeb27b562915fd52010ba`。
- fast-anchor 重训模型 SHA-256 为 `79e705e78d3680e9528f479dd2b6722ef6dc06ba0272c0ff0e8823385a256fe0`，与实验63正式模型一致；控制组输出与实验63交付包逐行一致。
- 新窗口正式输出 pooled accuracy `96.223416%`，base-anchor `96.167988%`，差 `-0.055427 pp`，配对 95% CI `[-0.106699,-0.003329] pp`。fast-pseudohuber `96.038797%`，差 `-0.184618 pp`，CI `[-0.254921,-0.119372] pp`。两候选的 false finite 与 reachable false unreachable 均为 0。
- 两个候选均未达到 `+0.03 pp` 且 CI 下界未为正，精度门禁失败；按预注册协议不做 3 对性能测量，正式入口、源码和交付包保持实验63/71 状态。

收尾时 `/dev/sdd` 可用 488G。本轮未删除文件，释放量 0；`build/exp76` 与 `validation/results/exp76-score.json` 保留用于复现。新窗口结论只支持同架构该切片，隐藏分布和平台 1B 未验证。
