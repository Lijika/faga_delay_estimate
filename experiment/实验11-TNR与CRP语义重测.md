# 实验11 TNR 与 CRP 语义重测（Material Passport）

## 0. 标识与目的

日期 2026-09-17，基线提交 0ed9f8c，工作树在本轮只有 `tests/plan_probe.cpp` 被修改。
目的：把实验2 §6.3（CRP/MLD）与 §6.6（TNR/Hub Labeling）中标为失效的探针结论，
用真实几何语义重测，并把结果与旧失效说明分开记录。旧日志（实验2 的两处失效横幅、
实验3 的修正记录）本轮一字未改，继续作为历史。

## 1. 材料清单（passport）

| 材料 | 身份 |
|---|---|
| 架构 | doc/eda比赛文件/arch（5 个 JSON，未改动） |
| 探针源码 | tests/plan_probe.cpp `a225d04433d406c001267029ae5941bbb908633397b889cde976f3f66ec6c234` |
| 生产依赖（未改） | src/architecture.h `816818df…`、src/architecture.cpp `c764afc7…`、src/router.h `387ff924…`、src/router.cpp `a75562ca…`、src/residue_estimator.h `0b49c760…`、src/residue_estimator.cpp `013788cf…` |
| 提交二进制（未重建） | estimate `45b592f2edb87165f42fa9c1d13a4de13221ad5107f00e67ba256aeb6ab9b9ee` |
| 探针二进制 | build/plan_probe_exp11 `f4c98ee80467c7ac3cbf347d5c0ca8b3656a373b224e299ed6bbb350dde0649a` |
| 输出证据 | validation/results/exp11-{self-check,crp,tnr}.txt 与对应 .time.txt |

编译命令（本轮唯一构建方式，未跑 scripts/build.sh）：

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -o build/plan_probe_exp11 \
    tests/plan_probe.cpp src/architecture.cpp src/router.cpp src/residue_estimator.cpp
```

## 2. 运行与退出码

| 模式 | 命令 | exit | wall | user | sys | RSS | 输出 sha256 |
|---|---|---:|---:|---:|---:|---:|---|
| self-check | `./build/plan_probe_exp11 --arch doc/eda比赛文件/arch --self-check` | 0 | 1.28s | 1.35s | 0.05s | 47,188 KiB | `33f1cf5c2b7ae142706b989d727157b4973776bef5cfa252d83adace9d851256` |
| crp | `./build/plan_probe_exp11 --arch doc/eda比赛文件/arch --crp` | 0 | 44.40s | 44.79s | 0.07s | 84,496 KiB | `3f857de45ca94c419eb2f562b526c50fd9dfca00a50983e3f0b655bfb9296b8f` |
| tnr | `./build/plan_probe_exp11 --arch doc/eda比赛文件/arch --tnr --width 8 --height 8` | 0 | 0.27s | 0.22s | 0.04s | 47,148 KiB | `642512edfa4779e07d41021c0fd1c160179a95fd31f614d661d10f3a1a53b9c7` |

未出现超时，未降低样本量。

## 3. 本轮修正的语义

CRP 接口枚举与计费。入口是真实 `resolveNet` 落点在 cell 内、origin 在 cell 外的跳；
出口是 cell 内 Z lane 的跳落到 cell 外。接口 identity 现在是
`(landing x, landing y, landing I* port, 跳方向 dx/dy, Z lane)`：方向取 Net 模板位移符号，
lane 取承载跳的 Z 端口的 `[k]` 序号。入口 identity 与出口 identity 同形，因为一个 cell
的出口就是下一个 cell 的入口，只有 port、方向、lane 全一致才能组合。矩阵入口费用只算
入口 I* 的出 Arc，末跳只记 gap（含 Block 与 Line 费用），落点的 I*→Z* Arc 属于下一个
cell 的入口展开，不计入本矩阵。独立对照 `restrictedPortDijkstra` 是显式 496 端口图上的
普通 Dijkstra，按同一 cell 限制与同一方向/port/lane 出口 identity 判定，不复用矩阵的
Z 状态抽象。

TNR relay。共享函数现在同时给出两种有向候选：单 hub 的 `min_h d(s,h)+d(h,t)`
（反向 Dijkstra 给 d(v,h)，正向给 d(h,v)）和把同一 hub 集合同时当作两侧 access 集合的
TNR 表达式 `min_{a,b} d(s,a)+d(a,b)+d(b,t)`（d(a,b) 由 hub 正向表读取，hub 索引用
节点表映射，避免把 hub 序号当节点号）。两者都与窗口内精确 Dijkstra 逐对比较，
判定 via/equal/strict/under，并统计精确可达但 relay 覆盖不到的对数。

## 4. 结果

### 4.1 CRP（10×10 cell，两步对照）

| 项 | no-block cell(20,200) | block-skip cell(90,100) |
|---|---:|---:|
| 跨 cell 出/入接口 | 3,275,840 / 3,275,840（守恒） | 同左 |
| 名义 origin 计数 | 出 3,275,840 / 入 3,189,440（不守恒） | 同左 |
| 真实 entry / exit 接口 | 5,760 / 5,760 | 5,760 / 5,760 |
| 方向 / lane | 4 / 8 | 4 / 8 |
| Skip entry（实际位移 > 名义 span） | 0 | 1,440 |
| 采样矩阵 | 12×64，密度 100%，build 0.04s | 12×64，密度 100%，build 0.04s |
| 同约束对照（显式 port 图 Dijkstra） | **768/768 相等，mismatch 0** | **768/768 相等，mismatch 0** |
| 历史名义 origin 漏计 | 0 对 / 0 个 landing | **1,440 对 / 1,440 个 landing** |
| 全图比较（描述性） | equal 626，better 142，out-of-bound 0，local 有限而全图不可达 0 | equal 653，better 115，同样 0/0 |

结论：矩阵计费在相同约束下不重复、不漏计（768 个有限对全部等于独立对照），
名义 origin 规则会漏掉 Block skip 造成的 1,440 个 entry，真实枚举把例中的
`SRB_90_100/ILE[0]`（实际 origin `SRB_66_100`）找回。每 cell 平均 4,963 个跨 cell 接口，
与实验2/实验3 的记录一致。

### 4.2 TNR（8×8 window，20 对样本，同窗口/同样本/同向公式）

| hub 数 | via 有限 | equal | strict | under | unreachable | 精确可达但 relay 不可达 | 平均 relay/exact |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 12 | 0 | 12 | 0 | 8 | 0 | 2.251 |
| 8 | 12 | 0 | 12 | 0 | 8 | 0 | 2.136 |
| 12 | 12 | 0 | 12 | 0 | 8 | 0 | 2.069 |

窗口 10,240 节点 / 101,888 条边；单 hub 与 hub-pair 两种形式在这 20 对上取相同值；
hub 数增加时 relay 值单调不增（消融违反 0）。under=0 表示有向公式没有低于精确距离，
是本轮唯一能确认的正确性；equal=0 与平均 2.07 倍说明这组按出度取的 hub 集合没有落在
样本的最短路上，只是合格上界。这是该 hub 集合在该窗口上的描述性结果，不能推广成
TNR 不可行。

### 4.3 自检（新增回归）

新增并通过的检查：方向/lane 身份（每个 Z 端口都能解析出 [0,8) 的 lane、八个 lane 都存在、
接口方向为单轴、lane 是 key 的一部分）、两个 cell 的矩阵同约束对照（各 18/18 采样）、
skip entry 的存在性判别（block cell 有、no-block cell 无）、Block-skip 例子带方向/lane 命中、
hub-pair 形式包含单 hub 形式、hub 数消融单调性、有向 relay 不低于精确距离、
以及原有的不对称图反例与名义计数不守恒检查。总计 29 条 ok、0 条 FAIL。

## 5. 证据等级

定义：**A** 本轮直接实测且带独立对照；**B** 由本轮数据复算/交叉检查；**C** 未验证或外推。

| 主张 | 等级 | 依据 |
|---|---|---|
| CRP 矩阵在同约束下计费正确 | A | 两个 cell × 768 个有限对全部等于显式 port-graph Dijkstra |
| 名义 origin 枚举会漏 entry | A | 真实枚举与历史规则复算并行，block cell 漏 1,440 |
| 跨 cell 接口计数守恒 | A | 全数组真实枚举，出=入=3,275,840 |
| 有向 relay 不低于精确 | A | 20 对样本 × 3 个 hub 数，under=0 |
| hub 集合覆盖最短路 | C | equal=0、平均 2.07 倍，未实现 access mapping/transit matrix/locality filter |
| CRP/TNR 端到端加速 | C | 没有 overlay、组合查询、任何计时收益测量 |

## 6. 限制与未验证边界

1. cell 粒度 10×10 时每 cell 有 5,760 entry 与 5,760 exit，完整矩阵是 5,760²，
   本轮只对照 12×64 的采样；没有建立两级 overlay 或组合查询，也没有测端到端时间。
2. 只测了两个 cell（一个无 Block、一个有 Block skip）；未穷举全部 660 个 cell。
3. 全图比较里 local 矩阵值 ≥ 全图最优（equal/better），这是同约束与跨约束之比，
   不是加速证据；out-of-bound 与 local 有限/全图不可达都为 0。
4. TNR 只测 8×8 窗口与 20 对样本，8 对在窗口内不可达；hub 集合仅按出度取前 N，
   没有 access mapping、transit matrix、locality filter、hub-label cover，
   因此不能把结果当作完整 TNR 的可行性判定。
5. `--labels`、`--pdb`、`--periodic` 本轮未重跑；`--labels` 复用同一 relay 函数，
   语义已随共享实现更新，但没有本轮新证据。
6. 本轮不产生比赛分数或生产收益结论；`estimate` 默认、ResidueEstimator 与 Router
   生产逻辑均未修改，根二进制未重建。

## 7. 历史

实验2 §6.3 与 §6.6 的旧结论仍保留“本节结论已失效”横幅，实验3 的修正记录未改。
本轮把实验3 的修正再向前推进一步：接口 identity 加入方向与 lane、矩阵与对照都用同一
identity 匹配、CRP 增加第二个（Block skip）cell 并比较全部有限对、TNR 增加 hub-pair
形式与 4/8/12 消融，并为这些语义补了回归检查。
