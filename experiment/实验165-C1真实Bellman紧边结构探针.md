# 实验165 C1 真实Bellman紧边结构探针

2026-10-10，Asia/Shanghai。分支`research/exp165-tight-edge-structure`，
起点`1855582`，开工`/dev/sdd`可用454G，正式exp131保持。

## 固定假设与范围

当前具体safe Provider已经通过一致性资格审计，sigma定义为
`w+h(child)-h(parent)`。固定exp161 helper、radix与唯一I*消元，
只在私有Router的已展开真实折叠边上统计sigma，任何负值立即失败。
对全部扫描的successor计数，包含被best或已有dist剪掉的边。
额外h调用会填充dense bound缓存，query CPU只记探针成本。

范围是exp161固定0.10族262行，每行一次，保留六条terminal边界检查。
报告零边占比、存在/单个/同端口/全部tight successor的状态占比、
最大tight出度、原边最小费用及六档slack直方图。
每行answer与冻结expanded/relaxed必须相同。
共享pure/tail源码保持，复用exp161全域等价证据。

同端口tight状态的1M distinct加权占比≥5%时，
继续研究同端口宏转移的退出证书；低于5%停止扩大该窄构造。
这个门只决定研究优先级，宏转移精确性、CPU与acc收益各自另验。
所有tight退出、位移和prefix条件仍待Astra两题答复及独立核对。
理论与诊断边界见Obsidian `固定目标Bellman余量的结构诊断`。

## 固定命令与停止条件

CPU3、同机串行、单线程，一次运行≤300秒、RSS≤2,000,000,000 B。
编译警告、exact/轨迹/直方图差异或负sigma均停止并保留现场。
产物`build/exp165/`与`validation/results/exp165-*`拒绝覆盖。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp165_tight_edge_structure.py freeze
# 提交冻结后运行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp165_tight_edge_structure.py run
```

本轮只测结构与资源。未参与选择的新请求、静态ELF、生产接入、
完整1M与平台1B保持未验证。
