# 实验132 C2 dy场Zstandard与源子集竞争

2026-10-09，Asia/Shanghai。分支`research/exp132-dy-zstd-source-subset`，起点`205da69`。正式基线为exp131，68,201,104 B、SHA `aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c`，容量余31,798,896 B。开工`/dev/sdd`可用463G。协议先于本轮压缩和新候选评分提交。

## 固定问题与候选

路线图选择C2及C1/C4。exp127模板最终覆写的损失集中在Arc源，有限源端口子集与平移误差是两个独立假设。主候选固定使用p1锚点`(60,284)`的10个lane0场，核心平移和真实端点解析沿用exp127，只把行输出改为当前预测与有限模板预测的较小值。基线值为零或负时保持，模板缺失时保持。该比较使用现有预测的数值，不使用exact决定触发。

开发评分复用exp127完整12,357行逐行证据、实验93/105旧窗口exact与七带权重。p0相同比较、两组模板相同比较作为单项与组合诊断；p1为唯一可进入独立验证的固定选择。报告原模板、当前预测与比较后输出，按直接Z源和Arc源分别统计改善、恶化、过估/欠估。较小值本身保持近似语义，不能用作精确界或搜索剪枝。局部源候选子集取最小值的关系复用已有理论笔记。

容量候选固定p1的10场，沿用exp115已经验证的dy模差分和字节分平面，使用exp131同一离线助手与libzstd 1.5.5、level19、单线程、checksum、内容大小。每场完整解压字节与dy流相同，逆变换与原21,120,000 B uint16场SHA相同；有限值和INF位模式保持。逐场报告压缩、解压、逆映射CPU与RSS。使用完整dy流相同传递已有模差分证明，保持180个field/A*检查原身份。

## 门槛与停止

开发主门为p1比较后的accuracy差在两个旧窗口均≥+0.05 pp，零延迟、可达性错配保持基线，且全部改变行满足预登记比较式。较低收益候选停止本次扩大，C1/C2/C4方向继续保留。这里属于开发筛选；模型和触发规则改变后必须新请求验证，旧窗口bootstrap只能描述开发不确定性。

容量门为10场实际frame合计≤30,798,896 B，给ELF新增代码及数据索引保留1,000,000 B。保持当前residue启动表与模型；独立压缩文件之和只用于筛选，最终静态文件须重新实测并严格小于100,000,000 B。单助手进程CPU≤300秒、wall≤600秒、RSS≤2GB，主Python进程CPU≤120秒、RSS≤2GB；整组按10场串行运行，逐场原始证据拒绝覆盖。加载/恢复开销、实际查询CPU与缓存属于后续部署测试。

两个门均通过才登记独立窗口、配对精度与综合收益门，并在私有构建目录实现实际组合。任一门失败时保留压缩流、结果与提交，正式exp131保持。平台1B及golden本轮保持未读。

## 范围、验证与记录

新增`validation/exp132_field_candidate.py`、独立门槛复核脚本`validation/exp132_gate_check.py`及结果；复用`exp115_capacity.encode/decode/selfcheck`、`exp127_template_probe.score`、身份工具和已验收packer。生产源码、构建脚本、正式二进制与包指针保持。小型assert覆盖零、负值、模板缺失、较大/较小模板的输出，并逐行核对已有单项与组合最小值关系。

冻结正式身份、架构、旧报告及逐行证据、p1原场、libzstd、packer源码与二进制、编码和评分工具、协议及当前提交。私有目录`build/exp132/`，结果`validation/results/exp132-*`。本轮结束提交证据，按完整SHA、可重建和引用规则清理临时往返副本，并记录磁盘变化。

```sh
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp132_field_candidate.py --stage score
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp132_field_candidate.py --stage capacity
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp132_field_candidate.py --stage verify
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp132_gate_check.py
```

## 结果与判定

协议提交`0830b1b`后运行固定候选。p1模板直接覆写的两个窗口accuracy变化为`-0.449239/-0.321502 pp`；与当前预测取较小值后为`-0.010280/+0.026256 pp`，未过两个窗口均至少`+0.05 pp`的固定门槛。可达性及零值错配均为0。依照预登记停止条件，本次p1覆写/竞争候选停止扩大，正式预测保持exp131。

十场dy流用Zstandard19压缩的总字节为`24,377,085 B`，预算门`30,798,896 B`通过，估算当前二进制与十场合计`92,578,189 B`，距100,000,000 B有`7,421,811 B`；该值不包含新加载代码的最终ELF增量，余量判断仍以实际静态构建为准。每帧单帧大小、内容大小和解压通过；逆差分恢复的uint16完整SHA分别等于十份原场SHA。解压CPU总和0.236411秒，纯Zstandard压缩CPU总和97.187178秒；这是逐场助手时间，未包含Python读写、编码及逆映射。

逐场助手CPU与RSS检查通过，独立复核主进程RSS为411,701,248 B。原始评分与容量阶段的主Python完整CPU和墙钟未单独存档，整组运行资源仍保留这项证据缺口。

复核同时重算了实验127的p0、p1、combined原始分数，三组均与原报告一致；以及`min_p0/min_combined`的结果仅属**查看结果后的事后诊断**，不用于本轮候选选择或性能主张。源端口分组显示p1直接覆写的退化来自non-Z/Arc源，而直接Z子组为正，但精度证据仍只覆盖已反复查看的93/105开发窗口。实验127理论笔记说明近似平移及端口子集没有精确下界性质，本轮较小值规则只是一种开发评分筛选，不进入生产剪枝。

本轮固定协议提交`0830b1b`在首次测量之前；实现提交与独立输入冻结滞后于首次运行，该流程偏离及首次测量脚本、结果身份见`exp132-initial-identity.json`。原始结果之后由独立复核补充。结果、十场恢复SHA、分组误差和冻结身份见`exp132-score.json`、`exp132-capacity.json`、`exp132-evidence-check.json`。本轮证据范围为旧开发窗口与离线容量；独立新请求、实际静态组合、完整1M和平台成绩仍待验证，C1/C2/C4方向保留，正式预测保持exp131。

## 审查与后续

直接pi只读审查正常退出，模型为`magpie/opencode-go/deepseek-v4.1-flash`、thinking `max`、pi `1.1.0`，stderr为空。报告见`validation/results/exp132-pi-review.md`，调用与输出身份见`exp132-pi-review-environment.json`。当前环境缺少Herdr受管身份，本轮记为直接pi替代审查。

审查核对了单帧精确EOF、完整SHA、INF位模式、dy逆变换、估算容量与开发停止判定。采纳独立重算计数和门槛的建议：`exp132_gate_check.py`从原CSV重建三个固定候选的输出，重新计算两个窗口分数、改动行、可达性与零值错配，再推导选择门。`exp132-gate-check.json`确认min_p1改动360行、两类错配均为0，重新推导的门槛为false，与首次结果相同；门槛边界与错配拒绝assert通过。原脚本和首次结果保持身份，避免重写已经使用的证据。审查提到的事后改动计数风险受首次结果SHA检查约束；本次补充解决的是独立计数复核不足。

收尾复核38项输入、脚本、工具、场和正式产物身份，全部保持；已有恢复证据按身份复用。`strict_100mb_passed`字段描述的是frame与基线的相加估算，最终ELF仍需实际静态构建。下一轮依据容量证据选择真实源场并检验新的目标候选，使用未参与旧开发窗口的请求确定收益。

收尾`df -h /dev/sdd`可用463G，与开工显示相同。本次收尾额外删除0 B；压缩过程的临时往返副本由`TemporaryDirectory`在退出时清理，释放量未单独计量。保留十个frame、packer和首次脚本存档，总计26,911,175 B，供本轮证据复现。
