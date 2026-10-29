# Spec 030 Task 08 后端评审：质量基础

> 当前状态：复审 PASS，首轮 P1 已修复；首轮 BLOCK 记录保留如下。

- 评审者：`/root/quality_foundation_review`
- 角色：Backend Reviewer
- 模型：Luna xhigh（本次指定）
- 分派方式：原生子代理
- 范围：仅 `backend/app/research/application/report_quality.py`、`tests/research/test_report_quality.py`；按 Spec 030 内容充分性修订、`report-quality-v1` 质量合同与 Task08 后端计划评审。未审查并行存储/预留改动。

## 首轮结论（修复前）：BLOCK

### [P1] 混入无效 Evidence 引用时仍把覆盖项计为有效

**位置：** `backend/app/research/application/report_quality.py:474-484, 523-527, 536-538, 548-550`

`_reference_papers()` 遇到无效 Evidence ID 时只把 ID 加进全局 `invalid_ids`，但仍返回其余有效引用映射出的 paper 集合。调用方只按该集合的大小计数，没有检查本次引用集合是否全部有效。因此，一篇分析中同时有有效引用和伪造 ID，仍会增加 `paper_count`；比较和综合发现中也可在满足两篇有效论文的同时掺入无效 ID，仍增加各自覆盖计数。定向复现得到 `status=fail`、`paper_count=5`、`comparison_count=1`、`supported_finding_count=3`，但三类元素各包含一个无效 Evidence ID。

这违反合同对质量计数字段的定义（paper 的 Evidence 必须全部有效；比较/发现只计映射通过的元素），也可能使后续按覆盖数区分 `partial` 与 `draft` 的状态映射误判证据覆盖。全局 `INVALID_EVIDENCE_REFERENCE` 仍会令总体 status 为 `fail`，所以当前缺陷本身不会令候选通过或发布。

**最小修复：** 让引用映射 helper 同时返回“本次引用是否全部有效”的布尔值；只有当它为真且 paper 映射/维度/选择条件满足时，才增加 `paper_count`、`comparison_count` 或 `supported_finding_count`。增加混合有效/无效 ID 的回归用例，断言这些覆盖计数不增长。

## 验证

- 首轮实际命令 `python -m pytest tests/research/test_report_quality.py -q`：setup 时导入 `backend.app.platform.ollama` 失败，提示缺少 `langchain_ollama`。后续确认该交互式 zsh 的 `python` alias 指向 `/opt/anaconda3`，所以该输出不是项目 `.venv` 的依赖状态。
- 首轮实际命令 `python -m pytest --confcutdir=tests/research tests/research/test_report_quality.py -q --tb=short`：18 passed；当时同样使用了上述 alias，并跳过与纯函数用例无关的根级能力缓存 fixture。
- 用测试内的上下文/报告构造器，无文件改动地复现了上述计数偏差。

## 首轮 Review Summary（修复前）

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 1 | block |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **BLOCK — 修正 P1 覆盖计数后再复审。**

## 复审（2026-10-29）

**复审结论：PASS；首轮 P1 已修复。**

- `_reference_papers()` 现在返回有效 paper 映射及本次引用是否全部有效；逐篇分析、比较和综合发现只有在所有 Evidence 引用均有效时才计入覆盖数。研究缺口仍会把无效引用记入全局失败结果。
- 新增 `test_mixed_valid_and_invalid_evidence_refs_do_not_increase_coverage_counts`，断言混合引用时 `paper_count=4`、`comparison_count=0`、`supported_finding_count=0`、`invalid_evidence_count=1`。
- 按主会话要求使用绝对解释器 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality.py -q`：退出码 0，19 passed（0.21s）。
- 首轮的 `langchain_ollama` 导入错误来自 shell alias 选择了 Anaconda Python；不作为项目依赖缺陷记录。

**当前复审 Verdict: PASS — 原 P1 已解除。**
