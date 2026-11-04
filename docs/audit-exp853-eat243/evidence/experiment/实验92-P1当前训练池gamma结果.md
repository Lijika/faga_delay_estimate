# 实验92：当前训练池 gamma 单变量结果

日期：2026-09-27。状态：P1 通过，已接入正式源码与新不可变提交包。

## 接受条件与冻结对象

- 基准：exp90 `subm/versions/exp90-row-load-65952db-dirty`，bin SHA `fc6ccc544c802d1da01081d3460939f07bdede34eee22fdee85b0f30e1f64aff`。
- 训练池：46,505 行可达 exact；47 维 base 特征；目标 `exact-fast`；128 棵、depth 8、`reg:absoluteerror`、`eta=0.1`、seed `20260919`、单线程。
- 候选唯一变化：XGBoost `gamma=1.0`，control 为 `gamma=0`。统一输出偏移固定为 `-3 ps`。
- 独立窗口：affine unique `[36M,38M)`；2M 请求、每带最多 1,024 条 exact 标签；probe 为冻结 `query_profile_exp18b --pdb-only --dedup-endpoints --landmarks 8`；bootstrap 10,000 次、seed `20260925`。
- 冻结输入身份：模型 `6904544684efacfb0bbb80ae7340900bd8c6888e7993f6146351b15985ba338f`；FAST `a80595dd4ecd933da5ea46dc6293df33b912d77dc716ef1fcfbb6b047b8211c`；BASE `d66c067658a7e7ad92edc5cc0351119661543648c61adaa3682779df390c45c5`；probe `613139d1b2d3363f1909c2d4a15dbe31c61fa8592732afc8ed5136e26b2730e5`。

## 数据与精度结果

请求和采样命令：

```sh
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage requests
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage sample
build/venv-ml/bin/python validation/exp92_p1_gamma.py --stage score
```

- 38M 请求生成阶段耗时 79.211 s，历史 4M/6M/8M/10M 前缀逐行匹配，生成器身份一致。`unique-38m.csv` SHA `3d52215579712976fcdbb5d38f87ad970f26db2cb8a438c42678e7cb89e4127a`。
- probe 扫描 2M 行耗时 542.403 s，保留 6,177 行；七带覆盖完整，历史排除集及实验91样本命中 0，距离和带交叉检查通过。
- control accuracy `96.394478%`，MAPE `0.917779%`。
- gamma1 accuracy `96.426573%`，MAPE `0.909521%`。
- 增益 `+0.032095 pp`；paired bootstrap 95% CI `[+0.016312,+0.048297] pp`；false finite 和 reachable false unreachable 均为 0。四项 gate 全部通过。

评分证据：`validation/results/exp92-p1-score.json`，SHA `d1cabb2b76a32d7ac7d06bb116674c274b5bdf722ea15a894ae5baa318eb1edd`。

## 私有部署与性能

gamma1 模型导出为固定 depth-8 静态树表，模型头 SHA `f0c77cfba202298bd620c6433a77dc5d219870ea275e6e133b7f9c6064f751d0`；512 行浮点遍历位级等价检查通过。私有 C++ 二进制在 6,177 行新窗口输出上与 Python gamma1 加 `-3 ps` 逐行一致。

3 对 1M unique 计时命令由 `validation/exp92_timing.py` 固定，输入 SHA `2cf587f1b27ccc5699040e64ea3efc6eb68c100cfd72a36cad383383a018d7bd`。candidate 减 exp90 baseline CPU 差 `[-0.25,-0.18,+0.17] s`，均值 `-0.087 s`，95% CI `[-0.646,+0.472] s`；两侧每轮 1,000,000 行、负值 17,585 行、单线程，candidate 最大 RSS `572,157,952 B`。按正式偏移口径，综合点收益 `+0.026398`，保守下界 `+0.009114`。

## 正式构建与验收

```sh
ALGO_VERSION=exp92-gamma1 VERSION_LABEL=exp92-gamma1-384b9bf-dirty sh scripts/build_submission.sh --verify
build/venv-ml/bin/python validation/exp92_package_check.py
```

新不可变包：`subm/versions/exp92-gamma1-384b9bf-dirty/`。

- bin SHA `607b52e80cb6dad8905e4c46ff3ed45fa7670730b165e3ca995e34c97c837c63`。
- zip SHA `fec2d63ad9da8475b7420efc9f983dd69f2ca92e1a007e88b68c2d6e6e76ae68`。
- 公开 1M 输出 SHA `4ea85e2a03d288a4e5cffd6c5bb81fddb1772f9838a2fada9010843eb7e20cdf`；holdout 3,107 行输出 SHA `195aad0bdc6473c5587a11817bf105b91fb30cfab64e29f727205e085703b2b4`。
- 包验收最大 RSS `570,368,000 B`，最大 wall `26.12 s`，单线程，公开 1M 两次和 unique 1M 一次全部通过。

正式根入口、`build/submission/estimate`、`subm/latest/` 和 `subm/submission.zip` 已同步为该包身份；exp90 历史目录未修改。按约定本轮未运行完整 1B，平台隐藏集成绩以实际评测为准。

## 收尾

开工可用空间约 483G，收尾约 481G。新增 38M 请求是可重建原始输入，按名保留以支持复核；未删除其他实验文件。P2 的 residue exact 回退仍关闭：理论审计显示纯 residue 启发式在真实跳格边上不可采纳，未进入生产路径。
