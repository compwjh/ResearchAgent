# Task02 入口覆盖与可行性

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [任务索引](README.md)

依赖：Task01。当前状态：已完成（技术盘点部分；Spec050 仍 `待确认`，Gate 2 评审未执行，见下方状态边界）。

## 目标、数据与接口

盘点工具分发、下载/导入、研究异步及重试入口；落盘授权与事件契约、M3 Max 加载冒烟、可用数据及许可；为第一交付和第二交付分别给出阻塞项。

## 分派与边界

角色：architect / backend-dev / tester。模型与预算引用 Spec 执行配置和当次用户指派。只读取本任务契约、相关路径及直接依赖产物。涉及前后端分别分派。改动及交接结果需读回核对。

## 验收与回滚

覆盖矩阵逐入口可追溯；第一交付独立 Go/No-Go；训练或公开数据阻塞只影响第二交付。

发现缺陷先定向修复。发现超范围需求退回 Spec 评审。候选验证失败时维持既有可用版本与硬安全约束，记录具体阻塞。

## 产物、结果与变更

执行日期 2026-11-14，分支 `codex/spec050-piguard-integration`。全部产物位于 `docs/sdd/plans/050/runs/task-02/`。

| 产物 | 内容 |
|---|---|
| [入口覆盖矩阵](runs/task-02/entry-coverage-matrix.md) | 20 个入口逐条给出文件行号与覆盖/跳过/禁止判定；5 个 Scope 场景逐项核对 |
| [授权与事件契约（盘点草案）](runs/task-02/authorization-and-event-contract.md) | 现有可复用资产、单动作授权状态机候选、`guard-event-v1` 候选字段、Task03 三个挂接点 |
| [M3 Max 加载冒烟](runs/task-02/m3max-load-smoke.md) | 真实命令、退出码、分阶段耗时、峰值内存与 swap |
| [m3max-load-smoke.json](runs/task-02/m3max-load-smoke.json) / [stderr](runs/task-02/m3max-load-smoke.stderr.txt) | 原始输出与告警 |
| [可用数据与许可盘点](runs/task-02/data-and-license-inventory.md) | MIT 许可、数据指纹、PINT 口径冲突、许可缺口 |
| [两次交付 Go/No-Go](runs/task-02/go-no-go.md) | 第一交付建议 Go；第二交付 No-Go 与 B01–B13 阻塞项 |

**验证命令与结果**：

- 加载冒烟：`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python /tmp/piguard_load_smoke.py` → `EXIT=0`、`conclusion=PASS`、`2.95s`、200 参数严格匹配（`missing/unexpected` 均空）、RSS 峰值 `2009.5MB`、swap 增量 `0`。
- 权重哈希前置校验：`3f284d8e2655ba9714ab2ab449645aa82f4953a1c7ec20cf62402dfb81af35ea`，与 Spec050 一致。
- 产物链接校验：5 份 Markdown 全部相对链接 `BROKEN=0`。
- 静态检查：`.venv/bin/ruff check . --no-cache` → `Found 185 errors`，与本分支基线一致（本任务未新增任何 `.py` 到仓库）。
- `git diff --check` → `EXIT=0`；占位符与冲突标记 0 命中。

**实测结论**：覆盖矩阵逐入口可追溯 ✅；第一交付独立 Go（技术前提成立，不依赖训练/公开数据）✅；训练与公开数据阻塞全部归入第二交付 ✅。`guard-event-v1`、单动作授权端点在本分支 ABSENT，属 Task03/04 交付。

**发现并原样记录的差异（交负责人裁决，未自行修复）**：

1. 验证集 144 条含 48 条 PINT 派生样本，而 Spec050 要求 PINT 无授权记 N/A；`111/144` 是否需要按 96 条子集另报。
2. `logs/model-weight-sha256.txt` 指向基础模型权重哈希，非候选权重哈希。
3. `formal-v1.log` 有两次 `started_at`（首次启动被环境清理，`RUNLOG.md:17` 有说明）。
4. 样本数不在 `config.json`，实际落在 `events.jsonl`/`audit.json`/`preparation-audit.json`。
5. 本机 swap 基线 `15423.81/16384 MB`（94%），双模型常驻与并发队列未实测。

**回滚证据**：本任务未修改任何运行时代码、端点、权重、数据或配置；仅新增 Markdown 与冒烟原始输出。回滚即删除 `runs/task-02/` 目录并还原本文件状态行，无数据或 schema 影响。

**状态边界**：本任务完成的是入口覆盖与可行性技术盘点。Spec050 仍 `待确认`，Gate 2 需求/技术评审未执行，评审记录三行未改；新增确认端点的具体路径、状态码、读写契约与事件水合载体按 Spec050 在 Gate 2 冻结。执行授权边界、检测失败时敏感动作处置、上线阈值、最终评测口径由负责人定稿，本任务不裁决。模型转换、公开评测、运行时接入由 Task08 处理。

## 可先分派：本机复训证据核对

接手条件：检出 `codex/spec050-piguard-integration`，并可读取训练 Mac 上的 `/Users/wjh/piguard-repro`。GitHub 分支仅包含方案和任务文档，模型权重及原始实验记录保存在训练 Mac。若本机目录不可读，记录缺失路径，由负责人提供受控只读副本。

1. 查看 `/Users/wjh/piguard-repro/logs/formal-v1.exit-code` 和 `/Users/wjh/piguard-repro/runs/formal-v1/events.jsonl`。核对退出码 0、最终 `finished` 事件、3 个 epoch 和 7,194 步。
2. 查看 `/Users/wjh/piguard-repro/runs/formal-v1/config.json`、`/Users/wjh/piguard-repro/logs/model-revision.txt` 和 `/Users/wjh/piguard-repro/runs/official-clean/preparation-audit.json`。核对基础模型版本、训练 76,729 条、验证 144 条，以及六条排除记录。
3. 查看 `/Users/wjh/piguard-repro/runs/formal-v1/best_scores.json`，核对最佳验证准确率 111/144。运行 `shasum -a 256 /Users/wjh/piguard-repro/runs/formal-v1/best_model.pth`，与 Spec050 的候选权重哈希比较。此步骤只需读文件，无需加载模型。
4. 在本任务目录新增 `piguard-training-evidence.md`。逐项记录预期值、实测值、证据路径和结论（符合、差异、缺失）。有差异时保留实测值，交负责人裁决。交付仅覆盖证据核对，Task02 的其余契约和可行性验收仍待执行。

这项核对可在 Spec 确认前进行。执行范围限于读取实验文件和撰写核对记录，模型转换、公开评测和运行时接入由后续任务处理。
