# 实验98：depth 10 无用末层节点删除

日期：2026-09-27。开工 `/dev/sdd` 可用约 479G。

## 冻结协议

实验93独立窗口 accuracy 增益 `+0.040127 pp`，95% 区间 `[+0.000557,+0.080474] pp`；现有静态实现相对实验92 depth 8 的三对 1M unique CPU 增加 `5.00 s`。本轮固定模型与输出，检验其工程成本是否还能下降。已有符号 perf 记录 `build/exp93/perf-depth10-symbols.data` 中 `applyResidual` 占用户态采样 22.29%，`quadrantDiagnostics` 占 33.39%；无丢样。

基线为 `build/exp93/estimate-depth10-static`，SHA-256 `fedf38b2fe299eb1d6db4d35fb42d661c179de78d26b1eabce5eeb3864328b68`。模型 JSON SHA-256 `9e0989b5b0f38e272a3e481498ea7042b69fd9b2d8d87bbf78adb04e21ea58cf`，padded header SHA-256 `1e96563432104b87a16901b95469cb9b266c2d1bf4a69825f73afd78de2a8919`。候选使用私有 `build/exp98/src/`，只删除节点数组每棵树的索引 `[1023,2047)`，stride 从2047改为1023。全部 leaf、使用特征、阈值、10次比较、浮点累加顺序、编译参数与单线程保持。

固定深度10遍历在第 `d` 次比较前的 heap index 上界为 `2^(d+1)-2`，其中 `0<=d<10`，故只读 `[0,1023)`；终点索引用于独立 leaf 数组。逐树保留这1023个节点足以保持所有输入的路径与 leaf 值。脚本穷尽比较保留节点与全部 leaf，并核对6178条独立样本的输出 SHA。

性能输入固定为 `build/exp57/timing-1m-unique.csv`，SHA-256 `2cf587f1b27ccc5699040e64ea3efc6eb68c100cfd72a36cad383383a018d7bd`。核3、同机串行，双方预热一次，再按基线/候选、候选/基线、基线/候选交错3对。每次完整核对端点原文、1M行、3字段、整数delay、精确EOF与SHA，并采样进程树线程数，检查RSS<=2GB和wall<=3600秒。

等价工程收益通过条件固定为 CPU差95%上界小于0且点综合收益至少 `+0.01`（平均至少节省1.2秒）。失败关闭本布局；通过后才重新评估depth10整体相对depth8的精度与CPU联合收益，保留实验93精度区间。1M差仅描述已测unique分布；平台1B与隐藏分布另计。

```sh
build/venv-ml/bin/python validation/exp98_trim_depth10.py --stage build
build/venv-ml/bin/python validation/exp98_trim_depth10.py --stage timing
```

原始证据为 `validation/results/exp98-build.json` 和 `validation/results/exp98-timing-1m-unique.json`。正式入口与当前交付包保持本轮开工时状态。

## 结果

候选静态二进制 SHA-256 为 `64d5e9dc05ae0a3db8aa52be4dd97ada7df24b05c5f7da343819577d3b782b91`，删除节点数据 1,048,576 字节。130,944 个保留节点、131,072 个 leaf 全部一致；6,178 条独立样本的输出 SHA 为 `73a9125e0fcea0f777453217834113a41717f15c63a99d81f3e074583c2bbc49`，与实验93完全相同。

| 配对 | 原 depth10 CPU/s | 删除末层 CPU/s | 差值/s |
| --- | ---: | ---: | ---: |
| 1 | 30.98 | 29.64 | -1.34 |
| 2 | 30.92 | 29.52 | -1.40 |
| 3 | 31.01 | 29.82 | -1.19 |

CPU差均值 `-1.31 s`，3对 t 区间95%为 `[-1.578701,-1.041299] s`。等价综合点收益 `+0.010917`、保守下界 `+0.008677`，预设工程门槛通过。双方预热和6次正式运行的完整1M输出 SHA 均为 `d7b5f9ac590c97004404ee7827fa8161f287d19172566f0f1cf2d8979fe105fa`；每次1,000,000行、17,585个负值及位置一致，端点、3字段、整数delay和精确EOF均通过。进程树采样单线程通过，峰值RSS为572,260,352字节，最大wall为31.03秒。

结论限同模型的末层删除，直接证明其输出等价及已测 unique 分布的性能改善。depth10相对depth8的整体接入需另作直接配对并合并实验93精度区间；两轮CPU均值相加只可用于候选筛选。repeated和平台1B未验证。

收尾 `/dev/sdd` 可用约479G，释放量0；本轮私有构建约98MB，无大文件删除。
