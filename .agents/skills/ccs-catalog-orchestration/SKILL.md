---
name: ccs-catalog-orchestration
description: ACM CCS Worker 的受控来源编排协议；只调用统一 paper_discovery Tool，官网覆盖未验证时明确阻塞。
tools: [paper_discovery]
---

# ACM CCS 目录 Worker 编排

只处理服务端注册的 `ccs` 来源。当前官网年度覆盖尚未验证；Crossref/OpenAlex 只能作为明确标注的降级元数据，不能伪称会议官网字段。

用批准年份/query 调用 `paper_discovery(discover, ccs)`，按 envelope 的 candidate_id、provenance、error.code/retryable 交接；只有选中候选才调用 `paper_discovery(import, ccs)`。不提交任意 URL、凭据或自定义根地址，不在 Skill 中解析 HTML/PDF。

官网证据缺失、未知/停用来源、schema 不符、候选来源不符或 URL 未获白名单授权时返回 blocked，不猜参数或静默转其它会议。
