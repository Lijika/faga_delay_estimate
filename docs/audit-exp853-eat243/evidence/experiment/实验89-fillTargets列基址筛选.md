# 实验89：fillTargets 列基址筛选

## 假设

在 `fillTargets` 中把列的 `zIndex` 和表槽基址移到 residue 循环外，能够减少建表内层循环的重复寻址，同时保持表布局和输出不变。

## 方法与结果

- 基线：`subm/versions/exp87-more-labels-54e0202/bin-estimate`，SHA-256 `2813881c1a22fca79c47752d71784a120e5000fec282d86be94bfa47332bf043`。
- 候选：`build/exp89-estimate-fill-pointer`，SHA-256 `db6f542fc1fd172b672f3a885b5df82a4c20b800b4e7c0926f8488bd876ba9ac`。
- 输入：`build/exp57/timing-1m-unique.csv`，SHA-256 `2cf587f1b27ccc5699040e64ea3efc6eb68c100cfd72a36cad383383a018d7bd`。
- 固定核 3，预热 1 次，随后交错 3 对；每轮核对完整输出、行序、字段、整数和 EOF。
- 两侧每轮输出 SHA-256 均为 `2fabc5f89059bcd15d16735e5579ec7e472a92706ef1e749c01b5209e999ee0d`，1,000,000 行，负值 17,585 行，负值位置 SHA-256 为 `6c9e67fb737c58a52edc1db23a805285bc26118600da3aca8cc1db85c7d242a6`。
- 候选减基线 CPU 差 `[-0.73, +0.12, -0.07] s`，均值 `-0.227 s`，95% 区间 `[-1.335, +0.882] s`；最大 RSS `572,133,376 B`，单线程，最大 wall `27.25 s`。

原始证据：`validation/results/exp89-timing-1m-unique.json`。

## 结论

输出等价成立，CPU 区间跨过 0，未接入正式源码。候选可由固定编译命令重建；本轮未运行 1B。

## 清理

删除前逐一核对 `build/exp89/candidate.csv`、`build/exp89/timing-baseline.csv`、`build/exp89/timing-candidate.csv`，三者大小均 `40,655,222` 字节、SHA-256 均为 `2fabc5f89059bcd15d16735e5579ec7e472a92706ef1e749c01b5209e999ee0d`；按固定计时命令可重建，未被正式命令按名引用。`df -h /dev/sdd` 收尾可用空间约 `484G`。
