# 三项模型资产复现工具包

主报告：**`三项模型资产的算法与完整复现报告.md`**。

- **已经验证**：832 个历史远域帧解析 + Zstd-8 字节一致性；冻结 `books.npz` 转 `books.f32`；5 个原始 JSON 转 `arch.bin`；六张 `*.inc` 表均可由观测 NPZ 精确导出。
- **没有宣称已验证**：在零冻结数值输入下跑完全部最短路与 120 个 KMeans 分级码本，重新训练出 832 帧。训练脚本有完整路径，但需要在算力充足的服务器执行，并锁定原始环境。

## 快速恢复当前发布资产

需要已有的独立源码包 `FPGA-estimate-self-contained-source.zip`，解压至 `$KIT`。本工具包解压后进入本目录：

```bash
python3 tools/split_frames.py --frames "$KIT/model/frames.bin" \
  --out /tmp/asset-wire --reencode
python3 tools/pack_assets.py --wire-dir /tmp/asset-wire \
  --out /tmp/asset-model --compare-frozen
python3 tools/check_frozen_tables.py
```

上述三个脚本已经在实际冻结数据上执行成功。`pack_assets.py` 生成三个文件及 `frameBytes.inc`，不需要原 `estimate` ELF。

## 从原始图训练自己的资产

需要与本研究对应的完整冻结 `faga_delay_estimate/source/`（带 5 JSON、`assets/surface779/`、`build.py`）。需要 NumPy、Pandas、SciPy、scikit-learn 和 Python zstandard。

```bash
bash tools/full_train.sh /abs/path/to/source \
  /abs/path/to/work /abs/path/to/public/cohort.csv.gz
```

这个命令计算量较大，完整训练未在本次运行完成。注意生成新模型以后还要更新 `nearOrder.inc` 等六张 C++ 表及原 `frameBytes.inc`，而不是只替换三个 `model` 文件。

## 包结构

- `raw_arch/`：由冻结 `arch.bin` 已实际无损恢复并检查 SHA 的原始 5 JSON。
- `frozen/`：冻结的 `books.npz`、8 个 k40/k56 观测 NPZ、6 张文本表、历史 832 帧长度表。
- `sources/`：历史训练器、最短路认证求解器、导出工具、角色映射和跟踪工具。
- `tools/`：独立打包与完整帧语法验证脚本以及全链训练脚本。
- `receipts/`：原地计算得到的 SHA、全 832 帧信息和参数表对照收据。

**不包含**原有的 94 MB `frames.bin`，因为你的上一独立源码包已经有它。这样既避免重复发送同一训练码流，又保留了从零训练新的 832 个帧的源码入口。
