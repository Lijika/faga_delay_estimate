# exp855 classified-A 错误请求 2M

从 classified-A 的完整 100,000,000 条请求中，筛出 exp855 GPT Pro fast
预测值与所附 exact 标签不同的 37,892,952 条请求，再分层无放回采样
2,000,000 条。全部样本来自 A，保留原始行序。

`errors-2m.csv.gz` 为 43,887,982 B，解压后为 117,075,835 B。
它包含表头和恰好 2,000,000 条数据行。已逐行核对误差条件、分层和配额，
并验证所有有向请求对唯一、gzip 解压前后的完整 SHA-256 一致。
样本覆盖全部 208 种源端口、288 种目标端口、59,904 种角色端口对。

| 字段 | 含义 |
| --- | --- |
| `From`、`To` | A 中原始请求端点 |
| `exact` | 用户提供的 A 集标签，整数 delay |
| `exp855_prediction` | 冻结 exp855 ELF 对同一请求的预测 |
| `a_row_id` | A 中从 1 开始的数据行号，表头不计入 |
| `stratum_id` | 对应 `sampling.json` 中的分层 ID |

## 分析依据

exp855 在完整 A、B 上的 Acc 分别为 98.270103312478% 和
98.270525909850%。Acc 使用连续误差评分
`100 × mean(1 − tanh(4 × abs(prediction−exact)/exact))`；
A、B 的 exact 标签均为正数。

| 曼哈顿距离 | A 请求占比 | A Acc | B Acc | A 总扣分贡献 |
| --- | ---: | ---: | ---: | ---: |
| 0，同 SRB 不同 pin | 7.2074% | 93.168893% | 93.160665% | 28.4610% |
| 1–12 | 23.3831% | 97.287885% | 97.291247% | 36.6598% |
| 13–24 | 8.7446% | 99.056486% | 99.057350% | 4.7695% |
| 25–50 | 13.6195% | 99.030400% | 99.033952% | 7.6337% |
| 51–100 | 12.3833% | 98.749362% | 98.749087% | 8.9526% |
| 101–300 | 22.7159% | 99.216480% | 99.215619% | 10.2887% |
| 301 及以上 | 11.9462% | 99.531576% | 99.532071% | 3.2348% |

A 的低估请求贡献约 93.38% 的扣分；相对误差超过 5% 的请求占
2.604635%，贡献约 59.04% 的扣分。采样同时保留短距离严重误差、
长距离小误差、不同端口族和两种误差方向。

## 采样方法和权重

以距离七组、源端口族六组、目标端口族六组、低估/高估两组、
非零相对误差九组分层。4,536 个可能层中有 3,367 个非空层。

每个非空层先分配一条，其余名额按该层剩余总体数量成比例分配，
用最大余数法处理整数名额，相同余数按层 ID 排序。
层内采用 reservoir sampling，固定种子 `85520261105`；
随机整数使用拒绝取模以避免取模偏差。最终按 A 原行号排序。

`sampling.json` 保存每层的总体数量、采样数量、纳入概率和
`inverse_probability_weight = population_rows / sample_rows`。
这些权重用于还原 **A 中有误差请求的条件分布**。
`representation.json` 对比各维度的原错误总体与采样占比。

样本中有 1,208,641 条低估、791,359 条高估；
338,200 条距离不超过 12，138,183 条相对误差超过 5%。
原错误总体的 Acc 为 95.434779830491%，
样本直接平均为 95.416786381786%，按层权重还原后为 95.434010842737%。
这三个值描述错误请求子集；完整 A 的 Acc 见上方。

## 使用与复现

使用 Python 标准库流式读取，无须完整解压。

```python
import csv
import gzip
import json

with open("sampling.json", encoding="utf-8") as f:
    weights = {
        group["id"]: group["inverse_probability_weight"]
        for group in json.load(f)["strata"]
    }
with gzip.open("errors-2m.csv.gz", "rt", newline="") as f:
    for row in csv.DictReader(f):
        target = int(row["exact"])
        weight = weights[int(row["stratum_id"])]
        # 以 From、To 为模型输入；exact 为标签。
```

有完整 A 标签及同身份 exp855 预测文件时，可以重现采样。

```sh
g++ -std=c++17 -O3 -Wall -Wextra -Werror \
  tools/exp860_sample_errors.cpp -o tools/sample-errors
tools/sample-errors --self-check
tools/sample-errors /path/to/A/exact.csv /path/to/exp855-A.csv \
  100000000 2000000 85520261105 reproduced.csv reproduced-summary.json
```

重现 CSV 的 SHA-256 应为
`c2cdceede2901b4e14d5abe8a104ad1f7886f99b1816a1464bf34ed5c09b7b12`。
`manifest.json` 保存 ELF、完整输入、标签和预测文件的 SHA-256；
`SHA256SUMS` 检查本目录提供的文件。

## 使用范围

A 已参与训练与开发，本数据适合错误分析和继续训练。后续泛化评估需要
另行保留验证数据。原归档没有十类生成场景的逐行标签，本次按可核验的
端点和误差属性分层。标签按用户提供的 exact 使用，求解器完整来源尚未
独立核验。当前统计尚未区分名义模型、量化与物理校正各自的误差贡献。
