# 实验73：固定预算 LightGBM 残差

日期2026-09-26。开工 `/dev/sdd` 可用490G。

## 预注册

- 正式基线exp71，模型仍为exp63；身份与数据沿用实验72。实验72类别切分表现为训练提升、两开发窗口退化，本轮保持全部特征数值编码。
- 固定一个新学习器候选 LightGBM4.6.0，依赖仅在 `build/exp73/deps`；安装命令 `build/venv-ml/bin/python -m pip install --no-deps --only-binary=:all: --target build/exp73/deps lightgbm==4.6.0`。训练时复用现有numpy/scipy，生产无新依赖。
- 原34,352条可达标签、47维/6屏蔽槽、目标exact-fast、原带份额/标签倒数权重、64树最大深度8、学习率0.1、单线程seed20260919和输出-3保持。LightGBM使用regression_l1、num_leaves256、max_bin256、min_data_in_bin1、min_data_in_leaf1、min_sum_hessian_in_leaf1、lambda_l2=1、lambda_l1=0、不采样行列。deterministic=true和force_col_wise=true，四个相关seed显式固定。两种库的建树/分箱内部算法不同，所得差异归因于学习器整体，不能单独归因于叶优先增长。
- 参数已核对官方4.6.0文档 https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html ，本地副本 `build/exp73/lightgbm-parameters.md`，并检查安装版本API签名。control重新训练需完整复现exp63 SHA；新模型重复拟合一次，两个model字符串SHA需相同。
- 开发集仍为已看过的exp62和exp64，使用各窗口原始带份额评分；核对完整端点、文件身份和XGBoost control与验收参考逐行一致。两窗口增益都≥+0.03 pp、可达性误判不增加才入选。本轮一个固定候选，不根据开发结果调LightGBM参数。
- 若通过，先冻结model SHA再生成未使用 `[26M,28M)` 新窗口，七带各最多1024条exact；排除公开1M/训练及全部旧窗口端点。配对bootstrap10,000次/seed20260925，点增益≥+0.03 pp、95%下界>0且可达性误判不增加，才做私有C++静态树导出。
- 通过后必须核对LightGBM的 `<=` 阈值语义和双精度累加，生产不调用Python或LightGBM动态库；逐行输出/边界与Python一致，3对交错1M CPU综合点收益≥0.01、保守下界>0，再完整1M契约/资源验收。开发失败即停止，不读取新exact、不修改正式实现。
- 所有开发筛选不代表独立泛化；公开golden只作最终评分，平台1B/隐藏集另待实测。

## 结果

`build/venv-ml/bin/python validation/exp73_lightgbm.py` 完成；证据 `validation/results/exp73-screen.json`。XGBoost control完整复现exp63 SHA并逐行对齐参考，LightGBM重复拟合的model字符串完全相同。候选保持64树、最大深度8，共15,032节点/7,548叶子，训练约1.055秒，模型文件797,990字节，SHA `cfff2a89baff42116074f586e7242714f644f54a8e1d1725d983f649b34f220e`。

训练accuracy96.763793%，低于XGBoost的96.937624%；exp62/exp64开发增益为-0.065195/-0.057888 pp，两类可达性误判均为0。本轮这个固定配置未达到开发门槛，停止部署，不读取 `[26M,28M)` 新exact窗口。结论只针对该训练池、特征和预算下的固定LightGBM配置。原始模型、库身份、分带误差和预测CSV身份已保留。

收尾 `/dev/sdd` 可用490G，未删除文件，释放量0；正式入口仍为exp71。
