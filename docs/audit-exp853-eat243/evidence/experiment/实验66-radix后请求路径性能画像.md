# 实验66：radix 后请求路径性能画像

日期：2026-09-26。开工时 `/dev/sdd` 可用490G。

## 预注册

- 当前正式源码基线 `./estimate` SHA-256 `391f765c53edb12c8dcf079d9ca85435fc3116afb3ef86f6186efcec58ebef99`；冻结1M unique输入 `build/exp57/timing-1m-unique.csv` SHA-256 `2cf587f1b27ccc5699040e64ea3efc6eb68c100cfd72a36cad383383a018d7bd`，完整输出应为 `c17380dddfeba86addf764bad79a887eb25bab8544d4f64f69d8cb3097fe7e19`。
- 先对该二进制运行一次完整1M的 `perf record -g -e cpu-clock:u`，按无子调用累计的函数样本确认新热点，再按一次建表、每 distinct 请求与每输入行区分成本。采样计时仅用于定位，不作收益估计。
- 根据画像按预计节省的 CPU、实现风险、输出影响和 2 GB 内存预算列候选。只选择一个当前代码可复用的等价改动；先核对完整SHA、行序、整数delay、EOF、线程数与RSS，再预热后做3对交错CPU比较。
- 通过门槛：数值及资源契约不变，候选减基线的CPU差95%区间上界小于0，点综合收益至少 `+0.01`。精度不变时综合增益按 `-ΔCPU/120` 算。未通过则保留实验结果，不接入正式路径。
- 本轮公开1M只作输出契约与性能样本，不用于模型、特征或阈值选型。1B与隐藏分布只能按明确输入假设外推，正式成绩以平台为准。

## 画像与候选

`perf record` 完整1M输出SHA与冻结值一致，133,088个用户态样本、丢样0。`perf report --no-children` 的热点：`quadrantDiagnostics` 30.41%、`RadixFrontier::top` 28.74%、`runResidueDijkstra` 14.18%、`fillTargets` 11.86%、`applyResidual` 4.36%。`perf annotate` 将 `top()` 的主要采样定位到桶0内线性寻找最小状态编号的循环。

| 候选 | 热点上限与成本口径 | 风险 | 本轮决定 |
| --- | --- | --- | --- |
| 桶0直接弹出同键条目 | `top()`占28.74%，其中扫描占主要样本；一次建表成本 | Router exact 的同键状态顺序变化，需核对数值 | 先做 |
| `quadrantDiagnostics` 生产快路径 | 30.41%，每distinct请求多次调用 | 探针/生产语义分叉风险 | 留待独立实验 |
| `fillTargets` 重排 | 11.86%，一次建表 | 表布局与INF语义风险 | 暂缓 |
| 残差推理微调 | 4.36%，每distinct请求 | 模型逐位等价要求 | 暂缓 |

`RadixFrontier::top()` 在非空桶0中取最小 `uint64_t`，即同键时按状态编号破同分。桶0条目的高32位都等于当前 `last_`；直接取尾项仍弹出最小键。Dijkstra与Router A*使用最小键和陈旧条目检查，同键顺序只影响搜索次序。新候选只删除该扫描，其他队列逻辑和键计算保持。

## 结果

候选只删除 `RadixFrontier::top()` 在桶0中的线性最小值扫描，直接弹出桶尾；最小键仍由桶分配和 `last_` 保证，同键顺序不参与距离判定。新增的 tie/bucket self-check 通过。`build/exp66/verify_internal --oracle --oracle-cases 8` 的10条独立图 oracle 查询无差异（该检查运行binary Router）；正式源码重建后的 `build/verify_estimator --quick --residue-mult 2` 的3,469条冷表查询无差异；`build/exp66/plan_probe --radix --count 24` 的22条 binary/radix exact 查询无差异（2条因坐标条件跳过），radix为1.69倍速，该短探针只用于功能检查。

过程中曾误运行旧 `build/exp65/verify_estimator`，其通过结果不计为本轮候选证据；上面的正式重建检查覆盖了当前修改。`plan_probe` 初次链接遗漏 `residue_estimator.cpp`、首次传入错误的 `--radix 24`，修正为完整构建及 `--radix --count 24` 后通过。

私有候选 `build/exp66/estimate-unordered` SHA-256 `6686f424e4f923df3b6991da6e648553aad5d98a2c4cd46564e44cb2faf16d89`。在冻结1M unique输入上，预热后3对交错CPU差为 `-9.67/-7.10/-7.80 s`，均值 `-8.19 s`，95%区间 `[-11.491,-4.889] s`；数值等价时综合收益点估计 `+0.06825`，保守下界 `+0.04075`。预热和6次正式运行的输出SHA均为 `c17380dddfeba86addf764bad79a887eb25bab8544d4f64f69d8cb3097fe7e19`，最大RSS `925,769,728 B`，单线程，最大wall `36.97 s`。原始证据为 `validation/results/exp66-timing-1m-unique.json`。

本轮没有模型或精度变量，公开1M只验证数值、输出和性能。改动作用于 residue 建表和 exact Router 的同键出队；已测 exact oracle 与生产输出保持一致。1B与隐藏集尚未验证；其他输入规模的收益按一次建表和 exact 队列成本外推。配对时基线为当时的 `./estimate`；重建后复现脚本指向SHA相同的冻结副本 `build/exp65/estimate-radix`。

理论前提与同键顺序证明见 Obsidian `[[radix同键出队顺序与精确距离]]`；索引与依赖双向关系已更新。

## 接入与打包

实现提交 `175449a`。正式 `sh scripts/build.sh` 的根二进制SHA与私有候选相同。`ALGO_VERSION=exp66-radix-ties VERSION_LABEL=exp66-radix-ties-175449a-dirty sh scripts/build_submission.sh --verify` 完成clean-room、公开1M及3,107条holdout核验，公开SHA为 `99dc587b98718fd63213bf6f44a497b5970c199fc444c01dbeb30401c004d41c`。

不可变包 `subm/versions/exp66-radix-ties-175449a-dirty/` 的bin SHA为 `1f68d9248f5fab50494bcb0cf6d0f53ae15945b1fb4429b75cdf78b80cecf1c8`，zip SHA为 `756b21949ddfe2e1fad6e457a7ec2cc773479064f6aaee5bb79947ef03f87303`。`build/submission/estimate` 同步到该bin，最新镜像和指针zip相同。复建历史label会按规则失败，应传新的唯一label。

`build/venv-ml/bin/python validation/exp66_package_1m.py` 三次完整1M unique通过行数、端点顺序、恰好3字段、整数delay、精确EOF和完整SHA检查；CPU `27.74/27.22/27.24 s`，最大wall `27.69 s`、RSS `923,795,456 B`，线程数1。三次完整输出均为 `c17380dddfeba86addf764bad79a887eb25bab8544d4f64f69d8cb3097fe7e19`，原始结果 `validation/results/exp66-package-1m-unique.json`。

收尾 `/dev/sdd` 可用490G，与开工同一显示值；本轮未删除文件，释放量0。本轮只有1M规模输出，原始画像与中间产物留存供复现。
