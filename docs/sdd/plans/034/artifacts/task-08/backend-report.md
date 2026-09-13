# Spec034 Task08 后端交付报告

状态：已按 backend-review P1 修复，待 backend-reviewer/backend-tester 与主 Agent 做收口。

## 结果状态和摘要

- 新增 `backend.app.research.application.report_synthesis`：`ReportSynthesisOutput`、严格安全字段/哈希校验、`ReportSynthesizer` 白名单合成、固定 Markdown→HTML 转换器。输入候选必须显式通过 verified/validated 标记，引用必须存在于 allowlist；不读取会话、Prompt、CoT、凭据、URL 或文件路径。
- 新增 `ReportDeliveryService`：Markdown、HTML、citation manifest 三类 Artifact 按 `(task, report_version, artifact_type)` 插入；同版本重试复用已存在 Artifact；最终助手消息使用 `research-report:{task}:{version}` 的既有 `MemoryRepository.create_activity_message` 幂等键，新版本自然生成新消息；通知独立插入。
- 强化 `ResearchStore`：Artifact content hash 与内容一致性检查；owner 通过 task join 校验单 artifact/list；通知 payload 拒绝敏感字段、URL、超长/非 JSON 对象；保留 Task02 兼容别名。
- 新增 Artifact 列表/下载、owner 通知列表/read/SSE 路由；下载只接受库内 `content`，拒绝 `storage_ref` 路径解引用，并返回固定 Content-Type、Content-Disposition、CSP、nosniff 与 no-store。
- P1 修复：验证标记必须是字面量 `True`；title/heading 与真实模型 synthesis 输入共用 URL/路径/Prompt/凭据边界；AgentWorkItem 消费并校验真实 Synthesizer Run 的 schema/hash/引用白名单，不再重拼替代报告；无 kept/evidence 只收敛为 partial/诊断；Artifact 竞态回读再次比较 hash；通知失败同时留下 failed+partial，重试使用独立幂等键，waiting_approval/interrupted（含 startup recovery）接线；SSE 按 cursor 有界轮询并发送 heartbeat，支持连接期间新通知和断线补发。
- 最新 P1 修复：AgentWorkItem 按 `depends_on_json` 拓扑调度并 fail-closed；Evaluator 只能接受同一上游 Search Worker 的合法 source、candidate、evidence/citation ref 和 `source_refs`，伪造或跨源数据（如 `source=attacker`、`search:attacker`）统一返回 `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`；Synthesizer 只读取自身祖先链上、已完成且语义校验通过的 Evaluator WorkItem，Critic/其他角色输出不会注入；空证据不调用 Synthesizer；Runner 暴露最终 continuation AgentRun ID，Artifact 归因使用最终成功 Run；`source_refs` 必须精确等于 evaluator citation manifest。
- API 下载进一步只开放 markdown/html/citation_manifest 三种报告 Artifact；存储层增加 `report_version >= 1` 校验（保留旧调用兼容的可选 owner 写入参数）。
- 新增 12 项行为断言，覆盖严格布尔、安全输入、真实 synthesis 消费/引用边界、Evaluator 上游 candidate/ref/source 隔离、Artifact 竞态 hash、SSE 游标轮询；原有合同覆盖不可变/owner/幂等/CAS/XSS。

## 改动文件

- `backend/app/research/application/report_synthesis.py`
- `backend/app/research/application/orchestrator.py`
- `backend/app/research/application/agent_runtime.py`
- `backend/app/research/application/planner.py`
- `backend/app/research/domain/contracts.py`
- `backend/app/research/application/entry.py`
- `backend/app/research/infrastructure/research_store.py`
- `backend/app/api/routes_research.py`
- `backend/app/api/routes.py`
- `tests/test_spec034_task08_backend.py`

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py` | 0 | 18 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task05_contract.py tests/test_spec027_runtime_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py` | 0 | 96 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task07_backend.py tests/test_conversations_api.py tests/test_spec027_backend_research_slice.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task06_contract.py` | 0 | 181 passed，5 subtests passed |
| `.venv/bin/python -m py_compile backend/app/research/application/report_synthesis.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/entry.py backend/app/research/infrastructure/research_store.py backend/app/api/routes_research.py backend/app/api/routes.py tests/test_spec034_task08_backend.py` | 0 | 通过 |
| `.venv/bin/ruff check [Task08 改动文件] --select E9,F63,F7,F82,I001 --output-format concise` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## 决策依据

- 复用 Task02 独立 research SQLite 与 `ResearchArtifact`/`ResearchNotification` 表，不复制存储或消息流；Artifact owner 不冗余字段，读取时 join `research_tasks.owner_id`。
- 复用 MemoryRepository 的 activity-message 幂等接缝，不直接写会话库 SQL；跨库按可重放 Saga 处理，Artifact/消息/通知不宣称跨库原子。
- HTML 采用固定、可复现的转义渲染器，不解释原始 HTML、Markdown link 或 image；因此 XSS payload 只能作为文本出现。
- 通知 event_seq 继续由既有 ResearchStore owner 级原子分配，read 继续使用 `status='unread'` CAS；通知事实与 Artifact 生命周期独立。

## 风险与阻塞

- `research-report-synthesis` 磁盘 Skill 位于 `.agents/skills`，属于本轮 backend-dev 禁止修改的范围；主 Agent 负责确认 Skill 文件与运行时 registry。
- AgentWorkItem 的真实模型输出必须带报告 schema/hash、非空 sections/citation_manifest，并且每条引用命中 Task06 evaluator 的字面量验证证据；不满足时返回 stable `AGENT_OUTPUT_INVALID`/`NO_VALIDATED_EVIDENCE`，任务为 partial，且 failed+partial 通知均可重放。真实 Ollama smoke 仍不在本轮范围。
- SSE 是有界（默认 20 polls）连接；客户端应保存最后 `event_seq` 并通过 `after_seq`/`Last-Event-ID` 重连，避免服务端无限占用测试或连接资源。
- 本轮未运行真实 Ollama/外部来源 smoke；未声称真实模型成功。

## 主 Agent 后续动作

1. 确认 `.agents/skills/research-report-synthesis/SKILL.md`（仅领域编排协议）与本实现的 schema/通知键一致。
2. 运行 backend-reviewer/backend-tester，重点复核 AgentWorkItem 真实输出、owner/path isolation、HTML 响应头、artifact immutable conflict、通知 SSE 重连。
3. 与前端对接 session artifact URL 和 notification SSE，完成 Task08 跨端验收后再更新 Task08/Spec034 台账。

## 执行元数据

- 开始：2026-09-13 12:45（Asia/Shanghai）
- 结束：2026-09-13 13:12（Asia/Shanghai）
- 总耗时：约 27 分钟
- 可用模型：当前执行 Agent 自身；主 Agent 指定临时 Luna high
- token 统计：子任务上下文未提供可查询 token 计数
- 工具统计：`apply_patch` 24 次，`exec_command` 16 次，`write_stdin` 4 次；未使用网络或子 Agent；未 commit/push/merge/reset/stash/clean
- 本轮追加工具统计：`apply_patch` 约 20 次，`exec_command` 约 16 次；未使用网络或子 Agent；未 commit/push/merge/reset/stash/clean
- 进展日志：`.codebuddy/agent-logs/spec-034/task-08/backend-dev/20260913-131553.md`
