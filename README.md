# faga_delay_estimate

本轮外部 AI 咨询以 **exp728 冻结阶段版**为对象。完整非重复 1B 的 CPU 为 **184.190953 秒**，同次输出的 3,833,856 条分层 exact 估计 Acc 为 **98.644899649%**。目标是总体 Acc 严格大于 99%、完整 CPU 接近 100 秒，后续争取 >99.1% / <90 秒。

实验日志已补齐至 exp743，本次新增的 exp733 至 exp743 共11份记录见[历史实验索引](experiment/README.md)。此次同步包含日志及其索引和校验信息，新增实验的代码与原始结果尚未上传。

## 阅读入口

- [exp728 外部 AI 提问书](docs/exp728/exp728-外部AI提问书.md)
- [exp707 至 exp732 的复盘、失败范围及暂停条件](docs/research/exp707-732复盘与停止范围.md)
- [冻结源码与独立构建](source/README.md)
- [本轮资料更新和清理说明](docs/exp728/资料更新与验证.md)
- [历史实验索引](experiment/README.md)
- [官方赛题解析](docs/task/EDA2026赛题一-MinerU-flash.md)及 [V0.3 PDF](docs/task/赛题一-V0.3.pdf)

提问书重点要求判断当前架构是否值得继续投入，并给出可实施的状态表示、路径选择、训练、CPU 优化和替代架构。历史失败按表示形式、数据域和资源配置限定结论；同时要求专家主动补充研究盲区。

## 材料地图

| 目录 | 本轮用途 |
| --- | --- |
| [source](source/README.md) | exp728 全部源码、五份架构、模型、压缩资产及静态构建 |
| [accuracy](accuracy/README.md) | 全部 3,833,856 条 exact/exp688/exp728 配对记录，479,232 条代表性 CSV，权重和历史划分 |
| [path_witness](path_witness/README.md) | exp705 全部路径、四位置交叉重放、exact 与 tracer 源码、平局策略 |
| [training](training/README.md) | 当前 T2D6/V8 及历史 S8 的重训入口，百万训练数组，背景与曲线流程 |
| [dataset_protocol](dataset_protocol/README.md) | 1B、exp720 新 100M 和旧 exp685 的完整生成与抽样协议 |
| [benchmark](benchmark/README.md) | 机器身份、exp727 十四次 100M 记录、exp728 1B 及历史 perf |
| [research_code](research_code/README.md) | exp707 至 exp732 研究原型、生成与审计代码 |
| [experiment](experiment/README.md) | 888 份历史记录，覆盖至 exp743，保留原始假设、停止条件和证据范围 |
| `validation/results/` | exp732 及以前已收录的原始结果、冻结身份和验收 |

`source/` 的五份目标文件和最终 ELF 已在 r9 独立重建为相同 SHA。逐条精度数据的端点、唯一性、角色 pair、抽样权重、历史源 pin 标记和两版 Acc 已重新计算。其余复用与新增核验见 [publication-verification.json](publication-verification.json)。

```sh
sha256sum -c PUBLICATION-SHA256SUMS
cd source
python3 build.py
./build/estimate -in request.csv -out result.csv
```

复现工具链为 Ubuntu 22.04、GCC 11.4.0、binutils 2.38 和匹配静态运行库。exp728 ELF 为 93,442,072 B，SHA-256 为

```text
9c05eb2ce01450f58ffa6d2adaa6793f307f44d8962a66e5d36453be32c5c68f
```

旧 exp688 提问和重复版本说明已从当前目录移除；历史提交 `fed4155` 可恢复当时完整快照。exp688 配对预测、既有路径、训练、生成器、相关实验及失败证据继续保留。exp704/706 的目录补丁已包含在当前源码，旧独立补丁入口已移除。

当前性能实机为 **Xeon Gold 6226R**，用户目标机为 **6242R**。已有 1B 属于历史开发输入，Acc 是分层抽样估计。6242R、官方平台和角色域外合法输入覆盖仍有待验证。本次整理没有新增完整估计程序运行，算法研究保持暂停。
