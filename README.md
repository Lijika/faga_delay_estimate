# faga_delay_estimate

本轮外部 AI 咨询以 **exp688 冻结提交版**为对象。`source/` 对应固定提交包
`exp688-v8-boundary-generic-1b243s-1965119f-dirty-20261025-0035`，
实际查询实现为 exp686/N，包含 D64 背景、字节距离曲线、S8 修正和 V8 事件专家。
历史实验记录更新至 exp706，后续候选的验证状态见研究进展说明。

## 阅读入口

- [exp688 外部 AI 提问书](docs/exp688/exp688-外部AI提问书.md)
- [版本表现、研究进展与证据范围](docs/exp688/研究进展与证据范围.md)
- [源码与独立构建](source/README.md)
- [历史实验原文与索引](experiment/README.md)
- [exp610 至 exp701 的整体复盘](docs/research/exp610-701复盘与研究优先级.md)
- [赛题解析](docs/task/EDA2026赛题一-MinerU-flash.md)及 [V0.3 原 PDF](docs/task/赛题一-V0.3.pdf)

## 外部分析补充材料

2026-10-25 补充逐条数据、生成和训练代码、阶段补丁及原始性能证据。
各目录 README 给出文件结构、数据含义、复现命令和验证范围。

| 目录 | 内容 |
| --- | --- |
| [path_witness](path_witness/README.md) | exp705 全部 239,616 条查询、五份路径见证文件、精确求解及交叉重放代码、最短路径平局策略 |
| [accuracy](accuracy/README.md) | 479,232 条完整端点 exact/prediction、采样权重与历史划分，原 exact 求解器源码和独立重建入口 |
| [dataset_protocol](dataset_protocol/README.md) | 冻结 100M/1B 生成器、seed、可达性索引、历史排除集合、分层 exact 抽样及源 pin 隔离 |
| [training](training/README.md) | D64、曲线、S8、V8 的训练与导出来源，百万行训练数组、特征定义和残差重训入口 |
| [benchmark](benchmark/README.md) | r9 机器配置、目标 6242R 截图、exp703 perf、exp704 全部十四次完整 100M 记录 |
| [stage_changes](stage_changes/README.md) | exp704/706 的 688 槽目录补丁、候选 header、编译配置、解析对照和阶段验收 |

路径见证已全部重求并核对 SHA，958,464 次交叉重放逐元素一致。
原 exact 求解器及阶段 ELF 在 r9 上均重建为相同 SHA；
V64 和 S16 route 0 也已从导出的数据重训，参数与冻结模型一致。
检查总表见 [supplement-verification.json](supplement-verification.json)，
来源说明见 [supplement-provenance.json](supplement-provenance.json)。

```sh
sha256sum -c supplement-SHA256SUMS
```

当前 r9 配置识别为 Xeon Gold 6226R，6242R 是用户指定的另一台目标机器；
现有材料没有 6242R 实测成绩。208×288 是项目当前角色域，官方文档尚未明确
将合法请求限定为此域，域外可达例子及实现限制已单列在请求协议中。
本次补充没有新增完整 100M/1B 估计运行，`source/` 的冻结文件身份全部保留。

## 历史记录

实验原文共 851 份，包含 exp611 至 exp706 的 99 份记录。文件身份见
`docs/experiment-log-manifest.json`。记录保留原始假设、停止条件和结果，
其中的机器路径指向当时研究工作区。`validation/results/` 收录本轮讨论所需的主要原始证据。
早期日志中的 1M、10M 为历史测试；后续完整程序验证使用非重复 100M、1B。

## 构建与身份

```sh
cd source
python3 build.py
./build/estimate -in request.csv -out result.csv
```

复现环境为 Ubuntu 22.04 x86-64、GCC 11.4.0、binutils 2.38 和匹配的静态运行库。
构建脚本检查全部归档文件、五份目标文件、静态链接、容量与最终 ELF SHA。
五个架构 JSON、模型、压缩背景和静态 Zstandard 依赖均随源码提供。

exp688 ELF 为 93,402,392 B，完整 SHA-256 为

```text
66fb0307d24b4ce2fa4514350e97420acf9de37171419f15c6001ac15dc985e3
```

## 已有完整 1B 证据

r9 上全端口、非重复 1B 的 CPU 为 **243.302538 秒**，
wall 为 269.009493 秒，峰值 RSS 206,372,864 B，单线程且完整输出契约通过。
同次输出的 **3,833,856 条 exact 分层样本**估计 Acc 为 **98.658061657%**。
这套输入已被历史验证观察，官方隐藏分布的成绩仍需平台实测。

本轮咨询目标为总体 Acc 严格大于 99%、非重复 1B CPU 约 100 秒，
后续争取 Acc >99.1%、CPU <90 秒。提问书完整说明交付约束、当前研究主张、
架构上限问题及通用 CPU/6242R 自动分派，附用户提供的目标 CPU 截图。
exp706 已完成 100M 验证，完整 1B 待测。本仓库的查询源码保持 exp688 身份，
后续实验作为改进建议的背景材料。当前仅更新咨询材料，算法实验保持暂停。
