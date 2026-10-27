# 只读运行基线与证据限制

graph.json及analysis-source-status.json来自当前8000服务只读请求，用作隔离回放输入和后续全文候选。

live-before-after.json及live-selected.png第一轮点击SVG g包围盒，没有真正打开详情，因此不能作为详情行为验证成功证据。保留该失败操作记录，禁止将其解释为“未复现”。后续实际circle点击和隔离回放的有效复现、尺寸及修复验证记录在2026-10-27-usability-layout.md及独立review报告。

本目录不含本轮部署后API成功链或最终验收结论。
