# exp610 正式版完整源码

本目录对应已发布的 `exp610-d64-generic-1b251s-dddbb955-dirty`。运行入口固定选择
exp609/F 的通用 SSE2 查询实现，包含 D64 几何数据和 R8 修正模型。
源码取自远端冻结构建，文件来源和 SHA-256 见 `provenance/source-origin.json`。

## 独立构建

复现环境为 Ubuntu 22.04 x86-64、GCC 11.4.0
(`Ubuntu 11.4.0-1ubuntu1~22.04.3`)、GNU binutils 2.38、glibc 2.35
(`Ubuntu GLIBC 2.35-0ubuntu3.15`)，构建脚本使用 Python 3 标准库。
安装 GCC/G++、binutils 和静态 C/C++ 运行库后，在本目录执行

```sh
python3 build.py
```

生成 `build/estimate` 和 `build/build-report.json`。脚本先验证所有归档文件的 SHA-256
及嵌入架构文本，再编译全部源文件、检查静态链接与 100,000,000 字节容量限制，最后核对
发布 ELF 的完整 SHA-256。编译参数、链接顺序和精度设置沿用冻结版本。
相同工具链用于复现发布文件；其他工具链可能产生不同字节，此时脚本保留产物并报告失败，
该产物需要独立验收。

程序调用方式为

```sh
./build/estimate -in request.csv -out result.csv
```

算法测试按项目约定在 `r9r4900` 上执行，输入须覆盖全部 59,904 端口对。
程序运行所需的五份架构和模型数据均嵌入 ELF。

## 文件内容

- `src/` 包含入口、完整查询实现、架构加载与解析代码、生成的架构文本和预计算 resolver。
- `include/` 包含 R8 树参数、D64 几何访问、SSE2/SSE4.1/AVX2 内核、批处理解析和输出代码。
- `assets/` 包含 69,303,616 字节的冻结 D64 数据和嵌入汇编。
- `models/` 包含导出为查询头文件之前的 16 份 R8 模型 JSON。
- `arch/` 包含五份原始 SRB JSON；`scripts/gen_embedded_arch.py` 可核对或重建嵌入文本。
- `provenance/` 包含原编译命令、源文件身份、发布版本信息、完整程序测试和打包证据。
- `SHA256SUMS` 覆盖本目录全部归档文件；构建输出写入独立的 `build/` 子目录。

几何数据、树参数和 resolver 是本版本的固定训练或预计算资产，均随源码提供。
编译使用这些资产，无需安装 XGBoost 或重跑训练。SSE4.1/AVX2 实现随原版保留，
正式入口固定选择 F/SSE2。汇编仅将原绝对 `.incbin` 路径改成包内相对路径，
原文件保存在 `provenance/original-geometry.S`。

## 发布身份与已知范围

静态 ELF 为 76,907,800 字节，SHA-256 为

```text
7e9ab5769e11f090fcf4c189851c09076a96580d02a9c9705996e0bead259c1d
```

r9 上已有全端口、非重复完整 100M CPU 24.728427 秒及完整 1B CPU 251.136671 秒证据。
独立完整 1M Acc 为 98.333506862%；1B 中 239,616 条全端口分层 exact 样本的加权
Acc 为 98.346099343%。本源码包已在 r9 的独立目录完成重建，六份目标文件和最终 ELF
均与冻结发布构建逐字节一致，因此复用原完整测试证据。重建命令与校验结果见
`provenance/standalone-build-r9.json`。
平台隐藏集、其他 CPU 的表现和完整 1B 全量 exact 精度仍待验证；当前已有精度证据低于
项目文档规定的最终 Acc 严格大于 99% 要求。

本目录用于源码交付。比赛上传包为历史发布目录
`subm/versions/exp610-d64-generic-1b251s-dddbb955-dirty/submission.zip`，其中只有
`bin/estimate`。本次源码整理保留该提交包及 `subm/latest/`、`subm/submission.zip` 的身份。
