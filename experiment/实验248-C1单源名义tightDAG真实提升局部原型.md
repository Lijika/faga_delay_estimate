# 实验248 C1 单源名义 tight DAG 真实提升局部原型

2026-10-12。复用 exp210 的 ZSEA[0] C4800 完整名义距离和 parent 证书。
正式入口仍为 exp131，精度参考为已冻结的 exp243 path 模型。

## 预注册

主假设是同余终端键和全部同费前驱各自能补充合法真实路径。固定三臂
parent、shift、tie。parent 只用 terminal 的原名义位移和原 parent；
shift 枚举预算盒内满足实际横位移模14的全部名义终端键，沿原 parent；
tie 对相同终端键递归全部 tight 前驱，以 (nominal_id,actual_x) memo
最小真实前缀费。三臂使用相同 source 本地 Arc 与终端 Net/Arc 枚举。
tie 保存 shift 上界，严格改善才恢复 winner，费用项保持整数。

样本来自已经查看的 `validation/results/exp243-predictions.csv`。
要求 exact>0，source 直接或一条本地 Arc 可到 ZSEA[0]。
每带按 exp243 candidate 的单行损失降序、原 index 升序排列，
选最多4条最高损失和4条最低损失；不足8条全选，结果按带和 index 排序。
预计53条，均为开发集，样本构成固定后写完整身份。

主指标为相对 exp243 upper 新增有限 U 或降低至少16的请求数。
至少3条时继续研究此机制。分别报告 shift-parent、tie-shift 的新增
有限/降低行数、对 exp243 candidate 的安全截断收益、获胜链来源、
访问状态、tight 边、resolver 调用、每请求 CPU/wall、完整性和峰值RSS。
评分仅为此53条局部诊断，报告各带均值及样本均值，整体泛化另需新请求。

tie 每请求固定限额200,000个提升状态、4,000,000次 reverse/forward
resolver 调用、2.0秒 CPU。任一触发即标为不完整，中断未完成终端并
保留已完成合法候选与 shift U；完整子集最小值结论只用于完成请求。
逐请求 CPU 包含终端准备、memo 与 winner 恢复；winner 验证另计。
本地整体原型限时1200秒、地址空间与峰值RSS不超过2,000,000,000 B，
单线程。计时作原型规模筛选，正式性能结论需远程配对测试。

冻结后先运行四跳 witness，分别在 (30,49)/(30,50) 返回256并交换
获胜链。所有有限 U 完整 forward 重放并核对 U>=exact；独立 Python
按五份原始 JSON 再解释 winner 的几何、端口、名义 tight 费用和终点。
完成请求满足 U_tie<=U_shift<=U_parent 的有限集合包含关系。
任何身份、完整性或路径证书失败都先修正实现，再另记修改和新证据。
此前 exp210 的完整 Bellman/parent 证书按 SHA 复用。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp248_lifted_dag.py freeze
# 提交冻结文件后
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp248_lifted_dag.py run
PYTHONDONTWRITEBYTECODE=1 python3 validation/exp248_lifted_dag.py report
```

## 身份与范围

冻结提交 `88fb95e`，冻结记录
`validation/results/exp248-frozen.json`。私有构建目录 `build/exp248/`。
理论见 Obsidian `agent-theory/真实终端反向tightDAG的有界局部查询.md`。
本轮没有改动正式源码或交付包。开工 `/dev/sdd` 可用429 GiB。

首次编译缺少 `<iostream>`，已补齐。失败编译日志和固定样本保留在
`build/exp248-compile-failed/`，当时尚未冻结或运行新实验。

## 结果与归因

`run` 和独立 `report` 均通过。53条请求的三臂全部完成，
四跳 witness 的两位置费用为256/272和272/256，最小费用均为256且
获胜链交换。独立 JSON 解释器核对135条有限 winner、1,750条边，
全部保持真实几何、端口、名义 tight、终点费用与 U>=exact。

| 对照 | 新增有限 U | 已有限 U 降低 | 解释 |
| --- | ---: | ---: | --- |
| shift-parent | 9 | 0 | 收益来自横向同余 terminal 键 |
| tie-shift | 0 | 0 | 此样本全部 tight 前驱保持 shift 的最小 U |
| tie-exp243 upper | 7 | 1条降低87 | 共8条满足新增有限或降低至少16的机制门 |

8条过门请求来自13～24带1条、25～50带4条、51～100带2条、
101～300带1条。其中一条101～300请求取得 U=2564、exact=2554，
exp243预测2378。53条的直接向下截断收益与各带收益均为0。
这里的新增信息价值需要另测双向选择或残差特征。

| 臂 | 查询 CPU 合计 | 中位数 | 最大值 | resolver 调用 |
| --- | ---: | ---: | ---: | ---: |
| parent | 0.006643 s | 0.112 ms | 0.290 ms | 4,919 |
| shift | 0.040732 s | 0.310 ms | 3.402 ms | 167,041 |
| tie | 0.699393 s | 2.643 ms | 91.396 ms | 391,020 |

tie 共访问170,449个提升状态，单请求最多22,021个状态，累计159,317条
名义 tight 边；53条均未触发限额。单线程，峰值RSS384,851,968 B，
加载CPU0.708660 s，整体wall1.521757 s。查询CPU包含终端准备与搜索，
winner证书核验另计。计时只用于本地原型筛选。

## 结论与边界

预注册机制门通过，实际新增上界全部由 shift 单项取得。下一步优先检查
shift 上界的候选质量与双向选择空间，再决定扩大源和映射。
此固定样本上的全 tight 查询单项精度增量为0，扩大工作需另有收益假设。
样本已经查看且按损失选取，只支持局部机制判断；总体accuracy、新请求、
完整1M、其他源/映射、压缩与在线性能仍待验证。

原始证据为 `build/exp248/{console.log,rows.csv,paths.csv,run.json}`，
复核汇总为 `validation/results/exp248-report.json`。冻结日志原文可从
`git show 88fb95e:experiment/实验248-C1单源名义tightDAG真实提升局部原型.md`
恢复。收尾 `/dev/sdd` 仍可用429 GiB，本轮未删除文件，释放量0 B。
