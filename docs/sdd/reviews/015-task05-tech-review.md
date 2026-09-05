# Spec 015 Task05 安全下载与知识库导入技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 调度：临时 `gpt-5.6-luna/high`，不固化模型规则
- 评审时间：2026-09-04 18:31–18:38 CST
- 评审范围：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`、`backend/app/services/paper_download_security.py`、`backend/app/services/paper_download.py`、`backend/app/services/paper_import.py`、`backend/app/services/paper_import_identity.py`、`backend/app/services/kb/store.py`、`backend/app/services/kb/index.py`、`backend/app/services/kb/tasks.py`、`backend/app/api/routes.py`、`backend/app/api/schemas.py` 及对应测试
- 评审约束：只读检查；未修改业务代码、测试或 Git；Task06 的批量任务、Playwright 登录/续传明确不在本轮要求内
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task05-review-20260904.md`

## 结论：打回

Task05 当前不能通过技术门禁。SSRF 基础校验、手动重定向、超时/大小上限、临时目录权限、服务端候选 ID 解析、基本错误体和新旧文件名路径回退已具备；但仍有两个直接影响安全与数据一致性的高优先级缺陷：API 把服务端候选 URL 主机动态加入 allowlist，绕过了“最小站点 allowlist”；文件 rename 或 Qdrant v1 写入后失败时，补偿不能保证清理已提交产物/向量。另有身份持久化和响应 Content-Type 校验缺口。它们属于 Task05 的核心验收项，不能以现有正向测试通过放行。

本轮定向回归命令：

```text
.venv/bin/python -m pytest tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_import.py tests/test_paper_discovery_api.py tests/test_kb_routes.py tests/test_kb_services.py -q
结果：132 passed，5 warnings
```

## 发现项

| 优先级 | 结论 | 证据 | 影响与要求 |
|---|---|---|---|
| **P0** | 候选 URL 主机被自动信任，allowlist 可被服务端外部数据扩大 | `backend/app/api/routes.py:333-348` 将 `candidate.pdf_url` 的 hostname 加入 `_paper_candidate_hosts()`；`routes.py:394-398` 将其直接传给下载器 | OpenAlex/其他召回快照本身是外部不可信数据。只要是 HTTPS、公共 IP，任意候选主机即可通过“allowlist”，这不符合 spec 的最小站点 allowlist，且允许下载任意公共站点资源。应只使用服务端固定/经验证的 allowlist（或由会议配置显式绑定），候选 URL 仅作待校验目标；补充“恶意候选主机不在配置 allowlist 时不得发出请求”的 API/服务测试。 |
| **P1** | rename 后元数据写入失败会遗留孤儿 PDF | `backend/app/services/paper_import.py:315-332` 先 `os.rename(source, target)` 再 `upsert_paper()`；`333-341` 异常补偿只调用 `_cleanup_download(download)`；该函数 `178-194` 只删除下载器原始 `file_path`，不会删除已经移动的 `target` | 文件已离开临时目录而元数据尚未提交时，异常路径留下 `papers_dir/规范名.pdf`，后续重试可能出现未对账文件/覆盖或错误显示。必须把 target 纳入本次 saga 上下文，元数据失败时按“只删除本次新文件”补偿，或实现启动对账并在测试中注入 rename 后 upsert 失败。 |
| **P1** | v1 索引失败补偿未删除已写入的 Qdrant 点 | `paper_import.py:343-371` 失败时只调用 `remove_paper()` 和 `_cleanup_download()`；`backend/app/services/kb/index.py:321-333` 的 `upsert_chunks()` 可能已写入向量后返回/抛错，`remove_paper()`（`store.py:160-175`）只处理 JSON 与 PDF，不调用 `delete_paper()` | 可能出现“知识库无 PaperRecord 但仍可检索到本次 paper_id 的向量”，违反 spec 的 saga 补偿及“索引失败不得显示成功/不可检索孤儿”要求。需要记录本次 paper_id/chunker，v1 失败时幂等删除本次向量；同时覆盖 embedding 失败、Qdrant upsert 失败/部分成功和最终 metadata 更新失败的故障注入。 |
| **P1** | DBLP-only 身份没有持久化，且稀疏记录与冲突 DOI 的 fallback 可能误判重复 | `PaperRecord` 字段仅在 `backend/app/services/kb/store.py:57-66` 保存 DOI 等元数据，没有 `dblp_key`；`paper_import.py:104-121` 从记录构造身份时只能读到已持久化字段。`paper_import_identity.py:188-207` 在一侧 DOI 缺失时直接允许 title/year/conference fallback | 仅有 DBLP key、标题发生变化的同一论文无法可靠去重；已有 DOI A 的记录与没有 DOI 但同标题的候选可能被判为同一论文，即使候选实际 DOI B，违背“同名不同 DOI 不覆盖”。应明确持久化 DBLP key（或另有不可丢失的身份索引），并在强身份冲突时禁止标题 fallback；补充 DOI 缺失/冲突与 DBLP-only 重试测试。 |
| **P2** | Content-Type 只拒绝 `text/html`，没有执行明确的 PDF 类型策略 | `backend/app/services/paper_download.py:216-237` 读取 `content-type` 后仅判断 `content_type == "text/html"`，`application/json`、任意未知类型仍可在 `%PDF-` 前缀满足时进入后续 | `%PDF-` 魔数和页解析是必要条件，但 Task05/Spec015 还要求校验 HTTP Content-Type。应固定允许 `application/pdf`（如需兼容缺失/`application/octet-stream`，写入契约并测试），其他类型稳定返回 `INVALID_PDF`，避免响应类型契约漂移。 |

## 已通过/条件通过的检查

### SSRF、重定向、资源边界

- `paper_download_security.py` 已拒绝非 HTTPS、非 443、userinfo、fragment、认证参数、混淆 IP、IPv4-mapped IPv6、loopback/private/link-local/multicast/reserved/unspecified 地址，并对每一跳执行 URL/DNS 校验。
- `paper_download.py:181-207` 使用 `follow_redirects=False`，最多 5 跳并对 Location 重新校验；`10/30/120` 秒 connect/read/total timeout、64 KiB 响应头、64 MiB PDF、流式大小检查均落地。
- 临时目录使用随机私有目录并设置 `0700`，partial 文件经同目录 `os.replace`；失败下载的目录清理在当前测试范围内通过。
- 需在修复 P0 后补充真实 allowlist 负例和自定义 client 无 peer 证据的边界测试。当前 `_check_peer()` 对 supplied client 且无 peer evidence 的路径直接放行（`paper_download.py:95-111`）；若保留测试 seam，必须确保生产调用不能走该旁路，真实连接必须提供 peer 复核。

### 身份、文件名和旧记录兼容

- `paper_import_identity.py` 的规范 DOI、DBLP key、标题/year/conference 组合键与安全文件名清洗基本正确；文件名超长只截断标题，服务端会议简称作为命名输入。
- `store.resolve_paper_path()`（`backend/app/services/kb/store.py:131-157`）对新 `stored_name` 和旧 `{paper_id}.pdf` 均有回退，KB reindex/delete 的现有路径测试通过。
- `PaperRecord` 的可选字段保持旧 JSON 记录可读取；但上表 P1 所述 DBLP key 持久化缺口必须在 Task05 收口前作出明确决策并验证。

### 单篇 API 与稳定错误体

- `PaperImportRequest`（`backend/app/api/schemas.py:54-66`）只接受 `search_id/candidate_id` 且 `extra="forbid"`；路由先查服务端 search session/candidate、检查过期，再解析服务端会议配置，未使用客户端 URL/标题。
- `routes.py:96-100` 的错误体固定含 `code/message/retryable/request_id`；下载/导入稳定错误映射在 `routes.py:286-305`，已有 API 测试覆盖过期会话、客户端额外 URL、关闭开关和主要下载错误。
- 仍需在 P0 修复后验证“服务端快照中的恶意 pdf_url 不能扩大 allowlist”；当前 API 测试 mock 了 `import_candidate`，未实际验证 allowlist 约束。

## 不计入本轮打回的范围

- Task06 的批量导入、批次/条目持久化状态机、受控并发、Playwright browser manager、ACM/IEEE 登录和 resume 明确标记为“待执行”，本轮不要求实现，也不以此作为 Task05 打回理由。
- 本轮只评估 Task05 已声称完成的单篇下载、命名、身份去重、PaperRecord 兼容、KB v1 导入和对应单篇 API；Task07 前端 Tab、Task08 全量安全回归和真实外部站点登录也不在本轮结论内。

## 放行前最小修订

1. 删除 `_paper_candidate_hosts()` 对候选 hostname 的动态信任；固定生产 allowlist，并为未授权候选主机补充“零外部请求”的测试。
2. 将已 rename 的 target 纳入 saga 状态和补偿；注入 `upsert_paper` 失败，确认无孤儿文件、元数据和临时目录。
3. 为 Qdrant v1 索引失败建立幂等向量补偿；注入部分/完整 upsert 失败，确认无遗留 paper_id 点，且不删除既有论文向量。
4. 决定并实现 DBLP key 的持久身份索引；修正一侧缺 DOI 时的强身份冲突规则；补充重复/并发/冲突 DOI 测试。
5. 固定 Content-Type 允许集合及缺失类型策略，并补充 JSON/未知类型伪 PDF 测试。
6. 修复后重跑 Task05 定向测试，并由 tester 再执行 Task05 验收；之后才能把 Task05 从“实施中”改为完成或进入 Task06。

## 最终裁定

**打回。** 当前 132 个定向测试通过，但未覆盖 P0 allowlist 扩大、rename 后孤儿文件、Qdrant 补偿和强身份冲突，因此不足以通过 Task05 技术门禁。
