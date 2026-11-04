# 实验220 C1 Line剪枝静态1M等价与CPU

2026-10-12。exp219的Line combined相对exp217 combined，12352条audit保持，
1405518条合法路径证书通过，远程组件查询CPU省8.9689%，
五对95%区间[-0.859262,-0.840282]s。exp218未过预注册5%门。
本轮仅将exp219 combined接入exp216私有静态程序，不更改正式`./estimate`。
私有目录`build/exp220`，开工`/dev/sdd`可用约436GiB。

## 预注册

对照固定`build/exp216/estimate-budget`，候选为复制相同源码、模型、
树压缩数据和静态编译参数，仅将`upper_tree.h`替换为exp219 combined，
类名恢复为`UpperTree`，计数与证书宏均关闭。
固定exp216/219身份、输入、校验输出及三个1M分布，禁止重新选择模型与阈值。
完整源码、命令和二进制身份由`exp220-frozen.json`锁定。

本地先运行12352条完整audit和API查询，与exp216逐字节一致；
6180条独立新请求与exp216 CLI逐字节一致。
14条边界请求在default、endpoint off/source、bias0及更改Arc架构下
对照exp216输出，覆盖零、不可达和端点顺序。静态ELF小于100,000,000B，
每个进程单线程、RSS≤2,000,000,000B、CPU/wall≤3600s。
任一等价或资源检查失败即停止扩大，保留原始证据。

本地门通过后在远程r9r4900工作目录、Herdr w1:p2、core3
对public、unique、repeated完整1M分别交错运行。
每分布双臂按AB各预热1次、3对按BA/AB/BA运行；
同机串行，避开其他重负载。
复用exp205的逐行契约校验，核对行数、端点顺序、恰好3字段、
整数delay、精确EOF、完整SHA，且每次结果严格等于exp216已冻结SHA。
记录输出身份、行序、distinct、CPU、wall、线程和峰值RSS。
缓存miss数由同输入已验的exp216诊断记录给出；本轮总CPU包含初始化。

对public、unique分别用三对差值和df2配对95%区间，主CPU门要求
两组平均各至少节省2.0秒，且各自区间上界小于0。
repeated只需输出与资源通过，其CPU作为缓存命中场景诊断。
精度由逐字节等价复用exp216公开1M分数及exp215新请求证据，
跨架构精度与平台1B另验。即使CPU门通过，仍保留私有候选，
正式更新需按项目规定完成验收和打包流程。

## 实际结果

协议提交`32a737e`，静态冻结构建`1928a1f`，本地等价检查`0fcc243`。
候选`build/exp220/estimate-line`为静态ELF，93,768,336B，
SHA-256为`dadb0ee3b09257df9bdefe374efc87757f630531cee29a29eb0b07c1f32b14e1`。
源码与exp216仅`upper_tree.h`不同，替换内容同时包含exp217分阶段剪枝
及exp219 Line combined增强；本轮整程序CPU差属于两项组合。

本地12352条audit/API、6180条新请求及五组边界配置逐字节等于exp216，
最大RSS1,658,433,536B，单线程。远程Xeon Gold 6226R、core3
各分布双臂预热后BA/AB/BA三对，共24次完整1M；全部行序、三字段、
整数delay、精确EOF及SHA等于exp216冻结值。最大RSS1,658,253,312B，
最长wall117.24s，所有进程单线程，满足2GB和3600s限制。
public/unique/repeated的distinct分别为1,000,000/1,000,000/1,000，
沿用同输入exp216诊断的cache miss数；计时含初始化。

| 输入 | exp216 CPU均值 | exp220 CPU均值 | 配对CPU差及95%区间 | 主门 |
| --- | ---: | ---: | ---: | --- |
| public 1M | 108.6200s | 76.4233s | -32.1967 [-32.5053,-31.8881]s | 通过 |
| unique 1M | 116.7967s | 82.1767s | -34.6200 [-35.8722,-33.3678]s | 通过 |
| repeated 1M | 2.1600s | 2.1267s | -0.0333 [-0.0477,-0.0190]s | 仅诊断 |

两个主分布均超过预注册每1M节省2秒且区间上界小于0的门槛，
节省比例均约29.64%。repeated节省0.0333s，不套用2秒主门。
Line相对exp217的独立组件CPU收益见实验219，整程序未单独消融Line。
输出严格等价使公开accuracy保持97.3811371988%，新请求证据复用exp215；
本轮不产生精度增量，99%目标仍未达到。
以exp216同机测得的exp205正式基线32.18s和约1M次cache miss作
条件性成本估计，本候选仍比其多约44.24s/1M，条件综合点值约-0.1829。
此比较跨实验且未配对，平台1B及跨架构CPU另验；正式入口及交付包保持exp131。

完整报告`validation/results/exp220-report.json`，SHA-256
`ae2a652b340e9f47ae9497e4fd98f0a817f72f5899bd515387ed6837000d6d93`；
原始记录`build/exp220/remote-timing.json`，SHA-256
`bf0e6befcb7063cae798e9d673d8e89e63e9b57e9576b79e6f4a032812ea1757`。
本地保留三份完整候选CSV及24份time、24份空stderr。
远程结果包`build/exp220/results.tar.gz`含这52个文件，
SHA-256为`593d9d0e2969b703851ad4aba62a2c04c360da742244ecba795bb52a6e8acbe9`；
本地相同SHA临时包已清理，可通过
`scp r9r4900:/home/lhj/lhjwork/eda2026/build/exp220/results.tar.gz build/exp220/results.tar.gz`
重取。归档元数据对比仅提示本地umask造成权限位不同，
完整内容SHA、计时文件身份及资源由报告校验通过。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp220_integrated_line.py freeze
# 冻结清单提交后执行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp220_integrated_line.py check
# 远程工作目录内运行
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp220_remote.py
# 取回52个原始文件后执行一次
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp220_integrated_line.py report
```

收尾`/dev/sdd`仍约436GiB可用，精确值467,729,027,072B；
较开工467,854,528,512B净减少125,501,440B。
清理前逐项核对了临时结果包与远程同SHA，本地52份原始文件已校验且远程
可重取，实验命令未按名引用本地结果包。仅删除本地
`build/exp220/results.tar.gz`（40,805,439B），释放该临时副本；
长期按名引用的输入、候选程序及原始证据全部保留。
