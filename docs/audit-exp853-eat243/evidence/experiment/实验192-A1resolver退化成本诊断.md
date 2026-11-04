# 实验192 resolver退化成本诊断

2026-10-10。分支`research/exp192-resolver-diagnostic`，上游`38820b4`。
开工`/dev/sdd`可用445G；正式exp131与exp191所有冻结候选和成绩保持。

## 问题与三个固定解释

exp191同ELF的两个estimator比较，formal table比raw点增5.100893s/1M，
同时95%[+3.201092,+7.000694]，C1差−0.146990s、区间跨零。
本轮仅诊断，原固定核停止完整1M扩大的决定保持。

1. 索引/资格分支的固定成本超过短Net原walk，实际单hop重放也会退化。
2. 双estimator分别持有460MB表，布局/工作集导致退化；
   同一estimator只切换资格时，full direct差会缩小。
3. 实际offset构成偏向短hop；加权调用量能解释局部表的低节省上限。

先把原6176正式direct预测的每次forward/predecessor记录成调用序列，
每条实际返回均与原walk比较。trace在另一私有二进制，计时核无trace分支。
以单个正式estimator同一份表切换raw/table资格，保持模型、query和输出。
以相同实际调用序列单独测公共resolver，保留valid/x/y/delay逐调用核对。
两项分别称single与micro；micro按所属请求人口权重计s/1M请求，
分母为该带原请求数，涵盖无调用请求，避免用调用数替代请求数。
两者差值只用于机制诊断，额外控制和CPU环境仍可能影响因果归因。

## 固定计时与检查

single/micro各10对，CPU3串行，2轮预热、7带50次，pair内交错，
process顺序奇偶轮转，同时95% t(df9,0.9875)=2.6850108468164575。
全部观测保留，本轮没有新接入门或选型；单hop与single结果都报告。
每项逐6176预测等价，micro全部实际调用返回保持，线程数1。
记录各进程CPU、峰值RSS、wall及运行前后环境；RSS<=2GB、wall<=3600s。
checker独立复算调用权重、offset构成、输出和同时CPU区间。
不重跑冻结exp191，不修改原统计门，不把诊断作为完整exp131成本结论。

```sh
python3 validation/exp192_resolver_diagnostic.py --stage freeze
python3 validation/exp192_resolver_diagnostic.py --stage run
python3 validation/exp192_evidence_check.py
```

协议与新test先提交，复制exp191的formal私有源码，仅增audit资格切换及trace钩子；
freeze提交后运行。真实resolver实现、表、模型、原walk均保持。
原始在`build/exp192/`，报告在`validation/results/exp192-*`。
