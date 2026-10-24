# 实验342 桶内 Packed 键

2026-10-17。基线为当前 exp335/exp334 `estimate`。候选只把
`SearchQueue` 桶内的 `(int id, uint32_t group)` 改为一个 `uint64_t` 全序键：
高 32 位保存经过符号序映射的 `id`，低 32 位保存 `group`。解码恢复原字段，
桶内堆操作仍使用同一字典序。大键四叉堆、搜索预算、模型、批次、cache0 和
输出顺序保持。

## 假设与验证

Packed 键减少桶内堆元素的构造、成员访问和比较开销，同时保持
`(id, group)` 的严格全序。普通和 ASan/UBSan 队列夹具、搜索字段、路径、
exact、边界、CLI、特殊 CSV、诊断和写出失败输入必须通过。

Xeon 核 3 单线程。20k/100k 非重复输入各做一组预热和三组交错配对
AB、BA、AB，计时区间包含 0.02 秒舍入。100k 区间上界小于 0 才扩展完整
1M；区间跨零或下界大于 0 时停止。

完整非重复 100M 和 1B 才是阶段有效成绩，1M 只用于候选筛选、输出契约和
资源检查。请求结果缓存关闭。

## 复现

```sh
python3 validation/exp342_packed_pair.py self-check
python3 validation/exp342_packed_pair.py prepare
python3 validation/exp342_packed_pair.py audit
python3 validation/exp342_packed_pair.py run
python3 validation/exp342_packed_pair.py check
python3 validation/exp342_packed_pair.py full
python3 validation/exp342_packed_pair.py check-full
```

原始证据写入 `validation/results/exp342/`，私有源码和二进制写入
`build/exp342/`。
