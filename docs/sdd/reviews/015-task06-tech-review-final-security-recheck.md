# Spec015 Task06 最终安全修复复核

- 评审角色：Tech Lead（当前协作 Agent）
- 评审时间：2026-09-04（Asia/Shanghai）
- 复核依据：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`、`docs/sdd/reviews/015-task06-tech-review-final-security.md`、`backend/app/services/paper_browser_manager.py`、`backend/app/services/paper_import.py`、`backend/app/api/routes.py`、`backend/app/api/schemas.py` 及 Task05/06 定向测试
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task06-security-recheck-20260904-203009.md`
- 约束：未修改业务代码、测试或 Git；未执行 commit/push/reset/stash/clean

## 结果状态和摘要

- 结论：**通过（离线安全修复复核）**。
- 前次评审的 S1（认证请求绕过 URL/重定向安全策略）与 S2（异常原文进入持久化/API）均已关闭。
- Task06 端到端真实 ACM/IEEE 登录续传仍不能宣称完成，原因是当前 `.venv` 未安装 Playwright；该环境限制不构成当前离线安全代码复核打回，但阻塞真实账户验收。

## 改动文件

- **无**。本次只读取实现/测试，并新增本复核报告与进展日志。

## 测试命令/退出码/结果

定向 Task05/06 全套回归（退出码 0）：

```text
.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_browser_manager.py tests/test_acm_paper_parser.py tests/test_ieee_paper_parser.py tests/test_paper_download.py tests/test_paper_download_security.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_kb_routes.py tests/test_kb_services.py tests/test_paper_discovery_api.py
```

结果：`212 passed, 5 warnings, 8 subtests passed in 5.99s`。警告为既有 PyMuPDF/Swig deprecation warning。

其他检查：

- `.venv/bin/python -m compileall -q backend tests`：退出码 0。
- `git diff --check`：退出码 0。
- 全仓冲突标记扫描：0 命中（`rg` 无匹配时返回 1，属于预期）。
- `.venv/bin/python -c 'import importlib.util; ... playwright ...'`：模块不存在；未执行真实浏览器。

## 产物路径

- 本报告：`docs/sdd/reviews/015-task06-tech-review-final-security-recheck.md`
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task06-security-recheck-20260904-203009.md`

## 决策依据

1. `paper_browser_manager.py:194-200,290-300` 的认证下载先复用 `validate_url`；共享安全层拒绝认证 query、userinfo、fragment、非 HTTPS/非 allowlist 目标，并执行 DNS 公网地址检查。
2. `paper_browser_manager.py:223-249` 每次请求显式传 `max_redirects=0`，收到 3xx 后仅手动读取 `Location`，通过 `validate_redirect_target` 和当前 ACM/IEEE 精确 origin 校验后才发起下一跳；目标跳出 allowlist 或超限均返回稳定 `DOWNLOAD_BLOCKED`。
3. `paper_import.py:59-95` 建立稳定错误码到固定消息映射；`paper_import_batch_service.py:322-381` 不再持久化 importer/transport 异常原文；`routes.py:364-368,500-523,535-539` 对单篇、批量状态和浏览器错误使用安全响应边界。回归测试覆盖 URL/Cookie/Authorization/password/token 伪造异常。
4. canonical API 已存在于 `routes.py:658,672,685,747,773,814`；客户端不能提交 URL，路由由 batch → search session → candidate 服务端快照推导目标。旧 `import-batches`/`browser-health` 仅作兼容别名。
5. 登录会话按 `item_id` 存放和清理（`routes.py:104-106,755-811`）；登录/resume 前重新检查搜索会话 TTL 与 candidate 归属（`routes.py:613-631`），测试确认认证 downloader/context 只传当前 item。
6. profile 目录/锁有权限和所有权检查（`paper_browser_manager.py:403-413`），headed persistent context 强制 `headless=False`、`accept_downloads=False`，并剔除 HAR、video、downloads 产物参数（`paper_browser_manager.py:441-451`）。`.gitignore:18-22` 忽略 agent logs、profile、搜索数据库和 profile lock；当前 `git ls-files` 未发现敏感运行文件。

## 风险与阻塞

- **环境阻塞（真实验收）**：`.venv` 中 `import playwright` 返回 `None`，未执行真实 ACM/IEEE 合法账户、SSO、验证码、付费授权、真实 DOM、重定向及下载；需在受控环境安装计划版本 Playwright 后由用户提供合法权限样本验收。
- **低风险后续加固**：`routes.py:526-532` 的 `_safe_browser_error_message` 对 `BrowserManagerError` 使用关键词拒绝后截断；当前生产 manager 生成的消息均为固定安全文本，未发现现行路径泄漏，但未来新增自定义错误消息应改为按稳定 code 的固定 allowlist。
- **范围说明**：routes.py 中既有旧 `/api/agent/...` 下载/问答流程仍有历史 `str(error)` 分支；本次复核针对 Task05/06 canonical paper import/login/resume 路径，不将旧流程冒充为本任务修复证据。若统一安全策略覆盖旧流程，应另立修复任务。

## 主 Agent 后续动作

1. 将本报告与进展日志纳入 Task06 收口证据，并保持业务代码不变。
2. 在具备 Playwright 1.52.0 与合法权限样本的受控环境执行 ACM/IEEE 真实登录续传验收；记录 A10/A11 证据后再决定 Task06 整体验收状态。
3. 若要求全局错误消息安全一致性，另建范围明确的后续修复 spec，收紧 `_safe_browser_error_message` 并处理旧 `/api/agent/...` 路径。

## 开始结束总耗时

- 开始：2026-09-04T20:30:09+08:00
- 结束：2026-09-04T20:32:45+08:00
- 总耗时：约 2 分 36 秒

## 可用时模型/token/工具统计

- 模型：当前执行任务的 Agent 自身；本次未调用子代理或外部模型。
- Token：平台未提供本回合精确 token 计数。
- 工具：读取/检索与测试命令共 9 次 shell 调用；文件落盘 2 次 apply_patch；未使用网络、GUI 或破坏性 Git 操作。

## Tech Lead 签字

- **开发主管（Tech Lead）：当前协作 Agent，签字：通过（离线安全修复复核）**
- 签字时间：2026-09-04
