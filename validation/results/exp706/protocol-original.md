# 实验706 直接端口目录阶段接入与完整1B

2026-10-25，exp704完整结果完成前条件登记。exp704的六对100M
配对节省区间下界为正、输出逐字节一致并满足资源限制时执行。

先独立核对全部十四次原始记录、冻结日程、完整输出SHA和配对区间，
复用同输入同输出的exp685全量契约及1,916,928条exact评分。
候选在仅含一个ELF的目录、空环境运行完整100M，静态、容量、
单线程、RSS<=2GB及输出身份通过后接入阶段版。按不可变目录、
latest镜像、submission.zip指针的顺序发布；精度99%仍标未达成。

接着在r9的CPU8串行运行原exp688/A和新候选/C，各一次完整1B。
输入为已核验全端口非重复role-1b，记录输入身份、原始CPU、wall、
RSS、线程数、计数及完整输出SHA。两输出均须与exp688冻结输出
完全相同，方可复用十亿行完整契约及3,833,856条exact评分。
新增标签、模型训练及1M/10M完整程序运行均为0。
单次配对提供规模验证；1B统计显著性继续保持未验身份。
性能计时期间暂停本任务归档，exact与训练串行。

当前候选不改变预测函数，精度保持exp688同输出的98.658061657%。
1B目标继续是<200秒并尽量接近100秒；完整实测结果分别判断。
100M的结果只作扩大依据，1B实测前不填入外推成绩。

## 大输出复用与清理

exp688旧1B原CSV已经开始压缩传往本地保留副本。1B开工前必须确认
本地完整解压SHA、远端原SHA和stat一致，完成归档删除后有42GB空闲。
保留副本为build/retained-outputs/exp688/1b.csv.zst。

本轮两份可重建输出分别为
research/exp706/build/exp706/1b-A.csv和1b-C.csv，每份40,135,645,803B，
预期SHA均为48341077a285b50acbaedd771419849550f141c569020b6eb9d4248a7e1754a9。
逐份完整SHA通过且与已审核的保留副本相同后删除，保存实际删除清单。
重建在research/exp706中分别执行以下命令。

```sh
taskset -c 8 ../exp686/build/exp686/N -in ../../build/hidden-suite-v1/role-1b/requests.csv -out build/exp706/1b-A.csv
taskset -c 8 ../exp704/build/exp704/C -in ../../build/hidden-suite-v1/role-1b/requests.csv -out build/exp706/1b-C.csv
```

有效容量释放和本地/dev/sdd起止空间在收尾补充。
