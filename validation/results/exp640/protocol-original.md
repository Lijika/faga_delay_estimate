# 实验640 Q4残差的对称树预算与独立解码

2026-10-23。状态 `PREREGISTERED`。在查看新候选结果前登记。
正式交付exp610，研究比较基线exp622/T；接续exp639完成后的独立机制。

## 问题与主假设

Gemini4第2.3、6.4节的同层共享split可以消除树内路径依赖。exp626已经
检验的是普通树全节点比较；本轮重新训练对称树，检验容量损失和计算成本。
保留D64/Q4、真实首Net、53整数特征、16路身份、目标、权重及输出舍入。
CatBoost和XGBoost的训练器共同改变，结果归属于训练结构族替换。

## 冻结候选与数据

- A为Q4与原R8，exp622/T数值函数。M为exp631/M的匹配Q4重训对照，复用原始raw。
- S8/S16为每路8/16棵depth4对称树。一次训练16棵，前8棵作为S8；不选择其他前缀。
- CatBoost固定1.2.8，CPU、Plain、SymmetricTree、MAE、Exact一次叶估计、
  learning_rate=0.3、border_count=256、l2_leaf_reg=1、bootstrap_type=No、
  random_strength=0、boost_from_average=False、score_function=L2、
  random_seed=20261023640、thread_count=16。训练并行仅用于离线拟合。
- 目标为`d0-base`，权重为`1000/max(d0+mandatory,128)`，均沿用float32输入。
  baseline和候选分别保留本身的叶值精度；S使用JSON的double叶及原树序double求和。
  量化、两树融合、改变求和次序作为本轮范围以外的独立改动。
- 复用exp631.load的开发1M，source-pin三折隔离，各折及补集覆盖59,904端口对。
  这批请求已反复查看，属于开发数据。当前验证支持同架构开发筛选。
- 独立JSON解码核对全部折外叶编号、raw最大差及整数输出。解码按模型记录的
  feature_index到flat_feature_index映射，split采用`x>border`，第j层位权`2**j`。
  所有特征须有限且为整数，scale=1、bias=0，只允许数值split。

## 指标、统计与停止条件

查看模型结果前固定两个继续条件，均对A比较。

1. 精度路径要求ΔAcc≥0.02pp、同时区间下界>0，distance和near_axis各组
   ΔAcc≥-0.03pp。
2. 速度路径允许总体ΔAcc≥-0.05pp、同时区间下界≥-0.08pp，各distance和
   near_axis组ΔAcc≥-0.15pp。仅获得完整程序计时资格，后续仍须联合收益通过。

统计沿用26个source-family簇、9,999次bootstrap，seed=20261023640。
S8/S16相对A/M共四个比较，以Bonferroni分位点0.05/8和1-0.05/8报告
同时区间；精确行变化、MAE、distance、near_axis、direction、forced及各族另列。
M对A仅辅助解释背景重训，独立模型解码失败时保存反例并停止评分。

合格者才生成通用静态C++完整程序，先独立核对解码和1M输出契约、资源及确定性。
固定1次预热、12轮正逆交错配对，选型用联合分点值≥0.005且95%下界>0；
1M CPU折算1B只作筛选假设，初始化成本分别报告。相同硬件串行运行。
候选冻结后以新source-pin隔离的未知非重复1M及完整10M、100M确认。
每次扩大前重述主要成本及收益机制；通过后及时接入正式版，并完整实测
全端口覆盖非重复1B。正式最终Acc严格>99%和全部交付限制继续有效。

所有候选质量门失败时结束当前预算配置；记录限制范围，保留其他深度、
训练目标、路由与量化的独立资格，不在已查看结果上追加预算。

## 命令与身份

所有拟合、解码和评分在`r9r4900:~/lhjwork/eda2026/research/exp640`执行。
私有依赖安装在`build/exp640/pydeps`，复用exp624的XGBoost3.0.5用于读取旧模块。
安装命令、版本及wheel身份见`validation/results/exp640/dependency-install.*`。
驱动为`validation/exp640_symmetric_residual.py`，按`prepare`、`train`、`evaluate`执行。
prepare保存协议副本、源码、数据、模型、背景、二进制及依赖身份。

## 理论与来源

理论笔记为Obsidian的[[对称残差树的独立比较与叶序保持]]。
官方资料为CatBoost的tree growing policy、common training parameters、
save_model和JSON model tutorial；Context7已核对。旧R手册的GPU限定与
现行CPU文档不同，本轮以安装的1.2.8 API和实际CPU训练共同核验。
普通网页读取返回空内容，资料读取使用Context7官方文档索引。
不采用Gemini4的加速倍数、零额外成本和预计Acc作为已测证据。

## 成本与空间

开工本地`df -h /dev/sdd`可用351G，远端可用约16G。当前不生成大型CSV。
收尾记录实际CPU、RSS、空间及清理；明确未验范围。
