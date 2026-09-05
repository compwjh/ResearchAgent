# 验收评审：Spec015 Task06 最终安全验收

- 评审角色：测试（tester）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联计划：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
- 复核依据：`docs/sdd/reviews/015-task06-acceptance-review-final.md`、`docs/sdd/reviews/015-task06-tech-review-final.md`、`docs/sdd/reviews/015-task06-tech-review-overall.md`、`docs/sdd/reviews/015-task06-tech-review-final-security.md`
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task06-final-security-acceptance-20260904.md`
- 评审时间：2026-09-04（Asia/Shanghai）
- 约束：未修改业务代码、测试、配置或既有文档；未提交、未 push、未 reset/stash/clean；仅新增本报告与进展日志。

## 固定字段

- 结论：**不通过（最终安全门禁）**
- 阻塞：**有**；S1 浏览器认证 URL 安全边界，S2 异常原文泄漏；真实 ACM/IEEE 账户验收另有环境阻塞
- 测试：**206 passed，5 warnings，8 subtests passed；连续 3 次，退出码均为 0**
- 编译：**通过**；Task05/Task06 目标实现与测试 `compileall` 通过
- 差异检查：**通过**；`git diff --check` 通过，冲突标记扫描 0 命中
- 签字：**测试（tester）：不通过**；不得据此将 Task06 标记为已完成

## 一、三次完整定向回归

执行集合覆盖批次 store/service/API、browser manager、ACM/IEEE parser、Task05 下载器/SSRF、单篇导入、身份去重及 KB 回归：

```text
.venv/bin/python -m pytest -q \
  tests/test_paper_import_batch_store.py \
  tests/test_paper_import_batch_service.py \
  tests/test_paper_import_batch_api.py \
  tests/test_paper_browser_manager.py \
  tests/test_acm_paper_parser.py \
  tests/test_ieee_paper_parser.py \
  tests/test_paper_download.py \
  tests/test_paper_download_security.py \
  tests/test_paper_import.py \
  tests/test_paper_import_identity.py \
  tests/test_kb_routes.py \
  tests/test_kb_services.py \
  tests/test_paper_discovery_api.py
```

| 次数 | 退出码 | 结果 |
|---:|---:|---|
| 1 | 0 | `206 passed, 5 warnings, 8 subtests passed in 6.18s` |
| 2 | 0 | `206 passed, 5 warnings, 8 subtests passed in 6.18s` |
| 3 | 0 | `206 passed, 5 warnings, 8 subtests passed in 6.22s` |

警告为既有 PyMuPDF/Swig 依赖弃用警告，不影响断言。系统 Python 因缺少 FastAPI 无法收集 API 测试；验收统一使用项目 `.venv/bin/python -m pytest`，该入口可用（`.venv/bin/pytest` 独立脚本的 shebang 已失效，但未修改环境）。

## 二、已通过的安全验收项

| 验收项 | 判定 | 证据 |
|---|---|---|
| canonical API path | 通过 | 当前路由暴露 `POST /api/papers/imports`、`GET/POST /api/papers/imports/{batch_id}`（含 retry）、`POST /api/papers/import-items/{item_id}/login`、`POST /api/papers/import-items/{item_id}/resume`、`GET /api/papers/browser/health`；旧 batch/health 路径仅作兼容别名。未知资源返回固定 `{code,message,retryable,request_id}`。 |
| item login/resume server snapshot | 通过 | API 测试确认 login 由 item → batch → search session → candidate 快照推导 ACM 目标，不接受客户端 URL；resume 仅取当前 item 的 session，响应不含 lease/idempotency/Cookie/Authorization。额外过期临时 DB 验证：canonical retry 与 item resume 均返回 `400 SEARCH_EXPIRED`，未触发外部调用。 |
| 认证 downloader fake context | 通过 | fake browser API 测试确认 resume 将当前 item 的 `download_pdf` 回调传入 importer；BrowserSession fake context request 成功写入受控临时 PDF，401/403 映射为 `LOGIN_REQUIRED` 且不回显响应 Cookie。 |
| 浏览器不可用降级 | 通过（离线/运行时契约） | 当前环境 `import playwright` 为 `ModuleNotFoundError`；`GET /api/papers/browser/health` 返回 `200` 且仅含 `available=false、version=null、supported_sites、reason=BROWSER_UNAVAILABLE`。Task05 公开 PDF 下载/导入回归三次通过，未依赖浏览器。 |
| ACM/IEEE parser URL 与凭证拒绝 | 通过（离线 parser 切片） | ACM 7 项、IEEE 10 项纳入 206 项回归；精确 HTTPS origin、认证 query、userinfo/fragment、Cookie/Authorization header、DOM 变化均按稳定错误拒绝。 |
| profile/.gitignore 安全 | 通过（离线检查） | fake headed context 强制 `headless=false`、`accept_downloads=false`，并移除 `record_har_path`、`record_har`、`record_video_dir`、`downloads_path`；profile/lock 实测权限 `0700/0600`。`git check-ignore -v` 命中 `data/browser-profile/`、`data/paper_search/` 与 `.profile.lock`，未发现敏感运行文件被 Git 跟踪。 |
| 批量状态机/幂等/过期 session | 通过（离线切片） | 206 项回归连续三次通过；此前 22 项状态机回归、CAS/锁、20 项硬上限、旧租约隔离、失败/等待登录隔离与重启恢复均保持通过。 |

## 三、阻塞问题

### S1（P1）：浏览器认证请求接受认证 query，且未关闭/逐跳校验重定向

证据：`backend/app/services/paper_browser_manager.py:71-85,183-203` 的 `_origin`/`validate_origin` 只校验 HTTPS、精确 host、port、userinfo、fragment；认证 query 未拒绝。临时 fake 验证结果：

```text
acm  https://dl.acm.org/doi/1?token=secret                 ACCEPTED
ieee https://ieeexplore.ieee.org/document/1?access_token=secret ACCEPTED
```

同一认证路径直接调用 `context.request.get(..., fail_on_status_code=False, timeout=...)`，没有显式 `max_redirects=0`，也没有复用 Task05 下载器的 DNS/peer、allowlist 和逐跳重定向校验。该路径可能把 token URL 带入受保护请求/`DownloadResult.source_url`，违反 Spec015“禁止认证参数、禁止自动跟随重定向、每跳重新校验”的硬约束。

放行要求：认证请求复用统一 URL 安全校验，拒绝认证 query；明确禁用自动重定向并手动执行次数、HTTPS/443、站点 allowlist、DNS/peer 校验；补 token-query 和 fake redirect 回归。

### S2（P1）：异常原文进入持久化与单篇 API 响应

证据：`backend/app/services/paper_import_batch_service.py:320-327,336-352` 将 importer 异常/结果的 `message` 传给 `transition_item`/`mark_failed`；`_mark_failed` 默认使用 `error.message`。临时 SQLite 注入以下测试字符串后，条目仍保存完整原文：

```text
Authorization: Bearer TOPSECRET https://evil.example/x?token=abc
```

结果为 `status=failed`，`paper_import_items.error_message` 完整包含上述 Authorization、URL 和 token。另以 TestClient 注入 `PaperImportError`，`POST /api/papers/imports` 返回：

```text
502 {"code":"INVALID_PDF","message":"Authorization: Bearer TOPSECRET https://evil.example/x?token=abc", ...}
```

`_safe_import_error_message` 只能掩盖批量状态读取层，不能修复持久化原文；`_paper_import_error_response`（`backend/app/api/routes.py:362-366`）直接返回单篇 message。该行为违反错误、异常、观测和 API 统一脱敏约束。

放行要求：在异常进入 store 前按稳定错误码映射固定安全消息；单篇、批量、浏览器和观测共用 allowlist/固定消息，禁止依赖关键词过滤；补持久化、单篇响应、批量响应的 URL/Cookie/Authorization/password/token 断言。

## 四、真实外站验收环境阻塞（不伪造通过）

`.venv/bin/python` 无 Playwright；本环境无可核验 ACM Digital Library 或 IEEE Xplore 合法账户。因此未执行真实 headed 登录、机构 SSO/验证码/付费授权、真实页面结构、认证重定向和受保护 PDF 导入。A10/A11 只能标记为环境验收项，不能替代上述离线安全判定，也不能宣称已通过。

## 五、补充静态检查

- Task05/Task06 目标实现与测试 `compileall`：通过。
- `git diff --check`：通过。
- 全仓冲突标记扫描（排除 `.git`、`.venv`、`__pycache__`）：0 命中。
- profile/search state 忽略规则与权限检查：通过。
- 本轮未修改业务代码、测试或配置，未提交、未 push、未 reset/stash/clean。

## 签字

- 测试（tester）：**不通过（S1/S2 未闭环）**
- Tech Lead 签字：待复核
- 签字时间：2026-09-04
