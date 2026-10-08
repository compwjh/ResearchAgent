# Spec032 Task14：自动导入与恢复接缝审计

> 角色：backend-reviewer（只读 backend/API 审计）  
> 审计时间：2026-10-08（Asia/Shanghai）  
> 分支：`codex/spec032-final-acceptance`  
> 范围：批准计划 → 候选评估 → 自动导入 → `waiting_login`/`failed` → 登录、上传、重试 → 报告新版本与旧版本不可变。  
> 结论：**不通过收口（P1 阻塞，未发现 P0）**。

本报告没有修改生产代码、没有创建 issue、没有登录、没有上传或重试任何用户数据。自然语言“最多 5 篇但计划预算变成 12”的 P1 已由另一交接处理，本报告不修改其报告或实现。

## 1. 结论摘要

代码中已有的能力并非空壳：批准门禁、评估候选白名单、批量导入状态机、候选级 issue、ACM/IEEE 受控浏览器入口、PDF 身份确认、KB 绑定、报告版本插入式存储和同版本不可变冲突均存在；本次定向回归也通过。

但收口所需的两条后端接缝仍不完整：

1. **P1：恢复动作没有接上 Research 续跑和新报告版本。** 登录后的 `resume`、失败项 `retry`、PDF `upload` 只更新导入链接/issue 状态。上传返回 `report_action="generate_new_version"`，但没有实际调用报告生成、创建新版本或恢复受影响步骤。现有报告版本服务本身能生成下一版本，但没有被恢复路由调用。
2. **P1：批次重启恢复仍被进程内快照 gate 限制。** 条目其实已有 SQLite `snapshot_json/snapshot_hash`，`_snapshots` 只是执行便利缓存；但新进程无该缓存时 `maybe_recover_batch()` 直接返回，没有使用可校验的持久快照。批次列表 API 明确只读且不启动恢复，因此某些 queued 批次在重启后可长期保持 queued，不能满足“恢复或明确变为可重试”。

没有证据表明存在 P0 级任意 URL、登录绕过、错误 PDF 静默入库或旧报告被覆盖；相反，身份不确定会进入人工确认，waiting_login 不允许走 failed-only retry，报告同版本内容变化会被拒绝。

## 2. 代码完成与真实证据缺口

### 2.1 已有代码能力（可视为完成的局部契约）

- `backend/app/research/application/orchestrator.py:1881-1923` 在自动导入前检查持久化计划批准、取消状态和批准记录；`backend/app/research/application/orchestrator.py:1925-1957` 只在批准后调用 `ApprovedPlanAutoImporter`。
- `backend/app/research/application/acquisition.py:542-603` 将评估后持久化的 selection 交给 `ResearchAcquisitionService`，并用现有 `PaperImportBatchService` 创建批次；候选身份不确定时写入 `waiting_identity` issue，不把它误当成下载成功。
- `backend/app/research/application/acquisition.py:292-419` 把批次条目投影为 `ResearchDocumentLink`、`AcquisitionEvent` 和候选级 `AcquisitionIssue`。`waiting_login` 的动作是 `login/resume/upload`，`failed` 的动作是 `retry/upload`，状态语义已分开。
- `backend/app/api/routes_paper.py:1134-1207` 提供受控 headed-browser 登录和续传；`backend/app/api/routes_paper.py:1210-1232` 的单项 retry 复用 store 的 `failed → queued` 迁移，不能把 waiting_login 当 failed 重试。
- `backend/app/api/routes_paper.py:1347-1412` 复用 canonical KB 上传，校验文件存在、身份确认和 mismatch；成功后绑定 `ResearchDocumentLink`、记录上传事件并关闭 issue。
- `backend/app/research/infrastructure/research_store.py:5943-5979` 的 `save_research_report()` 是 insert-only；`backend/app/research/application/report_generation.py:216-247` 通过 `next_report_version()` 生成新的 immutable report row。`ReportDeliveryService` 在 `backend/app/research/application/report_synthesis.py:601-643` 对同版本内容变化返回 `ARTIFACT_IMMUTABLE_CONFLICT`。

### 2.2 确定未接通的代码接缝

#### P1-A：恢复动作没有生成新版本，也没有续跑任务

`backend/app/api/routes_paper.py:1255-1298` 的 `_refresh_issue_links()` 只创建 `ResearchAcquisitionService` 并读取 `acquisition.status(task_id)`；`login/resume/retry` 成功后没有调度 Research runner、evidence matrix 重建或 report generation。

`backend/app/api/routes_paper.py:1387-1408` 的 upload 成功路径只写入 document link、事件、manual resolution，随后返回：

```json
{
  "document_id": "...",
  "research_task_ids": ["..."],
  "report_action": "generate_new_version"
}
```

这里的 `report_action` 是提示字段，不是队列、版本号、报告 ID 或报告 URL。代码中没有同一路径对 `ReportGenerationService.generate()` 或 `ReportDeliveryService.deliver()` 的调用。

此外，agent 主链在 `backend/app/research/application/orchestrator.py:1778-1831` 先交付报告，随后才在 `:1866-1869` 调用自动导入。这样即使本轮 PDF 导入成功，也不会把导入后的全文证据自动带入同一轮已经交付的 artifact；修复一个 issue 后若仍使用原 `plan_version`，又会触发报告 artifact 的同版本不可变冲突。必须由受控恢复服务明确推进 report version，并只续跑受影响步骤。

#### P1-B：重启后的 queued 批次没有可靠的快照恢复出口

- `backend/app/paper_discovery/application/paper_import_batch_service.py:179-190` 将 `_snapshots`（执行便利缓存）和 issue recorder 放在进程内字典；条目的 hash-verified `snapshot_json` 另已落在 SQLite，并由 `:398-475` 的 `_snapshots_for()` 支持新进程读取。
- `:773-787` 的 `maybe_recover_batch()` 在 `batch_id not in self._snapshots` 时直接返回。
- `:948-979` 的 `list_batches()` 明确是只读投影，不检查或启动 runner；`GET /api/papers/imports/{batch_id}` 虽调用 `maybe_recover_batch()`（`backend/app/api/routes_paper.py:1015-1024`），但新进程仍没有 snapshot 可供提交。
- Research acquisition 的 `_sync()`（`backend/app/research/application/acquisition.py:306-320`）会尝试再次提交 queued 批次；若绕过 `maybe_recover_batch()` 进入 runner，`_snapshots_for()` 可以读取持久快照，但批次列表刷新本身仍可一直展示 queued。应让 recovery gate 使用现有 hash-verified 持久快照，或在无法恢复时将条目明确转成稳定可重试状态，不能静默保持 queued。

这是静态边界缺陷；本次只读运行数据没有 queued 批次，因此没有将“可能长期 queued”误报成已在线复现。

## 3. 当前运行服务的只读证据

以下请求均为 `GET`，未触发 login、resume、retry、upload 或其他业务写入：

| 请求 | 结果 | 判定 |
|---|---|---|
| `GET http://127.0.0.1:8000/api/papers/issues?status=open&limit=20` | HTTP 200，`{"issues":[],"count":0}` | 当前没有可直接操作的 open Research issue |
| `GET /api/papers/imports?active=false&recent=true&limit=20` | HTTP 200；包含批次 `1a76e369-c638-4f2c-a430-42552a1e7012`，1 项 `waiting_login/LOGIN_REQUIRED`，以及 `83846ea1-0178-421a-bc8b-2ea5d8b7a0de` 等历史 `failed/partial_success` 批次 | 批次快照可读；不等于任务级 issue 恢复闭环 |
| `GET /api/papers/imports/1a76e369-c638-4f2c-a430-42552a1e7012` | HTTP 200，条目仍为 `waiting_login` | 历史批次状态可读；该批次没有被拿来伪造 issue 或执行登录 |
| `GET /api/papers/browser/health` | HTTP 200，`available=true`，`supported_sites=["acm","ieee"]` | 受控登录入口具备运行条件，但尚未执行用户登录 |
| `GET /api/research-sessions/670adeba6ebb4adfb45f413e093cc3df` | HTTP 200，计划 approval 为 approved，任务为 `partial`，`artifacts=[]` | 有真实批准计划，但没有报告 artifact 证据 |
| `GET /api/research-tasks/7fc66400a3f75df789b62e293aa80ff9/acquisitions` | `BATCH_NOT_FOUND` | 该已有任务没有可用自动导入批次 |
| `GET /api/research-sessions/670adeba6ebb4adfb45f413e093cc3df/artifacts` | HTTP 200，`artifacts=[]` | 不能宣称真实报告产物已生成 |

因此，历史批次读取得到的是“状态持久化读取”证据，不是“自然语言 Intake → 计划批准 → 候选评估 → 自动导入 → 报告产物”的成功证据。无任务绑定的历史 waiting_login 批次不能用于人工恢复验收。

## 4. 定向测试证据

执行命令：

```text
.venv/bin/python -m pytest -q \
  tests/research/test_candidate_acquisition_integration.py \
  tests/research/test_report_generation.py \
  tests/research/test_report_synthesis_contract.py \
  tests/research/test_research_plan_approval_contract.py \
  tests/paper_discovery/test_paper_issue_recovery.py \
  tests/paper_discovery/test_approved_plan_auto_import.py \
  tests/paper_discovery/test_acquisition_bridge.py \
  tests/paper_discovery/test_acquisition_snapshot_refresh.py \
  tests/paper_discovery/test_paper_import_batch_api.py \
  tests/paper_discovery/test_paper_import_batch_service.py \
  tests/paper_discovery/test_paper_import_batch_store.py
```

结果：退出码 `0`，`142 passed in 3.92s`。

测试覆盖和缺口：

- `test_candidate_acquisition_integration.py` 证明固定 SQLite 候选中一项 `completed`、一项 `waiting_login`，并产生一个 task-scoped issue；不访问真实 PDF、浏览器或报告服务。
- `test_paper_issue_recovery.py` 证明重启后的 acquisition status 可投影 issue、waiting_login 不能 retry、resume/retry resolution 可记录，及 store 层 upload 绑定；其中 `test_manual_upload_resolution_closes_issue_without_rewriting_report` 明确只验证“不改写旧报告”的存储动作，没有验证生成新版本。
- `test_report_generation.py` 和 `test_report_synthesis_contract.py` 分别证明独立的 next-version、同版本冲突、artifact replay 和 immutable owner scope；没有 issue recovery → report v+1 的集成断言。
- 仓库内没有 `report_action` 的测试断言。因此，当前测试绿只能证明各局部契约，不足以证明恢复后的新报告版本接缝。

## 5. 当前真实 API E2E 验收方案（只给步骤，本轮未执行写操作）

该方案应在自然语言预算 P1 修复并以新的 `run_id` 重跑；不要批准当前已有的 `target_paper_count=12` 计划，也不要复用历史任务。服务地址按当前部署为 `http://127.0.0.1:8000`。

### 主路径：自然语言 Intake → 批准 → 评估 → 自动导入 → 产物

1. **自然语言 Intake。**

   `POST /api/conversations/messages`，发送真实用户语句，例如“做一次 USENIX Security 2024 的安全方法研究，最多选择 1 篇论文，生成中文 Markdown 报告并使用行内引用”。保存 SSE 中的 `conversation_id`、`research_session_id`、`plan.version`、`plan.output_hash`。等待 `done.status=completed`，并断言计划显示的 `target_paper_count` 等于用户明确上限。

2. **批准持久化计划。**

   `POST /api/research-sessions/{research_session_id}/commands`：

   ```json
   {
     "command": "approve_plan",
     "subject_version": 1,
     "scope_json": {"plan_version": 1, "output_hash": "<SSE 中的 output_hash>"},
     "idempotency_key": "acceptance:<run_id>:approve-v1"
   }
   ```

   保存返回的 `research_task_id`，随后只轮询 owner-scoped 的 session/task/events 读取接口。

3. **候选评估。**

   轮询 `GET /api/research-sessions/{id}`、`GET /api/research-tasks/{task_id}` 和 `GET /api/research-tasks/{task_id}/events?after_seq=0`，等待搜索和 `evaluate_papers` 工作项有终态、selection 已持久化。候选 ID 必须来自服务端搜索快照，不在请求中注入 URL 或伪造 candidate。

4. **批准计划自动导入。**

   轮询 `GET /api/research-tasks/{task_id}/acquisitions`。成功条件是批次有稳定 `batch_id`，每个本轮选中的条目为 `completed`，document link 为 `completed`，没有 open issue，并且返回的 `paper_id/document_id` 可追溯到本任务。若出现 `waiting_login` 或 `failed`，转入下节受控恢复，不把 partial 当成功。

5. **报告产物与版本证据。**

   在 acquisition 达到预期终态后读取 `GET /api/research-sessions/{research_session_id}/artifacts`；每个 artifact 用返回的下载入口 `GET /api/research-sessions/{id}/artifacts/{artifact_id}/download?mode=inline` 读取。记录 `batch_id`、document IDs、artifact IDs、report version、非空 Markdown/HTML/citation manifest 和产物路径。当前代码若只返回 `report_action`、没有新 artifact，必须判定 P1 失败，不能人工补写为成功。

该流程的关键是“同一 run 的真实 ID 链”必须贯通：自然语言 message → session/plan → approval → task → evaluator selection → import batch/item → KB document → artifact。离线固定 SQLite 集成测试不能替代这条链。

## 6. 受控失败恢复方案与精确入口

只对第 5 步中真实生成且带 `research_task_id` 的 open issue 操作。当前历史批次 `1a76e...` 没有对应 issue，不能直接拿来做上传或登录演示。

### `waiting_login`：登录后继续

1. `GET /api/papers/issues?task_id={task_id}&status=open`，确认 issue 的 `reason_code=LOGIN_REQUIRED`、动作包含 `login/resume/upload`。
2. **精确登录入口：** `POST /api/papers/issues/{issue_id}/login`。服务会返回 `status=opened`、`site=acm|ieee`，并在服务端 headed browser 打开对应文章页面；用户只在这个受控页面完成 ACM/IEEE 登录，不向 API 传凭据。
3. 登录完成后，`POST /api/papers/issues/{issue_id}/resume`。该路径内部对应 `POST /api/papers/import-items/{item_id}/resume`，只续跑受影响条目。
4. 轮询 `GET /api/papers/imports/{batch_id}` 和 `GET /api/research-tasks/{task_id}/acquisitions`，等待 item/document link 完成，再确认 issue 变为 resolved。
5. **当前缺口：** 以上步骤到此只证明导入恢复；当前实现不会生成 report v+1。只有修复 P1-A 后，才可继续断言新版本 artifact 出现且旧版本仍可按旧 version 读取。

### `failed`：只重试失败项

1. 确认 issue 动作包含 `retry`，然后 `POST /api/papers/issues/{issue_id}/retry`。waiting_login issue 走此入口必须得到稳定的 `ISSUE_ACTION_NOT_ALLOWED`，不能偷换状态。
2. 轮询同一 `batch_id`；完成则按上面的 issue/acquisition/artifact 验收，仍失败则保留错误码并转人工上传，不循环制造新 batch。

### 人工上传：身份确认后复用 KB

1. 先确认候选标题/作者/DOI 与 PDF 身份，错误文件必须先被 `IDENTITY_MISMATCH` 拒绝；身份不确定时先得到人工确认。
2. 使用真实正确 PDF，调用：

   ```text
   POST /api/papers/issues/{issue_id}/upload?identity_verdict=confirmed&identity_confirmed=true
   Content-Type: multipart/form-data
   file=<真实 PDF>
   ```

3. 当前成功响应会给出 `document_id`、`research_task_ids` 和 `report_action="generate_new_version"`，并关闭 issue。它**不会**在当前实现中实际生成新报告；验收修复后应新增明确的 queued/completed report action、`report_version = old + 1` 和可读 artifact。
4. 修复后的最终断言：`GET /api/research-sessions/{id}/artifacts?report_version=old` 内容/hash 不变；`report_version=old+1` 有新 Markdown/HTML/citation manifest，且新版本记录了新 document/evidence。重复上传或重复恢复不得创建重复 KB 文件或重复报告版本。

### 服务重启恢复

在一个真实批次处于非终态时重启服务，然后只读 `GET /api/research-tasks/{task_id}/acquisitions`、`GET /api/papers/imports/{batch_id}` 和 issue 列表。成功条件是已完成项保持完成，queued/租约过期项被恢复或明确变成带稳定错误码的可重试状态；不能只看到 queued 而没有下一步。当前 P1-B 必须先修复或至少把 queued 明确标成 retryable，才可将该案例签为通过。

## 7. 最小 backend-dev 分派建议

### P1-A：恢复→续跑→报告新版本

- 最小文件范围：
  - `backend/app/api/routes_paper.py`
  - `backend/app/research/application/acquisition.py`（或新增单一 recovery application service；禁止第二套导入状态机）
  - `backend/app/research/application/report_generation.py` / `report_synthesis.py`（按既有 canonical service 接线）
  - 需要时 `backend/app/research/infrastructure/research_store.py` 的 durable recovery/outbox 字段
- 定向测试：
  - `tests/paper_discovery/test_paper_issue_recovery.py`：真实 route seam 断言 login/resume/retry/upload 只处理对应 issue，上传成功后产生可重试/已排队的报告动作，waiting_login 仍拒绝 retry。
  - 新增 `tests/research/test_report_recovery_versioning.py`：旧 artifact/report v 保持 hash 不变，修复后只插入 v+1；重复恢复幂等，不重复 KB 文档/报告版本。
  - `tests/research/test_candidate_acquisition_integration.py`：将现有离线 completed + waiting_login 集成样本扩展到“恢复后 document link + 新 report version”断言（仍不宣称真实网络成功）。

### P1-B：重启后的批次明确恢复或可重试

- 最小文件范围：
  - `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - `backend/app/api/routes_paper.py`（列表/详情刷新语义保持一致）
- 定向测试：
  - `tests/paper_discovery/test_paper_import_batch_service.py`：新 service 实例读取旧 queued snapshot 后能恢复，或原子地变成 `IMPORT_INTERRUPTED`/retryable；不得静默保持 queued。
  - `tests/paper_discovery/test_paper_import_batch_api.py`：`GET /api/papers/imports` 与详情 GET 的重启语义一致，单飞恢复不重复启动。
  - `tests/paper_discovery/test_acquisition_snapshot_refresh.py`：Research acquisition status 在重启后仍能投影 item/issue，且失败可以沿既有 retry 路径继续。

本审计不需要 frontend-dev；自然语言预算 P1 继续由已分派的另一 backend 交接处理。上述两个 P1 修复并通过新的真实 API E2E 前，Spec032 不应转为 `已完成`。

## 8. 审计产出与状态

- 业务代码：未修改。
- 只读 API：issue、batch、browser health、session、task、artifact 均按上文执行；未执行任何写接口。
- 定向回归：`142 passed`，退出码 `0`。
- P0：`0`。
- P1：`2`（恢复后报告新版本/任务续跑；重启 queued 可恢复性）。
- 收口判定：`BLOCKED`，等待 backend-dev 修复并由 tester 以新 `run_id` 完成真实 E2E、人工恢复和新旧报告版本证据。
