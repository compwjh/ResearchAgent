# Spec 030 Task 08：report_content 输出与渲染后端独立验收

日期：2026-10-29  
结论：**PASS（仅限 output-contract 与纯函数 renderer 两个冻结切片）**

## 验收范围

独立验证 `ReportSynthesisOutput` 的可选 `report_content` schema/hash envelope，以及 `render_report_payload` 的结构化渲染与 legacy matrix fallback。未修改生产代码或测试文件；额外 probes 位于 `/tmp`。

## 命令与结果

所有命令在 `/Users/wjh/.codex/worktrees/map-usability/ResearchAgent` 执行，解释器为 `/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_synthesis_contract.py tests/research/test_report_content_synthesis.py -q --tb=short` | 0 | 43 passed in 1.51s |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_content_rendering.py tests/research/test_report_generation.py -q --tb=short` | 0 | 21 passed in 0.98s |
| `PYTHONPATH=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent /Users/wjh/ResearchAgent/.venv/bin/python /tmp/report_content_output_contract_probes.py` | 0 | 30 passed, 0 failed |
| `PYTHONPATH=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent /Users/wjh/ResearchAgent/.venv/bin/python /tmp/report_content_renderer_security_probes.py` | 0 | 25 passed, 0 failed |
| `shasum -a 256 backend/app/research/application/report_synthesis.py backend/app/research/application/report_generation.py tests/research/test_report_content_synthesis.py tests/research/test_report_content_rendering.py tests/research/test_report_generation.py` | 0 | 五个 source/test hash 前后相同（下列记录） |

## Probe 覆盖

- Output envelope：缺省 `report_content` 保持旧 key 集合与 canonical SHA-256；显式 `null` 拒绝；内容改变但 hash 未变时拒绝，重新计算后接受；内容字段确实影响 envelope hash。
- Raw ID 边界：对 12 类 ID-bearing 字段分别注入前置/后置空格的 201 code point ID（trim 后 200），30/30 均拒绝，覆盖 scope、paper、三个逐篇 block 的 Evidence、dimension、comparison、finding、gap ID。
- Renderer 动态文本：对 title、research question、evidence scope、method/findings/limitations、dimension label、comparison statement、finding statement 和 `research_gaps.statement` 注入 `[999]`、Markdown heading/list/code fence、脚本标签和链接文本。内容保留为可见文本；无伪 citation 上标、脚本节点、伪标题或代码块结构；有效引用仍产生对应数字 citation。
- 无效 Evidence：逐篇分析、comparison、finding、gap 四种引用位置都 fail closed，即使 payload 同时带 legacy matrix schema 也不 fallback。
- Legacy renderer：matrix payload 的结果与 `render_evidence_report` 直接输出相同。

## 验收源文件 SHA-256

在测试前后分别采样，五个文件 hash 相同；renderer 在验收期间未变化。

- `backend/app/research/application/report_synthesis.py` — `22a0a18f14deda47a6fefe71ce7ba8e855459dacd6c95c3162c52953cdf73da4`
- `backend/app/research/application/report_generation.py` — `61ecc6e9d1afea9f9edb6eeeb094307065928faed173c7c9017c1ee20aed619b`
- `tests/research/test_report_content_synthesis.py` — `0a83c9a3a6c6f527f05ab571e351a3b29c7c4cd30667a6922e021c8b80d10aa9`
- `tests/research/test_report_content_rendering.py` — `eaaca1f46850a978af6550f0d4bdc7187d4d7e9eaa769087343784395a7a45c5`
- `tests/research/test_report_generation.py` — `61c743af6de3744b78d7589fa42010914de423ca50744d8fbce1fa2cf599ab03`

## 限制与阻塞项

本 PASS 仅证明输出 schema/hash 与纯函数渲染行为。没有验证 API、AgentRunner、Orchestrator、Store、canonical report 持久化、Artifact/message 发布或启动恢复，也不表示报告语义质量或 Task08/Spec 030 集成验收通过。本切片无新增缺陷。

进展日志：`.codebuddy/agent-logs/spec-030/task-08/backend-tester/20261029-121947.md`。
