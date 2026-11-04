# 实验64：新增独立 exact 训练池

日期：2026-09-26。开工时 `/dev/sdd` 可用492G。

## 预注册

- 正式基线为实验63静态包 `subm/versions/exp63-reachable-train-b58e538-dirty/bin-estimate`，SHA-256 `45c7bec5ed49c98d631d048865b9603afd2d5677a94c80f4eefc1bcebfecd59c`；参考模型JSON SHA-256 `79e705e78d3680e9528f479dd2b6722ef6dc06ba0272c0ff0e8823385a256fe0`。
- 单变量候选只把实验63 `[22M,24M)` 的exact样本加入实验63训练池，残差训练仍只使用 `exact >= 0`。47维特征、六个屏蔽槽、加权L1目标、depth 8、64树、seed `20260919`、单线程、`-3 ps`、训练权重及fast/base二进制不变。训练前按完整端点查重，重新计算fast并对齐；先冻结模型SHA，再获取验证标签。
- 验证使用同一 affine unique 生成器的 `[24M,26M)`，七带各至多1024条 exact；排除公开1M、训练池和所有已用独立窗口的完整端点。排除命中即停止，不补样。公开 golden 只作最终评分，不能用于选型。
- 主指标为按新窗口原始距离带份额加权的pooled accuracy差，七带配对bootstrap 10,000次、seed `20260925`。点增益至少 `+0.03 pp`、95%下界大于0、false finite及false unreachable均不增加，才进入私有部署。随后综合收益点估计至少`+0.01`、精度下界与CPU上界组成的保守下界大于0；性能预热后测3对同一1M unique输入。
- 若模型身份、端点、数值等价、精度或资源门槛失败，保留原始证据并停止此候选；正式入口与交付包保持实验63。新窗口仅支持同架构新请求泛化，隐藏分布以平台评测为准。

## 结果

训练阶段已先于新请求和exact标签完成。命令 `build/venv-ml/bin/python validation/exp64_incremental_labels.py --stage train`；身份和原始统计在 `validation/results/exp64-stage-train.json`。40,909条标签中排除476条负exact，使用40,433条可达标签；47维矩阵，fast重新计算后变动0行。冻结模型 `build/exp64/model-base-d8-more-labels.json` 的SHA-256为 `3009fe1aee16defcdbc5138fac2aa2c4ecfbdb4bd7388b7ac9c28b51d7fd0f42`，64树、depth 8、共19,788节点。评分阶段须重现这个完整SHA，否则停止。

## 独立验证与结论

依次运行 `build/venv-ml/bin/python validation/exp64_incremental_labels.py --stage requests|sample|score`。原始证据为 `validation/results/exp64-stage-requests.json`、`exp64-stage-sample.json`、`exp64-score.json`，逐行预测在 `build/exp64/predictions.csv`（SHA-256 `4cb74dcc9f288eafdde71eda3a7d6c0936ef6435fbc0cee20b3f68294b4edfda`）。

- `[24M,26M)` 新请求2,000,000行，exact样本6,179条；七带完整，历史端点排除命中0，距离与带划分检查通过。exact阶段耗时848.062秒。评分阶段重训后的模型完整SHA与预先冻结的 `3009fe1a…` 一致；参考模型的Python预测与实验63静态包逐行一致。
- 请求加权accuracy为基线 `96.293092`、候选 `96.300491`，差 `+0.007399 pp`，配对95%区间 `[-0.025251,+0.039873] pp`。MAPE `0.946695%` → `0.944949%`；近距几带略退，两类可达性误判均为0。
- 精度点收益低于预注册 `+0.03 pp` 且区间包含0。本次单纯增加实验63标签的候选停止，不进入1M性能测量，正式入口与交付包继续使用实验63。本结果只支持同架构新请求窗口的判断；隐藏分布未验证。

收尾时 `/dev/sdd` 可用491G，本轮未删除文件，释放量0；新请求、模型和预测中间产物留存以复现。
