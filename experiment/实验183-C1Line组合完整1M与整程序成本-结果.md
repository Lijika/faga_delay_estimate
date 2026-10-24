# 实验183 结果

2026-10-10。协议提交`f6f271e`，冻结提交`9f6b5dd`，静态检查提交`334ed9d`。
复用exp182的combo_line4 ELF，83,774,096 B，SHA
`62a4a5a21f2b945086783434a817e356e8f4eafc81784448469e5d00cc11c21c`。
本轮全部冻结输入、工具和产物身份保持；没有重新选模型、阈值或路径集合。

## 完整运行证据

unique10对、public/repeated各5对，各预热一对，CPU3串行交错。
46次完整1M均通过端点行序、3字段、整数delay、精确EOF、完整SHA、
负值位置、多次一致和单线程/2 GB/3600 s检查。
最高RSS 1,085,759,488 B，最长wall 98.98 s，46次计时进程CPU合计1,617.39 s。
40源parent完整恢复298,945,600 B、12,352 direct/text/cache整数、静态依赖、
三种clean-room无arch配置、边界/零/不可达以及改core后关闭表全部通过。
exp182的块流和组件输出证据按协议复用。

| 分布 | distinct | baseline均值s | candidate均值s | CPU差s | 95%差区间s | 条件综合点 | 联合保守下界 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| unique | 1,000,000 | 55.340 | 55.890 | +0.550 | [-6.242587,+7.342587] | +0.062080 | -0.003318 |
| public | 1,000,000 | 28.614 | 31.134 | +2.520 | [+2.081269,+2.958731] | +0.045664 | +0.033214 |
| repeated | 1,000 | 2.700 | 3.176 | +0.476 | [-0.004221,+0.956221] | +0.062697 | +0.049902 |

两个unique/public诊断均为cache miss 1,000,000；repeated为miss 1,000、hit 999,000。
三种candidate完整SHA保持exp175最终整数。公开golden全1M为
baseline96.616134450、candidate96.694213099，增益+0.078078648 pp。
公开得分属于诊断；选型所用独立精度继续复用exp174
+0.083329629 pp、95%[0.072337692,0.094965168]。

## 波动与结论

unique的baseline实测从98.66 s降到28.25 s，pair内差范围[-18.48,+15.23] s，
环境存在明显运行间变化。记录`validation/results/exp183-environment-snapshot.json`；
该快照loadavg约1，未观察到其他持续占满CPU的计算进程，WSL未暴露cpufreq。
变化原因未确定。冻结次数、顺序和判决式保持，未追加重测或筛掉运行。
t区间依赖配对差的抽样假设；这次波动限制其解释，无法把不同轮绝对CPU直接比较。

主门要求unique条件综合点≥0.01且联合下界>0，本轮下界-0.003318，主门未过。
组件query提速与完整程序成本分别保留；初始化、输入分布和环境贡献需要进一步分解。
完整1M的输出与资源门已通过，正式接入仍须后续候选通过预注册综合门。
正式`./estimate`和`build/submission/estimate`保持exp131，平台交付指针保持。
费用未访问槽填充先做单源容量筛选；全费用恢复、稀疏散射和几何合成各自另验。

条件综合依赖同架构精度分布迁移、目标1B的K=1M distinct及新增完整1M成本可迁移；
repeated只有1000 distinct，其条件分数与平台缓存布局需分别判断。
平台1B、隐藏集与跨架构精度尚未验证。

## 复现与清理

```sh
python3 validation/exp183_line_full.py --stage timing --workload unique
python3 validation/exp183_line_full.py --stage timing --workload public
python3 validation/exp183_line_full.py --stage timing --workload repeated
python3 validation/exp183_evidence_check.py
```

已有报告保持不可变；重测需要新实验目录与冻结身份。
原始证据为`validation/results/exp183-*`及`build/exp183/{unique,public,repeated}/`。
开工/收尾`df -h /dev/sdd`可用均447G，本轮删除0 B，新增文件均小于10 GB。
原始输出和time按复现路径保留。
