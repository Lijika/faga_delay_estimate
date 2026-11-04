# 实验158 C1 安全界radix小样本成本

2026-10-10，Asia/Shanghai。分支`research/exp158-safe-bound-radix`，起点`76221e9`。
开工`/dev/sdd`可用454G，正式exp131保持。

## 固定候选

exp157通过当前官方mult2安全界逐边一致性与uint32资格审计。
本轮保持exp154的max-before-floor安全界、dense cache及exp150 terminal消元，
复用exp156窄轨道表恢复。候选只把query frontier从binary改为现有radix。
假设为同一exact输出下query CPU减少，accuracy保持；heap同键顺序各自记录。

改动覆盖私有Router副本、全部编译消费者、probe和runner。
通过当前已审计的固定Provider和配置解除私有external+radix限制，
每个RadixFrontier push检查`key>=last`，建表也使用同一私有header。
生产接口、正式源码和提交包保持。冻结全部private源、架构、表和二进制身份。

## 预登记测量

固定exp146的92行与exp150原始逐行结果，8行做plain Dijkstra参考。
零延迟、I-target、同pin、不可达及跳格复用6条terminal checks，两种队列都跑。
两种队列分别全92行audit，访问的每个Provider状态比较两种已冻结等价计算方法，
binary轨迹与exp150逐行一致；radix只要求exact一致并记录自己的expanded/relaxed。
每种各warm一个50循环块，5对binary-radix/radix-binary交错，各块50循环全部92行；
测CPU3，单线程，串行，Provider缓存每块清空且query cache关闭。
重复运行要求各自轨迹和exact一致，检查monotone push、complete Provider、证据完整。

小样本CPU门为配对差df4双侧95%t上界<0且平均节省>=5%。
RSS<=2,000,000,000 B、wall<=600秒。失败保留候选和结果，
exact/单调断言失败停止radix；CPU门未过保留资格与待定成本结论。
该CPU包含运行时assert成本，单位为92行×50循环，属于组件筛选，
后续6176与0.10触发族另测weighted CPU与综合收益。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp158_safe_bound_radix.py freeze
# 提交冻结记录后运行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp158_safe_bound_radix.py run
```

私有`build/exp158/`，证据`validation/results/exp158-*`，拒绝覆盖。
本轮使用已查看的开发请求；完整1M、新请求、静态ELF与平台1B另验。

首次freeze编译生成产物，严格检查因main宏重复定义和未使用旧helper警告停止，
未进入测量。修正两处拼接残留，现场保留于`build/exp158-attempt0/`；
固定候选、输入、计时顺序及门槛保持。
