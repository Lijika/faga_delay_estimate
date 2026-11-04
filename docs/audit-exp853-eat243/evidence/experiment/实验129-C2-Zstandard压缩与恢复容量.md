# 实验129 C2 Zstandard压缩与恢复容量

2026-10-09，Asia/Shanghai。分支`research/exp129-zstd-residue-capacity`，起点`2a929d5`。开工`/dev/sdd`可用464G。协议先于Zstandard结果提交。

## 固定候选

实验128的dx/zlib9流为88,787,733 B，距离1MB存储门槛差33,996 B。沿用相同dx窄表字节流和完整宽表语义，固定测试Zstandard单线程带内容大小与checksum的level 3、9、19，使用系统libzstd 1.5.5 C API。level 3作为速度候选，9作为平衡候选，19作为容量候选；均为单帧，不使用多线程或字典。

固定基线为exp128的dx/zlib9流、exp120正式二进制与完整窄/宽表SHA。压缩器只替换离线流格式，解码器尚未接入生产。当前实验只决定是否值得进行静态C++恢复构建。

## 核对与门槛

对每个候选核对`ZSTD_getFrameContentSize`为230,031,360 B、`ZSTD_findFrameCompressedSize`等于文件大小、单帧无尾字节、checksum有效，解压后的窄表SHA和逐块恢复后的宽表SHA。重复压缩要求字节相同。资源记录压缩、解压与宽表恢复CPU、wall和RSS，单进程CPU≤300秒、wall≤600秒、RSS≤2GB。

最小候选按压缩字节选择。只有相对dx/zlib9再减少至少33,996 B、严格小于100,000,000 B的估算文件，才进入C++恢复实现；静态文件和完整1M仍需独立门槛。所有候选未过时方向保留，正式exp120不变。

## 实现、冻结与证据

新增`validation/exp129_zstd_capacity.cpp`和`validation/exp129_zstd_capacity.py`，复用实验119的dx编码、exp118的窄/宽表、身份与恢复夹具。私有文件放`build/exp129/`，结果放`validation/results/exp129-*`，拒绝覆盖。

```sh
build/venv-ml/bin/python validation/exp129_zstd_capacity.py
```

冻结libzstd头文件/版本、编译命令、exp128流及完整表身份、当前正式文件、脚本和五个架构JSON。压缩器API按官方文档核对单线程默认`nbWorkers=0`、内容大小、checksum及错误码检查。收尾记录空间与可重建副本，不删除长期引用的dx流。

## 结果与判定

冻结实现提交`cb4b83c`。23项输入身份复核通过，三个候选的完整230,031,360 B往返都等于同一dx字节流，重复压缩字节相同，单帧、内容大小、checksum和EOF均通过。

| level | frame B | 相对dx/zlib9减少 B | 首次CPU s | 重复CPU s | 最高RSS B |
| --- | --- | --- | --- | --- | --- |
| 3 | 78,200,840 | 10,586,893 | 3.48 | 3.37 | 696,115,200 |
| 9 | 73,049,556 | 15,738,177 | 7.65 | 7.52 | 705,867,776 |
| 19 | 58,017,384 | 30,770,349 | 133.48 | 134.84 | 695,304,192 |

按预先固定的字节选择规则采用19级，容量门槛通过。相对正式dx/zlib6流减少31,736,353 B，替换blob的文件估算为68,016,239 B。静态解码器的实际链接字节仍待构建测量。

完整dx往返相同，把实验128已核验的dx逆映射和quantum恢复等价传递到三个候选；恢复完整窄表SHA为`16089e40e5fe65f4376340492fca6f62b4727c26cbef6db57d97f7673dbf52da`，宽表SHA为`800dcf4af93e6fe5a298d239479ebc84c12a06fc1ae7712e9f194e4cff347e40`。Python主体最高RSS1,028,333,568 B，首次及重复进程的CPU、wall、RSS均通过固定门槛。

本次CPU包含读写、压缩、解压与逐字节比较，组件计时尚未拆分；宽表核验经完整dx字节相等传递，C++生产恢复另验。原始结果见`validation/results/exp129-capacity.json`，补充逐项核对见`validation/results/exp129-evidence-check.json`。下一轮固定实际静态恢复候选及组件计时，然后检查完整1M。当前正式exp120继续使用原文件。

## 空间与副本

逐个核对三个`dx-zstd{3,9,19}.roundtrip.u8`与`dx-delta.u8`的完整SHA相同，保留后者。副本仅被本轮结果身份引用，重建命令及删除清单见`validation/results/exp129-cleanup-plan.json`。按清单删除三个副本，释放690,094,080 B；收尾`/dev/sdd`可用464G。三个frame及原始计时文件保留。
