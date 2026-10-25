# exp704 / exp706 的直接端口目录

[direct-port.patch](direct-port.patch) 是相对冻结 exp688 的单文件源码改动，对应 `source/include/exp601_port_parser.h`。完整候选 header 同时保存在本目录，其 SHA 与 exp704 freeze 相同。`source/` 继续保留 exp688，方便独立比较。

原实现使用 2,048 槽哈希表。候选根据端口名称中的 role、族、方向、variant 和 lane 直接计算 688 槽目录索引，再核对完整短键和长度。初始化检查全部 496 个端口没有索引碰撞；解析仍保留端点坐标、长度和存在性检查。两个 header 的完整身份见 [parser-identities.json](parser-identities.json)。

## 重建及编译设置

```sh
python3 stage_changes/build.py /tmp/exp704-build
```

该入口先把 `source/` 复制到新目录，按 exp688 的冻结构建规则验证原版，再替换已核验的候选 header、重编 worker 并链接。最后运行 [exp704_port_decoder.cpp](exp704_port_decoder.cpp)，完成 829,072 次新旧解析对照。

补丁也可以在独立源码副本中使用 `git apply`。它的路径以源码根目录为基准。

```sh
git -C /tmp/isolated-source apply --check /path/to/repository/stage_changes/direct-port.patch
git -C /tmp/isolated-source apply /path/to/repository/stage_changes/direct-port.patch
```

字节复现环境为 Ubuntu 22.04、GCC 11.4.0、binutils 2.38 和匹配的静态运行库。主设置沿用 `-O3 -march=x86-64 -mtune=generic -fno-fast-math -ffp-contract=off`，查询设置为 `EXP582_BLOCK=64`、`EXP596_BATCH=8`、`EXP608_SIMD=0`、`EXP640_TREES=8`、`EXP684_V_ONLY`，最终静态链接。完整参数见 [verification-r9.json](verification-r9.json)。

本轮重建 ELF 为 93,380,632 B，SHA-256 如下，与 exp704/706 的冻结产物一致。

```text
8c5dec652cdcffae774c96b60e49c848a436622ac64a906caf0afc6068d4ecc1
```

首次重建在调用远端缺失的 Git 工具时中断；入口随后改为复制并核验冻结 header，沿用已通过的 exp688 构建结果完成检查。发布的补丁另在本地独立目录应用并核对 SHA，见 [patch-verification.json](patch-verification.json)。

## 已有验收范围

exp704 完成六对正式 100M 计时及两次 warmup，全部输出 SHA 相同。C 相对 A 的平均 CPU 节省为 0.785568 秒，95% CI 为 [0.684197, 0.886939] 秒。exp706 又通过清洁目录、空环境、完整 100M 的输出及资源检查。

逐次运行表见 [benchmark](../benchmark/README.md)，原始计时和协议在 [exp704](../validation/results/exp704/100m-report.json)，清洁验收在 [exp706](../validation/results/exp706/package-check.json)。这份阶段改动已有完整 100M 证据，完整 1B 与 6242R 实测仍待完成。
