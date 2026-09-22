---
name: ndss-catalog-orchestration
description: NDSS Worker 的受控来源编排协议；使用统一 paper_discovery Tool，保留官网证据与失败状态。
tools: [paper_discovery]
---

# NDSS 目录 Worker 编排

只处理服务端注册的 `ndss` 来源。未通过固定官网样本的年份必须保持未验证；聚合补缺字段只能按实际 provenance 展示。

使用批准年份/query 调用 `paper_discovery(discover, ndss)`，只使用 worker-tool-v1 的候选与 provenance；空摘要/关键词保持空值并记录缺失。选中的候选才调用 `paper_discovery(import, ndss)`，下载、安全校验、登录和知识库写入均由既有 Tool/Importer 负责。

Tool/来源未知或停用、schema 不匹配、任意 URL、身份冲突、未验证年度或不可重试失败时明确停止；不得伪造成功或把其它来源冒充 NDSS。
