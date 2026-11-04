# EDA2026 当前算法与实现

2026-11-04 stage `exp853-eat243-lossless-directory-20261104` publishes the Main-accepted lossless243 representation, with176 as parent. ELF86,937,624B has SHA-256`69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02`. The33-file source snapshot has canonical SHA-256`c799b57b0a4b88d9ea61fb8c5af0623655238236108fc34ac1bec3f2cfc4d3f8`; the source producer is private commit`e0a7a86aaec8b0939974c90456eb36439a63d6e4`. All five exact generated payloads79,398,908B, static zstd library/header/license, original assembly, actual compiler argv and standalone replay accompany the immutable version.

The registered exposed-development r9 CPU8 comparison measured parent/child complete1B meanCPU128.60633816666666/125.208939s; saving3.397399166666659s, composite gain0.028311659722220384 and registered joint one-sided95% lower0.02069454135805846. All14 full outputs match; 3,833,856 exact samples over59,904 role pairs give unchanged Acc98.85534283747039%. Full-output SHA is`0a19ea6494a4bf9f12bb70c5f52677e326ea67429616649f55d0228c5767ef9e`. The timing bound conditions on three registered blocks and measured host state.

The published version carries the actual-ELF complete1M empty-environment/clean-cwd receipt; the host filesystem namespace remains visible. The version is installed before INDEX and root/build/latest mirrors; submission.zip is the last pointer. The exact formal source is the immutable version's `source/` snapshot; ordinary dirty root sources and HEAD have independent identities. Use this version's `REPRODUCE.md` and `rebuild.py`. Official platform, official consecutive-five protocol, fresh hidden inputs, all-row exact accuracy, Acc>99% and approximately100s CPU remain open. The historical text below retains its original date and identity.

2026-11-02当前阶段为`exp853-eat176-direct-curves-20261102`，上一阶段117保留。
EAT176只在普通路径的已覆盖pair/context键上，把两次依赖A/B曲面读取替换为一条552格完整名义曲线读取。
33,280个键与曲线来自冻结架构数据，按完整方向和residue上下文进入既有目录；
事件与cycle分支恢复原word，其他请求沿用117函数。两项direct资产压缩后共2,436,789 B，全部212项资产嵌入单ELF。

算法提交`f8fec07c54b3bcf5a1fbeda9ef41046f513528a1`与32项编译输入manifest`fb09f4758e60407c36550db622bbdf6be10ebf98f8595769176cfd39cbaa4586`绑定。
实测静态ELF92,848,152 B，SHA`f8b71580262a3088d7f4e15287dda9d90be586105eaf80a0d4411f3d93c4a689`；版本内保存全量源码、212资产、两份历史driver及真实编译命令。
在可写副本中使用`EDA_ASSET_DIR="$PWD/assets" python3 -B build_native.remote.py`重建；
字节复现使用记录的GCC11.4.0、GNU ld2.38及Ubuntu22.04静态运行库。main HEAD、普通构建与该冻结来源分别记录。

完整1B平均CPU128.488276→127.10981016666666秒，抽样Acc98.85481661610247%→98.85534283747039%；
联合分增量0.011908192372118265、单侧95%下界0.005365878152688194。
实际发布ELF的完整1M清洁目录输出逐字节复现已验候选，各臂七次1B完整输出一致。
官方平台、连续五次协议、未知输入、全量exact及最终99%/约100秒目标继续待验。
以下内容保留各历史阶段的来源与结论。

2026-11-02，当前阶段为
`exp853-eat117-rawzero-parser-20261102`。父版本为`exp853-eat097-parser-eat112-20261102`，源码只修改`src/worker.cpp`：
`event679`返回0的无事件普通分支不再计算`symmetric640(...)`的raw修正，
直接使用0.0；非零事件仍由`replacement679(...)`计算，`event==1`的forced
bias、surface base、mandatory项与最终取整保持。该替换去掉了普通请求的
一组依赖查表，并把质量代价限定到该分支。

完整1B平均CPU由143.072572秒降至128.77176066666667秒，节省
14.300811333333334秒；同次3,833,856条exact样本的Acc由
98.88506734641447%降至98.85481661610247%，变化
-0.030250730312830036个百分点。综合分点值增量0.0949728435281827、
联合单侧95%下界0.0726986999684377，收益来自CPU节省。候选六次CPU样本
标准差0.2659525594730546秒、范围128.506809至
129.273615秒，仅描述
本轮r9 CPU8条件。

不可变版本的源码来自经审核的实测32文件快照，private integration commit为
`2d7c5625ff2da531bd37d249b5540a8c4940c6a2`，canonical manifest为`30e34ab81535b73c84862a1622aefb972a3d74c8cde923cd7f7c5e52de8c9383`。
静态ELF 90,411,032 B，SHA-256为
`8b80103cecfe7425f780f4e3497994fe55312186ec4bc80ab1ac57669241ca57`；发布ZIP SHA-256为
`4936fe0d26e894849bec33de58049191fdfe511eef4ba1f9010849215543dd57`。
根入口和`build/submission/estimate`由不可变版本硬链接刷新；普通源码HEAD、
`scripts/build.sh`及更早的普通构建声明身份保持独立，不能把本实测身份归给HEAD。

该结果覆盖一个已暴露的非重复U-role 1B输入、同输出3,833,856条exact样本、
七次/臂完整输出检查和全部1B契约；未知输入、全量exact、Acc>99%、约100秒、
官方平台和官方五次一致性仍未验证。

2026-10-30，上一阶段为
`exp853-c1e2b03-prefetch-batch32-1b154s-20261030`。
保留exp825全角色对曲面与残差函数，批量增至32条，在整批prepare之后
预取两个依赖曲面表再完成计算。完整输出与exp825相同。
直接100M各四次平衡对照平均CPU从15.717331降至14.05001575秒；
十二次同身份1B平均CPU154.18683675秒，抽样Acc98.88162871837434%。
静态ELF90,509,336 B，单线程，最大观测RSS270,303,232 B。

候选源码冻结于`../EDA2026_EAT/candidate`提交`c1e2b03`；
按不可变版本的`version.json`和`evidence/SOURCE_INTEGRATION.json`
指定的r9资产与构建命令复现。封装使用
`validation/exp853_c1e2b03_package.py`。根入口、提交包和构建镜像已同步，
本仓`scripts/build.sh`继续构建历史源码，其产物须另行验证。
清洁目录100M与既有十二次1B确定性证据核验通过；最终精度与CPU目标、
官方平台及连续五跑协议仍待验证。

2026-10-29，上一阶段为exp825。码本构造覆盖全部59,904角色对，
每对两条上下文，使用exp822固定B1R0及exp824完整目录；
保持A2048/B256码本容量、32位目录、四阶段批8和原残差。
构造分布与样本量共同改变，收益归于整个数据方案。
静态ELF90,509,336B，新100M抽样Acc98.883090386%，
配对提高0.037701809pp；六对平均CPU15.667661833秒，
联合至少95%收益下界0.024187115为正。
同轮完整1B CPU160.776248秒，基线164.639206秒；
3,833,856条同次exact抽样Acc98.881628718%，提高0.039949103pp。
完整契约、确定性、单线程资源、清洁目录100M及独立审核通过。
1B单对计时，精度为分层抽样估计；最终99.1%和约100秒、
官方平台继续待验。构建为`validation/exp825_surface_cli.py build`，
目录构造为`validation/exp824_balanced_directory.py`，
发布为`validation/exp825_package.py`。不可变版本为
`exp825-balanced-surface-1b161s-20261029`；普通`scripts/build.sh`
继续构建历史源码，其产物须另行验证。

2026-10-29，上一阶段为exp811。冻结exp806的批8四阶段、A2048/B256
完整曲面码本和原残差，仅将目录中的尾锚偏置改为名义评分权重下的
受限整数中位数。全28,753,920条记录高位码保持，低10位范围保持；
在线字段、读取次数及数值运算次序保持，目录压缩增加4,329,509B。
静态ELF89,268,248B。新100M提高0.016860776pp至98.840391528%，
六对平均CPU15.624470秒，联合95%门通过。
完整同轮1B CPU160.287954秒，基线160.234773秒；
3,833,856条同次exact估计Acc98.841679616%，提高0.017129286pp。
独立审核、完整SHA和清洁目录100M通过，已发布阶段包。
精度为抽样估计，1B计时为单对；最终99.1%和约100秒、官方平台仍待验。
专用构建为`validation/exp811_offset_cli.py build`，目录构造为
`validation/exp810_offset_directory.py`，发布为`validation/exp811_package.py`。
不可变版本为`exp811-offset-surface-1b160s-20261029`；
普通`scripts/build.sh`继续构建历史源码，其产物须另行验证。

2026-10-29，上一阶段为exp806，在exp780的固定批8内依次完成整批prepare、
整批目录word读取、整批finish和按序writer。新增word使用原padding，
Prepared596保持56B；逐请求与组件入口同时遵守stage后finish的顺序。
完整曲面、模型、浮点链和舍入保持，1,057,664次组件比较、
14次100M和同轮配对1B的完整输出均与exp780相同。
静态ELF84,938,776B，100M六对平均CPU15.704630667秒；
同轮1B CPU153.829989秒，比exp780少7.790437秒，单对计时无区间。
同输出3,833,856条exact样本Acc98.824550329%，单线程、
清洁目录完整100M和独立审核通过。当前目标为Acc>99.1%且留余量、
1B完整CPU约100秒；平台待验。专用构建为
`validation/exp806_batch_pipeline.py build`，封装为
`validation/exp806_release.py publish <新标签>`。
该阶段不可变版本为`exp806-surface-batch4-1b154s-20261029`；
普通`scripts/build.sh`继续构建历史源码，其产物须另行验证。

2026-10-27，上一阶段采用exp779完整曲面背景，由exp780验收和打包。
每pair×context保存一个uint32目录记录，恢复单元偏置与四方向
2048/256双码本的552点完整函数，在线删除N512/D64点积、尺度、
center及旧曲线查表。启动从ELF展开115015680B目录与10174464B码本，
所有架构与模型自包含；保留首段、Line、mandatory、cycle和输出合成。
普通人口使用16组T2D6坐标掩码，H/V分别匹配8树depth6/depth4。
通用静态ELF84938776B，100M平均CPU15.959997500秒、
同次抽样Acc98.825237844%，较exp728同时改善。完整资源、契约、
七次一致和清洁目录验收通过；完整1B同轮CPU从181.859664降至
165.039292秒，3833856条同次exact Acc98.824550329%，提高0.179650681pp。
1B采用磁盘输入和memfd输出，十亿行契约、归档恢复及独立审核通过。
封装入口为validation/exp780_release.py，身份见subm/latest/identity.json。
普通源码构建仍为历史路径，当前阶段制品与其构建身份分别记录。

2026-10-27，exp760按赛题补充信息修正主请求范围，根入口与包指针恢复
exp728坐标掩码阶段版。主请求使用208个非I源、288个目标，保证有向可达、
排除自查询；I*扩展适配保留为历史诊断。exp728沿用D64曲线、T2D6和V8，
加入编译准备、融合CSV与坐标掩码；静态ELF93,442,072B，完整U-role 1B
历史CPU184.190953秒、抽样Acc98.644899649%。当前研究目标按用户goal为
1B完整程序CPU约100秒，越快越好，同时Acc>99%并留余量。
身份见`subm/latest/identity.json`，范围核对与恢复证据见`validation/results/exp760/`。

2026-10-25历史阶段包与根入口`./estimate`采用exp704/C，由exp706接入。
背景、模型及数值顺序沿用exp688，仅将全部496端口名的2048槽线性探测
改为688槽直接目录，查询继续核对完整首尾键和名字长度。829,072项解析
组件对照及十四次完整100M输出一致；六对CPU平均节省0.785568秒，
95%区间[0.684197,0.886939]秒。静态ELF93,380,632B，清洁目录空环境
100M通过。完整1B已登记待执行，精度99%与1B尽量100秒继续研究。
专用封装入口为validation/exp706_package.py，身份见latest/identity.json。

2026-10-25上一阶段包与根入口`./estimate`采用exp686/N，由exp688接入。
背景沿用exp655的D64加字节曲线，普通区保持S8；纵向走廊V事件采用
共享八树专家，直接学习含背景补偿的目标，保持source-pin折外监督。
专家使用独立函数，公共prepare596栈帧由原V8的248B降至184B，
安全编译选项和模型数值顺序保持。其完整100M与原V8输出逐字节相同。
静态通用ELF93,402,392B，完整全端口非重复1B CPU243.302538秒、
RSS206,372,864B、单线程、完整输出契约通过。3,833,856条同次
exact样本Acc98.658061657%，较exp655扩大评分提高0.020594343pp。
最终Acc>99%与1B完整程序CPU约100秒继续研究。身份见subm/latest/identity.json，
专用打包入口为validation/exp688_package.py；普通源码构建身份另验。

2026-10-24上一阶段采用exp654/B，由exp655接入。
保留近域rank512、远域四方向rank64点积与冻结S8，使用一个
pair/context的uint8码选择共享二维距离残量函数。代码本保留全部
542个商位移点，四方向各256条曲线；原始int16值范围[-55,59]，
在线以uint8加固定origin=-55完整恢复。单元码28,753,920B，
共享曲线555,008B。D64资产在ELF内Zstd编码，启动单线程恢复原
INT8因子/尺度分表；查询算术、S8的double树序与两个整数恢复位置保持。
实际静态ELF93,398,296B，通用x86-64/SSE2、自包含与单线程通过。
完整新100M分层Acc98.636446981%，六块平均CPU23.365922333秒；
相对原S8提高0.191319140pp并新增CPU1.274042500秒，联合门通过。
21次三臂输出与资源、清洁目录空环境100M均通过，完整全端口
非重复1B CPU243.434110秒、RSS206,045,184B、单线程与完整契约通过；
同次分层样本Acc98.647508422%，最终Acc>99%继续研究。身份见latest/identity.json，
专用封装入口为validation/exp655_package.py，普通源码构建保留历史路径。

2026-10-24上一阶段包与根入口`./estimate`切换到冻结exp640/S8，由exp644完成
完整100M清洁目录验收和全端口非重复1B实测。该版背景为D64/Q4，地图残差
改为16组、每次8棵深度4的对称树。每层共享split独立比较，四位拼接选择
double叶值，保持JSON原树序double求和；全部叶编号、raw与最终整数已核验。
静态通用ELF91,039,000B，100M六对平均CPU22.324851333秒，
相对exp641平均节省2.641978167秒；分层Acc98.457078987%，
下降0.015695545pp。完整1B CPU225.515516秒、RSS134,967,296B，
单线程与10亿行契约通过，同次分层样本Acc98.457380644%。
当前配置通过联合收益门，最终Acc>99%继续研究。
身份见`subm/latest/identity.json`，专用封装入口为`validation/exp644_package.py`。
后续完整程序测试与清洁目录验收只使用100M和1B。

2026-10-23历史阶段包与根入口`./estimate`曾切换到冻结exp622/T，由exp641完成
完整1B及清洁目录验收。最终Acc严格>99%的目标仍在研究。
名义背景采用近域rank512、远域四方向各rank64的INT8因子与块尺度，真实
几何修正采用16组、每次8棵深度4的R8模型。Q4嵌入零中心标量残量，
保持近域背景，改善远域量化重建；R8按固定模型生成显式比较与叶选择，
原特征、叶值、树序及舍入保持。在线按8条稳定CSV视图准备
特征和残差，预取背景及端口中心项，再按原行序求值和输出。坐标1至3位
直接解析，长数字及溢出继续使用原from_chars。
紧凑节点和固定64项SSE2点积使用通用x86-64构建，无主机专用ISA依赖。
全资产嵌入91,047,192B静态ELF，查询分配0、RSS134.75MB。完整100M/1B
CPU为24.871782/251.200951秒，本地阶段速度门通过；1B分层exact样本
加权Acc98.473086536%。完整1B全量exact、平台与其他CPU待验。
历史身份与专用构建命令见exp641不可变版本及实验619、620、622、641。
普通源码构建路径保留历史实现；执行`sh scripts/build.sh`会重建该路径的根入口，
随后需要按其新身份验证。该历史阶段ELF由`validation/exp641_package.py`封装。

2026-10-21历史平台试提交包为冻结exp580 RP，其独立设计为exp575近远分组
INT16背景、16组8树depth4残差和exp580解析/端点resolver优化。全资产嵌入
93,746,456B静态ELF；构建身份见subm/latest/identity.json和实验579/580。
下文描述普通源码构建路径。平台包采用上述经独立验收的冻结候选。

本文描述实验354接入的源码。比赛入口使用单线程 C++17 的 `ResidueEstimator`，请求按有界批次中的目标端口稳定分组，每条独立预测，最后按输入原序输出。预测先进行预算480、排序权重1.01的真实路径搜索，得到合法路径时输出其费用；搜索未找到路径时，使用residue、端点修正及冻结路径模型。`Router` 提供精确搜索，用于独立验证和生成训练标签。实验中的 AIR、CRP、CCH、TNR 和 HL 实现保存在 `tests/`。

## 交付硬约束

提交物是单个静态 ELF，调用方式固定为 `estimate -in <request.csv> -out <result.csv>`，不得要求
位置参数或额外输入路径。评测镜像 `subm/fpga-ziguang-latest.tar` 内没有任何 SRB JSON 或数据文件，
官方架构与全部预计算表必须嵌入；本机 glibc 2.39 与评测镜像 glibc 2.35 不同，因此必须 `-static`。

静态 ELF 严格小于 100,000,000 B（十进制 100 MB），是赛题后续追加的硬约束；仓库内的赛题 PDF 为
V0.3（2026-08-31），不含这一条。普通源码路径的历史验收组合为94,087,824B；
当前exp779冻结ELF为84,938,776B，余量15,061,224B。构建脚本在编译后
立即检查。平台侧另有单线程、峰值内存 ≤ 2 GB、完整 10 亿对总时长 ≤ 1 小时、五次结果完全一致的限制。
完整清单、逐条来源与本地 1M 门槛见 `AGENTS.md`「平台提交硬约束」。

## 入口与模块

```sh
sh scripts/build.sh
./estimate -in delay_estimate_request.csv -out delay_estimate_result.csv
```

该命令按当前源码重建根入口，采用实验335的262,144行目标分组与默认cache0配置，实验354在cache0时省略请求键计算，预测器保持实验322验收的480窄除法候选。residue初始化沿用实验131的Zstandard预计算表，回退模型保留实验93的47维 base、128树 depth10、uniform -3及后续冻结上界树与路径残差模型。静态提交包由 `scripts/build_submission.sh` 从同一源码生成并存入不可变版本库 `subm/versions/`。实验29 冻结二进制 `db2cca1e…` 继续作为历史比较基线，其正式五次 1B 成绩与平台回执属于该二进制。实验31 候选保存在 `build/exp31/estimate`，默认 bounds off。

普通入口和提交包均携带官方架构与预计算表。程序依次检查显式 `-arch`、`DELAY_ESTIMATE_ARCH`、可执行文件附近、工作目录和仓库开发目录；没有外部架构时加载嵌入内容。根目录的 `arch` 相对链接指向 `doc/eda比赛文件/arch`；独立交付目录 `build/submission/` 可携带已有 `arch/`。输入为 `From,To`，输出为 `From,To,delay`，保留端点文本与行顺序。

| 文件 | 当前职责 |
|---|---|
| `src/main.cpp` | 参数、架构目录、流式 CSV、配置组合检查和退出码 |
| `src/target_batch.h` | 有界请求原文、目标端口稳定分组和原序结果索引 |
| `src/csv.h` | 缓冲读写和字段首尾空白处理 |
| `src/architecture.{h,cpp}` | Port、Arc、Net、SRB、Line、Block 及真实 Net 正反向解析 |
| `src/residue_estimator.{h,cpp}` | 建表、端点候选、数值估计及完整请求缓存 |
| `src/legal_path_search.{h,cpp}`、`src/search_queue.h` | 预算真实路径搜索、排序队列、局部状态及路径费用复核 |
| `src/upper_tree.h`、`src/embedded_upper_tree_data.h` | 冻结名义父树在真实几何上的路径重放及上界 |
| `src/selector_model.h`、`src/upper_residual_model.h` | 回退预测的固定选择器与路径残差模型 |
| `src/embedded_resolver_data.h` | 官方几何的正反向Net等价查询表 |
| `src/embedded_residue.h` | 无损解压、rx模差分恢复与原int32表重建 |
| `src/query_cache.h` | 有固定容量的确定性缓存，Router 与 residue 共用 |
| `src/router.{h,cpp}` | 隐式图 A*、plain Dijkstra、ALT 和可选下界接口 |
| `src/pattern_database.h` | 架构生成的 PDB 下界，主要用于加速 exact 标签搜索 |
| `src/xgb_residual*.h` | 冻结残差模型的特征计算与静态树推理 |

当前 `main` 默认使用mult2、`xgb-base47-d8`和uniform -3，完整请求结果缓存预算为0，显式`-cache-mb`保持可用。通过既有训练配置检查后，省略 `-endpoint-mode` 的生产调用将内部端点模式设为Both；显式选项保留原有配置含义。CLI模型名沿用历史标识，base模型头为实验93 depth10，SHA `1e96563432104b87a16901b95469cb9b266c2d1bf4a69825f73afd78de2a8919`。真实路径搜索和上界树由生产配置启用，显式bias0、端点off/source等诊断组合保持各自行为。独立测试直接构造 `ResidueEstimator::Options` 时，默认仍为mult1、端点Off、cache64 MiB；需要按实验目的显式设置。二进制身份与实测成绩见 `RESULTS.md` 和各次实验日志。

## 生产请求路径

默认每条请求独立调用预测器。`LegalPathSearch`在真实Net和Arc图上搜索，最多展开480个状态，以`g + floor(1010*h/1000)`排序。找到路径后按真实几何重新核对费用并返回；未找到时调用Both端点residue估计、base残差、冻结父树选择器和路径残差模型。同pin为零，无效端点和不可达语义由各路径保持。真实路径值在内部补偿外层uniform -3，最终输出等于核验路径费用。

`estimateText`解析合法端点后，仅在缓存容量非0时计算请求键并查找结果。容量为0时继续逐条执行原预测，末尾insert按原规则立即返回；显式开启缓存保留原返回值、统计和校准阶段。exp353在Xeon完整非重复1M上测得CPU减少0.680066%，输出逐字节保持，exp354按相同源码与ELF身份接入。

`TargetBatch`每批最多262,144行及16MiB原文，按目标端口稳定分组，全部结果计算后按原序写出；首条不可达警告也按输入行序选择。超长单行先清空已有批次，再单独处理。批次换序保持每条预测所用架构、模型、预算及初态，完整请求对结果缓存默认关闭。exp332核对12,150条搜索记录、126,462条路径边和完整1M输出，分组与原序批次的Xeon对照支持已测负载下的工程收益。exp334扩大窗口后在非重复1M上再省0.842539%，最终ELF由exp335按完整身份复用验收证据并交付；硬件缓存机制另待计数器证据。

当前等价工程包括按目标列排列的int16排序表、按查询复用坐标计算、按实际访问单元分配状态、冻结Net几何查表和非负状态编号的uint32除法。排序表超出窄值范围时使用原计算；几何查表仅在Net、Gap、Inst文本匹配官方嵌入身份时启用。预算与排序权重属于近似算法选择，residue排序值的使用没有建立全局最短路径保证。

实验320复用了145,800条搜索记录和1,379,555条路径边的等价审计；实验322的完整1M输出保持原480候选，独特请求Xeon CPU均值98.09秒，公开acc为99.0106972142%。该结果相对exp258允许精度下降，完整独特100M/1B及隐藏集仍待验证。

## 真实图与几何

架构包含 120×550 坐标、60,200 个有效 SRB、496 个端口、8,192 个 Arc 和 160 个 Net 模板。每个 SRB 复用同一组端口与 Arc。搜索状态保留 `(x,y,Z端口)`，共 160 种 Z/lane 身份；邻接边按模板生成。

`Architecture::resolveNet` 解释真实 Net 位移与费用。沿当前方向可穿越的 Block 不消耗规定的 SRB 步数，每个被跨越的 Block 计费一次。不可穿越方向保留名义坐标位移，落点位于空洞时连接无效；跨度足够的 Net 可以落在 Block 另一侧。Line Gap 按实际跨越的边界累计。`resolveNetPredecessor` 提供对应的真实前驱，供目标端接法使用。

一个完整 Z 状态转移包含先经过 Net 到 I，再沿同格 Arc 到下一个 Z。到达目标 Z 身份即可结束。I 目标在 Net 落点结束，逻辑目标还需计入终止 Arc。相同完整 pin 的延时为零。

## residue 建表

先建立忽略 Gap 的无限平移图，保留全部 160 个 Z/lane。每个象限从架构生成线性斜率，通过 Bellman-Ford 求势函数，把 Arc 与位移组合的约化费用变为非负整数，再在有限 residue 图上运行 Dijkstra。

实验65复用 `RadixFrontier` 建表。多源种子以最小种子距离平移为无符号键，出队恢复原距离；约化边非负保证键单调。正式数值不变，验证见 `experiment/实验65-现行版本性能热点定位.md`。

实验66直接弹出radix桶0的尾项，省去同键状态编号的线性扫描。桶0中的条目键相同，最小键语义和整数距离保持；可选radix Router的访问顺序会改变，验证见 `experiment/实验66-radix后请求路径性能画像.md`。

实验71在表初始化后，对表内完整系统页调用一次Linux `MADV_COLLAPSE`，尝试合并透明大页以降低地址转换成本。表仍由原vector拥有，虚拟地址及内容保持；内核不支持或不能合并时继续使用原映射。本机Linux6.18的1M unique配对CPU平均少1.683秒，平台收益取决于内核与页合并结果，见 `experiment/实验71-查询表透明大页.md`。实验85将Z源表按Net落点按需推导，并在radix重分桶时复用桶容量；多次队列校验和完整1M输出逐字节等价，初始化CPU在正式比较中平均减少1.103秒（与exp71比较），见 `experiment/实验85-radix桶容量复用.md`。实验90在查询阶段按连续四象限槽复用一次表行地址，候选三对1M unique CPU平均减少0.600秒，输出逐字节等价，见 `experiment/实验90-四象限连续表值读取.md`。

实验26独立检查了 160 点、2,752 边的名义商图。四条轴向自环给出斜率矩形的必要边界，四角逐边约化费用非负和可行集合的凸性给出充分性。因此当前四角已覆盖这个商图的全部可行线性斜率。费用预算内的 4,189,980 个状态满足 `L≤R1≤R2≤exact`，全位移的误差上界仍未建立。Karp 环均值和 min-plus 矩阵幂保留为理论诊断。

mult2 的模数为 20×24，整数缩放为 120。四个象限分别存储 368 种源端口到目标 residue 的值。逻辑上支持 448 种目标端口，实际只存 Z 与逻辑目标的 288 列；exp85 进一步只保存非Z源，Z源按固定Net落点和 residue 位移推导，物理表为 438.8 MiB。中间边费用写入 `uint16_t` 前检查非负和不超过 65535；表值使用 `int32_t`。

固定官方mult2表离线除公因子10后编码为int16，拆分四象限，沿rx做uint16模差分，再分低高字节平面。实验131用Zstandard level19、单线程、checksum和内容大小压缩为58,017,384 B，启动恢复全部原int32值和INF；原查询与模型保持。恢复时核对单帧大小、内容大小与解压结果，拒绝损坏或多余字节。Port/Arc/Net文本与生成输入相同且模数匹配时加载表，其他外部输入和multiplier继续动态建表。

`scripts/gen_embedded_residue.py` 复用原范围审计和完整恢复SHA核验，通过`scripts/pack_residue_zstd.cpp`调用已安装libzstd。缓存按源码、架构、编译器、库、NumPy与产物身份复用；构建需要NumPy、Zstandard开发库及静态库与GNU assembler。`scripts/gen_embedded_upper_tree.py`恢复exp216冻结父树并核对blob、元数据与目标文件身份，构建依赖其冻结记录及原blob或分帧资产。当前验收静态组合94,087,824 B，构建脚本检查严格小于100,000,000 B，两份生成清单随不可变版本保存。实验120预计算相对动态建表在完整1M平均省约10.16秒；exp130的Zstandard恢复组件再省约0.51秒，固定收益按一次运行计，平台成本另测。

实验17采用两项等价压缩。Z 源表由其固定 Net 落点的 I 源表平移得到，省去对应的 Dijkstra。I 目标由其唯一前驱 Z 列平移得到，省去 160 列存储。mult1 与 mult2 的独立全表对照分别比较 79,134,720 和 316,538,880 项，差异均为零。

基础查询对四象限取最大值，再取整并增加端点之间必过的 Line Gap。其形式为

```text
max_q (a[q]·dx + b[q]·dy + table[q,source,target,residue(dx,dy)]) / scale
```

I 目标查询会相应调整查表位移。四象限均无有限值时保留已有直线估计分支；已验证的架构表没有触发该分支。

## 真实端点修正

生产默认的Both在所有距离枚举源端与目标端。诊断模式`source-short`在曼哈顿距离不超过150时枚举两端，其他请求只枚举源端。源候选包含真实首 Net，非 Z 源同时计入首 Arc；目标候选用真实逆 Net 找到前驱，并计入末 Gap 与必要的终止 Arc。中间部分调用基础 residue 估计，候选取最小值。

Source 分支同时检查 I 目标的真实 Net 前驱。无法落到该目标时，只保留已找到的完整短路径候选。实验24据此修复了六条假可达请求，独立样本的其余 3,063 条可达估计保持一致。

同 pin、同格直接 Arc、单 Net 和单 Net 加 Arc 同时作为短路径候选。重复候选按身份合并并保留较小费用。已有最优值允许跳过费用已不可能改善它的候选。候选暂存区重复使用，只有完整请求结果进入缓存。

端点修正改善了首末跳的几何处理。中间 residue 值仍是近似，整条输出的误差由实测评估。内部 `-1` 同时用于无法解析的 pin、无效端点和无候选的请求，诊断计数分别记录这些原因。

## 缓存与规模

生产CLI默认关闭完整请求结果缓存。显式启用时，缓存键包含 From 和 To 的完整 pin ID，存储最终整数结果；64 MiB 对应4,194,304个槽，装载达到75%即停止插入，已有条目继续可查。不同 pin 对共享同一端口组合时各自拥有独立键。最终请求事先未知且输入内唯一，后续有效成绩采用非重复100M和1B完整实测。

以下保留显式启用缓存的历史负载证据。公开1M请求可以全部驻留。重复输入的首次请求包含实际计算成本，后续相同请求使用缓存。实验23的100M mixed输入包含90M公开重复请求和10M独特请求，实测缓存命中89M次，独特后缀超过插入上限。平均每行耗时随两类请求比例变化。

CSV 使用固定大小缓冲顺序读写。生产进程只读取架构和请求，生成器、验证器及离线评分器分别运行。计时包含进程启动与建表，生成数据和核对输出的 CPU 单列。100M 和 1B 的结果以实验23及后续记录为准。实验50的全独特输入在 10M 上为 20.42–22.98 µs/行，在 100M 上为 21.55–21.56 µs/行；两种缓存设置均无命中，100M 两轮 wall 为 2182.34–2183.44 s，RSS 为 838,116–903,644 KiB，输出逐行一致。按 100M 单点线性外推，全独特 1B 约 21,574 s，超过 3,600 s 上限；该结论限定于全独特上界负载，公开 1M distinct 扩展的 repeated 负载仍由实验29的 1B 五次验收覆盖。

实验29把当前行的两列作为 `string_view` 传入共享解析器，坐标使用 `from_chars`，输出整数使用 `to_chars`。视图只在当前调用内使用，输出保留端点原文。端口名称仍查询已有表，缓存键与估计结果相同。超出整数范围的坐标返回解析失败。100M两组相反顺序消融中，完整候选的平均CPU从111.750秒降到96.905秒，六次输出全部一致。正式1B五次平均CPU为464.056秒，比实验25减少31.69%；五次完整输出均与旧版相同，峰值RSS为925,442,048 bytes。

## 精确搜索与 PDB

`Router` 在隐式 Z 状态图上执行单向 A*。关闭启发式得到 plain Dijkstra，默认搜索队列为 binary heap。ALT 与 span 下界可加速搜索。PDB 用实际架构位移类型构造抽象图，按目标准备小表；无法提供有限下界时，由 Router 使用其他已支持的启发式。

PDB 与 Router 的组合已用于 exact 标签生成，配对证据见实验10和18。外部下界与 radix heap 的组合受配置检查限制，当前验证支持 binary heap。将 PDB 用作 residue 输出地板的实验没有改善公开输出，因此该选项保持关闭。

## 冻结残差模型

实验19的模型由独立 exact 标签训练，包含 64 棵树、1,838 个节点。运行时使用静态 C++ 数据，仅计算模型实际使用的 33 个特征，无需 XGBoost 运行时依赖。`xgb` 校正所有正估计，`long` 只校正距离超过 100 的正估计，零和负结果保留。

启用模型时，CLI 要求 mult2、source-short 150、PDB floor 关闭，bias 为关闭或 7 个 band 全等的 -3；其他 bias 取值（含 0 与非 uniform）保持残差 off 的冻结语义，exact/short-exact 组合仍被拒绝，`-bounds` 仍要求无 bias。该限制对应固定训练配置。

实验60 接入后，无参数运行默认在该训练配置上追加 7 个 offset 全为 -3 的 uniform bias（显式 `-bias-ps -3` 等价）。uniform 表只判定一次，`value >= 0` 时用 `bias.apply(value, 0)` 代替逐行 `parsePin`×2 加 Manhattan 距离；数学前提是 `offsets[bandOf(d)] == offsets[0]` 对所有 `d >= 0` 成立，故两条路径逐字节等价。`value < 0`、`-exact`、非法端点与禁用表不进入该分支，非 uniform 表保留原逐行 band 路径。标签、训练、特征和推理均不读取 golden；golden 仅供最终离线评分。

实验61将隐式残差换为实验58冻结的 47 维、64 棵、depth 8 `base-d8` 模型，继续使用 uniform -3。新增特征为预端点 `base`、`base-fast` 和 `base/max(fast,1)`；树表采用完整深度 8 堆序布局，原叶子子树填相同叶值，按原树序以 float32 累加，因此与原树遍历输出逐字节一致。私有消融在 1M unique 上减少约 2.38 秒 CPU，额外静态表约 1.3 MB。独立 `[18M,20M)` 窗口相对 exp60 包内版本提高 `0.179452 pp`；公开 1M 仅用于最终评分和契约检查，见实验61记录。

实验63保留同一特征、树数、深度与 -3 ps，将实验18B及实验56、57、58、61经核验的 exact 标签合并训练。残差只处理正估计，因此训练前排除379条负 exact，使用34,352条可达标签；负 exact 继续进入验证集检查可达性。独立 `[22M,24M)` 窗口相对实验61包提高 `0.264834 pp`，本地3对CPU增加 `0.613 s/1M unique`，综合收益保守下界 `+0.152276`。实验78在独立 `[30M,32M)` 窗口复核同一训练池的128树模型，增益 `+0.031625 pp`，95%区间 `[+0.011613,+0.051856] pp`；实验85接入该模型、Z源按需推导和radix桶容量复用。实验87保持同一推理路径，将可达训练池扩大至46,505行，新模型SHA `6904544684efacfb0bbb80ae7340900bd8c6888e7993f6146351b15985ba338f`；独立 `[32M,34M)` 窗口相对实验85提升 `+0.065893 pp`，配对95%区间 `[+0.023183,+0.110429] pp`。实验92在同一训练池上固定 `gamma=1.0`，独立 `[36M,38M)` 窗口相对 gamma=0 提升 `+0.032095307 pp`，paired bootstrap 95%区间 `[+0.016312354,+0.048297382] pp`；模型 JSON SHA `92a3c09217e7881fc07704159f4ba7d123f233bcb21dab5f78a2a8fc61c015cc`，该历史depth8头SHA为 `f0c77cfba202298bd620c6433a77dc5d219870ea275e6e133b7f9c6064f751d0`。用户当前源码使用实验93 depth10头，实验120保留其预测输出。

实验19的公开留出 accuracy 从 94.167 提高到 96.187，实验24的独立架构样本按请求频率加权后从 93.578 提高到 95.376。100M repeated 与 mixed 的推理总耗时接近关闭模型的结果，因此最终默认启用 xgb。99 条 stress 上的短距退化仍保留在实验19日志中；独立样本的同格请求也存在 ≤5% 比例下降。

## 正确性与证据边界

实验30以独立探针验证模型输出截断。下界L为496端口商图的最短Arc费用与必过Line费用之和；U1、U2分别来自至多一个、两个真实Net的完整路径。13,230条已见样本中边界与129次上界重放均通过。

实验31已在候选源码中增加 `-bounds off|lower|upper1|both`，默认off，CLI限定使用当前训练配置。lower/both在所有residue建表之前检查Arc、Block和Line费用非负，再建立984,064 bytes的端口商图表。`estimateEndpoint` 用局部输出参数传回已有短路径U1，残差输出之后执行截断；零负输出保留，未知边界保持原值，矛盾边界计数并跳过。完整请求缓存保存截断后的结果。

六种配置各通过13,230条独立探针对照，bounds off公开1M与实验29逐字节相同，端点270项及CLI检查通过。第二阶段3,105条新架构样本与公开1M的规则核对均通过，xgb组合分别提高请求加权accuracy 0.003129和公开accuracy 0.001587个百分点。纯查询及100M正反顺序十轮均已完成，100M输出和资源检查全部通过。计时波动大于精度收益允许的成本，稳定综合收益尚未确立；（当时）根入口和交付包继续使用实验29，该状态已由实验60 接入更新。候选结果与正式成绩分别记录在 `RESULTS.md`。

无限 Gap-free 平移图上的 residue 松弛有下界性质。真实 Block 图已有反例，例如 `SRB_75_0/ZSEA[0]` 到 `SRB_90_0/ISEA[0]` 的真实单 Net 费用为 292，早期纯 residue 输出为 327。真实图 exact 搜索的安全下界来自经过审计的势函数、ALT 或 PDB。

`tests/verify_internal.cpp` 检查真实几何、八条公开路径和独立显式小图。`tests/verify_estimator.cpp`、端点集成检查与全表等价检查覆盖估计器。区域方法在局部图上与 plain 对照，具体范围见实验20；局部查询收益需要结合全芯片空间与构建成本判断。

评分按 `0.8·accuracy + 0.15·time_score + 0.05·consistency` 计算。每项结果应同时说明请求分布、规模、二进制、CPU、峰值 RSS 和一致性次数。正式要求为单线程、2 GB、每次 1B 请求与五次完全一致。本机成绩及跨论文的 CPD、R²、MAPE 各自保留其评测条件。

## 近期候选与缓存判别

实验47把短距 `xgb-base` 与长距 `xgb` 合并到一个进程，公开和新切片输出与冻结两进程结果逐字节一致；1M screen 通过预注册综合收益门槛，1B 五次仅作诊断，（当时）正式入口仍为实验29。实验48证明固定端口对和完整位移的成组残差具有位置稳定性，但完整键在公开剩余请求中的覆盖率只有 0.00131%，新族修正劣于 xgb，因此不增加结构查表。实验49的 2M 容量判别显示64 MiB只在重复key上提供可测收益，unique输入无命中；实验50在10M和100M全独特输入上复现cache=0/64均为0命中且输出哈希相同。上述实验保留各自版本身份。exp331在同一exp323 ELF的独特1M上测得关闭全miss缓存节省0.454592%；exp333在完整1M及受影响消费者验收后将CLI默认改为0。当前非重复100M/1B完整CPU继续待验。
