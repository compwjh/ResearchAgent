# Task 08：来源注册、真实同步与 Research Graph/Store 接线

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task06、Task07；当前状态：`已完成（定向验证通过；真实外部 smoke 留 Task14）`

## 一句话目标

让七来源通过同一 Registry/Adapter 装配进入目录、SQLite、Planner 和 Research Task，而不是只在配置列表中出现。

## 现有缺口

`SourceRegistry`、同步 runtime 和 SQLite 终态已落地；原缺口是 Planner/Research Worker 对新来源仍会落入 USENIX/DBLP 旧 Graph。复用 Spec015 全局目录和 Research Task 原有事件/调度机制，不建第二套作业表或缓存。

## 实施与文件边界

后端角色负责 `backend/app/paper_discovery/application/**`、Store/Registry 必需接缝、`backend/app/api/routes_paper.py` 与 Research Planner 的最小参数校验；不碰前端、不改模型路由/报告。先建来源工厂与 `SourceResult → CatalogPaper/SourceRecord` 转换，再接字段合并/provenance、真实异步同步与可查询终态，最后接 `source_ids/scope` 422 和逐来源覆盖事件。PATCH 启停的持久化语义须响应明确，不伪装跨重启生效。

## 定向验证

- 相同年份重复只抓新增/变化/失败单元；重启/SQLite 重建后目录可恢复，单源失败不清旧缓存。
- 202 必对应真实 queued/running/terminal；无调度能力返回 409/503；未知/禁用来源 422/404；每个官方/聚合字段均有真实来源，合并不留孤儿 provenance。
- Research Worker 收到各来源真实覆盖事件，DBLP challenge 是 source_failed 而非 no_match。只跑来源 API、Store、Graph、Planner 定向测试和静态检查。

## 交接与产出

写 `artifacts/task-08/runtime-integration.md` 与 `artifacts/task-08/runtime-integration-worker-bridge.md`，附 schema 迁移、事件/接口样例、改动文件、命令/退出码与恢复验证。执行结果：Registry 七来源工厂、受控同步 API、SQLite 终态和重启读取已验证；非 `usenix/dblp/all` 来源已通过 `PaperDiscoveryToolFacade` 接入并冻结 `CatalogPaper`/`SearchJob`/`SearchResult`；旧 Graph 行为保持不变。真实外部目录、Ollama/Qdrant 和部署 smoke 留 Task14。

## 变更日志

- 2026-09-20：承接原 Task05 尚未接线的来源注册、同步与 provenance。
- 2026-09-20：Luna high 子 Agent 补充 Task08 runtime 合同测试并修复 generic adapter 状态覆盖；主 Agent 复跑 48 个 API/Store/runtime 测试与 12 个 subtests，静态检查通过。
- 2026-09-20：Task08 follow-up 完成：`CatalogSourceFactory` 接受七来源；新来源经统一 `PaperDiscoveryToolFacade`、`WorkerToolResult` validator 和既有 SQLite catalog/freeze/provenance 契约落库；Task08/09/相关 Graph 回归 215 passed，ruff、compileall、diff-check 通过。真实外部 smoke 留 Task14。
- 2026-09-20：Task07/08 follow-up 修复 NDSS 2024 runtime scope：官方年度单元显式传 `route=official`，其它年份保留 Crossref fallback；新增 runtime 不探测 PDF 的回归测试。
