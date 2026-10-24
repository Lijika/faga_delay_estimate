# 实验197 A1 resolver 同对象自切换与初始化顺序诊断结果

2026-10-10。实验197完成了预注册的20个固定进程。该轮只解释
exp191/192的resolver计时边界，没有修改正式源码、`estimate`、交付包、
精度候选或既有统计门。

## 结果

- 20个进程、18,528,000次逐行预测断言全部完成。
- 每个模式的逐行整数输出与exp174基线一致；`check` 通过。
- 从20份分带计时CSV独立复算加权效应，均值与汇总JSON最大差
  `1.8e-15 s/1M`；`F=S+B`逐对成立。
- 进程均为单线程，最大RSS `1,328,025,600 B`，最大wall `36.22 s`。
  这些资源数字只属于本轮直接查询诊断，不能外推为完整1M运行。
- `/dev/sdd` 开工与收尾均为可用 `445G`（54%）；本轮没有超过10 GB
  的可删输出，也没有释放量。

六项效应使用预注册的六项Bonferroni同时95%区间：

| 初始化顺序 | 效应 | 点差（s/1M） | 同时95%区间（s/1M） |
| --- | ---: | ---: | ---: |
| reference → candidate | `F` | +3.645818314 | [+1.891304322, +5.400332307] |
| reference → candidate | `S` | −0.967179784 | [−1.653587895, −0.280771672] |
| reference → candidate | `B` | +4.612998098 | [+2.497034961, +6.728961235] |
| candidate → reference | `F` | −5.079033818 | [−6.380038584, −3.778029052] |
| candidate → reference | `S` | −0.354842496 | [−1.951708374, +1.242023383] |
| candidate → reference | `B` | −4.724191322 | [−5.812288154, −3.636094491] |

`B` 在两种初始化顺序下都排除零且符号相反，说明同为 raw 的两个
estimator 存在显著的对象/初始化上下文效应。`F` 也随初始化顺序反号，
因此不能把exp191 formal的 `+5.100893 s/1M` 归因于68 KB表。`S`
在第一种顺序下为负，在第二种顺序下区间跨零；当前证据支持局部
resolver替换可能有收益，尚不足以证明稳定的同对象表收益。

## 结论与后续约束

- exp191 formal结果保留为“未隔离对象上下文”的观测，不再作为resolver
  表本身的CPU证据。
- 68 KB表仍保留为独立工程候选，下一次计时必须使用同一ELF、同一对象
  控制、完整1M输入，并将初始化、资格判断、索引、cache和输出成本一起计入。
- 本轮没有精度自由度，也没有相对正式exp131的完整CPU结论；不接入生产。
- 在完成同ELF raw/table控制前，不将`S`的init0点估计扩展为速度承诺。

## 证据与复现

- 汇总：`validation/results/exp197-resolver-context.json`
- 证据检查：`validation/results/exp197-evidence-check.json`
- 冻结身份：`validation/results/exp197-frozen.json`
- 逐进程CSV：`build/exp197/init{0,1}-pair{0..9}-audit.csv`及
  `build/exp197/init{0,1}-pair{0..9}-timing.csv`
- 检查命令：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp197_resolver_context.py check
```

输出为 `{"all_passed": true, "checked_predictions": 18528000}`。
