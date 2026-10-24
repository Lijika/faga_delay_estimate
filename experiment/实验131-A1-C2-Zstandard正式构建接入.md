# 实验131 A1 C2 Zstandard正式构建接入

2026-10-09，Asia/Shanghai。分支`research/exp131-zstd-release`，起点`0a4f798`。开工`/dev/sdd`可用463G。协议先于正式生成器和打包验证提交。

## 固定方案与范围

接入exp130唯一已验收候选。正式`src/embedded_residue.h`采用相同Zstandard恢复代码，保留dx逆映射与原查询和depth10模型。`scripts/gen_embedded_residue.py`继续使用原审计、编码与完整宽表SHA检查，只把离线zlib6替换为固定Zstandard19、单线程、checksum和内容大小；通过小型C++助手调用已安装libzstd。两份构建脚本链接`-lzstd`，提交包算法标识更新为`exp131-zstd-depth10`。

直接影响生成器、两份构建脚本、压缩数据头、`embedded_residue::restore`与发布身份文档。动态诊断和各历史实验脚本保留其冻结源码及输入；已通过的exp130完整表、异常流和24次完整1M证据按二进制身份复用。

## 验收与身份

生成的新frame必须与exp129选定19级流完整SHA相同，恢复窄/宽表及INF保持。正式静态构建必须与exp130已验收文件完整SHA相同，68,201,104 B、严格小于100,000,000 B、自包含。正式解码头必须与exp130候选相同；其余查询源码和模型逐文件保持身份。

普通构建运行受影响路径，核对完整公开1M与holdout输出SHA；新离线助手记录纯压缩和纯解压CPU、RSS，补充exp129混合计时。记录静态构建和普通构建身份，缓存命中仅在输入、实现和产物身份均相同后复用。正式包使用`--verify`，其公开1M和holdout同时作为最终包复核，完整契约与资源证据按相同二进制SHA复用exp130。

已阅读`subm/README.md`和`subm/versions/README.md`。保留exp120不可变包，选择全新label；按不可变版本、latest镜像、评测指针的固定顺序写入。打包完成核对zip内`bin/estimate`、版本文件、latest、根入口与`build/submission/estimate`完整SHA，重复label拒绝并保持当前指针身份。版本元数据包含提交、编译器、flags、构建清单、bin与zip身份。

失败时只停止本轮正式接入，使用保留的exp120文件；通过后正式产物切换至新版本，31,798,896 B剩余预算用于后续有精度与成本证据的候选。容量释放属于工程收益，真实图精度、平台1B与隐藏分布的成绩保持原验证边界。

## 证据

结果写`validation/results/exp131-*`，私有校验目录`build/exp131/`。冻结exp130完整证据、生产源码、生成器和助手、五个架构、原正式身份与打包规则。每个可验证阶段检查diff后提交Git；收尾记录空间和核对过的重复文件清理。

## 实际结果

实现提交`62dcc48`。新生成器完整复现exp129的58,017,384 B单帧SHA，并恢复exp130同一460,062,720 B宽表SHA；原范围审计的nonmultiple、int16_overflow与roundtrip_mismatch均为0。新离线助手纯压缩CPU129.739232秒、纯解压CPU0.306810秒，RSS1,191,387,136 B；首次私有完整生成器CPU164.51秒、wall166.59秒、RSS1,479,684,096 B。两次生成所得frame相同，输入/产物身份核对后缓存命中。

普通构建为66,107,808 B，SHA `79e0e0c13143f759556d9d85184d8df8fe10e4439a9cfcc331ce90bbffb47eb6`。公开1M输出SHA `4be11c91fcb011d6ef081f81f94c1e70d1286be07a6204bf9bc56a333f9656c4`，holdout为`e8c587c4b3e94c8f65367a9ffb1b5a54458efb29b0a4659c8801eb6b3ca49983`。完整公开输出契约、线程1、RSS794,976,256 B、wall18.35秒通过；单次CPU19.98秒作为构建复核记录。

静态最终包为68,201,104 B，SHA `aed8b929957a14cd5a2ae73bf94fedfd0cfaa86732ff79a7ee08a9e7afca064c`，与exp130已验收候选相同。全部模型、查询源码、架构和恢复头身份核对通过，复用exp130完整表、异常frame、10对组件及三个完整1M共24次运行证据。容量较exp120减少31,551,488 B，余31,798,896 B。预测保持，精度增益0；unique完整1M的CPU区间仍跨零，容量与恢复组件收益采用原预登记判据。

新不可变版本`exp131-zstd-depth10-62dcc48`按固定顺序归档后刷新latest及评测指针，zip SHA `d66e4778e4804dda65339317fa0f2b74d067382015e2a7e3301abb66db49369c`。自包含、clean-room、公开1M及holdout的`--verify`通过；包内、归档二进制、latest、暂存、根入口与`build/submission/estimate`完整SHA一致。重复label退出1，版本元数据、全部指针、生产生成清单及exp120历史包保持身份。元数据dirty=true记录了构建时已有未跟踪内容；正式源码差异全部属于已提交`62dcc48`。

```sh
VERSION_LABEL=exp131-zstd-depth10-62dcc48 ALGO_VERSION=exp131-zstd-depth10 sh scripts/build_submission.sh --verify
PYTHONDONTWRITEBYTECODE=1 build/venv-ml/bin/python validation/exp131_release_check.py --package exp131-zstd-depth10-62dcc48
python3 tests/exp131_packer.py build/exp131/pack-check
```

原始身份与结果见`exp131-generator-check.json`、`exp131-ordinary-check.json`、`exp131-package-check.json`、`exp131-packer-identity-check.json`。重复label命令用于拒绝检查；重建该源码须使用新label。

## 审查与边界

直接pi的`magpie/opencode-go/deepseek-v4.1-flash`、max只读审查完成，原文`exp131-pi-review.md`。Herdr环境快照来自启动时，`fallback_status=started`保留其时间含义；受管pane调用仍待环境。

| 建议或主张 | 核对与处理 |
| --- | --- |
| frame必须与exp129相同才能复用证据 | 正式与私有frame及最终ELF完整SHA均核对通过，写入证据；生成器继续按当前输入做完整无损核验 |
| 助手自检缺少被测身份 | 重新运行原测试，把助手二进制、源码、测试脚本身份绑定到新报告并核对生成清单 |
| 普通构建与包尚待验 | 审查读取时属实；以本节完成报告更新状态 |
| dy场Zstandard可能装入31.8MB | 保留为后续容量假设；源子集竞争、平移误差与新请求泛化分别验收 |

平台1B、隐藏集及新架构成绩尚未验证。局部完整1M与部署等价结论限冻结架构、参数和输入；后续数据或代码改变时重新核对受影响路径。

## 空间与维护

按完整SHA核对三项私有重复产物，保留生产frame/object及不可变包，删除`build/exp131/generated/residue.zstd`、`residue.o`和`build/exp131/estimate-static`，释放184,236,664 B。路径与重建命令见`exp131-cleanup-plan.json`，执行证据见`exp131-cleanup.json`；收尾`/dev/sdd`可用496,650,973,184 B，约463G。旧`build/embedded-residue/residue.zlib`仍被实验120/130脚本按名引用，继续保留。审查提出该文件已无引用，经检索确认仍有两处脚本消费者。

保留开工时已有的`blobs/`、`pelican-bike.html`、`study-xgboost/`和`subm/比赛平台结果/`。本轮代码、发布物和证据定向提交，正式基线分支随后固定在验收提交；新的容量研究使用单独实验分支。
