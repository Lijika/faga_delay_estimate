# exp913 PackedJoin 与现有CPU优化合并

在本版本目录的可写副本中，用 r9 的 Ubuntu22.04、GCC11.4.0、binutils2.38 静态重建。

```sh
python3 source/build.py --variant fast --mode source --out-dir rebuild
sha256sum rebuild/fast/estimate
rebuild/fast/estimate -in request.csv -out result.csv
```

ELF SHA-256 为 `c17781d33c9fa1c2d3672b320a4c0d9f3d667d3dee6ddac75dfcb5d5a485a3a0`，大小为 99,329,624 B。
source/ 包含全部源码、PackedJoin配套模型与修正表、静态zstd库和XZ解码源码。
程序自动识别6242R/6226R并检查可用指令集；其它x86-64机器使用SSE2批处理。
保留B2442初始化、逐源内存释放、batch64解析及输出；查询改用PackedJoin有限物理修正表。
发布ELF在r9完成官方1M五次一致性、原始PackedJoin逐字节等价、通用路径等价及U-role1M两路径检查。
完整官方1M Acc为99.21508547390856%，峰值RSS约1.965GB。
按用户要求先发布，再测完整A/B200M和1B；后续证据保存在 validation/results/exp913-packedjoin/，该不可变发布记录保留发布当时状态。
model_reproduction/保留历史exp855/exp858离线训练资料。当前采用用户提供的PackedJoin资产，其身份见source/manifest.json和evidence/supplied-PackedJoin.json。
PGO、按CPU缓存容量调参、官方平台和未知输入验收未执行。
