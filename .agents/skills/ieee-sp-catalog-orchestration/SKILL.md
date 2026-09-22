---
name: ieee-sp-catalog-orchestration
description: IEEE S&P Worker 的官网目录优先编排协议；只调用统一 paper_discovery Tool，不在 Skill 中抓取 HTML、下载 PDF 或拼接 URL。
tools: [paper_discovery]
---

# IEEE S&P 目录 Worker 编排

只处理服务端已注册且启用的 `ieee_sp` 来源。首轮官网证据仅覆盖 IEEE S&P 2024；其它年份必须如实返回 `unverified`/`failed`，不得以 Crossref、OpenAlex 或猜测页面冒充官网覆盖。

调用顺序：用批准的 `years`/query 调用 `paper_discovery(discover, ieee_sp)`；只消费 `worker-tool-v1` 的稳定候选 ID 和逐字段 provenance；只有评估阶段选中的候选才调用 `paper_discovery(import, ieee_sp)`。缺失字段保持缺失，导入错误保留 code/retryable。

未知/停用来源、未验证年份、schema 不匹配、候选来源不一致、任意 URL 或身份不确定时立即停止并报告 blocked；不降级到其它会议，不自行设计抓取或下载步骤。
