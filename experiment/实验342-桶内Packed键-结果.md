# 实验342 桶内 Packed 键结果

日期：2026-10-17。候选把 `SearchQueue` 桶内的
`(int id, uint32_t group)` 存成一个保持同一全序的 `uint64_t`，解码后返回
原字段。基线为 exp334/exp335，结果缓存关闭。

## 验证

执行：

```text
python3 validation/exp342_packed_pair.py self-check
python3 validation/exp342_packed_pair.py prepare
python3 validation/exp342_packed_pair.py audit
python3 validation/exp342_packed_pair.py run
python3 validation/exp342_packed_pair.py check
```

普通和 ASan/UBSan 队列夹具、搜索字段 12,150 行、路径边 126,462 条、exact、
边界、CLI、特殊 CSV、诊断和写出失败审计均通过。候选 exact-output、
exact-role、exact-exp258、exact-fresh319 和 boundary 输出 SHA 分别为
`de99c7ad...3dd8a81`、`e7b73110...2f202a9822f`、`4bcc3778...d20d8a2bd8acd0`、
`3bf96141...6bfc2bb44342a3c` 和 `072c2547...4640fbf15b`，与基线一致。

本轮 CLI 检查范围为 `--help`；exp333 的显式 endpoint、exact、hybrid 消费者
组合没有在本轮重跑。

## AMD 非重复参考计时

2026-10-17 更正。`timing.json` 的 `lscpu` 记录为 AMD Ryzen 7 4800H；原稿的
Xeon 标注有误。下表保留原始 AMD 数值，Xeon 测量另存 `xeon/`，候选选型等待
远端证据。

AMD 核 3，单线程，20k/100k 各一组预热和三组交错配对：

| 数据 | 基线均值 CPU | 候选均值 CPU | 候选减基线 | 95% 区间 | 判定 |
|---|---:|---:|---:|---:|---|
| 非重复 20k | 5.470 s | 5.293 s | -0.177 s | [-1.476, 1.123] s | 不确定 |
| 非重复 100k | 13.820 s | 13.643 s | -0.177 s | [-1.764, 1.411] s | 不确定 |

100k 区间跨零。本机结果作为成本参考，Xeon 的扩大条件继续按原协议判断。
当前正式入口、交付包和正式版本保持原身份。

## 成本与范围

原始证据在 `validation/results/exp342/`，私有源码和二进制在 `build/exp342/`。
freeze 记录的开始可用空间为 423,710,588,928 字节，收尾为 423,686,713,344
字节，约减少 23 MiB。完整非重复 100M 和 1B 未测，本轮没有新的有效阶段成绩。
