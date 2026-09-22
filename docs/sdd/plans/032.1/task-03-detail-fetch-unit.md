# Task 03：详情页抓取单元接入目录同步

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成（待本规格收口复核）`

## 一句话目标

在 USENIX 来源同步中新增**详情页抓取阶段**，为缺摘要的论文从 presentation 详情页补齐摘要
（**fill-if-missing**），复用既有租约 / 缓存 / 限流 / 内容哈希机制，做到增量可恢复。

## 背景与前置条件

- 任务 02 已完成：`parse_usenix_detail()` 已能正确解析摘要并规避 `.description` 陷阱。
- 现状：`backend/app/paper_discovery/infrastructure/usenix_publication_source.py` 的
  `_sync_one_page()`（约 457-547 行）抓取列表页并 `_persist_paper()`（约 547 行）持久化；
  列表页无摘要，故所有论文 `abstract` 为空。
- 每篇论文的 presentation URL 即详情页地址，形如
  `https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao`。

## 既有可复用机制（**必须复用，禁止新建旁路**）

| 能力 | 位置 |
|---|---|
| 抓取 | `_get_text(url, interval)`（约 214 行） |
| 限流 | `_before_request(interval)`（约 323 行） + `_rate_limit(route)`（约 281 行） |
| 内容哈希 | `_content_hash(text)`（约 401 行） |
| 单元与租约 | `ensure_fetch_unit` / `acquire_fetch_unit` / `save_fetch_unit` / `release_lease` |
| 租约释放 | `_release_owned_fetch_unit()`（约 419 行） |
| 事件 | `_append_event()`（约 583 行） |
| 解析 | `parse_usenix_detail()`（任务 02 已补齐 abstract） |

## 实施步骤与文件边界

1. 在 `usenix_publication_source.py` 新增详情页阶段（建议在 `_persist_paper()` 之后或
   `_sync_one_page()` 内衔接，二选一并在回传中说明理由）：
   - `unit_id` 形如 `usenix|{conference_id}|{presentation_path}|detail`；
   - 已完成单元（`status == "completed"` 且有 `content_hash`）→ **跳过网络请求**；
   - `acquire_fetch_unit` 取租约 → `_before_request(interval)` 限流 → `_get_text` 抓取 →
     `parse_usenix_detail` 取摘要 → 写回目录 → 单元置 `completed`；
   - 失败 → 单元置 `failed`（可重试），**不得影响该页其余论文、不得使整个 job failed**。
2. **fill-if-missing 语义（硬性）**：仅当目录中该论文 `abstract` 为空时才写入；
   **已有摘要一律不覆盖**（列表页若已有摘要则优先保留）。
3. **安全（不可绕过）**：详情页 URL 必须能过既有 `_safe_url(..., presentation=True)`
   （`https` + `www.usenix.org` + 路径匹配 `^/conference/[^/]+/presentation/[^/]+/?$`）；
   **不接受任意 URL 入参**，非法 URL 直接拒绝并记录事件。
4. **增量可恢复**：详情页会显著放大请求量（一个年度数百篇）。必须做到——
   - 缓存命中即跳过，禁止整年重抓；
   - 未完成的单元保持 `pending/failed` 可重试，**下次搜索继续补齐**；
   - **不要求一次全量完成**，也不得因超时把已完成的部分丢弃。
5. 图接入：优先在 source 内部完成（`sync_usenix_units` 内 page 同步后触发）；
   若确需改 `catalog_search_graph.py`，必须是**最小改动且默认开启**。

**只允许改动**：`usenix_publication_source.py`、新增/更新测试。
**不要改** `usenix_paper_parser.py`（任务 02 已完成并验证）。
**不要改** `PaperDiscoverySearchService.search` 返回结构。

## 子代理分派

角色 `backend-dev`（模型 `qwen3.8:27b-mlx`）。本地模型约束：单次**最多 2 个代码文件、约 150 行**；
若改动超量，拆成两次分派并在第一次回传中说明拆分点。
回传：改动文件、测试命令/退出码/结果、unit_id 设计、风险与阻塞。

## 边界与明确不做

- **搜索/目录同步阶段仍然禁止碰 PDF**：不得 GET/HEAD/Range PDF、不得做魔数/页数检查、
  不得调用 `paper_download.py` 或探测 PDF 链接。本任务只抓 HTML 详情页取摘要。
- 不让 LLM 介入（Q4=A：LLM 只编排，代码执行）。
- 不改 `/api/papers/searches` 对外契约；`abstract_status` 语义不变（仅由 missing 转 available）。
- 不改 USENIX 高权威优先规则（USENIX 摘要不得被 DBLP 覆盖）。
- 不新增第二套 HTTP 客户端或第二套下载器。

## 验收（每条都要有测试，**不依赖真实网络**，用 fixture / fake client）

1. 缺摘要的论文能从详情页补上摘要。
2. 已有摘要的论文**不被覆盖**（fill-if-missing）。
3. 已完成单元命中缓存时**不发起网络请求**（断言 client 调用次数为 0）。
4. 单篇详情页失败 → 该单元 `failed`，**其余论文不受影响**，job 不因此整体 failed。
5. 非 allowlist URL（其它域名 / 带 query / 路径不匹配 presentation）被拒绝且不发起请求。
6. 既有 `tests/test_usenix_publication_source.py`、`tests/test_usenix_paper_parser.py` 全绿。
7. `.venv/bin/ruff check` 对改动文件干净。

## 产出物、执行结果与变更日志

### 执行结果（2026-09-20 对账）

- 改动文件：`backend/app/paper_discovery/infrastructure/usenix_publication_source.py`、
  `tests/test_usenix_publication_source.py`。
- 定向验证：`.venv/bin/python -m pytest tests/test_usenix_publication_source.py -q` → **42 passed，exit 0**（5 个既有依赖告警）。
- 复核结论：详情单元按 `usenix|{conference_id}|{year}|{cycle}|detail:{slug}` 维持增量/可重试语义；fill-if-missing、缓存跳过、单篇失败隔离、URL 白名单和 PDF 禁探测均有离线测试覆盖。
- 规格收口仍待 032.1 Task07 的独立需求/验收评审，不将本任务证据等同于整规格完成。
