# Spec 015 Task05 安全下载与知识库导入技术复核（最终）

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审时间：2026-09-04 18:40:17–18:41:46 CST
- 总耗时：1 分 29 秒
- 复核范围：上次技术复核的 5 个阻塞（固定服务端 allowlist、rename 后元数据失败清理、索引失败向量补偿、DBLP key 持久化/冲突语义、Content-Type 策略）及其直接测试
- 约束：只做复核；未修改业务代码、测试或 Git，未提交、未 push
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task05-recheck-20260904-184017.md`

## 结果状态和摘要

**通过。** 五项阻塞均已在当前实现中闭环，并有对应回归测试或可核验的实现证据。Task05 可进入验收签字与后续 SDD 收口；本结论不覆盖 Task06 批量导入/登录续传、Task07 UI、真实外站权限下载及 Task08 全量安全回归。

## 逐项复核

| 阻塞项 | 结论 | 证据 |
|---|---|---|
| 固定服务端 allowlist | 已修复 | `backend/app/api/routes.py:333-349` 只从 `paper_discovery_allowed_hosts` 或既有服务配置读取主机，不再读取或加入 `candidate.pdf_url` 的 hostname；`routes.py:394-400` 将该集合传给导入器。`tests/test_paper_discovery_api.py:82-89` 验证候选 hostname 不扩大 allowlist。下载器每跳仍在 `paper_download_security.py` 执行 allowlist/DNS/peer 校验。 |
| rename 后元数据失败清理 | 已修复 | `backend/app/services/paper_import.py:197-218` 统一补偿 `paper_id` 元数据、rename 后 `target` 和下载临时文件；`paper_import.py:323-373` 在 rename、记录写入及异常路径均调用补偿。`tests/test_paper_import.py:111-130` 注入“写入后失败”，确认无 PDF 且 metadata 为空。 |
| 索引失败向量补偿 | 已修复 | `paper_import.py:375-422` 对 v1 非 indexed 结果、索引异常和最终状态写入异常均调用注入的 deleter；默认 deleter 调用 `delete_paper_chunker(paper_id, CHUNKER_V1)`，只删除本次论文的 v1 点。`backend/app/services/kb/index.py:141-169` 的过滤条件同时限定 `paper_id` 和 `chunker`。`tests/test_paper_import.py:133-153` 验证部分写入失败会调用 v1 补偿且记录/文件清理。 |
| DBLP key 持久化与冲突语义 | 已修复 | `backend/app/services/kb/store.py:57-67,194-223` 增加并保存可选 `dblp_key`，`paper_import.py:347-362` 写入规范化 DBLP key，`paper_import.py:85-96` 从旧/新记录重建身份。`paper_import_identity.py:188-217` 在 DOI 双方存在时只接受 DOI 相等；一侧 DOI 缺失时仅在双方 DBLP key、年份、会议一致时匹配，不再使用标题回退；无强身份时才使用标题组合键。定向测试 150 passed，且本次额外执行的四种 DOI/DBLP 组合检查得到预期 False/True/True/False。 |
| Content-Type 策略 | 已修复 | `backend/app/services/paper_download.py:223-245` 将声明的类型固定为 `application/pdf`；`application/json`、`text/html` 及其他声明类型统一返回 `INVALID_PDF`，同时仍强制 `%PDF-` 魔数和页解析。`tests/test_paper_download.py:84-97` 覆盖 HTML 与 JSON 伪 PDF，并确认失败后无残留。当前兼容策略允许缺失 Content-Type，但缺失时仍必须通过魔数和可读页校验。 |

## 验证方式与结果

定向测试命令：

```text
.venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_discovery_api.py tests/test_kb_routes.py tests/test_kb_services.py
```

- 退出码：`0`
- 结果：`150 passed, 5 warnings, 8 subtests passed in 5.45s`
- 目标模块语法编译：退出码 `0`
- `git diff --check`：退出码 `0`
- 警告：5 条 PyMuPDF/SwigPy 依赖弃用警告，不影响本次结论

## 改动文件（应为空）

业务代码、测试和配置改动：**无**。

本次仅新增以下评审产物：

- `docs/sdd/reviews/015-task05-tech-review-recheck-final.md`
- `.codebuddy/agent-logs/techlead-spec015-task05-recheck-20260904-184017.md`

## 决策依据

1. 上次技术复核提出的 5 个阻塞均可在当前代码中定位到明确修复点。
2. 新增故障注入和安全负例测试已纳入同一组 Task05/KB 回归，全部通过。
3. 补偿删除按本次生成的 `paper_id`/target 定位，不会按标题或目录做宽泛删除；DBLP/DOI 冲突不会因标题相同而覆盖。
4. Content-Type 缺失属于显式兼容策略，仍受 PDF 魔数与页面解析双重约束；声明型非 PDF 类型已固定拒绝。

## 风险与阻塞

- 当前无阻塞。
- 低风险：Content-Type 缺失响应仍被兼容接受；若后续要求严格 HTTP 头契约，可将缺失类型改为拒绝并补充外站兼容性评估。
- 低风险：本轮使用注入式 transport/indexer/deleter，未访问真实站点或 Qdrant；真实外部服务和权限下载保留给后续验收范围。
- 不计入本轮：批量导入、Playwright 登录/续传、前端入口、排序质量和全量安全回归。

## 主 Agent 后续动作

1. 将本复核作为 Task05 技术门禁的最终签字依据，并安排 tester 对修复后的 Task05 验收报告补签。
2. 验收签字完成后，按 SDD 清单更新 Task05/spec 状态、`spec-status-changelog.md` 与变更日志；不要把本复核扩大为 Task06–08 的完成声明。
3. 收口前保留上述 Content-Type 缺失兼容策略的风险记录，并按项目流程执行部署与运行时验证。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：通过**
- 签字时间：2026-09-04 18:41:46 CST

## 可用运行统计

- 模型：当前协作运行时未提供可核验模型名
- token：运行时未提供 token 统计
- 工具统计：`exec_command` 12 次、`write_stdin` 1 次、`apply_patch` 2 次
