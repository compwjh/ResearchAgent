# 技术评审：Spec 015 Task06 批量导入与登录续传（整体复核）

- 评审角色：Tech Lead（当前协作 Agent）
- 评审时间：2026-09-04
- 复核依据：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`、Task06 批次/浏览器/解析切片报告，以及当前 domain/store/service/browser/parser/routes/schemas 实现
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task06-overall-20260904.md`
- 约束：仅新增本报告与日志；未修改业务代码、测试、spec 或 Git，未提交、未 push、未 reset/stash/clean

## 固定字段

- 结论：**打回（整体 Task06 暂不放行）**
- 阻塞：**有**；见下表 B1–B6。批次状态机切片本身维持既有通过结论，但核心登录续传和规范 API 尚未形成可交付闭环。
- 测试：**186 passed，5 warnings，8 subtests passed，退出码 0**（`.venv/bin/python -m pytest -q`，Task06 相关批次 store/service/API、browser manager、ACM/IEEE parser、paper import/identity、KB 与 paper-discovery API 集合，13.98s）
- 编译：**通过**；目标 domain/service/browser/parser/routes/schemas 与测试 `compileall` 退出码 0
- 差异检查：**通过**；`git diff --check` 退出码 0；全仓冲突标记扫描（排除 `.git`、`.venv`、`__pycache__`）0 命中
- 签字：**Tech Lead（当前协作 Agent）：打回**

## 结论摘要

批次 domain/store/service 的状态迁移、真实状态聚合、租约 owner CAS、15 分钟租约与 5 分钟续租门禁、过期恢复、失败/等待登录逐项隔离、重试/取消边界、幂等身份索引和 20 项硬上限与既有最终切片报告一致，当前定向测试未见回退。

Browser manager 的 headed persistent profile、profile 文件锁、ACM/IEEE 精确 origin allowlist、健康字段收敛和基础敏感产物禁用测试通过；ACM/IEEE parser 的 HTTPS origin、PDF 请求筛选、Cookie/Authorization 及认证查询拒绝测试通过。

但这些组件目前是孤立切片：规范要求的批量/健康/login API 路径没有完整实现，`resume` 没有把登录后的 Playwright 认证上下文接入实际下载/解析链路。因此不能据此宣称 ACM 或 IEEE 登录续传已完成。

## 阻塞问题

| 编号 | 等级 | 代码事实 | 修复方向 |
|---|---|---|---|
| B1 | P1 | Spec 015 要求 `GET /api/papers/imports/{batch_id}`、`POST /api/papers/imports/{batch_id}/retry`、`GET /api/papers/browser/health` 和 `POST /api/papers/import-items/{item_id}/login`（spec:139–146）。OpenAPI 实际仅暴露 `/api/papers/import-batches...`、`/api/papers/browser-health` 和 `/api/papers/login/open`；规范的 3 个路径缺失。批量创建也与单篇 `POST /api/papers/imports` 复用路径冲突。批量状态/重试/取消/resume/login 返回均未声明 Pydantic `response_model`。 | 按 spec 固定路径和输入/输出模型；保留单篇与批量的无歧义路由设计，补齐规范路径兼容测试和错误体测试。 |
| B2 | P0 | 登录打开接口（`routes.py:724–739`）只接受客户端 `site/article_url`，按站点写入一个全局 session。resume（`routes.py:688–695`）先 `session.close()`，随后 `PaperImportBatchService.resume_item`（`paper_import_batch_service.py:424–436`）仍调用普通 `import_candidate`；该调用链没有 Playwright context、parser 或受控认证请求参数。认证后的 Cookie/请求上下文未用于下载，合法登录后无法证明会导入受保护 PDF。 | 以 `item_id` 从服务端候选快照解析站点/文章 URL；将 login session 与 item 绑定；resume 在不向 API/日志暴露凭证的前提下通过受控 Playwright 请求或安全适配器完成解析和下载，并补充端到端注入测试。 |
| B3 | P1 | 当前 login/open 可让客户端指定任意同源 ACM/IEEE URL，且全局 `paper_browser_sessions[site]` 只能保存一个站点会话；开启 item B 会覆盖 item A，resume A 可能取到 B 的 session。该行为不满足“条目级登录续传”和并发 resume 单一归属。 | login endpoint 只接受 `item_id`；由服务端读取 waiting_login 条目的候选地址和站点；session key 至少包含 item_id，并用条件更新/租约保护 resume。 |
| B4 | P1 | create/single import 路径检查 `SearchSession.expires_at`，但 retry 的 `_paper_server_snapshot`（`routes.py:565–577`）和 resume 的 `_paper_snapshot_for_item`（`routes.py:580–593`）只读取候选，不检查会话过期；service 的 `_snapshots_for` 也不补做 TTL 校验。过期搜索会话仍可能进入 retry/resume。 | retry/resume 共用同一个服务端快照校验函数，统一拒绝过期或损坏 session，并增加“创建后过期再 retry/resume”测试。 |
| B5 | P1 | `PaperBrowserManager` 只从 launch options 移除 `record_har`、`record_video_dir`、`downloads_path`（`paper_browser_manager.py:277–283`），没有移除实际 Playwright 的 `record_har_path`；`validate_origin`（`:230–233`）只检查 origin，不拒绝认证查询参数。另 `.gitignore`（:19–23）没有忽略 `data/browser-profile/` 或 `data/paper_search/`，工作树已出现 `data/browser-profile/security-papers/.profile.lock`，profile 不满足“不纳入 Git”。 | 禁止全部真实 HAR/trace/video/download 产物参数，复用统一认证查询拒绝规则；将 profile、搜索状态和锁文件加入忽略规则并补 `git check-ignore` 门禁。 |
| B6 | P1 | 批量 service 将异常或 importer 返回的 message 直接写入 item（`paper_import_batch_service.py:298–303,315–318,324–327`）；API 的 `_paper_batch_error_response`/`_safe_import_error_message` 只在部分响应路径按关键词清理。单篇 `_paper_import_error_response` 直接使用异常 message（`routes.py:448–457`）。任意注入的 URL、Cookie、Authorization 或令牌文本不应依赖关键词过滤后才安全。 | 在持久化、观测和 API 三层使用统一 allowlist 错误码与固定安全消息；禁止输出原始异常文本、完整 URL、查询参数和凭证头；补充每个错误路径的脱敏断言。 |

## 逐项技术复核矩阵

| 复核项 | 结论 | 证据与边界 |
|---|---|---|
| 状态机/聚合 | 通过（切片） | `paper_import_batch.py` 的迁移集合覆盖 queued→downloading→validating→indexing→completed 与 waiting_login 分支；store 从条目真实状态聚合批次计数。既有最终切片报告及相关测试通过。 |
| 租约/恢复 | 通过（切片） | 活动态 transition/mark-failed 需要 owner 与未过期条件；renew 有 300 秒门禁；recover 仅处理过期 downloading/validating/indexing 并写 `IMPORT_INTERRUPTED`。旧 worker、299/300 秒、并发 CAS 测试通过。 |
| 批量隔离/幂等 | 通过（切片） | 公开项继续执行，LOGIN_REQUIRED 只暂停当前项；retry/resume/claim 由条件更新保护；去重后 20 项硬上限和有效状态 partial unique indexes 测试通过。 |
| Browser profile/allowlist | 部分通过 | headed、固定超时、profile 所有权/文件锁、精确 ACM/IEEE origin 与基础产物选项 fake 测试通过；B3、B5 的条目归属、认证 query 和真实 HAR 参数仍阻塞。 |
| ACM parser 凭证边界 | 通过（单元切片） | 仅接受 `https://dl.acm.org`，拒绝 query/userinfo/fragment/非 GET 与 Cookie/Authorization header；只返回安全元数据和 allowlisted PDF URL。未接入登录下载。 |
| IEEE parser 凭证边界 | 通过（单元切片） | 仅接受精确 IEEE HTTPS origin，拒绝认证 query 与 Cookie/Authorization request header；DOM 变化返回稳定 retryable 错误。未接入登录下载。 |
| API 错误/脱敏 | 不通过 | 统一错误体 helper 和部分单篇/批量输出测试通过，但规范路径缺失、response model 缺失，且 B6 的原始 message 仍可进入持久化或单篇响应。 |
| Feature toggle | 部分通过 | 当前实际 Task06 路由在进入业务后均检查 `PAPER_DISCOVERY_ENABLED`（create/status/retry/cancel/resume/browser/login）；开关关闭时已测到业务端点返回 `503 PAPER_DISCOVERY_DISABLED`。但 FastAPI 参数校验先于路由，因此无效请求仍先返回 422；已有浏览器 session/进行中任务不会因环境开关自动关闭或停止，需明确并补充回滚行为。 |
| 观测 | 不通过/缺口 | Task06 计划要求记录批次/条目、状态、耗时、站点域名和错误码（plan:41）；当前 batch service 未接入 `start_trace`/状态事件等任务级观测。 |

## 测试与验证记录

### 执行命令

```text
.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_browser_manager.py tests/test_acm_paper_parser.py tests/test_ieee_paper_parser.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_kb_routes.py tests/test_kb_services.py tests/test_paper_discovery_api.py
```

结果：`186 passed, 5 warnings, 8 subtests passed in 13.98s`，退出码 0。系统 Python 的同一集合因环境缺少 `fastapi` 在 API 收集阶段失败；未修改环境，最终以项目虚拟环境完成验证。

### 静态与契约检查

- 目标实现与测试 `compileall`：退出码 0。
- `git diff --check`：退出码 0。
- 冲突标记扫描：0 命中。
- OpenAPI 路由核对确认 B1；实际暴露路径包含 `POST /api/papers/import-batches`、`GET/POST /api/papers/import-batches/{batch_id}...`、`GET /api/papers/browser-health`、`POST /api/papers/login/open`，而非 spec 的完整路径集合。
- 未执行真实 ACM/IEEE 合法账户登录、机构 SSO、验证码或付费权限验证；环境未提供可核验合法账户，本项作为验收前置风险记录，不伪造通过。

## 放行前最小修订清单

1. 对齐 spec 的批量、健康和 item login/resume API 路径、输入/响应 Pydantic 模型与错误映射。
2. 形成真正的 login→resume→受控下载/解析→知识库导入链路；session 按 item 绑定，不接受客户端 URL 作为登录目标。
3. retry/resume 统一校验 search session TTL；补过期场景回归。
4. 完整禁用 Playwright credential-bearing artifacts（包括 `record_har_path`），拒绝认证查询，并保护 profile/state 路径不进入 Git。
5. 统一错误码/安全消息，持久化、异常、观测和 API 输出均不得携带凭证或带令牌 URL。
6. 补 Task06 任务级 spec-013 观测，并在修复后由 tester 以合法账户执行 ACM/IEEE A10/A11 及浏览器崩溃、取消、无权限和页面变化验收。

## 签字

- Tech Lead（当前协作 Agent）：**打回**
- 签字时间：2026-09-04
