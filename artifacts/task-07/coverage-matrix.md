# Spec032 Task07 覆盖矩阵（首轮）

| 来源 | 年份 | 官方目录状态 | 字段证据 | PDF 阶段 | 可进入 Task08 |
|---|---:|---|---|---|---|
| IEEE S&P | 2024 | `verified_sample` | 标题/作者/年份/官网 URL；摘要/关键词明确缺失 | 未请求、未探测 | 是（仅 2024） |
| IEEE S&P | 2021–2023、2025 | `unverified` | 无固定官方样本 | 未执行 | 否 |
| ACM CCS | 2021–2025 | `NO-GO` | 2021/2022/2024 有静态 accepted/proceedings 页面但缺统一身份键；2023/2025 受 JS/动态数据库阻塞（详见 [ccs-coverage](./ccs-coverage.md)） | 未执行 | 否 |
| NDSS | 2024 | `verified_sample` | 标题/作者/年份/官网 URL；摘要/关键词/DOI/PDF 明确缺失 | 未请求、未探测 | 是（仅 2024 固定样本） |
| NDSS | 2021–2023、2025 | `unverified` | 无固定官方样本 | 未执行 | 否 |
| USENIX Security | 2022–2026 | 已有独立 accepted-papers 资产，待统一运行时接线 | 由既有 USENIX 资产提供 | 仍延迟到导入 | 由 Task08 复用接线 |

验证命令：首轮固定样本与 Task06 合同测试共 `76 passed`；CCS bounded gate 另有 `56 passed`；ruff、compileall、`git diff --check` 均通过。该矩阵只记录当前证据，不把 Crossref/OpenAlex 结果冒充官网年度覆盖。
