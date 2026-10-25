# exp688 逐条精度材料

[exp688-exact-subset.csv.gz](exp688-exact-subset.csv.gz) 包含 479,232 条逐条记录，覆盖全部 59,904 个角色端口对。每对从已有 64 条 exact 样本中独立抽 8 条，种子为 `202610250688`，选择在读取标签和预测值之前完成。

这批 prediction 来自 CPU 为 243.302538 秒的原完整 1B 运行。生成材料时没有重跑估计程序。完整 3,833,856 条记录重新对齐后，加权 Acc 为 98.65806165706269%，与原报告一致；发布子集为 98.6590479790631%。子集只是另一份较小的估计，完整样本仍是 exp688 的主要精度证据。

## 字段与权重

| 字段 | 含义 |
| --- | --- |
| `sample_index` | 原 3,833,856 条 exact 文件中的零基行号 |
| `input_row` | 原 1B 请求中的零基数据行号，不计表头 |
| `pair_id` | `source_index*288 + target_index` |
| `rank_within_original_64` | 同 pair 在原 exact 样本中的出现序号 |
| `From,To` | 原始完整端点，包括 SRB 坐标、完整端口名和 lane |
| `exact_delay` | 原 exp203 exact 求解器对完整真实图求得的延迟，单位 ps |
| `exp688_prediction` | 同次完整 1B 输出的整数预测 |
| `population_pair_rows` | 该 pair 在原 1B 中的实际请求数 `N_pair` |
| `sample_weight` | 子集权重 `N_pair/8` |
| `original_sample_weight` | 原 64 条样本的权重 `N_pair/64` |
| `split` | 固定为 `historical_1b_reviewed` |
| `source_pin_seen_in_training` | 完整源 pin 是否出现在 exp501 的百万行训练请求中 |

端口对顺序见 [mapping.json](../path_witness/query_source/mapping.json)。`From` 中 `/` 前是坐标，后面保留端口原文。LOGIC 名称中的 Q0、Q1 等仍完整保存，解析时应使用映射表中的族和 lane 定义。

原 64 条是每个 pair 内的无放回随机样本，子集再做独立的无放回抽样。因此权重总和为 1,000,000,000。按项目评分函数先算逐条分数，再按权重求均值。

```text
score_i = 100 * (1 - tanh(4 * abs(pred_i - exact_i) / exact_i))
Acc = sum(weight_i * score_i) / sum(weight_i)
```

项目评估器在 `exact=0` 时，将 `pred=0` 记为 100，其余记为 0。MAE、完全命中率及上述 Acc 应分别计算。配对比较应使用同一组行和同一权重，对每行的 score 差做统计。若只分析某个条件群，总体 Acc 损失贡献的分母仍应保留全部权重。

本批有 37,264 条源 pin 曾出现在训练请求中，其余源 pin 未出现。整批 1B 已被历史研究观察，`source_pin_seen_in_training=0` 仅说明源 pin 隔离，不能据此改标为新的盲测集。历史百万训练请求的 outer-fold 位于 [training](../training/README.md)，本批 1B 没有伪造 outer-fold 编号。

## 可复现操作

```sh
python3 accuracy/check_subset.py /tmp/accuracy-check.json
```

该检查会重建抽样选择，检查端点、pair、唯一性、权重和原始行号，重算加权 Acc 与分层标准误。已执行的结果见 [verification.json](verification.json)。

原始大文件仍在历史工作区。重新导出子集使用以下接口，完整输入身份和原路径在 [subset-manifest.json](subset-manifest.json) 中。

```sh
python3 accuracy/make_subset.py \
  HISTORICAL_EXACT_DIRECTORY \
  EXP688_1B_SAMPLE_CSV \
  EXP501_TRAINING_REQUESTS_CSV \
  NEW_OUTPUT_DIRECTORY
```

这里发布代表性子集。完整 1B 输入、40 GB 输出和全部 3,833,856 条文本标签没有重复放入 Git。

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

本轮重建 ELF 的 SHA 为 `3ba200cacb1f0e93485599fe0f02ddb06e4efbdf25befc9bbcba4fad7712a8d4`，与生成 exp683 标签的求解器逐字节相同。随后复算了覆盖 208 个源端口和 288 个目标端口的 1,032 条标签，并检查 3 个边界例子；13 条同时经不使用该 residue provider 的参考搜索核对。见 [构建证据](exact-build-r9.json)和[逐条核验](solver-verification.json)。

用于 exp705 的 tracer 额外记录父指针，且输入图已将 Line 置零。两类 exact 的数据语义在目录中分别保存。
