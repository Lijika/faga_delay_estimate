# 实验145：C1 安全 residue 启发式离线审计

## 目标与假设

验证跳格修正是否能把 residue 查询变成真实图 Router 的可采纳启发式。固定候选为

```text
h_safe(s,t) = min_c [
  R_nominal(s,t; dx - 14c, dy)
  + line(actual endpoints)
  + 292 * |c|
]
```

其中 `R_nominal` 只计算名义 Gap-free 图的 Arc residue 值，`c` 同时改变查表槽位和
`a*dx+b*dy` 的位移项；`line(actual endpoints)` 使用原请求端点的强制 Line 下界。
`c=0` 与当前 `-endpoint-mode off -residual off` 的 pure residue 语义对齐。`c` 是有符号
的水平跳格次数，14 是可穿越 Block 的宽度，292 是单次跨越费。

本轮只检验已有 exact 标签上的下界性质和公式语义，不修改 `./estimate`、Router 或正式交付包。
候选使用向下取整的整数值，避免 `llround` 把下界抬高；同时记录生产四舍五入值用于诊断。

## 固定数据与比较

- 架构：`doc/eda比赛文件/arch`，身份来自当前工作树。
- 见证：`validation/results/real-bound-witnesses.csv`，逐条重放检查。
- 开发集：`validation/results/exp127-development-rows.csv`，12,357 条旧请求，`exact` 列为已核验标签。
- 对照：当前 `ResidueEstimator` 的 mult1 和 mult2 pure residue；不读 golden，不引入新标签。
- `c` 搜索从 `0` 向两侧扩展，默认最大 `|c|=32`；若尾部理论下界已超过当前最优值则提前停止，
  否则记录为截断行，不把截断行宣称为安全。

## 检查与门槛

1. `c=0` 的离线复算与 `ResidueEstimator::estimate()` 逐行一致（排除同针脚、不可达和无有限象限的
   明确分支，并单独计数这些分支）。
2. 全部可复算见证行上，`h_safe <= exact`，且原有 12 条 `value > exact` 见证不再被
   `h_safe` 超过；若存在任何严格超界，停止 C1 安全启发式。
3. 12,357 条开发集上报告：可复算行数、截断行数、`h_safe > exact` 行数、最大超界、与 pure
   residue 的加权 gap、跳格候选命中率。该旧开发集结果只作选型证据，不外推隐藏集。
4. 对见证 `SRB_75_0/ZSEA[0] -> SRB_90_0/ISEA[0]` 和反向 `ZSWA[0]`，候选应分别不高于
   292 ps；只换 residue 槽位而不平移位移项的错误实现必须被自检捕获。
5. 资源记录构建和离线查询 CPU、wall、RSS；单线程。没有完整 1M 输出，不进入正式验收。

## 预注册判决

- 所有已复算行满足 `h_safe <= exact`，且搜索未截断：进入 exp146 的 Router A* 组件探针。
- 任意超界或大量截断：保留公式作为未证假设，转向商图 `L` 兜底或重新推导 `c` 的几何范围。
- 本轮不因下界成立宣称精度收益；只有后续 exact Router 扩张数和端到端 CPU 证据通过后才评估接入。

## 命令

```sh
python3 validation/exp145_safe_residue.py
```

原始报告写入 `validation/results/exp145-safe-residue.json`，临时二进制和中间文件写入
`build/exp145/`。

## 执行结果

协议和实现均在 `research/exp145-safe-residue-heuristic` 分支完成。编译命令为
`g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter`，离线探针最大 RSS
`606,992 KiB`，完整开发集运行 CPU `15.19 s`、wall `15.68 s`；28 条见证运行
CPU `15.41 s`、wall `14.98 s`，单进程单线程。

12,357 条开发请求中有 12,146 条可复算且 exact 非负，mult1/mult2 均无 fallback、
无截断。`c=0` 结果与当前 `ResidueEstimator::estimate()` 逐行一致；`h_safe > exact`
为 `0`，最大超界为 `0`。mult1 有 3 行、mult2 有 2 行选择非零 `c`，加权 gap
变化很小，证明本候选主要修复极少数跳格行，不改变普通行。

28 条审计见证全部可复算且搜索完整。mult1/mult2 均为 `0` 行 `h_safe > exact`；
12 条原先 `value > exact` 的跳格见证都选择非零 `c`，其中
`ZSEA[0]` 正向行从 `327` 降到 `292`，`ZSWA[0]` 反向行从 `337` 降到 `292`。
这两行同时验证了必须平移象限的位移项，单独修改 residue 槽位会得到错误的 `467` 级别候选。

本轮只复用旧开发标签和已保存的真实路径证书，不读取 golden、不修改 `./estimate`，
不测 Router 扩张数和端到端 CPU。离线门通过后，下一轮再实现 test-only BoundProvider，
验证一致性、重开/安全终止和 exact Router 答案。

构建身份另行记录：本轮执行 `sh scripts/build.sh` 生成的当前源码动态开发文件为
`66,112,088 B`、SHA `ea163e4febf8a38b4ff3b8523e885729a72eb7c7dbffaec46a1bc388b601f83d`。
该文件只用于本轮源码复核，不能替代正式静态交付；收尾已将根 `./estimate` 恢复为
exp131 不可变包副本，SHA `aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c`，
`build/submission/estimate` 与版本目录保持同一身份。
