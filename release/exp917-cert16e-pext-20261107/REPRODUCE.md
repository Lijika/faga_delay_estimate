# exp917 Cert16E PEXT接入

用r9 Ubuntu22.04/GCC11.4在可写副本中静态重建。

```sh
python3 source/build.py --variant fast --mode source --out-dir rebuild
rebuild/fast/estimate -in request.csv -out result.csv
```

ELF SHA-256 `abea3bf315e8a567d2ced6e0e2e3ff96ac22cab451cfabb68b9a59592c9b4a9f`，大小99,840,088 B。
在exp916上仅接入PEXT端点解析和相关内联，保留Cert16E全部精度与CPU改进。
6242R/6226R通过型号及OS指令检查后使用BMI2提取坐标索引，通用路径继续使用SSE2。
完整A/B200M、五次U-role100M和强制generic输出均保持，完整非重复1B输出也与父版一致。
1B CPU为100.569933秒，同轮父版104.145960秒，A/B200M Acc为99.284029677240%。
1B为单次配对，尚未建立重复计时置信区间；本次按用户指定采用当前已完成的最快候选。
完整输入及输出SHA相同后复用契约与精度证明，每次估计器CPU/wall/RSS/线程重新记录。
全部构建模型/地图、数学计算和分轴生产表身份保持，复用exp916有限域证书。
重新训练、地图或浮点语义改变时须重做证书。无PGO、无新增1M测试。
官方平台、6242R实机与1B全量exact精度仍待验证。
