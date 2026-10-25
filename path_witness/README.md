# exp705 逐条路径见证

这里提供全部 239,616 条查询、5,558,667 个 Net 字、逐条分解和 958,464 次交叉重放。查询按 59,904 个完整端口对排列，每对有四个实际位置。二进制以 gzip 保存，解压后的名字、大小和 SHA 与历史 `build/exp705/` 一致。

**这些路径求解的是 D0**。五份图描述中只有 Line 的费用被置零，真实 SRB 存在性、边界、Block 跳越和 Block 费用均保留。带全部 Line 费用的逐条精度标签与原求解器见 [accuracy](../accuracy/README.md)。

## 读取和复现

以下命令从仓库根目录执行，工作目录须由调用者选择。Python 部分需要 NumPy，构建需要 Linux x86-64、GCC 和静态 C++ 运行库。

```sh
python3 path_witness/unpack.py /tmp/witness-data
python3 path_witness/generate_queries.py /tmp/witness-data
python3 path_witness/replay.py /tmp/witness-data
sh path_witness/build.sh
path_witness/build/trace \
  path_witness/solver/no-line-arch \
  /tmp/witness-data/data/queries.bin \
  /tmp/witness-data/data/known.i32 \
  /tmp/witness-data/query_source/orbit.i16 \
  /tmp/witness-data/recomputed
```

`unpack.py` 检查全部归档文件身份。`generate_queries.py` 从原始百万行查询和 D0 分解重新选择锚点并生成四位置查询。`replay.py` 逐元素比较全部交叉记录，并核对原分组统计。查询生成与重放程序沿用原语句，只调整了文件位置和归档校验。

本轮已完整重跑上述查询生成、全部精确路径求解及交叉重放。三份重新求解的路径文件与原文件 SHA 全部相同，见 [精确求解核验](verification.json)和[交叉重放核验](replay-verification.json)。原始脚本、未改动的 tracer、冻结记录和字典位于 `original/`，可对照移植后的入口。

## 二进制结构

全部多字节整数使用 little-endian，数组按 C 行序存放。索引均从 0 开始。

| 解压后的文件 | 类型与形状 | 含义 |
| --- | --- | --- |
| `queries.bin` | 12 字节头，加 `(239616,10)` 个 int32 | magic 为 `EX535Q01`，随后 uint32 行数。十列依次为 `sx,sy,tx,ty,sf,sl,tf,tl,sp,tp` |
| `known.i32` | `(239616,)` int32 | 每组 slot 0 的已有 D0 标签，其余为求解前占位值 `-2` |
| `anchors.u32` | `(59904,)` uint32 | 每个端口对在原百万行查询中的锚点行号 |
| `delta.i32` | `(59904,2)` int32 | 首 Net 对齐后的有符号名义位移 |
| `paths.lengths.u32` | `(239616,)` uint32 | 每条路径包含的 Net 数 |
| `paths.words.u8` | `(5558667,)` uint8 | 变长路径字串的顺序拼接 |
| `paths.summary.i32` | `(239616,8)` int32 | 下表列出的路径分解 |
| `normalized.i32` | `(59904,4)` int32 | D0 减去源端首 Net 的 Block 费用 |
| `cross.i32` | `(59904,16,7)` int32 | 固定端口对内，源字串在目标位置的重放结果 |

`sp,tp` 是 `SRB_Port.json` 中的原始端口序号，`sf,tf` 是映射中的族号，`sl,tl` 是族内 lane。完整映射位于 [mapping.json](query_source/mapping.json)。来源与目标顺序均按该文件；目标域包含 160 个 Z 端口和 128 个 LOGIC 输出端口。

读取第 `i` 条路径时，令 `offsets = [0] + cumsum(lengths)`，取 `words[offsets[i]:offsets[i+1]]`。每个字是 0 到 159 的代码，字典为 [trace.json](original/trace.json) 的 `z_ports` 和 `z_names`。字表示这一跳的 Net 源端口；从当前端口进入它的 Arc 及最后一段终止 Arc 由图补齐。

| summary 列 | 名称 | 定义 |
| --- | --- | --- |
| 0 | `arc_cost` | 起始、内部及终止 Arc 费用之和 |
| 1 | `line_cost` | 本实验恒为 0 |
| 2 | `block_cost` | 所有真实 Net 边扣除 Line 后的费用之和 |
| 3 | `nominal_dx_sum` | Net 模板的 dx 之和 |
| 4 | `nominal_dy_sum` | Net 模板的 dy 之和 |
| 5 | `net_hops` | 等于对应 length |
| 6 | `block_jump_hops` | 实际横向位移与模板 dx 不同的跳数 |
| 7 | `extra_dx_sum` | 实际横向位移减模板 dx 的总和 |

逐条成立 `D0 = col0 + col1 + col2`、`tx-sx = col3 + col7`、`ty-sy = col4`。这只是保存的具体路径的守恒关系。

## 交叉重放

第二维编号为 `source_slot*4 + target_slot`。七列依次是 `reason, first_invalid_step, final_x, final_y, cost, cost_minus_target_D0, uphill`。`uphill=1` 表示源位置的 normalized D0 小于目标位置的 normalized D0。

| reason | 含义 |
| --- | --- |
| 0 | 路径合法、落在目标坐标及目标端口，扣除目标首 Net 费用后仍等于源 normalized 值 |
| 1 | 某一跳离开芯片范围 |
| 2 | 某一跳落在芯片范围内的缺失 SRB |
| 3 | 全部跳可执行，但最终坐标发生变化 |
| 4 | 路径合法且终点正确，扣除目标首 Net 费用后的总费用发生变化 |

`first_invalid_step` 是首次非法 Net 的零基序号，合法遍历时为 `-1`。reason 1、2 的坐标是最后一次成功落点，cost 是已成功部分的费用。reason 3 的 cost 也不能当成通向原目标的合法路径费用。只有 reason 0、4 可以用 `cost_minus_target_D0` 解释目标路径次优差；reason 0 也可能次优。

## 平局选词与结论范围

固定实现使用 radix heap。`relax` 仅在 `g < dist[state]` 时更新父指针；同距离到达保留先前父指针。终点费用也只在严格降低时更换，搜索遇到 `f >= best` 时终止。相同 key 在 bucket 0 中采用 `back()/pop_back()`，上层 bucket 按现有容器顺序搬移；种子与后继按冻结端口表顺序遍历。相关实现见 [router.cpp](solver/src/router.cpp)和[router.h](solver/src/router.h)。

因此字串由图顺序、队列顺序和严格更新共同确定。它没有附加最少跳数、字典序最小、跨位置最稳定等选词目标。同成本的另一条最短路可能有不同的重放表现。当前重放证据排除了保存字串在指定位置上的若干可迁移形式；关于全部最短路是否共享某个小状态，仍需额外论证。

位置生成种子为 `20261025705`。先冻结坐标，再读取标签；每组保留原锚点及三个不同位置，实际 proposal 循环 60 次。数据属于同架构、已观察的研究诊断，没有独立泛化声明。
