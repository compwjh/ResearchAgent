# Task 15：Semantic Scholar 元数据补全与字段 provenance

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task06、Task08、Task14 ｜ 当前状态：`最小实现完成，待 Task14 真实环境验收`

## 一句话目标

在官方目录/DBLP 已识别论文缺少摘要、作者或 DOI 时，以 Academic Graph 批量详情接口补缺；官方字段不覆盖，且每个补齐字段记录真实 `semantic_scholar` provenance。

## 当前证据

- `semantic_scholar_adapter.py` 已提供 DOI/ArXiv OA 查找和进程级 1 秒限流。
- `semantic_scholar_metadata.py` 提供批量详情、严格标题/作者/年份匹配、缓存边界和统一错误码；不读取 PDF。
- `CatalogSearchGraph.merge_catalog_metadata` 已接入可配置的缺字段补全，API 不可用时搜索继续并记录降级事件。

## 前置门禁

- 只能通过 Semantic Scholar Academic Graph API；禁止抓取搜索页、Reader 或 PDF。
- 生产环境必须只从 `SEMANTIC_SCHOLAR_API_KEY` 读取 key；所有请求共用 1 秒限流。
- 官方目录字段优先；关键词不由 Semantic Scholar 模型生成，缺失保持 `missing`。

## 思维链

1. 先按 DOI/ArXiv ID 批量请求，避免 N+1；观察批量上限、429 和响应缺失字段。
2. 对每个候选做标题、年份、作者交集校验；任何身份不确定都不写入。
3. 只计算缺字段 diff，写回现有 `CatalogPaper` 和字段 provenance；变更后回到既有索引状态机。
4. API 失败只影响富化，不影响官方目录结果；记录稳定错误码供 Task14 复核。

## 子任务与分派

- 后端：维护 `SemanticScholarGraphClient` 与 Graph 接线。
- 测试：验证批量请求、限流、身份门禁、官方字段不可覆盖、API 降级。

## 分派 Prompt

```text
角色：后端开发；模型：按 Spec032 执行配置；只读取 Spec032、Task15、semantic_scholar_adapter.py、CatalogSearchGraph、PaperDiscoveryStore 和相关定向测试。
允许修改：backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py、backend/app/paper_discovery/application/catalog_search_graph.py、backend/app/paper_discovery/domain/source_authority.py，以及 tests/paper_discovery/ 下分类测试；禁止修改下载器、PDF 字节、任意 URL allowlist、前端和其他 Spec 的文件。
必须遵守：只补缺字段；不得覆盖官方字段；不得在搜索阶段下载 PDF；不得打印 API key；不得新增第二套缓存或导入链。
完成后运行定向 pytest、py_compile 和静态检查；结果文档写入 docs/sdd/plans/032/artifacts/task-15/，日志写入 .codebuddy/agent-logs/spec-032/task-15/backend-dev/。
固定返回：结果状态和摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险与阻塞、主 Agent 后续动作、开始/结束/总耗时、可用时模型/token/工具统计。
```

## 子 Agent 必须返回的字段

结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时模型、token 和工具调用统计。

## 主 Agent 校验步骤

1. 检查 diff 没有下载或新 allowlist 逻辑。
2. 用 MockTransport 验证 batch body、字段、API key header 和 1 秒限流。
3. 验证官方已有摘要/作者不被覆盖，缺字段才写 `semantic_scholar` provenance。
4. API 429/5xx/身份不确定时，确认搜索结果仍可冻结且事件可观测。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/spec-032/task-15/backend-dev/*.md
```

## 测试与验收标准

- 批量详情一次最多 500 个 ID，禁止 N+1。
- 独立客户端共享进程级 1 秒限流，重试仍重新占用配额。
- 标题、作者或年份不匹配时返回 `SEMANTIC_SCHOLAR_MATCH_UNCERTAIN`，不写库。
- 删除/禁用 API key 时无外部请求，官方目录仍可用。

## 风险、停止条件与回滚

遇到 API schema 变化、身份不确定率异常、SQLite provenance 冲突或测试需要改公开合同时停止；回滚仅撤销本 Task 文件，不 reset/stash/clean。

## 产出物

客户端、Graph 富化接线、定向测试和本文件对应的验证报告。

## 执行结果

已完成最小实现；33 项相关定向测试和 Ruff 已通过。待 Task14 复核真实 key 环境、重启行为和最终回归后更新。

## 变更日志

- 2026-09-21：根据用户确认，把 Semantic Scholar 从 OA 下载兜底扩展为元数据批量补全；保留官方来源权威边界。
