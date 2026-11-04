<!-- page 1 of 17 -->

![Image block](doc:1262b5e/tier:flash/page:1/block:1)

“长沙银行杯”2026中国研究生创芯大赛·EDA精英挑战赛赛题指南

| 版本 | 时间 | 修订内容 |
| --- | --- | --- |
| V0.1 | 2026-7-31 | 初稿 |
| V0.2 | 2026-8-26 | 修正了赛题指南附件中关于SRB阵列的文字表述。（比赛用到的5个阵列json文件不变） |
| V0.3 | 2026-8-31 | 优化比赛规则；1、正式比赛的非公开测试用例，由1亿对提升到10亿对；2、比赛打榜期间，评测平台由原来执行100万次查询请求，改为执行10亿对查询请求（基于原100万对公开测试用例随机复制扩充）； 3、将原来的"运行时长超过30分钟即无效"，改为"运行时长超过30分钟即此项不得分，运行时长超过1小时即该作品无效"。 |

## 一、赛题名称

超大规模FPGA的布局布线延时估算算法

## 二、命题单位

1

<!-- page 2 of 17 -->

深圳市紫光同创电子股份有限公司

## 三、赛题背景

## 3.1 FPGA互联架构

FPGA（Field Programmable Gate Array）的互联架构作为芯片的核心部分之一，是可编程逻辑模块（CLM）、存储模块（DRM）、算术运算模块（APM）等模块之间交互的桥梁。紫光同创FPGA芯片的互联架构由互联交换块（SRB）连接组合而成，SRB的对外端口为Port，内部走线通道定义为Arc，外部走线通道定义为Net。以下是SRB阵列的简化示意图。

## SRB

## SRB

## SRB

## SRB

**Port**

**Arc**

**SRB**

**Net**

**Logic Block**

**SRB**

## SRB

## SRB

## SRB

## 图1 SRB阵列简化示意

<small><span class="docvortex-page-footnote" data-block-type="page_footnote" style="color:#6b7280">3.2 FPGA延时估算需求</span></small>

<small><span class="docvortex-page-footnote" data-block-type="page_footnote" style="color:#6b7280">在基于时序驱动的布局布线算法中，布局器和布线器均需要频繁调用延时估算函数以获取当前节点到目标点之间的最短路径延时。延时估算的准确度越高，</span></small>

2

<!-- page 3 of 17 -->

布局布线的结果就越理想；延时估算的耗时越少，布局布线的编译速度就越快；延时估算的内存开销越小，布局布线的峰值内存也越低。

## 3.3 FPGA 延时估算的目标

FPGA内部信号的互连走线主要通过SRB阵列来实现。如果给定起始节点和目标节点，两者可以通过SRB的内部Arc资源和外部互连线资源走线，那么这两个节点之间就可以有很多种走线路径，不同的路径对应的延时不同。延时估算的目标是，开发一个延时估算算法，当调用者给出起始节点和目标节点信息时，由延时估算算法给出两个节点之间所有可能的走线路径中的延时最小值。

## 四、赛题描述

本赛题属于EDA软件算法领域的经典问题，拥有一定的工程实用价值，希望参赛者能够充分研读相关技术论文，提出创新性的解决方案，在满足延时估算准确性要求的前提下，尽可能地减少运行时间和内存开销，同时保证算法运行结果的一致性。具体描述如下:

本赛题提供一个SRB阵列（含不规则区域），由参赛者自行定义数据结构和开发延时估算算法。为了贴近FPGA真实情况，本赛题的SRB阵列中增设了一些block或gap特殊区域（详见SRB阵列描述文件），这些特殊的区域会增加延时估算的难度，具有一定的挑战性。评测脚本会调用执行10亿次的查询操作，然后统计查询结果，从准确性、时间开销、内存开销和运算结果一致性等维度给出技术评分。

主要文件:

1、阵列大小为120\*550的FPGA SRB阵列描述文件；（附件，另行提供）2、测试输入和结果输出的格式文件；（附件，另行提供）

## 五、评分标准

评分采用百分制，最终成绩由准确性、运行时长和运算结果一致性等3个维度的得分进行加权求和产生，计算公式如下:

3

<!-- page 4 of 17 -->

## score = acc\_score ∗ 80% + time\_score ∗ 15% + consistency\_score ∗ 5%

## 5.1 准确性

准确性重点关注延时估算结果(delay\_estimate)与golden数值（delay\_min）的偏差，偏差越小，认为估算结果越准确，得分也越高。

如下图所示，图中曲线表示的是单点的偏差（ delay\_estimate − delay\_min ，横坐标）

delay\_min

与单点得分（1− tanh 4∗ delay\_estimate − delay\_min

delay\_min

，纵坐标）的关系。

![Image block](doc:1262b5e/tier:flash/page:4/block:10)

图2 预估偏差与得分关系

最终统计的准确性得分为各单次得分的平均值，公式如下:

![Formula block](doc:1262b5e/tier:flash/page:4/block:13)

## 5.2 时间与内存

![Formula block](doc:1262b5e/tier:flash/page:4/block:15)

参赛作品的运行内存不能大于2GB，超出将被视为无效，并被强行终止；参赛作品跑完完整测试集（10亿对延时估算请求）的总运行时长不能超过1小时，超时将被视为无效，并被强行终止。考虑到服务器的运行波动，参赛作品提交后将被执行5次。若5次运行中存在以上2种无效情况中的任何一种，该作品将被视为无效，最终成绩将被判为0分。

参赛作品仅允许单个线程运行。作品提交运行后，评测脚本自动统计5次运行的cpu time，将5次运行时长取平均得到avg\_time。当avg\_time时间超过limit\_time

4

<!-- page 5 of 17 -->

（30分钟）时，time\_score得0分。

最终统计的运行时长得分的计算公式如下:

![Formula block](doc:1262b5e/tier:flash/page:5/block:4)

## 5.3 一致性

本赛题要求延时估算算法能够稳定运行、结果可复现，即基于相同测试用例，参赛作品的每次运行结果必须完全一致。作品提交后，测试脚本会自动对比5次运行的延时估算结果，若5次运行结果完全一致，则consistency\_score = 100；若存在不一致，则consistency\_score= 0。

若5次运行存在不一致，acc\_score将取5次结果的平均值。

## 5.4 测试集说明

正式的评测脚本将提供延时估算请求的输入件delay\_estimate\_request.csv，包含10亿对延时估算请求，每1对延时估算请求包含1个from pin和1个to pin。

比赛期间，将公开100万对延时估算请求数据（含golden值）作为公开测试集供参赛队伍进行算法的本地测试和调优。在打榜练习阶段，评测平台会基于这100万对数据采用随机复制的方式将测试样本扩充到10亿对。

## 5.5 提交说明

参赛者需要提交一个可执行程序，支持如下调用方式

## estimate -in ./delay\_estimate\_request.csv -out ./delay\_estimate\_result.csv

5

<!-- page 6 of 17 -->

## PANGO FPGA SRB 互联阵列

下文为SRB阵列描述文件的说明文件，仅为格式和命名规则示范说明，并非正式文件。具体文件请关注赛题提供的附件。

## SRB 阵 列 描 述 文 件 ， 包 含 SRB\_Inst.json, SRB\_Port.json, SRB\_Arc.json,

SRB\_Net.json和SRB\_Gap.json五个文件。其中，

 SRB\_Inst.json 描述SRB的名称和坐标信息； SRB\_Port.json 描述各端口的名称和端口方向信息； SRB\_Arc.json 描述SRB内部走线通道信息，包括每根Arc的源端口

和目标端口信息以及该Arc的走线延时数据； SRB\_Net.json 描述SRB之间的端口互连信息和互连线延时数据，目

标端口所在的SRB由相对坐标偏移给出； SRB\_Gap.json 描述SRB阵列中的少数沟道行或者沟道列的位置信

息，走线穿过沟道行或者沟道列时会增加额外的延时，属于延时估算算法需要考虑的特殊情况；以及SRB阵列中的特殊单元块的位置和大小信息，其内部不能走线，也属于延时估算算法需要考虑的特殊情况。

## 1 Inst

## { // SRB\_Inst.json

## “Insts” : [

## {“name” : “SRB\_0\_0”, “x” : 0, “y” : 0 },

## {“name” : “SRB\_0\_1”, “x” : 0, “y” : 1},

## {“name” : “SRB\_1\_0”, “x” : 1, “y” : 0 },

## {“name” : “SRB\_1\_1”, “x” : 1, “y” : 1 },

## // ....

]

6

<!-- page 7 of 17 -->

} Inst描述SRB及其坐标位置。SRB命名规则如下

## SRB

## \_

## 0 \_ 0

**Xcoordinate**

**Ycoordinate**

SRB互联阵列坐标以左下为原点(0,0)，向右(X)向上(Y)递增。

![Image block](doc:1262b5e/tier:flash/page:7/block:9)

图1 SRB互联阵列示意图

## 2 Port

## { // SRB\_Port.json

“Ports” : [{“name” : “A\_AQ0”, “direction” : “input”}, {“name” : “A\_A0”, “direction” : “output”}, {“name” : “ZSS[0]”, “direction” : “output”}, {“name” : “ISS[0]”, “direction” : “input”},

7

<!-- page 8 of 17 -->

## // ...

]

}

Port描述SRB的端口，一共有两种类型，分别是LOGIC，INTER。

## 2.1 LOGIC PORT

LOGIC PORT是与逻辑资源（如CLM、APM或DRM等）相连的端口。这些端口的名字以与CLM的连接关系为基准，分为input（连接逻辑资源的输出端口）和output（连接逻辑资源的输入端口）。Logic port命名规则如下:

## A \_ E Y

## Connect with which logicinstance

A: CLMA S: CLMS

**Connect with which**

**Connect with which**

**logicinstance**

**logicinstance**

**implementation port**

**implementation**

A: First

Y: LUT6 output

Q0: First FFQ output

B: Second

Q1: Second FFQ output

C: Third

D: Fourth E: Fifth

0: LUT6First input

1: LUT6Second input

F: Sixth

G: Seventh

2: LUT6Third input

3: LUT6Fourth input 4: LUT6Fifth input 5: LUT6Sixth input D: First FFD input M: Second FFD input

H: Eighth

A\_A0，这个端口将会连接CLMA第一个LUT6的第一个输入端口；

S\_HQ1，这个端口将会连接CLMS第八个FF对中第二个FF的Q输出端口。

具体的连接关系，见文件SRB\_LOGIC\_PORT.vsd。

## 2.2 INTER PORT

Inter port 是互联交换块（SRB）之间连接的端口。互联端口是成对存在（Z /I），有固定的跨度（S/D/Q/L），不同连接方向（N/S/E/W）的总线端口。Inter

8

<!-- page 9 of 17 -->

port命名规则如下:

## Z S S [0]

**Input or output**

**Distance**

**Direction**

**Bus**

0\~7: First to Eighth

Z: output

I: input

S: 1 Single

D: 2 Double

Q: 4Quad

L: 8Long

N: North

S: South

E: East

W: West

ZSS[3]，这个端口是输出、跨度为1、南向第四位，其对应的输入端口为ISS[3] ZQE[1]，这个端口是输出、跨度为4、东向第二位，其对应的输入端口为IQE[1]具体的连接关系，见下方Net章节

## 3 Arcs

## { // SRB\_Arc.json

“Arcs” : [{“from” : “A\_AQ0”, “to” : “ZDN[1]”, “delay” : 100 }, {“from” : “A\_BY”, “to” : “ZSS[0]”, “delay” : 100}, {“from” : “ISS[3]”, “to” : “A\_A0”, “delay” : 100 }, // ....]} Arc描述SRB 端口在Inst内部的连接关系。一条Arc有一个来源端口，一个驱动端口，对应的延时值。{“from” : “A\_AQ0”, “to” : ”ZDN[1]”, “delay” : 100 }表示一条Arc，从A\_AQ0端口到ZDN[1]端口，延时值为100ps。

9

<!-- page 10 of 17 -->

## 4 Nets

{ // SRB\_Net.json “Nets” : [{“from” : “ZSS[0]”, “to” : “ISS[0]”, “delta x” : 0, “delta y” : -1}, {“from” : “ZDW[0]”, “to” : “IDW[0]”, “delta x” : -2, “delta y” : 0}, {“from” : “ZQN[0]”, “ to” : “IQN[0]”, “delta x” : 0, “delta y” : 4}, {“from” : “ZLE[0]”, “ to” : “ILE[0]”, “delta x” : 8, “delta y” : 0}, // ...]} Net描述SRB之间的端口连接关系。{“from” : “ZSS[0]”, “to” : “ISS[0]”, “delta x” : 0, “delta y” : -1},由端口名字解析，这条Net是 single（跨度为1），South（方向南）。对应的其连接坐标偏移量为向下1个坐标。

如下为四种跨度和四种方向的连接示意图。

10

<!-- page 11 of 17 -->

![Image block](doc:1262b5e/tier:flash/page:11/block:1)

![Image block](doc:1262b5e/tier:flash/page:11/block:2)

图2 SRB跨度示意图具体的端口连接关系示意可以见附件SRB\_NET.vsd。

对于边界，当端口对应net偏移后超过边界时，net将会断开。

![Image block](doc:1262b5e/tier:flash/page:11/block:5)

图3 SRB边界连接示意图注:此处图片中的跨度仅做示意，具体跨度请以给出的SRB\_Net.json为准。

## 5 Gaps

## { // SRB\_Gap.json

## “Gaps” : {

## “Lines” : [

## {“id” : 0, “direction” : “horizontal”, “site” : 5, “delay” : 15},

11

<!-- page 12 of 17 -->

{“id” : 1, “direction” : “vertical”, “site” : 3, “delay” : 7}, // ...],“Blocks” : [

## {“id” : 0, “lower” : 2, “upper” : 5, “left” : 5, “right” : 6, “vertical crossable” :

false, “vertical cross delay” : 0, “horizontal crossable” : true, “horizontal cross delay” : 55},

// ...]}}

Gaps描述FPGA中的特殊资源导致的空白行、列和块。有行列（Line）和块（Block）两种类型的Gap。

## 5.1 Gap Line

行列Gap产生的原因有很多，最常见的有时钟行、DRM列和APM列。行列不会影响SRB互联阵列的坐标。但是它们会影响跨越的Net延时值。

{“id” : 0, “direction” : “horizontal”, “site” : 5, “delay” : 15},如上表示id为0的行Gap，位于y=5的上方，跨越Gap增加的延时为15ps。{“id” : 1, “direction” : “vertical”, “site” : 3, “delay” : 7} Id为1的列Gap，位于x=3的右方，跨越Gap增加的延时为7ps。

12

<!-- page 13 of 17 -->

![Image block](doc:1262b5e/tier:flash/page:13/block:2)

图4 Gap Line示意图

## 5.2 Gap Block

块Gap产生的主要原因是大块硬核资源，如PCIE、CCS等。与行列Gap不同，块Gap不仅仅会改变SRB的阵列，同时还会改变Net的连接关系。

## {“id” : 0, “lower” : 2, “upper” : 5, “left” : 5, “right” : 6, “vertical crossable” :

false, “vertical cross delay” : 0, “horizontal crossable” : true, “horizontal cross delay” : 55}

13

<!-- page 14 of 17 -->

如上描述的是id=0 占据x [5, 6]，y [2,5]，水平可以穿越，延时增加55ps，垂直不可穿越的Block Gap。

## 5.2.1 受Gap Block影响的SRB阵列

Gap Block 是一个矩形范围，范围内的SRB将被其取代。

![Image block](doc:1262b5e/tier:flash/page:14/block:5)

图5 Gap Block示意图

## 5.2.2 受Gap Block 影响的Net连接

Gap Block 对Net连接的影响遵循如下规则若Gap这个方向不可穿越，按照存在SRB计数进行连接；

14

<!-- page 15 of 17 -->

若Gap这个方向可穿越，按照不存在SRB计数进行连接。

例1.

SRB\_7\_5/ZSW[0]，按照规则应该是连接x = -1, y = 0偏移量的SRB\_6\_5，但这个位置是Block Gap 0。连接为水平，Block Gap 0水平可穿越，按照Gap中不存在SRB计数，则连接到SRB\_4\_5/ISW[0]，延时计算 block gap delay 55ps = 55ps。

SRB\_7\_5/ZDW[0]按照规则连接到 SRB\_3\_5/IDW[0]，跨过了Block Gap 0和Line Gap 1。延时计算 block gap delay 55ps + line gap delay 7ps = 62ps

![Image block](doc:1262b5e/tier:flash/page:15/block:6)

图6 Gap Block可穿越，影响Net连接示意图

例2.

SRB\_5\_1/ZSN[0]，按照规则应该是连接x = 0, y = 1偏移量的SRB\_5\_2，但这个位置是Block Gap 0。连接为垂直，Block Gap 0垂直不可穿越，按照Gap中存在SRB计数，连接不到SRB，连接断开。

SRB\_5\_1/ZQN[0]同理，SRB\_5\_5被Block Gap 0占据，不可穿越。连接断开。

SRB\_5\_1/ZLN[0],应该找到 x=0, y=8 偏移量的SRB\_5\_9/ILN[0]。跨过Block Gap 0，连接为垂直，不可跨越，偏移量不受影响。跨过Line Gap 0。延时计算 line gap delay 15ps = 15ps。

15

<!-- page 16 of 17 -->

![Image block](doc:1262b5e/tier:flash/page:16/block:2)

图7 Gap Block不可穿越，影响Net连接示意图

16

<!-- page 17 of 17 -->

## 延时估算check、request与result文件

## 1 delay\_estimate\_check.csv

本文件提供一些golden示例，并给出详细的最短延时路径走线信息，参赛者可以用来对比检查自己的数据结构和模型构建是否正确。

## From,To,Min Delay,Path

## SRB\_0\_1/A\_AQ0,SRB\_0\_0/A\_A0,200,SRB\_0\_1/A\_AQ0|SRB\_0\_1/ZSS[0]|SR

## B\_0\_0/ISS[0]| SRB\_0\_0/A\_A0

## 2 delay\_estimate\_request.csv

本文件是测试用例，参赛作品需要读取这一文件，执行延时估算操作，并输出结果。

## From,To

## SRB\_0\_1/A\_AQ0, SRB\_0\_0/A\_A0

## SRB\_0\_1/A\_HY, SRB\_0\_0/S\_C4

## ....

## 3 delay\_estimate\_result.csv

参赛作品的输出结果文件。

## From,To,delay

## SRB\_0\_1/A\_AQ0, SRB\_0\_0/A\_A0, 274

## SRB\_0\_1/A\_HY, SRB\_0\_0/S\_C4, 163

## ....

\*本赛题指南未尽问题，见赛题Q&A文件

17
