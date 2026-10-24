# 实验197 A1 resolver 同对象自切换与初始化顺序诊断

2026-10-10。承接 exp191 的 68,160 B resolver 表和 exp192 的 single/micro
诊断。DeepSeek 审查指出 exp191 formal 的双 estimator 对照没有隔离对象身份、
堆布局和初始化顺序。本轮只做私有工程诊断，不修改正式源码、`estimate`、交付包、
既有统计门或预注册精度候选。

## 问题与假设

待区分的量为：

```text
F = candidate(table) - reference(raw)
S = candidate(table) - candidate(raw)
B = candidate(raw) - reference(raw)
F = S + B
```

exp191 观察到 `F=+5.100893 s/1M`，exp192 同对象 single 观察到
`+0.405697 s/1M` 且区间跨零，micro 观察到 `-0.217376 s/1M`。
本轮检验 `F` 是否主要来自双对象/布局，而非 resolver 表本身。

## 固定输入与实现

- 6176 条 exp174 加权请求、exp192 的 `build/exp176/queries.txt` 顺序和七带权重。
- exp192 已冻结的 resolver 表、架构输入、嵌入 residue 对象和候选模型。
- 三个运行臂由两个 estimator 在同一进程提供：
  - `reference(raw)`：独立 raw `Architecture` 与 estimator；
  - `candidate(table)`：candidate estimator，resolver 开启；
  - `candidate(raw)`：同一个 candidate estimator，切换同一个
    `Architecture::setResolverForAudit(false)`。
- 两种初始化顺序：
  - A：reference → candidate(table)；
  - B：candidate(table) → reference。
  初始化顺序只改变私有诊断构造，不改变查询语义。

每一臂都先以同一最终整数逐行核对。查询分组使用进程CPU时钟，计时不包含
初始化、预审计与CSV写出；完整进程的CPU/RSS/wall另记。每种初始化顺序固定
10个进程，按pair编号交错两种初始化顺序，每带50次重复、两轮预热、
`taskset -c 3`。进程内三臂按固定六排列循环，resolver开关每臂只切换一次。
七带按exp174总体权重外推每1M请求，20个进程共18,528,000次预测断言。

预先固定六项效应（两种初始化顺序各F/S/B），使用df=9配对t区间及六项
Bonferroni双侧同时95%区间。不把非显著结果解释为等价；无统计门、无追加计时。

## 预注册判定

- 主要诊断量：`S = candidate(table) - candidate(raw)`；
  `F = candidate(table) - reference(raw)`。
- 若同轮`B`的同时区间排除零，当前工装存在同为raw仍不等速的对象效应；
  该证据限制当前`F`的表替换归因。历史exp191观察与原判定保持。
- 若交换初始化顺序后`F/B`反号，初始化位置/对象上下文作为解释得到支持；
  页着色、cache/TLB和物理页机制仍需额外测量。
- 若`S`退化，记录双对象驻留下的同对象表替换效应；单对象生产CPU仍待测。
- 若区间跨零，仅记录未确定效应；历史single/micro不是本轮效应的上下界。
- 本轮没有 accuracy 自由度、没有生产 CPU 门，也不以任何结果接入正式版本。

## 证据与边界

完整结果写入 `validation/results/exp197-resolver-context.json`、逐行审计与分带
计时文件。此诊断只解释 exp191/192 的测量边界，不能替代相对 exp131 的完整
1M 验收，也不能外推到 combo_line4 的 parent、终端准备或重放成本。

## 命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp197_resolver_context.py freeze
git add experiment/实验197-A1resolver同对象自切换与初始化顺序诊断.md \
  tests/exp197_resolver_context.cpp validation/exp197_resolver_context.py
git commit -m "exp197: freeze resolver context diagnostic"
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp197_resolver_context.py run
```
