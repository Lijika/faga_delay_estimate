# 实验154 C1 分子最大值单次floor

2026-10-10，Asia/Shanghai。分支`research/exp154-floor-after-max`，起点`663fca1`。
开工`/dev/sdd`可用454G，正式exp131保持。

## 单一改动与假设

exp153共同gamma标量化加权query CPU再省6.36%。本轮只改变每状态常数计算，
利用正整数scale下`max_q floor(Nq/S)=floor(max_q Nq/S)`，
先取有限分子的max，再进行一次floor。控制为exp153四次floor，
候选为单次floor；共同gamma、int32轨道表、pure枚举、provider与终端消元保持。
空集合直接返回LL_MIN，sentinel保持在除法与取负之外。
理论见Obsidian`agent-theory/正比例floor与有限最大值的交换.md`。

## 固定数据与测量

复用exp153冻结6176行、0.10族262行、逐行exact/expanded/relaxed。
全量实际状态比较六个界字段、pure次数与搜索轨迹。
各版warm50循环；五对`old-new,new-old,old-new,new-old,old-new`，
每块262行原序循环50次，CPU3、单线程、串行。
加权query CPU按七带换算为1M distinct，配对差报告df=4双侧95%t区间。
轨道及Router/provider初始化计入预算。
联合bootstrap沿用固定10000次、seed20261010，各带成对抽行并共同抽五个计时块。

## 门槛与停止

状态六字段、exact及搜索轨迹完全一致，pure次数相同，provider完整；
RSS<=2,000,000,000字节、wall<=1800秒、单线程。
CPU门为加权配对差95%上界<0、均值节省至少5%。
通过则保留等价优化；综合点>=0.01且联合95%下界>0才扩大新请求及接入。
正确性失败立即停止并保留前缀，CPU门未过时保留证据并继续其他优化。

## 命令与范围

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp154_floor_after_max.py freeze
# 提交冻结记录后运行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp154_floor_after_max.py run
```

私有目录`build/exp154/`，原始证据`validation/results/exp154-*`，拒绝覆盖。
本轮完成后按既定十实验计数通过Herdr向Astra提出两个具体难题。
生产完整1M、独立新请求、平台1B及跨架构另验。
