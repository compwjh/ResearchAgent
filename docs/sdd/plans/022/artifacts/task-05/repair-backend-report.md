# Spec022 Task05 修复轮后端实现报告

## 结果状态摘要

**完成（backend-dev 修复轮补丁）**。仅修改后端实现与后端定向测试；未修改前端、Spec/AGENTS、Git 状态，未运行全量回归。

## 改动文件

- `backend/app/memory/models.py`
  - 新增 `MemoryAnalysisJob` 与 `MemoryAnalysisItem` 持久化模型。
- `backend/app/memory/repository.py`
  - schema v5 迁移：稳定 processing step 的 `logical_sequence` 与唯一索引；新增 `memory_analysis_jobs/items` 表、索引、lease token/version 恢复字段。
  - ProcessingStep 同一 `message_id + kind + logical_sequence` 原位更新；终态不可回到 running；增加残留 running 终止和显式 step-id 更新入口。
  - 新增分析任务/结果的创建、claim、checkpoint、分页、幂等项写入与状态决策存储。
  - 新增 lease-CAS 原子 `create_analysis_memory`，旧 worker 不能写入 memory/evidence/item。
- `backend/app/platform/config.py`
  - 新增配置解析 `MEMORY_ANALYSIS_MODEL`，默认值为已核实的小模型 `qwen3.5:9b`；业务逻辑不硬编码模型名。
- `backend/app/chat/application/conversation_service.py`
  - `classify_memory_intent` 调用既有 `run_chat` facade，使用 job 配置模型、`think=False` 和 JSON-only prompt；模型/解析失败降级为 `none`。
  - `MemoryAnalysisWorker` 增加 lease token/version CAS，旧 worker 不能覆盖新 claim 的进度或终态。
  - 新增可重启分析任务：独立于回答 SSE，支持零到多候选、批次 checkpoint、自动保存/待确认/重复/纠正 supersede、项目快照隔离和失败恢复。
- `backend/app/api/schemas.py`
  - 新增单条/批量记忆分析决策请求体。
- `backend/app/api/routes_conversations.py`
  - SSE 不再同步执行当前消息 memory analysis；发送消息时仅持久化并排队分析任务。
  - 增加消息级分析查询、逐条决策和批量决策 API；回答完成/失败/中断时清理残留 running 步骤。
- `tests/test_task05_memory_analysis_repair.py`
  - 新增修复轮定向测试：稳定 step、异步不阻塞、自动保存/待确认/重复、多条分页、项目快照、失败重启恢复、API 决策。
- `tests/test_conversations_api.py`
  - 将过时的同步记忆 SSE 断言调整为异步分析查询断言，并校验中断终态。
- `tests/test_memory_repositories.py`
  - 更新 schema 版本断言至 v5。

## 决策依据

- ProcessingStep 使用 schema 层唯一键和 repository 状态机保证同一逻辑阶段不会产生 running/terminal 两条记录；`done/error/abort` 归一为终态，回答收口时统一清理残留 running。
- 分析 job 是消息级 durable queue，队列线程只负责唤醒；重启时从 pending/running/partial/failed 扫描，SQLite 中的 item 唯一约束和已存在记忆比对保证幂等。
- 项目记忆目标始终使用发送时的 `project_id_snapshot`；会话移动不改变目标，快照项目已不存在时任务失败且不写入新项目。
- 自动保存只针对明确、高置信度候选；模糊/冲突候选待确认；重复返回已有 memory_id；明确纠正创建新版本并 supersede 旧记忆。所有持久化复用现有 `MemoryRepository` 与记忆 evidence 语义。
- 分析结果只提供脱敏 rationale 摘要，不持久化或展示隐藏思维链。
- 分类器仅接受结构化 JSON；不能解析或模型不可用时返回 `none`，不伪造记忆。
- 分类器失败通过 `classification_error` 传递给 worker，job 可见为 `failed` 并保留错误码；合法 JSON `none` 仍正常完成。
- 分析 lease 通过 token+version CAS 绑定当前 claim；schema v4 校验同时检查 processing step 唯一索引，v5 迁移补齐 lease 字段。
- memory 与 analysis item 在同一事务中再次校验 lease，旧 worker 到达写入边界时直接回滚。

## 风险与阻塞

- 未运行全量 pytest、前端检查、部署或浏览器 smoke，按 Task05 backend-dev 范围保留给主 Agent 收口。
- 分类任务使用现有分类入口和配置化模型 seam；若本机分类模型不可用，任务进入 failed，普通回答仍成功，需由上层按既有分析查询展示失败状态。
- 既有历史 schema v1/v3/v4 会在启动时迁移到 v5；旧 repair 轮重复步骤会在迁移时保留终态记录并删除残留 running 重复项。

## 主 Agent 后续动作

1. 阅读本报告及测试报告，交给 backend-reviewer / tester 做修复轮复审与验收汇总。
2. 与 frontend-dev 对齐分析查询返回的 `job`/`analysis`、`items`、`next_cursor` 以及决策状态枚举。
3. Task08 收口时再执行全量回归、部署及运行时 smoke；本轮不标记 Spec 完成。

## 运行信息

- 开始：2026-09-11 11:23:59 CST
- 结束：2026-09-11 12:05:00 CST（补丁轮）
- 总耗时：约 41 分钟（含补丁轮）
- 模型：gpt-5.6-luna high（主 Agent 指定）
- 进展日志：`.codebuddy/agent-logs/spec-022/task-05/backend-dev/20260911-112359.md`
