# Spec030 Task08：report_content 输出合同接缝

日期：2026-10-29  
角色：backend-dev  
范围：只把版本化 `report_content` 接入现有 `ReportSynthesisOutput` 验证与哈希 envelope；不接 AgentRuntime、Orchestrator、Renderer、Store、canonical report 或 publication gate。

## 接口与序列化行为

- `ReportSynthesisOutput.report_content` 是可选字段。缺失时仍按旧字段形状序列化；显式 `null` 无效；存在时必须符合 `research-report-content-v1` schema。
- `REPORT_SYNTHESIS_OUTPUT_SCHEMA.properties.report_content` 暴露固定顶层字段、严格对象字段、枚举和合同 bounds（文本/ID 长度、数组数量、唯一数组）。`additionalProperties=false`。512 KiB UTF-8 总量及字段间约束由 Python 验证器执行。
- `validate_report_synthesis_output(payload, expected_version=None) -> dict[str, Any]` 继续验证原 envelope、可选 report version 和 output hash。`report_content` 仅交给 `report_quality` 的 shape/bounds validator；当前 task/plan、Evidence 映射和 provenance 校验仍由后续 server pure-quality 调用负责。
- `report_output_hash(payload)` 沿用 UTF-8、`ensure_ascii=False`、递归 key 排序及紧凑分隔符的 JSON SHA-256 规则；排除 `output_hash` 自身。新字段存在时进入 hash，改变其任意字段而不重算 hash 会被拒绝；旧字段缺失时不补 `null`，旧 hash 与旧序列化形状保持不变。
- `ReportSynthesizer.consume_validated_output` 原样保留结构化 `report_content`，同时继续执行既有 candidate/citation allowlist 校验。它仍生成旧候选元数据 Markdown；此切片未用 `report_content` 渲染正文，也未新增 `quality_validation`、`quality_status` 或 `published`。

## 修改文件

- `backend/app/research/application/report_synthesis.py`：暴露可选的严格有界 schema 与模型字段；用 report-quality shape-only 验证器拒绝错误 version/结构/bounds；缺失时保留旧序列化行为。
- `tests/research/test_report_content_synthesis.py`：6 个能力测试覆盖旧 hash/序列化、字段内容 hash、schema bounds/错误拒绝、通过候选校验后的结构化内容传递、citation allowlist 不被绕过，以及旧固定候选合成不产生质量 PASS 声明。

## 验证记录

命令均在 `/Users/wjh/.codex/worktrees/map-usability/ResearchAgent` 执行，解释器为 `/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| RED：`python -m pytest --confcutdir=tests/research tests/research/test_report_content_synthesis.py -q --tb=short` | 1 | 4 failed、2 passed；预期因旧 schema 禁止 `report_content`/缺少 schema 字段而失败 |
| GREEN：`python -m pytest --confcutdir=tests/research tests/research/test_report_content_synthesis.py -q --tb=short` | 0 | 6 passed |
| `python -m pytest --confcutdir=tests/research tests/research/test_report_synthesis_contract.py tests/research/test_report_content_synthesis.py -q --tb=short` | 0 | 41 passed |
| `python -m py_compile backend/app/research/application/report_synthesis.py tests/research/test_report_content_synthesis.py` | 0 | 编译通过 |
| `python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `python scripts/check_test_naming.py` | 0 | 命名检查通过 |
| `python -m pytest --confcutdir=tests/research tests/research/test_report_content_synthesis.py --collect-only -q` | 0 | 6 tests collected |
| `git diff --check -- backend/app/research/application/report_synthesis.py` | 0 | 生产文件差异无空白错误；新测试另由 pytest、py_compile 与命名检查覆盖 |

本轮未跑全量回归、服务/API/live E2E、模型、部署或 Git 写操作。

## 限制与交接

本切片只证明 `report_content` 可经现有输出校验/hash envelope 携带，并且旧无字段 payload 继续可读。它不证明正文的 Evidence 归属或来源等级；不计算机器质量 PASS/FAIL；不改变固定候选 Markdown/HTML、artifact、canonical report、消息或发布行为。不能据此声称既有报告质量问题已修复或报告已通过质量门禁。Task08 后续仍需把 trusted context 传入 `validate_report_content`，再实现 renderer 与 canonical/published gate；Task10 仍须做人工语义 rubric 和真实 API E2E。

初次独立 backend-reviewer 评审：PASS with one P2 follow-up，详见 [review](../../reviews/030-report-content-output-review.md)；该 follow-up 状态见下节。

进展日志：`.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-120900.md`。

## Reviewer P2 follow-up：ID 原始长度边界（2026-10-29）

独立 backend review 为 PASS（带一项 P2 follow-up）：质量纯函数的 `_id()` 先 `strip()` 再检查 200 字符，因此 `" " + "p" * 200`（raw 201 code points）会在该内部 shape helper 中按 200 长度接受；这与输出 JSON Schema 的 `maxLength: 200` 不一致。

按评审建议，在 `ReportSynthesisOutput` 边界、成功完成 shape 校验后，逐一检查所有 `report_content` ID 字段的未修剪原始长度（paper、dimension、finding、Evidence ID 及其数组）。任何 raw ID 长度超过 200 都作为 schema validation error 拒绝。`report_quality.py` 未改动；trusted source context 仍由后续 quality gate 负责。

新增前后空格回归：leading 与 trailing whitespace 各一个 201-code-point ID；两例均确认 trim 后长度为 200，并且旧实现 RED（两例均未抛错误）。修复后验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m pytest --confcutdir=tests/research tests/research/test_report_content_synthesis.py -q --tb=short` | 0 | 8 passed |
| `python -m pytest --confcutdir=tests/research tests/research/test_report_synthesis_contract.py tests/research/test_report_content_synthesis.py -q --tb=short` | 0 | 43 passed |
| `python -m py_compile backend/app/research/application/report_synthesis.py tests/research/test_report_content_synthesis.py` | 0 | 编译通过 |
| `python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `python scripts/check_test_naming.py` | 0 | 命名检查通过 |

独立 reviewer 的窄复核：待回交；未自行把 P2 标记为 reviewer 已关闭。
