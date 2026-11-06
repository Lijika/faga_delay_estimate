# 离线追踪与源端口次序

目录中的 nominal_source 是用于架构名义标签的历史求解器，配套 src/architecture.cpp。当前正式源树 source 则提供 SRB 的五份 JSON 和 exp579-models.h。不可把旧求解器的顺序直接用作当前 EAT 顺序。historical 的 roleTargets 枚举所有输出 raw ID 升序，当前 target 索引由 kTargetIndex 的非负值指定。对 valid raw IDs 排序 current target index 即得按 EAT 顺序的旧序号。source 需要先找到 kSourceIndex>=0 的 raw ID，按 kSourceIndex 再排序。cross/gather.py 实现逐源请求与此变换。

打包的 `inputs/` 包含前两批架构金标与权重，以及可编译的追踪和名义标签脚本。公开百万来自正式仓库 data/official-1m；历史子集来自历史提交：

~~~bash
git -C /tmp/bf4-repo show fed41553d0f85b963612ed9fc783d8d96598d918:accuracy/exp688-exact-subset.csv.gz > /tmp/bf4-history.csv.gz
python3 repro/inputs/trace.py /tmp/bf4-repo/source /tmp/bf4-trace-build
~~~

trace.py 的推理产物在运行目录生成 nomtrace.bin。分别用公开、历史、两批新源的请求运行并各自保存成 pub.raw、hist.raw、fresh.raw、blind.raw。前两批与第三批均按给定 weights.csv 评分。统计工具中 pub、hist、fresh、blind 分别对应公开、历史、新源一、新源二。第三批使用 third 标签。golden CSV 不会被读进参赛 ELF。独立求解器的重建与向量表、源索引的实际示例见对应的参数解析（--help）以及各章的数学描述。

训练样本矩阵和数 GB 临时距离场并未逐一打包。standalone 二进制包提供实际计时的 ELF，矩形和 CART 支持从冻结生成源码直接再链，具体 SHA 核对见各分支 receipts。分阶段汇总中的 CPU 占用来自实测，文中的周期仅是指定频率下的时间预算折算。

## 重新生成四个整源架构场

在研究包根目录设定 SRC 为仓库 source 的绝对路径，OUT 为可写的空工作目录。四个源的作用是拟合非均匀格点、插值与创新码本。不是从测试请求的答案提取的点。下面的 full-residue-field 输出含认证头的 152,618,144 B 整源文件。

~~~bash
mkdir -p "$OUT/fields"
bash repro/nominal_source/build.sh
repro/nominal_source/field "$SRC/arch" 'ZSNB[4]' "$OUT/fields/0.bin"
repro/nominal_source/field "$SRC/arch" 'A_DY' "$OUT/fields/1.bin"
repro/nominal_source/field "$SRC/arch" 'ZDN[2]' "$OUT/fields/2.bin"
repro/nominal_source/field "$SRC/arch" 'S_DQ0' "$OUT/fields/3.bin"
OPENBLAS_NUM_THREADS=1 python3 knots/fit.py "$OUT/near-model" "$OUT/fields/"{0,1,2,3}.bin --force-near
g++ -O3 -std=c++17 -I repro/nominal_source knots/export.cpp repro/nominal_source/src/architecture.cpp -o "$OUT/export"
~~~

完全重新训练时需现有公开 gold.csv 与由 trace.py 生成的 pub.raw。逐源离线编码可以较慢；--jobs 只影响离线生成，目标 ELF 仍为单线程。为与所测的 AQ35 对齐，按此处参数编码：

~~~bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 knots/encode_rates.py "$OUT/near-model" "$OUT/export" "$SRC/arch" repro/inputs/sources.ids repro/inputs/targets.oldidx "$OUT/public/gold.csv" "$OUT/pub.raw" "$OUT/wire" --fields "$OUT/fields/"{0,1,2,3}.bin --count 208 --jobs 2 --maxrate 10 --adaptive-price 0.5683326721191406 --save adaptive
~~~

构建脚本将原来在建场时用到的五个架构 JSON 压缩入程序，并保留输出协议。快速复建则使用 knots/native/rebuild_frozen.py，已经在另一个空构建目录逐字节重建相同 SHA-256。SGCbias 可以用 bias/build.py、evidence/sgcbias/delta.zst 和 speed 目录的子曲面资产直接重建，无需重新求 48 个锚点。
