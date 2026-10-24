# 实验85：radix桶容量复用

日期2026-09-26。开工 `/dev/sdd` 可用486G。

## 冻结协议

- 基线固定exp82 O2组合二进制SHA `c6a7d7477ff1bf496fdc14218d7c7dfff4aad7620424bd87af9508f9d39030bb`，源码与128树模型身份沿用 `validation/results/exp82-build.json`。唯一改动为 `RadixFrontier::top` 重分桶时直接遍历原桶，分配完成后clear保留容量，替代临时vector交换和析构释放。编译固定GCC13.3.0 O2，exp84 O3暂留独立候选。
- 假设为减少重分桶分配/释放可降低初始化CPU。exp82 perf中该函数12.48%的样本提供热点依据；分配贡献尚未单独量化。此改动覆盖residue建表和可选radix Router。原桶内所有键在改用其最小键后转入更低编号桶，迭代对象保持稳定；推导见Obsidian `[[radix重分桶容量复用]]`。
- 先对队列做固定随机操作与优先队列逐条键/条目校验，含32位边界、同键、交错插入及clear。私有测试再核对6,174条冻结exact样本输出SHA；随后完整1M SHA、端点/行数/3字段/整数/EOF、一致性、单线程、2GB/3600秒。精度复用exp77/78独立窗口，冻结模型和参数，1M只用于工程核对和计时。
- 每项比较预热后固定3对交错，核3，同机串行。首项候选对同源码O2，工程明确收益定义为CPU95%上界<0且点收益≥+0.01分。若点减时≥0.5秒但区间跨零，可继续对正式exp71直接比较，以评估128树整体工程收益；保留两项不确定性及选择效应。此条件预先固定，用户已授权继续优化CPU以保留精度明确提升的候选。
- 正式比较使用exp78精度+0.031625 pp、95%区间[+0.011613,+0.051856]，综合点收益≥+0.01且保守下界>0作为实测资格。exp77增益+0.026485 pp、区间[+0.005821,+0.047546]及其原+0.03 pp点门槛事实同时报告；结合用户最新授权审查实际收益，保持历史门槛记录。正式接入另做最终静态包完整1M验收；1B和隐藏分布按平台结果。
- 停止条件为正确性失败即定位，首项减时点值<0.5秒则保留证据并终止本轮组合；总计每项3对，避免追加轮次筛选噪声。原始证据 `validation/results/exp85-*`。复现 `build/venv-ml/bin/python validation/exp85_build.py` 与 `build/venv-ml/bin/python validation/exp85_timing.py --against o2`，条件满足后 `--against formal`。

## 构建与单项结果

私有候选SHA `8d4f08941e607f62510f2262638e3549a26b1cf904d7eb6833bd7250ea875c74`。队列基线/候选176,749次返回序列摘要同为 `b32efcbf7a12bdbd`，独立有序容器校验通过。6,174条冻结样本完整输出SHA `feb2787753fbde873ab8894fd8344b47d6e4082710987d06ef1470db8e61c38c`。首次构建因手写diff行数多1而在patch阶段停止，修正元数据后通过，代码语义保持。构建及身份见 `validation/results/exp85-build.json`。

| 配对 | 同源码O2 CPU/s | 复用桶CPU/s | 差/s |
| --- | ---: | ---: | ---: |
| 1 | 29.52 | 27.19 | -2.33 |
| 2 | 28.26 | 26.86 | -1.40 |
| 3 | 28.72 | 26.99 | -1.73 |

平均减少1.82秒，95%三对t区间[-2.991239,-0.648761]秒，1M工程筛选换算点收益+0.015167、保守下界+0.005406，单项通过。减时主要为一次建表收益，平台1B全程时间待测。预热及测量均完整核对1M输出SHA `a25c7c7c3483c5d8dcc20716de2e2294e693246256bec0a9162550fd539d33cc`、端点/3字段/整数/EOF、一致性，单线程与资源通过；候选测量最大RSS572,190,720 B、wall28.61秒。基线CPU29.52>wall29.21及CPU28.72>wall26.65按原读数保留，计时环境仍有不一致。

原始计时 `validation/results/exp85-timing-o2.json`；满足预注册条件，继续正式exp71比较。正式比较的中间输出/原始time文件放在 `build/exp85/formal/`，保存单项原始文件。

## 正式比较与接入验收

候选与正式exp71包的三对交错结果如下：

| 配对 | exp71 CPU/s | 候选CPU/s | 候选−exp71/s |
| --- | ---: | ---: | ---: |
| 1 | 27.44 | 26.70 | -0.74 |
| 2 | 27.52 | 26.65 | -0.87 |
| 3 | 28.41 | 26.71 | -1.70 |

CPU平均减少1.103333秒，95%区间[-2.397074,+0.190407]秒；结合exp78独立窗口精度+0.031625 pp、95%区间[+0.011613,+0.051856] pp，综合点收益+0.034495，保守下界+0.007704，按用户授权的实际收益判定通过。候选三轮公共1M输出SHA均为 `a25c7c7c3483c5d8dcc20716de2e2294e693246256bec0a9162550fd539d33cc`，exp71输出SHA为 `c17380dddfeba86addf764bad79a887eb25bab8544d4f64f69d8cb3097fe7e19`；两侧各自端点/3字段/整数/EOF、单线程、2GB/3600秒通过。候选最大RSS572,153,856 B、最大wall27.38秒；exp71最大RSS923,791,360 B、最大wall28.95秒。CPU与wall存在少量不一致读数，按预注册CPU指标保留。

接入前正式源码公开1M输出SHA `95d7fe3fd9733dd3dd510dbaa4dac2286b041ec164ff7a63a1917eab8c74af88`，CPU26.07+1.22=27.29秒、RSS558,648,320 B、wall28.54秒；3,107条holdout输出SHA `2cab76bb5b7b04a401387f8e6b5c8aa1fb6c9353825916420184d3bbb891c4b2`，行序、端点、字段和整数通过。根入口候选SHA `8d4f08941e607f62510f2262638e3549a26b1cf904d7eb6833bd7250ea875c74`，由 `sh scripts/build.sh` 和 `build/verify_estimator --quick --residue-mult 2` 重建检查；完整源码核验脚本待静态包生成后运行 `build/venv-ml/bin/python validation/exp85_package_1m.py <bin>`。

正式包将使用新算法标签和不可变版本目录；更新打包脚本中的历史公开/holdout期望只在静态包3轮1M与holdout验收通过后提交。平台1B、隐藏集和赛方机器仍未验证，正式分数以平台评测为准。

静态包 `exp85-radix-reuse-88d0d86` 已生成并完成 clean-room 自包含检查，包内bin SHA `e79648162f765f146e6f3989dfcda02e54622a3a96e4906f70697591673be3eb`，zip SHA `506a9cdfa426d64878ba877a991bc9614296f00a3e17fffd7541637fddaf42c5`。包内公共1M三轮输出SHA均为 `95d7fe3fd9733dd3dd510dbaa4dac2286b041ec164ff7a63a1917eab8c74af88`，CPU `27.17/27.04/27.11 s`，最大wall `28.15 s`，最大RSS `570,298,368 B`；3,107条holdout输出SHA `2cab76bb5b7b04a401387f8e6b5c8aa1fb6c9353825916420184d3bbb891c4b2`，CPU `11.76 s`，wall `13.54 s`，RSS `570,298,368 B`。输出契约、2GB/3600秒资源门槛通过；原脚本当时未实测线程。打包脚本 `--verify` 已更新为当前公开与holdout哈希，后续用新标签重建并复验。

随后修正验收脚本的线程计数，使其轮询实际进程及子进程；重跑同一bin的公开1M三轮、unique 1M一轮与holdout一轮。公开1M CPU `29.50/29.34/28.68 s`，输出SHA均保持；unique 1M CPU `28.78 s`、输出SHA `a25c7c7c3483c5d8dcc20716de2e2294e693246256bec0a9162550fd539d33cc`；holdout CPU `12.27 s`、输出SHA保持。五轮实际最大线程数均为1、最大RSS `570,294,272 B`、最大wall `29.59 s`，行序/字段/整数/EOF通过。修正后报告覆盖原 `validation/results/exp85-package-1m.json`，前一次原始time文件已被同名覆盖；此前CPU数值只保留在本日志中。两次独立验收CPU波动较大，性能判定采用预先固定的交错3对比较。收尾 `/dev/sdd` 可用485G，未清理大文件，释放量0。

最终用 `ALGO_VERSION=exp85-radix-reuse VERSION_LABEL=exp85-radix-reuse-5f5e016 sh scripts/build_submission.sh --verify` 生成新不可变版本。clean-room、公开1M SHA和holdout SHA均通过；包内bin SHA仍为 `e79648162f765f146e6f3989dfcda02e54622a3a96e4906f70697591673be3eb`，与上述实际线程验收的bin逐字节一致，复用输出与资源证据。新zip SHA `8be95c474a6c20a312185ad91bd0c27a2b60874e60dd062ff693922776cd4648`，`subm/latest/`、`subm/submission.zip` 和本地 `build/submission/estimate` 身份一致。旧版本目录保持不可变。版本元数据的 `git_working_tree_dirty=true` 反映仓库中仍有未纳入本实验的用户文件，核心提交身份为 `5f5e0166dfe45af834e8ef95b8c6cc33ba43057b`。

收尾 `/dev/sdd` 可用486G，释放量0；本轮未删除大文件。
