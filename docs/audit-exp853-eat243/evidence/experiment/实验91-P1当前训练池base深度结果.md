# 实验91：当前训练池 base 深度筛选结果

日期：2026-09-27。状态：P1 关闭，候选未接入正式实现。

## 协议与身份

- 预注册：`实验91-P1当前训练池base深度预注册.md`。
- 训练池：46,505 行可达 exact，特征为生产 44 维加 `base`、`base-fast`、`base/max(fast,1)`。
- 候选：128 棵树、`max_depth` 4/6/8，`reg:absoluteerror`、`hist`、CPU、`eta=0.1`、seed `20260919`、单线程；目标为 `exact-fast`。
- 新窗口：affine unique `[34M,36M)`，抽样标签来自冻结 `build/query_profile_exp18b --pdb-only --dedup-endpoints --landmarks 8`，每带最多 1,024 行，bootstrap 10,000 次、seed `20260925`。
- 冻结身份：exp87 模型 `6904544684efacfb0bbb80ae7340900bd8c6888e7993f6146351b15985ba338f`；FAST `a80595dd4ecd933da5ea46dc6293df33b912d77dc716ef1fcfbb6b047b8211c`；BASE `d66c067658a7e7ad92edc5cc0351119661543648c61adaa3682779df390c45c5`；probe `613139d1b2d3363f1909c2d4a15dbe31c61fa8592732afc8ed5136e26b2730e5`。

## 数据阶段

执行命令：

```sh
build/venv-ml/bin/python validation/exp91_p1_base_depth.py --stage requests
build/venv-ml/bin/python validation/exp91_p1_base_depth.py --stage sample
build/venv-ml/bin/python validation/exp91_p1_base_depth.py --stage score
```

- 请求阶段生成 36,000,000 行，切片 2,000,000 行；历史 4M/6M/8M/10M 前缀逐行匹配，生成器身份一致。请求文件 SHA-256 为 `ba72c0839111a9005ce1c4a06b9f92c8d514ed9cef06e92b23e3b09747affce2`，阶段耗时 77.866 s。
- probe 扫描 2,000,000 行，抽取 6,178 行。七带均有样本，排除集命中 0，距离和带交叉检查 6,178/6,178 通过；阶段耗时 506.0 s。
- 评分重跑输出与首次评分完全一致：`exp91-p1-score.json` SHA-256 `225bee70df12c9e12aef9ef2e9e78b28180c64e43a62df2c70d30eb3593a3124`，预测 SHA-256 `dc6bc8bbaecd7ad400cea56336e2549562ae8b736955f1893e72709af46bb633`。

## 结果

主指标为新窗口距离带份额加权 accuracy；d8 为当前模型的重训 control。d8 重训模型 SHA-256 与冻结模型相同。

| 模型 | accuracy | MAPE | 相对 d8 | 95% CI（百分点） | false finite | reachable false unreachable | gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base-d4 | 96.165266% | 0.976416% | -0.269088 | [-0.316827, -0.221850] | 0 | 0 | 未通过 |
| base-d6 | 96.377268% | 0.922578% | -0.057085 | [-0.086311, -0.027003] | 0 | 0 | 未通过 |
| base-d8 control | 96.434353% | 0.907745% | 0 | — | 0 | 0 | control |

d4、d6 的点增益均低于 `+0.03 pp`，bootstrap 95% 下界均为负。两类可达性误判在全部模型中均为 0。逐带 accuracy、MAPE、样本数和 bootstrap 原始数据见 `validation/results/exp91-p1-score.json`。

## 判定与边界

本轮关闭 d4/d6 深度候选，正式源码、`./estimate`、`subm/latest/` 和提交包保持原身份。本轮未做私有 C++ 导出、逐行部署核对或 1M unique CPU 测量，因为精度 gate 未通过；没有 1B 结论。结果覆盖一个新窗口和当前 46,505 行训练池，不能外推到其他架构或隐藏评测分布。

评分脚本的 gate 只读取四个布尔门槛字段，数值、bootstrap 字典和报告字段保持为证据数据。

## 资源与收尾

开工前 `df -h /dev/sdd`：可用约 484G；收尾：可用约 483G。`build/exp91/unique-36m.csv` 为本轮唯一请求原始输入，大小 1,287,071,509 字节，SHA-256 如上，可由请求阶段命令重建，当前保留以支持复核。评分计时：wall 61.62 s，CPU 64.36 s，最大 RSS 903,764 KiB；模型训练使用单线程。未删除本轮唯一输入或结果文件。
