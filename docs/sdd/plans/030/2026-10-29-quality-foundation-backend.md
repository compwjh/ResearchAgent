# Spec 030 Task 08：报告质量基础后端交接

## 本次范围

实现了纯函数报告结构校验与确定性质量计数，供后续 Task08 Runner/报告链集成。未接入 API、AgentRunner、Orchestrator、ResearchStore、Renderer、Artifact 或 UI；因此本次没有改变现有报告的生成/发布行为，也不能据此称既有短报告问题已修复。

## 交付文件

- `backend/app/research/application/report_quality.py`（594 行）：版本化 `report_content` bounds、服务端选择/Evidence/dimension/provenance 校验、质量结果模型与 CJK 计数。
- `tests/research/test_report_quality.py`（286 行）：18 个能力测试，覆盖 1,499/1,500 阈值、冻结 Unicode 范围、markup/link/heading/reference/appendix/code 排除、unknown states、schema/payload bounds、选择集/维度/证据映射、当前 task/plan 与全文升级 provenance。

## 暴露接口

- `ReportQualityContext(task_id, plan_version, selected_paper_ids, evidence_matrix, evidence_upgrades)`：`selected_paper_ids` 应来自该任务已批准的选集；`evidence_matrix` 应来自当前计划版本的 `EvidenceMatrixService.read_matrix`；`evidence_upgrades` 应是该任务的持久升级记录。
- `validate_report_content(report_content, context, revision_count=0) -> ReportQualityValidation`：返回固定 `report-quality-v1` 结果；候选引用错误返回 fail 和稳定原因码，坏的 schema 或服务端上下文抛 `ReportQualityError`。
- `count_report_content_cjk(report_content) -> int`：只读取结构化正文文本字段，排除 Markdown/HTML heading、reference marker/list、appendix section、links/URLs 和 fenced/inline/indented code。字符范围与方法版本按质量合同固定。

机器 `pass` 只表示结构、引用来源、覆盖计数和字符数门禁通过，不声称证实陈述的语义真实性；该判断留给 Task10 人工 rubric。

## 复用的现有校验

- `EvidenceMatrixService._evidence`：复用已有来源等级、Evidence ID、状态与 locator 校验。
- `EvidenceMatrixService._fulltext_upgrade_matches`：复用 document/hash/manifest/chunk provenance 匹配；本模块补充核对 upgrade 的 `task_id` 与 `to_level="fulltext"`。

没有新增检索、安全框架、模型自评分或持久化逻辑。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality.py -q` | 0 | 18 passed（0.21s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_quality.py tests/research/test_report_quality.py` | 0 | 编译通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |

测试先按 TDD 写出 RED；工作树内无 `.venv/bin/python`，使用同一仓库主目录的 `.venv` 运行，RED 收集失败为缺少目标模块，退出码 2。随后新增模块后，上表定向验证通过。没有运行全量后端测试、数据库/服务、模型或自然语言 E2E。

## 待后续处理

1. 将 context 从自然语言主路径当前批准 selection、当前 plan matrix 与升级记录构建，并将验证结果接入 AgentRunner 实际候选分支。
2. 将固定 renderer、canonical report、quality status、失败原因与 Artifact/消息发布链按已确认 Task08 合同连接；本交接不覆盖这些行为。
3. 由独立 backend-reviewer 评审本次后端代码；后续 Task 继续负责 API/恢复/预算/发布链的定向验收。

日志：`.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-115200.md`。

## 独立评审 P1 修复（2026-10-29）

评审发现同一 paper/comparison/finding 引用集合混入伪造 Evidence ID 时，旧逻辑虽然令整体质量 status 为 fail，却仍可能把剩余有效映射计入覆盖数，影响后续 partial/draft 判定。

最小修复：`_reference_papers()` 现在同时返回映射出的 paper 集合和“本次全部引用有效”标志；paper、comparison 和 finding 只有在全部引用有效且其余映射条件满足时才增加覆盖计数。无效 ID 仍去重计入 `invalid_evidence_count`。

新增 `test_mixed_valid_and_invalid_evidence_refs_do_not_increase_coverage_counts`：对 paper analysis、comparison 和三条 finding 都混入同一个伪造 Evidence ID，断言 `paper_count=4`、`comparison_count=0`、`supported_finding_count=0`、`invalid_evidence_count=1`。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| RED：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_quality.py::test_mixed_valid_and_invalid_evidence_refs_do_not_increase_coverage_counts -q --tb=short` | 1 | 按预期失败；复现旧行为 `paper_count=5`、`comparison_count=1`、`supported_finding_count=3` |
| GREEN：同一聚焦用例命令 | 0 | 1 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_quality.py -q --tb=short` | 0 | 19 passed（0.03s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_quality.py tests/research/test_report_quality.py` | 0 | 编译通过 |

使用固定绝对解释器并添加 `--confcutdir=tests/research`，避免仓库根 conftest 在共享环境中因缺少 `langchain_ollama` 阻断纯函数用例；没有运行全量回归、Git 或部署操作。本次仅修复计数门禁，仍未接入生成链，不代表报告行为已集成完成。
