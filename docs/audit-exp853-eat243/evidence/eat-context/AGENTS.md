# Project boundaries

This directory coordinates FPGA delay-estimator research with Codex and PySR.
The algorithm project is `/home/lhjysyx/EDA2026`; its frozen exp825
baseline and official release remain under the main operator's ownership.

| Path | Ownership and dependency |
| --- | --- |
| `framework/` | Independent EAT Git; fixed parser, namespace bridge and overlap auditor |
| `candidate/` | Independent algorithm Git; `AGENTS.md` and `eat/task.md` define editable paths and contest rules; `CLAUDE.md` points there |
| `candidate/work_<role>/` | Assigned research copies; designated workers integrate into `src/` and `include/` |
| `candidate/LEARNING.md` | Cross-team hypotheses, measured findings, exclusion boundaries and evidence links |
| `tools/` | Codex dispatch, PySR coordination, isolation/audit, frozen-source upload, scoring, verification and cleanup |
| `pysr/` | Offline trainers, feature contracts, search configurations and compact C++ exports |
| `/home/lhjysyx/EDA2026/pysr_workspace/` | Local PySR environment, frozen jobs, search outputs and checkpoints |
| `results/iteration-NNN/` | Team config, Codex sessions, independent eval, learning snapshots, source differences and per-role artifacts |
| `results/EVOLUTION_HISTORY.md` | Team diagnoses, configurations, decisions and measured score trajectory |
| `results/pipeline/<study>/` | Team configuration/status, exchange, PySR exports, frozen evaluation sources and round review |
| `skills/` | Source of the `eda-eat` Codex plugin, two skills and license files |
| `docs/` | Framework maintenance and coverage records |
| `.agents/plugins/marketplace.json` | Local Codex plugin registration |
| `/home/lhjysyx/EDA2026_EAT_eval_data/` | Large frozen assets and evaluation data outside algorithm Git |

The coordination root has no Git repository. Keep algorithm changes in
`candidate/`; keep `framework/` fixed. The installed plugin carries
instructions and depends on these project-side tools and prepared assets.
Refresh its cache after skill changes using the root README.

## Supervision and execution

Before leading, checking or resuming research, read
`skills/eda-eat-supervisor/SKILL.md` and its `SUPERVISOR.md`. Read
`skills/eda-eat-pysr/SKILL.md` for worker/export contracts.

The current main session owns REFLECT → EVOLVE → LAUNCH → MONITOR. Follow the
Supervisor philosophy: evolve roles and information flow; workers
discover and test algorithm changes. Preserve its plateau mindset.
During research, Supervisor authors TEAM_CONFIG with Reflection/Evolution,
role prompts, phases, read/write ownership and compute allocation. Assign all
solution code, trainers, formula integration and LEARNING.md updates to workers.
The harness records measurements and history. Framework maintenance takes place
between rounds under the user's task scope.
Respect the goal's pause state and `results/PAUSE` separately. Before continuing
after a context handoff, read `results/HANDOFF.md` and refresh the study's status.
Record actual token usage, team size and per-role timeouts; unknown cost stays `null`.

Use `python3 tools/pipeline.py start` for a coordinated team. `TEAM_CONFIG`
contains Supervisor-defined roles. Ordinary tasks use `**Model:** deepseek-v4.1-flash`;
difficult execution uses `**Model:** gpt-6.1-sol-routing`. Both use max reasoning.
One optional `**Model:** agy-gemini-3.8-flash-high` role may provide algorithm ideas,
with high reasoning and plan mode. It must not implement, experiment or publish.
The launcher permits at most one active agy role across studies and rejects a
second within a team. Supply context in the prompt; agy uses no tools.
Choose each role's name, task, prompt, timeout and phase, including PySR
specialists. `--team-size` is the maximum number of roles (default 128).
All roles in a phase run concurrently; phases run sequentially and retain
failure reports for later roles. A prepared `--config` starts a frozen PySR
search concurrently with the team using the root README's remote-first host policy. Supervisor may also launch a
reviewed configuration while the team works. The search is a tool execution
with its own status; each role uses the CLI selected by its model alias.
The Codex aliases resolve to `auto/deepseek-v4.1-flash` and `auto/gpt-6.1-sol`.
agy uses `gemini-3.8-flash-high`. Every role has a maximum 60-minute execution.

Supervisor reviews `work_<role>/pysr-request.json` and `pysr-feedback.json`,
updates `exchange/brief.md`, and starts a new study for changed search hypotheses.
`status` collects and independently verifies completed exports and writes a
combined `TEAM_OUTPUT.md` and `team-status.json` for all roles.
`watch`, `history`, `finish` and `handoff` record monitoring, decisions and context.
`pause/resume` control subsequent starts; `stop` terminates study-owned jobs.
Use `--help` and the README for commands and the team configuration format.

Workers may use `--cleanroom` with explicit `--allow-read` inputs. This isolates
filesystem/network access and removes temporary credentials at exit. Read the
automatic `audit.json` before accepting work. Role ownership within the shared
candidate stays an instruction-level boundary. Evaluator files stay fixed
throughout a comparison; pipeline fixes belong between rounds.

## Evaluation and delivery

Before any complete1B evaluation, apply the 2026-11-03 CPU admission rule in
`/home/lhjysyx/EDA2026/AGENTS.md`, section `1B CPU 前置筛选`.
Matched complete1M/100M evidence must support projected complete1B CPU
at most200s; a projection above200s is `screened_out_cpu` and skips1B.
Missing or stale evidence requires screening first. This supersedes older
direct1B and immediate-positive-candidate instructions below.

Before any prototype or small algorithm experiment, read
`/home/lhjysyx/EDA2026/AGENTS.md`, section
`算法原型与小实验的最小测试规模（2026-11-01 用户更新）`.
Use at least 1,000,000 actual test requests; the full official 1M is allowed.
Report subgroup diagnostics alongside the complete test. This user update
supersedes historical smaller-prototype plans. Preserve the existing >=10M
unique PySR fit requirement and full-1B promotion rules.

Use `python3 candidate/build.py` for an independent build and `pipeline.py evaluate`
for r9 evaluation. It freezes sources before upload so other research can continue.
After all role phases, the harness automatically invokes `eat/eval.sh` or
`eat/eval.py` and accepts its final finite `SCORE` only on successful execution
with unchanged task/evaluator entry files. This is the generic task contract:
project root, `eat/task.md`, and that evaluation entry; `eat/env.sh` is optional.

For this task, `candidate/eat/eval.sh` scores two complete nonrepeating 1B runs
on r9. The competition formula uses mean CPU, mean sampled Acc and actual
two-run output consistency. Sample/100M are optional screening evidence and
have no team score. The 2026-10-30 user instruction permits direct two-run 1B
scoring. `verify` repeats the selected protocol from frozen sources; reuse
unchanged passing evidence before spending that cost. Official delivery retains
the separate five-run consistency check.

The objective is higher Acc and shorter complete-program CPU time. CPU and sampled
Acc come from the same output on unknown, nonrepeating valid requests.
Contest requirements remain a single static,
self-contained ELF <100,000,000 B, one thread, peak RSS ≤2,000,000,000 B and the
fixed `estimate -in INPUT -out OUTPUT` contract. Official promotion follows
the original project's submission rules.

Remote evaluation uses CPU8 and the shared evaluation/cleanup lock
`/home/lhj/lhjwork/eda2026/.eat-evaluation.lock`. Check unrelated machine load
separately. Summaries go to `/home/lhj/lhjwork/eda2026/eat/results/`; disposable
builds go to `/dev/shm/eda2026-eat/<run>/`. Owned predictions and scratch files
are removed after scoring, including failure paths. Preserve requests, necessary
exact labels, reusable assets and small results; inspect unresolved cleanup before
another large run.

For local launches and cleanup, follow the main project's AGENTS.md disk policy:
measure Windows F: FreeSpace as well as WSL free space before large writes and
after cleanup. Budget against the smaller value and record host recovery separately.
