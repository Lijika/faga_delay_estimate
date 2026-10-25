# 请求域、生成与划分协议

本目录提供冻结请求生成器、可达性索引、100M 的历史排除集合、分层抽样入口及原始协议。所有已测规模、请求唯一性与源 pin 隔离分别记录。后续完整估计程序测试沿用非重复 100M、1B。

## 208×288 的证据范围

当前 U-role 生成器从 60,200 个实际 SRB 中独立均匀选择源位置和目标位置，再独立均匀选择源角色及目标角色。源角色包括 160 个 Z 端口和 48 个有出 Arc 的 LOGIC 端口，目标角色为 160 个 Z 端口和 128 个 LOGIC 输出端口。完整顺序见 [mapping.json](../path_witness/query_source/mapping.json)，实现见 `generator/scripts/hidden_suite.h` 的 `Domain`。

这一定义来自项目的生成与建模方案。仓库中的官方 V0.3 文档第 5.4 节说明每条请求包含一个 from pin 和一个 to pin，端口章节定义全部端口及其连接；已找到的文字没有把请求域明确收窄为上述 208×288。公开 golden 的 1,000,000 行均落在当前角色域内，实际出现 113 个源端口和 256 个目标端口，见 [公开样本检查](public-domain-audit.json)。它支持已测范围内的覆盖结论。

exp728 的生产入口先检查角色索引，域外请求保留默认 `answer=-1`。`prepare596` 内部同 pin 返回 0 的分支也受这项前置检查影响。图中存在当前角色域外的可达请求，例如 `SRB_20_100/IDE[0]` 到 `SRB_20_100/A_A3`，原 exact 工具已经复算，结果见 [solver-verification.json](../accuracy/solver-verification.json)。因此，如果官方允许这类端点，正式实现需要扩展支持。官方是否排除它们仍需赛事方明确；本次材料保持该问题开放。

## 冻结生成器

`generator/` 从已记录的 Git 提交 `26f0b04` 提取，逐文件 SHA 与历史 [toolchain-original.json](generator/toolchain-original.json) 一致。这里保存了原生成器、独立检查器、可达性索引生成代码及对应图代码，避免把工作区后来修改的脚本当成旧输入的来源。

生成过程使用 `std::mt19937_64` 和显式拒绝采样实现整数均匀分布。依次过滤同 pin、不可达请求和输入内重复的完整请求对；每个保留请求再生成两个 64 位洗牌 key，经 256 个桶排序，最终输出规范端点文字。位置与端口的提议独立，条件过滤后的分布随实际可达性变化，应使用实际 pair population 加权。

可达性检查使用冻结 SCC 索引 `reach.bin`，独立几何检查使用 `eligibility.bin`。压缩文件在 `data/`，解压后分别为 79,873,492 B 和 60,205,224 B。它们属于离线生成工具的输入。

```sh
python3 dataset_protocol/prepare.py /tmp/dataset-tools
```

该命令检查历史源码和两个索引的 SHA，编译生成器、检查器、可达性工具及分层抽样工具。本轮已编译并检查工具用法，结果见 [tools-verification.json](tools-verification.json)。

## 已有 1B

原 1B 使用 U-role，proposal seed 为 `2026101202`，shuffle seed 为 `2026101302`。

```sh
/tmp/dataset-tools/make_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin \
  U-role 1000000000 2026101202 2026101302 /tmp/role-1b

/tmp/dataset-tools/check_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin /tmp/dataset-tools/eligibility.bin \
  U-role 1000000000 /tmp/role-1b/requests.csv /tmp/role-1b/check
```

预期输入大小为 35,197,849,579 B，SHA 为 `3e01ed8f591ca1c06e3e4c36e66853437b784efbff22d1cc9880d4baf1adc474`。生成时没有 exp685 的源 pin 及历史请求排除步骤。这套 1B 在多个历史版本中复用，属于已观察数据。

1B 生成器的去重表需要约 17.2 GB，洗牌还会产生较大的临时文件。请为完整生成预留数十 GB 内存和足够磁盘。赛题的 2 GB、单线程约束针对提交估计程序；离线生成资源单独计量。

## exp685 的 100M

exp703、exp704、exp706 使用 exp685 的同一份 100M。先提议 120,000,000 个唯一请求，proposal seed 为 `20261025685`，shuffle seed 为 `20261026685`。随后按原顺序排除 exp501 训练集中的完整源 pin，再排除预登记历史请求，保留前 100,000,000 条。

`exclusions/` 保存了全部 960,505 个训练源 pin，以及经源 pin 排除后剩余的 20,391,557 个历史完整请求对。历史文件身份见该目录的 `manifest.json`。端点采用可逆整数编码，文件不包含标签。

```text
pin_id = (y*120+x)*496 + port_id
pair_key = (source_pin_id << 32) | target_pin_id
```

`port_id` 遵循 `source/arch/SRB_Port.json` 的原始顺序。`filter_fresh.py` 是便于外部使用的适配入口，适用输入为冻结生成器输出的规范端点；历史原函数仍在 `training/original/validation/exp642_fresh_symmetric.py`。

```sh
/tmp/dataset-tools/make_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin \
  U-role 120000000 20261025685 20261026685 /tmp/proposal-685

python3 dataset_protocol/filter_fresh.py \
  /tmp/proposal-685/requests.csv /tmp/fresh-100m --protocol exp685

/tmp/dataset-tools/check_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin /tmp/dataset-tools/eligibility.bin \
  U-role 100000000 /tmp/fresh-100m/requests.csv /tmp/fresh-100m/check
```

预期请求 SHA 为 `34124e61db52c4f1de64e742a96508d160087153d5c446292bf9ab5b13db9a30`。源 pin 隔离相对 exp501；历史排除覆盖 manifest 中已登记的数据，范围包含多个旧抽样集，不能扩展成与所有历史 1B 全量输入都互斥。原始输入证据位于 [100m-input.json](../validation/results/exp685/100m-input.json)。本轮没有重新生成完整 100M 或 1B。

## 当前 exp720 的新 100M

exp720 的模型比较及后续 exp723、727、728 等价验收使用另一份新请求。提议仍为 120M，proposal seed `20261025720`、shuffle seed `20261026720`。先排除同一批 960,505 个训练源 pin，再排除 22,308,485 个登记历史请求，按原顺序取前 100M。其相对 exp685 多排除了 exp685 已抽样的 1,916,928 条请求，增量集合在 `exclusions/exp720-additional.npz`，身份和来源见 `exclusions/exp720-extension.json`。

```sh
/tmp/dataset-tools/make_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin \
  U-role 120000000 20261025720 20261026720 /tmp/proposal-720

python3 dataset_protocol/filter_fresh.py \
  /tmp/proposal-720/requests.csv /tmp/fresh-720 --protocol exp720

/tmp/dataset-tools/check_hidden_suite \
  source/arch /tmp/dataset-tools/reach.bin /tmp/dataset-tools/eligibility.bin \
  U-role 100000000 /tmp/fresh-720/requests.csv /tmp/fresh-720/check
```

`filter_fresh.py` 默认采用 exp720 排除集合，复现旧 exp685 需明确选择 `--protocol exp685`。当前输入为 3,519,786,871 B，SHA 为 `922c4ea35138501ae5014db483e9f2cfad3d28f226e5ee19d33eec07e1d9a2e3`。原证据见 [100m-input.json](../validation/results/exp720/100m-input.json)，人口见 [exp720-pair-populations.json](exp720-pair-populations.json)。

原过滤访问 108,460,406 条提议，排除 8,460,395 条训练源 pin 请求和 11 条历史请求。登记排除集合与全部历史完整 1B 的互斥范围分别理解；该 100M 经过 exp720 模型验收后也成为开发证据。

```sh
python3 dataset_protocol/sample_exact_requests.py exp720-100m \
  /tmp/fresh-720/requests.csv dataset_protocol/exp720-pair-populations.json \
  /tmp/dataset-tools/stratified-sample /tmp/sample-720
```

每 pair 抽 32 条，seed 为 `20261027720`，共 1,916,928 条。原动态生成的函数文本保存在 `exp720-generated-population.py` 和 `exp720-generated-sample.py`。本轮检查增量集合与旧集合、训练源 pin 的全量互斥，并重建抽样计划核对 SHA。报告见 [exp720-protocol-verification.json](exp720-protocol-verification.json)。本轮没有重新生成完整 100M。

## exact 抽样与 outer-fold

| 人口 | 每 pair 样本数 | 样本总数 | 抽样 seed |
| --- | --- | --- | --- |
| exp685 100M | 32 | 1,916,928 | `20261024685` |
| exp720 100M | 32 | 1,916,928 | `20261027720` |
| 原 1B 的 exp683 扩大抽样 | 64 | 3,833,856 | `20261025683` |

两个 `population-*.json` 保留实际人口计数。抽样先在每个 pair 内选定出现序号，再顺序扫描 CSV，输出原始行位置；抽样比例为 `n_pair/N_pair`。抽样、位置和标签对齐代码来自 exp683。

本轮已重新生成两份完整抽样计划，SHA 均与历史冻结文件一致。历史排除集合的全部 SHA、整数编码与顺序通过核对；便携过滤入口在 228 行机制样本上与原函数的保留顺序、人口计数和两类拒绝计数一致。C++ sampler 的正常选择、重复输出拒绝和缺少末尾换行检查也已通过，详见 [protocol-verification.json](protocol-verification.json)。

```sh
python3 dataset_protocol/check_protocol.py \
  /tmp/dataset-tools/stratified-sample /tmp/protocol-check
```

```sh
python3 dataset_protocol/sample_exact_requests.py 100m \
  /tmp/fresh-100m/requests.csv dataset_protocol/population-100m.json \
  /tmp/dataset-tools/stratified-sample /tmp/sample-100m
```

1B 将参数改为 `1b`、对应请求和 `population-1b.json`。原标签生成使用四个离线 shard，每个求解器单线程，并有 12 条参考搜索复核。原始流程与评分在 `training/original/validation/exp683_expanded_exact.py`、`exp683_expanded_score.py`。`exp685-generated-population.py` 和 `exp685-generated-sample.py` 保存当时动态生成的函数文本。

模型研究的三个 outer-fold 以完整源 pin 为分组单位，随机种子为 `20261020554`。为使每折都覆盖 59,904 个端口对，分配后按固定规则移动整个源 pin 组；修复过程只使用组、pair 和计数。重建代码为 `exp554_real_kernel_function.split`，百万行原始折号及组号随训练数据提供。本轮已重新生成并逐行核对折号，见 [data-verification.json](../training/data-verification.json)。

这些 OOF 指标是历史开发证据。官方分布泛化、跨架构泛化以及新的盲测效果，需要各自独立的数据支持。
