# Spec032 Task14：自然语言研究 E2E 候选前置记录

## 最终裁决

**BLOCKED — CANDIDATE_UNREVIEWED。**

本轮没有提交新的自然语言 Intake，也没有批准计划、评估候选、下载/导入论文或生成报告。主 agent 在 E2E 写入前通知：backend-dev 的全文恢复生产代码刚落地，当前 8000 服务可能载入尚未独立复审的切片；因此不能把当前 HEAD/进程作为正式验收版本。为避免在未复审运行时上创建业务实体，本轮在只读 readiness/health 前置后停止。

本轮唯一新证据见 [current-research-e2e-candidate-evidence.json](./current-research-e2e-candidate-evidence.json)。旧的自然语言失败报告、Semantic Scholar API 证据均未覆盖：

- [current-research-e2e-report.md](./current-research-e2e-report.md)
- [current-research-e2e-evidence.json](./current-research-e2e-evidence.json)
- [evidence.json](./evidence.json)

## 运行环境与实际前置请求

- `run_id`：`spec032-task14-research-e2e-candidate-unreviewed-20261007T172607Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 观测提交：`005f707`
- 观测进程 session：`8648`
- `/api/ready`：HTTP 200，`ready=true`；`jieba`、`ollama_tags`、`embedding`、`qdrant` 均为 `ready`
- `/api/health`：HTTP 200，`status=ok`、`paper_discovery_enabled=true`，服务默认报告模型 `qwen3.8:27b`
- 目标自然语言请求模型原计划为请求级 `qwen3.5:9b`、`reasoning_effort=off`；本轮未发送，因此不声称模型链路已验证。

## 未发送的自然语言主路径请求

原计划沿用此前失败请求，但使用新的 conversation/run：

> 请进行一次深度研究。主题是USENIX Security 2024中的security/privacy方法，目标是比较至少5篇方法与局限，并且最多选择5篇论文，目标论文数: 5，来源限定为USENIX Security，输出中文Markdown报告并使用行内引用。时间范围是2024-2024。

契约上应从 `POST /api/conversations/messages` 开始，收到计划后先检查 `budget.target_paper_count <= 5`、`plan_version`、`output_hash`，再调用现有 `POST /api/research-sessions/{research_session_id}/commands` 的 `approve_plan`。本轮因未复审运行时暂停，以上请求均为 **not sent**，没有 conversation、session、plan、approval 或 task 实体可记录。

## 状态与产物

| 阶段 | 实际状态 | 证据 |
|---|---|---|
| readiness/health | 完成，HTTP 200 | candidate evidence `ready-01` / `health-01` |
| 自然语言 Intake | 未开始 | `UNREVIEWED_RUNTIME_HOLD` |
| Intake 预算检查 | 未开始 | 无计划实体 |
| 计划 hash/批准 | 未开始 | 未发送命令 |
| 候选评估/自动导入 | 未开始 | 无 task、无下载、无 KB 写入 |
| 非空引用报告 | 未开始 | 无 artifact/report |

本轮没有业务写入、没有读取 `.env` 或 API key、没有修改全局模型/阈值、没有删除或 reindex 文档，也没有下载 PDF。

## 恢复条件

1. 完成当前未复审 backend-dev 生产切片的独立 review；
2. 重启 8000 服务并确认实际提交/进程对应复审后的代码；
3. 用新的 `run_id` 重新提交上述自然语言请求；
4. 只有真实计划预算 `target_paper_count <= 5` 且 `output_hash` 可核对时才批准；随后按 15–30 秒有限轮询记录评估、自动导入、报告和引用产物。

在这些条件满足前，不允许把本轮标为 `READY_FOR_USER`，也不允许把未发送请求、缺失实体或报告路径填成成功值。

## 结论

`BLOCKED`，阻塞码 `UNREVIEWED_RUNTIME_HOLD`。本轮完成到只读服务前置检查，未进入产品主路径；需要独立复审与重启后的新 run 才能继续。
