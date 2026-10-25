# 实验678 H/V事件共享替换专家与容量消融

2026-10-24，查看本轮结果前登记。正式版保持exp655，静态ELF
93,398,296B、SHA d9a8194584b644ffa331d31a8713a39f559b881a1fe40e8f0dce4d4ad8ff58dd。
其完整1B CPU243.434110秒、同次分层样本Acc98.647508422%，
当前最终速度与精度目标继续待达成。

## 假设与接合位置

Gemini4第2.2、5.1和6.2节提示将容量集中到物理事件。exp677确认
H是横向同Block行带跨越，V是中央列带中必须离开再返回的事件。
两者互斥、合计2.0677%；地图标签干预约0.118pp属于离线空间。
本轮沿用生产曲线背景和mandatory，普通区域沿用原S8，仅在H/V
事件内直接替换残差模型。每事件跨原16route共享，避免V再切分
后的低支持度。8树与64树用于区分共享模型和容量效果。

exp614仅限定旧D64/R8增广；exp631限定Q4/R8、20路跨列带、
53特征与8树；exp656限定原16路匹配S8；exp658支持保留真实背景
补偿。上述失败证据继续保留各自表示、数据域与资源范围。

## 固定方法与数据

- 复用exp593全端口开发缓存，1,000,000行、59,904端口对。此为
  历史开发数据，完整程序测试只新增100M与1B。
- 复用原source-pin隔离三折。H/V每折train至少1,000行、test至少
  500行，先核对支持度和cluster无交集，再训练。逐事件逐折报告
  源/目标端口、端口对及原route覆盖；不要求每事件覆盖全部端口对。
- 特征固定为原53列、exp614.geometry的16列、exp677定义的中央
  阻挡行带数和中央列带端点数，共71列。仅使用可在线计算的量，
  无真值、名义oracle、旧OOF响应或旧模型误差特征。
- 目标为d0-current_curve_base，权重1000/max(d0+mandatory,128)。
  current_curve_base调用exp677.curve_base，包含Q4恢复和生产曲线。
  每个outer fold的训练完全由其他折的原始标签与固定背景构造。
- CatBoost1.2.8，MAE、Exact叶估计一次、SymmetricTree、depth4、
  learning_rate0.3、64树、Plain、No bootstrap、boost_from_average
  false、random_strength0、border_count256、l2_leaf_reg1、
  score_function L2、seed20261024678、CPU单线程。8树为其固定前缀，
  无早停、无其他参数或前缀选型。六个模型共384棵树。
- 候选固定为H8、V8、HV8、H64、V64、HV64。互斥事件使组合增益
  等于单项全局增益之和，评估脚本必须检查该恒等式及普通区逐行相等。
  原S8的旧OOF输出仅作独立配对对照。
- 复用exp640的JSON独立解码函数，核对native叶编号、float64树序
  求和及最终整数输出。固定阈值在整数特征上严格等价；不量化叶值。
  历史基线整数exact行数严格相同，聚合浮点指标容许1e-10差值，
  同时保存历史值与当前NumPy值。

## 统计、资源与停止条件

主指标为真实truth上的官方Acc配对差，按26个源族整族重采样9999次，
seed20261024678，对六个候选采用Bonferroni同时95%区间。另报告
MAE、变化行、改善/恶化行、原精确行损失、H/V、distance、near_axis、
方向、原route、fold和源族分组差。

开发质量门为全局Acc增益至少0.01pp、同时区间下界>0、distance及
near_axis组最差差值>=-0.03pp，且被替换事件内点估计均>=0。
通过者按全局增益最大选一个，完全相同则按期望树工作量较小、
名称字典序决胜。其余候选保存证据。离线总CPU<=600秒、
wall<=900秒、峰值RSS<=2,000,000,000B，新增文件<=50MB。
任一自检、支持度或资源门失败即停止本轮扩大。

若质量门通过，另冻结通用静态CLI构建和全端口未知非重复100M
配对协议，联合收益95%下界>0且点估计>=0.005、资源与输出契约
合规后及时阶段接入并完整测1B。100M成本只作筛选，1B正式记录
使用同次完整运行CPU与输出的分层exact评分，最终Acc须>99%。
归档传输结束前保持离线训练诊断，CPU配对计时串行执行。

## 范围、命令与证据

本轮修改仅涉及validation/exp678_hv_replacement.py、本协议及
validation/results/exp678，模型位于远端research/exp678/build/exp678。
exp677/exp614/exp640帮助函数、冻结数据、生产source及正式包保持。
不新建外部依赖。理论笔记为Obsidian的
[[低频拓扑事件共享替换专家的监督隔离与容量分配]]。

远端所有命令从~/lhjwork/eda2026进入。复用exp491的venv，
PYTHONPATH指向research/exp640/build/exp640/pydeps，
OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=1。在research/exp678执行
`python -u validation/exp678_hv_replacement.py`，内部记录已安装API
帮助、全部输入身份、自检、支持度、训练、评分、资源及空间变化。
开工本地/dev/sdd可用328GiB，远端15GiB；本轮不新增大CSV，
不删除用户手动移除的.bin，也不恢复它们。
