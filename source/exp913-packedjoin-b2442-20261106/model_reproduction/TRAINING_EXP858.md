# exp858 四来源重新训练记录

本轮重新训练新模型，使用原复现工具包提供的图求解器和资产格式。
`INTEGRATION.md`、`frozen/` 和 `receipts/` 保留exp855及更早资产的历史身份。
当前正式模型的身份和成绩以exp858发布记录为准。

| 训练来源 | 全量拟合记录数 |
| --- | ---: |
| eda-mixed-v0 | 100,000,000 |
| eda-mixed-v1 | 100,000,000 |
| eda-classified-test-a | 100,000,000 |
| 远端role-1b分层exact样本 | 3,833,856 |
| 合计 | 303,833,856 |

全部记录进入最终拟合，端点对去重后共有303,833,716对。
四个来源分别归一化权重，源端点哈希分组用于内部参数选择。
最终物理残差头采用Huber=1、ridge=64、12轮，固定后在所有记录上重新拟合。
classified-test-b的标签只用于模型冻结后的最终评分。

名义模型从52个源角色的认证距离场选择插值参数，然后为208个源角色生成观测点，
重新训练120组分级量化码本。四来源的完整角色和空间统计共同参与权重计算。
新压缩帧预算为93,000,000 B，最终832帧合计92,951,277 B，
覆盖28,753,920个编码键。六张插值表、`speed/smallplan.inc`、
`shared/frameBytes.inc` 和 `speed/g4.h` 随资产同步更新。
`arch.bin` 的五份架构JSON保持原始无损数据。

离线工作目录在l7：
`/home/lhj/lhjwork/eda2026/research/exp858-diverse-models/`。
该目录保留完整数据、特征、训练中间结果和冻结候选。
原始归档在项目 `doc/生成数据400m/`，数据身份见主仓
`validation/results/exp858-diverse-models/training-data-identities.json`。

主仓的训练入口如下，`WORK` 应指向新建的远端项目工作目录。
既有训练任务和数据应按完成收据复用，避免覆盖历史产物。

```sh
python3 validation/exp858_prepare_nominal.py --root "$WORK" --jobs 12
python3 validation/exp858_fit_knots.py --root "$WORK" --statistics \
  "$WORK/statistics/mixed-v0.json" "$WORK/statistics/mixed-v1.json" \
  "$WORK/statistics/classified-a.json" "$WORK/statistics/remote1b.json"
python3 validation/exp858_train_aq.py --root "$WORK" --jobs 12 --frames-budget 93000000
python3 validation/exp858_finish_training.py --root "$WORK" --threads 12
python3 validation/exp858_training_overlap.py --root "$WORK"
```

准备目录时需放入 `source/` 正式源码、`repro/` 本复现工具包、`tools/` 训练脚本、
`data/` 四来源完整紧凑记录与B端点键、`statistics/` 四来源统计。
具体输入路径和格式以随版本保存的 `evidence/training-tools/exp858_*.py`
及训练收据为准；B端点键只用于交集统计。
训练依赖和版本见主仓 `nominal-training/environment.lock.txt`。
离线训练允许并行，交付程序使用单线程。

最终B完整100M Acc为98.279501246106%，相对exp855增加0.008975336256个百分点。
排除124条训练重合请求后的Acc为98.279502369702%。
改善低于本轮预期的0.05个百分点，总体Acc仍低于99%目标。
B结果已观察；进一步依据它修改参数时须另用新验证请求。
新ELF为98,304,088 B，五次B完整运行一致、RSS和输出契约检查通过。
用户提供的完整exact标签用于评分，其原始求解器运行记录尚未核验。
