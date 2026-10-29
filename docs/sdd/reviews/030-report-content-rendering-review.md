# Spec 030 Task 08 后端评审：结构化报告渲染

- 评审者：`/root/report_reservation_review`
- 角色：Backend Reviewer
- 模型：Luna xhigh（本次指定）
- 评审范围：仅 `backend/app/research/application/report_generation.py` 相对 `8b486c29` 的 `render_report_payload` 改动，以及 `tests/research/test_report_content_rendering.py`；按报告正文渲染交接与已确认质量合同核对。未评审 `ReportGenerationService.generate/read` 集成或并行文件。

## 结论：打回（BLOCK）

### [P1] 模型正文可伪造数字引用并改变 HTML 结构

**位置：** `backend/app/research/application/report_generation.py:294-329`；下游行为见 `backend/app/research/application/report_synthesis.py:291-295`

结构化文本字段和比较维度标签直接拼入 Markdown。既有 `render_markdown_html` 会把任意 `[数字]` 转成带 `data-citation-no` 的上标，不核对该编号是否在本次服务端 Evidence manifest 中。因此模型文本中的 `[999]` 会显示为看似有效但无对应 Evidence 的引用。文本中的 Markdown 控制行（例如 `# ...`、`- ...`、代码围栏）也会被当作结构解析；围栏本身会从 HTML 中移除，并能改变后续章节的呈现方式。现有 HTML 转义阻止了原始 HTML/XSS，但不能保证引用真实性或正文按普通文本保留。

**最小修复：** 将模型/动态文本作为纯文本渲染，对正文中的 Markdown 控制语法和 `[数字]` 做编码；仅将 renderer 自己产生的受信任 Evidence 引用标记转换为上标。补测试覆盖模型正文 `[999]`、标题/列表行和围栏，断言它们不会创建 citation marker、不会改变章节结构且文本仍可见；同时保留由 Evidence ID 派生的合法引用。

## 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py tests/research/test_report_generation.py -q --tb=short`：退出码 0；13 passed（1.01s）。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 1 | block |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

**Verdict: BLOCK — 修复 P1 后再复审。** 本结论仅针对结构化 renderer；不代表后续生成/读取链已接入或任何报告已发布。

## 窄复审（2026-10-29）：Markdown/引用编码修复

### 结论：仍为 BLOCK（原 P1 未完全解除）

标题、维度标签、问题/范围文本、逐篇分析、比较、综合发现与引用清单现在通过 `_plain_report_text` 编码；新增测试验证 `[999]`、标题/列表行、围栏保持普通文本，同时合法 Evidence 引用仍渲染为上标，legacy renderer 也保持原路径。

**残余 P1：研究缺口正文没有编码。** `report_generation.py:347-350` 将 `research_gaps[].statement` 原样拼入 Markdown。该模型字段仍可包含 `[999]` 并被通用 HTML renderer 转成无 Evidence 对应项的 citation 上标，也可用 `#`、列表行或围栏改变 HTML 结构。新增回归把攻击字符串只放入 `research_question.text`，未覆盖研究缺口这一动态字段。

**最小修复：** 将该行改为 `_plain_report_text(item['statement'])`，并在新增回归中把 `[999]`/heading/list/fence 至少再放入一个 `research_gaps[].statement`，确认没有伪造上标或结构变化且正文可见。修复后复审该字段即可。

### 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py tests/research/test_report_generation.py -q --tb=short`：退出码 0；14 passed（1.01s）。

**签字：** Backend Reviewer：BLOCK（同一 P1 尚未完全解除）；其余本次窄复审范围未发现新问题。

## 最终窄复审（2026-10-29）：P1 已解除

结构化 renderer 的 8 类模型正文位置（research question、evidence scope、三种逐篇分析、comparison、synthesis finding、research gap）现在都经过 `_plain_report_text`。动态标题、维度标签和引用清单 ID 也经过编码。只有 `citation_suffix` 根据通过 `validate_report_content` 的 Evidence ID 输出未编码数字 marker；正文中的 `[999]`、标题/列表控制行和围栏不会变成引用或 HTML 结构。参数化回归覆盖全部 8 类位置，校验文本仍可见、伪造 citation/结构不存在、真实 `[1]` Evidence 引用保留。Legacy matrix 分支仍直接调用原 renderer。

**最终签字：Backend Reviewer：PASS（仅原 P1 renderer 范围）。** 该结论不覆盖 `ReportGenerationService.generate/read` 集成、部署或 Spec 030 整体验收。

### 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py tests/research/test_report_generation.py -q --tb=short`：退出码 0；21 passed（0.98s）。
