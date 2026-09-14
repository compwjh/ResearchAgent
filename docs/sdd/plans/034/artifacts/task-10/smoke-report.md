# Spec034 Task10 真实 Smoke 与部署记录

日期：2026-09-15（Asia/Shanghai）
分支：`feature/spec-034-conversational-research-runtime`

## 服务与页面

- 使用 `RERANKER_ENABLED=false ./deploy/start.sh` 前台启动，因沙箱监听限制使用提升权限；服务仅绑定 `127.0.0.1:8000`。
- `GET /api/health`：HTTP 200，返回 `status=ok`、`paper_discovery_enabled=true`。
- `GET /`：HTTP 200，页面 53904 bytes；真实浏览器打开 `http://127.0.0.1:8000/#research-view`，可见 Research Tab、会话列表、Intake 表单和任务卡。
- 默认配置的 `OLLAMA_MODEL=qwen3.8:27b` 通过本地健康检查可见，但运行时该模型只声明 completion；未修改项目 `.env` 或局域网 Ollama 配置。

## 固定研究流程

固定输入：

> 帮我做一个深度研究：总结 2020–2024 年 USENIX Security 论文中的软件供应链攻击面与防御方法

流程实际执行：

1. `POST /api/research-sessions` 创建 Intake 会话；返回 `202`、会话标题“深度研究：软件供应链攻击”、`status=intake`、`activation.skill=deep-research-orchestration`。
2. `POST /api/research-sessions/{id}/plans` 写入结构化计划；返回 `202`、`status=plan_pending_approval`。
3. `POST /api/research-sessions/{id}/commands` 使用 `approve_plan`；返回 `200`、`status=queued` 和 `research_task_id`。
4. Task 真实进入 `running`，事件流产生 `research-event:{task}:{seq}`，可见 `phase:plan` → `agent:*:search-usenix` → `skill:*:usenix-catalog-orchestration` 的三级 ProcessingStep。
5. 真实运行最终返回 `status=partial`，终止事件明确记录 `MODEL_UNAVAILABLE` / `AGENT_OUTPUT_INVALID`，没有生成虚假的报告或 Artifact。

两次可复核 Task：

- 默认配置：`7fc66400a3f75df789b62e293aa80ff9`。
- 临时回环 Ollama + 已安装 tools 模型 `qwen3.8:27b-q4_K_M`：`48899b3f0d02549697398c8f1516d13d`。

第二次已确认 `GET /api/health` 返回临时模型名，直接 Ollama `/api/chat` 最小请求 HTTP 200；但同一模型对研究 Tool schema 返回普通文本而非 `tool_calls`/结构化 JSON。Runtime 因无法满足 `ROLE_OUTPUT_FIELDS[search_worker]` 合同，按设计重试后以 `MODEL_UNAVAILABLE → partial` 终止。这是本机模型输出契约不满足，不是服务连通性失败。

## 结论与复验

- 代码链路证据：Intake、计划、批准、唯一 Orchestrator/Runner 启动、三级事件投影、错误/部分终态均真实通过。
- 核心成功 Smoke：**未通过**；缺少 `resolved_model/reasoning_effort` 的成功 Run、真实 Tool 结果及 Markdown/HTML/manifest Artifact。
- 不伪造成功，不将 Spec034 标记为已完成。
- 复验命令（不修改项目配置）：

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_MODEL=<能按 Runtime 契约返回 tool_calls/JSON 的已安装模型> \
RERANKER_ENABLED=false ./deploy/start.sh
```

服务可达且模型能返回符合各角色 `ROLE_OUTPUT_FIELDS` 的结构化结果后，再用同一固定输入复验并补齐报告 Artifact、浏览器审批、刷新恢复和下载证据。

## 2026-09-15 后续复验与契约修复

在上述记录之后，继续使用临时本地 Ollama 模型复验三阶段最小计划，并保留每次真实运行的任务 ID：

| Task | Search Worker | Evaluator | Synthesizer | 结果 |
|---|---|---|---|---|
| `65a8400207955c1d8b5792a2272e8ff1` | 重复目录 Tool 调用，运行超过预算后取消 | 未进入 | 未进入 | 取消；未伪造成功 |
| `f527e27924a65e7696c6e32c3f954bf2` | 完成，1 次目录 Tool，保留候选 ID | 计划仅含 Search Worker，未配置下游 | 未配置 | 作为单阶段链路验证通过 |
| `dd730552c8ae51ceb6322df5a3c686ee` | 完成 | 首轮无效后完成，但 ID 不透明、`keep=false`、无证据 | 未进入 | `NO_VALIDATED_EVIDENCE` |
| `773eb1f92d1153d99c2e45bb08e3691f` | 完成，候选 `462dbdc453dbb373` | 完成，`candidate_id` 合法但 `keep=false`、`evidence_refs=[]` | 未进入 | `NO_VALIDATED_EVIDENCE` |

针对最后一个失败形态已补充最小 Search→Evaluator 证据交接：Orchestrator 现在把 Search Worker 已安全化的目录 Tool 摘要、候选 ID 交集和 `catalog:<id>` 引用作为 bounded `catalog_evidence` 传给 Evaluator；URL、详情 Tool 结果和非候选 ID 不会进入该视图。Evaluator 仍必须基于真实事实返回 `keep=true` 与非空证据引用，Synthesizer 仍不会因空证据而启动。详见 [`smoke-evidence-path.md`](./smoke-evidence-path.md)。

本轮定向集合为 **80 passed，退出码 0**；py_compile、`git diff --check` 通过。由于当前外部 USENIX 来源不可达且本地模型尚未稳定返回满足角色合同的有效证据选择，真实成功 Artifact 仍为 **NO-GO**，Task10 保持 `实施中`，不更新 Spec 状态。

## 受控部署探针（当前提交）

8000、8300、8400 均被已有本机进程占用，未停止用户进程；使用临时端口 18080 启动当前提交，命令为：

```bash
PORT=18080 \
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_MODEL=qwen3.8:27b-q4_K_M \
RERANKER_ENABLED=false ./deploy/start.sh
```

探针结果：`GET /api/health` **HTTP 200 / 334 bytes**，`GET /` **HTTP 200 / 53904 bytes**。健康响应确认服务加载当前模型与论文发现能力；这只是部署可达性证据，不替代真实模型/USENIX 成功 Smoke。

## 2026-09-15 受控真实 Smoke（iHunter 目录样本）

为复核当前提交的真实运行闭环，在提升权限下用临时端口 `18080` 启动服务，未修改项目配置，随后停止服务。该次使用隔离会话和本地真实 Ollama 模型：

- `research_session_id=a561682a29fb43c98f16db71e7e47550`
- `research_task_id=a7012915b1465b60889414155efa3955`
- 模型：`qwen3.8:27b-q4_K_M`，`reasoning_effort=off`
- Intake：首条消息后正确要求缺失 `time_range`；补充 `2024–2024` 后 `missing=[]`。
- 计划：第一次故意包含越权 `scope.topic` 被 `AGENT_OUTPUT_INVALID` 拒绝；修正为受限 scope 后 HTTP 202，计划版本/哈希与审批范围一致。
- 批准：`approve_plan` HTTP 200，创建唯一 ResearchTask；事件流真实产生 `phase:research` → `phase:plan` → `agent` → `skill` → `tool` 三级树。
- USENIX 目录 Tool：真实完成，命中 5 篇候选并返回稳定 `catalog_paper_id`；事件 `research-event:a7012915b1465b60889414155efa3955:6`。
- 详情 Tool：真实来源详情请求失败（`TOOL_EXECUTION_FAILED`），随后相同参数被重复调用时由幂等护栏返回 `TOOL_ALREADY_EXECUTED`；事件 7–16 可复核。
- 终态：用户取消卡住的详情调用后，Session=`cancelled`，ResearchTask=`partial`；未生成 Artifact，符合失败闭环的 fail-closed 语义。

这次复验确认了真实 Intake、计划安全校验、审批、唯一 Runner、USENIX 目录访问、三级事件投影、重复只读 Tool 防护和取消收口；但仍未获得 `keep=true` 的有效评估证据及 Markdown/HTML/manifest Artifact，因此不能把 Spec034 标为已完成。失败原因是当前真实 USENIX 详情来源/本地模型组合无法在时限内产出可验证详情，不是用 Fake Runtime 代替真实成功。
