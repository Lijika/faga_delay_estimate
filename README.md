# faga_delay_estimate

FPGA SRB 布局布线延时估算的 exp610 冻结源码与技术咨询材料。

## 源码与构建

`source/` 原样保存发布版本 `exp610-d64-generic-1b251s-dddbb955-dirty` 的 69 个文件，包含 D64 背景、16 份 R8 模型、五份 SRB 架构 JSON 与原始验证证据。`source/SHA256SUMS` 覆盖其中 68 个归档文件。

```sh
cd source
python3 build.py
./build/estimate -in request.csv -out result.csv
```

复现冻结 ELF 需要 Ubuntu 22.04 x86-64、GCC 11.4.0、binutils 2.38 与匹配的静态运行库。完整要求见 [源码说明](source/README.md)。构建脚本校验源文件、静态链接、十进制 100 MB 容量和冻结 ELF SHA-256；工具链差异会影响字节复现。

## 咨询材料

- [外部 AI 提问书](docs/exp610/exp610-外部AI提问书.md)
- [历史实验与理论摘要](docs/exp610/exp610-历史实验与理论摘要.md)
- [发送说明](docs/exp610/发送说明.md)
- [参考材料 ZIP](docs/exp610/exp610-外部AI参考材料.zip)

文档中的 `source/...` 路径相对于本仓库根目录。参考包中的路径按 ZIP 成员解释。冻结源码和历史记录中的机器路径保留原始证据身份。

## 已有证据

远端 Xeon 已有完整非重复 1B CPU 251.136671 秒、独立 1M Acc 98.333506862% 的记录。当前精度距离最终 Acc 严格大于 99% 的目标仍有差距。官方隐藏集、其他 CPU 与全量 1B exact 精度仍待验证。本次仓库整理复用已有运行和独立重建证据。
