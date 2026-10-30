# Spec 030：报告证据忠实度后端交接

日期：2026-10-30 12:47 Asia/Shanghai  
Task：08，接内容审查反馈；保持实施中，交原 reviewer 独立复审。

## 范围与改动

依据 [报告内容审查](./artifacts/20261030-report-only/content-review.md)、其审阅的 [report.md](./artifacts/20261030-report-only/report.md)、已确认的[质量合同](./2026-10-29-report-quality-contract.md)、[Task08](./task-08-substantive-report-generation.md) 和 [Task10](./task-10-quality-acceptance.md)，只修改后端 synthesizer 的质量路径 prompt 与对应能力测试。

- 在 `agent_runtime.py` 的 `_report_quality_prompt_boundary` 增加通用证据忠实度约束。沿用既有 `paper_analyses[].findings.text` 等文字字段，不增 schema、endpoint 或论文特例。
- 要求逐篇按题目与研究范围标明 `direct`、`adjacent` 或 `cross-domain`，解释研究实际保护/认证的对象及系统层级；分类依据是所给研究范围，不能靠“authentication”等词面重合。跨域材料明确作为类比，直接结论锚定直接相关证据。
- 明确分开模拟评估结果和实践部署事实：摘要同时报告模拟效果和部署时，应分别描述；不得因效果来自模拟而称部署不存在或未经验证，只能把摘要未给出的部署细节列为未知。
- 要求区分作者明确提出的后续工作与审阅者根据当前证据范围推得的研究缺口，并标注推断；不得从摘要扩写全文实验、用户群体、部署结果或未验证局限。
- `test_report_content_runtime.py` 新增混合认证范围反例：浏览器风险认证、MIGP 的模拟攻击结果与 Cloudflare 实际部署、内核 CFI 的 Pointer Authentication、SMTP DANE/TLSA、面部活体验证。用捕获模型核对系统约束与原始摘要证据均进入同一请求。

## TDD 与验证

新增能力测试先运行失败：提示缺少逐篇范围分类约束（1 failed）。加入 prompt 规则后该反例通过（1 passed）。最终定向验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py` | 0 | 20 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_report_content_runtime.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_report_content_runtime.py` | 0 | 通过 |

## 验收边界

新增测试验证 prompt 有证据范围指引，且测试摘要原文随请求传递；它不调用模型、不检查模型正文，也不能证明生成报告语义正确。没有新增机器语义校验或将 `quality_validation` 的结构 PASS 扩大为语义 PASS。Task10 仍须由 tester 对真实最终 Markdown/JSON 与 Evidence refs 按人工 rubric 判定。当前代码和定向测试已冻结，可由原 reviewer 独立复审。
