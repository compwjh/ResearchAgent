# Task09 后端独立代码复核：摘要队列与图谱视图兼容

## 复核范围

- 分支：`codex/spec043-map-interaction`
- 角色：`backend-reviewer`
- 复核日期：2026-10-24
- 只评审：
  - `backend/app/api/routes_literature_maps.py`
  - `backend/app/literature_maps/application/analysis.py`
  - `backend/app/literature_maps/application/service.py`
  - `backend/app/literature_maps/domain/models.py`
  - `backend/app/literature_maps/infrastructure/store.py`
  - `tests/literature_maps/test_map_analysis_queue.py`
- 依据：`docs/sdd/plans/043/task-09-backend-report.md`、`task-09-interface-contract.md`、Spec043、Task08 隔离回归计划及精确 git diff。
- 明确不评：前端改动、知识库下载/导入失败 bug、部署、外部模型/API。

## 验证记录

在 `/private/tmp/spec043-task09-backend-review-E7GRud` 临时隔离数据根下执行：

| 检查 | 结果 |
|---|---|
| `scripts/check_test_layout.py` | 退出码 0，`test layout: ok` |
| `scripts/check_test_naming.py` | 退出码 0，未发现 spec/task 编号测试文件 |
| Task09 精准后端测试（7 个 literature_maps 测试文件） | 退出码 0，47 passed |
| 变更文件 `py_compile` | 退出码 0 |
| `git diff --check`（指定后端/测试文件） | 退出码 0 |

精准测试命令（所有数据库、KB、Qdrant、pytest cache/basetemp 均指向上述临时根目录）：

```text
PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule \
LITERATURE_MAP_DB_PATH=<review-root>/data/literature_maps/literature_maps.sqlite3 \
... .venv/bin/python -m pytest -q \
tests/literature_maps/test_map_analysis_queue.py \
tests/literature_maps/test_map_analysis_lifecycle.py \
tests/literature_maps/test_map_analysis_evidence.py \
tests/literature_maps/test_map_analysis_api.py \
tests/literature_maps/test_map_store.py \
tests/literature_maps/test_map_job_store.py \
tests/literature_maps/test_map_job_recovery.py \
-o cache_dir=<review-root>/pytest-cache --basetemp=<review-root>/pytest-tmp
```

精准测试通过不能覆盖下面的并发、配置变更和迁移缺口，因此本复核结论仍为不通过。

## Findings

### [P1] 自动 ensure 的幂等键不含模型配置，模型切换被吞成幂等冲突

文件：`backend/app/literature_maps/application/service.py:1200-1207`；`backend/app/literature_maps/application/analysis.py:459-484`

`_enqueue_abstract_summaries()` 的 `auto-sync` key 只由 `node_id/title/abstract/external_ids` 组成，不含 `MODEL_NAME` 或配置指纹；但 `ensure_analysis_queue()` 把模型写入 `params_hash`。同一地图发生模型配置切换时，第二次自动 ensure 使用同一幂等键却得到新的 params hash，store 抛出 `ValueError("idempotency conflict")`，随后 service 在 1207 行把该异常静默吞掉。因此不会创建新的 `analysis_id/version`，旧配置的分析会继续被复用。

可复现证据（将 `analysis.MODEL_NAME` 从默认值改为 `changed-model` 后再次触发自动 enqueue）：

```text
before: [(1, 'qwen3.8:27b')]
after:  [(1, 'qwen3.8:27b')]
queue:  {'total': 1, 'completed': 0, 'queued': 1, ...}
```

修复方向：自动幂等 key 必须包含规范化的服务端配置指纹，或让同一同步 key 在配置变化时进入受控 reconcile；不能把配置冲突静默当作并发删除/竞态而忽略。验收应断言模型配置变化产生新版本且旧版本仍可读。

### [P1] 持久退避只写 `next_retry_at`，没有任何路径在到期后重排队

文件：`backend/app/literature_maps/infrastructure/store.py:1540-1565`、`backend/app/literature_maps/infrastructure/store.py:1150-1175`、`backend/app/literature_maps/application/analysis.py:508-520`

retryable 失败在 `finish_analysis()` 中被持久为 `status='failed'` 并写入 `next_retry_at`，聚合队列随后变为 `partial`。`next_queued_analysis_job()` 只查询 `status='queued'` 的子项，而 `run_analysis_queue()` 只在聚合状态为 `active` 时循环；没有定时器、恢复路径或队列运行器把到期的 failed 子项转回 queued。`POST .../retry` 是用户手动动作，不能替代有限退避的自动调度。

可复现证据：模型 runner 第一次抛出 `MapAnalysisError("MAP_MODEL_RATE_LIMITED", retryable=True)` 后，队列为 `partial/failed=1`；再次调用 `run_analysis_queue()` 仍为 `partial/failed=1`，没有第二次模型调用。

修复方向：增加持久、幂等的 due-retry transition（检查 `next_retry_at`、attempt 上限和 queue pause 状态），由受控 scheduler 唤醒；超过上限才停在安全的 retryable failed 状态。补测第一次 transient 失败、到期自动重试、达到上限及暂停期间不重试。

### [P1] 真实 provider 的鉴权/配置错误被归类为普通模型失败，队列不会暂停

文件：`backend/app/literature_maps/application/analysis.py:304-316`；调用链 `backend/app/platform/ollama_direct.py:140-141`

`run_analysis_job()` 只有 `MapAnalysisError` 分支会调用 `_queue_pause_required()`；真实的 `run_chat(... reasoning_effort="off")` 经过 direct Ollama 链路时，HTTP 401/403/429/模型不存在等非 200 响应会由 `ollama_direct.py` 抛出普通 `RuntimeError`。这些异常进入通用 `except Exception`，统一持久为 `MAP_MODEL_FAILED`/`retryable=true`，不会设置 `pause_reason`，也不会把 auth/config 错误安全暂停队列。

修复方向：在现有 provider 边界将 401/403/缺模型/缺配置映射为稳定的 `MAP_MODEL_AUTH_REQUIRED`、`MAP_ANALYSIS_CONFIG_REQUIRED` 等 `MapAnalysisError`；429/网络短暂失败映射为可退避的 transient code。队列失败和 pause 应尽量在同一持久状态转换中完成，避免其他 worker 在两次写之间抢到下一项。

### [P1] 队列 drain 长时间占用共享 2-worker executor，会饿死建图、预览和显式分析

文件：`backend/app/literature_maps/application/runtime.py:185-208`；`backend/app/literature_maps/application/analysis.py:504-525`

生产运行时将建图、预览和摘要分析共用 `ThreadPoolExecutor(max_workers=2)`。每个自动队列只提交一个 `run_analysis_queue()`，而该函数在同一个 worker 中 `while True` 连续调用 `run_analysis_job()`，模型调用期间不会释放 worker。两个地图同时有队列时即可占满两个 worker，其他建图/预览/显式分析只能排队；重复 ensure 还可能继续提交短暂的重复 queue runner。

独立阻塞 runner 的复现结果：

```text
{'queue_workers_in_model': 2, 'other_task_done_before_release': False}
{'other_task_after_release': 'graph/other-task-ran'}
```

修复方向：为摘要队列使用独立受限 executor，或让共享池每次只调度一个 child 并释放/公平轮转；必须增加“两个地图摘要运行时建图任务仍能获得执行槽”的回归测试，不能只依赖 map-level CAS 保证串行。

### [P1] lease 只生成和保存，未用于过期回收或 finish 过期校验

文件：`backend/app/literature_maps/infrastructure/store.py:1481-1503`、`backend/app/literature_maps/infrastructure/store.py:1179-1208`；`backend/app/literature_maps/application/runtime.py:232-238`

`claim_analysis_job()` 写入 300 秒 `lease_expires_at`，但 claim 查询只接受 `status='queued'`，不处理已过期的 running；`finish_analysis()` 只校验 worker token，不校验 lease 是否仍有效。唯一的 `recover_analysis_jobs()` 会无条件把所有 running 重排为 queued，且调用点只在进程启动恢复。若 executor 内 worker 被遗弃而进程仍存活，队列保持 running，`next_queued_analysis_job()` 永远返回空；若没有另一个 recovery，任务无法继续。一个过期但仍持有 token 的 worker 也可在无人重置 token 时完成写入，lease 没有实际 fail-closed 语义。

修复方向：增加一次性、原子、按 `lease_expires_at <= now` 的 recovery/reaper；finish 必须同时验证 token 和 lease（或明确 renew 约定），且恢复不能把仍在有效 lease 内的 worker 无条件抢走。补测过期 lease、有效 lease、重复 recovery、旧 token late finish 和 paused queue 重启。

### [P2] 新增 job 列迁移不在同一事务内，旧库升级无法保证原子回滚

文件：`backend/app/literature_maps/infrastructure/store.py:337-368`（事务从 369 行才开始）

`worker_token`、`lease_expires_at`、`attempts`、`next_retry_at` 的 `ALTER TABLE`、旧 group 清理和 claim 索引创建均在 `BEGIN IMMEDIATE` 之前执行；只有旧幂等修复和唯一索引在 369-379 行事务内。任一中间 DDL/清理失败都会留下部分迁移，随后 schema version 标记还可能未写入。新库测试没有覆盖从 schema 5 的真实旧表打开、失败回滚和再次启动恢复。

修复方向：把 schema 6 的所有增量 DDL、数据修复、索引和 version marker 放入一个可回滚 migration transaction（避免 `executescript` 的隐式 commit），并添加旧库兼容测试：旧表打开、重复初始化、任一步失败后的回滚/重试。

## 已核对且未发现阻塞的部分

- `claim_analysis_job()` 使用带 owner/map/status/running guard 的单条条件 UPDATE；`finish_analysis()` 校验持久 worker token，删除地图或移除节点后的迟到完成不会复活节点。
- `GET /{map_id}/analysis-queue` 只读取现有聚合/子状态；未 ensure 的地图返回零计数，不创建 queue/analysis，也不提交 executor。
- 用户 pause 不更新当前 running child，active/paused 状态持久化；重启恢复路径不会自动唤醒 paused queue。
- owner 通过服务端 `OWNER_ID` 注入，queue command、analysis、map/node 查询均有 owner scope；旧 abstract/full 分析路由和版本读模型在精准测试中保持通过。
- `label_mode` 为可选字段，`update_view()` 只在非空时更新该字段，未覆盖 positions、viewport、filters、layers；旧 view projection 默认 `all`。
- 新测试文件 `tests/literature_maps/test_map_analysis_queue.py` 按能力命名，不含 spec/task 数字。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH / P1 | 5 | block |
| MEDIUM / P2 | 1 | warn |
| LOW | 0 | pass |

Verdict: **BLOCK — 5 个 P1 功能/可靠性问题需修复并复审后才能签署 Task09 后端。** 本轮没有发现新的 CRITICAL 安全问题；不影响上述 P1 门禁判断。

复核日志：`.codebuddy/agent-logs/spec-043/task-09/backend-reviewer/20261024-112735.md`

## 第二轮复审：修复后复核（2026-10-24）

本节追加在首轮 BLOCK 之后，保留首轮发现、复现和结论，不覆盖历史记录。复核依据为开发者追加的“独立 review 修复追加”证据、当前工作区实际代码/测试和以下隔离执行结果。

### 第二轮验证证据

| 检查 | 结果 |
|---|---|
| 队列/分析/存储精准集合（7 个 `tests/literature_maps` 文件） | 退出码 0，**56 passed**，临时根 `/private/tmp/spec043-task09-backend-review2-i0us0K` |
| 运行时受影响集合（4 个 `tests/literature_maps` 文件） | 退出码 0，**45 passed**，同一临时根 |
| `scripts/check_test_layout.py` + `scripts/check_test_naming.py` | 均退出码 0 |
| 变更后端生产文件 `py_compile` | 退出码 0 |
| 指定后端/测试 `git diff --check` | 退出码 0 |
| 实际 provider 错误文本分类烟测（不发起网络） | `HTTP 401/403 -> MAP_MODEL_AUTH_REQUIRED` 且不可重试；`HTTP 404 -> MAP_ANALYSIS_CONFIG_REQUIRED` 且不可重试；`HTTP 429 -> MAP_MODEL_RATE_LIMITED` 且可重试；`HTTP 500 -> MAP_MODEL_FAILED` 且可重试 |

上述两组 pytest 均使用 Task08 隔离约定，将 SQLite、KB/Qdrant、缓存和 basetemp 指向唯一临时根；未启动服务、未调用模型/外网、未访问生产数据，也未运行全量回归。Git 仅用于只读 diff/检查，没有提交、推送或其他写操作。

### 首轮问题逐项状态

#### P1-1 自动 ensure 配置指纹：PASS

`service.py:1205-1217` 将 `analysis_config_fingerprint()` 纳入自动同步 key，`analysis.py:84-94` 以规范化服务端模型配置生成指纹；`test_automatic_enqueue_reconciles_after_model_configuration_changes` 断言模型从默认值切换后得到版本 2，旧版本仍保留。此前的静默 `ValueError("idempotency conflict")` 路径已去除（当前只将并发删除作为 `LookupError` 竞态处理）。

#### P1-2 持久 due retry/暂停：PASS（当前范围）

`store.py:1151-1207` 在写事务中按 `next_retry_at`、队列暂停状态和 attempt 上限原子 promote；`analysis.py:605-664` 由一次性 Timer 唤醒已有 queue executor，进程重启由 `analysis.py:704-738` 根据持久 deadline 重建唤醒。`test_persisted_retry_deadline_wakes_existing_queue_executor` 使用真实 `ThreadPoolExecutor`（仅将重试延迟注入为 0 以避免等待）验证第二次调用；暂停和 attempts=3 上限也在同一集合通过。该结论不覆盖 lease 到期 reaper，见 P1-5。

#### P1-3 真实 provider 状态分类/原子暂停：PASS（静态边界 + 精准烟测）

`analysis.py:752-777` 同时读取异常的 status 属性、response status 和真实 direct provider 的错误文本；`ollama_direct.py:140-141` 的非 200 `RuntimeError("...HTTP NNN...")` 可被该分类器稳定归类。无网络的实际错误文本烟测覆盖 401、403、404、429、500；队列测试还验证 401 原子置 `paused/MAP_MODEL_AUTH_REQUIRED`、429 保持 partial 且可退避。`store.py:1645-1703` 在同一事务内完成 child 失败、错误码和队列暂停，未发现 claim 窗口。

#### P1-4 executor 公平性：PARTIAL，仍 BLOCK

队列 drain 每次只运行一个 child（`analysis.py:538-564`），生产运行时也已将队列放到独立单槽 executor（`runtime.py:186-213`）；因此两个阻塞摘要队列不再占用通用建图/预览 executor，当前 `test_queue_children_release_shared_slots_for_other_map_work` 通过。

但生产 wiring 同时把旧显式 `abstract|full` 分析的 `executor` 和自动队列 `queue_executor` 都指向该单槽 `_analysis_executor`（`runtime.py:190-213`）。这仍会让一个阻塞的自动摘要占住唯一槽位，另一张地图的显式分析只能排队：实际使用同样的单槽 `ThreadPoolExecutor` 和阻塞模型 runner 复现为 `explicit_before_release: pending`，释放后才变为 `completed`。这保留了首轮 P1-4 对“显式分析不应被自动队列饿死”的未解决部分；应将显式分析恢复到通用受限池，队列继续使用独立池，并保持数据库 map-wide claim 串行约束。

#### P1-5 lease/recovery/late finish：PARTIAL，仍 BLOCK

token/CAS 和 late finish 的 fail-closed 已修复：`store.py:1645-1669` 同时检查 worker token、可解析且未过期 lease，并在 UPDATE CAS 中再次检查 `lease_expires_at > now`；`store.py:1252-1300` 只回收已到期（或旧库 NULL）lease，保留有效 lease，测试也覆盖有效/过期 lease、重复 recovery、旧 token 和 paused queue。

但是当前运行时没有存活进程内的 lease reaper，也没有 renew：

- `analysis.py:549` 和 `analysis.py:648` 只调用 `requeue_due_analysis_jobs()`，该方法仅处理 failed child 的 `next_retry_at`，不处理 expired running child。
- `analysis.py:704-738` 的 `recover_analysis_jobs()` 只从显式 `recover()` 调用；唯一生产调用在 `main.py:68-73` 的启动 lifespan。进程保持存活而 worker 线程丢失时没有到期唤醒路径。
- `run_analysis_job()` 忽略 lease 过期后的 `finish_analysis()` 返回 `None`，所以模型调用超过 300 秒或 direct Ollama 300 秒 timeout（`ollama_direct.py:250-260`）后，child 仍保持 `running`，聚合队列也永久显示 `running`，不会进入有限重试。

无模型 live-like 复现（仅临时把 `_ANALYSIS_LEASE_SECONDS` 设为 `-1` 以免等待 300 秒）实际调用 `ensure -> _schedule/run_analysis_queue -> run_analysis_job -> finish_analysis`，结果为：

```text
{'queue': {'state': 'active', 'counts': {'total': 1, 'completed': 0, 'queued': 0, 'running': 1, 'failed': 0, 'skipped': 0}}, 'analysis': 'running'}
```

这不是只调用 `recover()` 的测试替代品，而是实际 queue runner 在 lease 已过期时的生产调用链。需要增加按到期时间的一次性原子 reaper/唤醒（或明确的 bounded renew 协议）；过期 worker 的回调必须保持 fail-closed，同时将 child 恢复为可有限重试状态。当前 300 秒 lease 无 renew 且无 live reaper，不能签署 Task09 后端。

#### P2 schema 6 迁移原子性：PASS

`store.py:339-383` 将 node/preview/job 增量 DDL、旧 group 修复、claim index、legacy idempotency repair、唯一 index 和 schema marker 全部置于同一 `BEGIN IMMEDIATE`/`COMMIT`；失败统一 rollback。`test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry` 在持久 SQLite 文件上模拟 schema 5（移除四个 schema6 job 列、回退 version marker），注入 repair 故障后确认列/index/version 均未落库，解除故障后升级到 schema 6 且可重复 initialize。未发现本轮 schema 迁移阻塞。

### Timer 生命周期附注

`analysis.py:633-641` 的 retry Timer 只记录在 service 实例内；`runtime.py:247-255` shutdown 时关闭 executor，但没有 cancel/clear 这些 Timer。回调会在 `analysis.py:658-662` 捕获已关闭 executor 的 `RuntimeError`，因此不会复活旧 executor，但可能在 runtime reset 后继续改写持久 retry 状态且无法把任务交给新 executor。生产 lifespan 当前没有调用 `reset_literature_map_runtime()`，故将其记为与 P1-5 同一调度生命周期的 P2 风险，不另计首轮 P1；若保留 runtime reset/热重载路径，应在 shutdown 中取消并清空 Timer，或让回调解析当前 runtime。

### 第二轮结论

| Severity | 首轮状态 | 第二轮状态 |
|---|---:|---|
| P1-1 配置指纹 | block | **PASS** |
| P1-2 due retry | block | **PASS** |
| P1-3 provider 分类/暂停 | block | **PASS** |
| P1-4 executor 公平性 | block | **PARTIAL / BLOCK**：显式分析仍与队列共享单槽 |
| P1-5 lease recovery | block | **PARTIAL / BLOCK**：只有启动 recovery，无存活进程 reaper/renew |
| P2 schema 6 migration | warn | **PASS** |

**第二轮结论：BLOCK。** 当前精确测试共 101 passed，不能据此进入部署里程碑；必须先修复显式分析 executor 隔离和 lease 到期 live recovery，再进行一次集中复审。首轮 BLOCK 记录保持不变。

## 第三轮复核：第二轮 BLOCK 修复（2026-10-24）

本节追加第二轮复现与最小修复证据，保留前两轮历史结论；外部 queue API 字段、路由路径和 schema version 未变化。

### 红测复现

在修复前新增能力测试并运行：

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py -k 'runtime_explicit_analysis or expired_queue_lease or shutdown_cancels_retry'
退出码 1，3 failed，18 deselected
```

逐项复现为：

- `test_runtime_explicit_analysis_uses_general_slot_while_queue_child_runs`：自动摘要占用 `_analysis_executor` 单槽时，另一张地图的显式摘要在释放前未启动。
- `test_expired_queue_lease_wakes_real_scheduler_after_worker_loss`：真实 `ensure -> queue dispatch -> claim -> worker loss` 链路在 lease 到期后没有第二次调用，子项永久保持 running。
- `test_analysis_service_shutdown_cancels_retry_wakeup_without_late_store_write`：service 没有 shutdown 定时器清理接口，旧 retry timer 无法被取消。

### 最小修复与绿证据

#### P1-4 显式分析与自动队列 executor 隔离：PASS

`runtime.py` 现在将显式 `MapAnalysisService.executor` 接回通用 2-worker executor，将 `queue_executor` 保持为独立单槽；队列仍由原有持久状态和 dispatch guard 调度，没有新增第二套队列状态机。真实阻塞模型 runner 测试证明自动队列持有单槽期间，另一张地图显式摘要已启动。

#### P1-5 存活进程 lease 到期 recovery：PASS

`MapJob` 增加仅供内部调度使用的持久 `lease_expires_at` 投影字段（`to_dict()` 不暴露）；claim 后按服务端 lease deadline 注册一次性 daemon timer。到期 callback 在 shutdown 锁内调用已有原子 `recover_analysis_jobs()`，复用原 queue/explicit executor 分派；有效 lease 不抢占，过期 token 的 finish 仍 CAS fail-closed。达到 `_ANALYSIS_MAX_ATTEMPTS` 的过期 running child 原子落为安全 `MAP_ANALYSIS_LEASE_EXPIRED` failed，队列进入 partial，不会留下不可领取的 queued 项。

`test_expired_queue_lease_wakes_real_scheduler_after_worker_loss` 使用真实 queue runner 和模拟 worker 丢失验证第二次模型调用；`test_expired_lease_at_attempt_cap_becomes_terminal_failure` 验证上限路径；既有 `test_analysis_finish_fails_closed_after_lease_expiry` 保留迟到完成 fail-closed 证据。

#### Timer shutdown 生命周期：PASS

`MapAnalysisService.shutdown()` 设置实例关闭闸门、取消并清空 retry/lease timers；`reset_literature_map_runtime()` 在关闭 executor 前调用它。timer callback 在同一锁下检查关闭状态，executor 关闭竞态仅保留持久 queued 状态供新实例 recovery，不对旧服务再写库。`test_analysis_service_shutdown_cancels_retry_wakeup_without_late_store_write` 与 `test_analysis_service_shutdown_cancels_lease_reaper_without_late_recovery_write` 验证 deadline 到期后旧实例没有 requeue/recovery 写入。

### 第三轮精确验证命令与退出码

| 检查 | 结果 |
|---|---|
| 新增三条红测（修复前） | 退出码 1，3 failed |
| 队列能力全量（含 attempt cap、executor、lease、shutdown） | 退出码 0，**23 passed** |
| 分析/存储受影响集合（7 个文件） | 退出码 0，**61 passed** |
| runtime 受影响集合（4 个文件） | 退出码 0，**45 passed** |
| `scripts/check_test_layout.py` + `scripts/check_test_naming.py` | 均退出码 0 |

本轮仍未启动服务、调用模型/外网、访问生产 DB、执行下载导入链或全量回归；没有修改 frontend。建议独立 reviewer 复核真实 timer 到期路径后再更新本节结论。

## 第四轮独立最终窄复审：shutdown 旧实例写入竞态（2026-10-24）

开发者在本报告前一节追加的第三轮说明不是本 reviewer 的签字。本节基于当前工作区实际代码、独立临时数据根和真实 runtime 调用链给出最终结论；前述首轮/第二轮 BLOCK 历史均保留。

### 已独立确认的修复

- **显式分析与自动队列槽位：PASS。** `backend/app/literature_maps/application/runtime.py:186-217` 创建通用 `max_workers=2` executor 与独立 `max_workers=1` queue executor，并将 `MapAnalysisService.executor` 接回通用池、`queue_executor` 接到单槽池。`test_runtime_explicit_analysis_uses_general_slot_while_queue_child_runs` 用真实 runtime、阻塞 runner 和事件同步确认队列 child 阻塞时另一地图显式分析已启动。
- **存活进程 lease reaper：PASS。** `backend/app/literature_maps/application/analysis.py:293-309,709-752` 在真实 claim 后按持久 `lease_expires_at` 注册一次性 Timer；到期 callback 在 shutdown 同一把锁内调用 `recover_analysis_jobs()`，再重派 queue/explicit job。`test_expired_queue_lease_wakes_real_scheduler_after_worker_loss` 走 `ensure -> queue dispatch -> claim -> simulated lost worker -> Timer -> recovery -> second runner`，没有直接调用 `recover()` 代替运行时路径；仅将 lease 常量临时设为 `-1` 缩短等待，并在首个 claim 后恢复为 300 秒。
- **attempt cap/late finish：PASS。** `backend/app/literature_maps/infrastructure/store.py:1282-1366` 对到期 running child 做条件 recovery；达到上限原子落为 `MAP_ANALYSIS_LEASE_EXPIRED` failed，未达到上限回到 queued；`store.py:1709-1735` 的 worker token + 未过期 lease 条件 UPDATE 继续拒绝迟到完成。相关 queue/lifecycle 精准用例通过。
- **Timer callback shutdown：PASS。** `backend/app/literature_maps/application/analysis.py:83-97,679-707,738-752` 取消/清空 retry 与 lease Timer，callback 的持久转换与 shutdown 共用锁；`backend/app/literature_maps/application/runtime.py:250-264` 在关闭两个 executor 前调用 service shutdown。两个 shutdown 测试在 deadline 到期后均观察到旧 retry/recovery callback 没有写库。

### 新发现的 P1：worker final finish 可越过 shutdown 闸门

**复现：BLOCK。** `backend/app/literature_maps/application/analysis.py:343-377` 的成功与异常分支只是分别读取 `self._shutdown`，随后调用 `store.finish_analysis()`；该检查与持久写之间没有持有 `self._queue_dispatch_lock`。`shutdown()` 在 `analysis.py:91-97` 只在另一处持锁设置 `_shutdown`，而 `reset_literature_map_runtime()` 在 `runtime.py:250-264` 随后以 `wait=False` 关闭 executor，因此正在收尾的旧 worker 仍可能在 reset 返回后写同一 SQLite。

独立复现使用临时 SQLite `/private/tmp/spec043-task09-backend-review3-Q1zJJE/runtime-race.sqlite3` 和真实 `get_literature_map_service()` runtime（model runner 仅返回内存中的 `ChatRun`，不调用模型/网络）：

1. 显式 analysis 已由通用 executor claim 并运行到 `finish_analysis` 入口；临时 wrapper 用 Event 暂停其真正的事务写入。
2. 调用生产 `reset_literature_map_runtime()`，其确实先执行 `analysis.shutdown()`，再关闭 executor 并清空 runtime globals。
3. 释放 wrapper，使旧 worker 继续调用原始 `finish_analysis()`。
4. 读取同一临时 DB，结果为 `analysis.status == "completed"`；也就是 shutdown/reset 返回后旧实例仍完成了持久写。等价的直接 `service.shutdown()` 复现同样结果。

这不是 Timer callback 的假阳性：Timer 测试验证的是 callback 写入已被 shutdown 锁挡住，而这里是已进入 final-CAS 前后的 worker 竞态。只要 reset/热重载与模型收尾并发，旧结果可能在新 runtime 接管后写入；现有 23/61/45 通过集合没有覆盖这个窗口。

修复建议（交给 backend-dev，不在本轮代改）：将每个 `finish_analysis()` 调用的 `_shutdown` 检查与调用本身放进 `self._queue_dispatch_lock`，使 shutdown 要么先关闸、阻止 finish，要么等待已经开始的短事务完成后再返回；并增加上述 barrier 回归，断言 reset 返回后旧 worker 不再写库。另可给 `analysis.py:797-805` 的 `_schedule_waiting_analysis()` 增加 shutdown 检查，避免旧 worker 在 reset 后向已关闭 executor 提交任务；该项当前是非持久写的次要清理，不改变本次 P1 判断。

### 本轮独立验证证据

| 检查 | 结果 |
|---|---|
| `tests/literature_maps/test_map_analysis_queue.py` | 退出码 0，**23 passed** |
| 分析/存储精准集合（7 个 `tests/literature_maps` 文件） | 退出码 0，**61 passed** |
| runtime 受影响集合（4 个 `tests/literature_maps` 文件） | 退出码 0，**45 passed** |
| 生产文件 `py_compile`、`check_test_layout.py`、`check_test_naming.py`、指定 `git diff --check` | 均退出码 0 |
| runtime reset 旧 worker final-finish barrier 烟测 | **失败（发现 P1）**：reset 后状态仍为 `completed` |

以上 pytest 使用 `/private/tmp/spec043-task09-backend-review3-Q1zJJE` 隔离 SQLite/缓存/KB 根；未启动服务、未访问生产 DB、未调用外部模型/API、未运行全量回归，未修改业务代码或测试代码。

### 本轮独立结论

**BLOCK。** 原剩余两项 P1、lease live reaper、attempt cap/late finish 及 Timer callback 生命周期已通过独立窄复审；但 shutdown/runtime reset 仍存在可复现的旧 worker 持久写 P1。必须先修复 final finish 与 shutdown 的原子互斥并补 barrier 回归，再集中复审；不能以当前 23+61+45 测试通过签署 Task09 后端或进入部署里程碑。

## 第五轮窄修：final finish 与 shutdown 原子互斥（2026-10-24）

本节只记录上一节新增 P1 的红绿证据；此前已 PASS 的项目不重做语义变更，外部 queue API/字段保持不变。

### 红测复现

新增 barrier 用例后，旧实现运行：

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py -k 'runtime_reset_and_final_analysis_finish_are_atomic'
退出码 1，1 failed，23 deselected
```

旧实现中 `finish_analysis()` wrapper 已进入并阻塞时，`reset_literature_map_runtime()` 可先返回；释放 wrapper 后旧 worker 继续把 analysis 写成 `completed`，复现 reviewer 的 reset-after-finish barrier 竞态。

### 最小修复

`MapAnalysisService._finish_analysis_if_active()` 统一封装成功与 error finish：仅在最终短持久 CAS 阶段获取 `_queue_dispatch_lock`，锁内同时检查 `_shutdown` 并调用 `store.finish_analysis()`；模型生成、全文证据检查和 source re-check 均不持锁。`shutdown()` 若先获得锁则阻止旧 worker 写入；若 finish 先获得锁，则 reset 等待该短事务完成后再返回。成功和 `MapAnalysisError`/provider error 路径共用同一闸门。

### 绿证据

`test_runtime_reset_and_final_analysis_finish_are_atomic` 以 success/error 两个参数化场景通过：reset 不会在 final finish 持锁事务完成前返回，旧 worker 不会在 reset 返回后写 SQLite。

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py
退出码 0，25 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py
退出码 0，63 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api.py
退出码 0，45 passed
```

命名/布局检查、后端 `py_compile` 和指定 `git diff --check` 均退出码 0；未运行服务、模型/网络、生产 DB、全量回归或部署。请主会话安排该单一 P1 的集中窄复审。

## 第六轮独立最终窄复审：final finish 修复（2026-10-24）

作者上一节“第五轮窄修”是交接证据，不是本 reviewer 的签字。本节只复核上一轮新增 reset-vs-final-finish P1 与 `_schedule_waiting_analysis()` shutdown 护栏；先前 executor 隔离、live lease reaper、attempt cap/late finish、Timer callback shutdown、schema6 和其他既有 PASS 结论保持不变，未重跑 63/45 集合。

### 实际代码核对

- `backend/app/literature_maps/application/analysis.py:99-131` 的 `_finish_analysis_if_active()` 是 success、`MapAnalysisError` 和 provider-error 三条路径的唯一 final finish 入口。它在同一 `_queue_dispatch_lock` 临界区内检查 `_shutdown` 并调用 `store.finish_analysis()`；锁只覆盖短 SQLite CAS，不覆盖 `analysis.py:347-376` 的模型调用、全文检索或 source re-check。
- `backend/app/literature_maps/application/analysis.py:91-97` 的 `shutdown()` 也使用该锁设置关闭闸门。因此 finish 先进入时 reset 必须等待短事务完成，shutdown 先进入时 finish 返回而不写，消除了上一轮复现的 reset 返回后旧 worker 写入窗口。
- `backend/app/literature_maps/application/analysis.py:835-856` 的 `_schedule_waiting_analysis()` 在读取 queued jobs 前、每个候选提交前都检查 `_shutdown`；提交与 executor 关闭的剩余竞态捕获 `RuntimeError`。即使提交恰好发生在第二次检查之后，`run_analysis_job()` 的入口/claim 闸门（`analysis.py:327-340`）仍拒绝旧实例 claim，不产生持久写；模型调用不在 lifecycle lock 内。

### 独立 barrier 证据

在 `/private/tmp/spec043-task09-backend-review3-Q1zJJE` 隔离数据根运行：

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py -k runtime_reset_and_final_analysis_finish_are_atomic
退出码 0，2 passed，23 deselected
```

该参数化测试分别覆盖 success 与 `MapAnalysisError`/error finish。wrapper 在真实 executor worker 已进入 `store.finish_analysis()` 前置后阻塞；另一个线程调用真实 `reset_literature_map_runtime()`。测试确认 reset 在 lifecycle lock 释放前不会返回，释放后 `writes_after_reset == [False]`。因此覆盖的不是只调用 helper 的单元路径，而是 runtime reset、executor worker、final finish 三者的实际并发路径。

### 本轮独立结论

**GO（本轮窄复审）。** 新 P1 已以统一 success/error final-CAS 和真实双 barrier 通过；模型生成未持有 lifecycle lock；`_schedule_waiting_analysis()` 已具备 shutdown/closed-executor 护栏，旧实例不会因该路径再 claim/持久写。此前已确认的其余 PASS 项保持有效。未修改业务代码或测试，未启动服务、调用模型/网络、访问生产 DB、运行全量回归或执行部署。

## 第七轮独立 source review：arXiv 指定 ID 作者缩写窄修（2026-10-24）

本节是对作者新增 KB/arXiv 交接记录的独立签字；不重开前述队列/runtime 结论，也不把作者报告中的 19/61 证据直接当作本 reviewer 的签字。本轮只看 `backend/app/paper_discovery/infrastructure/arxiv_adapter.py`、`tests/paper_discovery/test_arxiv_adapter.py`，未改业务代码或测试。

### 代码与边界核对

- `arxiv_adapter.py:18-28` 保留 `AUTHOR_THRESHOLD = 0.80`，新增形状解析只接受带点的一字母缩写（`T.Mei`/`T. Mei`）；完整姓名要求至少两个 token 且 given name 至少两个字符，因此 `Tmei` 不会被当成缩写。
- `arxiv_adapter.py:150-207` 先按规范化全名精确匹配；仅 `expected_arxiv_id is not None` 时构建缩写兼容边，并要求 expected/candidate 两侧各自唯一、逆向也唯一。不同首字母、不同姓氏、同姓多个不同 given-name candidate 均不会因一对多边增加分数。相同的重复全名只折叠为一个身份，不会重复抬高分数。
- `arxiv_adapter.py:222-237,372-380` 的标题搜索仍调用 `allow_abbreviations=False`；只有 `lookup_by_id()` 经过 `expected_arxiv_id` 路径允许缩写，不存在“标题相似即可放宽”的回退。
- `arxiv_adapter.py:251-270` 的指定 ID 门禁仍先校验合法 ID、标题、年份和作者非空；`arxiv_identity_matches()`、title threshold、year gate、`_safe_pdf()` 原逻辑未被放宽。缓存 key 使用大小写折叠但保留原始标点形状/重复项（`author_shape_key`），因此 `T.Mei` 与 `Tmei` 不会共用结果，不需要 schema 迁移。
- arXiv feed 的 exact-ID、标题、年份和 PDF 安全门禁仍在 `arxiv_adapter.py:361-397`；没有修改下载、导入、安全校验或其他来源适配器。

### 独立精准证据

在隔离环境中运行 adapter 专项测试：

```text
./.venv/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py
退出码 0，19 passed in 3.22s
```

测试 fixture 对应指定的官方 arXiv 元数据形状：`1809.07041v1`、`Exploring Visual Relationship for Image Captioning`、2018、`Ting Yao / Yingwei Pan / Yehao Li / Tao Mei`；候选第四作者为 `T.Mei` 时 `lookup_by_id("1809.07041", ...)` 命中。参数化反例覆盖错 title、错 year、错首字母、错姓氏、同姓歧义（`Tao Mei`/`Tim Mei`）和不带点的 `Tmei`；另有标题搜索不放宽和缓存 raw-signature 区分测试。独立私有函数边界烟测也确认同姓多 candidate 的缩写边不唯一时得分为 0，不会错配；重复同一全名只作为一个身份，不会通过重复计数抬分。

静态补充检查：目标 adapter 生产/测试文件 `py_compile` 退出码 0，目标 `git diff --check` 退出码 0。未访问网络或生产数据；HTTP 仅由现有 MockTransport fixture 模拟，未下载或导入论文。

### 本轮独立结论

**GO（source review）。** 指定 arXiv ID 的 `T.Mei` ↔ `Tao Mei` 兼容仅在 exact-ID 路径开启，且保持 `.80` 作者阈值、ID/title/year/PDF 安全门禁；同姓多 candidate、错误首字母/姓氏、歧义和 `Tmei` 均 fail-closed，标题搜索不被放宽，缓存签名区分缩写形状且不需要 schema。原有其他后端 GO 结论保持有效。

## 第八轮独立 KB canonical import 接缝复审（2026-10-24）

作者前一节“KB import_candidate canonical 接缝窄修”是交接证据，不是本 reviewer 的签字。本轮只复核 `backend/app/knowledge_base/application.py` 与 `tests/kb/test_kb_application_boundary.py` 的实际 diff，并补跑该边界文件及 source-mutation 的两个必要精准用例；不重跑此前 37/49 集合、queue/arXiv、全量或部署。

### 实际代码核对

- **canonical 字段可信来源：PASS。** `application.py:354-534` 的 `create_immutable_document()` 仍由服务端生成 UUID、唯一 `stored_name`、`media_type="application/pdf"` 和源文件 SHA-256；候选快照只填展示/来源元数据，不能注入 `document_id`、`source_sha256` 或媒体类型。`import_paper()` 在 `application.py:1246-1364` 只把 `created["document"]` 交给默认 indexer；`application.py:1161-1192,1194-1237` 的 v1/v2 调度改用 `record_id()`，不会再通过重建 `PaperRecord` 丢掉 canonical 字段。
- **owner / project / generation / manifest：PASS。** owner、源 inode/hash 和 generation collection 仍由服务端 `ImportResourceCapability` 及 `_capture_import_generation()` 绑定；默认路径在创建前、索引收尾前后均走 generation binding 检查，v1/v2 继续进入既有 `GenerationBoundIndexPort`。索引收尾调用既有 strict bundle/manifest publisher，随后只用 `patch_knowledge_document()` 允许的状态字段更新；不会覆盖 canonical identity、哈希、媒体类型或 project-association sidecar。新边界用例同时确认新文档的 owner capability、目标 collection、payload/manifest hash，以及既有文档的 generation marker、metadata、manifest 和 project association 均保持。
- **legacy 与来源安全：PASS。** `infrastructure/index.py:384-415,713-751` 对缺 `document_id/source_sha256` 的 legacy record 仍不建立 strict bundle/manifest，只更新兼容状态；新反例确认 `indexed_source_sha256` 不被伪造为 verified。source 在向量写入后发生变化时仍由既有 post-write digest 检查转为 `SOURCE_HASH_MISMATCH`、failed、generation fail-closed；未新增 hash/manifest 旁路。
- **schema/API 边界：PASS。** 生产 diff 只扩展默认 indexer 的输入类型并保留注入式 legacy `PaperRecord` seam；没有新 schema/version、路由字段、下载器或安全校验旁路。测试文件名按能力命名，无 spec/task 编号。

### 独立精准证据

```text
./.venv/bin/python -m pytest -q tests/kb/test_kb_application_boundary.py
退出码 0，8 passed，5 warnings（既有 PyMuPDF deprecation warnings）

./.venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py -k 'source_change_after_vector_write_is_not_verified or parse_source_hash_mismatch_is_normalized_and_published_fail_closed'
退出码 0，2 passed，22 deselected，5 warnings（既有 PyMuPDF deprecation warnings）
```

首组实际覆盖默认 canonical import 的 strict manifest/hash、owner capability、generation marker、既有 metadata/manifest/project 保持，以及缺 hash legacy 不进入 verified/manifest。第二组独立确认来源修改不会被发布为 verified。测试运行只使用 pytest 临时目录和内存 fake client，未访问生产 DB、未调用网络/模型、未启动服务或执行 reindex。

### 本轮独立结论

**GO（本轮 KB canonical import 窄复审）。** 默认 indexer 已真实复用服务端 canonical document mapping，严格 manifest/hash 证据链恢复；注入式 legacy seam 与无 hash fail-closed 兼容保持；owner/project/generation/既有 manifest 未被覆盖，source mutation 仍失败关闭；本轮未发现 P1/P2。此前其他后端 PASS/GO 结论保持有效。root 可按既定计划执行一次既有 reindex 恢复文档，再进行后续实际 full verification；该部署/验证不属于本轮签字。
