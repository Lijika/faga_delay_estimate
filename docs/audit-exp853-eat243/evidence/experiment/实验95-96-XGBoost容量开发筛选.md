# 实验95-96：XGBoost 容量开发筛选

日期：2026-09-27。两轮均复用实验93已标注的 `[38M,40M)` 请求窗口，只作开发筛选，不作独立泛化或正式接入证据。基线是实验93的 46,505 行可达 exact 训练池、47 维 base 特征、`reg:absoluteerror`、`eta=0.1`、`gamma=1`、depth 10、128 棵树和统一 `-3 ps` 输出；基线模型 SHA-256 为 `9e0989b5b0f38e272a3e481498ea7042b69fd9b2d8d87bbf78adb04e21ea58cf`。

实验95只把深度改为 12，实验96只把树数改为 256。筛选门槛沿用先前固定的请求加权 accuracy 点增益至少 `+0.03 pp`、七带配对 bootstrap 10,000 次的 95% 下界大于 0、两类可达性误判均不增加。只有通过筛选的候选才使用新的 `[40M,42M)` exact 窗口独立验证。

| 候选相对 128 树 depth 10 | accuracy 增益/pp | 95% 区间/pp | false finite / reachable false unreachable | 筛选 |
| --- | ---: | --- | --- | --- |
| depth 12，128 树 | -0.026251 | [-0.067507,+0.016019] | 0 / 0 | 未通过 |
| depth 10，256 树 | +0.013958 | [-0.001811,+0.029955] | 0 / 0 | 未通过 |

复现命令为 `build/venv-ml/bin/python validation/exp95_depth12_screen.py` 和 `build/venv-ml/bin/python validation/exp96_trees256_screen.py`。原始报告在 `validation/results/exp95-depth12-screen.json`、`validation/results/exp96-trees256-screen.json`，模型与逐行预测分别在 `build/exp95-screen/`、`build/exp96-screen/`。两个 control 重训模型的 SHA 与上述冻结模型一致；实验96的 control 逐行预测与 `validation/results/exp93-p1-predictions.csv` 一致。样本共 6,178 行，七带覆盖完整；公开 golden 未参与训练或筛选。

初版脚本只用冻结 `fast.csv` 覆盖了训练行，导致两份报告把 9 条负 exact 行误计为 false finite。修正为覆盖训练和验证全部行后重跑，双方可达性误判均为 0，正样本 accuracy、区间和筛选结论均未改变。修正后的完整输入、预测和模型 SHA 见报告。

这两项容量候选关闭；不生成新窗口标签，不做 C++ 导出和 1M 计时。实验93的 depth 10 虽在独立窗口提高 `+0.040127 pp`，但三对 1M unique CPU 平均增加 `5.00 s`，综合分点估计 `-0.009565`。当前证据支持停止沿相同特征和训练池继续堆深度/树数。实验87增加 exact 训练行的独立窗口收益 `+0.065893 pp`，实验92 gamma 调整收益 `+0.032095 pp`，因此尚不能判定 XGBoost 或机器学习整体收益耗尽；下一次筛选应优先检验标签增量或真正新增的路径级信号。

开工和收尾 `df -h .` 均显示工作区所在 `/dev/sdd` 约 479G 可用；本环境没有 `/dev/sdd` 设备节点，直接 `df -h /dev/sdd` 失败。本轮不运行 1B，未删除任何文件，释放量 0。新增模型和预测均小于 20 MB，保留以复核；可由上述脚本重建。
