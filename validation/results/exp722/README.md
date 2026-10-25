# exp722 证据说明

完整1B、383万条exact评分和独立复算均已通过，见1b-report.json、
1b-decision.json及close-audit.json。1B仅执行候选一次，CPU比较基线
来自历史同输入exp708；100M配对证据由exp720提供。

column-archive-command-help.txt保存工具原始帮助输出，其中含行尾空格。
整批git diff检查因此报告格式告警，保留原字节以维持来源身份。
代码与手写文档的检查另行通过；原始帮助输出的空格不影响运行结果。
提交69b5c623发生在该格式告警之后，本说明补记实际检查范围。
