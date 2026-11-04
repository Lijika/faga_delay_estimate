# EDA2026 EAT 工作目录

`framework/` 保持上游 EAT 原样。`candidate/` 是独立 Git 任务仓，初始算法复现
exp825；后续允许替换整个计算架构。`tools/` 保存固定的上传、计时、契约检查与评分工具。
`pysr/` 负责符号搜索配置和 C++ 导出。`results/` 只保留轻量评估摘要和日志。
大型评估数据在相邻目录 `/home/lhjysyx/EDA2026_EAT_eval_data/`，保留在 Git 之外。

当前主会话担任 Supervisor，执行 REFLECT → EVOLVE → LAUNCH → MONITOR。
Supervisor 按 Philosophy 与 plateau Mindset 改进团队和信息协作。
研究期间主会话编写的任务产物为 TEAM_CONFIG，包含诊断、角色演化、提示词、阶段、
读写路径和资源分配。工作角色负责实现、训练器、公式接线及候选接入。
工作角色通过分析、性能测量与实验发现优化。研究方向是 Acc 越高越好、
完整程序 CPU 时间越短越好，同时满足赛题约束。
所有角色都由 Supervisor 在 TEAM_CONFIG 中定义。普通执行使用 Codex DeepSeek，
困难执行使用 Codex Sol routing；最多一个 agy Gemini 角色只提供算法想法。
PySR 专职角色负责符号研究，主会话审核其搜索请求并协调执行。
角色数量和工作阶段按每轮证据决定，默认团队上限为128。

本地独立构建及脚本自检。

```bash
cd ~/EDA2026_EAT
python3 candidate/build.py
python3 tools/self_check.py
```

团队全部阶段结束后，harness 自动调用任务评估入口，在 r9r4900 计分。

```bash
cd ~/EDA2026_EAT/candidate
bash eat/eval.sh
```

完整1B先执行主仓AGENTS.md的2026-11-03 CPU前置筛选。依据完整1M/100M、
分开初始化成本后的1B CPU预计严格大于200秒时，记录`screened_out_cpu`并跳过1B；
缺少同ELF、同硬件的有效证据时先补筛选。此要求优先于旧版直接1B流程。

EAT 主评分使用通过筛选的同一冻结候选的两次完整1B实测，CPU与抽样Acc分别取均值，
两次完整输出SHA相同则一致性分为100，否则为0。综合分使用赛题公式。

```text
time_score = 100 * max(0, 1 - mean_CPU_seconds / 1800)
score = 0.80 * mean_Acc + 0.15 * time_score + 0.05 * consistency_score
```

任一次执行、资源或输出契约失败，整轮评分为0。两次运行共用同一个冻结ELF与输入，
在评估锁内串行执行。完整输出相同可以复用精度计算，各次CPU仍独立测量。
正式交付另验五次一致性。当前Acc来自exact抽样，样本量、加权方式和区间随摘要保存。

显式 `pipeline.py evaluate --tier sample` 是已观察的3,833,856行开发样本，
使用 `1-tanh(4*relative_error)` 及角色端口对总体权重，CPU仅作诊断。
显式100M支持预登记筛选，sample与100M的 `score` 为 `null`，各自保留筛选指标。
100M与1B将完整程序输出写入普通
memfd文件，固定CPU8，检查全部行数、端点、字段和EOF，再从同次输出按冻结位置抽样评分。
100M的10倍CPU外推区间只用于筛选，主评分由两次1B实测产生。

远端只上传候选源码，复用冻结的exp824嵌入资产和exp683/825标签。每轮在
`/dev/shm/eda2026-eat/<run>/` 隔离构建；正式计时前与主操作人确认r9没有哈希/清理负载。
评估器与清理任务共用 `/home/lhj/lhjwork/eda2026/.eat-evaluation.lock`。
摘要和完整输出SHA写入
`/home/lhj/lhjwork/eda2026/eat/results/<run>/`，下载到本地 `results/`。
预测文件在评分结束或异常退出后释放，隔离源码、ELF、对象和抽样CSV随后删除。
远端保留原有请求对、标签、嵌入资产及轻量摘要。
上传或连接异常也会尝试清理本轮唯一目录，状态写入`transport-cleanup.json`。
活动评估持有独立运行锁，继续由远端评估器负责清理；远端连接持续失败时，
本地状态明确记录清理未核验及对应目录。

当前主会话负责 EAT Supervisor 的判断，项目侧角色执行器复用上游配置解析，
按阶段运行工作角色。每轮先写明确的任务配置，再执行有限时长的角色调用。

```bash
cd ~/EDA2026_EAT
python3 tools/pipeline.py roles --team-config results/iteration-002-team.md \
  --iteration 2 --team-size 1 --minutes 12
python3 tools/pipeline.py roles --team-config results/iteration-002-team.md \
  --iteration 2 --team-size 1 --minutes 12 --execute
```

配置模板和角色范围见 `skills/eda-eat-pysr/SKILL.md`、`candidate/eat/task.md`。
配置中的模型别名 `deepseek-v4.1-flash` 由执行器映射为
`auto/deepseek-v4.1-flash`；`gpt-6.1-sol-routing` 映射为
`auto/gpt-6.1-sol`，两者思考强度均为 max。`agy-gemini-3.8-flash-high`
使用 agy 的 `gemini-3.8-flash-high`，强度 high、plan 模式，仅提供研究想法。
每个团队最多一个 agy 角色，执行器用锁保证跨团队同时也最多一个。
agy 从提示词中的材料推导，不调用工具；空回答和权限拒绝记录为失败。
每个角色上限 60 分钟。harness在全部phase结束后运行独立评估，
保存最终 `SCORE`、返回码与任务入口身份；角色自报数值保留在各自报告中。
角色 JSONL 保存用量；CLI 尚未返回费用时记录 `null` 和相应原因。
主仓 `~/EDA2026` 的基准、提交与发布入口由负责人维护。

exp825独立构建与完整100M已通过，二进制和100M输出SHA均与冻结基准一致，
实测CPU15.703823s、抽样Acc98.883090386%、RSS270.2MB。
详细证据与本次验证边界见 `BASELINE.md`。上游框架保持原样；
当前角色执行使用 Codex CLI，PySR 训练按下节的远程优先规则选择隔离环境。

## Codex 插件

本机已安装并启用 `eda-eat@eda2026-local`。插件从 `skills/` 打包，
`skills/eda-eat-pysr/SKILL.md` 与 `skills/eda-eat-supervisor/SKILL.md` 是技能维护源文件。
项目说明使用 `AGENTS.md`，`CLAUDE.md` 指向同一组任务规则。
配置解析沿用上游 `parse_team_config.py`；角色启动、超时处理和结果提取由
`tools/run_roles.py` 调用 `codex exec` 完成。上游 Claude launcher 保留原样。
Supervisor 的详细职责在 `skills/eda-eat-supervisor/SUPERVISOR.md`。
插件包含两个技能和 LICENSE/NOTICE，执行时依赖当前工程的
`tools/`、复用的 `framework/` 组件及研究资产。

通用任务执行器只要求项目根目录、`eat/task.md` 和 `eat/eval.sh` 或 `eat/eval.py`，
可选 `eat/env.sh` 提供任务环境。评估入口成功退出，最后一行给出有限数值
`SCORE: <number>`。执行器把任务规则与本轮角色prompt注入会话，具体机器、
数据与评分方式由任务契约给出。

跨团队认知保存在 `candidate/LEARNING.md`，由本轮指定工作角色维护；
`results/EVOLUTION_HISTORY.md` 保存配置、诊断、独立成绩和决策。
各轮目录保存完整TEAM_CONFIG、角色会话、`official_eval.txt`、
`learning-before.md`、`learning-after.md`、Git已跟踪源码的前后差异，
以及 `artifacts/<role>/` 内的profile和测试证据。

换机器安装时运行以下命令。修改 skill 后，移除并重新安装此插件以刷新缓存。

```bash
codex plugin marketplace add /home/lhjysyx/EDA2026_EAT --json
codex plugin add eda-eat@eda2026-local --json
codex plugin list --marketplace eda2026-local --json
```

刷新缓存使用 `codex plugin remove eda-eat@eda2026-local --json`，
随后再次运行上述 `plugin add`。插件缓存只包含小型 skill 与元数据。
当前会话通过实际读取技能文件使用新指令；新的会话从刷新后的插件发现技能。

## EAT 与 PySR 协同入口

`tools/pipeline.py` 统一调度研究产物与完整程序评估。当前主会话判断方向、分配角色、
审查结果；`roles` 将参数原样交给项目侧 `tools/run_roles.py` 执行 EAT 工作角色。
PySR 接口来自 `pysr/pipeline.json`，现有五分钟 pilot 保持研究身份。

完整团队使用 `start`。Supervisor 根据上一轮报告和测量结果，自行选择角色名称、
数量、职责、提示词、时限与阶段。普通任务使用 `**Model:** deepseek-v4.1-flash`，
困难执行使用 `**Model:** gpt-6.1-sol-routing`。可选的单个想法角色使用
`**Model:** agy-gemini-3.8-flash-high`，其余角色负责实现和核验。默认团队上限为128。
同一 phase 内并行，下一 phase 等前一 phase 结束后开始。

配置格式见 `skills/eda-eat-pysr/team-template.md`。填写本轮 TEAM_CONFIG 后保存到
`results/iteration-NNN-team.md`，明确各角色输入、可写路径和交付证据。
如果已有经审查的搜索配置，可用 `--config` 让 PySR 搜索和团队同时启动；
省略该参数即可先由角色准备数据和配置。主会话在监控过程中通过 `launch`
执行经审查的搜索，其他角色继续独立工作。

```bash
python3 tools/pipeline.py start exp-next \
  --team-config results/iteration-003-team.md \
  --config pysr/surface.json --iteration 3 --team-size 128 --minutes 15 \
  --cleanroom --allow-read /home/lhjysyx/EDA2026_EAT/BASELINE.md
```

默认只预览；研究恢复后使用新 study 和未使用的 iteration，加 `--execute` 启动。
Reflection与Evolution从TEAM_CONFIG读取；同名命令行参数可提供操作人覆盖值。
按任务另加只读资料路径。每角色时限取配置与 `--minutes` 的较小值。
与团队一起启动的 PySR 搜索以 `--minutes` 约束排队、训练与导出总时长，
配置中的搜索时限应留出编译和核验时间。单独 `launch` 使用
`--job-timeout-seconds` 声明总时限。
某个角色失败后，后续 phase 继续运行并可读取失败报告；团队最终状态仍记录失败。
PySR 搜索有自己的状态，持续执行到结束或时限。

```bash
python3 tools/pipeline.py status exp-next
python3 tools/pipeline.py watch exp-next --once
python3 tools/pipeline.py feedback exp-next
python3 tools/pipeline.py history
python3 tools/pipeline.py handoff exp-next --next-action '记录下一步和未决判断'
python3 tools/pipeline.py finish exp-next \
  --decision '记录评估证据、选择结果或尚无可评估候选的原因' \
  --next-action '记录下一轮假设'
```

`status` 收集并重新编译完成的公式，写入 `exchange/pysr-export.json`。
同一研究的 `TEAM_OUTPUT.md`、`team-status.json` 汇总全部角色和搜索状态。
主会话审查 `work_<role>/pysr-request.json` 和 `pysr-feedback.json`，
更新 `exchange/brief.md`；改变训练假设时创建新 study。
`finish` 要求团队与已启动的搜索均已结束，并保存复核、演化历史和交接文档。
`pause/resume` 控制后续轮次，现有任务继续到结束或时限；
`stop STUDY` 清理该研究拥有的进程。goal 的暂停状态由主会话另行遵守。

`--cleanroom` 使用 bubblewrap 隔离文件系统和网络，仅开放指定 API origin。
候选与角色日志可写，资料及异步导出只读；结束删除临时凭证与会话目录。
执行后自动生成 `audit.json`，Supervisor 复核来源、网络和评估资料引用。
若具体研究限制来源，可通过 `pipeline.py audit --help` 配置源代码重叠审计。

独立角色及已有 PySR 产物仍可通过以下入口维护。

```bash
cd ~/EDA2026_EAT
python3 tools/pipeline.py self-check
python3 tools/pipeline.py roles --help
python3 tools/pipeline.py launch exp-new-formula --config pysr/pilot.json
python3 tools/pipeline.py poll exp-new-formula
python3 tools/pipeline.py collect exp-new-formula
```

每次 `launch` 先检查 l7claude 的 SSH、Python/Julia 路径和本轮输入，最长等待15秒。
检查通过时优先在远程运行；连接失败或所需文件缺失时，自动使用
`/home/lhjysyx/EDA2026/pysr_workspace`。本地 `.venv`、Julia runtime、depot、
`jobs/<study>/` 和 `runs/<study>/` 均放在该目录，准备好的输入从 `pysr/` 只读引用。
两端都冻结本轮脚本与配置，后台执行有时限的搜索与 C++ 导出检查。
`launch.json` 保存检查证据和执行位置；`poll`、`status`、`collect`、`stop` 沿该位置执行。
已启动的远程任务失联时记录状态未知，继续查询原句柄。新的搜索使用新 study。
本地及远程结果都收集到 `results/pipeline/<study>/export/`，验证后写入该 study 的 exchange。

已审核的私有训练器可以在搜索配置中指定以下三个字段，复用同一个 `launch` 入口。
`trainer_source` 使用本地绝对路径，`trainer` 是冻结任务内的文件名，只接受
`train.py` 或 `train_<name>.py`。`trainer_sha256` 必须匹配 Supervisor 审核过的
脚本内容；启动前及复制到任务目录后均核对身份，复制后使用冻结副本执行。
Supervisor 在新搜索前审核训练目标、划分、停止条件和运行检查；SHA 用于确认内容身份。
共享调度器、评估器和已安装训练器仍在一轮内冻结，角色将新训练器写在自己的工作目录。

```json
{
  "trainer": "train_accuracy.py",
  "trainer_source": "/absolute/role/work/train_accuracy.py",
  "trainer_sha256": "<reviewed SHA-256>"
}
```

私有脚本须在现有 Python/Julia 环境中独立运行，使用 `--config`、`--out` 参数及
配置中的冻结输入，生成现有六个导出文件。它不能依赖未随任务提供的角色目录辅助文件。
私有训练器保持自己的验证合同，不接受 pilot 专用的 `--validation-features`。
现有已安装训练器配置继续按原方式运行。

## SkyDiscover 搜索预算与主机余量

2026-11-03 用户更新：SkyDiscover 单次搜索预算为120轮迭代。每项研究使用一个
campaign、一个连续 Runner；首次调用 `runner.run(iterations=120)`，中断后沿用
同一 campaign 和 checkpoint，只执行剩余轮次。以迭代数作为总预算；模型调用、
单次评估和锁排队分别保留有限超时。每个团队角色的执行上限继续保持60分钟。
历史研究保留其冻结预算，新研究按本节配置。

一般优化使用 `search.type: adaevolve`；已有有效评估证明优化停滞，或涉及复杂的
表示与搜索策略设计时使用 `search.type: evox`。这是用户所称 `algorithm` 在当前
SkyDiscover 配置中的实际字段。调用失败、额度错误和排队属于执行问题，分别计数。
启动前记录问题证据、选择依据、迭代计数规则及恢复方法；seed、候选与meta调用单列。
解生成、guide和meta模型均使用 `auto/gpt-6.1-sol`，思考强度max；EvoX设置
`search.share_llm: true` 并核验实际meta可用状态及策略checkpoint。

搜索主指标为通过200秒CPU前置筛选的同一冻结ELF两次完整非重复1B实测产生的
`combined_score`，采用本文EAT综合分公式。完整1M/100M承担工程检查与CPU预筛选。
超限候选保留测量和成本反馈，使用`screened_out_cpu`状态，综合实测分留空。
保留不同表示及暂时较差候选供探索，
同时记录重复尝试与已排除条件。反复用于选型的1B标为开发数据；正式接入仍按主仓
独立验证、资源检查与打包规则执行。当前启动器与实测状态见 `results/HANDOFF.md`。

Windows F盘日常尽量保留23,000,000,000B可用空间，搜索产物的2GB上限单独
记录。启动前及生成、评估边界查询F盘；查询失败记录unknown，余量不足或
未知时有序停止新增评估。WSL空闲容量不能替代宿主盘查询。所有新增研究文件
和临时文件都放在获准的本地或远程项目目录内，子进程继承项目内TMPDIR。

显式 `--validation-features build/v0-features.csv.gz` 可在冻结后追加样本评价；
新 v1 留到表示形式冻结后由主会话决定打开。`next-pairphase.json` 记录研究提案，
其训练器和稠密数据准备完成后再启动对应搜索。
`train_surface.py` 已部署到 `pysr/`，保持 signed nominal residual、
`floor(value + 0.5)` 取整和未知 joint 报错。prepare-only 已验证，
完整 surface 搜索仍待研究恢复后执行。

收集已有研究可以选择远端 run 或本地 run。

```bash
python3 tools/pipeline.py collect pilot-review --run runs/pilot-v1
python3 tools/pipeline.py collect pilot-local --local-run ../EDA2026/pysr_workspace/runs/pilot-v1
python3 tools/pipeline.py publish pilot-local --candidate /path/to/candidate-worktree
```

`collect` 仅传输六个导出文件，在临时目录重新编译 C++，核对全部参考整数预测，
验证 manifest/result 的数据和训练身份，保存文件 SHA。checkpoint 保留在实际执行机器的工作目录。
`publish` 复制经过核验的头文件到候选 `include/`；EAT 工作角色随后完成
`Features` 语义接线和相应计算的替换，记录被替换的完整工作。复制头文件这一步
记录为 `research_header_published`。

完整候选使用同一入口评估，示例中的 study 与 worktree 应替换为当前实验。

```bash
python3 tools/pipeline.py evaluate exp-new-model --candidate /path/to/candidate-worktree \
  --tier sample --integration-note 'worker.cpp replaces the complete background prediction path'
python3 tools/pipeline.py evaluate exp-new-model --candidate /path/to/candidate-worktree \
  --tier 100m --purpose research --baseline results/BASELINE-RUN \
  --min-accuracy "$MIN_ACCURACY" --min-score-gain "$MIN_SCORE_GAIN" \
  --timing-margin-s "$TIMING_MARGIN_1B_S" \
  --integration-note 'worker.cpp replaces the complete background prediction path'
python3 tools/pipeline.py evaluate exp-new-model --candidate /path/to/candidate-worktree \
  --tier 1b --integration-note 'unchanged candidate from the eligible 100M run'
python3 tools/pipeline.py feedback exp-new-model
```

每次 `evaluate` 先保存源码快照，上传和计时使用该副本，其他角色可继续研究。
100M 开始前保存源码身份、基准和筛选阈值。示例中的三个变量在本轮结果出现前，
根据已有误差和计时噪声证据预登记。筛选比较相同输入、标签、计分文件、主机、
CPU亲和性和评估器SHA，联合使用同次完整运行的 CPU 与 Acc。
精度采用现有正态抽样区间的保守组合，时间使用预登记余量；此值是1B验证筛选界，
其范围包含现有抽样假设，联合统计显著性仍由主会话结合配对实验判断。
`research` 使用本轮显式预登记的精度阈值，技能与角色提示词保持连续优化目标。

团队评估通过200秒CPU前置筛选后执行两次完整1B，筛选记录随研究保存并绑定当前候选。
100M收益比较使用完整赛题公式的差值，包含时间分在1800秒处归零的边界。
低于阈值的研究公式继续保留在研究阶段。1B结果报告平均完整CPU和平均同次输出抽样Acc，
正式交付、五次一致性、未知集泛化与平台验收仍分别记录。
摘要保存在 `results/pipeline/<study>/`，完整测量证据继续使用现有 `results/<run>/`。
每轮预测和远端构建由固定评估器自动清理；公式、轻量摘要和可重用 checkpoint 保留。

`verify STUDY --tier 1b` 预览冻结候选的独立复核，加 `--execute` 后再执行同一协议的
两次串行r9测量，并核对源码、输入、标签、评估器、二进制与输出身份。
`watch --verify-new-best` 为相同协议的新最佳成绩准备复核；加 `--execute`
才投入实际评估。已有证据身份保持一致时复用，避免重复占用 r9。
