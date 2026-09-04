# 任务 03 — 定义 Task 文档与 Prompt 协议

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02 Go ｜ 被依赖：任务 04 ｜ 当前状态：`待执行`

## 一句话目标

建立一个同时适合人阅读和程序解析的 Task Markdown 协议，固定权威元数据、完整子 Agent Prompt、统一返回 schema 与状态镜像规则，使后续弱调度 Agent 不需要重新设计任务。

## 当前证据（2026-09-03）

- spec-013 的 Task 已具备目标、思维链、分派、监控、验收和结果，但早期文件与后期文件章节不完全统一。
- spec-014/015 已采用“一任务一文件”，但大多只写“Prompt 要点”，不能保证可原样分派。
- spec、README、Task 顶部都保存状态，当前需要人工同步。
- 项目还没有 Task schema 版本、稳定 ID、allowed paths、Prompt hash 或结果 JSON schema。
- 本 Task 是协议与模板任务，不实现 SQLite 或 CLI。

## 前置门禁

1. Task 02 明确 Go，且强制约束已回填。
2. 读取 spec-013/014/015 各一个完成、部分完成和待执行 Task 样本，不能只根据模板设计。
3. 协议必须兼容系统 Python 3.9 标准库；机器元数据使用有明确边界的 JSON，不引入 YAML/TOML 依赖。
4. 任何新状态必须说明谁写、何时写、如何恢复；禁止再引入多个权威状态源。

## 思维链

### A. 固定 Task Markdown 结构

1. 定义顶部双向链接、依赖、被依赖和人类可读状态行。
2. 在标题后加入 `sdd-task-meta` JSON 块，固定 schema v1 与字段校验。
3. 正文统一为：目标、当前证据、前置门禁、思维链、分派 Prompt、返回后处理、监控、验收、风险回滚、产出、执行结果、变更日志。
4. “思维链”定义为规划 Agent 预写的执行阶段与决策依据，不采集模型隐藏内部推理。

### B. 固定 Prompt 与返回协议

5. Prompt 必须写在 Task 文件内，只允许 `RUN_ID/WORKTREE/BASE_COMMIT` 等白名单占位符。
6. Prompt 必须包含角色、最小读取集、allowed paths、禁止项、完成状态、验证命令、结果路径和完整回传字段。
7. 定义 `sdd-run-result/v1` JSON schema，区分必填值、可空指标和敏感字段禁入规则。
8. Prompt 或协议变化必须递增版本并改变 hash；运行中的 hash 漂移必须停止 finalize。

### C. 固定状态与镜像

9. Task 元数据 `status` 是唯一权威持久状态；spec/README 表格仅是生成镜像。
10. `claimed/running/failed/abandoned` 只存在于运行账本，不写成新的持久 Task 状态。
11. 定义 legacy `migration_unverified` 为迁移标记而非可执行状态；未对账时永远不可领取。
12. 更新现有 SDD 模板、门禁与 AGENTS 说明，但不迁移旧 Task；旧任务迁移留给 Task 08。

## 子代理分派计划

### 分派 1：`tech-lead` — 协议设计复核与精确草案

**完整 Prompt：**

```text
你是 spec-016 Task 03 的 tech-lead。请基于真实旧 Task 设计可机器解析且适合人阅读的 Task 文档协议；本轮只产出精确草案，不修改业务代码。

只读取：
1. docs/sdd/specs/016-portable-task-ledger.md
2. docs/sdd/plans/016/task-03-task-document-contract.md
3. docs/sdd/00-sdd-spec-template.md
4. docs/sdd/SDD-GATE-CHECKLIST.md
5. AGENTS.md 中 SDD/子代理/状态/Git 段
6. docs/sdd/plans/013/task-02-deploy-langfuse.md
7. docs/sdd/plans/013/task-04-ollama-direct.md
8. docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md

允许产出：
- .sdd/runtime/runs/{{RUN_ID}}/task-protocol-draft.md
- .sdd/runtime/runs/{{RUN_ID}}/result.json

禁止直接修改仓库 tracked 文件、业务代码、旧 Task 状态或 Git 历史。

草案必须给出：
1. sdd-task-meta JSON 的完整字段、类型、枚举、默认值和示例。
2. Task Markdown 的固定章节顺序。
3. 完整 Prompt 的必备段落与允许占位符。
4. sdd-run-result/v1 的完整字段定义与示例。
5. Task 持久状态、run 状态、迁移标记及合法迁移图。
6. spec/README 镜像生成和不一致时的失败规则。
7. 对 00-sdd-spec-template、SDD-GATE-CHECKLIST、AGENTS.md 的精确修改建议。
8. 密钥、Cookie、Token、Authorization、绝对个人路径和原始完整命令输出的脱敏规则。

设计约束：机器元数据用 JSON；Task Markdown 是长期事实源；SQLite 是可重建索引；弱调度器不得补全缺失字段；不保存隐藏内部思维链。

result.json 使用 sdd-run-result/v1，至少包含 outcome、summary、artifacts、decisions、risks、blockers、main_agent_actions、started_at、ended_at、duration_ms、model、token_usage、tool_call_count、log_paths。不可得指标写 null。
```

## 子代理返回后主 Agent 必须执行

1. 逐字段核对草案与 spec-016，不接受新增范围或含糊枚举。
2. 将协议正式落盘为 `docs/sdd/TASK-PROTOCOL.md`。
3. 分两批更新文档：`00-sdd-spec-template.md` + `SDD-GATE-CHECKLIST.md`；`AGENTS.md` + 本 Task 执行结果。纯文档可由架构师落盘，但必须读回验证。
4. 用至少三个 fixture 手工验证：合法 Task、缺 Prompt、依赖环；结果必须明确。
5. 确认未迁移 spec-013～015 的真实状态；Task 08 前只允许 legacy parser 读取，不允许自动执行。

## 实时监控命令

```bash
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
sed -n '1,260p' .sdd/runtime/runs/<run-id>/task-protocol-draft.md
git diff -- docs/sdd/TASK-PROTOCOL.md docs/sdd/00-sdd-spec-template.md docs/sdd/SDD-GATE-CHECKLIST.md AGENTS.md
```

## 测试与验收标准

- Task schema v1 字段、枚举、迁移与 JSON 示例完整且无歧义。
- Task 正文可直接复制 Prompt 分派，不需要弱调度器补写。
- 返回协议覆盖改动文件、测试、产物、决策、风险、主 Agent 待办、耗时和可空指标。
- 状态唯一事实源和镜像生成规则明确。
- 模板、门禁、AGENTS 与协议文档互相链接，路径真实。
- 旧 Task 尚未迁移时被明确标为不可自动领取。

## 风险、停止条件与回滚

- 字段只存在于自由文本、无法稳定解析：退回协议设计。
- 同一状态需要多个文件手工维护：退回并改成单一权威源。
- Task Prompt 仍含“自行判断/自行完善”等开放决策：不得通过。
- 回滚只需停止使用新模板；不得改写既有历史 Task。

## 产出物

- `docs/sdd/TASK-PROTOCOL.md`。
- 更新后的 spec 模板、Gate 清单和 AGENTS 流程约束。
- 合法/非法 Task fixture 的验证证据。
- 本文件执行结果与变更日志。

## 执行结果

> 待 Task 02 Go、spec 确认并执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 03，状态置待执行 |

