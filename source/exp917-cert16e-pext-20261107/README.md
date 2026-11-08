# Cert16E PEXT 正式源码

在exp916 G4-Cert16E上合入Xeon端点解析的BMI2 PEXT及相关内联优化。保留分轴费用、下界证书、16字节工作项、G4整型查表、近距提前处理和既有初始化。模型、地图与预测数值保持。
6242R/6226R经过型号及操作系统指令检查后使用专用路径；其它x86-64使用SSE2与原坐标索引操作。
使用r9 Ubuntu22.04/GCC11.4静态构建，无PGO。命令为 `python3 build.py --variant fast --mode source --out-dir build`。
模型、地图或浮点语义变化时须重新验证下界证书。历史manifest.json保留供方原身份。
