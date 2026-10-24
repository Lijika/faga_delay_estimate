# 实验119 C2 residue轴差分与预计算接入

2026-10-09，Asia/Shanghai。分支 `research/exp119-residue-delta`，起点 `02c8f2a`。开工 `/dev/sdd` 可用470G。本协议在新布局测量前提交。

## 假设与固定候选

实验118已证明完整物理表可用公因子10编码为int16，全量SHA往返保持；原字节平面压缩133.57MB。假设四象限交错会混合不同斜率形成的模式，先重排为 `[source,target,quadrant,ry,rx]`，再对residue轴做模差分，可降低zlib容量。

按以下顺序测量，首个容量通过的表示用于接入，之后停止增加布局：

1. `quadrant`，四象限分离，低高字节分平面；
2. `dx`，在同一源/目标/象限/ry内，沿rx做uint16模差分；
3. `dy`，在同一源/目标/象限/rx内，沿ry做uint16模差分；
4. `dxdy`，先dx后dy，按相反顺序做前缀和恢复。

zlib level6保持。每种完整流恢复int16原顺序并核对SHA，全体范围、公因子及int32恢复复用exp118未变证据。每种压缩与解压合计墙钟≤300秒，Python峰值RSS≤2GB。估算文件小于100,000,000 B（含exp92基线与200,000 B余量）才准许嵌入；四种均失败则停止本固定布局候选，A1/C2继续。

## 私有接入与验证

复用 `build/exp118/table.i16` 与完整SHA `16089e40e5fe65f4376340492fca6f62b4727c26cbef6db57d97f7673dbf52da`，原int32 SHA `800dcf4af93e6fe5a298d239479ebc84c12a06fc1ae7712e9f194e4cff347e40`。shape为 `[208,288,24,20,4]`，所有lane和端口保持。

使用exp118已登记的初始化替换边界。固定Port/Arc/Net文本与嵌入数据完全相等且mult2时才加载表；其他输入或multiplier走现有动态构表。文本等价判断采用逐字节相等；格式改变会继续动态构表，行为保持。运行时恢复原int32表，查询逻辑保持；原大页提示与表尺寸保持。

private baseline与candidate均从同一源码构建，C++17/O2、静态、嵌入官方架构、exp92模型。比较完整表、开发预测、零/不可达/边界及mult1，检查外部同内容架构、clean-room嵌入和修改Arc输入的动态行为。预计算加载需由Dijkstra次数0证明；其他输入保持832次。实际静态文件必须小于100,000,000 B。

完整1M unique与性能协议沿用exp118，输入及exp92期望完整SHA保持。核3、串行、双方预热一次，再AB/BA/AB三对，df=2的95% t区间；CPU均值至少减少1.2秒且区间上界小于0才批准工程候选。相等输出意味着精度增益0，固定启动收益按每次完整运行计；平台1B和隐藏集仍待平台验收。通过后单独核验用户当前depth10组合和正式包。

## 理论与产物

Obsidian短笔记 `residue轴模差分与启动恢复等价.md` 记录当前表重排与模差分的可逆条件，并与整数编码及距离场差分笔记建立双向链接。私有目录为 `build/exp119/`，原始证据为 `validation/results/exp119-*`；实验代码复用exp118导出与压缩helper。

## 容量与私有接入结果

四象限分离压缩115,255,410 B，容量未过；沿rx模差分后89,753,737 B，加冻结二进制及余量估算97,943,641 B，通过。按固定规则停止后续dy/dxdy布局。两个完整流恢复均符合窄表SHA，Python峰值RSS1,085,050,880 B。

实际静态candidate `build/exp119/estimate-precomputed` 为97,786,512 B，SHA-256 `4faebd4f747fb99c8e28fbca9a1ef366594952c7325b29949986a8afbe27ea04`，距离十进制100MB上限剩2,213,488 B。同源码baseline完全复现exp92自包含SHA。完整C++恢复的int32 SHA与实验118原表一致；构表Dijkstra次数0，初始化探针1.663917秒。该探针只用于成本分析，端到端CPU待配对结果。

12,357行开发请求的官方外部架构和clean-room嵌入输出均与exp92预测一致，SHA `1bdd2b26dea72d261be9f6b69a2c4d256665b170c5439985dac00e063ac70d92`。mult1和全部Arc延时加1后的配置与各自baseline逐字节相同；输入匹配探针证明前者执行832次Dijkstra，修改Arc输入也执行832次。6个零延时/边界/不可达请求及人工signed/INF/轴重置解码夹具通过。

命令为 `python3 validation/exp119_residue_layout.py --stage capacity|build|verify|timing`（逐stage执行），证据为 `exp119-layout.json`、`exp119-build.json`、`exp119-compatibility.json`。私有阶段保留正式源码与用户已有交付。

## 完整1M性能

核3、双方各一次预热后AB/BA/AB三对完成。baseline CPU26.72/26.47/27.01秒，candidate16.47/16.55/16.54秒，差值-10.25/-9.92/-10.47秒，均值-10.213333秒、95% t区间[-10.901010,-9.525656]秒。保持精度时按完整运行CPU差计算的综合点收益+0.085111、保守下界+0.079380，登记门槛通过；这一换算限当前计时分布，固定启动收益按每次完整运行计。

全部8次预热及正式运行输出SHA符合exp92 unique1M，17,585个负值及其位置相同。端点顺序、恰好3字段、整数delay、精确EOF、完整SHA、多次一致性通过；最大线程1、candidate最大RSS823,164,928 B，最大wall19.06秒。证据 `validation/results/exp119-timing-1m-unique.json`。

容量与初始化候选通过，允许进入生产构建。当前只测exp92组合；用户当前depth10组合、repeated与最终包另立实验120核验。平台1B与隐藏集尚未验证。

收尾 `/dev/sdd` 可用469G，新增私有源码、压缩流与恢复表等约1GB，释放量0；已有按名引用的表和输入继续保留。
