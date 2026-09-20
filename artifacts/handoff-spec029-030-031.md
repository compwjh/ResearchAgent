# 交接说明：Spec 029/030/031 agent 路径打通

**分支**：`fix/spec029-030-031-pipeline`（已 push，从 `main` 5a8181f 切出）
**提交**：`c721dc9` fix(research): 打通 Spec029/030/031 agent 路径全链路（7 files, +1022/−26）
**验收任务**：`7841a91237275d52bf6b8004ecb25303`

---

## 一、本轮进度（已完成）

**目标**：先把 Spec 029/030/031 的**流程**跑通，暂不做内容质量优化。

**关键前提**：research 流水线有两条路径，`orchestrator.py:580` 判定——注入了 `_agent_runner` 且有 session 时走 **agent 路径**（`_run_agent_work_items()`，**当前生产路径**），否则走确定性路径（`_run_search_evaluate_coverage()`）。两条路径行为差异巨大，此前所有交付物都卡在 agent 路径上。

**已修复 3 个真实 bug**：

1. **检索工具无本地兜底**（`backend/app/skills/tool_dispatch.py`）
   `_search_catalog()` 只查外部实时源（`PaperDiscoverySearchService` → DBLP / USENIX accepted）。当前 DBLP 已被 Anubis 反爬拦截（返回挑战页 → `DBLP_INVALID_RESPONSE`），USENIX accepted 部分年份路由不可用（`ACCEPTED_ROUTE_UNAVAILABLE`），**0 命中被当作成功返回**。而本机 894 篇已索引 USENIX Security 目录（`data/paper_search/state.sqlite3` 的 `catalog_papers` + Qdrant 集合 `paper-discovery-catalog`）只有 `CatalogSearchAdapter` 会用到。
   **修法**：外部源 `count == 0` 时经 `CatalogSearchAdapter`（Spec027 唯一检索出口，不新写第二套检索）回退本地目录，再用 `PaperDiscoveryStore.get_catalog_paper` 回填真实元数据。抽出 `_format_search_entries()` / `_format_search_body()` 供两条路径共用，输出格式逐字符一致。异常或无真实行时安全退化为 0 条（返回 `None`）。

2. **agent 路径不落库选集**（`backend/app/research/application/orchestrator.py`）
   `replace_selections()` 全仓库**唯一调用点**在确定性路径，agent 路径从不写 `research_paper_selections` → Spec029 永远 `REPORT_NOT_READY`。
   **修法**：新增 `_persist_agent_selections()`，在 `paper_evaluator` completed 分支落库。**必须兼容 evaluator 两种产出形状**——聚合形 `{"kept":[...]}`，以及模型实际最常产出的**单条聚合形**（`candidate_id: null`，候选 ID 全在 `evidence_refs` 的 `catalog:<id>` 里，`keep: true`）。只接受 Search Worker 召回白名单内的 ID，去重，`evidence_level` 固定 `"catalog"`，落库失败仅告警不阻断流水线。

3. **失败不可见**（同 `orchestrator.py`）
   跳过 WorkItem 时写 `queued → failed` 属**非法状态转移**（`WORKITEM_TRANSITIONS["queued"]` 只允许 `running`/`cancelled`），被 `with suppress(Exception)` 整体吞掉 → 被跳过的 item **永远停在 `queued`**、`error_code` 丢失。
   **修法**：新增 `_fail_work_item()`，先走合法中间态 `queued → running → failed`，并 emit 失败事件。

**端到端验证结果**（任务 `7841a91237275d52bf6b8004ecb25303`）：
- 任务 `completed`，5 个 work item（s1/s2 search、e1 evaluate、c1 coverage、syn synthesize）**全部 completed**
- 选集 3 条落库：`154723ce0856642f` / `ba342a19004e4a13` / `c1dc0e43cad8a4a3`，均 relevance 0.7、evidence_level catalog
- **029** ✅ `acquisition-preview` → 200，`selection_version: 1`，3 个 pending items
- **030** ✅ `evidence-matrix` → 202 `evidence-report-v1`；`POST /reports` 生成 v1；`GET /reports/1` 有完整 cells + citation_manifest
- **031** ✅ 无 HTTP 端点，决策写入 `research_routing_decisions`（34 条）：fast → `qwen3.5:9b`，strong → `qwen3.8:27b-q4_K_M`
- 回归测试 **421 passed**（`tests/ -k "research or orchestrator or evidence or acquisition or selection or dispatch or skill or catalog"`，含新增 17 例）

**新增测试**：
- `tests/test_search_catalog_local_fallback.py`（9 例）
- `tests/test_agent_selection_persistence.py`（6 例）
- `tests/test_agent_work_item_failure_visibility.py`（2 例）

**文档**：`artifacts/spec029-030-031-api-sample.md`（三端完整 curl 样例 + 真实响应 + 枚举约束 + 落库计数）

---

## 二、遗留问题（交接给下一个 agent，按优先级）

**P0 — `_validated_evaluator_candidates()` 元数据依赖导致 synthesizer 被跳过**
`orchestrator.py:150` 附近，聚合分支要求 `ref_id in metadata_index`，而 `metadata_index` 来自 search 的 `tool_results`。当元数据缺失时该函数仍返回空 → synthesizer 被判定无有效证据 → 跳过（`NO_VALIDATED_EVIDENCE`）。
本次验收任务之所以 syn 能 completed，是因为该任务里 search 的 tool_results 恰好带了元数据。**换一个 query / 换一次检索就很可能复现跳过**。这是「内容优化前必须先解决的结构性问题」，建议下一位 agent 优先处理：要么让 evaluator 聚合形走 `catalog_paper_id` 直连本地目录补元数据，要么把 `metadata_index` 的来源从 tool_results 解耦。

**P1 — 中文 query 命中英文目录时排序质量差**
`CatalogRagAdapter` 在词法降级路径下对所有论文得分 0.0，排序退化为字典序。所以本次 3 条选集 relevance 都是 0.7（默认值），并非真实相关度。需要给中文 query 加跨语言映射（或直接用向量检索 + 阈值），否则「选出来的 3 篇」实际是随机的。

**P2 — `/api/kb/health` 报 `qdrant: false`、`chunks: 0`，主集合 `papers` 不存在**
知识库主链路（chat/RAG）与 paper-discovery 的 Qdrant 集合不是同一个。需要确认这是设计如此还是配置遗漏。

**调用 030 的两个硬约束**（下一位 agent 直接踩过的坑）：
- `claims` + `dimensions` **必须显式传**，库里没有就 409 `EVIDENCE_INSUFFICIENT`
- `claim_id` / `evidence_id` / `dimension_id` **全局唯一**，跨任务复用会 503（日志 `ValueError: evidence_id already exists with different identity`）

**环境坑（反复踩）**：
- 跑 pytest 必须 `PYTEST_DEBUG_TEMPROOT=<仓库内目录>`，且**每次跑之前** `rm -rf .pytest-tmp/pytest-of-*`，否则沙箱 shim 的 mkdir 报 `EEXIST` → 整批 ERROR（不是代码问题）
- zsh 里 `"$TID:e1"` 会被当成 history modifier，必须写 `"${TID}:e1"`
- 后台 `sleep NNN` 常被 SIGTERM（exit 137），用 ≤110s 分段
- `ps` 被沙箱拦，用 `lsof -ti tcp:8000`

---

## 三、复现方式

```bash
git fetch origin
git checkout fix/spec029-030-031-pipeline

# 回归测试（必须先清临时根目录）
rm -rf .pytest-tmp/pytest-of-*
PYTEST_DEBUG_TEMPROOT=/Users/wjh/ResearchAgent/.pytest-tmp \
  .venv/bin/python -m pytest tests/ \
  -k "research or orchestrator or evidence or acquisition or selection or dispatch or skill or catalog" -q

# 三端样例见 artifacts/spec029-030-031-api-sample.md
```
