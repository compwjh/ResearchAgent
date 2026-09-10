# 验收评审：spec-015 Task05 安全下载、规范命名与知识库导入

> 评审角色：测试（子代理 tester，模型 gpt-5.6-luna/high）
> 关联：spec-015、`docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`
> 验收范围：Task05 定向验收；使用注入式 transport/indexer/temp dir，不访问真实站点或 Qdrant。

## 结论：通过

Task05 指定的安全下载、身份命名、单篇导入、知识库路径兼容、重复幂等、索引失败补偿和论文单篇 API 契约均通过。批量导入、Playwright 登录、UI、真实站点、Spec013/014、reranker 及排序质量不属于本次验收范围。

## 验证命令与结果

```text
.venv/bin/python -m pytest -q \
  tests/test_paper_download_security.py \
  tests/test_paper_download.py \
  tests/test_paper_import.py \
  tests/test_paper_import_identity.py \
  tests/test_paper_discovery_api.py \
  tests/test_kb_services.py

115 passed, 5 warnings, 8 subtests passed in 1.06s
```

另行使用临时目录和注入式 downloader/indexer 验证：两线程重复导入最终仅 1 条元数据和 1 个 PDF；indexer 抛异常时返回 `KB_IMPORT_FAILED`、可重试，元数据、论文文件和临时文件均清理。

## 逐项判定表

| 验收点 | 状态 | 依据（文件:行或关键片段） |
| :--- | :--- | :--- |
| 安全 URL：仅 HTTPS/443、allowlist、禁止用户信息/认证参数/fragment、DNS 公网地址和 peer 复核 | 通过 | `backend/app/services/paper_download_security.py:143-181` 的 `validate_url`；`:123-140` 的 DNS 公网筛选；`:217-222` 的 `validate_peer_ip`。测试 `test_paper_download_security.py` 覆盖协议、端口、allowlist、凭证、fragment、认证查询参数、IPv4/IPv6 内网与混淆地址。 |
| 重定向不自动跟随且逐跳重新校验 | 通过 | `backend/app/services/paper_download.py:181-207` 创建 `follow_redirects=False` 客户端并逐跳调用 `validate_redirect_target`；测试 `test_downloads_pdf_with_manual_redirect_and_private_random_file` 与 `test_redirect_target_is_revalidated_and_blocked` 通过。 |
| 公开 PDF 模拟下载成功、受控临时目录和原子文件流程 | 通过 | `paper_download.py:173-180` 创建私有 `0700` 目录和随机临时文件，`:243-258` 原子 rename 并返回结果；测试确认重定向后内容、PDF 后缀、目录权限和字节数。 |
| 超时、伪 PDF/HTML、404/登录、超大响应被拒绝且无残留 | 通过 | `paper_download.py:190-242` 映射超时/HTTP/PDF/大小错误，`:261-268` 清理；测试 `test_stable_http_and_pdf_errors_are_reported_and_cleaned`、`test_declared_and_streamed_size_limits_clean_up`、`test_timeout_maps_to_stable_error`、`test_page_validator_failure_removes_renamed_file` 均通过。 |
| 文件名安全、Unicode/非法字符/空标题/保留名/超长和同名不同 DOI | 通过 | `tests/test_paper_import_identity.py` 覆盖 `build_paper_filename`、`unique_paper_filename` 和 `filename_for_candidate`；`paper_import.py:294-315` 仅使用服务端会议简称并做 basename 边界检查。 |
| 论文身份与重复幂等（下载前检查、写入锁内二次检查） | 通过 | `paper_import.py:273-279` 下载前查重，`:298-305` 提交段二次查重；测试 `test_duplicate_is_checked_before_download` 证明重复提交不再次下载。补充两线程测试最终为 1 条记录、1 个 PDF，第二调用返回 `PAPER_ALREADY_EXISTS`。 |
| 单篇导入成功：规范命名、元数据、文件和 v1 indexed 状态 | 通过 | `paper_import.py:306-332` rename 后写入论文元数据并进入 indexing，`:343-363` 仅在 `_index_succeeded` 后置为 indexed；测试 `test_import_persists_metadata_renames_and_indexes` 通过。 |
| 索引失败补偿，不伪造完成状态 | 通过 | `paper_import.py:349-371` 非 indexed 或异常均抛 `KB_IMPORT_FAILED` 并调用 `remove_paper`、清理下载；测试 `test_index_failure_removes_record_and_file` 及补充 indexer 异常场景确认无元数据、无 PDF、无临时残留。 |
| 新 `stored_name` 与旧 `{paper_id}.pdf` 路径兼容，重建/删除路径可解析 | 通过 | `backend/app/services/kb/store.py:137-164` 的 `resolve_paper_path` 优先 `stored_name`、缺失时回退旧路径；`tests/test_kb_services.py` 覆盖新旧记录加载、删除和 stored_name 删除；路由重建使用 `resolve_paper_path`（`backend/app/api/routes.py:873-881`）。 |
| 单篇 API 仅接受 `search_id`/`candidate_id`，拒绝客户端 URL/元数据，服务端解析候选 | 通过 | `backend/app/api/schemas.py:54-67` 的 `PaperImportRequest` 设置 `extra="forbid"`；`backend/app/api/routes.py:363-399` 先查会话和候选，再把服务端候选传给 importer。`test_import_resolves_candidate_server_side_and_returns_result_fields` 与 `test_import_rejects_client_metadata_with_stable_validation_error` 通过。 |
| API 关闭开关时零 store/importer 外部调用 | 通过 | `backend/app/api/routes.py:364-367` 在任何 store/importer 调用前检查 `_paper_discovery_enabled()`；`test_import_disabled_does_not_open_store_or_import` 用注入断言确认无调用并返回 `PAPER_DISCOVERY_DISABLED`。 |
| API 错误体字段完整且稳定 | 通过 | `routes.py:95-100` 固定返回 `{code,message,retryable,request_id}`；`routes.py:301-305` 映射导入错误；API 测试验证参数错误、过期会话及 `LOGIN_REQUIRED`/`DOWNLOAD_BLOCKED`/`DOWNLOAD_TIMEOUT`/`INVALID_PDF` 的字段集合和状态码。 |

## 风险与建议（不阻塞）

- 本报告未验收批量任务、登录续传、真实 ACM/IEEE 权限下载、前端入口和排序质量；这些应在 Task06–08 的专门验收中执行。
- 定向测试产生 5 条 PyMuPDF 相关 DeprecationWarning，不影响本次结果；建议在全量回归中持续观察依赖升级影响。

## 开发主管签字

（待开发主管填写）
