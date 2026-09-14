# SPEC-035 体验与稳定性优化合集

状态：已完成
日期：2026-09-13
类型：bugfix + UX 优化合集（5 项独立改动，可并行开发、独立验收）

## 背景

用户反馈 5 个问题：
1. 论文批量导入失败（截图：批次 64c0f4bc，0/2 完成，两篇均"该论文导入失败"）。
2. 知识库计数延迟：上传 1 篇 PDF 后侧边栏计数显示 0，过一会才变 1。
3. 模型能力（reasoning effort 支持）每次切换模型都实时探测，慢且浪费；应后端每日定时探测并入库，前端直接读库。
4. Skill/Tool 视图中标题用了单数（Skill/Tool），且紫色 eyebrow（AGENT SKILLS / AGENT TOOLS）与其重复展示。
5. 对话模型选择器在聊天面板顶部（.chat-header），对话一长要滚到最顶才能切模型，应移到底部输入区。

## 非目标

- 不改动导入批次的数据模型（items/snapshot_json 结构保持不变）。
- 不引入新的调度框架（APScheduler 等），沿用 asyncio 后台任务。
- 不改动 reasoning effort 的档位语义与降级逻辑（spec-026 契约不变）。

---

## Bug 1：论文批量导入失败（搜索会话不存在/过期）

### 根因

`backend/app/paper_discovery/application/paper_import_batch_service.py`

- 执行/重试链路：`_run_batch_in_background → run_batch → _snapshots_for`。
- `_snapshots_for`（L382-432）在解析快照**之前**先做会话活性门禁：
  - L389-394：`discovery_store.get_search_session(batch.search_id)` 存在但已过期 → `SEARCH_EXPIRED`；
  - L395-399：`batch.search_expires_at` 缺失或已过期 → 直接失败；
  - catalog 异步搜索路径回退 `_catalog_server_snapshot`（L204-237），search_job 被 TTL 清理后抛 `SEARCH_NOT_FOUND（"搜索会话不存在"）`。
- 但**每个 item 的候选快照早已持久化**（items.snapshot_json + snapshot_hash，L370-380）。批次本身是自洽的，会话死活本不该影响重试。日志实锤：
  `PaperImportBatchServiceError: 搜索会话不存在`（run.log L228-242，批次 64c0f4bc）。

### 方案

1. `_snapshots_for` 调整门禁顺序：**先尝试解析持久化快照**；当批次内全部 item 都能取得哈希校验通过的 durable snapshot 时，**跳过会话活性/过期门禁**（批次自洽，无需会话存活）。
2. 仅当快照缺失/损坏（`SNAPSHOT_REBUILD_REQUIRED` 路径）需要重新解析时，才要求搜索会话/job 存活且未过期，保留现有报错语义。
3. `search_expires_at` 缺失不再一律报错：若 durable snapshots 完整，视为可用（legacy 批次兼容）。
4. 重试按钮（HTTP retry 路由）与服务内 `run_batch` 行为保持一致，两端共用同一 `_snapshots_for`，不另设边界。

### 验收

- 已过期搜索会话（search_session 与 search_job 均被清理）下的批次，重试单篇与重跑批次均成功导入。
- 快照确实损坏的批次仍返回 `SNAPSHOT_REBUILD_REQUIRED`，不静默失败。
- 既有单测全绿；新增测试：会话过期 + 快照完整 → 重试成功。

---

## Bug 2：知识库计数延迟

### 根因

- 前端 `frontend/app.js`：计数只由 `renderKbPapers`（L4305-4308）更新，数据来自 `GET /api/kb/papers`；上传成功后没有立即刷新列表，靠 `scheduleKbPoll`（2.5s 轮询，且仅索引期间）兜底，导致"上传后显示 0，过一会变 1"。
- 后端 `routes_kb.py` 上传接口若在解析/索引完成后才登记 paper 记录，则列表在索引前确实为空——前端无论怎么刷都是 0。

### 方案

1. 后端：`POST /api/kb/upload` 在接收文件后**同步创建 paper 记录**（status=processing/pending），再进入异步解析/索引；`GET /api/kb/papers` 立即可见该记录。（若现有实现已同步登记，则此项只补测试锁定行为。）
2. 前端：上传成功回调中**立即** `await loadKbPapers()`，不等待轮询；`scheduleKbPoll` 在存在 status 为 processing/indexing 的条目时持续轮询直至全部稳定。
3. 计数来源保持单一（papers.length），不引入独立 count 接口。

### 验收

- 上传 1 篇 PDF：请求返回后 ≤1s 内侧边栏计数变为 1，无需等待索引完成。
- 索引过程中计数不回退为 0；删除论文后计数立即 -1。
- 新增/更新前后端测试覆盖"上传后立即可见"。

---

## Bug 3：模型能力改为每日定时探测 + 入库

### 现状

- `backend/app/platform/ollama.py`：`probe_reasoning_capabilities` 对每个 effort 发真实 Ollama 请求（每模型 5 个请求、timeout 5s）；`get_reasoning_capabilities` 仅**进程内存**缓存（`_capability_cache` + TTL），重启即失、多 worker 不共享；前端切模型/刷新即触发实时探测，用户感知"每次都检测"。

### 方案

1. 新增 SQLite 表 `model_capabilities`：
   `model TEXT PK, supported_efforts TEXT(JSON), default_effort TEXT, source TEXT, evidence TEXT(JSON), probed_at TEXT(ISO8601)`。
2. 新增 `backend/app/platform/capability_scheduler.py`（或就近模块）：
   - FastAPI `lifespan` 启动 `asyncio.create_task` 后台循环：启动时先跑一轮，之后每 24h 一轮；
   - 每轮对 `GET /api/tags` 的全部模型依次 `probe_reasoning_capabilities` 并 upsert 入库；单模型失败不影响其它模型（沿用 unknown 不覆盖旧值的契约）。
3. `get_reasoning_capabilities` 读取顺序：内存缓存 → **DB（probed_at 在 24h 内视为有效，source=cache）** → 实时探测（探测结果写回 DB）。`refresh=True` 强制实时探测并写回 DB。
4. `GET /chat/reasoning-options` 契约不变（字段、四态 source 语义不变），只是数据源多了一层 DB。
5. 前端保留"重新检测能力"按钮，行为不变（触发 refresh=1）。

### 验收

- 重启后端后，切换模型不再触发实时探测（日志/计时可见直接返回 DB 值）。
- 后台每 24h 自动刷新一次；Ollama 离线时探测失败不影响已存能力值（stale 语义不变）。
- 单测：DB 命中不探测、refresh 强制探测并写库、unknown 不覆盖旧值。

---

## Bug 4：Skill/Tool 视图标题复数 + 去重

### 现状

`frontend/index.html` L578-604：两个 `.st-section` 均为 eyebrow（AGENT SKILLS / AGENT TOOLS，紫色）+ h1（`Skill` / `Tool`，单数）+ subtitle，信息重复。

### 方案

1. h1 改为复数：`Skills`、`Tools`（`#skill-tool-title` 及 Tool 区块）。
2. 去掉与 h1 重复的紫色 eyebrow（AGENT SKILLS / AGENT TOOLS 删除），保留 h1 + subtitle 一层结构。
3. 空态与状态文案同步用复数（"还没有可用的 Skills/Tools"）；`app.js` 中相关字符串同步。
4. 侧边导航 "Skill 与 Tool" 更名 "Skills 与 Tools"，面包屑同步。

### 验收

- 视图中不再出现单数 "Skill"/"Tool" 标题；同一信息只展示一层。
- 纯文案/结构改动，`node --check` 通过，无功能回归。

---

## Bug 5：模型选择器移到对话底部

### 现状

`frontend/index.html` L132-136：`#model-select` 位于 `.chat-header`（聊天面板顶部）；composer footer（L146-170）已有模式提示、上下文环、思考档位、发送按钮。

### 方案

1. 将 `label.model-picker > select#model-select` 从 `.chat-header` 移入 `.composer-footer`，置于行首（composer-tip 之前或替换其位置），与"思考"档位选择器同行。
2. `.chat-header` 若因此为空则整个移除（`chat-state` 并入 topbar 或保留在 header 视实际情况）。
3. `styles.css`：新增/调整 composer-footer 内 model-picker 样式（宽度约束、溢出省略），保证 textarea 3 行起步布局（spec-025）不被破坏。
4. `#model-select` 的 id、事件绑定、`refreshKbModelOptions` 等 JS 逻辑不变（按 id 查询，移动 DOM 位置无影响）；`app.js` 中若有依赖 `.chat-header` 层级的选择器需同步。

### 验收

- 长对话滚动到底部即可切换模型；顶部不再有模型选择器。
- 切换模型、能力档位联动（spec-024/026 行为）不回归。
- `node --check` 通过；手工验收对话页视觉无错位。

---

## 实施与分工

- 后端（Bug1、Bug2 后端半、Bug3）：backend-dev，改 `backend/**` + 后端测试。
- 前端（Bug2 前端半、Bug4、Bug5）：frontend-dev，改 `frontend/**`。
- 每项独立提交，commit message 前缀 `fix(spec-035):` / `feat(spec-035):`。

## 测试计划

- 后端：pytest 新增用例（会话过期重试、上传即登记、能力调度器入库/命中/refresh），全量回归 `tests/`。
- 前端：`node --check` 全部 JS；手工验收 4（复数/去重）与 5（选择器位置、切模型联动）。
- 跨端：tester 按上述验收点出 NNN-acceptance-review.md。

---

## 实际改动与验证结果（2026-09-15 收口）

### 提交清单（5 项全部落地）

| Bug | 提交 | 内容 |
|---|---|---|
| 1 | `a10abc5` | 批次自洽（durable snapshot 完整）时跳过搜索会话/过期门禁，重试不再因会话过期失败 |
| 2 | `0e75391` + `f0096c4` | 前端上传成功立即刷新列表、processing/indexing 持续轮询；后端补"上传后立即可见"契约测试 |
| 3 | `206b9a1` | 模型能力每日定时探测入库，读取链路 内存 → DB → 实时 |
| 4 | `2e9afb7` | Skill/Tool 标题改复数、去重紫色 eyebrow、空态文案同步 |
| 5 | `dc58125` | `#model-select` 移入 `composer-footer`，移除 `chat-header`，补溢出样式 |
| — | `c72e483` | 同步前端资源版本断言 `v=46` 与 upload-closure-matrix 冻结哈希 |

### 验证结果

- 后端定向：`pytest -k "035 or capability or upload or import_batch or session"` → **163 passed / 0 failed**。
- 全量回归：`pytest tests/` → **1764 passed**；3 个失败为既有项（`test_chat_route` 的 prompt roles 断言、`test_import_compensation` 临时目录清理），与本 spec 无关，不在本 spec 范围内修复。
- 前端语法：8 个 JS 文件 `node --check` 全部通过。
- 前端落地核对：Bug4 `index.html:579` 已是 `<h1 id="skill-tool-title">Skills</h1>`、eyebrow 已移除、空态文案为复数；Bug5 `#model-select` 位于 `index.html:141-142` 的 `.composer-footer` 内，`.chat-header` 已移除。

### 部署与运行时验证（2026-09-15 完成）

重新部署 8400 服务并实测验收：

- **向量库恢复**：先 `kill -9` 掉残留旧进程（PID 31766，此前仅释放端口未退出、仍持有 `data/kb/qdrant/.lock`），新进程（PID 99823）正常持有锁，`/api/health` 与 `/api/kb/health` 均 200。
- **目录重嵌入**：894 篇全部重建索引 —— pending 0 / **indexed 894** / failed 0（2022:176、2023:246、2024:227、2025:245）。检索 `total_results` 由 0 恢复为 649/245，结果条目带完整作者与摘要，作者回填已可被检索命中。
- **Bug3 运行时验收通过**：`GET /api/chat/reasoning-options?model=qwen3.8:27b` 返回 `"source":"cache"`、`cached_at=2026-09-14T18:48:29`（来自 `data/model_capabilities.sqlite3`），即切模型直接读库、**不再触发实时探测**；能力库现有 6 条记录。
- **Bug2 运行时验收通过**：上传 1 篇 PDF 后不做任何等待，`GET /api/kb/papers` 计数由 1 立即变 2，新记录 `status='indexing'`——**无需等索引完成即可见**；验收后已删除该测试文档（HTTP 200），`grep` 确认 0 残留。

### 遗留（不影响本 spec 收口）

- Bug4（标题复数/去重）与 Bug5（选择器位置）为纯前端展示改动，`node --check` 与代码核对已通过，**视觉层面仍建议人工过一眼**（打开 `http://127.0.0.1:8400` 看 Skills/Tools 视图与对话底部模型选择器）。
- Reranker 模型 `data/models/qwen3-reranker-0.6b-q8_0.gguf` 不存在，服务以 RRF 降级模式运行（检索状态显示 `degraded=true`）。属独立环境缺口，非本 spec 范围。
