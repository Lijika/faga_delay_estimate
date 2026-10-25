# exp688 技术审查：配套材料

正文见 report.md；可编辑 Word 与排版 PDF 另行提供。报告以 fed4155 材料及 exp688 冻结源码解释为基础，明确列出读取和验证范围。

code/ 包含独立测试与后续审计脚本。已运行：四种 INT8 内核算术正确性、计数/范围推导、合成投影案例及四行合成 CSV 自测。未运行：仓库真实二进制/CSV 数据重新评分、完整生产程序复现、Xeon 6242R 性能测试。脚本不是已经集成或经过性能验收的优化补丁。

复现合成 CSV 自测：

```sh
python3 code/audit_accuracy.py code/synthetic_accuracy.csv --candidate-column candidate
```

其余命令与边界见 code/README.md。manifest.json 的散列用于核对本交付包内的文件身份，不代表仓库源数据身份认证。
