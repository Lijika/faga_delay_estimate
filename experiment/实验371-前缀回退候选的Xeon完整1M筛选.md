# 实验371 前缀回退候选的Xeon完整1M筛选

2026-10-17，在远端新计时前登记。候选固定exp369，开发反事实、路径和
公开完整1M通过，公开acc99.0799475034%。CPU基准固定exp323发布版，
沿用exp367公开输入和golden身份，每份输入请求对唯一。

远端exp367结束后在核3单线程串行运行。每臂预热20k，随后完整1M按
baseline/candidate、candidate/baseline、baseline/candidate三组交错。
原始time计算完整程序CPU与wall，记录RSS、线程、初始化和cache_hits=0。
逐次检查完整输出契约、端点顺序、SHA及同臂一致性，输出与冻结身份相同
时复用对应golden评分。本轮新增exact与评分CPU为0。

采用原三对t95区间并加入0.02秒舍入误差。CPU差区间上界小于0即保留明确
收益；1%节省作为实际效应参考。区间跨零保留待定，区间全正记录退化。
结合exp370新pin精度决定10M资格；程序报告的enter_10m只表示本公开分布
CPU与已知公开精度过关，新增精度证据另核对。100M等待10M充分优化。

本轮不外推1B综合分。U-output分布、其他架构及平台表现单列。
私有目录build/exp371，证据validation/results/exp371，正式版本保持exp354。
