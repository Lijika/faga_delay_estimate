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

r9 Xeon 上全端口、非重复 1B 的 CPU 为 **243.302538 秒**，
wall 为 269.009493 秒，峰值 RSS 206,372,864 B，单线程且完整输出契约通过。
同次输出的 **3,833,856 条 exact 分层样本**估计 Acc 为 **98.658061657%**。
这套输入已被历史验证观察，官方隐藏分布的成绩仍需平台实测。

本轮咨询目标为总体 Acc 严格大于 99%、非重复 1B CPU 约 100 秒，
后续争取 Acc >99.1%、CPU <90 秒。提问书完整说明交付约束、当前研究主张、
架构上限问题及通用 CPU/6242R 自动分派，附用户提供的目标 CPU 截图。
exp706 已完成 100M 验证，完整 1B 待测。本仓库的查询源码保持 exp688 身份，
后续实验作为改进建议的背景材料。当前仅更新咨询材料，算法实验保持暂停。
