# 背景、曲线与残差模型的训练来源

本目录提供训练源码、百万行历史训练数据及重训入口。当前冻结参数位于 `source/models/` 和 `source/assets/`，历史 S16 参数位于 `training/baselines/exp688/`。编号对应关系如下，便于区分模型训练与后续部署编码。

| exp728 组件及历史对照 | 训练或拟合来源 | 部署处理 |
| --- | --- | --- |
| D64 背景 | exp586 的 N512 近域，加 exp589 的四方向 rank64 远域 | exp589 量化导出，exp646 无损压缩和启动恢复 |
| 距离曲线 | exp650 原型，exp651 全相位四方向拟合 | exp652 查询实现，exp654 将 int16 曲线无损编码为 u8 |
| T2D6 | exp719 比较、exp720 最终训练 | 两棵 depth6，exp727 编译一元坐标判定 |
| 历史 S8 | exp640 的 16 路 S16 对称树 | 每路取前 8 棵，保留原树次序和叶值 |
| V8 | exp678 的 OOF 研究，exp679 的 V64 最终模型 | exp684 取前 8 棵，exp686/N 仅在 V 事件使用，H 专家关闭 |

`original/` 保存历史脚本及依赖，文件身份见 [original-source-manifest.json](original-source-manifest.json)。其中保留当时的兄弟实验目录、主机检查和资源检查，直接执行前需要恢复这些路径。可独立使用的入口为本目录下的 `check_data.py`、`retrain_residual.py` 以及 `nominal_source/build.sh`。

## 百万行训练数据

三个 NPZ 按同一行序保存，完整端点查询复用 [anchors-source-queries.bin.gz](../path_witness/query_source/anchors-source-queries.bin.gz)。它是 exp501 的历史训练请求，经原工具转换为十列查询；完整端口可从坐标及原始端口序号恢复。

| 文件 | 内容 |
| --- | --- |
| `data/features53.npz` | `features`，`(1000000,53)` int16，转 float32 后与历史特征文件逐字节一致 |
| `data/features_extra18.npz` | `features`，`(1000000,18)` int16，包含 16 个几何特征及 bands、ends |
| `data/targets_splits.npz` | `truth,d0,mandatory,folds,clusters,pair,routes,base_q4,base_curve,base_d64,event` |

71 列的名字与来源见 [feature-schema.json](feature-schema.json)。`truth` 是完整图 exact，`d0` 是 Line 置零后的 exact，`mandatory` 是当前模型单独加回的确定性费用。三个 `base_*` 均处于 D0 空间。`pair` 为源角色序号乘 288 加目标角色序号，`clusters` 标记完整源 pin，`folds` 为 0、1、2。

`export_training.py` 调用原 exp679 的数据装配函数导出这些数组，原文件身份和导出文件 SHA 见 [export-manifest.json](data/export-manifest.json)。三个 outer-fold 按完整源 pin 隔离；划分种子为 `20261020554`，具体算法见 [请求协议](../dataset_protocol/README.md)。

```sh
python3 training/check_data.py /tmp/training-data-check
```

exp688 材料发布时检查了全部百万行的唯一性、53 列原文件 SHA、18 列重算结果、曲线背景重算结果及原函数重新生成的折号。共有 960,505 个完整源 pin，事件行数为 ordinary 979,323、H 18,064、V 2,613。结果见 [data-verification.json](data-verification.json)。

## 当前 T2D6

exp720 普通模型对每个 route 的全部行训练，包含后来由 V8 替换的事件行。目标为 `d0-base_curve`，权重为 `1000/max(d0+mandatory,128)`。固定参数为两棵 depth6 SymmetricTree、学习率 0.7599、MAE、Exact leaf estimation，一次 leaf iteration、Plain boosting、No bootstrap、`boost_from_average=false`、`random_strength=0`、`border_count=256`、`l2_leaf_reg=1`、L2 score、seed `20261023640`、离线 16 线程。完整参数见 [final-training.json](../validation/results/exp720/final-training.json)。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 training/retrain_residual.py --model t2d6 --route 0 --output /tmp/t2d6-route0

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 training/retrain_residual.py --model t2d6 --route 0 --fold 0 --output /tmp/t2d6-route0-fold0
```

当前重训入口支持 T2D6、历史 S8 和 V8。T2D6 默认匹配 curve 背景，S8 保留历史 q4 背景，V8 使用 curve。模型最终参数的 JSON 身份可独立核对；CatBoost JSON 中的训练时间等元数据不作为模型数值等价依据。

本轮新增重训 T2D6 route 0 最终模型，树、特征边界和 scale/bias 与冻结版完全一致，叶编号和原生 raw 预测一致；另验证 route 0/fold 0 的源 pin 隔离及历史 S8 route 0 的迁移路径。报告见 `retrain-t2d6-route0-verification.json`、`retrain-t2d6-route0-fold0-verification.json` 和 `retrain-s8-route0-current-verification.json`。其余 T2D6 routes 的参数按冻结 SHA 提供，本轮没有全部重训。

原生成过程保存在 `original/validation/exp719_leaf_budget.py`、`exp720_leaf_cli.py` 和 `exp727_coordinate_masks.py`，查询头文件在 `source/include/`。新增更深模型时应重新检查叶编号、raw、整数化及完整输出；当前入口只复现已用函数族。

## 残差重训与导出

环境使用 CatBoost 1.2.8；本轮远端 NumPy 为 2.2.6。S8 的训练目标是 `d0-base_q4`，V8 的目标是 `d0-base_curve`。这两个背景选择沿用各自训练时的版本，做背景与残差四格对照时应把它们分别列为实验因素。

两类模型均使用深度 4 的 SymmetricTree、MAE、学习率 0.3、Exact leaf estimation、一次 leaf iteration、Plain boosting、No bootstrap、`boost_from_average=false`、`random_strength=0`、`border_count=256`、`l2_leaf_reg=1` 和 L2 score。样本权重为 `1000/max(d0+mandatory,128)`。

| 参数 | S8 的训练模型 | V8 的训练模型 |
| --- | --- | --- |
| 树数 | 16，部署前 8 棵 | 64，部署前 8 棵 |
| 特征 | 前 53 列 | 全部 71 列 |
| 训练子集 | 指定的一个 route，共 16 路 | `event==2` |
| seed | `20261023640` | `20261024678` |
| 训练线程 | 16 | 1 |

这些线程数只用于离线训练。提交估计程序保持单线程。完整参数直接从 [exp640 prepare](../validation/results/exp640/prepare.json)和 [exp678 freeze](../validation/results/exp678/freeze.json)读取。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 training/retrain_residual.py --model s8 --route 0 --output /tmp/s8-route0

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 training/retrain_residual.py --model v8 --output /tmp/v8
```

使用 `--fold 0`、`1` 或 `2` 可以排除对应完整源 pin 折，默认 `--fold -1` 训练最终模型。`--background q4|curve|d64` 用于明确改变残差背景，输出写入新的目录。四格对照应固定数据划分，在每个训练折内重新拟合依赖该折标签的模型，再评估对应留出折；已有历史数据的 OOF 继续按开发证据解释。

exp688 材料发布时重训了 V64 全量模型及 S16 的 route 0，树、特征边界、scale/bias 与冻结模型完全相同，前 8 棵的叶编号与原生预测核对通过，raw 差为 0。见 [V64 核验](retrain-v8-verification.json)和 [S16 route 0 核验](retrain-s8-route0-verification.json)。其余 S8 routes 和全部 OOF 没有在本轮重新训练。

部署导出代码在 `original/validation/exp640_symmetric_cli.py` 的 `emit()` 及 `exp679_hv_cli.py` 的 `emit()`。它们读取 CatBoost JSON，生成固定比较和叶值累加；`exp684_event_prefix.py` 则选择部署前缀。整数化及边界处理沿用 `source/src/worker.cpp`，新模型导出时需要继续核对逐叶编号、raw 值、整数输出和事件路由。

## D64 的名义场与拟合

名义场使用 exp499/exp483 的周期图求解器，针对全部 208 个源角色导出 288 个目标角色及几何网格上的延迟。它与真实位置上的 D0 标签分别保存。field 保存减去固定方向线性项后的 int16 值，物化后的矩阵形状为 `59904×264960`，数据约 31.7 GB。原始 208 个 field 的身份、mapping 与 exact 认证在 `nominal-metadata/`。

```sh
sh training/nominal_source/build.sh
training/nominal_source/field source/arch --self-check
training/nominal_source/field source/arch 'ZDE[0]' /tmp/ZDE0-field.bin
```

`field` 的 SOURCE 参数取自 `nominal-metadata/mapping.json` 的 sources。文件以 `EX499D01` 开头，包含源端口序号、维度、目标端口顺序，随后按方向、rx、ry、target 和 552 个距离格点存放残量。读取与矩阵物化代码在 `exp500_split_residues.py` 及后续拟合脚本中。

构建入口已编译并检查帮助，见 [nominal-build-verification.json](nominal-build-verification.json)。本轮没有重新生成全部名义场；`--self-check` 使用 208 个源角色分别比较队列实现和独立全端口图，重跑成本需单列。GCC 13 对原源码给出了 range-loop-copy 提醒。

近域覆盖 4,800 个几何列，由 `exp586_near_capacity.py` 拟合 rank768 后取前 512 维，seed 为 `20261022586`。远域共有 260,160 列，按四方向分为每方向 65,040 列，`exp589_directional_far.py` 每方向拟合 rank96 后取前 64 维，seed 为 `20261022589`。

两者调用 `exp557_conditional_geometry.fit`，采用 `rank+16` 随机投影、一轮转置与正向 power 运算、QR 和 `gesdd`，并固定因子符号。拟合的归一化因子为 `128+125*qx+125*qy`；中心项、方向项和几何列定义应连同 `exp557`、`exp586`、`exp589` 源码读取。`exp589_complete_candidate.py` 导出 INT8 因子与尺度，保留 64 元素块的运算次序；`exp646_asset_restore.py` 负责无损表示及恢复。

## 距离曲线的训练与划分

曲线拟合对象是量化 D64 在名义场上的剩余误差。每方向有 120 个 phase，完整目录含 `59904×480` 个一字节 code。每方向的 codebook 有 256 条曲线，每条 542 个远域距离格点。

exp651 每方向从构建源端口中抽 16,384 行，seed 为 `20261024651+d`。前 16 条曲线固定为 Q4 常数，另 240 条从样本初始化，seed 为 `20261025651+d`。随后执行 6 轮坐标中位数更新及加权 L1 分配。几何训练格、验证格和权重见 `exp650_distance_curves.py` 的 `TRAIN`、`VALID`、`WEIGHTS`，完整冻结值见 [exp651 freeze](../validation/results/exp651/freeze.json)。

56 个源端口被排除在 codebook 拟合来源之外。全部源端口仍会使用自己的训练距离格选择 code，因此这里的隔离范围是共享 codebook 的构建来源；每个留出源对应的 code directory 仍经过分配。做新的泛化检验时，需要分别说明 codebook、code assignment、残差树的训练来源。

`exp651_full_distance_curves.py` 导出 int16 曲线资产，`exp654_curve_bytes.py` 用 origin `-55` 无损编码为 u8。exp688 材料发布时逐行核对百万训练请求上的解码和背景结果。完整名义场、矩阵物化及曲线全量拟合占用较大资源，本轮提供生成代码与历史身份，未重新执行这一部分。
