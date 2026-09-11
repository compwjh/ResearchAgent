# Spec022 Task08 后端最终候选修复报告

## 结论

**PASS（Task08 后端阻塞项已清零，交由 backend-tester/tester 继续最终候选验收）。**

本轮只修改后端安全/记忆实现、受影响后端测试与测试基线。未修改前端；未运行全量 pytest；未部署。

## 修复内容

### 1. 旧 Article Assistant 下载/探测入口安全复用

- `backend/app/article_assistant/infrastructure/article_download.py` 不再使用自动跟随重定向的裸请求。
- URL/DNS/redirect/peer 原语已抽到共享基础模块 `backend/app/core/url_security.py`；Article Assistant、paper downloader、USENIX source 和 browser manager 都从共享模块调用。`paper_discovery.domain.paper_download_security` 仅保留兼容导出，不再承载第二套实现。
- probe 与 download 均复用共享 `validate_url()`、`validate_redirect_target()`、`validate_peer_ip()`：逐跳限制 host/端口/协议、DNS 仅允许公网地址、对端 IP 必须与 DNS 校验结果一致、重定向有上限且跨 allowlist 目标被拒绝。
- allowlist 只来自服务端 `article_download_urls` 与显式 `paper_discovery_allowed_hosts` 配置；候选自身的 `pdf_url/article_url` 不会扩展允许来源。当前真实 `data/article_settings.json` 两者均为空，因此未配置来源时旧入口在发出请求前 fail-closed；测试夹具显式配置 `example.com` 后才允许模拟公开来源。
- HTML 中的 PDF 链接也经过同一安全入口；私网/环回/链路本地地址在发出请求前拒绝，下载失败清理部分文件。
- 为保持旧 Article Assistant 已接受的 HTTP(S) 配置行为，安全原语新增显式 `allowed_schemes` 参数；论文发现默认仍为 HTTPS-only，只有 legacy adapter 显式启用 HTTP 兼容路径。
- 保持旧 probe 状态与 download 结果字段/登录异常行为不变。

新增回归覆盖：未配置来源的公开候选被拒绝、私有 IP 探测、私有 IP 下载、重定向到私有 IP 不发出第二次请求；既有文章 HTML 探测与下载合同继续通过。

### 2. SystemRule 损坏行 fail-closed

- `MemoryRepository._system_rule()` 现在校验 owner、content、enabled 和非空 ISO 时间戳的数据形状。
- `get_system_rule()` 将时间戳不可解析、NULL/错误类型或其他损坏行统一转换为 `SystemRuleUnavailableError("SYSTEM_RULE_UNAVAILABLE")`。
- API 读取同一异常稳定返回 HTTP 503 与 `detail.code=SYSTEM_RULE_UNAVAILABLE`，不再泄漏 `ValueError`/500。

新增 malformed `updated_at` repository/API 回归测试。

### 3. Task05 global 门禁测试基线

`tests/test_task05_memory_analysis_repair.py` 的未绑定原文 `记住多条` fixture 仍让 classifier 建议 global，但断言已改为两个 `pending_confirmation`，且断言没有写入 global memory。业务原文 global 门禁未放宽。

### 4. KB inventory 基线核对

经真实 SHA-256 重算，两个受保护文件的漂移来自已确认 Task10 的项目文档关联/项目过滤变更，不是本轮后端安全修复越界：

| 文件 | 原记录 | 当前真实值 | 判断 |
|---|---|---|---|
| `backend/app/api/routes_kb.py` | `7674ee4927e273639aebf2806f0a64a44e2d930b219bb5e4eb42d04b93df7c59` | `eb7dd12fd285eec4d8f7b7e407b4b898ae1b7579ff728e23648b09ff8860d67d` | Task10 已确认变更 |
| `backend/app/knowledge_base/application.py` | `b91e2dc546c7720209acc6164e38e2cf28ae057d60dcd38024c3e61d084cdebc` | `7540b9865b752fb9b206b19641a194437f80fd965d1ae73dd390a10d050c2804` | Task10 已确认变更 |

已将两项记录及聚合 `inventory_digest` 更新为真实值，并在 `tests/test_kb_upload_closure_matrix.py` 将 Task10 新增的内部原子 sidecar writer `_save_associations` 登记为受控 helper；未移除哈希校验、AST 写入口核对、旧写 helper 禁止规则或 health 只读护栏。

## 验证结果

| 检查 | 结果 |
|---|---|
| 受影响后端集合：模块边界、Task05/07/10、memory、conversation、chat、KB、Article Assistant 与 inventory | **109 passed**, 退出码 0 |
| 论文下载/安全/路由兼容集合 | **95 passed**, 5 warnings，退出码 0 |
| `tests/test_kb_upload_closure_matrix.py` | **2 passed**, 退出码 0 |
| `tests/test_api_module_boundaries.py` + Article/paper 下载安全集合 | **51 passed**, 5 warnings，退出码 0 |
| 共享安全原语调用方（browser manager/USENIX source）及边界/Article/paper 回归 | **104 passed**, 5 warnings，退出码 0 |
| `py_compile`（7 个变更后端模块） | 退出码 0 |
| scoped `git diff --check`（本轮文件） | 退出码 0 |
| backend 冲突标记检查 | none |

验证命令：

```text
./.venv/bin/python -m pytest -q tests/test_api_module_boundaries.py tests/test_task05_memory_analysis_repair.py tests/test_task05_backend.py tests/test_task07_backend.py tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_article_download_probe.py tests/test_article_html_probe.py tests/test_article_services.py tests/test_kb_upload_closure_matrix.py --tb=short
./.venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_paper_download.py tests/test_api_routes_coverage.py tests/test_task05_memory_analysis_repair.py tests/test_task10_backend.py --tb=short
./.venv/bin/python -m pytest -q tests/test_paper_browser_manager.py tests/test_usenix_publication_source.py tests/test_api_module_boundaries.py tests/test_article_download_probe.py tests/test_article_html_probe.py tests/test_article_services.py tests/test_paper_download_security.py tests/test_paper_download.py --tb=short
./.venv/bin/python -m py_compile backend/app/core/url_security.py backend/app/article_assistant/infrastructure/article_download.py backend/app/paper_discovery/domain/paper_download_security.py backend/app/paper_discovery/infrastructure/paper_download.py backend/app/paper_discovery/infrastructure/usenix_publication_source.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py backend/app/memory/repository.py
```

全仓库 `git diff --check` 仍会命中父会话已有的 `docs/sdd/reviews/022-acceptance-review.md:420` trailing whitespace；本轮变更文件 scoped 检查通过，未改动该父会话文件。

## 交接

- 进展日志：`.codebuddy/agent-logs/spec-022/task-08/backend-dev/20260911-190850.md`
- 本轮未执行全量 pytest、前端检查或部署；由 Task08 后续 tester 按计划执行。
