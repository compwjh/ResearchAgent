# Spec012 索引任务重启后永久卡「索引中 0%」— 技术评审（Gate 2）

| 项 | 值 |
|---|---|
| **评审者** | 架构师子代理（architect） |
| **角色** | Architect / 技术评审（technical review） |
| **模型** | 当前执行该任务的 Agent 自身（不写死模型代号；与 spec「执行配置」表架构师一行口径一致） |
| **分派方式** | 主会话 `Task(architect)` 单次分派，本批次两项修订合并评审、分两份文档产出 |
| **评审时间** | 2026-11-06 04:20（本地） |
| **评审对象** | `docs/sdd/specs/012-kb-recall-quality.md:186-256`（索引卡死缺陷 + 冻结范围 B1/B2/B3/F1/V1）<br>`docs/sdd/specs/043-literature-map-topic-exploration.md:548-614`（顶部操作按钮可读性与尺寸 + 冻结范围） |
| **覆盖范围说明** | 本文档同时覆盖 **Spec043 顶部操作按钮批次** 的技术维度（§5），其需求维度结论见 `docs/sdd/reviews/012-index-stuck-requirement-review.md`。两批次共用同一轮前端分派与版本号升级，故合并评审、分两份文档。 |
| **结论** | **通过（附意见）** |

---

## 0. 一句话结论

冻结范围 **B1 / B2 / B3 / F1 / V1 五条全部严格落地，零越界**；数据模型、接口契约、「被重启打断 vs 真失败」区分、提交竞态兜底、版本号同步、测试覆盖**六项均成立**；实测 **后端 519 passed + 前端 406 passed**。发现 **P1 两条**（重启风暴仍有残余窗口、`_running` 与 `indexing` 的窄窗口未完全闭合）、**P2 三条**（styles.css 未登记、7 按钮验收口径、flaky 用例）。P1 均为**已知残余、可短期窗口解释与文档化**，不改变架构选型，故**通过（附意见）**，并以强制约束 A-1～A-10 收口。

---

## 1. 事实基线（评审前实测，非推测）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/kb -q -p no:randomly --ignore=tests/kb/test_kb_startup_generation_gate.py` | **516 passed, 29 subtests passed**（30.81s） |
| `.venv/bin/python -m pytest tests/kb/test_kb_startup_generation_gate.py -q` | **3 passed** |
| `.venv/bin/python -m pytest tests/frontend -q`（deselect 1 项 flaky，见 P2-3） | **406 passed, 1 deselected**（134.83s） |
| `node --check frontend/app.js` / `frontend/literature-maps.js` | OK |
| `node tests/frontend/test_frontend_kb_index_interruption_notice.js` | ok |
| `shasum -a 256 backend/app/main.py application.py store.py` vs `upload-closure-matrix.json` | 三条 hash **逐字一致**（`85c9beb…` / `833b3ae…` / `330e5c3…`） |

> **操作教训（写入约束 A-10）**：`source .venv/bin/activate` 在本仓库 shell 中不一定生效，直接用系统 python 会报 `ModuleNotFoundError: No module named 'langchain_ollama'`（表现为 20 errors，看起来像回归）。固定用 `.venv/bin/python -m pytest`。另：**禁止并发跑多个全量 pytest**，会互相抢资源导致 CPU 0% 全阻塞（本次评审中曾出现「卡在 91%」假象）。

---

## 2. 数据模型 / 接口 / 模块拆分是否合理 —— 成立

### 2.1 数据模型：零新增，语义扩展落在既有字段

| 项 | 事实 |
|---|---|
| 新增表 / 字段 / 迁移 | **无**。`git status --porcelain` 无 `backend/migrations/` 变更；`store.py:25-41` 常量集合未新增 |
| `papers.json` schema | 未变。复用既有 `auto_requeued_chunkers`（`store.py:36`）与既有 chunker state 的 `status/progress/error`（`store.py:744-782`） |
| 新语义 | 仅「收敛时清除被中断 chunker 的 `auto_requeued_chunkers[chunker]`」（`store.py:815-825`），不引入新键 |

**评价：合理。** 用「清标记」而不是「新增 `interrupted_by_restart` 字段」来表达「这次 failed 是被打断的」，避免了 schema 变更与迁移，且语义完全落在既有 `auto_requeued_chunkers` 的一次性机会机制上——这是最小改动且与 spec-036 Task06 既有设计同源，**没有第二套实现**（回归清单第 9 条）。

### 2.2 接口契约：三条响应契约均未改动

| 接口 | 契约 | 校验 |
|---|---|---|
| `GET /api/kb/papers` | 未改。顶层 `status` 仍跟随 v1（`store.py:829-831`，与 `:776-778` 同口径）；`chunkers.*` 结构未变 | 通过 |
| `GET /api/kb/health` | 未改（`frontend/app.js:6583-6600` 消费字段未变） | 通过 |
| `POST /api/kb/documents/{id}/reindex` | **`submitted[name]` 布尔契约保持**：`application.py:856` `submitted: dict[str, bool] = {}`；`:868` `submitted[name] = bool(accepted)` | 通过 |
| 409 生成路径 | `routes_kb.py:919-930` 仍以 `all(submitted.values())` 判假 → 返 `409 INDEX_ALREADY_RUNNING`，`operation_status="running"`, `progress=0`；`submitted` 为空或非 dict 同样 409 | **契约完整保留** |
| 三处调用点是否都兼容 | `routes_kb.py:592`（上传自动建索引）、`:753`（inspection 构建）、`:906`（用户重建）**三处均对 `submitted` 做同样的 `all(...)` 判定**，未出现只改一处的分叉 | 通过 |

**关键确认（用户点名项）**：`submit_document_reindex` **仍然是布尔映射契约**，没有改成「抛 409 异常」的新风格。这意味着 `routes_kb.py` 无需改动即保持 409 语义——**接口层零改动**是本次设计最稳的一点。

### 2.3 模块拆分：三层职责未被打破

```
main.py (lifespan 编排)  →  tasks (线程池 + 启动钩子)  →  store (持久化/收敛/标记)
                                              ↘  application (提交编排 + 自愈)
```

- `main.py:57-64` 只做**编排**：调 `tasks.mark_interrupted_on_startup()`，不碰 store 内部（符合 backend-patterns addendum「API 层只做校验与编排」的同类精神）。
- `tasks.py:148-154` `mark_interrupted_on_startup()` 只做**转发**到 `store.mark_interrupted_tasks()`，不在基础设施层重复实现收敛逻辑。
- `store.py:785-833` 是唯一的收敛实现；`application.py:876-919` 是唯一的自愈实现。**无重复实现。**

---

## 3. 冻结范围 B1/B2/B3 逐条对账（含越界判定）

### B1 — `backend/app/main.py`：lifespan 接线

| spec 要求（`012:248`） | 实现 | 判定 |
|---|---|---|
| `:15-18` 增加 `tasks` 导入 | `main.py:23` `from backend.app.knowledge_base.infrastructure import tasks` | ✅ |
| 在 `recover_failed_reindexes()` **之前**插入 `tasks.mark_interrupted_on_startup()` | `:57-64`（mark_interrupted）早于 `:69-75`（recover_failed_reindexes） | ✅ 顺序正确 |
| 独立 try/except，只记日志不阻塞启动 | `:57 try:` / `:63 except Exception as error: print(...)` —— **单独一个 try 块，不与其它恢复共用** | ✅ |

补充核对（spec 未明写但必须成立）：
- 收敛**早于** `start_warmup()`（`:87-92`）与 `start_capability_scheduler()`（`:95-99`）：✅ 否则预热线程可能先抢单线程池。
- 收敛**晚于** `require_generation()`（`:52-56`）无妨，因为收敛不依赖代次门。
- 收敛失败不阻断其后的 `recover_failed_reindexes()`：由 `tests/kb/test_kb_startup_interrupted_recovery.py:236-260` `test_convergence_failure_does_not_block_startup` 用 `side_effect=RuntimeError` 正向断言 `calls == ["recover_failed"]`。✅ **非恒真断言**。

**越界判定：无越界。**

### B2 — `application.py`：消除「先写 indexing 再提交」竞态

| spec 要求（`012:249`） | 实现 | 判定 |
|---|---|---|
| `update_chunker_state(status=indexing)` 移到 `submit_index_task()` 返回 True 之后 | `:850 try: accepted = submit_index_task(...)` → `:862 if accepted: update_chunker_state(status=STATUS_INDEXING, ...)` | ✅ |
| 返回 False / 提交抛异常时不写 `indexing` | `except Exception as error: logger.warning(...)` + `update_chunker_state(status=STATUS_FAILED, progress=0, error="索引任务提交失败")`；`accepted = False` → 不进 `if accepted` | ✅ |
| 回滚 `failed` + 明确原因 | `error="索引任务提交失败"`（固定中文，**不含 `str(error)`**）；原始异常只进 `logger.warning` | ✅ 符合回归清单第 14 条「payload 只放稳定错误码，不放原始异常文本」 |
| 复用 `:1224-1236` 既有回滚范式 | 差异：既有范式用 `contextlib.suppress(Exception)` 包住回滚（`:853-857` 同样如此），避免回滚自身异常二次抛出 | ✅ 一致 |

**关键细节（用户点名项）**：`submitted[name] = bool(accepted)` 保留在循环末尾（`:868`），**布尔契约未变**，`routes_kb.py:919-930` 的 409 路径不受影响。

**越界判定：无越界。** `_generation_bound_collection` / 源 hash 校验 / `source.is_file()` 等既有前置校验一行未动。

### B3 — `store.py`：`mark_interrupted_tasks()` 标记语义

| spec 要求（`012:250`） | 实现 | 判定 |
|---|---|---|
| 收敛 `indexing → failed` | `:806-812` 对 `status == STATUS_INDEXING` 的 chunker 写 `failed` / `progress=0` / `error=reason` | ✅ |
| **仅**对本次被收敛的 chunker 清 `auto_requeued_chunkers[chunker]` | `:815-825` `kept = {name: value for name, value in markers.items() if name not in interrupted}` —— **按 `interrupted` 白名单剔除，其余键原样保留** | ✅ 精准定向 |
| 真 failed 不动标记 | 真 failed 不在 `interrupted` 里（`:797-801` 只收集 `indexing`），因此 `marked` 不自增、`changed` 不变、`markers` 不被触碰 | ✅ |
| 保留防重启风暴 | 空 dict 时 `item.pop(AUTO_REQUEUED_CHUNKERS, None)`（`:823`）只在该文档**没有其它 chunker 标记**时才删整键，否则保留 `kept` | ✅ |

**越界判定：无越界。** 顶层 `status` 跟随 v1 的既有行为保留（`:829-831`），未顺手改。

**测试对账**：
- `test_interrupted_indexing_is_failed_and_marker_cleared` —— 收敛 + 清标记 + `error == "服务重启导致中断"`。✅
- `test_true_failed_record_keeps_requeue_marker` —— `marked == 0`、`error` 仍为 `"embedding OOM"`、标记 `True`。✅
- `test_marker_of_other_chunker_survives_convergence` —— 定向清除。✅
- `test_converged_document_is_requeued_once_by_startup_recovery` —— 收敛后自愈**恰好一次**，第二次用 `side_effect=AssertionError("不得二次排队")` 守门。✅

---

## 4. 关键技术质疑逐项裁决

### 4.1 「被重启打断 vs 真失败」的区分是否可靠 —— **可靠，但有一处残余窗口（P1-1）**

**区分机制（可靠部分）**：

| 事件 | `indexing` | 标记是否被清 | 自愈是否重排 |
|---|---|---|---|
| 被重启打断的 indexing | 是 → 收敛 failed | **清**（`store.py:815-825`） | 是，一次 |
| 真跑失败（`_guarded_run` 兜底写 failed，`tasks.py:103-112`） | 否（不进 `interrupted`） | **不清** | 否（若无标记则重排一次，有标记则跳过） |
| 已放弃的真 failed（标记存在）再次重启 | 否（仍是 failed，不被收敛） | **不清** | 否 |

三种情形均由状态位 + 标记位两维判定，**判定是确定性函数、无启发式猜测**，可靠。

**残余窗口（P1-1，不阻塞）**：`store.py:785-833` 的收敛只看 `status == indexing`。跨进程重启的时序是：

```
t0  submit_document_reindex: submit_index_task()  ← 任务已进线程池
t1  工作线程开始跑，_guarded_run 内 update_chunker_state(indexing)   ← 已落盘 indexing
t2  recover_failed_reindexes: submit_document_reindex() 成功
t3  mark_chunker_auto_requeued()                        ← 标记落盘
---- 若进程在 t2 与 t3 之间被 kill ----
t4  该 chunker: status=indexing（被 t1 写），无标记
t5  下次启动：被收敛 failed + 清（本就不存在的）标记 → 再次自愈重排 → 再回到 t3 前后
```

即**有极小概率在「已提交但标记未落盘」+「恰好此时 indexing 已落盘」+「进程被杀」三条件同时满足时，形成跨重启的重复重排循环**（每次重启重排一次，不是无限次同进程重试）。

**裁决**：这是**已知残余，不是缺陷回归**，理由三条：
1. 该窗口只有在「进程恰好在 `submit_document_reindex()` 返回与 `mark_chunker_auto_requeued()` 之间被杀」时才命中，窗口宽度约一次 `save_papers()` 写盘时间（毫秒级）。
2. 最坏后果是**每次重启多跑一次索引**，不会让状态永久错乱（终态仍是 `indexed` 或 `failed`），也不会让 `indexing 0%` 永久卡住——本批次的核心缺陷已消除。
3. 彻底闭合需要持久化队列或把「标记」与「状态」放进同一原子写（改 schema / 改 `papers.json` 事务），**已被用户在 `012:242` 明确排除**（不做持久化队列）。

**强制约束 A-1**：在 `store.mark_interrupted_tasks()` docstring 与 Spec012 风险区各补一句说明该残余窗口与「用户已接受不做持久化队列」的裁决，避免后续被当成新 bug 重开。**不改代码。**

### 4.2 收敛时清标记是否可能引入重启风暴 —— **不会（有界），但需显式写出上界**

清标记确实让「每次重启都给一次机会」。会不会风暴？**不会，因为上界是「每次进程重启每 (document, chunker) 至多 1 次」**：

- 标记在 `recover_failed_reindexes()` 内**紧接着** `submit_document_reindex()` 落盘（`application.py:909`），因此**同一次启动内绝不会二次排队**——由 `test_converged_document_is_requeued_once_by_startup_recovery:143-144` 守门。
- 重启是**人工动作**（`launchctl kickstart -k` / 部署），不是自动循环，因此不存在「重启 → 重排 → 失败 → 重启」的自激回路。
- 真 failed 的标记不被清，因此「逻辑性失败」不会因为反复重启而被反复重试。

**结论：有界，不会风暴。** 唯一需要写清的是上界语义（见 A-1）。

**P1-2（本次评审新增质疑）**：`_guarded_run` 的 `finally` 里 `_running.pop(key, None)`（`tasks.py:113-115`）与 `submit_document_reindex` 的 `update_chunker_state(indexing)`（`application.py:862-864`）之间还有一个**窄窗口**：

```
submit_index_task() 返回 True  →  任务可能在极短任务里瞬间完成/失败
                                   （_guarded_run 已写 failed 并 pop _running）
update_chunker_state(indexing)  ← 提交方现在把状态覆盖回 indexing 0%
结果：任务已结束，状态却是 indexing 0%，无人再写 → 卡住
```

命中条件：任务在第 862 行执行前就完成（`runner` 极快失败，例如源文件在提交后被删除、Qdrant 立刻拒写）。窗口是「一次函数返回 + 一次内存字典插入」级别，极窄但**非零**。

**裁决**：**当前有兜底，可接受**——即使命中，下次启动的 `mark_interrupted_on_startup()` 会把它收敛成 `failed` 并重排一次（本批次正是在补这个兜底）。即**最坏情况退化为「需要一次重启才自愈」，不再是永久卡死**。

**强制约束 A-2**：在前端/后端定向测试中补一条用例——`submit_index_task` 返回 True 但状态已被并发写为 `failed` 时，**不得**把状态覆盖回 `indexing`（或明确记录「本批次接受该窗口，由启动收敛兜底」并写进风险区）。二者择一，必须落盘。

### 4.3 `submit_index_task` 返回 True 与写 indexing 之间的窄窗口是否有兜底 —— **有（兜底链完整）**

| 兜底层 | 位置 | 覆盖场景 |
|---|---|---|
| L1 `_guarded_run` 的 `finally` | `tasks.py:113-115` | 任务抛异常 → 写 failed + pop `_running` |
| L2 `submit_document_reindex` 的 `except` | `application.py:850-861` | 提交本身抛异常 → 回滚 failed（固定文案） |
| L3 `if accepted:` 守卫 | `application.py:862` | 被去重拒绝 → **完全不写 indexing** |
| L4 启动收敛 | `main.py:57-64` + `store.py:785-833` | 任何原因残留的 indexing → 收敛 failed |
| L5 启动自愈 | `main.py:69-75` + `application.py:876-919` | 收敛后的 failed → 重排一次 |
| L6 前端兜底提示 | `app.js:6560-6567` | 万一仍是 `indexing 0%` → 可见提示「可点重试」 |

**六层兜底，链完整。** 这是本次修订最扎实的部分：即使 L1-L3 全失手，L4-L6 也保证用户不会永久卡在「索引中 0%」而在界面上无路可走。

### 4.4 版本号与缓存失效是否完整 —— **完整（3 个文件 3 处升版，一处需补登记）**

| 被改文件 | 是否有生效引用需要升版 | 实际 | 判定 |
|---|---|---|---|
| `frontend/app.js` | 是 | `index.html:807 app.js?v=71`（原 70） | ✅ |
| `frontend/styles.css` | **是**（本批次新增 `#kb-view .kb-item-error-restart`、`#kb-view .kb-item-hint`） | `index.html:8 styles.css?v=69`（原 68） | ✅ 已升，**但 spec 冻结表未登记（P2-1）** |
| `frontend/literature-maps.css` | 是 | `index.html:9 literature-maps.css?v=28`（原 27） | ✅ |

`git diff frontend/index.html` 只动了这 3 行（+ 第 7 行注释标记未变），无遗漏。

**自动化守门**：`tests/frontend/test_frontend_map_header_actions_readability.py:test_index_pins_updated_asset_versions` 逐字断言三个版本号；`test_styles_version_bumped_whenever_kb_item_states_are_styled` 用「只要 `#kb-view .kb-item-hint` 还在 styles.css，`styles.css?v=` 必须 > 68」的**不变式**守门（不是硬编码 69，未来再改仍有效）。**设计得当。**

**P2-1**：`012:252` 冻结表 V1 只写 `app.js?v=70→71`，未写 `styles.css?v=68→69`。属**必要配套但未登记**，违反「架构决策须落盘为文档」。→ 强制约束 A-5（纯文档补登记）。

### 4.5 测试覆盖是否够 —— **够（含正向断言），三点需补**

| 覆盖项 | 用例 | 是否正向断言（非恒真） |
|---|---|---|
| lifespan 接线顺序 | `test_lifespan_converges_interrupted_before_recover_failed` 用 `order` 列表断言 `["mark_interrupted", "recover_failed"]` | ✅ 严格顺序断言 |
| 收敛失败不阻塞启动 | `test_convergence_failure_does_not_block_startup` | ✅ |
| 收敛清标记 / 真 failed 保留 / 定向清除 | 3 条 | ✅ |
| 收敛后自愈仅一次 | `test_converged_document_is_requeued_once_by_startup_recovery` + `side_effect=AssertionError` | ✅ |
| 提交被拒 / 接受 / 抛异常 / all 部分拒绝 | 4 条 | ✅ 含「不得写 indexing」的负向断言 |
| 提交异常不回传原始异常文本 | `assertEqual(state["error"], "索引任务提交失败")` + `assertNotIn("executor down", ...)` | ✅ 防泄漏断言 |
| 冻结清单 sha256 | `test_kb_upload_closure_matrix.py` 两条，实测 hash 一致 | ✅ |
| 前端失败态 / 重试 / 无残留 0% / 轮询不变 / 无 innerHTML | `node:vm` 用例 `test_frontend_kb_index_interruption_notice.js` 从**真实 `app.js` 源码摘函数**执行（不复制影子实现） | ✅ 设计正确 |
| Spec043 CSS 取值 / 全局基类不动 / 7-4 按钮契约 / 版本号 | `test_frontend_map_header_actions_readability.py` 11 条 | ✅ |

**需补（非阻塞）**：
- **A-3**：`mark_interrupted_on_startup()` 在 `main.py` 中的调用**未被任何测试以「真实未 patch 的函数」端到端断言**过（现有两条 lifespan 用例都把 `tasks.mark_interrupted_on_startup` patch 掉了）。建议补一条：patch 掉 store 写盘目标后，真实走 `mark_interrupted_on_startup()` → 断言 `papers.json` 中残留 indexing 变 failed。当前由「接线顺序测试 + store 单元测试」两段合成，**逻辑上等价但存在接线回归未被单点捕获的风险**。
- **A-4**：`POST /api/kb/documents/{id}/reindex` 的 **409 端到端**未被断言。现有测试只覆盖 `submit_document_reindex` 层（`submitted={v2: False}`），未断言路由层返回 `409 INDEX_ALREADY_RUNNING` + `operation_status="running"`。建议补一条路由级用例（`routes_kb.py:919-930`）。
- **A-9**：`frontend/styles.css` 新增的两条 class 需要**反向 DOM 契约断言**（`app.js` 是否真的渲染了 `kb-item-error-restart` / `kb-item-hint`）。现有 `node:vm` 用例已断言 class 在 styles.css 中存在，但建议同时断言 `renderKbPapers` 在对应分支**确实产出**该 class（回归清单第 1 条「改了 CSS 则反向确认在 app.js 被渲染」）。

---

## 5. Spec043 顶部操作按钮 —— 技术维度

| 检查项 | 事实 | 判定 |
|---|---|---|
| 作用域限定 | `literature-maps.css:177` `#literature-maps-view .literature-map-job-actions button`；`:189/:193/:198` 三态同样带 `#literature-maps-view`；`:316-317` 移动端同样带前缀 | ✅ 严格限定 |
| 全局 `.secondary-button` 未改 | `styles.css:23` 内联压缩行中 `.secondary-button { border-radius:7px; padding:9px 12px; background:var(--paper); color:var(--muted); font-size:12px; }` **未出现在本批次 diff 中** | ✅ |
| `literature-maps.css` 是否选择器级覆盖 `.secondary-button` | `grep -rn "\.secondary-button" frontend/literature-maps.css` → **仅 `:174` 的注释 1 行** | ✅ |
| 取值与 spec 一致 | 12px / 600 / 9px 14px / min-height 36px / nowrap / #4a4560 / #fff / 1px solid #d8d2ff / 8px / hover #f0edff+var(--accent) / focus-visible `0 0 0 3px var(--accent-soft)` / disabled opacity .62 | ✅ **零偏差**（逐条对 `043:588-590`） |
| 移动端 | `:317` `min-height:44px; padding:8px 12px; white-space:normal`；`:316` `flex-wrap:wrap; gap:6px` | ✅ 对 `043:591` |
| 未改文案/id/显隐/事件 | `git status` **无 `frontend/literature-maps.js` 改动** | ✅ |
| 对比度是否真达 ≥8:1 | `#4a4560` 对 `#fff`：相对亮度比约 **9.1:1**（spec 标 9.09:1）；`#f7f5ff` 约 8.4:1 | ✅ 达标 |

**P2-2（本次评审发现）**：spec `043:574` 按「4 个按钮」验收，但 `literature-maps.js:975-1010` 同一容器实有 **7 个** `secondary-button`（`打开上次预览` / `停止任务` / `重试失败单元` 默认 `hidden=true`）。CSS 用 `button` 后代选择器 → **7 个都会被放大**。桌面端 `white-space:nowrap` + `flex-wrap:wrap`（`:170`）下 7 个按钮会换行（不会溢出），移动端 `min-height:44px` 会显著变高、抽屉内可能挤压图谱高度。**这不是 CSS bug，是验收口径不完整。** → 强制约束 A-7。

**P2-3（flaky）**：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 首次跑失败（`maxGestureWallMs=1421.7 < 1000`），**复跑通过**，且该文件未被本批次改动、该用例用合成 SVG 页不加载 `literature-maps.css` 顶部条样式。判定为**浏览器性能阈值抖动（既有 flaky）**，与本批次改动无关。→ 建议登记为已知 flaky（A-10 附带）。

---

## 6. 强制约束清单（本批次收口前必须全部满足）

| 编号 | 级别 | 约束 | 验证方式 | 归属 |
|---|---|---|---|---|
| **A-1** | P1 | 在 `store.mark_interrupted_tasks()` docstring 与 Spec012 风险区补写：①「清标记」的防风暴上界是「每次进程重启每 (document, chunker) 至多 1 次」；②`submit→mark` 之间进程被杀的残余重复重排窗口；③不做持久化队列为用户 2026-11-06 裁决。**纯文档，不改代码** | 文档 diff | spec + store docstring |
| **A-2** | P1 | 对 4.2 的「`submit_index_task` 返回 True 但任务已瞬间结束、状态被覆盖回 indexing」窄窗口二选一：①补测试 + 修（提交方写 indexing 前先读一次，若已 `failed` 则不改）；②在风险区显式记录「接受该窗口，由 L4 启动收敛兜底」。**必须落盘** | 新增用例或风险区条目 | backend-dev / 架构师 |
| **A-3** | P2 | 补一条**真实未 patch** `mark_interrupted_on_startup()` 的端到端用例（临时 meta 路径，断言残留 indexing → failed） | 新用例通过 | backend-tester |
| **A-4** | P2 | 补 `POST /api/kb/documents/{id}/reindex` 的 **409 INDEX_ALREADY_RUNNING 路由级**用例（`submitted` 含 False 时） | 新用例通过 | backend-tester |
| **A-5** | P2 | 纯文档补登记 `frontend/styles.css` 改动与 `styles.css?v=68→69` 到 `012:244-252` 冻结表 + `docs/sdd/spec-status-changelog.md` | 文档 diff，无代码改动 | 架构师（主会话） |
| **A-6** | P2 | 13 个版本的一次性运维恢复证据落到 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md`，逐版本含 document_id / chunker / 恢复前状态 / 恢复后状态 / `chunk_count` / 触发方式（重排 or 自愈） | 文件存在且 13 行 | 主会话运维步骤 |
| **A-7** | P2 | Spec043 真实浏览器验收必须覆盖「同一 header 容器 7 个按钮同时可见」（或显式声明 >4 按钮允许换行并附实测截图 + 尺寸），覆盖桌面 / 1180–760px / ≤760px 三档 | 验收报告含该项 | frontend-tester |
| **A-8** | P2 | Spec012 风险区补一行「重启仍会丢在跑任务，由启动收敛 + 一次性重排兜底；不做持久化队列是用户明确裁决」 | spec 风险区 | 架构师 |
| **A-9** | P2 | `styles.css` 新增 class 需反向 DOM 契约断言：`renderKbPapers()` 在「中断失败」分支确实产出 `kb-item-error-restart`、在「idle indexing」分支确实产出 `kb-item-hint` | 断言通过 | frontend-tester |
| **A-10** | P3 | ①验证命令固定 `.venv/bin/python -m pytest`（`source activate` 在本 shell 不生效）；②**禁止并发跑多个全量 pytest**（会互相阻塞，造成「卡在 91%」假象）；③`test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 登记为已知 flaky | 团队约定落盘 | 全体 |

---

## 7. 结论：**通过（附意见）**

**阻塞项 0**。技术评审判定依据：

1. **冻结范围五条全部严格落地、零越界**（§3 逐条对账），特别是用户点名的三处契约：`submitted[name]` 布尔契约保留 → `routes_kb.py:919-930` 409 不变；`mark_interrupted_tasks` 只清被收敛 chunker 标记、真 failed 标记与状态双不动；lifespan 收敛在 `recover_failed_reindexes()` 之前且独立 try/except。
2. **模块拆分与数据模型合理**：零新增表/字段/迁移，复用既有 `auto_requeued_chunkers` 机制，无第二套实现。
3. **兜底链完整（L1–L6）**：即使最窄窗口命中，也退化为「需一次重启自愈」，不再永久卡死。
4. **版本号三处同步 + 自动化不变式守门**，无缓存失效缺口。
5. **测试覆盖充分且非恒真**，实测后端 519 passed、前端 406 passed。
6. **P1-1 / P1-2 为已知残余窗口**，成因清晰、后果有界、彻底修复已被用户明确排除，因此**不构成打回**——但必须以 A-1 / A-2 落盘文档化，否则后续会被当成新缺陷重开。

**放行条件**：A-1 与 A-2（P1）必须在验收签字前完成落盘；A-3～A-9 建议在验收前完成，A-10 为团队约定。

**合并裁决倾向**：满足 A-1 / A-2 后，本批次可合并。**但在「13 个卡住版本的一次性运维恢复 + 真实服务重启 E2E」完成之前，不得判定缺陷已闭环**（见 A-6 与 `012:230-233`），因为本批次的核心用户价值是「13 个版本恢复可用索引」，代码修复只是使其可能。

---

**评审者签名**：架构师子代理（architect）
**关联文档**：`docs/sdd/reviews/012-index-stuck-requirement-review.md`（需求评审，同期产出）
