# Task 03：接通候选确认与既有批量导入

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 协议门已完成并冻结缺口；被依赖：Task04–06；当前状态：`已完成`

## 一句话目标

把用户确认后的 Research Task 论文清单映射到现有批量导入流程，并持久化每篇论文的共享文档引用。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec029、Task02 报告、现有 paper import batch API/service 和 Research Task repository。
允许修改：backend/app/research/**、routes_research.py、必要 facade、tests/test_spec029_acquisition*.py；本地模型每次最多两代码文件。
禁止新下载器/新导入状态机、自动确认、改前端、真实凭据、push/merge/reset/stash/clean。
完成状态：preview 分类已有/待下载/需登录；确认后复用 batch；重复请求幂等；结果映射 document_id。
验证：固定候选、已有文档、部分失败、重复确认、取消、权限、定向 pytest、git diff --check。
报告：artifacts/task-03/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 确认 URLs 和元数据仍由服务端快照解析，客户端不能注入下载地址。
- 不跑全量；产出接线代码、测试和报告。Task03 已完成，候选确认与既有批量导入映射通过。

## 变更日志

- 2026-09-12：创建审批与导入接线 Task。
