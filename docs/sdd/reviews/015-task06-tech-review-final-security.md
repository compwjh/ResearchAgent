# Spec015 Task06 最终安全复核

- 评审角色：Tech Lead（当前协作 Agent）
- 评审时间：2026-09-04（Asia/Shanghai）
- 复核依据：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`、`docs/sdd/reviews/015-task06-tech-review-overall.md`、API contract fix 与 authenticated resume 进展日志
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task06-final-security-20260904.md`
- 复核范围：Task06 全部切片及 Task05 共用导入/下载安全边界
- 约束：只新增本报告和进展日志；未修改业务代码、测试、spec 或 Git，未提交、未 push、未 reset/stash/clean

## 固定字段

- 结论：**打回（最终安全门禁不通过）**
- 阻塞：**有，S1/S2 两项 P1 安全问题；真实 ACM/IEEE 账户验收仍受环境阻塞**
- 测试：**206 passed，5 warnings，8 subtests passed；连续 3 次，退出码均为 0**
- 编译：**通过**；Task06/Task05 目标实现与测试 `compileall` 退出码 0
- 差异检查：**通过**；`git diff --check` 通过；全仓冲突标记扫描 0 命中
- 签字：**Tech Lead（当前协作 Agent）：打回**

## 已确认通过的安全边界

### 1. 规范路径与服务端候选绑定

OpenAPI 当前包含规范路径：

- `POST /api/papers/imports`（兼容 Task05 单篇形状及 Task06 批量形状）
- `GET /api/papers/imports/{batch_id}`、`POST /api/papers/imports/{batch_id}/retry`
- `POST /api/papers/import-items/{item_id}/login`、`POST /api/papers/import-items/{item_id}/resume`
- `GET /api/papers/browser/health`

旧的 `import-batches` 和 `browser-health` 仅作为兼容别名保留。批量、登录和续传请求体使用 `extra="forbid"`；登录接口不再接受客户端 `article_url`，而是从 batch → search session → candidate 快照推导站点和文章 URL。`_paper_snapshot_for_item` 与 `_paper_server_snapshot` 均检查搜索会话存在、候选归属和 TTL，过期 session 返回 `SEARCH_EXPIRED`，不会进入外部下载。

### 2. 条目级登录会话与认证 seam

`paper_browser_sessions` 以 `item_id` 为 key；登录会话替换和 resume finally 清理均只操作当前条目。resume 将当前 item 的 `session.download_pdf` 和 `session.context` 传入 `PaperImportBatchService.resume_item`，service 再通过 `_import_one` 的可选参数传给 `import_candidate`。这满足“当前条目认证上下文不借给其他条目”的静态路径及 fake 回归证据。

### 3. 站点 parser 和运行时文件边界

ACM parser 仅接受精确 `https://dl.acm.org` origin，拒绝 query、fragment、userinfo、非 GET、Cookie 和 Authorization；IEEE parser 仅接受精确 `https://ieeexplore.ieee.org`，并拒绝认证查询参数和 Cookie/Authorization 请求头。Browser manager 强制 headed persistent profile、profile 所有权/文件锁，移除 `record_har_path`、`record_har`、`record_video_dir`、`downloads_path`，健康响应只返回四个公开字段。

`.gitignore` 已包含 `data/browser-profile/`、`data/paper_search/` 和 `**/.profile.lock`。`git check-ignore -v` 对 profile lock、Cookies 路径和搜索 SQLite 均命中；`git ls-files` 未发现这些运行时敏感文件被跟踪。

## 阻塞问题

### S1（P1）：认证请求绕过下载 URL/重定向安全策略

`backend/app/services/paper_browser_manager.py:185-203` 的 `authenticated_pdf_request` 只调用 `validate_origin`，随后直接调用 `context.request.get(url, fail_on_status_code=False, timeout=...)`。当前 `_origin`/`validate_origin` 只检查 HTTPS、精确 host、port、userinfo 和 fragment，不拒绝认证 query（例如 `?casa_token=...`）；认证请求也没有显式 `max_redirects=0`，更没有对 `Location` 每一跳调用下载安全模块的目标校验。于是登录续传路径绕过 `paper_download_security.validate_url` 的认证参数、allowlist、DNS/peer 和逐跳重定向约束。真实 Playwright 默认行为未在本环境执行，但代码调用未传递重定向禁用参数本身已足以阻塞安全放行。

影响：受保护下载可能携带带令牌的候选 URL，或被自动跟随到未经逐跳校验的地址；这不满足 Spec015 的“URL 不含认证参数、禁止自动跟随重定向、每跳重新校验目标”硬约束。

最小修复：认证请求复用与公开下载一致的 URL 安全验证；拒绝认证 query；明确关闭自动重定向并手动限制次数、HTTPS/443、精确站点 allowlist、DNS/peer 绑定，每一跳重新校验；补 fake redirect 和 token-query 回归。

### S2（P1）：异常原文仍可进入持久化及单篇错误响应

`backend/app/services/paper_import_batch_service.py:320-327,338-344,349-352,370-378` 将异常或 importer 返回的 `message` 直接传给 `transition_item`/`mark_failed`；`_mark_failed` 对异常默认取 `error.message`。这会把包含 URL、Cookie、Authorization 或令牌的异常文本写入 `paper_import_items.error_message`。`backend/app/api/routes.py:362-366` 的 `_paper_import_error_response` 也直接将传入 message 放进错误体；它没有使用同一套固定安全消息/allowlist。

离线临时 SQLite 复现（仅使用测试字符串）确认：

```text
status= failed
persisted_error_message= https://evil.example/x?token=secret Cookie=secret
```

直接调用单篇错误 helper 也返回原文，而不是固定安全消息。批量状态响应的 `_safe_import_error_message` 只能掩盖 API 读取层，不能弥补数据库和单篇响应已经接收原文的事实。

影响：凭证或带令牌 URL 可能落入 durable state，违反“日志、异常、观测和 API 响应统一脱敏”以及不得将认证信息持久化的约束。

最小修复：在异常进入 store 前按稳定错误码映射到固定安全消息；单篇、批量、浏览器错误和观测共用 allowlist，不以关键词过滤代替固定映射；补充异常含 URL/Cookie/Authorization/password/token 的持久化和单篇/批量响应断言。

## 环境风险（不伪造通过）

`.venv` 中 `import playwright` 为 `ModuleNotFoundError`，本轮未执行真实 ACM Digital Library 或 IEEE Xplore 合法账户登录、机构 SSO、验证码、付费授权、真实 DOM/重定向和真实下载。该风险不能替代离线代码安全门禁，也不能宣称 A10/A11 已通过；应在受控环境安装计划版本 Playwright 并由用户提供合法权限样本完成真实验收。

## 验证记录

### Task06 + Task05 定向回归（连续三次）

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

三次结果均为：`206 passed, 5 warnings, 8 subtests passed`，退出码均为 0。警告为既有 PyMuPDF/Swig deprecation warning；测试期间观测 exporter 的本地连接重试不影响退出码。

### 静态与运行时检查

- Task06/Task05 目标实现与测试 `compileall`：通过。
- `git diff --check`：通过。
- 全仓冲突标记扫描（排除 `.git`、`.venv`、`__pycache__`）：0 命中。
- OpenAPI 路径核对：规范 canonical 路径均已暴露；存在 alias 路径的重复 operation-id 警告，但不改变路径匹配。
- `git check-ignore -v`：profile、Cookies 及搜索 SQLite 均被忽略。
- `git ls-files`：未发现 profile、HAR、Cookies、搜索状态 SQLite 等敏感运行文件。

## 复核结论

批次状态机、条目会话归属、canonical route、服务端快照 TTL、parser 凭证边界、录制产物禁止和 Git 忽略规则均有实质修复与离线回归；但 S1/S2 仍违反明确安全硬约束，且真实 A10/A11 环境验收不可执行。因此本轮不签署 Task06 整体安全放行。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-04
