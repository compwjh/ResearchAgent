# 验收评审：Spec015 Task06 最新安全修复最终复核

- 评审角色：测试（tester）
- 关联计划：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
- 关联既有报告：`docs/sdd/reviews/015-task06-acceptance-review-final-security.md`、`docs/sdd/reviews/015-task06-acceptance-review-overall.md`
- 复核实现：`backend/app/services/paper_browser_manager.py`、`backend/app/services/paper_import.py`、`backend/app/services/paper_import_batch_service.py`、`backend/app/services/paper_import_batch_store.py`、`backend/app/api/routes.py`、`backend/app/api/schemas.py`
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task06-security-recheck-20260904-205536.md`
- 评审时间：2026-09-04（Asia/Shanghai）
- 变更约束：未修改业务代码、测试、配置或既有文件；仅新增本报告与进展日志；未执行 commit/push/reset/stash/clean。

## 固定字段

- 结果状态和摘要：**离线安全复核通过；整体验收不通过（环境限制）**。此前 S1 认证 URL/重定向边界与 S2 异常原文泄漏均已由当前实现和回归测试闭环；真实 ACM/IEEE 登录续传仍无法执行，不能替代验收标准。
- 改动文件：**无业务改动**（仅新增本报告与进展日志）。
- 测试命令/退出码/结果：见下文；定向 `212 passed`，全量 `502 passed`，均退出码 0。
- 产物路径：本报告与 `.codebuddy/agent-logs/tester-spec015-task06-security-recheck-20260904-205536.md`。
- 决策依据：离线安全断言全部通过，真实外站 A10/A11 因 Playwright/账号不可用未执行；按计划要求不得伪造通过。
- 风险与阻塞：真实 ACM Digital Library / IEEE Xplore headed 登录、SSO/验证码/付费授权、真实 DOM、认证 PDF 续传未验证；当前环境 `.venv` 未安装 Playwright，也无可核验合法账户。
- 主 Agent 后续动作：保留整体验收阻塞状态；具备合法测试账号与固定 Playwright 运行环境后执行真实 A10/A11，并由 tester 更新本报告结论；在此之前不得把 Task06 标记为已完成。
- 开始/结束/总耗时：约 2026-09-04 20:39 至 20:55（Asia/Shanghai），约 16 分钟（含定向、全量回归及静态安全检查）。
- 可用时模型/token/工具统计：本地 QA 代理；未提供可核验的 token 计数；使用项目虚拟环境 pytest、编译检查、Git 只读检查与文本扫描工具。全程未调用外部站点或真实账号。

## 一、测试命令与结果

### 1. Task05/Task06 定向全套回归

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

- 沙箱内首次执行：2 条 browser fake 用例受 DNS 沙箱限制，未发出请求即失败；未修改任何文件。
- 获准的沙箱外网络解析环境重跑：退出码 **0**；`212 passed, 5 warnings, 8 subtests passed in 6.15s`。
- 5 个 warning 为既有 PyMuPDF/Swig 依赖弃用警告。

### 2. 全量回归

```text
.venv/bin/python -m pytest -q
```

- 退出码 **0**；`502 passed, 5 warnings, 33 subtests passed in 106.48s`。

### 3. 安全断言子集

```text
.venv/bin/python -m pytest -q \
  tests/test_paper_browser_manager.py -k 'authenticated_pdf_request or headed_context or origin_allowlist or same_profile or cancel_and_close' \
  tests/test_paper_download_security.py -k 'authentication or redirect or dns'
```

- 退出码 **0**；`6 passed, 44 deselected in 0.82s`。
- 其余隔离、TTL、批量状态机、服务端 snapshot、单篇/批量脱敏断言已包含在上述 212 项和全量回归中。

## 二、安全验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| canonical imports/retry/login/resume | 通过（离线） | `routes.py` 暴露 `POST /api/papers/imports`、`GET/POST /api/papers/imports/{batch_id}`（含 retry）、item login/resume；兼容旧路径不改变 canonical 路径。 |
| 服务端 snapshot、auth query/redirect 拒绝 | 通过 | login/resume 由 item → batch → search session → candidate 快照解析，不接受客户端 URL；browser 下载拒绝认证 query，使用 `max_redirects=0`，逐跳重新执行站点 allowlist/DNS/HTTPS 校验；fake redirect 与 token query 测试通过。 |
| item 隔离与 resume 幂等 | 通过 | session map 以 `item_id` 为键，resume 只读取当前 item 会话；store 使用状态条件更新，批量/服务并发、旧租约越权、retry/resume CAS 测试通过。 |
| TTL / 过期搜索会话 | 通过 | 服务端 snapshot 在导入、retry、resume 前检查过期时间；过期会话返回稳定 `SEARCH_EXPIRED`，不触发外部请求；相关 API/service 测试通过。 |
| 错误脱敏 | 通过 | importer/service/store/API 统一以稳定错误码和固定安全消息持久化/返回；单篇、批量、浏览器异常不会转发 URL、Cookie、Authorization、password 或 token 原文；相关断言通过。 |
| profile / HAR / 下载产物安全 | 通过（离线） | headed 模式固定 `headless=false`、`accept_downloads=false`；HAR、video、downloads 选项被移除；profile 目录/锁文件权限分别约束为 0700/0600，`.gitignore` 命中 browser profile 与 search state，未发现已跟踪敏感产物。 |
| 浏览器健康响应 | 通过（离线） | 健康响应仅包含 `available/version/supported_sites/reason`，不含 profile、Cookie 或认证状态明细；Playwright 缺失时稳定返回 `BROWSER_UNAVAILABLE`。 |
| 公共 PDF 降级与 Task05 回归 | 通过 | Task05 下载、导入、身份去重和 KB 相关测试均纳入 212 项/502 项回归；浏览器不可用不阻断公开路径。 |
| 真实 ACM/IEEE 登录续传 | 未执行，环境阻塞 | 当前环境未安装 Playwright，且无可核验 ACM/IEEE 合法账号；未将真实 headed 登录、SSO/验证码、付费授权和真实受保护 PDF 导入标记为通过。 |

## 三、静态与产物检查

- `compileall`（Task06 目标实现与 API/schema）：退出码 **0**。
- `git diff --check`：退出码 **0**。
- 全仓冲突标记扫描（排除 `.git`/`.venv`）：**0 命中**。
- `.gitignore`：`data/browser-profile/`、`data/paper_search/` 与 profile lock 规则命中。
- 已跟踪敏感运行产物扫描：未发现 browser profile、HAR、Cookie 文件。

## 四、签字

- 测试（tester）：**离线安全复核通过；整体验收不通过（真实外站环境限制）**。
- Tech Lead 签字：待复核。
- 签字时间：2026-09-04。
