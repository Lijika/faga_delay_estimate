# 实验159 C1 安全界radix大样本成本

2026-10-10，Asia/Shanghai。分支`research/exp159-radix-policy-cost`，起点`065184f`。
开工`/dev/sdd`可用454G，正式exp131保持。

## 固定假设与候选

exp158在92行保持exact并节省8.79%组件CPU。本轮固定相同私有Router、
exp154安全界与exp156窄表恢复，扩大至已冻结6176行。
先分别audit两队列每条exact与全部访问状态的界字段；
binary保持exp154完整轨迹，radix记录自己的确定性轨迹。
每种队列复用已通过的6条terminal checks，exp158的8行plain证据按相同源码/输入复用。
radix每次push单调断言保持。生产、模型、正式包及标签文件只读。

影响范围为实验probe、runner、私有scaffold与验证证据；全部消费者统一使用
exp158 private Router header/source，避免混用不同inline定义。
本轮源表、orbit、arch及private源码未变，exp157全域证书复用。

## 预登记测量与门槛

6176全行audit后，各队列先warm一个块，5对old-new/new-old交错。
每块50循环固定0.10族262行；每行CPU按2M总体七带权重折算1M distinct。
保持CPU3、单线程、同机串行、关闭query cache，每块清空Provider缓存。
每次exact及队列各自轨迹一致；全部Provider状态六字段一致、无unknown/incomplete，
所有push单调，完整证据与重复行序通过。
组件CPU门为weighted配对df4 95%t上界<0且节省>=5%。
RSS<=2,000,000,000 B、wall<=600秒；失败保留全部前缀。

条件综合模型复用exp151冻结0.10规则与精度差；使用本轮候选行级CPU
进行10,000次配对行/轮重采样，seed20261010。端口与位移角色为同一架构；
请求已反复查看，归开发集。
候选单次新测init=orbit恢复+Provider+一个radix Router，
初始化在bootstrap中固定，本轮单独报告其组件值。
预先固定门为综合点>=0.01且95%下界>0。
两项CPU门与条件综合门分别报告，保留单项工程收益；
新请求、生产trigger/cache、静态ELF、完整1M和平台1B独立验收。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp159_radix_policy_cost.py freeze
# 提交冻结记录后运行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp159_radix_policy_cost.py run
```

私有`build/exp159/`，证据`validation/results/exp159-*`，拒绝覆盖。
