# 实验158 结果

2026-10-10，冻结提交`fc34ff7`。正式exp131与生产源码保持。

## 正确性与CPU

92行binary/radix全部exact相等，各访问Provider状态的六字段audit无差异；
所有radix入队单调断言通过。8行plain折回参考、6条terminal自检通过。
binary expanded/relaxed为33,349/593,893，等于exp150完整轨迹；
radix为32,420/577,348。同键顺序变化，两个模式的重复轨迹分别保持。

每块92行×50循环，5对交错均值binary 4.1289401806秒、
radix 3.7659337128秒，节省8.79175895%；
配对差95%t区间[-0.635482414,-0.090530522]秒，固定5%与区间门通过。
CPU76.87秒、wall77.91秒、RSS818,626,560 B、单线程，资源通过。
运行时单调断言包含在CPU中；本轮没有估算1M distinct的加权CPU或综合分。

独立CSV/原始日志核对完整身份、模式与行序、exact、重复轨迹、
计时顺序、配对区间和资源，见`validation/results/exp158-evidence-check.json`。

## 结论与局限

保留现有radix queue工程收益，下一轮固定同一Provider扩大至6176行，
再测0.10触发族的weighted CPU与条件综合收益。
此次结果覆盖已查看的92行；plain参考使用已验证的terminal折回，
全域一致性使用exp157固定配置证书。实际ELF、完整1M与平台1B另验。

首次freeze生成的binary因两条探针拼接警告停止，现场保留`build/exp158-attempt0/`；
修正后重新冻结，未运行首次产物。该阶段没有查看新验证结果。
收尾`/dev/sdd`可用454G，删除0项、释放0 B。
