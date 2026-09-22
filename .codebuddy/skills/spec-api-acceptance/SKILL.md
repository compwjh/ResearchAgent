---
name: spec-api-acceptance
description: "Drive the live backend API to produce and persist a real success-case artifact for a spec (or set of specs) that is implemented and needs runtime / manual acceptance. Use when a spec is done and needs runtime verification, when the user asks to 'run a successful example' / '跑一个成功例子' / '保存成功案例' for one or more specs, or when completing the SDD '运行时验证' step."
agent_created: true
---

# Spec API Acceptance — 调用 API 跑通并保存成功案例

SDD 验收闭环的最后一步是「部署 + 运行时验证」。**本 skill 把这一步固化成可复用的 SOP**：
对已经实现（代码就绪、单端测试通过）的 spec，启动真实服务、用 curl 打它的端点、把**真实的**
请求体与响应（含 HTTP 状态码）原样落盘为 `artifacts/spec-*.md`，并回写验收状态。

> 已有范例可参照：`artifacts/spec029-030-031-api-sample.md`（单任务贯通 029/030/031 三端）。
> 本 skill 的坑点清单正是从该范例的真实经验提炼而来。

## When to Use

- 一个 spec 实现完成、单端测试通过，需要「运行时验证」且保存可复核的成功案例。
- 用户说「跑一个成功例子 / 保存成功案例 / 验收一下这个端点」。
- 多个 spec 共享同一条流水线产物时（如 029/030/031 都用同一个 `research_task`），一次贯通、一份产物。

## 核心原则

1. **真实调用，绝不编造**：artifact 里的 curl 与 JSON 必须是从活服务上实际跑出来的，不要凭记忆写、
   不要省略关键字段。探针类 503 也要把降级响应体完整保留。
2. **复用优先，新建兜底**：先确认是否已有合适的 `research_session` / `research_task` 可直接用；
   没有再走「建会话 → 批准计划 → 等流水线完成」新建一个。多 spec 共用一个 task 能省大量时间。
3. **记录坑，而不是只记录 happy path**：422/409/503 的**真实触发条件**、必带字段、枚举取值、
   设计使然的 `partial` 状态——这些比成功响应更值钱，必须写进 artifact 的「调用约束 / 已知限制」。

## 标准流程（6 步）

### Step 0 — 启动并探活服务

```bash
# 后台启动（单进程；Qdrant 本地文件锁不允许多 worker）
./deploy/start.sh -d
# 端口被占用先停：./deploy/stop.sh；或换端口 PORT=8300 ./deploy/start.sh -d

# 探活（二选一）
curl -s http://127.0.0.1:8000/api/kb/health            # 期望 {"qdrant":true,"chunks":N}
curl -s http://127.0.0.1:8000/api/research-routing/status   # 200 或 503(含降级体)
```

> 多进程争抢 Qdrant 本地文件会导致 `qdrant:false / chunks:0` 的**误报**，先 `stop` 再单进程 `start` 即可恢复。

### Step 1 — 准备验证任务（复用或新建）

复用：`research_store` / `routes_research_routing.py` 里已有的 `research_task_id` 直接拿来打端点。
新建（端到端贯通时必须）：

```bash
# 1) 建会话：intake 的 topic/objective/time_range 必须给全，否则 plans/generate 报 INTAKE_INCOMPLETE
curl -s -X POST http://127.0.0.1:8000/api/research-sessions \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"<uuid>","intake":{
        "topic":"...","objective":"...","time_range":{"from":2022,"to":2025},
        "language":"zh","sources":["USENIX Security"],"depth":"standard"}}'

# 2) 批准计划：command 必须带 subject_version 与 idempotency_key
curl -s -X POST "http://127.0.0.1:8000/api/research-sessions/<session_id>/commands" \
  -H 'Content-Type: application/json' \
  -d '{"command":"approve_plan","subject_version":1,"idempotency_key":"ap-<spec>-verify-001"}'
```

流水线（search_catalog → evaluate_papers → check_coverage → synthesize）本地 Ollama 约 4 分钟跑完。
确认 5/5 WorkItem `completed` 再继续。

### Step 2 — 逐端点调用并捕获真实响应

对每个目标 spec 的端点，用 curl 打一遍，**原样保存**：
- 请求行 + 请求体（注意必带字段，见坑点）；
- 响应 HTTP 状态码；
- 响应 JSON 关键字段（不要截断到看不出结构）。

多 spec 共用同一 `research_task` 时，把各端点按 spec 分段记录在同一份 artifact 中。

### Step 3 — 提炼「调用约束 / 已知限制」

把跑出来的 422/409/503 与"设计使然的 partial"写成可读的约束清单：
- 必带字段（如 `plan_version`、证据矩阵的 `claims`/`dimensions`）；
- 枚举取值白名单（成功案例里出现的每个枚举值）；
- 资源冲突（ID 全局唯一、跨任务复用会 503）；
- 设计使然的非 completed 状态（如 catalog 级证据 → 报告 `partial`，属正常）。

### Step 4 — 落盘 artifact

保存到 `artifacts/`，命名：

| 场景 | 文件名 |
|---|---|
| 单 spec | `artifacts/spec-NNN-api-sample.md` |
| 多 spec 合并 | `artifacts/spec-NNN-MMM-api-sample.md` |
| 配套请求体较大 | 同目录放 `artifacts/spec-NNN-<endpoint>-sample.json` 并用 `@` 引用 |

用下面的**模板**填充（直接复制骨架，把真实值填进去）。

### Step 5 — 回写验收状态

- 在 `docs/sdd/spec-status-changelog.md` 加一条：`spec 编号 / 标题 / 变更前后状态 / 时间 / 一两句说明（本次验证结果 + artifact 路径）`。
- 若 spec 文档有「验证方式」段，补充「已实现 / 已用真实 API 验证（见 artifacts/...）」。
- 多 spec 手动验收时，**等用户确认产品可用**后再把状态从 `实施中` 标 `已完成`，不要自作主张收口。

## Artifact 模板（复制到新文件后填真实值）

```markdown
# Spec NNN —— API 成功产物样例

生成时间：YYYY-MM-DD
分支：`<branch>`
服务：`http://127.0.0.1:8000`（`./deploy/start.sh -d`）

**本次验证任务**

| 项 | 值 |
|---|---|
| research_session_id | `<id>` |
| research_task_id | `<id>` |
| 主题 / 目标 | ... |
| WorkItem | 5 / 5 `completed` |
| 任务终态 | `partial`（终止码 ...，详见「已知限制」） |

---

## 前置：跑通一次研究流水线（若复用已有 task 可删此节）
（贴 Step 1 的两条 curl + 说明）

---

## Spec NNN —— <端点一句话说明> `POST /path/{id}/endpoint`

请求（**必须带 `plan_version`**，否则 422）：

\`\`\`bash
curl -s -X POST "http://127.0.0.1:8000/api/.../<id>/endpoint" \
  -H 'Content-Type: application/json' -d '{"plan_version":1}'
\`\`\`

响应 **200**：

\`\`\`json
{ "real": "response", "fields": "kept" }
\`\`\`

> 修复前这里返回 `400 ...`（一句话说明旧行为的根因）。

---

## 本轮修掉的问题 / 已知限制（按优先级）

- **P0 —— ...**：根因 ...；修法 ...；验证 ...。
- **P1 —— ...**：根因 ...；**属内容质量/设计使然，不影响流程贯通**。
```

## 通用坑点清单（每次都过一遍）

- **端点依赖前置实体状态**：多数 `/research-tasks/{id}/*` 端点要求该 task 已存在且选集/报告就绪，
  否则 `REPORT_NOT_READY` / `400`。先确认前置 WorkItem 已完成。
- **422 多因缺字段**：`plan_version`、`claims`、`dimensions`、`subject_version`、`idempotency_key`
  等是高频必带项，缺一个就 422，把报错字段补上即可。
- **枚举要显式列**：成功案例出现的每个枚举值（如 `confidence ∈ {low,medium,high}`、
  `evidence_level ∈ {catalog,abstract,fulltext}`、`relation ∈ {supports,contradicts,contextual,missing}`）
  都写进 artifact，下游复核才有据。
- **ID 全局唯一**：`claim_id` / `evidence_id` / `dimension_id` 跨任务复用会 503，每次验证用新 ID。
- **catalog 级证据 → 报告 `partial` 是设计使然**，不是失败；要 `completed` 需提升 `evidence_level`。
- **503 不是纯失败**：资源探针不可用时 503 仍返回降级状态体，按 spec 如实保留。
- **单进程启动**：`deploy/start.sh` 不要用 `--workers N>1`，否则 Qdrant 本地文件锁损坏。
- **保存真实响应**：artifact 里的 JSON 用真实返回值，不要为"整洁"改写结构。
```
