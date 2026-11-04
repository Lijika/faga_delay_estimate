# 实验92：当前训练池 gamma 单变量验证预注册

日期：2026-09-27。承接实验91 的 P1 负结果，在同一 46,505 行训练池上验证一个固定的 XGBoost 分裂门槛。

## 开发筛选与冻结

- control：实验87 `model-more_labels.json`，47 维 base 特征，depth 8、128 棵树，`reg:absoluteerror`、`eta=0.1`、`seed=20260919`、单线程、`gamma=0`。
- candidate：完全相同的训练池、特征、目标、权重和树结构参数，只固定 `gamma=1.0`。
- 开发窗口为已完成且不再用于本轮新标签选择的实验64、实验76 和实验91 `[34M,36M)`。无 bias 的 pooled accuracy 增益分别为 `+0.003505/+0.018344/+0.022606 pp`；该筛选结果只用于冻结候选，未读取 `[36M,38M)` 标签。
- 开发筛选跳过 gamma 扫描后的其他参数组合；本轮不调树数、深度、学习率、采样率、列采样、权重或输出偏移。

## 独立数据与标签

固定 affine unique 窗口 `[36M,38M)`，从未参与实验91 或历史训练/开发选择。生成 38M 行后切片 2M；排除公开输入、训练池、历史实验和实验91 的完整端点键。每带最多 1,024 行，由冻结 `build/query_profile_exp18b --pdb-only --dedup-endpoints --landmarks 8` 产生 exact 标签；命中排除集或距离带缺失即停止且不替换。

## 判决规则

主指标为新窗口原始距离带份额加权 accuracy，辅以 MAPE、逐带结果、false finite 和 reachable false unreachable。相对 d8 control 的候选必须同时满足：点增益至少 `+0.03 pp`、10,000 次七带 paired bootstrap（seed `20260925`）95% 下界为正、两类可达性误判不增加。通过后才做私有导出、逐行部署检查和 3 对 1M unique CPU 测量；失败则关闭本轮，不改正式实现。

## 复现入口

```sh
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage requests
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage sample
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage score
```

正式源码、`./estimate`、`subm/latest/` 和提交包在评分阶段保持原身份。模型、请求、样本、预测和报告分别保存到 `build/exp92/` 与 `validation/results/exp92-*`。
