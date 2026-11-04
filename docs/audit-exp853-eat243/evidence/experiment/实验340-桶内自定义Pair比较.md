# 实验340 桶内自定义 Pair 比较

2026-10-17。起点 4162627，基线为 exp335/exp334 `estimate`。exp336 的热点中
`std::pair` 构造占 `SearchQueue::push` 的主要源码行样本；本轮只把桶内
`std::pair<int,uint32_t>` 换成带 `first/second` 字段和显式字典序比较的本地
`Pair`，保持桶、位图、四叉堆、搜索参数、模型、cache0、输出顺序和所有数值逻辑。

## 假设

自定义 `Pair` 的 `<` 与 `>` 实现 `(id,g)` 的 C++ `std::pair` 字典序，能去掉
通用 pair 构造与一部分模板包装成本，同时保持所有堆操作的全序。

## 验证与停止

普通和 ASan/UBSan 队列夹具必须逐次保持完整三元组，随后复用搜索字段、路径、
exact、边界、CLI、特殊 CSV、诊断和写出失败审计。Xeon 核 3 串行，20k/100k
各预热一对并做三对 AB、BA、AB，比较 `pair-baseline` 的 user+sys 差，区间
包含 0.02 秒计时舍入。100k 区间上界小于 0 才扩展完整 1M；区间跨零则保留待定，
下界大于 0 则结束该实现。

100M 与 1B 仍须使用非重复、事先未知请求的完整程序实测，1M 和更小规模只用于
候选筛选、输出契约和资源检查。

## 复现

```sh
python3 validation/exp340_custom_pair.py self-check
python3 validation/exp340_custom_pair.py prepare
python3 validation/exp340_custom_pair.py audit
python3 validation/exp340_custom_pair.py run
python3 validation/exp340_custom_pair.py check
```

原始证据写入 `validation/results/exp340/`，私有源码和二进制写入 `build/exp340/`。
