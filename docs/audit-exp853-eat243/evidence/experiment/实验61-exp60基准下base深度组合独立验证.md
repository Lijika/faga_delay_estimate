# 实验61：exp60 基准下 base-d8 独立验证

日期：2026-09-26。开工空间：`df -h .` 显示 `/dev/sdd` 可用 495G。

## 预注册

- 主假设：实验58冻结的 `base-d8` 模型（47 特征、depth 8、64 树）与实验60正式版相同的 `-3 ps` 输出中心化组合，在新请求上有正的请求加权 accuracy 收益。
- 正式基线：`subm/latest/estimate-bin`，SHA-256 `cbc5c565ca1bff02d652509b801f1ffa65bffe328ef2f67d8f52dca6a64cd900`；本机相同算法的 `./estimate`，SHA-256 `a80595dd4ecd933da5ea46dc6293df33b912d77dc716ef1fcfbb6b047b8211c6`。候选由同一 `./estimate` 显式指定 `-residual xgb-base47-d8 -bias-ps -3`，模型 JSON SHA-256 `f98d726036801104ed88d60ec0d31340455cce0175ee7e653b875b6c0939661e`，静态头 SHA-256 `afb318fc50b3b394dab2c16fc0c8c68ea23328dbbb6a3f1ad846b8babe386810`。
- 新请求：现有 affine unique 生成器的 `[18M,20M)`，固定七个距离带、每带最多 1024 条。排除公开 1M、训练池和已有独立切片，包括实验57 `[14M,16M)`、实验58 `[16M,18M)`；命中排除集就停止，不补样。exact 标签由 `query_profile_exp18b --pdb-only` 给出，SHA-256 `613139d1b2d3363f1909c2d4a15dbe31c61fa8592732afc8ed5136e26b2730e5`。
- 主指标为按新窗口各距离带原始请求数加权的 pooled accuracy 差（百分点）。七带配对 bootstrap 10000 次，seed `20260925`；同时记录 MAPE、分带、负 exact 和不可达误判。点增益至少 `+0.03 pp`、95% 下界大于 0、false finite 不增加，进入 CPU 测量。最终综合收益点估计至少 `+0.01`，精度下界与 CPU 上界组成的保守下界须大于 0。
- 先用同一二进制、同一 1M unique 输入测量 10 对平衡顺序的 user+sys CPU，并核对输出 SHA、行序、字段、EOF、单线程和 RSS；再据 profile 判断计算、内存或 I/O 热点。每次优化只改一个变量，保留逐行数值一致性。repeated 和 unique 分开报告，按实测 distinct 数外推 1B。
- 若精度门槛失败，本模型组合停止正式接入；如果通过但 CPU 联合下界失败，保留私有候选与原始证据，定位最大热点后继续单变量优化。正式打包以完整 1M 输出与资源门槛为准，平台 1B 成绩另记。

## 命令与结果

运行 `build/venv-ml/bin/python validation/exp61_base_d8_exp60.py --stage requests|sample|score`。请求身份、模型身份、逐行预测和配对统计写入 `validation/results/exp61-*`，中间文件写入 `build/exp61/`。

### 独立精度结果

原始证据为 `validation/results/exp61-stage-requests.json`、`exp61-stage-sample.json`、`exp61-score.json` 与 `exp61-predictions.csv`。

- `[18M,20M)` 原始请求 2,000,000 行，实际采样 6,178 行，七带覆盖完整，端点排除集命中 0，距离与分带检查通过。
- 包内 exp60 accuracy `95.65084278983433`，base-d8 加 -3 accuracy `95.83029491835879`；增益 `+0.1794521285244599 pp`，七带配对 bootstrap 95% 区间 `[+0.12704936245490464, +0.23209117206734073] pp`。
- MAPE 为 `1.1068391109604523%` 与 `1.061218941424803%`；96 条负 exact 两侧均输出不可达，false finite 与 reachable false unreachable 均为 0。
- 本窗口用于冻结模型的独立验证。任何依据本窗口改变的模型、特征、训练参数，后续将使用另一固定新窗口验证。公开本地 1M 的用途为最终评分、输出契约和性能测量；其 golden 不进入本轮选样或选型。

### 失败检查与恢复

系统 `python3` 缺少 xgboost，改用项目已有 `build/venv-ml/bin/python`。exact 求解完成后的初次排除检查发现 `build/exp57/exp58-kept.csv` 内容为带内索引 `0,0`，其格式无法作为端点请求解析。exp58 的真正端点由 `exp58-samples.csv` 完整提供；改用这个已登记样本文件进行排除，通过 `--stage audit-sample` 复用已完成的 exact 产物，保持原抽样与标签。

### 性能测量与归因

冻结 1M unique 输入 SHA-256 为 `2cf587f1…a018d7bd`。包内 exp60、根目录 exp60、根目录 base-d8 加 -3 三路各预热一次、CPU 3、串行轮换 10 轮，原始数据见 `validation/results/exp61-timing-1m-unique.json`。

| 配对 CPU 差（秒/1M unique） | 均值 | 95% 区间 |
| --- | ---: | --- |
| 根目录 exp60 − 包内 exp60 | +0.056 | [−0.677,+0.789] |
| base-d8 − 根目录 exp60 | +2.411 | [+1.500,+3.322] |
| base-d8 − 包内 exp60 | +2.467 | [+1.351,+3.583] |

三路均为 1,000,000 行、单线程、恰好 3 字段、端点原序、整数 delay、精确 EOF；每路十轮单一 SHA。包内与根目录 exp60 SHA 都是 `bafd6006…`，base-d8 为 `983b8541…`；负值位置三路相同。最大 RSS `925,675,520 B`，最大 wall `46.16 s`。按新窗口精度与配对 CPU，综合收益点估计 `+0.1230`、联合保守下界 `+0.0718`（按 1M distinct 向 repeated 1B 摊销，依赖相同输入分布）。

Callgrind 组件探针 `build/exp61/callgrind.out` 使用真实 6,178 行特征。候选 `xgbBase47Raw` 的比较行约 1.78 亿指令，生产 `xgbRaw` 约 0.92 亿；特征计算增量较小。全探针包含架构 JSON 解析，因此热点判断以已计时的残差替换和树遍历调用区间为准。模型增量主要是单线程 CPU 的深树条件遍历；两模式共享建表、缓存、输入和输出路径，且没有锁。每个 cache miss 处理 64 棵深度至多 8 的树，树路径工作量为 `O(64×8)`；重复集总输出 I/O 为 `Ω(N)`，模型推理随 distinct 数 `K` 增长。

按预期回报排列的单变量候选为：① 固定深度遍历，目标回收模型增量约 2 s/1M；② 只写模型读到的特征，实验58消融收益落在噪声内；③ 缓存或 I/O，等新的端到端 profile 证明收益超过当前建表与输出成本再试。此轮选①，复用实验58同模型 padded 树数据，新增静态表约 1.3 MB。

私有实现只把 `xgbBase47Raw` 换为 `xgbBase47FastRaw`。6,178 条新窗口输出逐字节相同；3 对 1M unique 前后 CPU 差 `−2.383 s`，95% 区间 `[−3.193,−1.574] s`，三轮完整输出 SHA 都是 `983b8541…`，峰值 RSS `925,753,344 B`、线程数 1。原始数据见 `validation/results/exp61-walk-1m-unique.json`。用户要求后续测试使用 3 轮；区间按 df=2、t=4.302653 计算。

直接 exp60 包对新正式源码的 3 对 CPU 差为 `[+2.74,+6.13,+0.27] s`，均值 `+3.046667 s/1M unique`，95% 区间 `[-4.261696,+10.355030] s`。综合收益点估计 `+0.118173`，保守下界 `+0.015348`，通过本轮门槛；CPU 严格等价尚未证明。见 `validation/results/exp61-formal-1m-unique.json`。此组的源码二进制 `95c5ac2c…` 保存在 `build/exp61/estimate-formal`。

公开 1M 输出 SHA `01d19ee4…`，`validation/verify.py score` 核对 1,000,000 行、端点顺序与格式，accuracy `96.363441`。冻结 1M unique 输出完整 SHA `983b8541…`，与私有 walk 候选相同，17,585 个不可达位置相同，单次 CPU `42.80 s`、RSS `925,548,544 B`。`build/verify_estimator --arch doc/eda比赛文件/arch` 通过。公开 golden 只用于最终评分。最终源码保持 `-bounds` 等诊断配置的原模型选择。

静态包版本 `exp61-base47-d8-walk-aa33480`，包内 bin SHA-256 `f87675a4b99d8ba39f5f5634c21ec252c5235e67ed95f14ff6f96592a43d07f9`，zip SHA-256 `e47dbfe54942f751eacc490a76459ba606eb643b7341df08766d8421f247cc62`。`--verify` 的公开 1M SHA 与 3,107 holdout 逐字节检查通过，独立无架构目录运行通过。`validation/results/exp61-package-1m-unique.json` 记录包内完整 1M unique 三轮输出 SHA 均为 `983b8541…`，CPU `42.23/41.91/42.54 s`，最大 wall `44.28 s`，RSS `923,791,360 B`，单线程。`build/submission/estimate`、`subm/latest/estimate-bin` 和不可变版本目录中的 bin 已核对同一 SHA。平台 1B 与隐藏分布尚无回执。

冻结的 exp60 根目录二进制另存 `build/exp61/exp60-root`，包内版本从 `subm/versions/exp60-uniform-bias-scriptfix-70360a9/bin-estimate` 读取；脚本继续使用固定身份路径。后续测试默认 3 轮，此前已通过的 10 轮历史数据保留。
