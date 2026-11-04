# 实验233 C1 残差模型的选择历史与 Line 特征消融

2026-10-12。exp231 的 19 维残差模型通过独立请求精度门，exp232 正在
远程执行完整 CPU 检查。本轮使用 exp215 已查看开发集，检验既有程序
已经算出的选择历史和 Line 费用能否补充残差信息，模型容量保持不变。
理论前提复用 Obsidian 的《合法上界约束的带符号残差回归》。

## 预注册

唯一数据仍为 exp215 的 6,180 条请求。exp231 新标签继续只承担冻结模型
验证，本轮训练、校准和特征选择均保持与其分离。基础模型和 selector
训练端点排除复用 exp230 的已验记录，并在本轮检查完整 pin。

使用 exp220 冻结模块导出全部 26 维 selector 输入和 raw gain。
输入值由正式 exp131 在相同请求上生成；逐行核对 selector 输出、最小
C4800 上界与 exp215 的 baseline/upper/candidate。特征导出保持整数值与
float32 位，所有 online 特征都来自标签之外的计算。

四个模型臂共享 exp230 的空间五折、完整 pin 排除、校准 alpha 集合、
L1 样本权重、32 树 depth3、seed、训练参数与正值/上界输出规则。

- upper 为 19 维对照，必须逐行复现 exp230 的 upper 折外预测与 alpha。
- line 在 upper 上增加源目标 port class、Line x/y 费用，共 23 维。
- history 在 upper 上增加原预测、all、C、U-C、相对 U-C、原预测-C、
  合法旧路径数、selector raw gain、selected-P，共 28 维。
- combined 合并 line 和 history，共 32 维，为唯一主候选。

主假设是路径生成和选择过程的中间值有助于区分同一 P/U 的不同误差来源。
四臂都重新按固定切分训练，三项增量臂仅改变特征，原始标签与样本权重
保持相同。训练全部在本机运行，远程 exp232 独占计时。

主门固定为 combined 相对 upper 的折外增益至少 `+0.05 pp`，该配对差
的描述性 95% 区间下界高于零，且至少 4/5 个空间测试折为正。
七带 bootstrap 10000 次，seed2026101211。报告全部臂对 P 与 upper
的差、七带贡献、各折 alpha、改变/改善/恶化行数。line/history 只用于
归因，不按它们的得分改换本轮主候选。

未过即停止该固定特征组合。通过后才冻结全量模型，并另用新请求验证。
本轮结果属于已查看开发集上的模型比较，区间固定了已训练折模型，完整
程序 CPU、跨架构和新请求泛化均须另验。生产与交付包继续保持原样。

```bash
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp233_residual_history.py freeze
# 提交协议、输入和导出身份后
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp233_residual_history.py run
```

## 实测结果

冻结提交 `63ee8d8`。upper 对照逐行复现 exp230 折外输出和全部 alpha，
四臂的 JSON 树独立推理位与 XGBoost 一致；单独检查脚本再次复算空间
pin 排除、alpha、整数输出、评分和 bootstrap，全部通过。

| 特征臂 | 折外 accuracy | 相对 upper 增益 pp | 描述性 95% 区间 pp | 正收益空间折 |
| --- | ---: | ---: | --- | ---: |
| upper 19维 | 97.328233% | 0 | 对照 | 参照 |
| line 23维 | 97.333138% | +0.004905 | [+0.000188,+0.009747] | 4/5 |
| history 28维 | 97.374982% | +0.046750 | [+0.031926,+0.061910] | 5/5 |
| combined 32维 | 97.378365% | +0.050133 | [+0.035092,+0.065784] | 5/5 |

combined 超过预注册 `+0.05 pp` 点值门的幅度很小，五个空间折均为正。
相对 P 增益为 `+0.182773 pp`。history 单项解释了大部分开发收益，
Line 组合额外增加约 `0.003383 pp`。后续按原协议保留 combined 主候选，
新请求将单独判断这一小幅差值能否保持。

combined 相对 upper 的七带总体贡献依次为 `+0.000004/+0.003024/
+0.006355/+0.016429/+0.016986/+0.007827/-0.000492 pp`。
主要增益位于 25～100 距离带，301+ 有轻微退化。combined 五折 alpha
全部为 1，共改变 5,477 行，其中 2,890 行改善、2,494 行恶化。

二十个模型训练、JSON 推理检查与评分共 CPU `6.10 s`、wall `6.10 s`，
峰值 RSS `275,337,216 B`，stderr 为空。原始特征、二十个模型与训练记录
保留在 `build/exp233/`；逐行输出、主报告和复核为
`validation/results/exp233-predictions.csv`、`exp233-report.json`、
`exp233-evidence-check.json`。

冻结时 `/dev/sdd` 可用 `463,382,212,608 B`，收尾 `463,380,135,936 B`，
净减少 `2,076,672 B`，删除 0 B。结论限于已查看 exp215 的固定空间折外
比较，训练不确定性与多轮选择未由描述性区间覆盖；独立请求、部署等价
和完整 CPU 仍待验证，正式入口与交付包保持原样。
