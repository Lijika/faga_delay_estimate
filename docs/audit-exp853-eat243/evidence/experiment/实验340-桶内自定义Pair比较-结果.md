# 实验340 桶内自定义 Pair 比较：结果

2026-10-17。候选只把桶内 `std::pair<int,uint32_t>` 换成带相同字段类型和
字典序 `<`、`>` 的本地 `Pair`，其余搜索、分组、模型、cache0 和输出逻辑保持。

## 验证

- 普通和 ASan/UBSan 队列夹具通过：395,400 pushes、242,496 pops、75 clears。
- 搜索审计保持 12,150 条字段和 126,462 条路径边。
- exact、边界、CLI、特殊 CSV、诊断和写出失败审计全部通过。
- 20k/100k 输出 SHA 与基线一致，单线程，峰值 RSS 约 1.67 GB，候选 ELF
  94,087,824 字节。

证据：

- `validation/results/exp340/freeze.json`
- `validation/results/exp340/search-check.json`
- `validation/results/exp340/audit.json`
- `validation/results/exp340/timing.json`

## AMD 参考计时

2026-10-17 更正。`timing.json` 的 `lscpu` 记录为 AMD Ryzen 7 4800H；原稿的
Xeon 标注有误。下表保留原始 AMD 数值，Xeon 测量另存 `xeon/`，候选选型等待
远端证据。

固定核 3，20k 和 100k 各预热一对，再做三对交错 AB、BA、AB。区间包含
0.02 秒计时舍入。

| 输入 | baseline 均值 (s) | Pair 均值 (s) | 点差 | 95% 区间 (s) | 判定 |
| --- | ---: | ---: | ---: | --- | --- |
| 20k | 5.383 | 6.103 | +0.720 | [-1.605, 3.045] | 待定 |
| 100k | 13.580 | 13.693 | +0.113 | [-0.855, 1.082] | 待定 |

100k 区间跨零。本机结果作为成本参考，Xeon 的扩大条件继续按原协议判断。
候选保留为诊断证据，正式入口、正式版本和交付包保持原身份。

100M 与 1B 阶段成绩继续只认对应规模的非重复、事先未知请求完整程序实测。
