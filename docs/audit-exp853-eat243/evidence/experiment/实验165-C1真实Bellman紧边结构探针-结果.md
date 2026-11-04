# 实验165 结果

2026-10-10，冻结提交`3cf7fe7`，正式exp131与生产源码保持。

262行exact与冻结expanded/relaxed逐行相同，统计106,046展开状态、
1,797,161扫描边，零余量边51,885，负sigma检查零违约。
存在tight successor的状态49,333，恰有一个为46,907，
同端口tight状态2,110，全部successor都tight的状态0。
最大tight出度5，已扫描真实折叠边最小费用48 ps。
全图2752条折叠Arc另核验严格正费，范围48–135 ps；真实resolver追加非负
Block/Line费用。因此固定一致h的零余量链严格降低h，零余量周期可排除。
证据`validation/results/exp165-positive-folded-arcs.json`。

按原七带权重折算1M distinct，各结构占比为

| 指标 | 加权比例 |
| --- | --- |
| tight扫描边 | 3.946598% |
| 含tight successor的展开状态 | 63.948110% |
| 恰有一个tight successor的展开状态 | 60.499875% |
| 同端口tight successor的展开状态 | 3.628261% |
| 全部successor都tight的展开状态 | 0% |

同端口5%研究门未过，停止扩大同端口宏候选。
跨端口单tight successor现象保留为新构造依据；每个已展开状态都有正余量退出，
零余量身份本身尚未给出消去该退出的证书。宏转移及其CPU另验。
六档直方图之和、weighted重算、端点/exact/轨迹、SHA链与资源独立复核通过，
见`validation/results/exp165-evidence-check.json`。

完整进程CPU17.08秒、wall16.26秒、RSS668,360,704 B、单线程。
额外h调用填充了Provider缓存，该CPU只描述诊断资源。
首次运行先于冻结提交启动，保留为`build/exp165-attempt0/`及
`validation/results/exp165-*-attempt0.*`。候选、门槛和源码保持后重新冻结，
提交后运行；两次所有结构字段相同，仅CPU字段变化。

本轮两题Astra仍在只读推导，下一询问按十实验约定在exp174后。
真实宏退出支配、策略压缩容量、独立新请求、实际ELF、生产接入、
完整1M与平台1B保持未验证。收尾`/dev/sdd`可用454G，删除0项、释放0 B。
