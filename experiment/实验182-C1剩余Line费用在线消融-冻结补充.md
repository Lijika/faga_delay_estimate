# 实验182 冻结补充

2026-10-10。首轮构建完成后、任何trace或CPU运行前发现，
combo候选的`DELAY_ESTIMATE_BLOCK_TERMINAL`会同时启用reference中的三个分支。
参考应固定exp180 block4，原构建的combo探针会使用terminal-reuse参考。

保留`build/exp182-attempt1/`及其中`frozen.json`作为未运行的构建现场。
原冻结身份仍记录原路径，迁移后的现场仅用于诊断，不能作为正式运行输入。
首轮四项estimate均为83,774,096 B；其SHA仍见该冻结文件。

runner复制reference时明确把三个宏分支改为`#if 0`，同时核对分支数。
candidate、样本、统计方法、CPU顺序和停止门保持协议不变。
独立checker核对reference中该宏消失且三个分支固定关闭。
重新构建并冻结后才开始运行，原协议与首轮冻结记录保持可追溯。

重建命令为`python3 validation/exp182_line_cost_query.py --stage freeze`，
要求新的`build/exp182/`与`validation/results/exp182-frozen.json`均未存在。
开工磁盘可用448G，当前未清理任何文件。
