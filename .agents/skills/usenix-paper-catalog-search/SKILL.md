---
name: usenix-paper-catalog-search
description: ResearchAgent 项目级 USENIX Security/DBLP 论文目录元数据检索、增量缓存、LangGraph 进度与 RAG 召回；禁止在搜索阶段下载或验证 PDF。
---

# USENIX paper catalog search — 目录元数据版

## 适用范围

本 Skill 只用于按研究方向发现和检索论文元数据。它负责 USENIX Security 官方 accepted/prepublication 页面、DBLP 辅助书目信息、SQLite 增量目录、LangGraph 任务进度、独立目录 RAG 和固定分页；不负责 PDF 下载、PDF 有效性验证或个人知识库导入。用户选择论文后的下载使用 `usenix-accepted-papers` Skill。

先读取：

- `docs/sdd/specs/015-security-paper-discovery.md`
- `docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md`
- `docs/sdd/plans/015/task-14-usenix-incremental-catalog.md`
- `docs/sdd/plans/015/task-15-langgraph-catalog-rag.md`
- `docs/sdd/plans/015/task-16-search-progress-and-pagination.md`
- `docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md`
- `docs/sdd/plans/015/README.md`

Spec 未确认、Task13–16 未完成、接口契约缺失或目标子 Agent 不存在时，只能记录阻塞，不能写业务代码或猜测流程。

## 固定发现链

1. 本轮只搜索 USENIX Security；其他会议不得静默走旧 DBLP-only 路径。
2. 对请求年份从服务端受控年度入口和确定性种子发现 accepted 页面，只接受 `www.usenix.org` 同源、同年份的 cycle/summer/fall accepted 路径。
3. 只跟随 accepted 页面显式 presentation URL；提取标题、作者、摘要和官网明确提供的关键词。关键词缺失保存空列表，禁止生成。
4. USENIX 与 DBLP 并行；DBLP 只补 DOI、DBLP key 等空字段，不覆盖官方标题、作者、摘要、关键词。没有可核对官方摘要的 DBLP-only 记录不展示。
5. 按 `source_kind + conference_id + year + unit_key` 使用 SQLite 持久缓存、条件请求、内容哈希和唯一租约。已完成单元复用；只抓取缺失、失败、过期或变化单元。
6. 使用 `POST /api/papers/searches` 创建 LangGraph 任务，轮询状态和每页固定 10 条的冻结结果；不得使用旧同步搜索旁路。

## 明确禁止 PDF

搜索和目录同步阶段禁止：

- GET/HEAD/Range PDF、PDF 探测、魔数检查、页数检查、下载或临时保存 PDF；
- 调用 `download_candidate`、`_get_pdf`、`paper_download.py` 或个人知识库导入器；
- 根据文件名猜测 PDF URL、遍历系统文件目录或向客户端返回可替换下载地址。

目录只保存页面显式提供的受控 URL。用户点击导入后，必须切换到 `usenix-accepted-papers` Skill 执行 PDF 验证。

## LangGraph 与 RAG 约束

固定节点为：`validate_request → plan_fetch_units → (sync_usenix || sync_dblp) → merge_catalog_metadata → index_changed_catalog_papers → retrieve_and_rerank → freeze_search_results → finalize_job`。节点进度、缓存命中、错误和降级写入持久事件；网络、解析、embedding、Qdrant 和 rerank 不得在 SQLite 事务/全局锁内执行。

目录向量必须使用独立 `paper-discovery-catalog` collection，复用既有 BGE-M3 dense+sparse、RRF 和可选 reranker；不得把元数据写入个人 PDF 分块 collection。固定排序为 `final_score desc, retrieval_score desc, year desc, normalized_title asc, catalog_paper_id asc`；分页读取冻结快照，不重新抓取或重排。

## UI 进度与失败语义

前端必须分别展示 USENIX 与 DBLP：`正在检查本地目录`、`已使用缓存`、`正在获取`、`整理元数据`、`完成`、`部分失败`、`来源不可用`。一个来源失败但有缓存/另一来源结果时任务为 `partial`，只有两个来源失败且无可见结果才整体 `failed`；不得统一显示模糊的“论文服务暂时不可用”。事件和错误只返回稳定 code、计数、年份和脱敏信息。

## 复用、Agent 与回填

- Task13 必须先完成逐文件复用审计；发现第二套下载、安全、导入、批任务、身份规范化、embedding 或 RRF 实现立即停止。
- 开发前确认目标 Task 和 `junior-dev`；本地 Ollama 每次最多 2 个代码文件、约 150 行，线上模型不受此数量限制。
- 弱调度器只能原样执行 Task Prompt；信息不足必须标记阻塞。
- 子 Agent 必须回传状态摘要、改动文件、测试命令/退出码、产物路径、复用依据、风险阻塞、主 Agent 后续动作、起止/耗时及可用时模型/token/工具统计。
- 目录同步、SearchJob、事件和冻结结果写入业务 SQLite；研发执行记录写入 Task 文档和（若启用）`.sdd/runtime/task-ledger.sqlite3`。

## 停止条件

出现非 allowlist URL、页面结构无法由 fixture 解释、请求 PDF、跨年份猜测、DBLP覆盖官方字段、无官方摘要的DBLP-only结果进入界面、重复抓取同一单元、内存缓存替代SQLite、任务状态无法恢复或接口字段缺失时立即停止。禁止 `git reset`、`stash`、`clean`、自动 push 或合并 `main`。
