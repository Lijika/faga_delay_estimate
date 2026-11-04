# 实验97：XGBoost 新增 exact 标签开发筛选

日期：2026-09-27。开工 `df -h .` 显示 `/dev/sdd` 可用约 479G；本环境无 `/dev/sdd` 设备节点。

## 预设方案

假设现行 47 维 base 残差模型的训练行数仍限制泛化。control 固定为实验92模型：46,505 行可达 exact、128 树、depth 8、`gamma=1`、`eta=0.1`、`reg:absoluteerror`、单线程、统一 `-3 ps`，模型 SHA-256 `92a3c09217e7881fc07704159f4ba7d123f233bcb21dab5f78a2a8fc61c015cc`。candidate 只加入实验91 `[34M,36M)` 和实验92 `[36M,38M)` 已核验的可达 exact 行，训练参数、特征、树数、深度和输出函数全部不变。完整端点去重且冲突即停，`fast/base` 逐行取各窗口已冻结的二进制输出；不读公开 golden。

开发窗口固定为实验93已查看的 `[38M,40M)` 6,178 条样本，按其 2M 原始请求的七带份额加权评分。预设通过条件为相对实验92 control 的 accuracy 点增益至少 `+0.03 pp`、七带配对 bootstrap 10,000 次（seed `20260925`）的 95% 下界大于 0、false finite 和 reachable false unreachable 均不增加。开发结果只用于筛选；通过后冻结候选 SHA，使用未参与本次选型的新 `[40M,42M)` 请求和 exact 标签独立验证，再按综合分评估 CPU。失败即关闭这一组新增标签，不生成新窗口标签，不改正式实现。

脚本与结果：`validation/exp97_more_labels_screen.py`、`validation/results/exp97-more-labels-screen.json`；模型和逐行预测保留在 `build/exp97-screen/`。开工前模型、样本、输出 SHA 将从实验91/92/93报告核验，control 重训须复现实验92模型，control 预测须逐行复现实验93的保存结果。

## 开发筛选结果

运行 `build/venv-ml/bin/python validation/exp97_more_labels_screen.py`。新增 12,162 条可达 exact 行后，训练池为 58,667 行；control 模型 SHA 与实验92一致，control 在 6,178 条开发样本上的预测与实验93保存结果逐行一致。所有输入文件的大小和 SHA-256 检查通过。候选模型 SHA-256 为 `6ee6e29c87e54342bc9ad0cc21bd3989d0960beebda00b1d3632a90ba4fb26d4`。

| 指标 | control | 新增标签 |
| --- | ---: | ---: |
| 加权 accuracy | 96.196894% | 96.218037% |
| 加权 MAPE | 0.969715% | 0.964182% |
| false finite / reachable false unreachable | 0 / 0 | 0 / 0 |

accuracy 增益 `+0.021143 pp`，七带配对 bootstrap 95% 区间 `[-0.016836,+0.059841] pp`。点估计低于预设 `+0.03 pp`，区间下界低于零，筛选未通过。按距离带看，`101–300` 为 `+0.045536 pp`，`301+` 为 `+0.010287 pp`，`25–50` 为 `-0.065552 pp`，其他带的增减见原始报告。关闭本组新增标签候选，不生成 `[40M,42M)` 新标签，不修改正式实现。

这一结果只评价固定 47 维特征、depth 8、128 树、`gamma=1` 下的两窗增量；开发窗口此前已查看，不能把本次差值当作独立泛化证据。实验95/96的容量筛选也未通过，说明沿相同特征继续增加树数、深度和这组标签的收益已变弱。机器学习方向仍可检验新的、推理时可得且成本可控的路径级信号，其收益目前只是待测假设。

收尾 `df -h .` 显示 `/dev/sdd` 可用约 479G，与开工相同，释放量 0；本轮无 1B 文件或需清理的大文件。模型和预测均在 `build/exp97-screen/`，可由上述命令重建。
