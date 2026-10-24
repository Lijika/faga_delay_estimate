# 实验347 rankZ强制内联

2026-10-17，起点 e640927。正式入口及冻结基线为 exp335/exp334，
ELF SHA-256 为
`51f0002a31230262bc993110b64d68fe0a3ace6f225d5882dff6e7fd43cadd2b`。
本机开工可用 422,454,956,032 字节，约 394 GiB。

## 主假设与唯一候选

exp336 的同机器码采样中，rankZ 独立函数占 U-output / 公开完整 1M
约 18.67% / 16.11%。主假设为内联后减少调用和捕获参数读取的成本，
足以超过代码尺寸及寄存器压力的增长。这是待验证的工程假设。

候选 inline 只将私有 `legal_path_search.cpp` 的 rankZ lambda 添加
`__attribute__((always_inline))`。函数体、relax、排序键、heap、路径重放、
cap480、weight1010、模型、Both 端点、cache0 与 262144 行批次保持。
使用冻结基线的 GCC 13.3、C++17、O2、通用静态构建，保持构建参数。
GNU 属性语义参照本机 `/usr/share/info/gcc-13.info.gz` 的
Common Function Attributes 中 always_inline 条目，实际语法由编译核验。

改动经过 LegalPathSearch、estimateText、生产 CLI 及搜索探针。
正式源码和交付入口等候完整 1M 验收。本轮复用现有实验脚本，
无新增依赖和接口。

## 冻结验证与计时

先核对 12150 条搜索全部非时间字段及 126462 条路径边，
复用 exp332 搜索探针与 exp333 的 48184 条已标注开发请求、7 行边界、
6 类 CLI 消费者、特殊 CSV、诊断、帮助和写出失败检查。
输出与路径等价时复用标签、公开评分和分组误差，预期变化 0 行、
acc 配对差 0。任何身份、搜索、路径或输出不一致即停止性能运行。
该属性为单行编译改动，复用行为审计；队列和批次独立测试复用既有证据。

Xeon Gold 6226R 核 3、单线程、同机串行。仅在远端
`/home/lhj/lhjwork/eda2026` 执行。20k 和 100k 使用 exp334 绑定的
非重复 U-output 开发前缀，各预热一对，随后三对 AB、BA、AB。
完整程序计时包含初始化、输入与 CSV 输出，主指标为 user+sys。
主分析使用配对差的 df=2 的 95% t 区间，两端扩大 0.02 秒计入舍入。
1% 作为预登记实际幅度参照，明确 CPU 收益继续保留。

100k 差区间上界小于 0 时，扩至完整非重复 U-output 1M 三对
AB、BA、AB，之前各臂 20k 预热一次，之后候选公开 1M 两次。
100k 区间跨零保留待定并停止本轮扩大；下界大于 0 结束该固定实现扩大。
完整 1M 核对端点顺序、行数、恰好三字段、整数 delay、精确 EOF、
完整 SHA、多次一致、单线程、RSS <=2,000,000,000 字节和每次 <=3600 秒，
ELF <100,000,000 字节。acc 与本次输出的 CPU 联合记录，
评分和 exact 新成本单列；相同输出复用评分。

输入内唯一性与用于选型分别说明。以上均为开发与交付检查，
有效阶段成绩依次来自非重复 100M CPU <100 秒和非重复 1B CPU 100--300 秒
的完整程序实测。小规模数据和外推保留筛选及成本分析用途。

## 复现与证据

```sh
python3 validation/exp347_rank_inline.py prepare
python3 validation/exp347_rank_inline.py audit
python3 validation/exp347_rank_inline.py run
python3 validation/exp347_rank_inline.py check
python3 validation/exp347_rank_inline.py full
python3 validation/exp347_rank_inline.py check-full
```

私有源码与二进制使用 `build/exp347/`；冻结身份、编译日志、搜索及行为审计、
每次计时和统计使用 `validation/results/exp347/`。
协议、驱动、源码、二进制、工具链、架构、模型、输入和基线身份纳入冻结。
结果另写文档，保留失败和原始证据，记录 CPU、资源、磁盘及未验证范围。
