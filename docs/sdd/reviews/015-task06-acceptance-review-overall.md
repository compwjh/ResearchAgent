# 验收评审：Spec 015 Task06 批量导入与登录续传（整体验收）

> 评审角色：测试（tester）
> 关联计划：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
> 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
> 关联历史报告：`docs/sdd/reviews/015-task06-acceptance-review-final.md`、`docs/sdd/reviews/015-task06-tech-review-final.md`
> 进展日志：`.codebuddy/agent-logs/tester-spec015-task06-overall-acceptance-20260904.md`
> 评审时间：2026-09-04（Asia/Shanghai）
> 变更约束：本轮未修改业务代码、测试代码或既有文件；仅新增本报告与进展日志；未提交、未 push、未 reset/stash/clean。

## 结论：不通过（A10/A11 真实外站登录续传阻塞）

当前批次状态机、并发幂等、重启恢复、20 项上限、浏览器健康契约、站点 parser 安全边界和 API 脱敏均有测试或临时验证证据；但验收标准要求使用合法权限样本完成 ACM Digital Library 与 IEEE Xplore 的真实浏览器登录续传，本环境无可用 ACM/IEEE 账户，且未安装 Playwright，无法执行 A10/A11。该两项不能伪造通过，因此 Task06 整体验收暂不通过。

## 一、测试命令与结果

1. Task06 定向测试（批次 store/service/API、browser manager、ACM/IEEE parser、论文 discovery API）：

   ```text
   .venv/bin/python -m pytest -q \
     tests/test_paper_import_batch_store.py \
     tests/test_paper_import_batch_service.py \
     tests/test_paper_import_batch_api.py \
     tests/test_paper_browser_manager.py \
     tests/test_acm_paper_parser.py \
     tests/test_ieee_paper_parser.py \
     tests/test_paper_discovery_api.py
   ```

   退出码：`0`；结果：`60 passed, 4 subtests passed in 1.30s`。连续执行 3 次均为 `60 passed, 4 subtests passed`，退出码均为 `0`。

2. 扩展论文/知识库相关回归：

   ```text
   .venv/bin/python -m pytest -q tests/test_paper_*.py tests/test_kb_routes.py tests/test_kb_services.py
   ```

   退出码：`0`；结果：`208 passed, 5 warnings, 8 subtests passed in 15.67s`。警告为既有 PyMuPDF/Swig deprecation warning。

3. 全量回归：

   ```text
   .venv/bin/python -m pytest -q
   ```

   退出码：`0`；结果：`492 passed, 5 warnings, 33 subtests passed in 100.84s`。测试过程中既有 Langfuse exporter 连接失败重试，但未造成测试失败。

临时批次脚本首轮曾将“含 waiting_login 的混合批次”误断言为 `partial_success`；按实现和状态契约，`waiting_login` 优先于部分成功状态，修正断言后同一检查全部通过。该过程异常仅发生在验收脚本断言，不涉及业务代码。

## 二、整体验收矩阵

| 验收项 | 状态 | 证据 |
|---|---|---|
| 批次逐项隔离与状态聚合 | 通过 | `backend/app/services/paper_import_batch_store.py:421-459` 按条目真实状态聚合；临时 SQLite 混合 `completed / waiting_login / failed / cancelled` 得到 `(total, completed, failed, waiting_login, cancelled)=(4,1,1,1,1)`，且批次状态按契约为 `waiting_login`，等待项不吞掉其他项结果。 |
| 公开项不被登录项阻塞 | 通过 | `backend/app/services/paper_import_batch_service.py:295-328,393-404` 将登录要求限定为当前 item，并使用逐项 futures；既有测试 `test_public_items_continue_when_one_item_requires_login` 通过。 |
| claim 并发单一执行者 | 通过 | `backend/app/services/paper_import_batch_store.py:101-134,512-525` 使用 `BEGIN IMMEDIATE` 和 `state='queued'` CAS；临时 8 线程验证仅 1 个成功者，未泄漏 raw `database is locked`。 |
| retry 并发幂等 | 通过 | `retry_item` 仅允许 `failed → queued`；临时 8 线程验证仅 1 个成功者，其余为预期状态冲突。 |
| resume 并发幂等 | 通过 | `backend/app/services/paper_import_batch_store.py:527-540` 仅允许 `waiting_login → downloading` CAS；临时 8 线程验证仅 1 个成功者。 |
| recover 并发幂等 | 通过 | `recover_expired_leases` 只处理过期活动租约；临时 8 线程验证仅 1 次返回 `1`、其余 7 次返回 `0`，最终 item 为 `failed/IMPORT_INTERRUPTED`。 |
| service 竞争调用观察最终状态 | 通过 | `backend/app/services/paper_import_batch_service.py:360-391,424-436` 对 claim/resume loser 有界轮询；定向回归连续 3 次通过，阻塞 importer 场景中 importer 只执行一次且竞争调用者均观察到 `completed`。 |
| 旧 worker 租约隔离 | 通过 | `paper_import_batch_store.py:480-505,558-580` 活动态更新要求 owner、状态和未过期租约；历史测试覆盖过期→retry→新 owner 后旧 owner transition/fail 被拒绝。 |
| 服务重启恢复 | 通过 | 临时关闭并重新创建 store 后，过期 `downloading` 被恢复为 `failed/IMPORT_INTERRUPTED`，再次打开 store 可读取该状态，retry 后回到 `queued`；实现见 `paper_import_batch_store.py:625-641`。 |
| 单批硬上限 20 项 | 通过 | `MAX_BATCH_ITEMS=20` 与构造器钳制见 `paper_import_batch_store.py:38-50,82-87`；先去重再限额见 `paper_import_batch_store.py:336-347`。临时验证 20 个唯一项加重复项成功，21 个唯一项返回 `BATCH_LIMIT_EXCEEDED`，`max_items=999` 也不能绕过。 |
| browser-health 契约 | 通过 | manager 只返回四字段见 `backend/app/services/paper_browser_manager.py:192-221`，路由白名单见 `backend/app/api/routes.py:702-710`；实际 HTTP `GET /api/papers/browser-health` 返回 200 和 `available/version/supported_sites/reason`，无 profile/Cookie 等字段。 |
| 浏览器不可用降级 | 通过 | 当前环境 Playwright import 不可用；实际健康接口稳定返回 `available=false`、`version=null`、`reason=BROWSER_UNAVAILABLE`，没有抛出内部异常。公开导入相关回归仍通过。 |
| login/open 仅接收 site/article_url 且不回显 | 通过（模拟） | `PaperLoginOpenRequest` 为 `extra="forbid"`，仅定义 `site`、`article_url`（`backend/app/api/schemas.py:91-97`）；路由响应仅返回 `status/site`，不返回 URL（`backend/app/api/routes.py:724-744`）。临时 HTTP 检查中附加 URL/Cookie/Authorization/password 字段均稳定 422，响应不含敏感值；fake browser open/resume 回归通过。真实打开因 Playwright 缺失未执行。 |
| ACM origin/认证参数/凭证头边界 | 通过（离线/注入） | ACM 精确 origin 与 URL 清洗见 `backend/app/services/acm_paper_parser.py:156-212`；Cookie/Authorization 请求头在 `:183-192` 拒绝，认证查询参数不返回为 PDF。现有 7 项 ACM 测试及临时 Cookie/Authorization、非精确 origin 检查通过。 |
| IEEE origin/认证参数/凭证头边界 | 通过（离线/注入） | IEEE URL allowlist 与认证参数拒绝见 `backend/app/services/ieee_paper_parser.py:178-204`，请求凭证头拒绝见 `:273-291`；现有 10 项 IEEE 测试及临时 token/authorization/session、Cookie/Authorization、非精确 origin 检查通过。 |
| API 不接受客户端 URL/Cookie/Authorization | 通过 | `PaperImportRequest`、`PaperImportBatchRequest`、`PaperLoginOpenRequest` 均 `extra="forbid"`（`backend/app/api/schemas.py:54-97`）；应用级校验映射见 `backend/app/api/routes.py:211-216`。临时 HTTP 检查覆盖单篇 import、batch create、login/open，均返回稳定 422，响应不含提交的 URL、Cookie、Authorization 或 password。 |
| API 错误响应脱敏 | 通过 | 批次异常消息含 cookie/authorization/password/token/secret/URL 时统一替换见 `backend/app/api/routes.py:485-493`；条目错误 URL/凭证脱敏见 `:496-508`。临时 HTTP 检查确认异常响应和状态 item 均不含 URL、token、Cookie、Authorization 值。 |
| ACM 真实登录续传（A10） | 阻塞 | 验收标准要求合法权限样本真实浏览器登录并导入知识库；本环境没有 ACM 凭证，且 `.venv` 中 `import playwright` 为 `ModuleNotFoundError`，未执行、未伪造通过。 |
| IEEE 真实登录续传（A11） | 阻塞 | 验收标准要求合法权限样本真实浏览器登录并导入知识库；本环境没有 IEEE 凭证，且 `.venv` 中 `import playwright` 为 `ModuleNotFoundError`，未执行、未伪造通过。 |

## 三、敏感信息扫描与边界说明

- 临时检查使用的值仅为测试用 `secret`；响应断言确认其不出现。没有读取、生成或保存真实密码、Cookie、Authorization、profile 内容或带令牌 URL。
- parser 通过注入 HTML/request fake 验证拒绝规则，不代表真实外站 DOM、机构 SSO、验证码、付费墙或下载限额已通过。
- 全量测试输出包含既有测试源码中的安全字段名称（用于断言拒绝），不包含真实凭证值；本轮新增日志只记录测试观察，不记录任何凭证。
- 浏览器 manager 的 fake 测试覆盖 headed、profile lock、origin allowlist、崩溃恢复和敏感录制选项禁用；真实 Playwright 生命周期因依赖缺失未执行。

## 四、阻塞解除条件

1. 在受控环境安装并验证固定版本 Playwright（计划要求 `1.52.0`），确保 headed 浏览器可启动。
2. 由用户在真实浏览器中提供合法 ACM Digital Library 与 IEEE Xplore 权限样本，分别完成登录、续传、知识库导入；测试只观察稳定状态和 `paper_id`，不接触密码或凭证内容。
3. 重跑 A10/A11 以及登录取消、无权限、浏览器崩溃、页面结构变化的真实验收；通过后再更新本报告结论。

## 五、签字

- 测试（tester）：**不通过（A10/A11 阻塞）**
- Tech Lead 签字：**待填**
- 签字时间：待定
