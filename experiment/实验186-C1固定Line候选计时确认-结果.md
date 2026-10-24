# 实验186 固定Line候选计时确认结果

2026-10-10。协议`ece95d9`，freeze`5843914`，
使用exp182 `combo_line4`相同ELF83,774,096 B，正式exp131保持。
预热一对、固定32对unique完整1M，全部纳入；CPU3单线程串行。

## 结果

| 指标 | 数值 |
| --- | ---: |
| baseline均值 | 39.658750 s |
| candidate均值 | 47.069375 s |
| 配对CPU差均值 | +7.410625 s |
| 四次评估族校正的CPU单侧上界 | +10.301668 s |
| accuracy复用exp174 | +0.083329629 pp |
| 条件综合点 | +0.004908495 |
| 条件综合保守下界 | −0.027977081 |
| 预注册主门 | 未通过 |

66次完整运行共66,000,000行，输出契约、逐次完整SHA、
负值位置、行序和精确EOF通过。单线程、最大RSS1,085,693,952 B、
最大wall118.09 s均通过，独立checker已复算所有time文件及最后完整输出。
总timed CPU2,836.50 s，未追加观察或替换统计门。

## 环境与边界

baseline范围24.74–80.46 s，candidate28.68–109.83 s；
配对差中位数+5.255 s，30项正、2项负，SD6.166949 s。
这些是运行后诊断，最终门继续采用原均值、t与alpha。
pair10快照未见持续占满的额外计算；后续发现DeepSeek恢复历史文本时
启动的两项`grep -rl`扫描。核对PID/参数后在pair19期间逐项SIGTERM，
时刻与进程身份存于`exp186-environment-diagnostic.json`。
扫描和既有漂移限制区间的条件覆盖解释，各次波动的原因仍未分解。

组件query改善、同候选公开accuracy及其他分布证据均保留原结论。
当前确认门未过，正式路径继续exp131；同候选/输入的完整确认计时停止追加。
下一轮通过新算法降低parent恢复成本，以独立消融判断收益。
目标1B的K=1M及accuracy分布迁移属于原协议假设，隐藏集/平台CPU待实际评测。

## 证据与维护

命令为`python3 validation/exp186_line_timing.py --stage run`及
`python3 validation/exp186_evidence_check.py`，独立checker全部通过。
原始time/输出在`build/exp186/`，结果为`exp186-line-timing.json`、
`exp186-evidence-check.json`和环境诊断；冻材料保持原身份。
DeepSeek审查及纠正已记录，采用terminal前驱热路径独立探针建议。
收尾`/dev/sdd`仍可用447G，删除0 B，无新增>10 GB文件。
