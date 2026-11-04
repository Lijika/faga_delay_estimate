# 实验91：当前训练池 base 深度组合预注册

## 目标与基线

本轮执行下一阶段规划 P1，基准沿用 `exp85-radix-reuse-5f5e016`；当前正式实现使用同一 47 维 base 特征族和更大的 exp87 训练池，性能基线记录为当前 `exp90-row-load-65952db-dirty`。本轮只做离线精度筛选，不修改正式入口。

## 冻结候选

- 训练池：exp87 的 46,505 条可达 exact 行，由 `validation/results/exp18b-labels.csv`、`build/exp56/fresh-samples.csv`、`build/exp57/fresh-samples.csv`、`build/exp57/exp58-samples.csv`、`build/exp61/fresh-samples.csv`、`build/exp77/fresh-samples.csv`、`build/exp78/fresh-samples.csv` 合并，完整端点去重。
- 特征：生产 44 维矩阵加 `base`、`base-fast`、`base/max(fast,1)`，屏蔽槽和计算方式固定为 exp87。
- 目标：`exact-fast`；语料带权重沿用 `exp18b-labels.json`；XGBoost `reg:absoluteerror`、hist、CPU、eta `0.1`、seed `20260919`、单线程、128 棵树。
- 候选：`base-d4-128`、`base-d6-128`、`base-d8-128-control`。当前 `model-more_labels.json` 作为 d8 身份和重训一致性对照。
- 禁止选择项：树数、学习率、采样率、列采样、偏移量、阈值和新窗口上的重复调参。

## 独立数据与标签

固定 affine unique 窗口 `[34M,36M)`，从未参与历史训练、开发选择或 exp87 `[32M,34M)` 验证。请求生成后核对已记录前缀、生成器元数据和完整端点排除集；每个距离带最多 1,024 行，由冻结 `build/query_profile_exp18b --pdb-only --dedup-endpoints --landmarks 8` 生成 exact 标签。命中排除集或距离带缺失时停止，不替换样本；不读取 golden，不使用候选预测抽样。

## 判决规则

主指标为新窗口原始距离带份额加权 accuracy，辅以 MAPE、逐带指标、false finite 和 reachable false unreachable。使用七带 paired bootstrap 10,000 次、seed `20260925`。候选相对当前 d8 control 需达到点增益 `+0.03 pp`、95% 下界为正、两类可达性误判不增加；若 d6/d8 不能超过 control，关闭本轮 P1。精度通过后才做组件和 3 对 1M unique CPU 测量；本轮不运行 1B。

## 复现入口

请求/采样：`build/venv-ml/bin/python validation/exp91_p1_base_depth.py --stage requests`、`--stage sample`。评分：同一脚本 `--stage score`。原始输入、模型、预测、报告放在 `build/exp91/` 和 `validation/results/exp91-*`。
