# Task06 — 论文目录、评估、Critic 与覆盖补偿

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task05；当前状态：`已完成`

## 一句话目标

用真实 Search Worker、Evaluator 和 Critic 接通现有论文目录，让默认路径能找到论文、解释筛选和在证据不足时有界补搜。

## 背景与前置条件

- 必读 Spec034 的检索/阈值策略、角色 Skill 和零结果边界。
- 复用 Spec015 `CatalogSearchGraph`/`CatalogRagAdapter`、Spec032.1 来源 Skill 和 Spec033 解析结果；禁止研究命名空间内复制采集、目录或 RAG。
- 先冻结 `CatalogSourceFactory` 的真实注入点、PaperDiscoveryStore、USENIX/DBLP source 和本地目录路径；无注入来源不得走 `papers=[]` 恒空分支。

## 数据、配置与接口

- 新增 `research-paper-evaluation`、`research-coverage-review` Skill 与对应结构化 Schema。
- Search Worker 输出查询、来源、命中、刷新、候选和诊断；Evaluator 输出相关度、保留/淘汰及理由；Critic 输出 CoverageGap 与补搜建议。
- Tool 映射固定为 `sources[0]→source`、`time_range.years→years`、`max_results→limit`、`publication_scope` 原样；详情 Tool 只接收候选 `article_url/official_page_url→url`；下载/导入只接收已选候选 `candidate`，不接受单独 URL。
- “总体综述”不得作为自动 facet；相关度阈值是可解释软门槛，用户硬范围不可突破。

## 实施步骤与文件边界

1. 冻结现有目录 Tool 接口和真实缓存路径，先复现空目录/高阈值问题。
2. 实现本地优先、覆盖不足远程增量刷新和查询变体。
3. 批量评价候选并保存淘汰统计；零结果执行来源/目录/阈值诊断。
4. 最多两轮同范围 Re-plan，范围扩大转审批；证据不足生成 partial 或明确 failed。

## 子代理分派

- `backend-dev`：分 Search、Evaluate、Critic 小批实现，不跨文件大改。
- `backend-reviewer`：审查目录复用、论文提示注入、阈值和无结果真实性。
- `backend-tester`：固定样本、单源/双源失败、真实目录 smoke。

## 边界与明确不做

- 不下载 PDF、不复制目录、不实现完整 Claim/Evidence 矩阵。
- 不能因低于单一阈值把全部候选静默丢弃。
- 不用固定假文章让真实运行显示成功。

## 验收、风险与回滚

- 本地有相关论文时必须产生候选；本地不足时能证明调用远程目录刷新。
- 没有来源时必须返回 `SOURCE_UNAVAILABLE` 或可诊断 partial/failed，不得把空结果伪装 completed。
- 每个被淘汰批次有原因统计；阈值软化有边界和记录。
- 恶意论文文本不能改变 Skill、Tool、预算或计划。

## 产出物、执行结果与变更日志

- 产出：两个 Skill、三类角色执行接线、诊断数据、后端测试与评审报告。
- 执行结果：已完成；backend-reviewer 与 backend-tester 均 GO。
- 变更日志：2026-09-13 完成唯一目录来源工厂、本地优先与增量刷新诊断、Search Worker/Evaluator/Critic 结构化输出、严格 Tool 映射和两份领域 Skill；未新增目录/采集/RAG/下载/模型客户端实现。

## 执行结果（backend-dev）

- 唯一 `CatalogSourceFactory` 从既有 paper-discovery 受控出口组装 Store、USENIX/DBLP source、`CatalogRagAdapter` 与 `CatalogSearchGraph`，默认复用 `paper_discovery_db_path`（默认 `data/paper_search/state.sqlite3`）。
- `CatalogSearchAdapter` 先读已索引本地目录；不足 `max_results` 时调用既有九节点图刷新缺失/过期 source unit，并返回 cache hit/fetch/refresh/source status 诊断。异常返回稳定 `SOURCE_UNAVAILABLE`，不伪造空成功。
- Search Worker、Paper Evaluator、Coverage Critic 均输出 schema/hash/safe_summary/source_refs；Tool 参数严格执行 `sources[0]→source`、`time_range.years→years`、`max_results→limit`、`publication_scope` 原样。详情和下载映射只接受候选 URL/已选 candidate；不碰 PDF。
- `Orchestrator._run_search` 经唯一 SearchWorker→CatalogSearchAdapter 接线并保存结构化输出；Task05 Runner 在唯一 Tool 校验入口复用搜索映射。两个新增领域 Skill 只包含研究编排协议。

## 验证结果（后端）

- Task06 合同：12 passed（固定样本、失败、增量、缓存优先、阈值、安全、source scope/SearchJob/候选隔离、长生命周期 scope 切换与两轮边界）。
- Task06 + Task05/Task02/Task03/Task04/Spec027/Spec015/Spec032.1/Spec033/Skill/Tool 定向回归：234 passed、6 subtests（退出码 0）；新增 `usenix`/`dblp`/`all` source scope、SearchJob/候选隔离与长生命周期 Graph cache 合同。
- `py_compile`：退出码 0；聚焦 Ruff：退出码 0（All checks passed）；`git diff --check`：退出码 0。
- 真实目录 smoke：默认 SQLite 路径可打开但 indexed=0，受限沙箱未访问外部 USENIX/DBLP；固定 SQLite/Graph 注入样本通过，真实来源网络探针留 Task10 复验。

## 独立验收结果（backend-tester）

- 结论：GO；报告：`artifacts/task-06/backend-test-report.md`。
- 上轮 `source_scope` 兼容性回归已修复；失败测试单独复验 1 passed。
- Task06 与 Spec015/027/032/033、Skill/Tool 定向回归：384 passed、11 subtests，退出码 0；py_compile、Ruff、diff-check 均通过。

## 风险与后续动作

- 真实 Ollama/USENIX/DBLP 网络与 Qdrant 可达性仍需 Task10 运行时 smoke；不可达时保留 `SOURCE_UNAVAILABLE`/partial 诊断。
- 主 Agent 后续：进入 Task07，保持 processing_steps 三级树与实时投影复用 Task02 的 canonical event/replay 接缝；真实目录/Ollama/Qdrant smoke 留 Task10。
