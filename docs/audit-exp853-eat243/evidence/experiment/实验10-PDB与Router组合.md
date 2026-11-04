# 实验10 全图共享 PDB 与 Router/ALT 的组合比较

日期 2026-09-17，基线 a00e886（实验9 已提交）。本轮目标：把经过审计的 PDB 下界
以可选接口接进 Router 的 A*，在真实架构图上比较 plain、ALT、PDB、ALT+PDB 四配置，
并在有收益时也不改变默认提交路径。

结论：PDB 作为额外可采纳界时答案与 plain 逐行一致；176 条样本上展开数
default（span+ALT）556,570 -> default+PDB 24,912（22 倍），且没有任何一行变差；
PDB 界逐状态支配 span 与 ALT，PDB 单用时 ALT 仍有增益。默认路径保持不动。

## 接入方式（最小可选接口）

Router 增加 `Router::BoundProvider`（虚接口，`bool bound(sx,sy,sp,tx,ty,tp,value)`）与
`Options::boundProvider`（默认 nullptr）。`heuristic()` 把外部界作为 `max` 的一项；
provider 返回 false 表示该对未知（无穷抽象状态或 48 个入度为 0 的 target），此时忽略，
绝不当作 0。外部界只允许与二叉堆组合：radix 堆需要单调键序，而外部界只证明了可采纳。
正确性依据是可采纳 + 允许重开（Router 已有 dist_ 更新与陈旧项跳过），因此不要求一致性；
一致性没有证明，所以 PDB 配置一律不使用 radix 堆。默认路径的代码分支只在指针非空时执行，
提交行为不变。

## 样本与建表

32 条 `validation/results/endpoint-holdout-requests.csv`，加实验7 的 144 条
（28 条 exp4 见证 + 67 条 exp5 规则 + 49 条按同一规则生成的 terminal 样本），共 176 条；
输入计数在探针里固定校验（32/28/67/49）。PDB 为被请求的 97 个 target 加 1 个自检 target 建表：
93,327,360 B、5.72s、98 张表。

## 消融结果

六个配置、同一组 176 条样本、答案全部精确（查询缓存关闭）：

| 配置 | 展开总数 | 每样本均值 | 相对 plain | 答案不一致 | 初始界>exact | PDB 调用 | 建表 | 查询 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| plain | 9,694,712 | 55,083.6 | 1.000 | 0 | 0/132 | 0 | 0.06s | 4.08s |
| alt（8 地标） | 691,341 | 3,928.1 | 0.071 | 0 | 0/132 | 0 | 42.38s | 0.39s |
| default（span+ALT） | 556,570 | 3,162.3 | 0.057 | 0 | 0/132 | 0 | 41.16s | 0.33s |
| pdb | 157,417 | 894.4 | 0.016 | 0 | 0/132 | 788,379 | 0.04s | 0.15s |
| alt+pdb | 24,912 | 141.5 | 0.003 | 0 | 0/132 | 224,741 | 44.40s | 0.04s |
| default+pdb | 24,912 | 141.5 | 0.003 | 0 | 0/132 | 224,741 | 45.71s | 0.03s |

逐项消融的读法：

1. plain 到 ALT：8 个地标把展开数压到 7.1%。
2. ALT 到 PDB 单用：PDB 比 ALT 界更紧，展开数再降到 ALT 的 22.7%。
3. PDB 单用到 ALT+PDB：ALT 在 PDB 之上仍有价值，展开数再降 6.3 倍（894 -> 141）。
4. default（span+ALT）到 default+PDB：22 倍；**84 条严格减少、92 条持平、0 条变差**。
5. `alt+pdb` 与 `default+pdb` 在 176/176 条样本上展开数完全相同：这批样本里 PDB 界逐状态
   支配 span 与 ALT，`max` 由 PDB 决定，span 项不再起作用（若要启用，PDB+ALT 即可）。

长尾样例（exact 915，SRB_110_40/ZDN[5] -> SRB_94_32/A_BD）：
default 68,451 次展开 -> default+PDB 77 次（pdb 单用 78，alt 单用 89,393）。

## 下界质量

175 条可比较样本（1 条不可达）上，用源状态直接查询 PDB：

| 指标 | PDB | 线性界 |
|---|---:|---:|
| 可比较样本 | 175 | 175 |
| 等于 exact | 102（58.3%） | — |
| 平均 gap（exact - L） | 38.1 | 159.2 |
| L > exact | 0 | 0 |
| provider 未知对 | 0 | — |

自检里 48 个入度为 0 的 target 之一 `A_AY` 被显式拒绝（返回 false，值未写入）。
热批量基准：1,000,125 次调用、wall 0.0580s、CPU 0.0622s，62.2 ns/call，checksum=291047805。

## 正确性与回归

- 六个配置的答案与 plain Dijkstra 逐行一致：0 不一致（探针把任何不一致计入 exit）。
- 自检：审计 reduced 检查 33,728 次、min_reduced=0、negative=0；篡改势函数得 -1；
  入度 0 target 拒绝；输入计数与 176 行固定校验通过。
- 用改动后的 Router 重建 `tests/router_terminal_probe.cpp` 并运行 144 例：exit 0，
  span-only / alt-only / span+alt 三个配置 answer_mismatch=0、initial_bound_gt_exact=0，
  ALT 近场诊断 24 条 0 反例，9 条回归 0 失败。
- 用改动后的 Router 重建 `tests/verify_internal.cpp` 并运行 `--quick`：八条公开路径全部通过
  （973/843/786/997/929/562/692/661），ALL CHECKS PASSED。
- 根提交二进制 `estimate` 未重建：sha256 仍是
  45b592f2edb87165f42fa9c1d13a4de13221ad5107f00e67ba256aeb6ab9b9ee。

## 代价

| 项目 | 数值 |
|---|---:|
| 每 target 表 | 952,320 B |
| 本批 98 个 target | 93,327,360 B（89.0 MiB），建表 5.72s |
| 448 个可用 target 全建 | 约 450 MiB，约 26s |
| provider 单次调用 | 62.2 ns（热重复访问，缓存命中率未测） |
| 组合配置总调用 | 224,741 次（约 14 ms） |
| 探针峰值 RSS | 425,824 KiB（含 4 次 8 地标表，每次约 170 MB） |

## 适用条件与限制

1. 只作为可采纳的 A* 界；未证明一致性，因此不能与 radix 堆组合（代码里直接抛错）。
2. 48 个入度为 0 的 target（`A_*`/`S_*` 的 Q0/Q1/Y 端口）必须显式回退；本批 176 条样本
   0 条命中它们，1M 请求文件同样是 0 条。
3. PDB 表按 target 建表，按需缓存，上界是 496 个端口；启用前必须准备请求用到的 target。
4. 收益体现在展开数与单查询时间；公开 1M 负载由查询缓存主导（实验8 实测 9,000,000 次命中），
   因此本结果不能直接换算成公开评分，代表的是 unique/精确流。
5. 本批样本 176 条、单机单核；未测 10M/1G 重复请求，未测多线程。

## 复现命令与文件身份

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/pdb_router_probe \
    tests/pdb_router_probe.cpp src/architecture.cpp src/router.cpp
./build/pdb_router_probe --arch doc/eda比赛文件/arch --self-check
timeout 1500s /usr/bin/time -f "RSS=%MKiB user=%U sys=%S wall=%e" \
    -o validation/results/pdb-router-probe.time.txt \
    ./build/pdb_router_probe --arch doc/eda比赛文件/arch \
    --json validation/results/pdb-router-probe.json \
    --csv validation/results/pdb-router-samples.csv \
    > validation/results/pdb-router-probe.stdout.txt 2>&1
```

正式运行：exit 0，RSS 425,824 KiB，user 197.36s，sys 2.11s，wall 200.28s。

SHA256：`src/router.h` 387ff92445dc43437f41a68289183388cca6c748d4ff9fb3ddbf32cf8e77936e；
`src/router.cpp` a75562ca2098c8ecf3cad14846dbf327799a55948ab181d95be2f2d8fc19de46；
`tests/pdb_router_probe.cpp` 075683f697e95481b566a25de1da313eb42c7e536aacacde1f00faa93b85bd2f；
`build/pdb_router_probe` 80497e3ef0c6bfda571e633d36d982f487ce5d104e9fa6a96a89c7afd3cbe233；
`validation/results/pdb-router-probe.json` e00b4a8cec388e247155d7c2e43894e48ec078ebc1c74b8b00d8c78a3ae4ce07；
`validation/results/pdb-router-samples.csv` d45eadf6c7eb507dcabe229405a9e60d3665111b2f4cc28f03dc98889b69417f。

## 结论

PDB 与 Router/ALT 的组合带来可测且方向一致的收益（本批样本 0 行变差，长尾展开数下降两个数量级），
答案逐行不变。是否在提交路径启用由协调者决定；本轮不改变默认，接口保持可选。
