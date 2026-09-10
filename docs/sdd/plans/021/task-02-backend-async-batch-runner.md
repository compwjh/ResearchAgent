> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（spec 确认）；当前状态：`待执行`

# Task02 后端：批次入队即返回 + 后台单飞执行 + 启动恢复

## 状态与一句话目标

`待执行`。让 `POST /api/papers/imports`（批量）与 `POST /api/papers/imports/{id}/retry` **不再在请求线程内跑完整批**：创建/重排队后立即返回 `queued` 批次，由后台执行器推进，前端轮询可见逐条状态。

## 背景与前置条件

- 现状：`backend/app/paper_discovery/application/paper_import_batch_service.py:249-251`（`auto_run=True` → `run_batch`）与 `retry_batch`（434-439）都同步等待执行完成；`run_batch`（418-428）内部才用 `ThreadPoolExecutor` 并发。
- 实证：`deploy/run-8123.log:41-44` 中 1 次 imports + 3 次 retry 均为 200，但**没有任何 `GET /api/papers/imports/{id}`** 轮询请求——因为 POST 返回时批次已终态。
- 沿用既有能力：`service.recover_expired_leases`（`service.py:492-495`）用于租约回收；不得新造第二套回收机制。
- 前置：spec-020 / Task06（BUG-04，纯前端相位修复）先行，避免同文件互相覆盖。

## 数据、配置与接口

- `POST /api/papers/imports`（批量）→ 200 + 批次负载，`state=queued`，请求**亚秒级**返回。
- `POST /api/papers/imports/{id}/retry` → 200 + 批次负载（items 回到 `queued`），立即返回。
- `GET /api/papers/imports/{id}` → 契约不变，返回实时逐条状态。
- 新增进程内 `batch_runners: Mapping[batch_id, Future]`（单飞），不得落库、不得跨进程。
- 单篇兼容端点 `_import_single_paper` **不动**（仍同步）。

## 实施步骤与文件边界

**文件边界**：只改 `backend/app/paper_discovery/application/paper_import_batch_service.py`、`backend/app/api/routes_paper.py`、`backend/app/api/common.py`（如需注入执行器）与 `tests/` 下后端测试。不得改 `frontend/**`，不得改 `paper_import_batch_store.py` 的 CAS/租约语义。

1. **先写测试**（TDD）：覆盖"POST 返回即 `queued` 且未完成任何条目""重复触发执行只跑一次（单飞）""20 篇上限仍报错"。
2. 在 `PaperImportBatchService` 引入后台执行器（复用既有线程池语义，不新建第二个线程池；若必须新增，明确容量上限并说明）：
   - `submit_batch(batch_id)`：登记 runner，异步执行既有 `run_batch`；
   - 单飞：若 `batch_runners` 中已有未完成 Future，直接返回，不重复执行。
3. `create_batch`：`auto_run` 语义改为"提交到后台执行器"，立即返回 `queued` 批次（保留 `auto_run` 参数与默认值兼容既有调用与测试）。
4. `retry_batch`：只做"把 failed/waiting_login 条目回到 queued" + 提交后台执行，**不等待**。
5. 启动/首次访问恢复：对仍为 `queued` 且无 runner 的批次触发 `submit_batch`；过期租约复用 `recover_expired_leases`。
6. 路由层：`_create_paper_import_batch` 与 `retry_paper_import_batch` 返回值语义不变（仍是 `_paper_batch_status_payload`），仅不再阻塞。

## 子代理分派

- 角色：`backend-dev`（`hy3`，32k）。
- 最小上下文：本文件 + spec-021 §端点/接口 与 §边界 + `paper_import_batch_service.py` 的 `create_batch`/`run_batch`/`retry_batch`/`recover_expired_leases` 行号范围（206-252、418-446、492-495）+ `routes_paper.py:698-774`。
- 单次范围：≤2 个代码文件、≤150 行；按 AGENTS.md 第 5 条拆分多轮分派。
- 回传：先回传测试结果与代码，再回传说明；必须给日志路径。

## 边界与明确不做

- 不改 store CAS / 并发领用 / 租约语义；不改下载安全策略与 USENIX/DBLP 来源逻辑。
- 不引入 MQ / Celery / Redis；不做跨进程队列。
- 不改单篇端点同步契约；不改别名路径 `/api/papers/import-batches/*`。
- 幂等键冲突行为不变（仍报错，不静默复用旧批次）。

## 验收、风险与回滚

**验收**：
1. `cd backend && python -m pytest -q` 全绿（含新增用例）。
2. `ruff check .` 无新增告警。
3. 接口实测：`curl -X POST localhost:8123/api/papers/imports -d '{...}'` 返回 `state=queued` 且耗时 < 2s；随后轮询 `GET /api/papers/imports/{id}` 能观察到条目状态迁移。
4. 重复 `POST /retry` 同一批次不产生重复执行（以 item `updated_at` 与 go 日志/落盘文件数核对）。
5. 运行时导入成功（**前提：本机只保留一个持有 `data/kb/qdrant` 的实例**）。

**风险**：后台线程异常吞掉 → 批次永久 `queued`。必须在执行包裹 try/except 并把失败落到 item/batch 状态，同时由"启动恢复"兜底。

**回滚**：回退本次 commit；批次数据在 SQLite 中，回滚不影响已入库论文。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、改动文件与行数、日志路径）。
