# 实验130 A1 C2 Zstandard静态恢复与验收

2026-10-09，Asia/Shanghai。分支`research/exp130-zstd-static-restore`，起点`81cf711`。开工`/dev/sdd`可用464G。协议先于新恢复实现与计时结果提交。

## 固定候选与影响范围

唯一候选使用实验129按字节选出的19级流58,017,384 B，SHA为`01695d1fdbea811b7fd2411b8c86c6a16b8546af7a7faad8317cfe476d7e2e78`。保留当前生产dx逆映射、完整int32表、depth10模型和查询逻辑，替换压缩解码器并静态链接已安装libzstd 1.5.5。候选源码复制到`build/exp130/candidate/src/`，正式源码和产物先保持exp120。

直接消费者为`embedded_residue::restore`、`ResidueEstimator::buildTables`及表恢复夹具。新压缩器的异常路径、组件计时和静态产物需要验证；架构、模型、CLI及输入数据沿用冻结版本。构建生成器与两份正式构建脚本在候选通过后进入独立接入实验，避免将发布改动混入容量选择。

## 验证与固定门槛

先核对完整460,062,720 B恢复表SHA，沿用signed/INF、轴归零及三种shape夹具。新解码器核对单帧、内容大小、checksum与精确EOF；小夹具覆盖损坏checksum、截断、尾字节、错误内容大小和表entry count。六种既有CLI边界配置及3,107行holdout完整SHA保持。

实际静态候选须严格小于100,000,000 B，相对exp120减少至少30,000,000 B，动态依赖为空。组件计时固定CPU3，同机串行，一对预热加10对交错测量。计时探针单独记录分配、解压、dx逆映射CPU；首要恢复总CPU包含分配、解压和逆映射。差值采用候选减基线，配对t区间用df9。总CPU均值≤+0.05秒且95%区间上界≤+0.15秒，峰值RSS≤2,000,000,000 B、单进程wall≤3,600秒才继续完整1M。

组件通过后，unique、公开和repeated各做一对预热及三对交错完整1M。复用已有输出契约工具，逐行核对端点顺序、恰好3字段、整数delay、精确EOF、完整SHA、多次运行一致和负值位置；每次单线程、RSS≤2GB、wall≤3600秒。查询表、源码逻辑和输出相同，完整负载CPU作为当前实测证据报告，容量与组件门槛决定本轮选择。repeated记录1000 distinct和999,000 cache hits；unique与公开记录实际distinct。

正式接入要求上述容量、完整表、组件和三个1M契约/资源检查全部通过。失败时保留固定候选与证据，正式exp120继续使用原版本；A1/C2及其他路线图方向保持开放。平台1B与跨架构泛化继续由对应数据验收，本轮保持纯部署等价。

## 证据与复现

冻结当前源码、私有补丁、探针、已安装头文件与静态库、exp129 frame、完整表身份、五个架构、正式基线、六种边界输入、holdout及三个1M输入。结果写`validation/results/exp130-*`，私有构建写`build/exp130/`，原始文件拒绝覆盖。

```sh
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp130_zstd_restore.py --stage build
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp130_zstd_restore.py --stage component
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp130_zstd_restore.py --stage timing --workload unique
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp130_zstd_restore.py --stage timing --workload public
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp130_zstd_restore.py --stage timing --workload repeated
```

组件CPU补充实验129尚未拆分的恢复计时。收尾按完整SHA、可重建命令和文件引用检查清理重复输出，保留候选、frame和原始计时。

## 构建启动记录

实现提交`548d3b3`首次编译失败。生成数据头文件的f-string把两个闭合花括号输出成一个，命名空间缺少闭合。该次只有构建启动，算法结果与新CPU尚未产生；已把目录保留为`build/exp130-start-failed/`，原冻结证据改存`validation/results/exp130-failed-start-frozen.json`。修正为独立字面字符串并通过生成头文件的C++语法检查，固定候选与验收条件保持。

## 结果与判定

修正后的候选提交`9e551ed`，静态文件为`68,201,104 B`，SHA为`aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c`，相对exp120减少`31,551,488 B`，距离100,000,000 B上限余`31,798,896 B`。`ldd`确认无动态依赖。Zstandard frame为单帧、精确EOF、内容大小230,031,360 B，checksum损坏、截断、尾字节、错误内容大小和二帧拼接均被拒绝。

候选恢复出的完整宽表为460,062,720 B，SHA为`800dcf4af93e6fe5a298d239479ebc84c12a06fc1ae7712e9f194e4cff347e40`。signed/INF、三种shape、六种CLI配置和3,107行holdout均与exp120逐字节一致。

组件恢复计时采用CPU 3、1次预热加10对交错运行。候选减基线的总恢复CPU均值为`-0.5136671 s`，95%区间`[-0.5941307,-0.4332035] s`，峰值RSS候选`749,035,520 B`，组件门通过。拆分均值显示解压CPU从`0.7588125 s`降至`0.3092098 s`，dx逆映射从`0.1319196 s`变为`0.1313559 s`。

三个完整1M负载都通过行数、端点顺序、三字段、整数delay、精确EOF、完整SHA、单线程、2 GB RSS和3,600 s wall检查，各自输出SHA等于exp120。unique有1,000,000个distinct，CPU差`-0.200000 s`，95%区间`[-0.762645,+0.362645] s`；公开有1,000,000个distinct，CPU差`-0.183333 s`，区间`[-0.245849,-0.120817] s`；repeated有1,000个distinct、999,000次cache hit，CPU差`-0.460000 s`，区间`[-0.568281,-0.351719] s`。三个负载计入候选与基线的最大RSS为823,156,736 B、最大wall为22.92 s。`measured_1m_score_gate`保留已有CPU筛选公式的诊断结果；本轮预登记容量与组件门通过，完整负载的预测等价与资源门也通过。

原始证据为`validation/results/exp130-build.json`、`exp130-restore-timing.json`、`exp130-timing-unique1m.json`、`exp130-timing-public1m.json`、`exp130-timing-repeated1m.json`及`exp130-candidate-identity.json`。exp130候选已通过本地接入门槛，正式源码、构建脚本和提交包仍待下一次独立接入提交；在接入完成前正式exp120不变。

## 审查

Herdr环境快照显示`HERDR_ENV`为空，按`build/exp125/herdr/SKILL.md`停止受管控制；直接pi的`opencode-go/deepseek-v4.1-flash`、`max`只读审查完成。审查原文与环境见`validation/results/exp130-pi-review.md`和`exp130-review-environment.json`。

| 主张 | 核对与处理 |
| --- | --- |
| 容量、完整表、组件及边界通过 | 原始JSON和实现支持，采纳 |
| 日志需写回组件状态 | 支持，已更新日志、路线图和理论索引 |
| 完整1M尚未开始 | 审查读取的状态过时；本节采用三个完成报告，复核24次完整输出与资源 |
| 新余量使用实际31,798,896 B | 支持，后续预算采用实际静态文件 |
| 现有10/20场与模型扩容候选可直接使用 | 现有容量与失败精度证据阻止接入；保留方向和候选证据 |
| 任何固定坐标场无生产价值 | exp116固定场命中0、exp117任意20键上界0.323703%，仅限已测开发分布与固定20键；其他选择继续研究 |
| dy场改Zstandard可能装下 | 未测假设，精度和端口候选质量仍需独立验证 |
| 流式恢复可省临时内存 | 当前2GB资源充足，该建议缺少现行触发需求，保留现有两向量 |
| 工具中的脱敏占位符影响文件 | 磁盘JSON合法，差值重算一致；屏幕数字遮罩保持显示问题 |

## 空间与副本

exp129的重复往返副本已按完整SHA核对并删除，释放690,094,080 B，归属实验129。exp130逐个核对三个1M基线输出与同负载候选完整SHA相同，保留候选输出，按清单清理基线副本121,181,723 B；清单和重建命令见`validation/results/exp130-cleanup-plan.json`。收尾`/dev/sdd`可用463G，本轮新增候选、静态探针和冻结源码占用计入空间差。当前正式包及`subm/latest/`仍指向exp120。
