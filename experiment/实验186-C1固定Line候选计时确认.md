# 实验186 固定Line候选计时确认

2026-10-10，分支`research/exp186-line-timing`，上游exp185结果`18d56dd`。
开工`/dev/sdd`可用447G。复用exp182选中combo_line4 ELF与exp183全部身份，
83,774,096 B，SHA`62a4a5a2…`；正式exp131保持，标签/模型/参数/路径集合不变。
exp183 unique有显著运行间变化，baseline98.66→28.25 s、配对差[-18.48,+15.23]s，
原因未定；其完整输出与资源证据通过。此新确认研究当前运行条件的整程序增量成本。

## 固定设计

复用相同unique完整1M与原expected SHA，CPU3串行，预热一对，固定32对；
pair内baseline/candidate交错，开始、次数及结束由协议确定。
基于exp183差的SD9.495 s，32对的保守CPU半宽约4.45 s，作为规划依据。
全部运行纳入分析，不按中途结果筛掉观测；本轮后相同候选/输入不再追加计时。
pure deployment等价检查已通过且全部身份保持，复用exp183静态及public/repeated检查。
本轮每次仍检查完整1M契约、负值位置、多次SHA、单线程/2 GB/3600 s。
范围是完整运行CPU确认，未改变算法，无新accuracy样本。

为限制同一精度行为的正式接入反复计时，使用exp175/181/183/186四次CPU评估族。
CPU单侧alpha=0.025/4=0.00625；df31 t(0.99375)=2.651912689030802，
accuracy复用exp174双侧95%区间下端（单侧alpha=0.025）。
若各次CPU区间具有条件覆盖，union bound给accuracy及四次CPU总失败概率≤0.05。
前三次均未通过其原门，已记录结果保持；本次使用上述更严上界。
该覆盖依赖配对差的t模型和新计时误差假设；环境漂移会限制解释，需完整披露。
后续算法版本需要重新预注册，不能把该固定族当作无限次重测许可。

```text
cpu_upper = mean(delta) + 2.651912689030802 * sd(delta) / sqrt(32)
point = 0.8 * exp174_accuracy_gain_pp - mean(delta) / 120
lower = 0.8 * exp174_accuracy_ci95_pp[0] - cpu_upper / 120
gate = point >= 0.01 and lower > 0
```

条件继续为exp174同架构分布迁移、目标1B的K=1M distinct，
完整1M新增成本近似初始化/query/新增I/O。
完整1M契约资源门通过与本次主门通过后，另立正式接入实验核对最终构建身份。
平台1B、隐藏集及跨架构精度以实际结果为准。
计时期间Astra/DeepSeek仅只读轻量研究，压缩、求解或新编译保持串行。

## 命令

```sh
python3 validation/exp186_line_timing.py --stage freeze
python3 validation/exp186_line_timing.py --stage run
python3 validation/exp186_evidence_check.py
```

runner/checker/协议先提交，freeze后提交，再运行。
原始证据放`build/exp186/`与`validation/results/exp186-*`。
