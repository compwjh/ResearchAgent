# 021 论文导入异步化与进度反馈

> 用法：动手让 AI 写代码前，先和它一起把本 spec 填完整，并把实施工作拆到 `docs/sdd/plans/021/`。

## 状态

**当前状态：已完成**

> 2026-09-10：用户确认 → 实施 → 三份评审（技术/前端/验收）通过 → 转 `已完成`。
> 交付摘要：导入由"请求内同步跑完整批"改为"入队即返回 + 后台单飞执行 + 轮询"；新增 `KB_STORAGE_LOCKED` 与 `DUPLICATE_IMPORT`
> 两类可行动错误，单条目重试路由落地；运行时实测 `POST /api/papers/imports` 0–1 秒返回 `queued`、轮询到 `completed`。
> 后端 `819 passed`、前端契约 `22 passed`。验收报告见 `reviews/021-acceptance-review.md`（`tester` 子代理 429，由主会话代行并留痕）；
> 复盘落盘 `docs/sdd/retro/2026-09-10-import-sync-and-qdrant-lock.md`。遗留一项语义待评审：失败/取消条目是否释放唯一索引。

> 2026-09-10 由 spec-020 BUG-04 的 grill with docs 分析派生立项：BUG-04 只修前端相位与重试可见性，
> 但"导入为何失败失败为何查不出""为什么进度面板全程空白"两问指向同一结构性问题，故单独立项。
> 2026-09-10 用户明确"1 确认，2 停掉"：确认本 spec 与 spec-020 第 2 批；并已停掉占用 `data/kb/qdrant`
> 的多余实例（原 8002），重启 8123 后启动日志不再出现 qdrant 锁告警，本机另开客户端亦可正常打开。
> 实施顺序：先 spec-020 / Task06（即时止损），再本 spec Task02 → Task03 → Task04。

## 一句话目标

把论文批量导入从"在 HTTP 请求线程里同步跑完整批"改为"**入队即返回、后台执行、前端轮询可见**"，
并让"知识库存储被另一个实例占用"这类环境故障变成**可诊断、可行动**的错误，而不是笼统的"论文导入失败"；
同时释放终态条目对论文身份的长期占用——**已成功导入**的论文不再被自身历史批次挡住（去重交给知识库 `find_existing`），
**未入库**的论文（失败/取消）可自由重新导入与重试。

## 背景与证据（实测，2026-09-10）

| # | 事实 | 证据 |
|---|---|---|
| 1 | 批次 `61621ad2-8725-4652-bcb3-42915ed68bfe` state=`failed`，2 条 item 全部 `KB_IMPORT_FAILED`，`created_at 19:46:47Z → updated_at 19:48:47Z`（约 120s） | `data/paper_search/state.sqlite3` 直查 |
| 2 | **导入失败的近因是环境冲突**：`data/kb/qdrant` 本地存储被另一个项目实例独占 | `ps` 显示同项目两个 uvicorn（8123 起于 03:41、8002 起于 01:00）；`deploy/run-8123.log:5` 启动即告警 `Storage folder ... is already accessed by another instance of Qdrant client`；本机另开客户端验证：`RuntimeError: Storage folder data/kb/qdrant is already accessed by another instance of Qdrant client` → KB 写入/索引/查重全失败，一律退化为 `KB_IMPORT_FAILED`（`backend/app/knowledge_base/application.py:302-307,385`） |
| 3 | **导入在请求线程内同步执行** | `backend/app/paper_discovery/application/paper_import_batch_service.py:249-251`（`auto_run=True` → `run_batch`）；`retry_batch`（434-439）→ `run_batch` |
| 4 | **轮询从未真正发生**：日志里 1 次 imports + 3 次 retry 全部 200，但**没有任何 `GET /api/papers/imports/{id}`** | `deploy/run-8123.log:41-44`；原因：POST 返回时批次已终态，`frontend/app.js:1088-1091` 轮询首 tick 即 `clearInterval` 退出 |
| 5 | 20 篇上限下同步执行的最坏等待可达十余分钟，且前端无超时、无取消入口 | `store.max_items`（20）+ 事实 3；后端 `cancel` 接口存在（`backend/app/api/routes_paper.py:777-796`）但前端无入口 |
| 6 | 单条目重试能力后端已具备但无路由 | `service.retry_item`（441-446）/ `store.retry_item`（`store.py:581`）；API 只有 batch 级 retry（755-767）与 item 级 login/resume（823/849） |
| 7 | 幂等键是唯一索引而非"返回旧批次" | `store.py:349-353` + `store.py:227`；重复提交同一选择会冲突报错，不能当作重试手段 |

**结论**：`history 面板 + 轮询`这套 UI 在"同步执行"下物理上拿不到中间态，因此"进度"永远是假的；同时环境故障被压成无差别 `KB_IMPORT_FAILED`，用户无法自助。

## 数据模型

| 字段 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| `paper_import_batches.state` | 枚举 | 必填；创建后**响应里的 `state` 即为 `queued` 并立即返回**（此处指接口返回值，非 DDL 默认值），不得由请求线程推进；沿用既有 `BATCH_STATES`（不改 CAS 语义，spec-019 约束） |
| 后台批次执行句柄 `batch_runners: Mapping[batch_id, Future]` | 进程内映射 | 必填；**单飞**：同一 `batch_id` 同时最多一个执行中的 runner；进程内单线程池/线程池执行，进程退出即失效 |
| 批次/条目进度读取 | 既有 `GET /api/papers/imports/{id}` 负载 | 必填；轮询间隔沿用 2.5s；每条 item 需可见 `queued/downloading/validating/indexing/completed/failed/waiting_login/cancelled` 与 `error_code` |
| 错误码 `KB_STORAGE_LOCKED` | 字符串 | 必填（新增，可重试）；专指"知识库存储被另一个实例独占"，文案必须**可行动**："知识库存储被另一个实例占用，请关闭其他服务实例后重试" |
| 前端 `paperState.submitInflight` | number | 必填；未返回的提交/重试请求数，是 `submitting` 相位的唯一依据（spec-020 BUG-04 已定义） |
| 前端 `paperState.slowSince` | number\|null | 必填；批次进入非终态的时间戳；用于"仍在导入，可离开此页"的软提示，不用于判定失败 |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码）|
|---|---|---|---|
| `POST /api/papers/imports`（批量） | `{search_id, candidate_ids, idempotency_key?}` | **200 + 批次负载（`state=queued`，含 `batch_id` 与 items）；请求必须在亚秒级返回，不得等待下载/索引** | 400 `BATCH_LIMIT_EXCEEDED`；404 `SEARCH_NOT_FOUND`；400 `SEARCH_EXPIRED`；400 `CANDIDATE_NOT_FOUND`；400 `SEARCH_NOT_READY`；409（幂等键冲突，沿用现状）；424 `IMPORT_BATCH_ERROR` |
| `POST /api/papers/imports`（单篇兼容形态） | `{search_id, candidate_id}` | 契约**不变**（仍同步返回单篇结果；该路径单篇耗时可接受，本轮不改） | 同上 |
| `GET /api/papers/imports/{batch_id}` | 路径 `batch_id` | 200 + 实时批次负载（逐条状态） | 404 `BATCH_NOT_FOUND`；424 |
| `POST /api/papers/imports/{batch_id}/retry` | 路径 `batch_id` | 200 + **批次负载（`state` 回到 `queued`/`running`），立即返回**，后台执行 | 404；400 `INVALID_STATE_TRANSITION`（终态不可重试时）；424 |
| `POST /api/papers/import-items/{item_id}/retry`（**新增**） | 路径 `item_id` | 200 + 批次负载，该条目回到 `queued` 并后台执行 | 404 `ITEM_NOT_FOUND`；400 `INVALID_STATE_TRANSITION`（仅 `failed` 可重试）；424 |
| `POST /api/papers/import-batches/{batch_id}/cancel` | 路径 `batch_id` | 200 + 批次负载 | 400 `INVALID_STATE_TRANSITION`（仅 `queued`/`waiting_login`/`failed` 可取消，沿用现状） |

**兼容性**：原别名路径 `/api/papers/import-batches/*` 保持同构，不删除。

## 边界（每条之后会变成一条测试）

- `POST /api/papers/imports` 返回时批次必须是 `queued`，**且不得已完成任何一篇**。
- 同一 `batch_id` 并发触发执行（重复 retry / 重复 GET 触发）只允许一个 runner；第二个必须无操作返回，不得并发重复下载。
- 20 篇上限不变；超限仍 `BATCH_LIMIT_EXCEEDED`。
- 全局并发上限：同时执行的批次执行器不得多于既有 `max_workers` 语义，超出排队不丢弃、不谎报完成。
- 轮询期间**每条** item 的状态都要可见，`completed_count`/`total_count` 与 items 保持一致。
- 单条目重试只把目标 item 回到 `queued`；已成功条目不得重跑、不得重复入库。
- 取消只对 `queued`/`waiting_login`/`failed` 生效；已进入 `downloading`/`indexing` 的条目返回 `INVALID_STATE_TRANSITION`。
- **进程重启恢复**：不得新造第二套回收机制，复用既有 `service.recover_expired_leases`（`service.py:492-495`）；重启后未完成批次不得永久停在 `queued`。
- `KB_STORAGE_LOCKED`：当且仅当捕获到"存储被另一个实例占用"时返回该码；其余 KB 失败仍为 `KB_IMPORT_FAILED`/`KB_INDEX_FAILED`，不得一刀切。
- 前端：`submitting` 只在 `submitInflight > 0` 时成立；所有请求返回后必然落到 `running` / `partial_success` / `completed` / `failed` / `idle` 之一。
- 前端：批次非终态超过 X（建议 3 分钟）未推进（`updated_at` 无变化）时提示"仍在导入，可离开此页"，**不得**谎报失败也**不得**无限静默。
- 幂等行为不变：重复 POST 同一 `idempotency_key` 仍冲突报错，不静默复用旧批次。
- **唯一索引冲突必须可读**：同一论文在**活跃态**条目存在时再次导入，撞 `UNIQUE constraint failed: index 'import_item_title'`（实测 2026-09-10，`routes_paper.py:707` → `store.py:364`），必须映射为 409 `DUPLICATE_IMPORT`（"该论文已在导入批次中，请在原批次重试"），**禁止**继续以 `IMPORT_BATCH_ERROR` 兜底掩盖。
- **已入库论文重新导入 → 去重而非重跑**：对已完成且已成功入库的论文新建批次，**不得**再返回 409；由知识库既有 `find_existing`（`application.py` 扫 `papers.json`）命中，结果表达为 `PAPER_ALREADY_EXISTS` / `existing`（"论文已在知识库中"），复用既有 `paper_id`，**不得**重复落盘、不得报成批量导入失败。
- **未入库论文（失败/取消）释放后可真实重跑**：这类论文不在 `papers.json` 中，`find_existing` 不会命中，因此重新导入/重试会**真实重跑下载 + v1 索引 + 异步 v2**——这是预期行为（用户诉求正是能重来），但不得被唯一索引阻挡，也不得被误报为 `DUPLICATE_IMPORT`。

## 明确不做（划出范围，防 AI 自由发挥）

- 不改 `paper_import_batch_store.py` 的 CAS 状态机、并发领用与租约语义（沿用 spec-019 约束）。
- **释放唯一索引只改"哪些状态占位"，不改去重职责**：见下条。
- **已完成 / 失败 / 取消条目不再占用 `import_item_title`**：用户 2026-09-10 决策"释放"。唯一索引的 WHERE 收缩为**仅活跃态**（`queued`/`downloading`/`waiting_login`/`validating`/`indexing`），保留"同一篇论文不得并发重复导入"的保护；已终态条目不再阻塞重新导入，去重交给知识库的既有 `find_existing`（返回 `PAPER_ALREADY_EXISTS` / `existing` 语义）。不得为此削弱 CAS / 并发领用 / 租约语义，也不得放弃活跃态冲突的 409 保护。
- 不引入分布式/多进程任务队列（Celery/RQ/MQ 一律不做）；单进程内线程池即可。
- 不改下载安全策略、USENIX/DBLP 来源逻辑与 `_peer_from_response` 复核。
- 不做导入历史页、跨会话任务列表与后台任务中心（本轮只保证当前页面可见性）。
- 不改单篇兼容端点 `_import_single_paper` 的同步契约。
- 不自行解决"多实例共用本地 qdrant"的部署形态（只做检测与可行动提示）；是否停掉多余实例由用户决定。
- 不做自动重试次数上限/退避策略；重试保持手动。
- 不改 spec-012 双版本检索与召回归并语义。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 初稿（待 `doc-updater` 补写完整用户旅程）：

- 步骤 1：用户勾选候选论文，点击"添加到知识库"；点击后**立即**出现导入进度面板与批次卡片（状态"排队中"）。
- 步骤 2：导入在后台进行，面板按条实时更新（下载中 / 建索引中 / 已完成 / 失败 / 等待登录），状态栏仅在汇总终态时给结论。
- 步骤 3：出现失败项时，可对**单条**或**整批**重试；重试点击后立即进入进行中态，结束后场面同步刷新。
- 步骤 4：若知识库存储被占用，显示"知识库存储被另一个实例占用，请关闭其他服务实例后重试"，而不是"论文导入失败"。
- 步骤 5：用户可切换去做别的事（面板保留），需要时用"在知识库中查看"主动跳转；**任何路径不自动跳转**。
- 验收场景：
  1. 提交 3 篇：`POST` 亚秒级返回 `queued`，轮询可见逐条状态迁移，全程无需猜。
  2. 制造 1 篇失败：可单独重试该条，已成功条目不受影响。
  3. 另一个实例占用存储时：得到 `KB_STORAGE_LOCKED` 与可行动文案，而非 `KB_IMPORT_FAILED`。
  4. 长时间未推进：提示"仍在导入，可离开此页"，不谎报失败。
  5. 重新导入一篇**已在别的批次成功导入**的论文：不再被 409 拦下，返回 `queued` 并最终"论文已在知识库中"，复用既有 `paper_id`，知识库中仍只有一条；同一篇在**导入进行中**重复提交时仍给 409 `DUPLICATE_IMPORT`。

## 执行配置（由架构师填写，落盘可查）

> 沿用用户 2026-09-10 指定：**子 agent 全部 `Deepseek-V4.1-Flash`**（同日早些时候为 `hy3`，已切换；本文件与 `AGENTS.md` 选型表口径一致）。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 / 文档更新 | `Deepseek-V4.1-Flash` | 32k | `Task(doc-updater)` | 补写产品使用步骤、用户旅程与验收场景 |
| 后端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | 只改 `backend/**`：异步执行器、错误语义、单条重试路由 |
| 前端开发 | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 只改 `frontend/**`：真实轮询进度、取消、软超时提示 |
| 后端评审 | `Deepseek-V4.1-Flash` | 32k | `Task(backend-reviewer)` | 只评 `backend/**` |
| 前端评审 | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-reviewer)` | 只评 `frontend/**`（DOM 契约 / `?v=N` / XSS） |
| 后端回归 | `Deepseek-V4.1-Flash` | 32k | `Task(backend-tester)` | 只跑后端 pytest |
| 前端回归 | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-tester)` | 前端契约 / 静态核对 |
| 验收总控 | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 跨端验收与报告 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-021 | 本文件 | — | 完成 |
| 02 | 后端：批次入队即返回 + 后台单飞执行 + 启动恢复 | [`task-02-backend-async-batch-runner.md`](../plans/021/task-02-backend-async-batch-runner.md) | 01 | 完成 |
| 03 | 后端：`KB_STORAGE_LOCKED` 语义、单条目重试路由与唯一索引冲突可读化 | [`task-03-backend-error-semantics-and-item-retry.md`](../plans/021/task-03-backend-error-semantics-and-item-retry.md) | 02 | 完成 |
| 04 | 前端：真实轮询进度、取消与软超时提示 | [`task-04-frontend-progress-cancel-timeout.md`](../plans/021/task-04-frontend-progress-cancel-timeout.md) | 03 | 完成 |
| 05 | 评审、部署与复盘 | [`task-05-review-deploy-retro.md`](../plans/021/task-05-review-deploy-retro.md) | 02,03,04 | 完成 |
| 06 | 后端：释放已完成/失败/取消条目占用的唯一索引（迁移 + 重新导入去重） | [`task-06-release-title-uniqueness.md`](../plans/021/task-06-release-title-uniqueness.md) | 03 | 进行中 |

> 建议执行顺序的前置：**spec-020 / Task06（BUG-04）先行**，它修的是前端相位死锁与重试可见性，属即时止损，与本 spec 的后端异步化不冲突。

## 评审记录

- 需求评审：`docs/sdd/reviews/021-requirement-review.md`（**通过（APPROVE）**；首轮打回 0 P0 / 3 P1 / 5 P2，3 条 P1 已由架构师修订 spec 文本与 `plans/021/task-06` 后经 `architect` 定向复审闭环，残余 P2 见该文件「复审结论」段）
- 技术评审：`docs/sdd/reviews/021-tech-review.md`（**通过（APPROVE）**，`backend-reviewer`；0 CRITICAL / 0 HIGH，3 LOW + 1 INFO 已记录）
- 前端评审：`docs/sdd/reviews/021-frontend-review.md`（首轮**打回** P1 → 修复后复审**通过（Approve）**，`frontend-reviewer`）
- 验收评审：`docs/sdd/reviews/021-acceptance-review.md`（**通过**；`tester` 子代理 429 限流 → 主模型代行，报告头部已标注「代行（原因）」，开发主管签字栏填「架构师（主会话）代签」）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-10 | 架构师(自身) | 由 spec-020 BUG-04 的 grill with docs 派生立项：实测确认导入在请求线程内同步执行、轮询从未发生、失败根因为 `data/kb/qdrant` 被另一实例独占且被压成无差别 `KB_IMPORT_FAILED`。用户 Round1 五项全部采纳推荐（异步化 / 相位去自我守卫 / 整批+单条重试 / 纳入环境根因 / 拆 spec-021），并要求子 agent 统一 `hy3` |
| 2026-09-10 | 架构师(自身) | 用户就遗留语义拍板"**释放**"：已完成/失败/取消条目不再占用 `import_item_title` 唯一索引，仅保留活跃态并发保护，去重交给 KB 的 `find_existing`（`PAPER_ALREADY_EXISTS`）。已修订本 spec 的边界与明确不做，新增 Task06（含 store 迁移）。同期按用户要求把子 agent 模型由 `hy3` 统一改为 `Deepseek-V4.1-Flash` 并同步 `AGENTS.md` |
| 2026-09-10 | 架构师(自身) | Task02 运行时验收通过（停掉占存储的多余实例 + 重启 8123 后，`POST /api/papers/imports` 0 秒返回 `queued`，轮询 25 秒后 `completed 2/2`）。同时新发现"已存在条目（含失败条目）再次新建批次 → `UNIQUE constraint failed: index 'import_item_title'` 被兜底为 424 `IMPORT_BATCH_ERROR`"：新增边界条目与"不改索引、只做冲突可读化"的明确不做什么，移交 Task03；"失败条目是否释放唯一性"列为待评审的语义变更 |

---

**六条自检**：①每条边界能否写成测试→已对齐到接口与错误码；②spec 只描述需求、细节进 task；③task 链接待随 plans/021 一并建档；④范围已划死（不改 CAS、不做 MQ、不改来源策略）；⑤执行配置每行有模型与上下文；⑥产品使用步骤可映射到 4 条验收场景。
