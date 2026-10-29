# Spec 030 Task 08：质量基础后端独立验收

日期：2026-10-29  
结论：**PASS（仅限 report-quality 纯函数切片）**

## 验收范围

独立验证 `backend/app/research/application/report_quality.py` 与 `tests/research/test_report_quality.py`。作者补入无效 Evidence ID 覆盖回归用例后，对当前工作树重新执行目标文件；未修改生产代码或测试文件。本报告不覆盖同时进行的 `research_store.py` / report reservation 改动。

本切片是结构校验与确定性计数器，不包含 API、AgentRunner、Store、Renderer、Artifact、消息发布或恢复流程。质量合同将重复、空泛文本、事实准确性和综合分析质量留给 Task10 人工语义 rubric；机器 `pass` 不能代替该 rubric。

## 实际命令与结果

以下命令均在工作树 `/Users/wjh/.codex/worktrees/map-usability/ResearchAgent` 执行，解释器为 `/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality.py -q`（作者加回归用例前） | 0 | `18 passed in 0.21s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality.py -q`（作者补入混合有效/伪造 Evidence ID 回归用例后） | 0 | `19 passed in 0.21s` |
| `PYTHONPATH=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent /Users/wjh/ResearchAgent/.venv/bin/python /tmp/report_quality_boundary_probes.py` | 0 | `53 passed, 0 failed`；临时脚本，不在仓库内 |
| `PYTHONPATH=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent /Users/wjh/ResearchAgent/.venv/bin/python /tmp/report_quality_mixed_evidence_probes.py` | 0 | 3/3 通过：paper analysis、comparison、finding 含有效及伪造 Evidence ID 时，伪造 ID 均被计为无效且不抬高覆盖数；临时脚本，不在仓库内 |

未运行全量后端套件、Store/reservation 测试、数据库或服务、模型、自然语言/API E2E、部署或 Git 操作；这些均不属于本次授权范围。

## 通过项

- 计数阈值：1,499 CJK 失败、1,500 通过；计数遵守冻结 Unicode 范围。Markdown/HTML 标题、引用编号/清单、附录、Markdown/HTML 链接与 URL、行内/围栏代码不增加正文计数。
- Schema 上下界：检查了各主要文本字段最大长度及超一字符、ID 200/201、Evidence ID 数组 32/33、paper/analysis 64/65、comparison/finding 16/17、gap 32/33，以及最低 paper/comparison/finding 数量。
- Payload 边界：构造合法结构并直接核验 UTF-8 JSON 恰为 512 KiB 时接受；增加一个字节后拒绝。
- 归属边界：当前 task、plan、matrix envelope、research_task_id 与批准选集不匹配时拒绝。跨论文 finding 只有一个不同论文的有效 Evidence 映射时不计入三项覆盖。
- Evidence 覆盖：paper analysis、comparison、finding 中混有有效映射与伪造 ID 时，全量引用校验失败且不会因剩余有效引用而计数。
- 全文 provenance：匹配的升级记录通过；task、to_level、status、document_id、source hash、manifest generation/fingerprint、chunker 或 chunk IDs 不匹配时拒绝全文 Evidence。
- 输入不可变：成功校验和候选 Evidence 失败两种路径都未改变输入 report 或服务端 context。

## 语义评审与限制

以上 PASS 仅代表 schema、来源映射、覆盖计数和 CJK 计数等机器可判门禁通过。未验证报告陈述是否真实、是否有分析价值、是否重复或是否达到综述质量；这些必须由 Task10 人工语义 rubric 与真实 API E2E 验收。

`ReportQualityContext` 没有 owner 身份字段，因此本纯函数测试不能独立证明用户/任务 owner 授权隔离；它验证的是传入服务端上下文中的 task、plan、paper 选择和 Evidence 归属。Owner authorization 仍需由上游服务链验证。

## 阻塞项

本切片无新增阻塞或新缺陷。不得将此报告解释为 Task08 集成或 Spec 030 收口验收。

进展日志：`.codebuddy/agent-logs/spec-030/task-08/backend-tester/20261029-120014.md`。
