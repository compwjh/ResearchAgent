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
