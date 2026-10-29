# Spec 030 Task 08：结构化报告正文渲染后端交接

## 本次范围

新增可复用的 `render_report_payload(...)`，用于后续链路将模型给出的 `report_content-v1` 结构化内容转换为规范报告 JSON、Markdown 和 HTML。当前不修改 `ReportGenerationService.generate/read`，也不接入 API、AgentRunner、Orchestrator、ResearchStore、Artifact 或发布状态；没有将任何报告标记为 completed 或 published。

旧的 `evidence-report-v1` matrix payload 继续直接调用既有 `render_evidence_report`。已有 `ResearchReport.report_json` 读取路径保持原样。

## 文件

- `backend/app/research/application/report_generation.py`（465 行）：增加 `render_report_payload` 和私有结构化渲染实现，并导出新 helper。
- `tests/research/test_report_content_rendering.py`（227 行）：3 个新用例覆盖多语言正文、citation/source-level 派生、质量计数、unknown 状态、HTML 转义、无效 Evidence fail-closed 和旧 renderer fallback。

## 渲染行为

- 结构化 payload 先通过 `validate_report_content`；机器质量不是 `pass` 时抛 `EvidenceReportError`，不会返回可供发布的结构化渲染结果。
- 正文以 `research_question`、`evidence_scope`、逐篇分析、计划维度下的跨论文比较、综合发现和研究缺口为唯一内容来源。每个已支持字段只显示其文本与服务端 Evidence 映射派生的数字引用；`not_stated`/`unavailable` 使用固定“来源未说明”/“来源不可用”标签，不补造事实。
- citation manifest 按正文首次引用顺序编号；`paper_id`、`claim_id` 和 `source_level` 由经校验的当前 Evidence projection 派生。目录、摘要、全文分别显示其真实来源级别，不使用旧目录卡片生成结构化正文。
- HTML 从同一 Markdown 字符串交给既有 `render_markdown_html` 生成；模型文本作为普通文本转义，numeric citation marker 仍由现有 renderer 处理。
- 结构化报告保存 `quality_validation`，不赋 `ResearchReport.status=completed`，不设置 `published` 或 `generation`。

## 接口

`render_report_payload(payload, *, report_id, report_version, context, title="深度研究报告") -> {report, markdown, html}`

- `payload` 可为 `{"report_content": ...}`、直接的 `report_content-v1` 对象，或 legacy `evidence-report-v1` matrix。
- 结构化分支要求 `ReportQualityContext`，其 selection、当前 matrix 与 EvidenceUpgrade 输入须按质量合同构造。
- legacy matrix 分支继续使用旧 renderer；结构化 schema 无效时不会退回 legacy。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| RED：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py -q --tb=short` | 2 | 按预期收集失败：`render_report_payload` 尚不存在 |
| GREEN：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py tests/research/test_report_generation.py -q --tb=short` | 0 | 13 passed（0.98s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_generation.py tests/research/test_report_content_rendering.py` | 0 | 编译通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |

测试使用固定绝对解释器和 `--confcutdir=tests/research`，避免仓库根 conftest 的无关依赖阻塞纯报告用例。没有运行全量测试、live database/service/model、API E2E、Git 或部署操作。

## 后续边界

后续集成时应由生成链提供当前批准选集和当前 plan 的 `ReportQualityContext`，调用此 helper；再由已确认的发布链决定如何保存草稿/终态与 Artifact。此交付只提供经过机器校验的规范渲染入口，不等于报告生成链已完成。

日志：`.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-120800.md`。

## 独立评审修复记录：模型正文 Markdown 与引用伪造

- 评审发现：结构化正文中的 `[数字]` 会被通用 renderer 转成 citation 上标；标题、列表和代码围栏等 Markdown 控制行也会改变 HTML 结构或隐藏正文。
- 修复：结构化 renderer 对标题、维度标签、正文和引用清单中的动态文本统一编码 Markdown/HTML 控制字符及方括号，再通过既有固定 HTML renderer 生成结构；只保留本模块从已校验 Evidence ID 派生的数字引用标记。旧 `evidence-report-v1` renderer 分支不变。
- 测试：新增用例覆盖模型正文 `[999]`、伪造标题/列表、代码围栏，验证正文仍显示、无伪造 citation 上标/标题/代码块，且真实 Evidence 引用仍成为上标。
- RED：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py -q --tb=short`，退出码 1，新增用例因 `[999]` 未编码而失败（3 passed、1 failed）。
- GREEN：同一命令退出码 0，4 passed（0.46s）。未运行全量测试、Git 或部署；结构化 renderer 尚未接入生成链。
