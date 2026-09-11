# Task 04：接通全文 RAG 与证据升级

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05–06；当前状态：`待执行`

## 一句话目标

使用既有知识库检索和切片定位，把摘要级 Claim 升级为可追溯的全文证据。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec029、本 Task、Task03 报告、knowledge_base application facade、Spec018 inspection 引用合同。
允许修改：backend/app/research/**、必要 KB facade 接口、tests/test_spec029_fulltext*.py；本地模型按两文件拆分。
禁止新 Qdrant Collection、chunker、embedding/reranker、下载代码、前端和全量回归。
完成状态：只对 indexed 文档检索；证据保存 document/chunk/page；删除或重建后能识别失效/新版本。
验证：多文档检索、项目隔离、恶意文本、缺 chunk、索引重建、定向 pytest、git diff --check。
报告：artifacts/task-04/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 每条 fulltext 证据必须能通过现有检查接口定位，不能只保存模型摘录。
- 产出证据升级代码、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建全文证据升级 Task。
