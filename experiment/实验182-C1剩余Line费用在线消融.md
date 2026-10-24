# 实验182 剩余Line费用在线消融

2026-10-10，分支`research/exp182-line-cost-query`，开工可用449G。
参考固定exp180 block4 ELF，83,774,096 B，SHA `1b13f30a…`，
与exp175最终预测及三种完整1M输出相等。正式exp131保持。

## 假设与候选

固定parent真实重放的Gap费至少为端点Line伪度量，当前块费用guard与
名义恢复后的guard可以先加中间源S至终端前驱E的必付Line。
沿重放从当前实际R到E，已付Gap加剩余Line形成单调下界。
终端Gap覆盖E到最终目标，保持与中间Line费用各自计费。
独立证明在Obsidian《真实重放的剩余Line费用证书》。

四项line4、remain4、combo_line4、combo_remain4固定：
line4只增加恢复前与恢复后的端点Line guard；
remain4再用每hop已付Gap+剩余Line guard；
两个combo额外复用已核对的terminalGap，沿用exp176。
全部原parent、模型、校准、cache、顺序保持。只修改private upper_tree.h，
引用已冻结40源parent和block4 frame，不重新选择数据或重求标签。

## 检查与主门

四静态ELF<100MB，完整块流40源SHA与EOF，12,352条direct/text/cache，
6176条固定exp174查询及全部timed循环相等。
额外debug-only探针逐请求核对candidate恢复路径数、parent步数、
重放resolver数≤reference；正常query计时无计数器。
remain项每hop核对已付Gap+剩余Line下界单调，合法完整路径的最后下界≤真实费。

四项CPU3串行各10对、每带50遍、两轮预热，pair内交错，候选跨pair轮转，
固定exp174七带population。复用exp180配对驱动与普通/同时95%统计。
主组件门为点省≥10%且Bonferroni同时95%差区间上端<0，
四项各df9 t=3.1109348231794756。
全项测完后在通过者中选candidate query均值最低项；无通过者保留旧精度。
门通过后另建完整1M与正式综合验收，当前没有平台收益结论。

runner、checker与协议先提交，构建/输入身份freeze并提交后运行。
原始结果和失败现场保留，冻结协议不追加结果。下一Astra询问exp184后。
