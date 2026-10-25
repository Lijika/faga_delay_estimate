# exp728 逐条精度材料

本目录提供全部 **3,833,856 条**分层 exact 记录，以及同一请求上的 exp688、exp728 整数预测。两个 NPZ 分片各有 1,916,928 行，按原 exact 行序连接。另提供 [exp728-exact-subset.csv.gz](exp728-exact-subset.csv.gz)，包含 479,232 行完整文本端点，供直接阅读和较小规模分析。

预测来自已有完整 1B 输出。exp728 与 exp722、exp725 的完整输出 SHA 相同，因此复用 exp722 留存的逐条样本，并用最终输出身份关联当前 CPU。来源及每份文件 SHA 见 [records-manifest.json](records-manifest.json)。本轮新增完整估计程序运行和 exact 求解次数均为零。

## 数据字段

| 文件或字段 | 含义 |
| --- | --- |
| `exact-records-00.npz`、`exact-records-01.npz` | 全量标签与配对预测，NPZ 内各数组等长 |
| `record-mapping.json` | 全部 496 个完整端口名、208/288 角色顺序、59,904 个实际人口数 |
| `endpoints` | 六列 uint16，`source_x,source_y,source_port_id,target_x,target_y,target_port_id` |
| `input_row` | 原完整 1B 输入的零基数据行号，不计表头 |
| `pair_id` | `source_role_index*288 + target_role_index` |
| `rank` | 同 pair 在原 64 条 exact 样本中的出现序号，0…63 |
| `exact_delay` | 完整真实图 exact，int32，单位 ps |
| `exp688_prediction`、`exp728_prediction` | 同请求的两版整数输出，int32 |
| `source_pin_seen_in_training` | 完整源 pin 是否在 exp501 百万训练请求中出现 |

全量样本的 `sample_index` 是分片内行号加 manifest 中的 `start_index`。从 `endpoints` 及映射可以无损还原 `SRB_x_y/完整端口名`，包括全部 lane。每条全量记录的权重为 `population_pair_rows[pair_id]/64`，权重之和为 1B。

全量记录统一属于 `historical_1b_reviewed`。其中 299,391 行的完整源 pin 曾出现在训练集中。源 pin 未出现的行也已被历史研究观察，不能据此改标为新盲测。训练集的 outer-fold 在 `training/data/targets_splits.npz`，本批验证记录没有伪造 outer-fold。

CSV 子集继续使用旧 seed `202610250688`，每 pair 从原 64 条中选八条，选择先于读取预测和标签。字段保留 `From,To`、两版预测、exact、原行号、pair/rank、人口、`N_pair/8` 子集权重、`N_pair/64` 原始权重、split 和训练 source-pin 标记。旧 CSV 的全部字段已逐行比较相同，见 [exp688-replacement-check.json](exp688-replacement-check.json)，因此移除了旧的 exp688-only CSV。

## 评分与检查

| 样本 | exp688 Acc% | exp728 Acc% |
| --- | --- | --- |
| 全部 3,833,856 条 | 98.658061657 | 98.644899649 |
| 479,232 条代表性子集 | 98.659047979 | 98.646600910 |

全量样本是主要精度证据。配对变化行数为 1,295,611。每条先计算评分，再以人口权重求均值；不能把 MAE 当成最终评分。

```text
point_i = 100 * (1 - tanh(4 * abs(pred_i - exact_i) / exact_i))
Acc = sum(weight_i * point_i) / sum(weight_i)
```

项目约定在 exact=0 时，同为零得 100，其余得零；当前全量样本没有零真值。分组损失贡献使用总体权重为分母，各分组维度之间可能重叠。

```sh
python3 accuracy/check_records.py /tmp/exp728-records-check.json
python3 accuracy/loss_budget.py /tmp/exp728-loss-budget.json
```

本轮检查了全部数据的 SHA、原行顺序、请求唯一性、实际 SRB、完整端口及 pair、64 条分层覆盖、训练 pin 标记、权重、两版 Acc 和 CSV 与 NPZ 的逐条对应。见 [records-verification.json](records-verification.json)。[loss-budget.json](loss-budget.json) 从已有完整评分报告分解损失，无需再次运行 estimate。

NumPy 2.2.6 可复现导出。读取示例为

```python
import json
import numpy as np

mapping = json.load(open("accuracy/record-mapping.json"))
with np.load("accuracy/exact-records-00.npz", allow_pickle=False) as data:
    sx, sy, sp, tx, ty, tp = map(int, data["endpoints"][0])
    source = f"SRB_{sx}_{sy}/{mapping['ports'][sp]}"
    target = f"SRB_{tx}_{ty}/{mapping['ports'][tp]}"
    weight = mapping["population_pair_rows"][int(data["pair_id"][0])] / 64
```

重新从原大文件导出使用

```sh
python3 accuracy/export_records.py   HISTORICAL_EXACT_DIRECTORY EXP688_1B_SAMPLE_CSV EXP722_SAME_OUTPUT_SAMPLE_CSV   EXP501_TRAINING_REQUESTS_CSV source/arch/SRB_Port.json NEW_OUTPUT_DIRECTORY
```

`make_subset.py` 保留原抽样实现，本轮导出和检查共同复用其 selection、权重常数及评分函数。全量 1B 请求和 40 GB 输出留在研究环境，Git 中保存复现协议和身份。

## 原精确求解器


[build_exact.py](build_exact.py) 从冻结 exp158/203 源码重建原标签求解器。公共图代码复用 `path_witness/solver/`，三个与 tracer 不同的原文件保存在 `exact_original/`。构建会检查 exp203 的原始文件身份。

```sh
python3 path_witness/unpack.py /tmp/exact-data
python3 accuracy/build_exact.py /tmp/exact-build
/tmp/exact-build/build/exp203/exact_labels \
  source/arch accuracy/solver-check-input.csv \
  /tmp/exact-data/query_source/orbit.i16 \
  /tmp/exact-labels.csv
```

离线求解器的查询 CSV 使用下面五列，端点保留完整原文。`label=-2` 表示待求标签，`span_checked=1` 会额外调用不使用 residue provider 的参考搜索；给定已有 label 时检查求解结果与它完全一致。

```csv
kind,from,to,label,span_checked
new,SRB_20_100/IDE[0],SRB_20_100/A_A3,-2,1
```

输出为 `index,from,to,exact,expanded,relaxed,cpu_s`，输入行序保持。原工具的输出路径会由调用者指定，使用新的路径以保留已有结果。

字节复现环境为 r9 的 GCC 11.4.0、Ubuntu 22.04 运行库。该离线工具按历史命令动态链接；比赛交付的静态链接要求适用于 `source/` 中的 estimate。

exp688 补充材料发布时重建的 ELF SHA 为 `3ba200cacb1f0e93485599fe0f02ddb06e4efbdf25befc9bbcba4fad7712a8d4`，与生成 exp683 标签的求解器逐字节相同。随后复算了覆盖 208 个源端口和 288 个目标端口的 1,032 条标签，并检查 3 个边界例子；13 条同时经不使用该 residue provider 的参考搜索核对。见 [构建证据](exact-build-r9.json)和[逐条核验](solver-verification.json)。

用于 exp705 的 tracer 额外记录父指针，且输入图已将 Line 置零。两类 exact 的数据语义在目录中分别保存。
