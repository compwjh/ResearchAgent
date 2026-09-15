# Task11 子任务报告：报告正文丰富化

## 结论

已完成最小安全扩展：Search Worker 的已安全化目录事实可携带 `title`、`abstract`、`keywords`、`summary` 及有限方法/主题字段，随后只附着到已有验证候选；固定 Markdown 渲染器会输出论文标题、摘要（有则输出）、关键词（有则输出），并按 Synthesizer 已批准的主题/方法分组展示。

## 改动

- `backend/app/research/application/agent_runtime.py`
  - 从目录 ToolResult 的摘要或候选映射提取有界元数据。
  - URL 只保留 `[redacted-url]`，Prompt/CoT/凭据等敏感文本沿用严格安全过滤；全文下载/详情 Tool 链未改。
  - 更新 Synthesizer 运行契约，明确元数据只能由固定渲染器消费。
- `backend/app/research/application/orchestrator.py`
  - Search→Evaluator 交接保留与候选 ID 绑定的安全目录元数据。
  - Evaluator 的 `keep=True` 结果才可成为 `validated_candidates`；元数据不从模型输出复制。
  - 证据摘要再次清理 URL，避免不安全文本进入下游 AgentRun。
- `backend/app/research/application/report_synthesis.py`
  - Markdown/HTML 固定渲染输出标题、摘要、关键词；目录字段先做长度、URL、路径、Prompt/CoT/凭据校验。
  - 未验证候选、越权引用、危险字段仍 fail closed。
- 测试：补充目录字段传递、报告渲染和 URL 拒绝覆盖。

## 验证

- `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task10_backend.py`
  - 退出码 0，`42 passed`。
- `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py tests/test_spec034_task08_backend.py tests/test_spec034_task10_backend.py`
  - 退出码 0。

## 边界

- 只使用 Search Worker 已返回且与 `catalog_paper_id` 绑定的目录字段；不读取或下载全文，不新增 URL/网络/凭据路径。
- Synthesizer 模型仍只提交分组和引用 ID，不能注入摘要、发现、Artifact ID 或非白名单引用。
- 工作树中其它 Spec034/Task11 改动属于上游并行任务，本子任务未提交、未 push。
