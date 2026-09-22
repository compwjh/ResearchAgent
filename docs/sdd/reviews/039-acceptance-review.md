# Spec039 验收评审

## 结论

**BLOCKED（不通过）**。当前证据不满足 `READY_FOR_USER`，不允许交给用户开始人工验收，也不允许把 Spec039 标记为 `已完成`。

## 真实 API E2E 证据复核

证据来源：`artifacts/spec032-api-e2e-success.md`。

| 运行 | 真实结果 | 验收判断 |
|---|---|---|
| A：自然语言 Intake | `POST /api/conversations/messages` HTTP 200；SSE `done.status=completed`；`missing=[]`；生成计划 `plan_pending_approval` | **PASS（局部）**：证明自然语言入口能完成 Intake，但不证明后续研究完成。 |
| B：批准计划 | HTTP 200、approval `approved`；初次读取为 `running/queued`，随后最终 `completed`，5 个 WorkItem 全部完成，约 149 秒；Artifact 仍缺少标题、摘要、关键词、研究方法和安全问题比较 | **PARTIAL（状态通过、产物阻塞）**：审批和执行成功不等于报告质量合格。 |
| C：历史完成任务复核 | 查询 HTTP 200、任务 `completed`、Artifact 存在；但 Markdown 缺少标题、摘要、关键词、研究方法和安全问题比较 | **FAIL（产物质量阻塞）**：状态完成和文件存在不能替代用户可读报告。 |

因此，当前已有一条“自然语言主入口 → 状态机收敛 → Artifact 存在”的真实案例，但仍没有“合格报告产物”。状态通过与内容质量失败必须保持为独立事实，不能互相抵销。

## 十项准备度复核

按 `artifacts/spec032-readiness-matrix.md` 的真实证据，当前为 **6/10（60%）**；这低于 Skill 要求的至少 9/10，且关键产物质量失败会直接触发 `BLOCKED`。

| # | 检查项 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 服务启动并可访问 | PASS | `/api/health`、`/api/ready` HTTP 200。 |
| 2 | 真实 API 创建入口成功 | PASS | 运行 A 创建会话和 Intake。 |
| 3 | 主路径参数正确解析 | PASS | 运行 A `missing=[]`，主题/目标/时间范围被确认。 |
| 4 | 任务状态从初始态推进 | PASS | 运行 B 最终 `completed`，5 个 WorkItem 全部完成。 |
| 5 | 前端处理中提示可见 | **FAIL** | 没有完整、可复核的 Worker 进度证据。 |
| 6 | 用户知道何时点击/等待 | PASS（文档层） | 人工案例写了等待和下一步，但不能弥补运行阻塞。 |
| 7 | 核心业务产物真实生成且合格 | **FAIL** | 运行 B Artifact 存在，但内容为目录证据 ID 占位元数据。 |
| 8 | 失败状态有可操作恢复 | **FAIL** | 未完成真实登录/重试/重连闭环。 |
| 9 | 页面状态与 API 状态一致 | **FAIL** | API 已完成，但本轮未完成真实浏览器投影复核。 |
| 10 | 步骤文档可由无上下文用户复现 | PASS（文档层） | 案例包含入口、输入、等待、下一步和恢复段落；当前实例仍明确标为 BLOCKED。 |

## 人工验收案例复核

`artifacts/spec032-manual-acceptance.md` 明确写着“`BLOCKED，不要按此版本开始人工验收`”，并正确把运行 B 的报告质量失败写入“当前版本的实际结果”。案例的核心路径结构基本齐全，但它是阻塞态案例，不是可交付的成功案例：

- 审批后的等待阶段最终有真实完成证据，但需在人工案例中明确约 149 秒等待；
- “或同义状态”“或首页聊天输入框”等文案仍不是已验证的唯一 UI 控件/提示；
- 成功标准要求至少 5 篇可读论文和可比较报告，但运行 B 的 Artifact 未满足。

## 可复核检查命令

以下命令均实际退出码为 `0`：

```bash
# 证据文件存在性
for f in artifacts/spec032-api-e2e-success.md artifacts/spec032-manual-acceptance.md \
  artifacts/spec032-readiness-matrix.md; do test -f "$f" || exit 1; done
# 退出码：0

# 运行 B/C 产物不足和 6/10 阻塞证据
rg -n '运行 B|WorkItem|queued|运行 C|completed|缺少标题|缺少标题/摘要/关键词/方法比较|6/10|BLOCKED' \
  artifacts/spec032-api-e2e-success.md artifacts/spec032-readiness-matrix.md \
  artifacts/spec032-manual-acceptance.md
# 退出码：0

# Skill 的最终裁决、自然语言主路径和准备度门槛
rg -q 'READY_FOR_USER' .agents/skills/spec-acceptance-protocol/SKILL.md
rg -q '自然语言 Intake' .agents/skills/spec-acceptance-protocol/SKILL.md
rg -q 'PASS >= 9/10' .agents/skills/spec-acceptance-protocol/SKILL.md
# 退出码：0
```

## 是否允许交付

**不允许交付。** 需要在当前部署版本生成新的、不可覆盖原证据的运行 ID，修复并证明报告包含标题、摘要、关键词（缺失时明确标注）、研究方法/安全问题比较及可追溯引用；随后补做真实浏览器投影与恢复路径，十项准备度达到至少 9/10 且无 P0/P1，才能重新申请人工验收。

## Run D/E 复评（2026-09-20）

以上旧结论保留运行 A–C 的真实失败证据；以下为修复后的当前裁决：

- 运行 D 已通过自然语言 Intake → 审批 → 任务执行 → 报告生成，终态 `completed`，选集 5 篇；Markdown/HTML/引用清单均已落库。报告包含每篇标题、摘要、关键词字段、来源、年份和官方 URL。
- CUA 浏览器复核运行 D 会话，页面直接投影“深度研究报告”、5 篇论文和“研究已完成 · 报告 v1”通知。
- 运行 E 在批准后立即展开“处理过程”，真实看到 task、Worker Agent、Skill、Tool 的分阶段 `进行中/已完成` 和耗时，证明处理中提示不是静态 `Queued · 0%`。
- 真实 `recover` 请求返回 `recovery_required`，同时给出 `queued/completed/leases/reservations/checkpoint` 状态；中断任务不会被静默重放。
- 新增引用归属校正后，针对性测试为 `81 passed, 5 subtests passed`。未知或歧义证据仍硬失败。

### 当前裁决

**READY_FOR_USER（准备人工验收）**。最新准备度为 10/10，无 P0/P1；用户应使用 `artifacts/spec032-manual-acceptance.md` 的运行 D 核心案例验收内容，运行 E 仅用于核对处理中状态。Spec039 尚未标记为 `已完成`：用户验收通过后仍需按收口规则执行全量回归、部署复核和状态台账更新。

### 后续边界修复（2026-09-20）

已补齐评估器并行数组/批量引用展开、搜索 Worker 模型格式失败的既有目录只读恢复、长摘要安全上限，以及合成器失败时的固定渲染回退。定向测试 `85 passed, 5 subtests passed`；任务 `36385d917db1559794a4529728ce6981` 的报告 API 已返回 HTTP 200。该任务 coverage Worker 仍为 partial，故保留为修复证据，不把它冒充 Spec039 收口；人工验收核心仍使用运行 D。
