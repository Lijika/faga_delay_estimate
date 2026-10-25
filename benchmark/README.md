# 机器配置与已有完整运行

目前可提供的性能证据来自 r9。2026-10-25 采集该机器配置，CPU 为 **Intel Xeon Gold 6226R**，1 socket、16 cores、32 logical CPUs、22 MiB L3。用户给定的目标机器是 **6242R**，截图显示 2 sockets、每 socket 20 cores、80 logical CPUs、合计 71.5 MiB L3。目标截图见 [cpu-xeon-gold-6242r.png](cpu-xeon-gold-6242r.png)。

[r9-current-machine.txt](r9-current-machine.txt) 保存 `lscpu`、内核与工具链信息，[machine-provenance.json](machine-provenance.json) 标注采集时间和证据边界。历史运行使用同一 r9 主机，日志没有同时保存完整 lscpu、governor 或即时频率；当前采集用于说明机器身份。现有材料中没有 6242R 的实测成绩。

## 当前 exp728

当前阶段版的生产源码在 `source/`。exp727 在 exp720 新生成的 100M 上完成两次 warmup 和六对交错计时，全部十四次运行见 [exp727-complete-100m.csv](exp727-complete-100m.csv)。A 为 exp725 同算法代码，C 为当前 exp728 的坐标掩码实现。正式平均 CPU 从 18.635379667 秒降至 17.879823333 秒，节省 0.755556333 秒，95% 配对区间为 [0.632248121,0.878864545] 秒。全部完整输出 SHA 相同。

exp728 在非重复全角色域 1B 上 CPU 为 184.190953 秒，其中 user 161.463008 秒、system 22.727945 秒，wall 205.239648 秒、RSS 206,639,104 B、单线程。完整输入输出及标签身份见 [1b-report.json](../validation/results/exp728/1b-report.json)。该 1B 候选只运行一次，重复计时依据来自 100M。五次 1B 平均及 6242R 表现未验。

当前 1B 输出的 3,833,856 条 exact 加权 Acc 为 98.6448996487895%。exp722/725/728 输出 SHA 相同，评分按身份复用；完整逐条预测见 [accuracy](../accuracy/README.md)。清洁目录验收见 [package-check.json](../validation/results/exp728/package-check.json)。本轮材料发布复用了既有运行，没有新增完整 estimate、当前 perf 或硬件专项测试。

## exp703 的历史 100M perf

exp703 使用 exp688 对应的 exp686/N 二进制，输入是 exp685 的完整非重复 100M。三次完整运行的输出 SHA 相同，完整记录见 [report.json](../validation/results/exp703/report.json)。

| 完整运行 | CPU 秒 | wall 秒 | 用途 |
| --- | --- | --- | --- |
| warmup | 23.912229 | 24.019058 | 普通完整运行 |
| perf stat | 24.030878 | 24.342323 | 计数器采集 |
| perf record | 23.981182 | 23.991614 | `cycles:u`，999 Hz 采样 |

原始计数见 [exp703-counters.csv](exp703-counters.csv)。cycles 为 85,594,493,829，instructions 为 148,834,260,723，IPC 约 1.74，branch-misses 为 685,433,271，cache-misses 为 375,966,066。计数器采集进程的 CPU 时间与普通运行分别列出。

[inline-report.json](../validation/results/exp703/inline-report.json) 提供 23,697 个采样点的叶级函数、包含调用关系的函数、文件及行号分解。`inclusive` 中的百分比存在包含关系；同一采样可能出现在多个父级中，分析预算时应按所选层级计算。

原命令保存在 `validation/results/exp703/*.run.json`，工具帮助也在同目录。下面展示当前源码的测量接口。若要复现 exp703，请使用 Git 提交 `fed4155` 中的 exp688 源码及 exp685 输入；当前源码运行会产生 exp728 的新测量。旧 perf 热点占比仅用于历史比较。

```sh
/usr/bin/time -v -o run.time \
  taskset -c 8 source/build/estimate -in requests-100m.csv -out result.csv

perf stat -x, -o counters.csv \
  -e task-clock,cycles,instructions,branches,branch-misses,cache-misses \
  -- taskset -c 8 source/build/estimate -in requests-100m.csv -out stat.csv
```

历史 CPU 统计来自原测量脚本中的进程资源计量，精确复现命令见原 JSON。`time -v` 可独立记录 user、system、wall 和 RSS；比较时应保持同一种计量方式。采样版本另有符号构建，编译参数见 exp703 的 `compile-debug.json` 与 `link-debug.json`。

## exp704 / exp706 的阶段进展

[exp704-complete-100m.csv](exp704-complete-100m.csv) 包含全部 14 次完整 100M 运行，两次 warmup 和六对正式比较，每次均有 CPU、wall、RSS、线程数和输出 SHA。A 为 exp688 对应实现，C 为 688 槽端口直接目录。

正式配对顺序为 AC、CA、AC、CA、AC、CA。A 平均 CPU 23.789769 秒，C 为 23.004201 秒，平均节省 0.785568 秒，95% CI 为 [0.684197, 0.886939] 秒。输出逐字节相同，精度沿用相同输入、标签和输出的原评分。

exp706 的清洁目录、空环境完整 100M CPU 为 24.015962 秒，wall 为 30.489715 秒，峰值 RSS 为 206,372,864 B，单线程。验收见 [package-check.json](../validation/results/exp706/package-check.json)，该端口目录已经进入当前源码，旧补丁入口已移除；exp708 提供接入准备编译后的完整 1B 证据。

exp688 已有完整 1B CPU 243.302538 秒及 3,833,856 条分层 exact 的精度证据，详见 [accuracy](../accuracy/README.md)。exp704/706 的独立阶段身份保留，其改动经 exp708 进入后续 1B 测试。本次只整理既有完整运行证据，并核验工具和数据，没有新增 100M 或 1B 估计程序运行。
