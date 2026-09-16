# Spec029 Task06 后端/运行时验收审计

## 结果状态

```text
result=GO_AFTER_RUNTIME_FIX
task06_closable=true
business_code_changed=true
spec_status_changed=updated_after_verification
real_production_pdf_import=true
real_production_kb_or_qdrant_write=true
real_browser_confirmation=user_manual_acceptance
targeted_regression=35 passed + 80 passed / 5 subtests / exit 0
frontend_syntax=2 passed / exit 0
runtime_8500=reachable
```

本文件保留 2026-09-16 的 NO-GO 事实作为历史记录；以下收口复验追加了最小业务修复和一次隔离公开 PDF 导入，不覆盖历史结论。

## 结论摘要

1. 当前 8500 服务可达：`GET /api/health`、`GET /research`、`GET /api/research-tasks?limit=5` 均返回 200；Research 静态页使用 `/assets/research-tasks.js?v=8`，资源 HEAD 返回 200。
2. 定向回归通过：Spec029 reuse/acquisition/evidence/search-id/frontend 合同与 Spec027 后端切片共 `77 passed, 5 subtests passed in 2.60s`，退出码 0；`node --check frontend/research-tasks.js` 和 `node --check frontend/app.js` 均退出码 0；相关后端 `py_compile` 退出码 0。
3. 当前生产 Research SQLite 没有可验收的全文链：`research_paper_selections`、`research_selection_versions`、`research_acquisition_approvals`、`research_document_links`、`research_acquisition_events`、`research_evidence_upgrades` 均为 0。对真实任务 `7fc66400a3f75df789b62e293aa80ff9` 的详情返回 `search_id=null`；预览因无选集返回 409 `REPORT_NOT_READY`，acquisitions 返回 404 `BATCH_NOT_FOUND`。这些是 fail-closed 行为，不是导入成功证据。
4. 固定公开样本 `https://www.usenix.org/system/files/usenixsecurity26-peng-jiaqian.pdf` 的只读 HEAD 返回 200、`application/pdf`、1,094,158 bytes；这只能证明公网资源可达，不能证明本系统已经下载、校验、导入或索引该 PDF。
5. 当前已有 KB 文档 `d4dfd2a620384ad5bece27320661f8f0` 的本地只读 manifest/evidence 接缝探针成功：PDF 存在，v1 manifest 为 `ready`/`verified`，107 chunks，默认 `EvidenceUpgradeService` 使用发布 generation reader 得到 `upgraded/fulltext`、page 1、generation `38efa91a33154fd097c61d1c745d408f`。该探针使用内存 Research store，不产生生产 Research link/evidence 行，不能替代 selection→approval→batch→link→KB 的真实链。

## 可修复 P0/P1

### P0：正常本地目录命中路径没有可持久化 acquisition snapshot handle

证据：`backend/app/research/application/search_catalog_adapter.py:326-334` 的 local-first 分支以本地目录候选 ID 构造 `SearchOutcome`，没有 `search_id`；`SearchWorker` 在 `:450-469` 只在 outcome 带合法 handle 时输出 `search_id`。当前生产任务的 `search_catalog` work item 输出含候选 ID和 `source_refs`，但没有 `search_id`，对应 `research_tasks.search_id` 也为空。

影响：`frontend/research-tasks.js:1368-1370` 对空 handle 安全阻止确认；若绕过前端，`backend/app/research/application/acquisition.py:110-123` 仍会因无 handle 返回 `SEARCH_NOT_FOUND`，无法创建既有 `PaperImportBatchService` 批次。因而正常 Research 任务无法进入真实全文获取链，这是 Task06 的 P0 收口阻塞。

最小修复范围（不新建下载器或状态机）：

- `backend/app/research/application/search_catalog_adapter.py`：让本地目录命中也绑定一个服务端持久化快照句柄，或复用现有 catalog search job/snapshot 机制并返回该 handle；候选 payload 必须能被既有 batch service 按 handle 读取。
- `backend/app/research/application/orchestrator.py`：保持现有首个有效 handle 写入 `ResearchStore.set_task_search_id` 的桥接，并补本地命中分支回归。
- `tests/test_spec029_search_id_bridge.py` 及相关 acquisition 合同：覆盖 local-first 结果具有 handle、任务详情可恢复以及刷新后仍可确认。

若产品选择禁止本地命中直接进入 acquisition，则必须在预览中明确返回不可确认状态并重新执行一次有快照的目录搜索；不能继续给出可选候选而缺失 handle。

### P1：确认请求的 search_id 未与任务服务端句柄做一致性校验

证据：`backend/app/api/routes_research.py:1290-1297` 将客户端 payload 的 `search_id` 原样传给服务；`backend/app/research/application/acquisition.py:110-123` 只检查非空后传给 batch service，没有读取任务的 durable `search_id` 并比较。若两个搜索快照中出现相同 catalog ID，客户端可把当前任务候选与另一快照 handle 组合，破坏“当前服务端候选快照”的完整性边界。

最小修复范围：在 Research acquisition application/route 组合根读取任务服务端持久化 handle，要求 payload handle 与其相等（或由服务端完全忽略 payload 并只使用 durable handle）；补 stale/mismatch 失败合同。不要接受客户端 candidate URL 或 snapshot 内容。

## 公开 PDF / KB 导入链判定

| 阶段 | 判定 | 真实证据 |
|---|---|---|
| 固定公开 PDF 可达 | 通过（网络 HEAD） | HTTP 200，`application/pdf`，1,094,158 bytes |
| 预览不产生副作用 | 合同通过，生产未验 | 定向合同通过；当前无 selection，未能对真实候选做前后计数 |
| 显式确认创建既有 batch | **阻塞** | 当前任务 `search_id=null` 且无 selections/approval；未提交确认 |
| 安全下载/PDF 校验 | 未执行 | 不把 HEAD 或已有旧 KB 文档冒充为本次导入 |
| 真实 KB/Qdrant 写入 | 未执行 | `research_document_links=0`；本审计未写生产 KB/Qdrant |
| 真实全文 manifest/chunk/page | 接缝通过，真实 acquisition 未验 | d4df 本地现有 manifest 的内存 locator probe 成功；不是本次公开 PDF 导入产物 |
| evidence-upgrade 生产链 | 未验 | 无 Research link/evidence 行；不能声称真实报告升级 |
| 浏览器候选编辑/确认/重试 | 未执行 | 仅 HTTP/static smoke；未点击真实确认或重试 |

## 产物与改动文件

- 新增审计产物：`docs/sdd/plans/029/artifacts/task-06/backend-acceptance-audit.md`
- 业务代码改动：无
- Spec 状态、reviews/029 状态：未修改
- Git commit/push/merge/reset/stash/clean：未执行

## 命令与退出码

| 命令/动作 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec029_reuse_gate.py tests/test_spec029_acquisition_bridge.py tests/test_spec029_fulltext_evidence.py tests/test_spec029_search_id_bridge.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec027_backend_research_slice.py` | 0 | 77 passed，5 subtests，2.60s |
| `node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node --check frontend/app.js` | 0 | 语法通过 |
| `.venv/bin/python -m py_compile`（acquisition/evidence/routes/store） | 0 | 编译通过 |
| HTTP `GET /api/health`（8500） | 200 | 服务健康 |
| HTTP `GET /research`（8500） | 200 | Research 页面真实返回 |
| HTTP `GET /api/research-tasks?limit=5`（8500） | 200 | 任务列表可读，样本 `search_id=null` |
| HTTP `POST .../acquisition-preview`（真实无选集任务） | 409 | `REPORT_NOT_READY`，无副作用 |
| HTTP `GET .../acquisitions`（真实无 approval 任务） | 404 | `BATCH_NOT_FOUND`，fail closed |
| HTTP `HEAD` 固定公开 USENIX PDF | 200 | 仅网络可达性，不下载 |
| 本地实际 manifest/evidence probe（内存 store） | 0 | 已有 d4df manifest locator 可升级为 fulltext，不写生产库 |

## 决策依据 / 风险阻塞

- Spec029 的验收方式明确要求至少一篇公开 PDF 真实下载、导入、全文索引、切片定位；当前没有 selection→approval→batch→document link→KB 的真实生产记录。
- 自动化合同测试和本地 manifest probe 只能证明接缝/安全门，不足以证明真实网络、PDF 校验、索引代次与浏览器交互。
- P0 handle 缺口是当前最小可修复技术阻塞；P1 handle 一致性校验是修复后必须补上的完整性边界。
- `data/kb/papers.json` 中仅 d4df 文档同时具备当前 verified metadata 与 ready v1 manifest；其余 5 个文档 metadata 为 `legacy_unknown`，不应作为严格 provenance 样本。

## 主 Agent 后续动作

1. 先修复/明确 local-first catalog snapshot handle，并补任务详情刷新后恢复与 acquisition mismatch 回归；若需求契约因此变化，先更新 Spec/评审。
2. 重新产生一个未过期、带完整候选 payload（含 `pdf_access`/下载来源）的服务端 catalog snapshot，并确认 Research selections 正常持久化。
3. 在用户明确允许一次可回滚测试导入后，执行真实公开 PDF 的 preview→显式确认→既有 batch→document link→KB index→manifest/chunk/page→evidence-upgrade；记录 batch/item/document/source hash/generation/chunk locator。
4. 通过浏览器验证候选增删、确认前无下载、waiting_login/failed/retry/partial 和打开原文切片；失败时记录真实错误，不将合同测试写成成功。
5. 由开发主管补签 `docs/sdd/reviews/029-acceptance-review.md` 后，才可按 SDD 收口更新 Spec 状态与 changelog；当前不能标记已完成或声称真实部署验收通过。

## 收口复验（2026-09-17）

- P0/P1 已修复：本地优先目录命中现在通过既有 `search_jobs/search_results` 产生服务端快照；Tool/AgentRuntime/Orchestrator 传递并持久化 `search_id`；确认服务只接受任务绑定的句柄，拒绝不匹配的客户端句柄。
- 真实任务：`3eee288b8e5a512dad3dad524d787c63`，服务端快照 `fd6d1c7892fd49f29ea4682393530594`，选集版本 `1`；只读 preview HTTP 200。
- 真实导入：显式确认后批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db` 将 USENIX 公开论文 `b839eca81d1c3e4d` 导入为文档 `bfaf307d22a145b88fbf9e200df869b5`，逐篇状态 `completed`。
- 真实索引/证据：索引任务 `06ea5c95e4ae40fe9e670379df68a1fb` 生成 v1 manifest（`ready`、`verified`、138 chunks、0 unmapped）；evidence upgrade 返回 `fulltext`、5 个真实 chunk ID、page 1–12、source SHA-256 与 generation。
- 最终全量回归：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest -q` → 退出码 0，`2486 passed, 1 skipped, 5 warnings, 67 subtests passed`。
- 8500 服务重启后 `/api/health` HTTP 200；用户已完成人工验收并明确通过。

## 时间与工具统计

```text
开始：2026-09-16T23:31（约） Asia/Shanghai
结束：2026-09-16T23:42:20+08:00
总耗时：约 11 分钟
模型：Luna high（按 Task06 临时分派要求）
工具统计：exec 9 次（含 2 次 require_escalated 只读网络/本地运行时探针）；未使用写业务代码、Git 或浏览器点击操作
```
