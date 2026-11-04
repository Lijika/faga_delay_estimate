# 实验183 Line组合完整1M与整程序成本

2026-10-10，分支`research/exp183-line-full`，开工`/dev/sdd`可用447G。
固定exp182选择的combo_line4，83,774,096 B，SHA
`62a4a5a21f2b945086783434a817e356e8f4eafc81784448469e5d00cc11c21c`。
参考正式exp131为68,201,104 B，SHA `aed8b929…`。

## 假设与范围

恢复前Line加块费用、名义恢复后的Line及terminalGap复用保持exp175最终输出。
exp182纯query点省52.14%，本轮核验包含初始化的整程序收益。
复用已冻结ELF、模型、40源parent、块流、校准、cache和全部路径顺序。
受影响消费者为default CLI、direct/text/cache、架构匹配的表恢复及三种1M输入。
exp182的完整块流与组件等价证据复用；执行40源parent流、12,352条最终整数、
静态依赖、clean-room无arch、边界/零/不可达与改core关闭表检查。

三种完整1M的candidate完整SHA固定为exp175相应输出，
baseline固定为正式exp131现有输出。每次检查行数、原端点顺序、恰好3字段、
整数delay、精确EOF、完整SHA、负值位置、多次一致、单线程/2 GB/3600 s。
记录distinct、cache miss、行序与每次完整初始化CPU。
本轮没有模型、阈值或候选路径集合选型，精度复用exp174独立exact标签。

## 配对设计与主门

CPU3同机串行；每分布预热一对，pair内baseline/candidate交错。
unique固定10对、df9 t=2.262157162798205；
public/repeated各5对、df4 t=2.7764451051977987。
全部固定次数一次测完，完整1M同时承担契约和资源验收。

主门沿用exp181，unique条件综合点至少0.01且联合保守下界>0。
精度为exp174 +0.083329629 pp、95%[0.072337692,0.094965168]。

```text
point = 0.8 * accuracy_gain_pp - mean_cpu_difference_s / 120
lower = 0.8 * accuracy_ci95_pp[0] - cpu_ci95_s[1] / 120
```

前提为同架构exp174精度分布迁移、平台1B具有K=1M distinct，
完整1M新增CPU近似初始化+新增query+新增I/O。
public的条件式及全1M公开golden得分为诊断；repeated仅1000 distinct，
其精度与平台缓存布局另验。通过完整契约/资源及主门后另立正式接入实验。
本地1B属于可选诊断，平台1B和隐藏集以实际评测为准。

runner、checker与协议先提交，再freeze全部输入/工具/ELF身份并提交后运行。
结果写独立文件，冻结协议保持不可变；原始输出/time/diagnostic按名保留。
exp184后按十实验节奏向Astra提出两项有具体突破口与证据要求的问题。
