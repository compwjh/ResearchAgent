# 验收评审：spec-015 Task05 安全下载、规范命名与知识库导入（安全修复复验）

> 评审角色：测试（tester）
> 关联：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`
> 复验依据：`docs/sdd/reviews/015-task05-acceptance-review.md`、`docs/sdd/reviews/015-task05-tech-review.md`、`.codebuddy/agent-logs/junior-dev-spec015-task05-security-fix-20260904.md`
> 进展日志：`.codebuddy/agent-logs/tester-spec015-task05-reacceptance-20260904-184241.md`

## 结论：通过（Tech Lead 已签字）

本轮已针对上次技术复核提出的 P0/P1/P2 项完成复验：固定服务端 allowlist 不会被候选 URL 主机扩大；rename 后元数据失败清除目标文件、记录和临时文件；v1 索引失败调用幂等向量删除补偿；DBLP key 写入 `PaperRecord` 且 DOI 强身份冲突不走标题误判；声明型非 PDF Content-Type（含 JSON）被拒绝。既有安全下载、命名、路径兼容、单篇 API、并发和幂等场景均通过。

批量导入、Playwright 登录续传、前端、真实外部站点/Qdrant、Task06–08 不属于本 Task05 单篇验收范围。

## 测试命令、退出码和结果

1. Task05 定向与 KB 回归：

   ```text
   .venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_discovery_api.py tests/test_kb_routes.py tests/test_kb_services.py
   ```

   退出码：`0`；结果：`150 passed, 5 warnings, 8 subtests passed in 14.32s`。警告为现有 PyMuPDF/Swig deprecation warning，不影响断言。

2. 修复项精确回归：

   ```text
   .venv/bin/python -m pytest -q \
     tests/test_paper_discovery_api.py::PaperImportEndpointTests::test_candidate_hostname_cannot_expand_download_allowlist \
     tests/test_paper_download.py::test_stable_http_and_pdf_errors_are_reported_and_cleaned \
     tests/test_paper_import.py::test_import_persists_metadata_renames_and_indexes \
     tests/test_paper_import.py::test_metadata_failure_after_rename_removes_target_and_record \
     tests/test_paper_import.py::test_index_failure_invokes_idempotent_vector_compensation \
     tests/test_paper_import_identity.py::test_missing_doi_does_not_collapse_into_doi_record_by_title \
     tests/test_paper_import_identity.py::test_different_dois_do_not_collapse_only_because_display_title_matches \
     tests/test_paper_import.py::test_duplicate_is_checked_before_download
   ```

   退出码：`0`；结果：`11 passed in 0.56s`。

3. 固定 allowlist 实际下载边界（临时目录、MockTransport、无真实网络）：

   退出码：`0`；结果：恶意候选 `https://evil.example/public.pdf` 在请求前返回 `DOWNLOAD_BLOCKED`，请求调用 `0` 次，产物 `0` 个。

4. 并发/幂等复跑（临时目录、注入 downloader/indexer、两线程、10 轮）：

   退出码：`0`；结果：`10/10` 轮通过；每轮下载调用 `2` 次，最终元数据 `1` 条、PDF `1` 个，结果集合为一个成功导入和一个 `PAPER_ALREADY_EXISTS`。

## 修复项逐项判定

| 验收点 | 状态 | 复验依据 |
|---|---|---|
| 固定 allowlist 不可被候选 URL 绕过 | 通过 | `routes._paper_candidate_hosts()` 仅读取 `paper_discovery_allowed_hosts`/服务端配置，不读取候选 hostname；`test_candidate_hostname_cannot_expand_download_allowlist` 通过；独立下载边界验证恶意候选 0 请求、0 产物。 |
| rename 后元数据写入失败无孤儿 PDF/记录 | 通过 | `test_metadata_failure_after_rename_removes_target_and_record` 注入“已写入后抛错”的 `upsert_paper`，最终 papers 目录无 PDF、元数据为空；`paper_import._cleanup_import_artifacts()` 同时清理 target、record 和临时下载。 |
| v1 索引失败执行向量补偿且不伪造完成 | 通过 | `test_index_failure_invokes_idempotent_vector_compensation` 注入部分索引后失败，断言调用 deleter `(paper_id, "v1")`，最终无 PaperRecord、无 PDF；实现默认使用 `delete_paper_chunker`。 |
| DBLP key 持久化 | 通过 | `test_import_persists_metadata_renames_and_indexes` 读回记录并断言 `dblp_key == "conf/ccs/safe"`；`PaperRecord`/`new_record()` 含可选 `dblp_key` 字段，旧记录仍可读取。 |
| 强身份冲突不被标题 fallback 合并 | 通过 | `test_missing_doi_does_not_collapse_into_doi_record_by_title` 与 `test_different_dois_do_not_collapse_only_because_display_title_matches` 均通过；身份匹配在一侧有 DOI 时禁止仅按标题去重。 |
| Content-Type 校验 | 通过 | `test_stable_http_and_pdf_errors_are_reported_and_cleaned` 覆盖 `text/html` 与 `application/json` 伪 PDF，均映射 `INVALID_PDF` 且无残留；下载器仅接受明确 PDF 类型（缺失类型仍由注入测试路径兼容）。 |
| 既有并发/幂等 | 通过 | 10 轮双线程复跑均只有一个成功记录/文件，另一个返回 `PAPER_ALREADY_EXISTS`；顺序重复测试同时确认第二次不再次下载。 |

## 过程异常说明

并发复跑的第一次临时断言直接对 `None` 与字符串错误码排序，测试脚本自身退出码为 `1`；未涉及业务代码。修正为集合计数后重新执行 10 轮，全部通过；该次脚本未写入仓库文件。

## 风险与阻塞

- 本轮无 Task05 阻塞。
- 仍不覆盖批量任务、登录续传、真实站点权限/网络行为、前端入口和排序质量；应由 Task06–08 分别验收。
- 保留现有 5 条 PyMuPDF/Swig deprecation warning，建议在全量回归中持续观察。
- 未提供模型/token/工具消耗计数器：模型名与 token 统计不可用；可核验的工具产物见进展日志。

## Tech Lead 签字

- 结论：**通过**
- 签字人：**Tech Lead（当前协作 Agent）**
- 时间：**2026-09-04**
- 签字依据：`docs/sdd/reviews/015-task05-tech-review-recheck-final.md` 与本验收报告；两者的 150 passed、11 passed、并发 10/10 轮结果及复核结论一致。

## 主 Agent 后续动作

1. Tech Lead 已复核本报告并填写“通过”签字。
2. 将本报告与进展日志纳入 Task05 收口交接；在 Task06 启动前保持批量/登录范围边界不变。
3. 本 tester 未修改业务代码、测试代码，未提交、未 push。

## 时间与耗时

- 开始：2026-09-04 18:35 CST
- 结束：2026-09-04 18:43 CST
- 总耗时：约 8 分钟
