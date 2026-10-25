# exp688 审查配套代码

这些文件用于复核报告中的独立数学推导和开展后续实验，不是已经集成到仓库的优化补丁。

## 本轮已运行

- `int8_equivalence.cpp`：四种 INT8 内核，每个 165,600 个整数案例和 4,096 个八块 scale 合成案例。结果见 `int8_local_result.json`。
- `proof_checks.py`：容量、范围和目标差距计数；89,018 个合成区间投影案例。结果见 `proof_checks_result.json`。
- `audit_accuracy.py`：仅运行了四行合成数据自测；见 `audit_script_selftest.json`。

本地 CPU 是 AMD EPYC 9V74，编译器 GCC 14.2.0。这里没有 Xeon Gold 6242R 性能结果，也没有 GCC 11.4 冻结构建结果。

## 尚未对项目真实数据运行

- `audit_accuracy.py`：需传入仓库的 `accuracy/exp688-exact-subset.csv.gz`。使用发布权重，输出设计型分层标准误及近似区间。不是新的盲测。
- `audit_witness.py`：需先用仓库自带 `path_witness/unpack.py` 解压并核验身份，再传入解压根目录。需要 NumPy。输出守恒、覆盖和重放统计；不是独立最短路求解器。

## 使用

```sh
g++ -std=c++17 -O2 -march=x86-64 -fno-fast-math -ffp-contract=off \
    int8_equivalence.cpp -o int8_equivalence
./int8_equivalence
python3 proof_checks.py
python3 audit_accuracy.py /path/to/repo/accuracy/exp688-exact-subset.csv.gz --out accuracy-audit.json
python3 audit_witness.py /path/to/unpacked-witness --out witness-audit.json
```

`--candidate-column` 可用于对已经按 sample_index 精确对齐到同一 CSV 的候选预测做配对比较。不要把不同行序或不同查询的预测拼在一起。

C++ 中 target 属性是独立内核测试的组织方式；生产制品仍建议按报告拆分通用初始化和多个 ISA 单元，并做静态链接、构造器、CPU/OS 状态和完整输出审计。只通过点积测试不等于完整函数等价。
