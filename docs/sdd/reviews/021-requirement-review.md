# 021 需求评审

> 评审类型：**需求评审**（非技术评审；不含代码行级实现评审）
> 评审对象：[spec-021 论文导入异步化与进度反馈](../specs/021-paper-import-async-progress.md) 全文，含 Task06「释放终态条目占用的唯一索引」最新修订
> 评审人：`architect`（架构师，自身）
> 评审基线：分支 `fix/spec-021-import-async-progress`，HEAD `1ec85eb`
> 评审时间：2026-09-10
> 日志：`.codebuddy/agent-logs/spec-021/task-06/architect/20260910-223355.md`

## 结论

**打回（REQUEST CHANGES）** —— 0 个 P0，**3 个 P1**。

打回不等于否定方向：**§产品使用步骤（100%）→ Task06（机制 100%）→ §边界第 79 行验收口径（≠100%）**，需补齐后再进技术评审与实施。P1 全部是"需求口径/验收可执行性"问题，可在 spec 文本内收敛，不需要改架构。

| 编号 | 级别 | 问题 | 落点 |
|---|---|---|---|
| R1-1 | **P1** | 「释放唯一索引」的语义选择**未被记入 spec**，其**可观测后果（重跑下载/索引）也未写进验收口径**；边界第 79 行"重新导入已入库的论文即 `existing`"只对 `completed` 成立，对 `failed`/`cancelled` 不成立 | spec §一句话目标 / §边界第 79 行 / §产品使用步骤 |
| R1-2 | **P1** | §「评审记录」的需求评审条目为"待补"，但本 spec 状态已是**已完成**、Task01–05 均已标"完成" | spec §状态 / §评审记录 |
| R1-3 | **P1** | Task06 验收 1（索引 WHERE 断言）与"旧库迁移/失败与取消条目回到可重导"的**产品级验收**缺位 | Task06 §验收 / spec §产品使用步骤 §验收场景 |

---

## 判据 1：目标是否清晰可测（现象/根因/修复/验收四段是否闭环；验收能否直接执行）

**结论：通过。**

- **四段闭环完整，且是实测证据驱动**：§背景与证据 7 条事实全部带可复核证据（`state.sqlite3` 直查、`ps` 双实例、`deploy/run-8123.log:5` 启动告警、`app.js:1088-1091` 轮询首 tick 退出、`store.py:349-353` 唯一索引）；§一句话目标直接给出"改前 → 改后"形态（同步跑完 → 入队即返回 + 后台 + 轮询）。
- **验收可执行**：4 条验收场景均为可观察事实（`POST` 亚秒级返回 `queued`、逐条状态迁移可见、单条重试不影响已完成条目、`KB_STORAGE_LOCKED` 文案、长时间未推进提示），无主观词。
- 补充优点：§端点/接口 明确写"请求必须在亚秒级返回，不得等待下载/索引"，把性能要求变成了可测量断言。

## 判据 2：范围是否划死（「明确不做」是否足以防 AI 自由发挥；spec 只写做什么/为什么/做到什么程度）

**结论：通过（有一条待补强）。**

- §明确不做 10 条覆盖面足够：CAS/租约不动、释放范围不动去重职责、不引 MQ、不改下载安全与来源策略、不做历史页/任务中心、不改单篇同步契约、不自行解决多实例部署、不做自动重试退避、不改 spec-012 检索语义。与 `regression-guard` 项目清单中"禁止重复实现（下载/安全/导入/批任务只保留一套）"一致。
- 实施细节确实留在 `docs/sdd/plans/021/`：Task06 plan 才写 DDL、迁移步骤、文件边界、TDD 用例清单、验收命令（`pytest tests/test_paper_import_batch_*.py -q`、全量 819 passed 基线、`ruff check`），spec 正文不出现文件路径与 SQL。✔
- **待补强（并入 R1-1）**：spec §一句话目标只承诺"环境故障变得可诊断、可行动"。Task06 释放终端索引后新增了一条**用户可感知的结果变化**（原本被 409 拦住的重新导入，现在会真的进下载/索引流水线），这属于目标级信息，应写进 §一句话目标或 §产品使用步骤，而不是只躺在"明确不做"的否定式表述里。

## 判据 3：每条「边界」能否映射成一条测试（含糊者点名）

**结论：14 条中 13 条可测；1 条（第 79 行）点名要求改写。**

已可测（有明确断言对象）：第 66/67/68/70/71/72/73/75/76/77/78 行分别对应 `POST` 返回态、单飞 runner、20 篇上限、逐条状态与 `completed_count` 一致、单条重试范围、取消状态集、`recover_expired_leases` 复用、`submitting` 相位、软超时提示、幂等冲突、`DUPLICATE_IMPORT` 文案——Task06 plan 与 `tests/test_paper_import_batch_*.py`、`tests/test_frontend_paper_contract.py` 均已有对应用例。

**点名（P1 · R1-1）**：第 79 行

> "**终态条目释放后必须能重新导入**：已完成 / 失败 / 取消的条目**不得**阻止同一论文新建批次或重试；重新导入已入库的论文时，由知识库既有 `find_existing` 去重，结果表达为 `PAPER_ALREADY_EXISTS` / `existing`"

三点含糊，无法直接写成一条测试：

1. **"重新导入已入库的论文"没有定义"已入库"**。事实核对：`find_existing`（`backend/app/knowledge_base/application.py:217-229`）只扫 `papers.json`，即**只有曾经成功入库**的论文在册；而释放后的 `failed` / `cancelled` 条目**从来不在册**。因此同一句边界对三类终态给出**不同结论**：`completed` → `existing`（命中 KB 去重，不重复入库）；`failed`/`cancelled` → **不命中 KB，会真实走一遍下载 + v1 索引（+ 异步 v2）**。这不是缺陷（用户诉求正是"失败后能重新导入"），但 spec 现在的写法会让测试与评审误以为"一律 `existing`"。
2. **未写"重跑"的验收口径**：对 `failed`/`cancelled` 释放，验收应表述为"可重新发起导入，**允许重复下载/索引**；成功且 KB 命中后必须不重复入库"。release 的价值是让**已成功**论文免于二次下载，不是让失败论文免于重跑——这一句必须进 spec，否则"释放"的成本无人在评审时看到。
3. **未写"成功去重 vs 从未入库成功"的区分测试要求**：需要两条独立测试（前者断言 `existing` + KB 只有一条记录；后者断言可重新导入成功）。

旁证（release 对已完成论文是安全的）：`data/kb/papers.json` 实测 59 条、全部 `status=indexed`；`_same_identity` 用 doi → dblp+year+conf → title+year+conf 三级回退（title 级要求 year 与 conference 同时非空且相等），所以"释放后重导入已入库论文"会稳定命中 `existing`，不会双份落库。

其余需注意但**不阻塞**的边界表述：

- 第 67 行"重复 retry / 重复 **GET 触发**"——`GET` 触发执行不在 §端点/接口 表格的语义内（GET 只读），属表述冗余，建议删除或改为"重复 retry / 重复入队"。非阻塞（不影响测试可写）。
- 第 74 行"**当且仅当**捕获到存储被占用"——`KB_STORAGE_LOCKED` 采用窄匹配（`tests/test_paper_import.py:355-417` 两处注入验证），"当且仅当"作为需求约束可接受；建议在 Task 层写清匹配范围，避免实现者扩宽。

## 判据 4：产品使用步骤/验收场景是否覆盖正常、失败、环境故障三类路径且可映射到验收点

**结论：打回后再过（P1 · R1-1 / R1-3）。**

| 路径 | 覆盖情况 | 映射 |
|---|---|---|
| 正常 | ✔ 步骤 1/2/5 + 场景 1 | 亚秒返回 `queued`、逐条状态迁移、无自动跳转 |
| 失败 | ✔ 步骤 3 + 场景 2 | 单条/整批重试、已成功条目不重跑 |
| 环境故障 | ✔ 步骤 4 + 场景 3 | `KB_STORAGE_LOCKED` + 可行动文案 |
| 软超时/静默 | ✔ 场景 4 | "仍在导入，可离开此页" |

缺两条：

1. **Task06 的释放路径完全没有产品级场景**（P1 · R1-3）。Task06 引入的是可见行为变化（重新导入不再被 409 挡住、真正开始下载与索引），却只有 plan 级、store 级的验收。至少需要："对一篇**已在别的批次成功导入**的论文再次添加到知识库 → 不再报"该论文已在导入批次中"，结果提示"论文已在知识库中"且**不重复入库**"。
2. **"失败/取消条目释放后重导入"缺少可观测预期**（P1 · R1-1）：应补"可重新导入并**重新下载/建索引**（耗时与首次一致）"的预期，避免用户与验收者把"重跑"误判为 bug。

## 判据 5：数据模型与接口是否自洽（字段名/类型/约束/错误码文案与实现现状一致）

**结论：通过。** 逐项与实现比对的结论（详见下表"证据"）。

| # | spec 声明 | 实现现状证据 | 一致 |
|---|---|---|---|
| 5.1 | `state` 创建后立即 `queued`，沿用既有 `BATCH_STATES`，不改 CAS | `paper_import_batch_store.py:160` 状态集合含 `queued/running/waiting_login/partial_success/completed/failed/cancelled`；`architect` 侧核对 diff 未触碰 `claim_item`/`transition_item`/`mark_failed` | ✔ |
| 5.2 | `KB_STORAGE_LOCKED` 文案"知识库存储被另一个实例占用，请关闭其他服务实例后重试" | `paper_import.py:41`、`_SAFE_IMPORT_ERROR_MESSAGES`（`paper_import.py:55`）逐字一致；`tests/test_frontend_paper_contract.py:253` 断言前端同文案 | ✔ |
| 5.3 | `DUPLICATE_IMPORT` 文案"该论文已在导入批次中，请在原批次重试" / 409 | `paper_import.py:42,57`；三条路径映射 409：`paper_import_batch_service.py:267-275`（create）、`531-539`（retry_batch）、`550-559`（retry_item） | ✔ |
| 5.4 | 单条重试端点 `POST /api/papers/import-items/{item_id}/retry` → 200 + 批次负载 | `tests/test_paper_import_batch_api.py:304/348/380/389/460-572`（成功 / 404 / 活跃态 409 / 别名路径同构）；前端契约 `tests/test_frontend_paper_contract.py:264` 断言调用该路径 | ✔ |
| 5.5 | 轮询间隔 2.5s；item 状态与 `error_code` 可见 | 前端契约 22 passed（含进度面板与状态栏相位重算） | ✔ |
| 5.6 | `paperState.submitInflight` / `slowSince` 由 spec-020 BUG-04 定义 | BUG-04 数据模型表已列 `submitInflight`/`retryingBatchIds`；BUG-04 修复说明与 spec-021 边界第 75 行一致（相位只在确有未返回请求时为 `submitting`） | ✔ |
| 5.7 | `PAPER_ALREADY_EXISTS` = "论文已在知识库中" | `paper_import.py:47`；`application.py:217-229` 返回 `existing=True` | ✔ |

**两条措辞需点名（均非 P0/P1）**：①§数据模型表 第 44 行"`state` 创建后**立即**为 `queued`"若被读成字面 DDL `DEFAULT 'queued'`，与实现不同——实现是建表未设默认值、由创建路径显式写 `queued`。建议改为"创建路径显式写入 `queued`（不依赖列默认值）"。②Task06 plan 第 45 行"新增一次幂等的迁移步骤（**版本号 +1**）"表述歧义：现状 `SCHEMA_VERSION = 2`、legacy 表达为 `version=1`（`paper_import_batch_store.py:149-154` 只接受 `1` 与 `2`，无更长版本链）。"1 → 2"在语义上就是 +1，事实无误；但需在该句后加一句"即 v1 → v2（既有常量取值 2），不是新增 2 → 3"，否则实现者可能误读为要在已发布版本 2 上再加一版，从而拒绝合法旧库。

## 判据 6：与 spec-019 及 spec-020 BUG-01/02/03 是否冲突；Task06「释放唯一索引」是否与「不改 store CAS/租约」冲突

**结论：通过，无冲突。**

- **与 spec-019**：spec-019 §明确不做为"不改 `paper_import_batch_store.py` 的 CAS 状态机与并发领用语义"，并要求 `renderImportSummary()` 为状态栏唯一入口。spec-021 边界第 75 行把 `submitting` 相位的判定依据改为 `submitInflight > 0`，是**强化**"单一来源"（原文 21 条根因正是状态栏被三处覆写），不违反 spec-019；同期 Task06 靠 WHERE 收缩 + schema 版本推进落地，`transition_item`/`claim_item` 的条件 UPDATE + `expected_state` + `lease_owner` 语义未动。✔
- **与 spec-020 BUG-01/02/03**：BUG-01（即时反馈/计数）、BUG-02（导入补 v2 异步索引，复用同一单线程池）、BUG-03（移除自动跳转、direct 论文入面板）在 spec-021 中均未被改动或回退；BUG-02 涉及 KB 索引链路，spec-021 §明确不做 明确"不改 spec-012 双版本检索与召回归并语义"。✔
- **用户点名的焦点问题——Task06 释放唯一索引 vs「不改 store CAS / 租约」**：**不冲突，且约束遵守到位**。核心理由：CAS/租约管的是"**条目状态怎么迁移、谁能领用**"（行级并发控制），唯一索引管的是"**哪些身份在哪种状态下全局互斥**"（唯一性约束），两者是不同关注点。Task06 只改了后者的 `WHERE` 谓词与 schema 版本推进：
  - 未改：`transition_item` / `mark_failed` / `retry_item` / `retry_batch` 的条件与 `expected_state`、`lease_owner` 校验、`recover_expired_leases` 的租约回收、`UNIQUE(batch_id, candidate_id)`。
  - 已改（有意且被 spec 授权）：`active_sql` 谓词（`paper_import_batch_store.py:218`）+ 5 个条目身份索引重建（`227-235`）+ 版本记录推进（`149-154`）。
  - **活跃态互斥保护未被放弃**：`queued/downloading/waiting_login/validating/indexing` 仍互斥，活跃态重复导入仍 409 `DUPLICATE_IMPORT`（`tests/test_paper_import_batch_api.py:278-299`、`tests/test_paper_import_batch_store.py:132-146`）。
  - **幂等键语义有意收紧/保留**：批次级 `paper_import_batch_idempotency` 仍含 `completed`（`paper_import_batch_store.py:238`），与 spec 边界第 77 行"幂等行为不变"一致；另有 `UPDATE paper_import_batches SET idempotency_key=NULL WHERE state IN ('failed','cancelled','partial_success')`（`222-225`）用于清理历史库残留，属幂等键清理而非 CAS 改动。✔
- 一个**范围外观察**（不在本次评审范围内，仅记录）：`release` 实际作用于**全部五类**条目身份索引（doi/dblp/title/idempotency/paper_id），而 spec 只讨论了 `import_item_title`；`paper_id` 释放影响面最大（同一 paper_id 可在两个终态批次各留一条），但仅"同一论文被两次成功导入"才可能同值 paper_id，而该情形已被 KB `find_existing` 拦截，风险可接受。建议在 spec §边界第 79 行后补一句"释放范围同时覆盖 doi/dblp/title/idempotency/paper_id 五类活跃态索引，`import_item_title` 为其中代表"，以免后续读者以为只有 title 一个索引被改。

## 判据 7：执行配置五行是否齐全、架构师行是否写"自身"而非模型代号

**结论：通过（2 处小的一致性提醒）。**

- §执行配置表 **9 行齐全**（架构师、产品经理/文档更新、后端开发、前端开发、后端评审、前端评审、后端回归、前端回归、验收总控），每行都有"选用模型 / 上下文上限 / 分派方式 / 职责"四列。
- **架构师行写的是"自身（当前执行任务的 Agent，不写死模型代号）"**，符合要求，未写死模型代号。✔
- **提醒 A（一致性）**：表头前的引用块写"沿用用户 2026-09-10 指定：**子 agent 全部 `hy3`**"，但表体与 §变更日志（第 150 行）记录的却是"子 agent 模型由 `hy3` 统一改为 `Deepseek-V4.1-Flash`"。同一份 spec 内两处口径相反，会让分派者无所适从。建议把该引用块改为"用户指定 `Deepseek-V4.1-Flash`（最早为 `hy3`，已按 2026-09-10 变更）"。
- **提醒 B（沿用现状，可接受）**：spec-020 §执行配置同样写 `hy3`，而其 §变更日志记录模型已改动——两份 spec 的引用块都停留在旧值。若本轮统一口径，建议两处同步，避免再次出现"文档与 `AGENTS.md` 选型表不符"。

---

## 阻塞项清单（P0/P1）

| 编号 | 级别 | 阻塞项 | 修复建议（spec 文本级，不改代码） |
|---|---|---|---|
| R1-1 | **P1** | 边界第 79 行"重新导入已入库论文 → `existing`"对 `failed`/`cancelled` 不成立（二者不在 KB 册内，释放后会真实重跑）；且"重跑"这一可观测后果未写进验收 | 拆成两条边界：①"**已成功入库**的论文（`completed` 条目释放）再次导入 → 命中 KB `find_existing`，结果 `PAPER_ALREADY_EXISTS`/`existing`，**不得**重复落库"；②"`failed`/`cancelled` 条目释放后，同一论文**可重新发起导入并真实重跑下载与建索引**（允许重复下载/索引），成功后若已在库则仍为 `existing`"。同时在 §一句话目标 补一句"让**已成功**导入的论文不再被自身历史条目挡住" |
| R1-2 | **P1** | §「评审记录」需求评审为"待补（429 限流）"，与本 spec 状态"已完成"、Task01–05"完成"相互矛盾（流程记录与终态不一致） | 待本评审回传后，把该行更新为指向 `docs/sdd/reviews/021-requirement-review.md` 的**首轮打回 + 复审结论**；状态维持"已完成"的同时必须显式标注"需求评审于交付后补做" |
| R1-3 | **P1** | Task06 只有 store/plan 级验收（索引 WHERE 断言、tmp 库迁移），缺产品级验收 | Task06 §验收 补一条运行时验收："对已在别的批次 `completed` 的论文新建批次 → 不再是 409，而是正常导入并返回"论文已在知识库中"，且 `data/kb/papers.json` 仍只有一条记录"；spec §产品使用步骤 §验收场景 增第 5 条对应之 |

## 建议项（P2，不阻塞）

1. 迁移验证建议增加"在**真实** `data/paper_search/state.sqlite3` 副本上重开 store"的步骤（现仅有 tmp 库用例），并把"回滚 = 回退 commit + 按版本机制重建旧 WHERE"的命令写进 Task06 §回滚。
2. Task06 plan §实施步骤 1 要求"重新导入已入库论文不得重复落盘（`papers.json` 或注入 port 断言只有一条）"——当前测试集未见对应断言函数，建议补齐（这与 R1-1 的新验收口径正好合并落地）。
3. 边界第 67 行删去"重复 GET 触发"（GET 不触发执行），或改为"重复 retry / 重复入队"。
4. §数据模型 `state` 行改为"创建路径显式写入 `queued`（不依赖列默认值）"，避免被读成 DDL `DEFAULT 'queued'`。
5. §执行配置引用块与 §变更日志的模型口径对齐（提醒 A/B）。

## 复审条件

R1-1 / R1-2 / R1-3 三点在 spec（或 Task06 plan）文本层收敛后，本评审可直接转**通过**，无需重新走完整评审；R1-1 的改写同时会为 Task06 提供可直接执行的测试清单（含"成功去重 vs 未入库成功"两条独立用例）。
