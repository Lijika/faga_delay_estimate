# 实验168 最优prefix包络Pareto目录

2026-10-10，分支`research/exp168-prefix-envelope`，起点`d6b4c56`。
正式exp131与exp161组件保持，开工`/dev/sdd`可用454G。

## 假设与固定表示

同exp167名义商图、C1200、195水平同ZSEA[0]根。
完整预算距离标签枚举所有最优前驱，正Arc使DAG费用严格下降。
从固定源递推prefix bbox，包含关系删除外包络，等bbox保留首个路径；
每个保留标签有完整最优端口序列与parent-label绑定。
统计覆盖全部名义最优walk的矩形容纳性，Line费及跨Block行为继续由真实重放判定。

每根保存exp167原路径，再保存不同的Pareto路径；真实使用取已重放合法路径的最小U。
基线始终保留，可比较输出保持所有已有合法项且U不增。
目录为20 B头、195条12 B根、每条16 B包络记录及uint16动作，完整恢复核验。
初版目录预算128 KiB，节点上限100,000、每节点标签上限4096、总标签上限1,000,000，
达到任一cap保留现场并报告未完成，不截断成完整性证据。

## 数据与门

同exp167 30源位置×195根5850项。逐行baseline状态/费用须与exp167一致。
全部名义费用、prefix最短标签、端口、位移、bbox、编码恢复与实际重放保持；
新增合法路径的U≥已有exp167提前固定exact，未知exact保留未验证。
主门为容量≤128 KiB及至少一个此前重放失败项获得合法路径。
费用下降另报，不用此网格宣称总体acc或CPU收益。
门失败仅停止固定Pareto-only表示扩大，事件标签、替代tie-break、更广端口/二维继续开放。

## 命令

```sh
python3 validation/exp168_prefix_envelope.py freeze
git add tests/exp168_prefix_envelope.cpp validation/exp168_prefix_envelope.py experiment/实验168* validation/results/exp168-frozen.json
git commit -m "exp168: freeze Pareto prefix-envelope directory"
python3 validation/exp168_prefix_envelope.py run
```

私有构建`build/exp168/`；CPU3、单线程、timeout300 s、RSS≤2,000,000,000 B。
冻结版本提交后读取结果，原始证据`validation/results/exp168-*.csv/json/bin`。
本轮复用exp167 exact；未读golden与新请求。完整首步RLE、实际incumbent性能、
组合ELF/冷启动、生产trigger/cache、新请求、完整1M与平台1B继续独立验证。
理论入口为Obsidian `路径prefix包络的矩形容纳与事件边界.md`。
